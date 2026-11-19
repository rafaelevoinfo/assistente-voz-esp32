"""Fakes para testar ConexaoPlaca e o app sem Pipecat e sem rede."""

from __future__ import annotations

import json

import numpy as np

from voz.interfaces import EventosSessao


class SessaoFalsa:
    def __init__(self, eventos: EventosSessao):
        self.eventos = eventos
        self.iniciada_com: list[str | None] = []
        self.memorias: list[str | None] = []
        self.audio: list[bytes] = []
        self.encerrada = False

    async def iniciar(self, contexto, memoria=None):
        self.iniciada_com.append(contexto)
        self.memorias.append(memoria)

    async def enviar_audio(self, pcm16k):
        self.audio.append(pcm16k)

    async def encerrar(self):
        self.encerrada = True

    # gatilhos para os testes
    async def modelo_fala(self, dados: bytes = b"\x01\x00" * 2400):
        await self.eventos.ao_audio(dados)

    async def modelo_termina(self):
        await self.eventos.ao_fim_resposta()

    async def usuario_transcrito(self, texto: str):
        await self.eventos.ao_texto_usuario(texto)

    async def modelo_transcrito(self, texto: str):
        await self.eventos.ao_texto_modelo(texto)

    async def modelo_pede_codigo(self, pedido: str) -> str:
        return await self.eventos.ao_pedido_codigo(pedido)


class FabricaFalsa:
    def __init__(self):
        self.sessoes: list[SessaoFalsa] = []

    def criar(self, eventos: EventosSessao) -> SessaoFalsa:
        s = SessaoFalsa(eventos)
        self.sessoes.append(s)
        return s

    @property
    def ultima(self) -> SessaoFalsa:
        return self.sessoes[-1]


class SintetizadorFalso:
    """Devolve 0,5 s de PCM 24 kHz (24000 bytes) por texto."""

    def __init__(self, bytes_por_texto: int = 24000):
        self.textos: list[str] = []
        self.bytes_por_texto = bytes_por_texto

    async def sintetizar(self, texto: str) -> bytes:
        self.textos.append(texto)
        return b"\x02\x00" * (self.bytes_por_texto // 2)


class EnvioFalso:
    def __init__(self):
        self.mensagens: list[dict | bytes] = []

    async def texto(self, msg: str) -> None:
        self.mensagens.append(json.loads(msg))

    async def binario(self, dados: bytes) -> None:
        self.mensagens.append(bytes(dados))

    def tipos(self) -> list[str]:
        return [m["type"] if isinstance(m, dict) else "bin" for m in self.mensagens]

    def textos(self) -> list[dict]:
        return [m for m in self.mensagens if isinstance(m, dict)]

    def binarios(self) -> list[bytes]:
        return [m for m in self.mensagens if isinstance(m, bytes)]

    def limpar(self):
        self.mensagens.clear()


class RelogioFalso:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def avancar(self, s: float) -> None:
        self.t += s


def pcm16k(ms: int, amplitude: int) -> bytes:
    n = 16000 * ms // 1000
    t = np.arange(n) / 16000
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype("<i2").tobytes()
