"""Simula a placa contra o servidor local (Task 7, passos 3 e 4).

    uvicorn voz.app:app --port 8000          (com .env real; CLAUDE_CMD pode apontar para o fake_claude)
    python scripts/teste_real.py --wav pergunta.wav [--token ...] [--url ws://localhost:8000/ws]

Conecta, envia hello e wake, faz streaming do .wav (16 kHz mono 16 bits) em tempo real,
em blocos de 20 ms, só enquanto o servidor pede ``listen``. Salva todo áudio recebido em
``saida.wav`` (24 kHz) e responde ``playback_done`` a cada ``audio_end`` (após a duração do
áudio, como o notebook faria). Termina após ``session_end`` (use --esperar-resultado para
continuar ouvindo resultados empurrados do Claude Code).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import wave

import websockets


def ler_wav(caminho: str) -> bytes:
    with wave.open(caminho, "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f"{caminho}: precisa ser PCM 16 bits mono 16 kHz")
        return w.readframes(w.getnframes())


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--url", default="ws://localhost:8000/ws")
    ap.add_argument("--token", default=os.environ.get("TOKEN_PLACA", ""))
    ap.add_argument("--saida", default="saida.wav")
    ap.add_argument("--esperar-resultado", type=float, default=0.0,
                    help="segundos extras para esperar resultados empurrados após o session_end")
    args = ap.parse_args()

    pcm = ler_wav(args.wav)
    recebido = bytearray()
    t0 = time.monotonic()

    def log(msg: str) -> None:
        print(f"[{time.monotonic() - t0:6.2f}s] {msg}")

    async with websockets.connect(f"{args.url}?token={args.token}", max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "fw": "teste"}))
        await ws.send(json.dumps({"type": "wake"}))
        log("-> hello, wake")

        ouvindo = asyncio.Event()
        enviado = 0
        bytes_audio_atual = 0
        fim_sessoes = 0
        prazo_final: float | None = None

        async def streaming():
            nonlocal enviado
            while enviado < len(pcm) + 16000 * 2 * 3:  # wav + 3 s de silêncio
                await ouvindo.wait()
                bloco = pcm[enviado:enviado + 640] if enviado < len(pcm) else b"\x00\x00" * 320
                await ws.send(bloco)
                enviado += 640
                await asyncio.sleep(0.02)
            log("fim do streaming do wav")

        async def playback_done_apos(segundos: float):
            await asyncio.sleep(segundos)
            await ws.send(json.dumps({"type": "playback_done"}))
            log("-> playback_done")

        tarefa_stream = asyncio.create_task(streaming())
        try:
            while True:
                timeout = None if prazo_final is None else max(0.1, prazo_final - time.monotonic())
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    break
                if isinstance(msg, bytes):
                    recebido.extend(msg)
                    bytes_audio_atual += len(msg)
                    continue
                dados = json.loads(msg)
                tipo = dados.get("type")
                log(f"<- {dados}")
                if tipo == "listen":
                    ouvindo.set()
                elif tipo == "stop_listen":
                    ouvindo.clear()
                elif tipo == "audio_start":
                    ouvindo.clear()
                    bytes_audio_atual = 0
                elif tipo == "audio_end":
                    asyncio.create_task(playback_done_apos(bytes_audio_atual / 48000))
                elif tipo == "session_end":
                    ouvindo.clear()
                    fim_sessoes += 1
                    prazo_final = time.monotonic() + args.esperar_resultado
                    if args.esperar_resultado <= 0:
                        break
        finally:
            tarefa_stream.cancel()

    with wave.open(args.saida, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(bytes(recebido))
    log(f"salvo {args.saida} ({len(recebido) / 48000:.1f} s de áudio recebido)")


if __name__ == "__main__":
    asyncio.run(main())
