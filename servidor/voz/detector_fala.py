"""Detecção local (por RMS) de início e fim de fala no mic da placa.

Serve só para os timeouts da janela de continuação; o fim de turno de verdade
é decidido pelo VAD do provedor.
"""

from __future__ import annotations

from typing import Literal

import numpy as np


class DetectorFala:
    """O RMS é medido depois de um passa-altas de 1ª ordem (``corte_hz``).

    O mic da placa (INMP441) tem um ronco/deriva abaixo de 100 Hz que, sem filtro,
    deixava o "silêncio" com RMS acima do limiar e a janela de escuta nunca fechava.
    Voz fica bem acima de 100 Hz, então o filtro não a afeta.
    """

    def __init__(
        self,
        limiar_rms: int = 500,
        min_fala_ms: int = 150,
        silencio_fim_ms: int = 1000,
        taxa: int = 16000,
        corte_hz: float = 80.0,
    ):
        self.limiar_rms = limiar_rms
        self.taxa = taxa
        self._r = float(np.exp(-2 * np.pi * corte_hz / taxa))
        self._x_ant = 0.0  # estado do filtro: contínuo ao longo da conexão
        self._y_ant = 0.0
        self.bloco_ms = 20
        self.bytes_bloco = taxa * self.bloco_ms // 1000 * 2
        self.min_blocos_fala = max(1, -(-min_fala_ms // self.bloco_ms))
        self.min_blocos_silencio = max(1, -(-silencio_fim_ms // self.bloco_ms))
        self.reset()

    def reset(self) -> None:
        self._buffer = bytearray()
        self._falando = False
        self._blocos_fala = 0
        self._blocos_silencio = 0

    @property
    def falando(self) -> bool:
        return self._falando

    def processar(self, pcm16k: bytes) -> Literal["inicio", "fim"] | None:
        self._buffer.extend(pcm16k)
        evento: Literal["inicio", "fim"] | None = None
        while len(self._buffer) >= self.bytes_bloco:
            bloco = bytes(self._buffer[: self.bytes_bloco])
            del self._buffer[: self.bytes_bloco]
            ev = self._processar_bloco(bloco)
            if ev is not None:
                evento = ev
        return evento

    def _passa_altas(self, x: np.ndarray) -> np.ndarray:
        """y[n] = r*y[n-1] + x[n] - x[n-1]."""
        y = np.empty_like(x)
        x_ant, y_ant, r = self._x_ant, self._y_ant, self._r
        for i, v in enumerate(x.tolist()):
            y_ant = r * y_ant + v - x_ant
            x_ant = v
            y[i] = y_ant
        self._x_ant, self._y_ant = x_ant, y_ant
        return y

    def _processar_bloco(self, bloco: bytes) -> Literal["inicio", "fim"] | None:
        amostras = self._passa_altas(np.frombuffer(bloco, dtype="<i2").astype(np.float64))
        rms = float(np.sqrt(np.mean(amostras * amostras))) if amostras.size else 0.0
        voz = rms >= self.limiar_rms
        if not self._falando:
            self._blocos_fala = self._blocos_fala + 1 if voz else 0
            if self._blocos_fala >= self.min_blocos_fala:
                self._falando = True
                self._blocos_silencio = 0
                return "inicio"
        else:
            self._blocos_silencio = 0 if voz else self._blocos_silencio + 1
            if self._blocos_silencio >= self.min_blocos_silencio:
                self._falando = False
                self._blocos_fala = 0
                return "fim"
        return None
