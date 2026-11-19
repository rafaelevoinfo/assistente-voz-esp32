"""SessaoVoz real com Pipecat (Gemini Live; OpenAI Realtime como alternativa configurável).

APIs confirmadas no pipecat-ai 1.16.0 instalado (ver docs/notas-pipecat.md).
Pipeline: [agregador do usuário → LLM speech-to-speech → SumidouroAudio → agregador do assistente].
O áudio do mic entra com ``PipelineWorker.queue_frame(InputAudioRawFrame(...))``.
"""

from __future__ import annotations

import asyncio
import logging

import numpy as np
from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import (
    InputAudioRawFrame,
    LLMFullResponseEndFrame,
    LLMRunFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    TTSTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.llm_service import FunctionCallParams
from pipecat.workers.runner import WorkerRunner

from voz.config import Config
from voz.interfaces import EventosSessao
from voz.protocolo import TAXA_ENTRADA, TAXA_SAIDA

log = logging.getLogger(__name__)

PROMPT_SISTEMA = (
    "Você é um assistente de voz em português do Brasil. Responda perguntas gerais de forma breve e "
    "natural. Todo pedido relacionado a programação, código, sistemas, sites, bugs, deploy ou projetos "
    "de software deve ser enviado IMEDIATAMENTE à ferramenta tarefa_de_codigo, com o pedido do usuário "
    "copiado literalmente no parâmetro 'pedido'; nunca tente resolver programação por conta própria. "
    "Depois de chamar a ferramenta, confirme em uma frase curta. Se receber um contexto de mensagem "
    "anterior, o usuário pode estar respondendo a ela; responda apenas se a fala for dirigida a você ou "
    "relacionada ao assunto; caso contrário, fique em silêncio."
)

ESQUEMA_TAREFA_DE_CODIGO = FunctionSchema(
    name="tarefa_de_codigo",
    description=(
        "Envia um pedido de programação (código, sistemas, sites, bugs, deploy, projetos de software) "
        "ao Claude Code, que executa em segundo plano. Use para TODO pedido desse tipo."
    ),
    properties={
        "pedido": {
            "type": "string",
            "description": "O pedido do usuário, copiado literalmente, sem resumir nem reescrever.",
        }
    },
    required=["pedido"],
)

ESPERA_PRONTO_S = 15.0
ESPERA_ENCERRAR_S = 5.0


def reamostrar(pcm: bytes, de: int, para: int) -> bytes:
    """Reamostragem linear simples de PCM 16 bits mono."""
    if de == para or not pcm:
        return pcm
    amostras = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype="<i2").astype(np.float64)
    n_saida = int(round(len(amostras) * para / de))
    if n_saida <= 0:
        return b""
    x_saida = np.arange(n_saida) * (de / para)
    saida = np.interp(x_saida, np.arange(len(amostras)), amostras)
    return np.clip(np.round(saida), -32768, 32767).astype("<i2").tobytes()


def mensagem_de_contexto(contexto: str) -> dict:
    return {
        "role": "user",
        "content": (
            "Contexto: a última mensagem falada ao usuário (resultado de uma tarefa) foi: "
            f"\"{contexto}\". O usuário pode responder a ela agora. Não responda a esta mensagem; "
            "espere a fala do usuário."
        ),
    }


def instrucao_sistema(memoria: str | None) -> str:
    """PROMPT_SISTEMA + memória (CONTEXTO.md e últimas trocas), se houver."""
    return f"{PROMPT_SISTEMA}\n\n{memoria}" if memoria else PROMPT_SISTEMA


class ColetorTranscricaoUsuario(FrameProcessor):
    """Fica ANTES do LLM: o Gemini Live empurra a transcrição da fala do usuário para cima."""

    def __init__(self, eventos: EventosSessao, **kwargs):
        super().__init__(**kwargs)
        self._eventos = eventos

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.UPSTREAM and isinstance(frame, TranscriptionFrame) and frame.text:
            await self._eventos.ao_texto_usuario(frame.text)
        await self.push_frame(frame, direction)


class SumidouroAudio(FrameProcessor):
    """Repassa o áudio do modelo (em 24 kHz) e o fim de cada resposta para os eventos da sessão."""

    def __init__(self, eventos: EventosSessao, **kwargs):
        super().__init__(**kwargs)
        self._eventos = eventos
        self._falou = False

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, OutputAudioRawFrame):
                pcm = frame.audio
                if frame.num_channels != 1:
                    amostras = np.frombuffer(pcm, dtype="<i2").reshape(-1, frame.num_channels)
                    pcm = amostras.mean(axis=1).astype("<i2").tobytes()
                pcm = reamostrar(pcm, frame.sample_rate, TAXA_SAIDA)
                if pcm:
                    self._falou = True
                    await self._eventos.ao_audio(pcm)
            elif isinstance(frame, TTSTextFrame) and frame.text:
                await self._eventos.ao_texto_modelo(frame.text)
            elif isinstance(frame, LLMFullResponseEndFrame):
                if self._falou:
                    self._falou = False
                    await self._eventos.ao_fim_resposta()
        await self.push_frame(frame, direction)


