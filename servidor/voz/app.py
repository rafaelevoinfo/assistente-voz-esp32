"""Servidor web: WebSocket da placa (``/ws``) e health check (``/health``).

Uso em produção: ``uvicorn voz.app:app`` (o ``app`` do módulo é montado na
primeira vez que é acessado, a partir das variáveis de ambiente e com as
implementações reais de voz e TTS).
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from voz.conexao import CaixaDeSaida, ConexaoPlaca
from voz.config import Config
from voz.interfaces import FabricaSessaoVoz, Sintetizador
from voz.memoria import Memoria
from voz.protocolo import ProtocoloInvalido, decodificar
from voz.tarefas import ExecutorClaude, FilaTarefas

log = logging.getLogger(__name__)

CODIGO_TOKEN_INVALIDO = 4401
CODIGO_SUBSTITUIDA = 4000
INTERVALO_TICK_S = 0.25


class EnvioWebSocket:
    """Envio para a placa; serializa os envios vindos de tasks diferentes."""

    def __init__(self, ws: WebSocket):
        self._ws = ws
        self._trava = asyncio.Lock()

    async def texto(self, msg: str) -> None:
        async with self._trava:
            await self._ws.send_text(msg)

    async def binario(self, dados: bytes) -> None:
        async with self._trava:
            await self._ws.send_bytes(dados)


def _token_valido(recebido: str | None, esperado: str) -> bool:
    if not recebido:
        return False
    return hmac.compare_digest(recebido.encode(), esperado.encode())


def criar_app(
    config: Config,
    fabrica: FabricaSessaoVoz,
    sintetizador: Sintetizador,
    executor: ExecutorClaude,
) -> FastAPI:
    caixa = CaixaDeSaida()
    conexao: ConexaoPlaca | None = None

    async def ao_concluir(resultado):
        assert conexao is not None
        await conexao.ao_resultado(resultado)

    fila = FilaTarefas(executor, ao_concluir=ao_concluir)
    memoria = Memoria(config.memoria_dir) if config.memoria_dir else None
    if memoria is None:
        log.info("MEMORIA_DIR não definido: sem histórico")
    conexao = ConexaoPlaca(config, fabrica, sintetizador, enfileirar=fila.enfileirar, caixa=caixa, memoria=memoria)

    atual: dict[str, WebSocket | None] = {"ws": None}
    troca = asyncio.Lock()

    async def loop_tick():
        while True:
            await asyncio.sleep(INTERVALO_TICK_S)
            if atual["ws"] is None:
                continue
            try:
                await conexao.tick()
            except Exception:
                log.exception("erro no tick da conexão")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await fila.iniciar()
        tarefa_tick = asyncio.create_task(loop_tick(), name="tick-conexao")
        try:
            yield
        finally:
            tarefa_tick.cancel()
            try:
                await tarefa_tick
            except asyncio.CancelledError:
                pass
            await conexao.desconectar()
            await fila.parar()

    app = FastAPI(title="Assistente de voz", lifespan=lifespan)
    app.state.conexao = conexao
    app.state.fila = fila
    app.state.caixa = caixa
    app.state.config = config

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.websocket("/ws")
    async def ws_placa(ws: WebSocket):
        await ws.accept()
        if not _token_valido(ws.query_params.get("token"), config.token_placa):
            log.warning("conexão recusada: token ausente ou inválido (%s)", ws.client)
            await ws.close(code=CODIGO_TOKEN_INVALIDO)
            return

        async with troca:
            antiga = atual["ws"]
            if antiga is not None:
                log.info("nova conexão da placa substitui a anterior")
                atual["ws"] = None
                try:
                    if antiga.application_state != WebSocketState.DISCONNECTED:
                        await antiga.close(code=CODIGO_SUBSTITUIDA)
                except Exception as e:  # socket antigo já pode estar morto
                    log.debug("falha ao fechar a conexão antiga: %s", e)
                await conexao.desconectar()
            atual["ws"] = ws
            await conexao.conectar(EnvioWebSocket(ws))
        log.info("placa conectada: %s", ws.client)

        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if atual["ws"] is not ws:
                    break  # fomos substituídos
                if msg.get("bytes") is not None:
                    await conexao.ao_audio(msg["bytes"])
                elif msg.get("text") is not None:
                    try:
                        dados = decodificar(msg["text"])
                    except ProtocoloInvalido as e:
                        log.warning("frame de texto ignorado: %s", e)
                        continue
                    await conexao.ao_texto(dados)
        except (WebSocketDisconnect, RuntimeError) as e:
            log.info("conexão da placa terminou: %s", e)
        finally:
            async with troca:
                if atual["ws"] is ws:
                    atual["ws"] = None
                    await conexao.desconectar()
                    log.info("placa desconectada")

    return app


class FiltroToken(logging.Filter):
    """Mascara ``token=...`` nas mensagens de log (o uvicorn registra a URL da conexão)."""

    _padrao = re.compile(r"(token=)[^&\s\"']+")

    def filter(self, record: logging.LogRecord) -> bool:
        mensagem = record.getMessage()
        if "token=" in mensagem:
            record.msg = self._padrao.sub(r"\1***", mensagem)
            record.args = ()
        return True


def instalar_filtro_token() -> None:
    filtro = FiltroToken()
    for nome in ("uvicorn", "uvicorn.error", "uvicorn.access", ""):
        logger = logging.getLogger(nome)
        logger.addFilter(filtro)
        for handler in logger.handlers:
            handler.addFilter(filtro)


def criar_app_do_ambiente() -> FastAPI:
    """Monta o app com as implementações reais (Pipecat + TTS do Gemini)."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    instalar_filtro_token()
    from voz.sessao_pipecat import FabricaSessaoPipecat
    from voz.tts_gemini import TTSGemini

    config = Config.do_ambiente()
    comando = tuple((os.environ.get("CLAUDE_CMD") or "claude").split())
    executor = ExecutorClaude(cwd=config.workspace_dir, timeout_s=config.claude_timeout_s, comando=comando)
    return criar_app(config, FabricaSessaoPipecat(config), TTSGemini(config), executor)


_app: FastAPI | None = None


def __getattr__(nome: str):
    # ``app`` é montado sob demanda para que importar este módulo (testes) não
    # exija variáveis de ambiente nem carregue o Pipecat.
    global _app
    if nome == "app":
        if _app is None:
            _app = criar_app_do_ambiente()
        return _app
    raise AttributeError(nome)
