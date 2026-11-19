"""Sintetizador real: TTS do Gemini via ``google-genai`` (Gemini API / AI Studio).

Chamada confirmada no google-genai 3.4.0 e no ``GeminiTTSService`` do pipecat-ai 1.16.0
(ver docs/notas-pipecat.md): ``client.aio.models.generate_content`` com
``response_modalities=["AUDIO"]`` e ``speech_config``. O retorno vem em
``candidates[0].content.parts[*].inline_data.data``: PCM 16 bits mono 24 kHz
cru, ou WAV (os modelos 3.8 devolvem WAV por padrão em chamadas não-streaming).
"""

from __future__ import annotations

import io
import logging
import re
import wave

from google import genai
from google.genai import types

from voz.config import Config
from voz.protocolo import TAXA_SAIDA
from voz.sessao_pipecat import reamostrar

log = logging.getLogger(__name__)

HTTP_OPTIONS = types.HttpOptions(api_version="v1beta")


def pcm_de_resposta(dados: bytes, mime_type: str | None = None) -> bytes:
    """Normaliza o áudio do TTS para PCM 16 bits mono 24 kHz."""
    if dados[:4] == b"RIFF" and dados[8:12] == b"WAVE":
        with wave.open(io.BytesIO(dados), "rb") as w:
            taxa = w.getframerate()
            canais = w.getnchannels()
            pcm = w.readframes(w.getnframes())
        if canais != 1:
            import numpy as np

            pcm = np.frombuffer(pcm, dtype="<i2").reshape(-1, canais).mean(axis=1).astype("<i2").tobytes()
        return reamostrar(pcm, taxa, TAXA_SAIDA)
    taxa = TAXA_SAIDA
    if mime_type:
        m = re.search(r"rate=(\d+)", mime_type)
        if m:
            taxa = int(m.group(1))
    return reamostrar(dados[: len(dados) - len(dados) % 2], taxa, TAXA_SAIDA)


class TTSGemini:
    def __init__(self, config: Config):
        self._config = config
        # v1beta é obrigatório: na v1 (padrão do google-genai) não existem speech_config
        # nem os modelos de TTS/Live (a API responde 400 "Unknown name speechConfig").
        self._cliente = (
            genai.Client(api_key=config.google_api_key, http_options=HTTP_OPTIONS)
            if config.google_api_key
            else None
        )

    async def sintetizar(self, texto: str) -> bytes:
        if self._cliente is None:
            raise RuntimeError("GOOGLE_API_KEY não definido; o TTS do Gemini não está disponível")
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                language_code="pt-BR",
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self._config.voz_tts)
                ),
            ),
        )
        resposta = await self._cliente.aio.models.generate_content(
            model=self._config.modelo_tts,
            contents=[types.Content(role="user", parts=[types.Part(text=texto)])],
            config=config,
        )
        audio = bytearray()
        mime = None
        for candidato in resposta.candidates or []:
            if not candidato.content or not candidato.content.parts:
                continue
            for parte in candidato.content.parts:
                if parte.inline_data and parte.inline_data.data:
                    mime = mime or parte.inline_data.mime_type
                    audio.extend(parte.inline_data.data)
            break
        if not audio:
            raise RuntimeError(f"o TTS ({self._config.modelo_tts}) não devolveu áudio")
        log.info("TTS gerou %d bytes (%s)", len(audio), mime)
        return pcm_de_resposta(bytes(audio), mime)
