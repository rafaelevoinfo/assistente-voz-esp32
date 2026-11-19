"""Memória do assistente: ``CONTEXTO.md`` (escrito pelo usuário) e histórico de trocas.

O histórico fica em ``historico.jsonl`` (uma troca por linha). Quando o arquivo
passaria de ``max_bytes`` ele é rotacionado: o atual vira ``historico.1.jsonl``, o
``.1`` vira ``.2`` e assim por diante, mantendo no máximo ``max_arquivos`` no total
(o atual incluso). Spec §7.2.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

MAX_BYTES_PADRAO = 10 * 1024 * 1024  # 10 MB
MAX_ARQUIVOS_PADRAO = 7
TROCAS_NA_SESSAO = 5
LIMITE_CONTEXTO_MD = 8000  # caracteres; evita uma instrução de sistema gigante


@dataclass(frozen=True)
class Troca:
    ts: str
    origem: str  # "conversa" | "claude_code"
    pergunta: str
    resposta: str


class Historico:
    def __init__(self, pasta: Path | str, max_bytes: int = MAX_BYTES_PADRAO,
                 max_arquivos: int = MAX_ARQUIVOS_PADRAO):
        self.pasta = Path(pasta)
        self.max_bytes = max_bytes
        self.max_arquivos = max(1, max_arquivos)

    @property
    def atual(self) -> Path:
        return self.pasta / "historico.jsonl"

    def _antigo(self, n: int) -> Path:
        return self.pasta / f"historico.{n}.jsonl"

    def registrar(self, pergunta: str, resposta: str, origem: str = "conversa") -> None:
        troca = Troca(datetime.now().isoformat(timespec="seconds"), origem, pergunta.strip(), resposta.strip())
        linha = (json.dumps(asdict(troca), ensure_ascii=False) + "\n").encode("utf-8")
        self.pasta.mkdir(parents=True, exist_ok=True)
        tamanho = self.atual.stat().st_size if self.atual.exists() else 0
        if tamanho > 0 and tamanho + len(linha) > self.max_bytes:
            self.rotacionar()
        with self.atual.open("ab") as f:
            f.write(linha)

    def rotacionar(self) -> None:
        """Renomeia o arquivo atual e começa um novo, apagando o mais antigo se preciso."""
        if not self.atual.exists():
            return
        ultimo = self.max_arquivos - 1  # quantos arquivos antigos cabem
        if ultimo < 1:
            self.atual.unlink()
            return
        if self._antigo(ultimo).exists():
            self._antigo(ultimo).unlink()
        for n in range(ultimo - 1, 0, -1):
            if self._antigo(n).exists():
                self._antigo(n).rename(self._antigo(n + 1))
        self.atual.rename(self._antigo(1))
        log.info("histórico rotacionado (%s)", self._antigo(1).name)

    def ultimas(self, n: int = TROCAS_NA_SESSAO) -> list[Troca]:
        """As ``n`` trocas mais recentes (mais antiga primeiro); completa com o arquivo anterior."""
        trocas = self._ler(self.atual)
        if len(trocas) < n:
            trocas = self._ler(self._antigo(1)) + trocas
        return trocas[-n:] if n > 0 else []

    @staticmethod
    def _ler(caminho: Path) -> list[Troca]:
        if not caminho.exists():
            return []
        trocas: list[Troca] = []
        for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
            if not linha.strip():
                continue
            try:
                d = json.loads(linha)
                trocas.append(Troca(str(d["ts"]), str(d["origem"]), str(d["pergunta"]), str(d["resposta"])))
            except (ValueError, KeyError, TypeError):
                log.warning("linha corrompida ignorada em %s", caminho.name)
        return trocas


class Memoria:
    """Junta o ``CONTEXTO.md`` e as últimas trocas num texto para a instrução de sistema."""

    def __init__(self, pasta: Path | str, historico: Historico | None = None):
        self.pasta = Path(pasta)
        self.historico = historico or Historico(self.pasta)

    def registrar_conversa(self, pergunta: str, resposta: str) -> None:
        if pergunta.strip() or resposta.strip():
            self.historico.registrar(pergunta, resposta, origem="conversa")

    def registrar_tarefa(self, pedido: str, resultado: str) -> None:
        self.historico.registrar(pedido, resultado, origem="claude_code")

    def _contexto_md(self) -> str:
        caminho = self.pasta / "CONTEXTO.md"
        if not caminho.exists():
            return ""
        return caminho.read_text(encoding="utf-8", errors="replace").strip()[:LIMITE_CONTEXTO_MD]

    def texto_para_sessao(self) -> str | None:
        partes: list[str] = []
        contexto = self._contexto_md()
        if contexto:
            partes.append("## Informações fixas sobre o usuário (CONTEXTO.md)\n" + contexto)
        trocas = self.historico.ultimas(TROCAS_NA_SESSAO)
        if trocas:
            linhas = ["## Conversas anteriores (apenas referência; não retome esses assuntos "
                      "a menos que o usuário peça)"]
            for t in trocas:
                quando = t.ts.replace("T", " ")[:16]
                if t.origem == "claude_code":
                    linhas.append(f"[{quando}] Pedido ao Claude Code: {t.pergunta}\n  Resultado: {t.resposta}")
                else:
                    linhas.append(f"[{quando}] Usuário: {t.pergunta}\n  Assistente: {t.resposta}")
            partes.append("\n".join(linhas))
        return "\n\n".join(partes) if partes else None
