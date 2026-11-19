"""Interfaces entre a lógica da aplicação e as implementações de voz/TTS.

Sem dependências externas: a aplicação (``conexao.py``, ``app.py``) só conhece isto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol


@dataclass
class EventosSessao:
    ao_audio: Callable[[bytes], Awaitable[None]]
    """PCM 16 bits mono 24 kHz vindo do modelo."""
    ao_fim_resposta: Callable[[], Awaitable[None]]
    """O modelo terminou de falar a resposta atual."""
    ao_pedido_codigo: Callable[[str], Awaitable[str]]
    """Recebe o pedido literal e devolve o texto de retorno da ferramenta."""
    ao_texto_usuario: Callable[[str], Awaitable[None]] = None  # type: ignore[assignment]
    """Trecho da transcrição da fala do usuário (frases)."""
    ao_texto_modelo: Callable[[str], Awaitable[None]] = None  # type: ignore[assignment]
    """Trecho da transcrição da resposta do modelo (já com os espaços)."""

    def __post_init__(self) -> None:
        async def nada(_texto: str) -> None:
            return None

        if self.ao_texto_usuario is None:
            self.ao_texto_usuario = nada
        if self.ao_texto_modelo is None:
            self.ao_texto_modelo = nada


class SessaoVoz(Protocol):
    async def iniciar(self, contexto: str | None, memoria: str | None = None) -> None: ...
    async def enviar_audio(self, pcm16k: bytes) -> None: ...
    async def encerrar(self) -> None: ...


class FabricaSessaoVoz(Protocol):
    def criar(self, eventos: EventosSessao) -> SessaoVoz: ...


class Sintetizador(Protocol):
    async def sintetizar(self, texto: str) -> bytes:
        """Devolve PCM 16 bits mono 24 kHz."""
        ...
