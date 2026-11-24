"""Task 3: contorno e posição dos componentes (roda com o Python do KiCad, que tem o pcbnew)."""
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

pcbnew = pytest.importorskip("pcbnew", reason="rode com o Python do KiCad")

HW = Path(__file__).resolve().parents[1]
PCB = HW / "placa" / "assistente.kicad_pcb"
POSICOES = HW / "placa" / "posicoes.json"
MEDIDAS = json.loads((HW / "medidas.json").read_text(encoding="utf-8"))


def mm(v):
    return pcbnew.ToMM(v)


@pytest.fixture(scope="module")
def placa():
    subprocess.run([sys.executable, str(HW / "placa" / "montar_pcb.py")], check=True)
    return pcbnew.LoadBoard(str(PCB))


@pytest.fixture(scope="module")
def contorno(placa):
    poligono = pcbnew.SHAPE_POLY_SET()
    assert placa.GetBoardPolygonOutlines(poligono, False), "contorno da placa inválido"
    return poligono


def dentro(contorno, x, y):
    return contorno.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))


def fp(placa, ref):
    achado = placa.FindFootprintByReference(ref)
    assert achado, ref
    return achado


def pads(placa, ref):
    return {p.GetNumber(): (mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in fp(placa, ref).Pads()}


def test_largura_cabe_na_caixa(placa):
    c = MEDIDAS["caixa"]
    largura = mm(placa.GetBoardEdgesBoundingBox().GetWidth())
    assert largura <= c["largura"] - 2 * c["parede"] - 2 * c["folga"] - 2


def test_tudo_dentro_do_contorno(placa, contorno):
    for f in placa.GetFootprints():
        for numero, (x, y) in pads(placa, f.GetReference()).items():
            assert dentro(contorno, x, y), f"{f.GetReference()} pad {numero} fora do contorno"


def test_antena_para_fora(placa, contorno):
    area = [z for z in placa.Zones() if z.GetIsRuleArea() and z.GetZoneName() == "ANTENA"]
    assert len(area) == 1, "falta a área ANTENA"
    caixa = area[0].GetBoundingBox()
    x0, y0, x1, y1 = mm(caixa.GetLeft()), mm(caixa.GetTop()), mm(caixa.GetRight()), mm(caixa.GetBottom())
    assert (y1 - y0) >= MEDIDAS["esp"]["antena"]["comprimento"] - 0.01 or (x1 - x0) >= MEDIDAS["esp"]["antena"]["comprimento"] - 0.01
    passo = 1.0
    x = x0 + 0.5
    while x < x1:
        y = y0 + 0.5
        while y < y1:
            assert not dentro(contorno, x, y), f"placa embaixo da antena em ({x:.1f}, {y:.1f})"
            y += passo
        x += passo


def test_pot_na_borda_direita(placa):
    borda_direita = mm(placa.GetBoardEdgesBoundingBox().GetRight())
    p = pads(placa, "RV1")
    assert max(x for x, _ in p.values()) <= borda_direita
    assert borda_direita - max(x for x, _ in p.values()) <= 12, "RV1 longe da borda direita"
    pos = json.loads(POSICOES.read_text(encoding="utf-8"))
    assert pos["pot"]["eixo_dir"] == [1, 0]
    assert pos["pot"]["corpo_borda_x"] <= borda_direita + 0.01


def test_caps_colados_no_amp(placa):
    amp = pads(placa, "U3")
    vin, gnd = amp[str(7)], amp[str(6)]
    rotacoes = set()
    for c in ("C1", "C2"):
        p = pads(placa, c)
        assert math.dist(p["1"], vin) <= 15 or math.dist(p["2"], gnd) <= 15, c
        rotacoes.add(round(fp(placa, c).GetOrientationDegrees()) % 360)
    assert len(rotacoes) == 1, "C1 e C2 com rotações diferentes"
    for c in ("C1", "C2"):
        nets = {pad.GetNumber(): pad.GetNetname().lstrip("/") for pad in fp(placa, c).Pads()}
        assert nets == {"1": "+5V", "2": "GND"}, c


def test_usb_c_na_borda_traseira(placa):
    pos = json.loads(POSICOES.read_text(encoding="utf-8"))
    borda_traseira = mm(placa.GetBoardEdgesBoundingBox().GetTop())
    assert abs(pos["usb_c"]["y_borda"] - borda_traseira) <= 1.0
    for chave in ("x", "largura", "altura_sobre_placa"):
        assert chave in pos["usb_c"]


def test_mic_longe_da_frente(placa):
    frente = mm(placa.GetBoardEdgesBoundingBox().GetBottom())
    _, y_mic = mm(fp(placa, "U2").GetPosition().x), mm(fp(placa, "U2").GetPosition().y)
    _, y_amp = mm(fp(placa, "U3").GetPosition().x), mm(fp(placa, "U3").GetPosition().y)
    assert (frente - y_mic) > (frente - y_amp), "mic deve ficar mais para trás que o amplificador"
