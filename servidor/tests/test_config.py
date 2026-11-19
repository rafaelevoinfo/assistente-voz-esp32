import pytest

from voz.config import Config


def test_config_le_ambiente():
    c = Config.do_ambiente({"TOKEN_PLACA": "t", "GOOGLE_API_KEY": "g", "JANELA_CONTINUACAO_S": "5"})
    assert c.provedor_voz == "gemini" and c.janela_continuacao_s == 5.0


def test_config_sem_token_falha():
    with pytest.raises(ValueError):
        Config.do_ambiente({"GOOGLE_API_KEY": "g"})


def test_config_sem_chave_google_falha():
    with pytest.raises(ValueError):
        Config.do_ambiente({"TOKEN_PLACA": "t"})


def test_config_openai_exige_chave_openai():
    with pytest.raises(ValueError):
        Config.do_ambiente({"TOKEN_PLACA": "t", "PROVEDOR_VOZ": "openai"})


def test_config_openai_com_chave():
    c = Config.do_ambiente({"TOKEN_PLACA": "t", "PROVEDOR_VOZ": "openai", "OPENAI_API_KEY": "o"})
    assert c.provedor_voz == "openai" and c.openai_api_key == "o"


def test_config_provedor_desconhecido_falha():
    with pytest.raises(ValueError):
        Config.do_ambiente({"TOKEN_PLACA": "t", "GOOGLE_API_KEY": "g", "PROVEDOR_VOZ": "xyz"})


def test_config_modelos_vem_do_ambiente():
    c = Config.do_ambiente({
        "TOKEN_PLACA": "t", "GOOGLE_API_KEY": "g",
        "MODELO_VOZ": "m1", "VOZ": "v1", "MODELO_TTS": "m2",
        "ESPERA_RESPOSTA_S": "3", "WORKSPACE_DIR": "/w", "CLAUDE_TIMEOUT_S": "60",
    })
    assert (c.modelo_voz, c.voz, c.modelo_tts) == ("m1", "v1", "m2")
    assert c.espera_resposta_s == 3.0 and c.workspace_dir == "/w" and c.claude_timeout_s == 60.0


def test_config_proactive_audio():
    base = {"TOKEN_PLACA": "t", "GOOGLE_API_KEY": "g"}
    assert Config.do_ambiente(base).proactive_audio is True
    assert Config.do_ambiente({**base, "PROACTIVE_AUDIO": "0"}).proactive_audio is False
