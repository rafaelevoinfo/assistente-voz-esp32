"""Task 2: as ligações da placa são as mesmas da protoboard (docs/ligacoes.png)."""
import sexp
import subprocess
import sys
from pathlib import Path

import pytest

HW = Path(__file__).resolve().parents[1]
NET = HW / "placa" / "assistente.net"

# Fileira de baixo da YD-ESP32-S3, na ordem da serigrafia (igual a docs/gerar_ligacoes.py).
FILEIRA_ESP = ["3V3", "3V3", "RST", "4", "5", "6", "7", "15", "16", "17", "18", "8", "3", "46",
               "9", "10", "11", "12", "13", "14", "5Vin", "GND"]


@pytest.fixture(scope="module")
def netlist():
    """({net: {(ref, numero, nome_do_pino)}}, {(ref, numero): nome_do_pino}) lidos do .net gerado."""
    subprocess.run([sys.executable, str(HW / "placa" / "netlist.py")], check=True)
    raiz = sexp.ler(NET.read_text(encoding="utf-8"))
    nets, pinos = {}, {}
    for net in sexp.filhos(sexp.filhos(raiz, "nets")[0], "net"):
        nome = sexp.valor(net, "name").lstrip("/")
        nos = set()
        for no in sexp.filhos(net, "node"):
            ref, numero = sexp.valor(no, "ref"), sexp.valor(no, "pin")
            funcao = sexp.valor(no, "pinfunction", "")
            nos.add((ref, numero, funcao))
            pinos[(ref, numero)] = funcao
        nets[nome] = nos
    return nets, pinos


def net_de(netlist, ref, nome_pino):
    nets, _ = netlist
    achadas = [n for n, nos in nets.items() if any(r == ref and f == nome_pino for r, _, f in nos)]
    return achadas[0] if achadas else None


def esp(netlist, rotulo, ocorrencia=0):
    """Net ligada ao pino do U1 com esse rótulo da serigrafia."""
    numero = str([i for i, p in enumerate(FILEIRA_ESP) if p == rotulo][ocorrencia] + 1)
    nets, _ = netlist
    achadas = [n for n, nos in nets.items() if any(r == "U1" and p == numero for r, p, _ in nos)]
    return achadas[0] if achadas else None


def test_ordem_dos_pinos_do_esp(netlist):
    _, pinos = netlist
    for i, rotulo in enumerate(FILEIRA_ESP, start=1):
        if ("U1", str(i)) in pinos:
            assert pinos[("U1", str(i))] == rotulo, f"U1 pino {i}"


def test_ligacoes_do_mic(netlist):
    assert net_de(netlist, "U2", "VDD") == esp(netlist, "3V3") == "+3V3"
    assert net_de(netlist, "U2", "GND") == "GND"
    assert net_de(netlist, "U2", "L/R") == "GND"
    assert net_de(netlist, "U2", "WS") == esp(netlist, "4") == "I2S_WS"
    assert net_de(netlist, "U2", "SCK") == esp(netlist, "5") == "I2S_SCK"
    assert net_de(netlist, "U2", "SD") == esp(netlist, "8") == "I2S_SD"


def test_ligacoes_do_amp(netlist):
    assert net_de(netlist, "U3", "LRC") == esp(netlist, "6") == "AMP_LRC"
    assert net_de(netlist, "U3", "BCLK") == esp(netlist, "7") == "AMP_BCLK"
    assert net_de(netlist, "U3", "DIN") == esp(netlist, "9") == "AMP_DIN"
    assert net_de(netlist, "U3", "VIN") == esp(netlist, "5Vin") == "+5V"
    assert net_de(netlist, "U3", "GND") == esp(netlist, "GND") == "GND"
    assert net_de(netlist, "U3", "SD") is None


def test_potenciometro(netlist):
    pontas = {net_de(netlist, "RV1", "1"), net_de(netlist, "RV1", "3")}
    assert pontas == {"+3V3", "GND"}
    assert net_de(netlist, "RV1", "2") == esp(netlist, "10") == "VOL"


def test_capacitores_em_paralelo(netlist):
    for c in ("C1", "C2"):
        assert net_de(netlist, c, "+") == "+5V", c
        assert net_de(netlist, c, "-") == "GND", c


def test_jumper_de_ganho(netlist):
    assert net_de(netlist, "JP1", "2") == net_de(netlist, "U3", "GAIN") == "GAIN"
    assert net_de(netlist, "JP1", "1") == "GND"
    r1 = {net_de(netlist, "R1", "1"), net_de(netlist, "R1", "2")}
    assert net_de(netlist, "JP1", "3") in r1 and "GND" in r1
