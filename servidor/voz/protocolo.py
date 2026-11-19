"""Mensagens JSON placa <-> servidor (ver docs/contrato.md §1)."""

from __future__ import annotations

import json

TAXA_ENTRADA = 16000
TAXA_SAIDA = 24000

TIPOS_PLACA = frozenset({"hello", "wake", "playback_done"})
TIPOS_SERVIDOR = frozenset({"listen", "stop_listen", "audio_start", "audio_end", "session_end"})
TIPOS = TIPOS_PLACA | TIPOS_SERVIDOR


class ProtocoloInvalido(Exception):
    """Frame de texto que não segue o contrato."""


def codificar(tipo: str, **campos) -> str:
    if tipo not in TIPOS:
        raise ProtocoloInvalido(f"tipo desconhecido: {tipo!r}")
    return json.dumps({"type": tipo, **campos}, ensure_ascii=False, separators=(",", ":"))


def decodificar(texto: str) -> dict:
    try:
        msg = json.loads(texto)
    except (json.JSONDecodeError, TypeError) as e:
        raise ProtocoloInvalido(f"JSON inválido: {e}") from e
    if not isinstance(msg, dict):
        raise ProtocoloInvalido("a mensagem precisa ser um objeto JSON")
    tipo = msg.get("type")
    if not isinstance(tipo, str):
        raise ProtocoloInvalido("campo 'type' ausente")
    if tipo not in TIPOS:
        raise ProtocoloInvalido(f"tipo desconhecido: {tipo!r}")
    return msg
