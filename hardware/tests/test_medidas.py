"""Task 1: medidas.json é a fonte única de medidas (mm) da placa e da caixa."""
import json
import re
import subprocess
import sys
from pathlib import Path

HW = Path(__file__).resolve().parents[1]
CHAVES = [
    "esp.comprimento", "esp.largura", "esp.pitch_fileiras",
    "esp.usb_c.x", "esp.usb_c.y", "esp.usb_c.largura", "esp.usb_c.altura",
    "esp.led.x", "esp.led.y", "esp.antena.comprimento",
    "mic.diametro", "mic.pitch_fileiras", "mic.furo.x", "mic.furo.y",
    "amp.comprimento", "amp.largura",
    "pot.corpo_diametro", "pot.rosca", "pot.eixo_diametro", "pot.eixo_comprimento", "pot.pitch_pinos",
    "falante.diametro", "falante.profundidade",
    "cap.diametro_max",
    "caixa.parede", "caixa.folga", "caixa.largura", "caixa.profundidade", "caixa.altura",
]


def medidas() -> dict:
    return json.loads((HW / "medidas.json").read_text(encoding="utf-8"))


def valor(d: dict, chave: str):
    for parte in chave.split("."):
        d = d[parte]
    return d


def test_medidas_completas_e_coerentes():
    m = medidas()
    for chave in CHAVES:
        assert isinstance(valor(m, chave), (int, float)), chave
    assert valor(m, "falante.diametro") == 40
    assert valor(m, "falante.profundidade") == 20
    assert valor(m, "cap.diametro_max") == 10
    assert 2 <= valor(m, "caixa.parede") <= 2.4
    assert 0.2 <= valor(m, "caixa.folga") <= 0.3
    assert valor(m, "esp.largura") < valor(m, "caixa.largura") - 2 * valor(m, "caixa.parede")


def test_scad_gerado_bate_com_json(tmp_path):
    saida = tmp_path / "medidas.scad"
    subprocess.run([sys.executable, str(HW / "gerar_medidas_scad.py"), str(saida)], check=True)
    scad = saida.read_text(encoding="utf-8")
    m = medidas()
    for chave in CHAVES:
        nome = chave.replace(".", "_")
        achado = re.search(rf"^{nome} = ([-0-9.]+);$", scad, re.M)
        assert achado, nome
        assert float(achado.group(1)) == float(valor(m, chave)), nome
