"""Só importa e constrói as implementações reais, sem rede (não há chave do Gemini nos testes)."""

import numpy as np

from voz.config import Config
from voz.interfaces import EventosSessao

CONFIG = Config(token_placa="t", google_api_key="chave-falsa")


async def _audio(pcm):
    pass


async def _fim():
    pass


async def _pedido(p):
    return "ok"


EVENTOS = EventosSessao(ao_audio=_audio, ao_fim_resposta=_fim, ao_pedido_codigo=_pedido)


def test_sem_prompt_fixo_no_codigo():
    import voz.sessao_pipecat as m

    assert not hasattr(m, "PROMPT_SISTEMA")


def test_fabrica_gemini_cria_sessao_sem_rede():
    from voz.sessao_pipecat import FabricaSessaoPipecat, SessaoPipecat

    sessao = FabricaSessaoPipecat(CONFIG).criar(EVENTOS)
    assert isinstance(sessao, SessaoPipecat)
    llm = sessao.criar_llm()
    assert type(llm).__name__ == "GeminiLiveLLMService"


def test_fabrica_openai_cria_servico_sem_rede():
    from voz.sessao_pipecat import FabricaSessaoPipecat

    config = Config(token_placa="t", google_api_key="", provedor_voz="openai", modelo_voz="m", voz="marin", openai_api_key="o")
    llm = FabricaSessaoPipecat(config).criar(EVENTOS).criar_llm()
    assert type(llm).__name__ == "OpenAIRealtimeLLMService"


def test_esquema_da_ferramenta():
    from voz.sessao_pipecat import ESQUEMA_TAREFA_DE_CODIGO

    assert ESQUEMA_TAREFA_DE_CODIGO.name == "tarefa_de_codigo"
    assert ESQUEMA_TAREFA_DE_CODIGO.required == ["pedido"]


def test_reamostrar_para_24k():
    from voz.sessao_pipecat import reamostrar

    pcm16 = (np.ones(1600) * 1000).astype("<i2").tobytes()  # 0,1 s a 16 kHz
    saida = reamostrar(pcm16, 16000, 24000)
    assert len(saida) == 2400 * 2
    assert reamostrar(pcm16, 24000, 24000) == pcm16


def test_tts_constroi_sem_rede():
    from voz.tts_gemini import TTSGemini, pcm_de_resposta

    TTSGemini(CONFIG)
    pcm = b"\x01\x00" * 10
    assert pcm_de_resposta(pcm) == pcm


def test_tts_remove_cabecalho_wav():
    import io
    import wave

    from voz.tts_gemini import pcm_de_resposta

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x05\x00" * 100)
    assert pcm_de_resposta(buf.getvalue()) == b"\x05\x00" * 100


def test_tts_reamostra_wav_de_outra_taxa():
    import io
    import wave

    from voz.tts_gemini import pcm_de_resposta

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x05\x00" * 1600)
    assert len(pcm_de_resposta(buf.getvalue())) == 2400 * 2


def test_monta_pipeline_sem_rede():
    from voz.sessao_pipecat import FabricaSessaoPipecat

    sessao = FabricaSessaoPipecat(CONFIG).criar(EVENTOS)
    worker = sessao.montar("Pronto, PR 12 aberto.")
    assert type(worker).__name__ == "PipelineWorker"


async def test_sumidouro_repassa_audio_e_fim():
    from pipecat.frames.frames import LLMFullResponseEndFrame, TTSAudioRawFrame
    from pipecat.processors.frame_processor import FrameDirection

    from voz.sessao_pipecat import SumidouroAudio

    recebido, fins = [], []

    async def ao_audio(pcm):
        recebido.append(pcm)

    async def ao_fim():
        fins.append(True)

    sumidouro = SumidouroAudio(EventosSessao(ao_audio=ao_audio, ao_fim_resposta=ao_fim, ao_pedido_codigo=_pedido))
    enviados = []

    async def push_frame(frame, direction=FrameDirection.DOWNSTREAM):
        enviados.append(frame)

    sumidouro.push_frame = push_frame
    # FrameProcessor.process_frame base exige setup; chamamos só a nossa lógica
    import pipecat.processors.frame_processor as fp

    original = fp.FrameProcessor.process_frame

    async def base_noop(self, frame, direction):
        return None

    fp.FrameProcessor.process_frame = base_noop
    try:
        await sumidouro.process_frame(TTSAudioRawFrame(audio=b"\x01\x00" * 160, sample_rate=16000, num_channels=1), FrameDirection.DOWNSTREAM)
        await sumidouro.process_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)
    finally:
        fp.FrameProcessor.process_frame = original
    assert len(recebido) == 1 and len(recebido[0]) == 240 * 2
    assert fins == [True]
    assert len(enviados) == 2


