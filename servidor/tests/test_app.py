import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.fakes import FabricaFalsa, SintetizadorFalso
from voz.app import criar_app
from voz.conexao import Estado
from voz.config import Config
from voz.tarefas import ExecutorClaude, ResultadoTarefa

TOKEN = "segredo-da-placa"
CONFIG = Config(token_placa=TOKEN, google_api_key="g")
FAKE_CLAUDE = (sys.executable, str(Path(__file__).with_name("fake_claude.py")))


def _montar(config=CONFIG):
    fabrica = FabricaFalsa()
    app = criar_app(config, fabrica, SintetizadorFalso(), ExecutorClaude(cwd=".", timeout_s=5, comando=FAKE_CLAUDE))
    return app, fabrica


@pytest.fixture
def ambiente():
    app, fabrica = _montar()
    with TestClient(app) as client:
        yield app, client, fabrica


def _receber_json(ws):
    return ws.receive_json()


def test_health(ambiente):
    _, client, _ = ambiente
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_ws_sem_token_recusado(ambiente):
    _, client, _ = ambiente
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()
    assert e.value.code == 4401


def test_ws_token_errado_recusado(ambiente):
    _, client, _ = ambiente
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws?token=errado") as ws:
            ws.receive_text()
    assert e.value.code == 4401


def test_ws_fluxo_wake_listen(ambiente):
    _, client, fabrica = ambiente
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.send_json({"type": "hello", "fw": "1.0"})
        ws.send_json({"type": "wake"})
        assert _receber_json(ws) == {"type": "listen"}
        ws.send_bytes(b"\x00\x00" * 320)
        _esperar(lambda: fabrica.ultima.audio)
        assert fabrica.ultima.audio == [b"\x00\x00" * 320]


def test_ws_texto_invalido_nao_derruba(ambiente):
    _, client, _ = ambiente
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.send_json({"type": "hello", "fw": "1.0"})
        ws.send_text("lixo")
        ws.send_json({"type": "tipo_que_nao_existe"})
        ws.send_json({"type": "wake"})
        assert _receber_json(ws) == {"type": "listen"}


def test_nova_conexao_substitui_antiga(ambiente):
    app, client, fabrica = ambiente
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws1:
        ws1.send_json({"type": "hello", "fw": "1.0"})
        ws1.send_json({"type": "wake"})
        assert _receber_json(ws1) == {"type": "listen"}
        # resultado chega no meio da conversa → vai para a caixa
        client.portal.call(app.state.conexao.ao_resultado, ResultadoTarefa("p", "Feito.", True))
        with client.websocket_connect(f"/ws?token={TOKEN}") as ws2:
            msg = ws1.receive()
            assert msg["type"] == "websocket.close" and msg["code"] == 4000
            assert fabrica.ultima.encerrada
            ws2.send_json({"type": "hello", "fw": "1.0"})
            assert _receber_json(ws2) == {"type": "audio_start", "rate": 24000}
            dados = ws2.receive_bytes()
            assert len(dados) <= 4800
            assert app.state.conexao.estado in (Estado.TOCANDO, Estado.RESPONDENDO)


def test_pedido_de_codigo_resultado_empurrado():
    """Fluxo B do contrato com o fake_claude: o resultado chega sozinho."""
    config = Config(token_placa=TOKEN, google_api_key="g", janela_continuacao_s=0.5)
    app, fabrica = _montar(config)
    with TestClient(app) as client, client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.send_json({"type": "hello", "fw": "1.0"})
        ws.send_json({"type": "wake"})
        assert _receber_json(ws) == {"type": "listen"}
        retorno = client.portal.call(fabrica.ultima.modelo_pede_codigo, "ok")
        assert "Claude Code" in retorno
        # a janela (0,5 s aqui) fecha sem fala; depois o resultado é falado
        assert _receber_json(ws) == {"type": "session_end"}
        assert _receber_json(ws) == {"type": "audio_start", "rate": 24000}


def _esperar(cond, timeout=2.0):
    fim = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > fim:
            raise AssertionError("condição não atingida")
        time.sleep(0.01)


def test_token_nao_aparece_nos_logs():
    # o uvicorn registra a URL da conexão ("WebSocket /ws?token=... [accepted]")
    import logging

    from voz.app import FiltroToken

    reg = logging.LogRecord("uvicorn.error", logging.INFO, __file__, 1,
                            '%s - "WebSocket %s" [accepted]', ("1.2.3.4:5", "/ws?token=SEGREDO123&x=1"), None)
    assert FiltroToken().filter(reg) is True
    assert "SEGREDO123" not in reg.getMessage()
    assert "token=***" in reg.getMessage()