class SessaoPipecat:
    def __init__(self, config: Config, eventos: EventosSessao):
        self._config = config
        self._eventos = eventos
        self._llm = None
        self._worker: PipelineWorker | None = None
        self._runner: WorkerRunner | None = None
        self._tarefa: asyncio.Task | None = None
        self._encerrada = False

    # ---------------------------------------------------------- provedor

    def criar_llm(self, memoria: str | None = None):
        """Cria o serviço speech-to-speech do provedor configurado (sem abrir conexão)."""
        c = self._config
        instrucao = instrucao_sistema(memoria)
        ferramentas = ToolsSchema(standard_tools=[ESQUEMA_TAREFA_DE_CODIGO])
        if c.provedor_voz == "gemini":
            from google.genai.types import ProactivityConfig
            from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
            from pipecat.transcriptions.language import Language

            settings = GeminiLiveLLMService.Settings(
                model=c.modelo_voz,
                voice=c.voz,
                language=Language.PT_BR,
                system_instruction=instrucao,
            )
            if c.proactive_audio:
                settings.proactivity = ProactivityConfig(proactive_audio=True)
            llm = GeminiLiveLLMService(
                api_key=c.google_api_key,
                settings=settings,
                tools=ferramentas,
                inference_on_context_initialization=False,
            )
        elif c.provedor_voz == "openai":
            from pipecat.services.openai.realtime import events
            from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService

            llm = OpenAIRealtimeLLMService(
                api_key=c.openai_api_key,
                settings=OpenAIRealtimeLLMService.Settings(
                    model=c.modelo_voz,
                    system_instruction=instrucao,
                    session_properties=events.SessionProperties(
                        instructions=instrucao,
                        audio=events.AudioConfiguration(output=events.AudioOutput(voice=c.voz)),
                        tools=ferramentas,
                    ),
                ),
            )
        else:
            raise ValueError(f"provedor de voz desconhecido: {c.provedor_voz}")
        llm.register_function("tarefa_de_codigo", self._ao_tarefa_de_codigo)
        return llm

    async def _ao_tarefa_de_codigo(self, params: FunctionCallParams) -> None:
        pedido = str(params.arguments.get("pedido", "")).strip()
        log.info("modelo chamou tarefa_de_codigo: %s", pedido)
        if not pedido:
            await params.result_callback({"resultado": "Pedido vazio; pergunte ao usuário o que ele quer."})
            return
        texto = await self._eventos.ao_pedido_codigo(pedido)
        await params.result_callback({"resultado": texto})

    # ------------------------------------------------------------ SessaoVoz

    def montar(self, contexto: str | None, memoria: str | None = None) -> PipelineWorker:
        """Monta o pipeline (sem conectar ao provedor)."""
        self._llm = self.criar_llm(memoria)
        mensagens = [mensagem_de_contexto(contexto)] if contexto else []
        contexto_llm = LLMContext(messages=mensagens)
        agregadores = LLMContextAggregatorPair(contexto_llm)
        pipeline = Pipeline(
            [
                agregadores.user(),
                ColetorTranscricaoUsuario(self._eventos),
                self._llm,
                SumidouroAudio(self._eventos),
                agregadores.assistant(),
            ]
        )
        self._worker = PipelineWorker(
            pipeline,
            params=PipelineParams(audio_in_sample_rate=TAXA_ENTRADA, audio_out_sample_rate=TAXA_SAIDA),
            idle_timeout_secs=None,
            enable_rtvi=False,
        )
        return self._worker

    async def iniciar(self, contexto: str | None, memoria: str | None = None) -> None:
        self.montar(contexto, memoria)
        self._runner = WorkerRunner(handle_sigint=False)
        await self._runner.add_workers(self._worker)
        self._tarefa = asyncio.create_task(self._runner.run(), name="sessao-pipecat")
        # Envia o contexto ao LLM; com inference_on_context_initialization=False ele não responde sozinho.
        await self._worker.queue_frame(LLMRunFrame())
        await self._esperar_pronto()

    async def _esperar_pronto(self) -> None:
        """Espera o provedor aceitar áudio (senão o início da fala seria descartado)."""
        limite = asyncio.get_running_loop().time() + ESPERA_PRONTO_S
        while asyncio.get_running_loop().time() < limite:
            if self._tarefa is not None and self._tarefa.done():
                erro = self._tarefa.exception() if not self._tarefa.cancelled() else None
                raise RuntimeError(f"pipeline terminou antes de ficar pronto: {erro}")
            # Atributo interno do GeminiLiveLLMService / OpenAIRealtimeLLMService (1.16.0).
            pronto = getattr(self._llm, "_ready_for_realtime_input", None)
            if pronto is None:
                pronto = getattr(self._llm, "_session", None) is not None or getattr(self._llm, "_websocket", None) is not None
            if pronto:
                return
            await asyncio.sleep(0.05)
        raise TimeoutError("o provedor de voz não ficou pronto a tempo")

    async def enviar_audio(self, pcm16k: bytes) -> None:
        if self._worker is None or self._encerrada:
            return
        await self._worker.queue_frame(
            InputAudioRawFrame(audio=pcm16k, sample_rate=TAXA_ENTRADA, num_channels=1)
        )

    async def encerrar(self) -> None:
        if self._encerrada:
            return
        self._encerrada = True
        if self._worker is not None:
            try:
                await self._worker.cancel(reason="sessão de voz encerrada")
            except Exception:
                log.exception("falha ao cancelar o pipeline")
        if self._tarefa is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._tarefa), timeout=ESPERA_ENCERRAR_S)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._tarefa.cancel()
            except Exception:
                log.exception("pipeline terminou com erro")


class FabricaSessaoPipecat:
    def __init__(self, config: Config):
        self._config = config

    def criar(self, eventos: EventosSessao) -> SessaoPipecat:
        return SessaoPipecat(self._config, eventos)