async def test_ciclo_de_vida_do_pipeline_com_llm_falso():
    """Roda o pipeline de verdade (WorkerRunner/PipelineWorker) com um LLM falso, sem rede."""
    import asyncio

    from pipecat.frames.frames import InputAudioRawFrame, LLMFullResponseEndFrame, TTSAudioRawFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    from voz.sessao_pipecat import SessaoPipecat

    class LLMFalso(FrameProcessor):
        _ready_for_realtime_input = True

        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            await self.push_frame(frame, direction)
            if isinstance(frame, InputAudioRawFrame):
                await self.push_frame(TTSAudioRawFrame(audio=frame.audio, sample_rate=16000, num_channels=1))
                await self.push_frame(LLMFullResponseEndFrame())

    recebido, fins = [], []

    async def ao_audio(pcm):
        recebido.append(pcm)

    async def ao_fim():
        fins.append(True)

    class SessaoTeste(SessaoPipecat):
        def criar_llm(self, memoria=None):
            return LLMFalso()

    sessao = SessaoTeste(CONFIG, EventosSessao(ao_audio=ao_audio, ao_fim_resposta=ao_fim, ao_pedido_codigo=_pedido))
    await asyncio.wait_for(sessao.iniciar(None), 10)
    await sessao.enviar_audio(b"\x01\x00" * 320)
    for _ in range(200):
        if fins:
            break
        await asyncio.sleep(0.01)
    await asyncio.wait_for(sessao.encerrar(), 10)
    assert fins == [True]
    assert sum(len(p) for p in recebido) == 480 * 2


def test_tts_gemini_usa_api_v1beta():
    # Na v1 o TTS falha com 400 "Unknown name speechConfig" (descoberto no spike).
    from voz.tts_gemini import HTTP_OPTIONS

    assert HTTP_OPTIONS.api_version == "v1beta"


async def _processar_isolado(processador, frames):
    """Roda só a lógica do processador (sem o setup do Pipecat) e devolve o que ele repassou."""
    import pipecat.processors.frame_processor as fp

    enviados = []

    async def push_frame(frame, direction=None):
        enviados.append(frame)

    processador.push_frame = push_frame
    original = fp.FrameProcessor.process_frame

    async def base_noop(self, frame, direction):
        return None

    fp.FrameProcessor.process_frame = base_noop
    try:
        for frame, direcao in frames:
            await processador.process_frame(frame, direcao)
    finally:
        fp.FrameProcessor.process_frame = original
    return enviados


async def test_coletor_pega_a_fala_do_usuario_que_sobe_do_llm():
    from pipecat.frames.frames import TranscriptionFrame
    from pipecat.processors.frame_processor import FrameDirection

    from voz.sessao_pipecat import ColetorTranscricaoUsuario

    falas = []

    async def ao_texto_usuario(t):
        falas.append(t)

    eventos = EventosSessao(ao_audio=_audio, ao_fim_resposta=_fim, ao_pedido_codigo=_pedido,
                            ao_texto_usuario=ao_texto_usuario)
    frame = TranscriptionFrame(text="Quanto é 2 mais 2?", user_id="", timestamp="")
    enviados = await _processar_isolado(ColetorTranscricaoUsuario(eventos), [(frame, FrameDirection.UPSTREAM)])
    assert falas == ["Quanto é 2 mais 2?"]
    assert enviados == [frame]  # o frame continua seu caminho


