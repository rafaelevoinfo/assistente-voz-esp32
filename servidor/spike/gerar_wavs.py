"""Gera os .wav de entrada do spike (16 kHz mono 16 bits) com o TTS do Gemini.

Uso (de dentro de servidor/):  python spike/gerar_wavs.py
Le a GOOGLE_API_KEY de servidor/.env (sem imprimi-la).
"""
import asyncio
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

for linha in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in linha and not linha.lstrip().startswith("#"):
        k, v = linha.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import wave  # noqa: E402

import numpy as np  # noqa: E402

from voz.config import Config  # noqa: E402
from voz.tts_gemini import TTSGemini  # noqa: E402

FRASES = {
    "pergunta.wav": "Que horas são em Tóquio agora?",
    "pedido_codigo.wav": "Adicione uma tag de cupom na página de pedidos do projeto Próximo Turno.",
}


def reamostrar_24k_para_16k(pcm: bytes) -> bytes:
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    n = int(len(a) * 16000 / 24000)
    b = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)
    return np.clip(b, -32768, 32767).astype(np.int16).tobytes()


async def main() -> None:
    tts = TTSGemini(Config.do_ambiente())
    for nome, frase in FRASES.items():
        pcm16 = reamostrar_24k_para_16k(await tts.sintetizar(frase))
        # 0,5 s de silencio antes e 1,5 s depois (VAD precisa perceber o fim da fala)
        pcm16 = b"\x00" * 16000 + pcm16 + b"\x00" * 48000
        with wave.open(str(Path(__file__).parent / nome), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm16)
        print(f"{nome}: {len(pcm16) / 32000:.1f} s")


asyncio.run(main())
