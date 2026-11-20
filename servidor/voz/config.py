"""Configuração do servidor, lida só de variáveis de ambiente.

Os nomes de modelo aparecem aqui apenas como *default*; em produção vêm de
``MODELO_VOZ`` / ``MODELO_TTS`` / ``VOZ``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

PROVEDORES = ("gemini", "openai")

# Defaults confirmados no pipecat-ai 1.16.0 (ver docs/notas-pipecat.md).
MODELO_VOZ_PADRAO = {
    "gemini": "models/gemini-3.8-live",
    "openai": "gpt-realtime-2.1",
}
VOZ_PADRAO = {"gemini": "Charon", "openai": "marin"}
MODELO_TTS_PADRAO = "gemini-3.8-flash-lite-tts"
VOZ_TTS_PADRAO = "Charon"


@dataclass(frozen=True)
class Config:
    token_placa: str
    google_api_key: str
    provedor_voz: str = "gemini"
    modelo_voz: str = MODELO_VOZ_PADRAO["gemini"]
    voz: str = VOZ_PADRAO["gemini"]
    modelo_tts: str = MODELO_TTS_PADRAO
    janela_continuacao_s: float = 8.0
    espera_resposta_s: float = 6.0
    escuta_max_s: float = 60.0  # trava: tempo máximo ouvindo sem resposta do modelo
    workspace_dir: str = "/home/voz/workspace"
    memoria_dir: str = ""  # CONTEXTO.md + historico.jsonl; vazio = sem memória
    claude_timeout_s: float = 1800.0
    openai_api_key: str = ""
    voz_tts: str = VOZ_TTS_PADRAO
    proactive_audio: bool = True
    busca_google: bool = True  # ferramenta nativa do Gemini (Grounding with Google Search)

    @classmethod
    def do_ambiente(cls, env: Mapping[str, str] | None = None) -> "Config":
        if env is None:
            env = os.environ

        def texto(nome: str, padrao: str = "") -> str:
            return (env.get(nome) or padrao).strip()

        def numero(nome: str, padrao: float) -> float:
            bruto = texto(nome)
            if not bruto:
                return padrao
            try:
                return float(bruto)
            except ValueError as e:
                raise ValueError(f"{nome} precisa ser um número (recebido: {bruto!r})") from e

        token = texto("TOKEN_PLACA")
        if not token:
            raise ValueError("TOKEN_PLACA não definido")

        provedor = texto("PROVEDOR_VOZ", "gemini").lower()
        if provedor not in PROVEDORES:
            raise ValueError(f"PROVEDOR_VOZ inválido: {provedor!r} (use {' ou '.join(PROVEDORES)})")

        google = texto("GOOGLE_API_KEY")
        openai = texto("OPENAI_API_KEY")
        if provedor == "gemini" and not google:
            raise ValueError("GOOGLE_API_KEY não definido (necessário para PROVEDOR_VOZ=gemini)")
        if provedor == "openai" and not openai:
            raise ValueError("OPENAI_API_KEY não definido (necessário para PROVEDOR_VOZ=openai)")

        voz = texto("VOZ", VOZ_PADRAO[provedor])
        return cls(
            token_placa=token,
            google_api_key=google,
            provedor_voz=provedor,
            modelo_voz=texto("MODELO_VOZ", MODELO_VOZ_PADRAO[provedor]),
            voz=voz,
            modelo_tts=texto("MODELO_TTS", MODELO_TTS_PADRAO),
            janela_continuacao_s=numero("JANELA_CONTINUACAO_S", 8.0),
            espera_resposta_s=numero("ESPERA_RESPOSTA_S", 6.0),
            escuta_max_s=numero("ESCUTA_MAX_S", 60.0),
            workspace_dir=texto("WORKSPACE_DIR", "/home/voz/workspace"),
            memoria_dir=texto("MEMORIA_DIR", ""),
            claude_timeout_s=numero("CLAUDE_TIMEOUT_S", 1800.0),
            openai_api_key=openai,
            voz_tts=texto("VOZ_TTS", voz if provedor == "gemini" else VOZ_TTS_PADRAO),
            proactive_audio=texto("PROACTIVE_AUDIO", "1").lower() not in ("0", "false", "nao", "não", "no"),
            busca_google=texto("BUSCA_GOOGLE", "1").lower() not in ("0", "false", "nao", "não", "no"),
        )