async def test_sumidouro_repassa_a_transcricao_do_modelo():
    from pipecat.frames.frames import TTSTextFrame
    from pipecat.processors.frame_processor import FrameDirection

    from voz.sessao_pipecat import SumidouroAudio

    textos = []

    async def ao_texto_modelo(t):
        textos.append(t)

    eventos = EventosSessao(ao_audio=_audio, ao_fim_resposta=_fim, ao_pedido_codigo=_pedido,
                            ao_texto_modelo=ao_texto_modelo)
    await _processar_isolado(SumidouroAudio(eventos), [
        (TTSTextFrame("Qua", aggregated_by="sentence"), FrameDirection.DOWNSTREAM),
        (TTSTextFrame("tro.", aggregated_by="sentence"), FrameDirection.DOWNSTREAM),
    ])
    assert textos == ["Qua", "tro."]


def test_memoria_entra_na_instrucao_de_sistema():
    from voz.sessao_pipecat import instrucao_sistema

    assert instrucao_sistema("Instruções.", None) == "Instruções."
    assert instrucao_sistema("Instruções.", "Trocas.") == "Instruções.\n\nTrocas."
    assert instrucao_sistema("", None) == ""


def test_instrucoes_lidas_do_arquivo_a_cada_sessao(tmp_path):
    from voz.sessao_pipecat import carregar_instrucoes

    arquivo = tmp_path / "INSTRUCTIONS.md"
    assert carregar_instrucoes(str(arquivo)) == ""  # sem arquivo: sem instruções, sem erro
    arquivo.write_text("versão 1", encoding="utf-8")
    assert carregar_instrucoes(str(arquivo)) == "versão 1"
    arquivo.write_text("versão 2", encoding="utf-8")
    assert carregar_instrucoes(str(arquivo)) == "versão 2"


def test_config_aponta_para_instructions_md_do_repositorio():
    from pathlib import Path

    assert Path(CONFIG.instrucoes_arquivo) == Path(__file__).resolve().parents[1] / "INSTRUCTIONS.md"
    assert Config.do_ambiente({"TOKEN_PLACA": "t", "GOOGLE_API_KEY": "g",
                               "INSTRUCOES_ARQUIVO": "/x/I.md"}).instrucoes_arquivo == "/x/I.md"


def test_monta_pipeline_com_memoria_sem_rede():
    from voz.sessao_pipecat import FabricaSessaoPipecat

    sessao = FabricaSessaoPipecat(CONFIG).criar(EVENTOS)
    assert type(sessao.montar(None, "Meu nome é Rafael.")).__name__ == "PipelineWorker"


# ------------------------------------------- busca no Google (ferramenta nativa do Gemini)

def _ferramentas_gemini(config):
    from pipecat.adapters.llm.schemas.tools_schema import AdapterType

    from voz.sessao_pipecat import FabricaSessaoPipecat

    sessao = FabricaSessaoPipecat(config).criar(EVENTOS)
    esquema = sessao.ferramentas()
    return [f.name for f in esquema.standard_tools], (esquema.custom_tools or {}).get(AdapterType.GEMINI, [])


def test_busca_google_ligada_por_padrao():
    padrao, nativas = _ferramentas_gemini(CONFIG)
    assert padrao == ["tarefa_de_codigo"]
    assert {"google_search": {}} in nativas


def test_busca_google_pode_ser_desligada():
    config = Config(token_placa="t", google_api_key="g", busca_google=False)
    padrao, nativas = _ferramentas_gemini(config)
    assert padrao == ["tarefa_de_codigo"] and nativas == []


# ------------------------------------------ INSTRUCTIONS.md do repositório (instruções)

def _instrucoes_repo() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / "INSTRUCTIONS.md").read_text(encoding="utf-8")


def test_instructions_md_orienta_ferramenta_de_codigo():
    texto = _instrucoes_repo()
    assert "tarefa_de_codigo" in texto and "literalmente" in texto


def test_instructions_md_orienta_buscar_informacao_atual():
    texto = _instrucoes_repo().lower()
    assert "busca" in texto and "atual" in texto


