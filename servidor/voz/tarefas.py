"""Execução do Claude Code (``claude -p``) e fila FIFO de tarefas (uma por vez)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol, Sequence

log = logging.getLogger(__name__)

INSTRUCAO_RESPOSTA_FALADA = (
    "Sua resposta final será lida em voz alta por um assistente de voz. Responda em português, "
    "em no máximo 4 frases curtas, sem código, sem markdown e sem listas. Diga o que foi feito, "
    "em qual projeto, se abriu PR (e qual) e se a mudança já foi para produção."
)

MSG_TIMEOUT = "A tarefa do Claude Code passou do tempo limite e foi interrompida."
MSG_ERRO = "O Claude Code terminou com erro e não consegui ler a resposta."


@dataclass
class ResultadoTarefa:
    pedido: str
    texto: str
    sucesso: bool


class Executor(Protocol):
    async def executar(self, pedido: str) -> ResultadoTarefa: ...


class ExecutorClaude:
    def __init__(self, cwd: str, timeout_s: float, comando: Sequence[str] = ("claude",)):
        self.cwd = cwd
        self.timeout_s = timeout_s
        self.comando = tuple(comando)

    def argumentos(self, pedido: str) -> list[str]:
        return [
            *self.comando,
            "-p", pedido,
            "--output-format", "json",
            "--permission-mode", "bypassPermissions",
            "--append-system-prompt", INSTRUCAO_RESPOSTA_FALADA,
        ]

    async def executar(self, pedido: str) -> ResultadoTarefa:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.argumentos(pedido),
                cwd=self.cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as e:
            log.error("não consegui iniciar o Claude Code: %s", e)
            return ResultadoTarefa(pedido, MSG_ERRO, False)

        try:
            saida, erro = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s)
        except asyncio.TimeoutError:
            log.warning("Claude Code passou de %.0f s; matando o processo", self.timeout_s)
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            return ResultadoTarefa(pedido, MSG_TIMEOUT, False)
        except asyncio.CancelledError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise

        if proc.returncode != 0:
            log.error("Claude Code saiu com código %s: %s", proc.returncode, erro.decode(errors="replace")[-2000:])
            return ResultadoTarefa(pedido, MSG_ERRO, False)

        try:
            dados = json.loads(saida.decode("utf-8", errors="replace"))
            texto = dados["result"]
            if not isinstance(texto, str) or not texto.strip():
                raise ValueError("campo result vazio")
        except (ValueError, KeyError, TypeError) as e:
            log.error("saída inválida do Claude Code (%s): %r", e, saida[:500])
            return ResultadoTarefa(pedido, MSG_ERRO, False)

        return ResultadoTarefa(pedido, texto.strip(), not bool(dados.get("is_error", False)))


class FilaTarefas:
    """Fila FIFO; uma única task consumidora garante uma tarefa por vez."""

    def __init__(self, executor: Executor, ao_concluir: Callable[[ResultadoTarefa], Awaitable[None]]):
        self._executor = executor
        self._ao_concluir = ao_concluir
        self._fila: asyncio.Queue[str] = asyncio.Queue()
        self._pendentes = 0  # na fila + em execução
        self._consumidor: asyncio.Task | None = None

    def enfileirar(self, pedido: str) -> int:
        """Coloca o pedido na fila e devolve quantas tarefas estão à frente."""
        a_frente = self._pendentes
        self._pendentes += 1
        self._fila.put_nowait(pedido)
        log.info("tarefa enfileirada (%d à frente): %s", a_frente, pedido)
        return a_frente

    async def iniciar(self) -> None:
        if self._consumidor is None or self._consumidor.done():
            self._consumidor = asyncio.create_task(self._consumir(), name="fila-tarefas")

    async def parar(self) -> None:
        if self._consumidor is not None:
            self._consumidor.cancel()
            try:
                await self._consumidor
            except asyncio.CancelledError:
                pass
            self._consumidor = None

    async def _consumir(self) -> None:
        while True:
            pedido = await self._fila.get()
            try:
                try:
                    resultado = await self._executor.executar(pedido)
                except asyncio.CancelledError:
                    raise
                except Exception:  # o executor não deveria lançar, mas a fila não pode morrer
                    log.exception("executor lançou exceção")
                    resultado = ResultadoTarefa(pedido, MSG_ERRO, False)
                try:
                    await self._ao_concluir(resultado)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("erro ao entregar o resultado da tarefa")
            finally:
                self._pendentes -= 1
                self._fila.task_done()
