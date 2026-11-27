"""Task 5b: mapa de montagem da placa perfurada (grade de 2,54 mm)."""
import sys
from collections import defaultdict
from pathlib import Path

import pytest

HW = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HW / "placa"))
sys.path.insert(0, str(HW / "perfurada"))

import netlist  # noqa: E402

import layout  # noqa: E402
PASSO = 2.54


def todos_os_pinos():
    return [(ref, n) for ref, (_, _, pinos) in netlist.COMPONENTES.items() for n in range(1, len(pinos) + 1)]


def test_cabe_na_placa_cortada():
    colunas, linhas = layout.GRADE
    assert (colunas - 1) * PASSO + 4 <= 70.5, "largura (com 2 mm de margem de cada lado)"
    assert (linhas - 1) * PASSO + 4 <= 68.5, "profundidade (com 2 mm de margem de cada lado)"
    for ref, n in todos_os_pinos():
        c, l = layout.furo(ref, n)
        assert 0 <= c < colunas and 0 <= l < linhas, (ref, n)
    for _, a, b in layout.FIOS:
        for c, l in (a, b):
            assert 0 <= c < colunas and 0 <= l < linhas


def test_nenhum_furo_dividido():
    usados = defaultdict(list)
    for ref, n in todos_os_pinos():
        usados[layout.furo(ref, n)].append((ref, n))
    repetidos = {f: p for f, p in usados.items() if len(p) > 1}
    assert repetidos == {}


def test_fileiras_do_esp_a_10_furos():
    for i in range(1, 23):
        c_dir, l_dir = layout.furo("U1", i)
        c_esq, l_esq = layout.furo("U1", 22 + i)
        assert c_dir - c_esq == 10 and l_dir == l_esq, i
    assert layout.furo("U1", 22)[1] < layout.furo("U1", 1)[1], "GND (pino 22) do lado dos USB-C (trás)"


def test_fileiras_do_mic_a_3_furos():
    sd, vdd, gnd = (layout.furo("U2", n) for n in (1, 2, 3))
    sck, ws, lr = (layout.furo("U2", n) for n in (4, 5, 6))
    assert gnd[0] < vdd[0] < sd[0] and lr[0] < ws[0] < sck[0], "visto de cima: GND VDD SD / L/R WS SCK"
    assert sck[1] - sd[1] == 3 and sck[0] == sd[0]


def test_nenhum_fio_liga_nets_diferentes():
    net_do_furo = {layout.furo(ref, netlist.numero_do_pino(ref, p)): net
                   for net, nos in netlist.NETS.items() for ref, p in nos}
    for net, a, b in layout.FIOS:
        for ponta in (a, b):
            assert net_do_furo.get(ponta) == net, f"fio de {net} termina em {ponta} ({net_do_furo.get(ponta)})"


def test_todas_as_ligacoes_existem():
    for net, nos in netlist.NETS.items():
        furos = {layout.furo(ref, netlist.numero_do_pino(ref, p)) for ref, p in nos}
        grupo = {f: f for f in furos}

        def raiz(f):
            while grupo[f] != f:
                f = grupo[f]
            return f

        for n, a, b in layout.FIOS:
            if n == net:
                grupo[raiz(a)] = raiz(b)
        assert len({raiz(f) for f in furos}) == 1, f"{net} não está toda ligada"


def test_gnd_do_amplificador_com_fio_grosso():
    gnd_amp = layout.furo("U3", 6)
    vin_amp = layout.furo("U3", 7)
    grossos = [(a, b) for net, a, b in layout.FIOS if net in ("GND", "+5V") and (gnd_amp in (a, b) or vin_amp in (a, b))]
    assert grossos and all((a, b) in layout.FIOS_GROSSOS or (b, a) in layout.FIOS_GROSSOS for a, b in grossos)
