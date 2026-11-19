import json

import pytest

from voz.protocolo import TAXA_ENTRADA, TAXA_SAIDA, ProtocoloInvalido, codificar, decodificar


def test_taxas():
    assert TAXA_ENTRADA == 16000 and TAXA_SAIDA == 24000


def test_protocolo_ida_e_volta():
    assert decodificar(codificar("audio_start", rate=24000)) == {"type": "audio_start", "rate": 24000}


def test_codificar_json_compacto():
    assert json.loads(codificar("listen")) == {"type": "listen"}


def test_campos_extras_sao_aceitos():
    assert decodificar('{"type":"hello","fw":"1.0","x":1}')["fw"] == "1.0"


@pytest.mark.parametrize("texto", ["nao-json", "{}", '{"type":"inexistente"}', "[1,2]", '{"type":3}'])
def test_protocolo_invalido(texto):
    with pytest.raises(ProtocoloInvalido):
        decodificar(texto)
