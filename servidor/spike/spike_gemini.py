"""SPIKE DESCARTÁVEL (Task 3): valida Pipecat + Gemini Live + Gemini TTS com a chave real.

NÃO é usado pelo servidor. Ainda não foi executado (sem GOOGLE_API_KEY no momento da escrita).

Uso (em servidor/, com o venv ativo):
    set GOOGLE_API_KEY=...            (PowerShell: $env:GOOGLE_API_KEY="...")
    python spike/spike_gemini.py --pergunta pergunta.wav --pedido pedido_codigo.wav

    pergunta.wav       -> 16 kHz mono 16 bits, ex.: "que horas são em Tóquio?"
    pedido_codigo.wav  -> 16 kHz mono 16 bits, ex.: "adicione uma tag de cupom na página de pedidos do ProximoTurno"

Saídas: resposta.wav (a), resposta_pedido.wav + log do handler (b), tts.wav (c).
Variáveis opcionais: MODELO_VOZ (padrão models/gemini-3.8-live), VOZ (Charon),
MODELO_TTS (gemini-3.8-flash-lite-tts), PROACTIVE_AUDIO (1).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import time
import wave

from google import genai
from google.genai import types
from google.genai.types import ProactivityConfig
from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import InputAudioRawFrame, LLMFullResponseEndFrame, LLMRunFrame, OutputAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transcriptions.language import Language
from pipecat.workers.runner import WorkerRunner

CHAVE = os.environ.get("GOOGLE_API_KEY", "")
MODELO_VOZ = os.environ.get("MODELO_VOZ", "models/gemini-3.8-live")
VOZ = os.environ.get("VOZ", "Charon")
MODELO_TTS = os.environ.get("MODELO_TTS", "gemini-3.8-flash-lite-tts")
PROATIVO = os.environ.get("PROACTIVE_AUDIO", "1") != "0"

PROMPT = (
    "Você é um assistente de voz em português do Brasil. Responda perguntas gerais de forma breve. "
    "Todo pedido de programação deve ir IMEDIATAMENTE à ferramenta tarefa_de_codigo com o pedido literal."
)


def ler_wav_16k(caminho: str) -> bytes:
    with wave.open(caminho, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2, (
            f"{caminho}: precisa ser PCM 16 bits mono 16 kHz"
        )
        return w.readframes(w.getnframes())


def salvar_wav(caminho: str, pcm: bytes, taxa: int) -> None:
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm)
    print(f"  salvo {caminho} ({len(pcm) / (taxa * 2):.1f} s @ {taxa} Hz)")


class Coletor(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.audio = bytearray()
        self.taxas: set[int] = set()
        self.fim = asyncio.Event()

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, OutputAudioRawFrame):
                self.audio.extend(frame.audio)
                self.taxas.add(frame.sample_rate)
            elif isinstance(frame, LLMFullResponseEndFrame) and self.audio:
                self.fim.set()
        await self.push_frame(frame, direction)


async def conversar(wav: str, saida: str) -> list[str]:
    chamadas: list[str] = []

    async def tarefa_de_codigo(params: FunctionCallParams):
        pedido = params.arguments.get("pedido")
        print(f"  >>> handler tarefa_de_codigo chamado: pedido={pedido!r}")
        chamadas.append(str(pedido))
        await params.result_callback({"resultado": "Tarefa enviada ao Claude Code. Avise o usuário em uma frase curta."})

    settings = GeminiLiveLLMService.Settings(
        model=MODELO_VOZ, voice=VOZ, language=Language.PT_BR, system_instruction=PROMPT
    )
    if PROATIVO:
        settings.proactivity = ProactivityConfig(proactive_audio=True)
    llm = GeminiLiveLLMService(
        api_key=CHAVE,
        settings=settings,
        tools=ToolsSchema(
            standard_tools=[
                FunctionSchema(
                    name="tarefa_de_codigo",
                    description="Envia um pedido de programação ao Claude Code.",
                    properties={"pedido": {"type": "string", "description": "Pedido literal do usuário."}},
                    required=["pedido"],
                )
            ]
        ),
        inference_on_context_initialization=False,
    )
    llm.register_function("tarefa_de_codigo", tarefa_de_codigo)

    contexto = LLMContext()
    agregadores = LLMContextAggregatorPair(contexto)
    coletor = Coletor()
    worker = PipelineWorker(
        Pipeline([agregadores.user(), llm, coletor, agregadores.assistant()]),
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
        idle_timeout_secs=None,
        enable_rtvi=False,
    )
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    tarefa = asyncio.create_task(runner.run())
    await worker.queue_frame(LLMRunFrame())

    t0 = time.monotonic()
    while not getattr(llm, "_ready_for_realtime_input", False):
        if time.monotonic() - t0 > 15:
            raise TimeoutError("Gemini Live não ficou pronto em 15 s")
        await asyncio.sleep(0.05)
    print(f"  sessão pronta em {time.monotonic() - t0:.2f} s")

    pcm = ler_wav_16k(wav) + b"\x00\x00" * 16000 * 2  # + 2 s de silêncio p/ o VAD fechar o turno
    for i in range(0, len(pcm), 640):  # tempo real, blocos de 20 ms
        await worker.queue_frame(InputAudioRawFrame(audio=pcm[i:i + 640], sample_rate=16000, num_channels=1))
        await asyncio.sleep(0.02)
    try:
        await asyncio.wait_for(coletor.fim.wait(), timeout=20)
    except asyncio.TimeoutError:
        print("  (nenhuma resposta completa em 20 s — com Proactive Audio o modelo pode ter ficado em silêncio)")
    await worker.cancel()
    await asyncio.wait_for(tarefa, 10)
    print(f"  taxas de saída observadas: {sorted(coletor.taxas)}")
    if coletor.audio:
        salvar_wav(saida, bytes(coletor.audio), next(iter(coletor.taxas)))
    return chamadas


async def tts(texto: str, saida: str) -> None:
    cliente = genai.Client(api_key=CHAVE, http_options={"api_version": "v1beta"})
    resp = await cliente.aio.models.generate_content(
        model=MODELO_TTS,
        contents=texto,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                language_code="pt-BR",
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOZ)),
            ),
        ),
    )
    parte = resp.candidates[0].content.parts[0]
    dados = parte.inline_data.data
    print(f"  TTS: mime={parte.inline_data.mime_type!r}, {len(dados)} bytes, começa com {dados[:4]!r}")
    if dados[:4] == b"RIFF":
        with wave.open(io.BytesIO(dados)) as w:
            print(f"  WAV: {w.getframerate()} Hz, {w.getnchannels()} canal(is)")
        open(saida, "wb").write(dados)
        print(f"  salvo {saida}")
    else:
        salvar_wav(saida, dados, 24000)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pergunta", default="pergunta.wav")
    ap.add_argument("--pedido", default="pedido_codigo.wav")
    args = ap.parse_args()
    if not CHAVE:
        sys.exit("Defina GOOGLE_API_KEY.")
    print(f"modelo de voz={MODELO_VOZ} voz={VOZ} proactive_audio={PROATIVO} tts={MODELO_TTS}")

    print("(a) pergunta geral")
    await conversar(args.pergunta, "resposta.wav")

    print("(b) pedido de código")
    chamadas = await conversar(args.pedido, "resposta_pedido.wav")
    print(f"  handler chamado {len(chamadas)}x: {chamadas}")

    print("(c) TTS")
    await tts("Pronto. Adicionei a tag de cupom na página de pedidos do ProximoTurno e abri o PR 42.", "tts.wav")


if __name__ == "__main__":
    asyncio.run(main())
