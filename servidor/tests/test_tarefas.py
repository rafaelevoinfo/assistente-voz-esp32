import asyncio
import sys
from pathlib import Path

import pytest

from voz.tarefas import (
    MSG_ERRO,
    MSG_TIMEOUT,
    ExecutorClaude,
    FilaTarefas,
    ResultadoTarefa,
)


@pytest.fixture
def fake_claude():
    return (sys.executable, str(Path(__file__).with_name("fake_claude.py")))


async def test_executor_sucesso(fake_claude):
    r = await ExecutorClaude(cwd=".", timeout_s=5, comando=fake_claude).executar("ok")
    assert r == ResultadoTarefa("ok", "Feito.", True)


async def test_executor_timeout(fake_claude):
    r = await ExecutorClaude(cwd=".", timeout_s=0.5, comando=fake_claude).executar("dormir")
    assert not r.sucesso and "tempo limite" in r.texto and r.texto == MSG_TIMEOUT


async def test_executor_saida_invalida(fake_claude):
    r = await ExecutorClaude(cwd=".", timeout_s=5, comando=fake_claude).executar("lixo")
    assert not r.sucesso and "erro" in r.texto and r.texto == MSG_ERRO


async def test_executor_codigo_saida_nao_zero(fake_claude):
    r = await ExecutorClaude(cwd=".", timeout_s=5, comando=fake_claude).executar("falhar")
    assert not r.sucesso and r.texto == MSG_ERRO


async def test_executor_is_error(fake_claude):
    r = await ExecutorClaude(cwd=".", timeout_s=5, comando=fake_claude).executar("erro-json")
    assert not r.sucesso and r.texto == "Não consegui acessar o repositório."


async def test_executor_comando_inexistente():
    r = await ExecutorClaude(cwd=".", timeout_s=5, comando=("nao-existe-xyz-123",)).executar("ok")
    assert not r.sucesso and r.texto == MSG_ERRO


async def test_executor_passa_argumentos(fake_claude):
    r = await ExecutorClaude(cwd=".", timeout_s=5, comando=fake_claude).executar("eco-args")
    assert "--permission-mode" in r.texto and "bypassPermissions" in r.texto
    assert "--output-format json" in r.texto and "--append-system-prompt" in r.texto


class ExecutorFalso:
    def __init__(self, falhar=(), espera=0.05):
        self.eventos: list[tuple[str, str]] = []
        self.rodando = 0
        self.max_simultaneos = 0
        self.falhar = set(falhar)
        self.espera = espera
        self.liberar = asyncio.Event()
        self.liberar.set()

    async def executar(self, pedido):
        self.rodando += 1
        self.max_simultaneos = max(self.max_simultaneos, self.rodando)
        self.eventos.append(("inicio", pedido))
        await self.liberar.wait()
        await asyncio.sleep(self.espera)
        self.eventos.append(("fim", pedido))
        self.rodando -= 1
        return ResultadoTarefa(pedido, f"r-{pedido}", pedido not in self.falhar)


async def _esperar(cond, timeout=2.0):
    fim = asyncio.get_running_loop().time() + timeout
    while not cond():
        if asyncio.get_running_loop().time() > fim:
            raise AssertionError("condição não atingida")
        await asyncio.sleep(0.01)


async def test_fila_executa_em_ordem_um_por_vez():
    ex = ExecutorFalso()
    concluidos = []

    async def ao_concluir(r):
        concluidos.append(r.pedido)

    fila = FilaTarefas(ex, ao_concluir)
    await fila.iniciar()
    for p in ("a", "b", "c"):
        fila.enfileirar(p)
    await _esperar(lambda: len(concluidos) == 3)
    await fila.parar()
    assert concluidos == ["a", "b", "c"]
    assert ex.max_simultaneos == 1
    assert ex.eventos == [("inicio", "a"), ("fim", "a"), ("inicio", "b"), ("fim", "b"), ("inicio", "c"), ("fim", "c")]


async def test_fila_retorna_posicao():
    ex = ExecutorFalso()
    ex.liberar.clear()
    concluidos = []

    async def ao_concluir(r):
        concluidos.append(r)

    fila = FilaTarefas(ex, ao_concluir)
    await fila.iniciar()
    assert fila.enfileirar("a") == 0
    await _esperar(lambda: ex.rodando == 1)
    assert fila.enfileirar("b") == 1
    assert fila.enfileirar("c") == 2
    ex.liberar.set()
    await _esperar(lambda: len(concluidos) == 3)
    assert fila.enfileirar("d") == 0
    await _esperar(lambda: len(concluidos) == 4)
    await fila.parar()


async def test_fila_continua_apos_erro():
    ex = ExecutorFalso(falhar={"a"})
    concluidos = []

    async def ao_concluir(r):
        concluidos.append(r)

    fila = FilaTarefas(ex, ao_concluir)
    await fila.iniciar()
    fila.enfileirar("a")
    fila.enfileirar("b")
    await _esperar(lambda: len(concluidos) == 2)
    await fila.parar()
    assert [r.sucesso for r in concluidos] == [False, True]


async def test_fila_continua_se_ao_concluir_lanca():
    ex = ExecutorFalso()
    concluidos = []

    async def ao_concluir(r):
        concluidos.append(r.pedido)
        if r.pedido == "a":
            raise RuntimeError("falha no callback")

    fila = FilaTarefas(ex, ao_concluir)
    await fila.iniciar()
    fila.enfileirar("a")
    fila.enfileirar("b")
    await _esperar(lambda: len(concluidos) == 2)
    await fila.parar()
