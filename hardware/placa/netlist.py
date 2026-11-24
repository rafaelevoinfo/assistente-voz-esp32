"""Ligações da placa do assistente (fonte única: usada pelo montar_pcb.py e gravada em assistente.net).

Uso: python hardware/placa/netlist.py   -> hardware/placa/assistente.net (formato de netlist do KiCad)
"""
from pathlib import Path

# Fileira de baixo da YD-ESP32-S3, na ordem da serigrafia (docs/gerar_ligacoes.py).
FILEIRA_ESP = ["3V3", "3V3", "RST", "4", "5", "6", "7", "15", "16", "17", "18", "8", "3", "46",
               "9", "10", "11", "12", "13", "14", "5Vin", "GND"]
# A outra fileira só segura a placa (sem ligações); pinos 23..44.
FILEIRA_ESP_B = [f"B{i}" for i in range(1, 23)]

# ref -> (valor, footprint, [nomes dos pinos, na ordem dos números 1..n])
COMPONENTES = {
    "U1": ("YD-ESP32-S3", "assistente:YD_ESP32_S3_Soquete", FILEIRA_ESP + FILEIRA_ESP_B),
    "U2": ("INMP441", "assistente:INMP441_Soquete", ["SD", "VDD", "GND", "SCK", "WS", "L/R"]),
    "U3": ("MAX98357A", "assistente:MAX98357A_Soquete", ["LRC", "BCLK", "DIN", "GAIN", "SD", "GND", "VIN"]),
    "RV1": ("B10K WH148", "assistente:WH148_Horizontal", ["1", "2", "3"]),
    "C1": ("470-1000uF 10V", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", ["+", "-"]),
    "C2": ("470-1000uF 10V", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", ["+", "-"]),
    "JP1": ("GANHO 9/12/15dB", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", ["1", "2", "3"]),
    "R1": ("100k", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", ["1", "2"]),
}

# net -> [(ref, nome_do_pino)]   (U1 pelo número do pino, para os rótulos repetidos como "3V3")
NETS = {
    "+3V3": [("U1", 1), ("U2", "VDD"), ("RV1", "1")],
    "GND": [("U1", 22), ("U2", "GND"), ("U2", "L/R"), ("U3", "GND"), ("RV1", "3"),
            ("C1", "-"), ("C2", "-"), ("JP1", "1"), ("R1", "2")],
    "+5V": [("U1", 21), ("U3", "VIN"), ("C1", "+"), ("C2", "+")],
    "I2S_WS": [("U1", 4), ("U2", "WS")],
    "I2S_SCK": [("U1", 5), ("U2", "SCK")],
    "I2S_SD": [("U1", 12), ("U2", "SD")],
    "AMP_LRC": [("U1", 6), ("U3", "LRC")],
    "AMP_BCLK": [("U1", 7), ("U3", "BCLK")],
    "AMP_DIN": [("U1", 15), ("U3", "DIN")],
    "VOL": [("U1", 16), ("RV1", "2")],
    "GAIN": [("U3", "GAIN"), ("JP1", "2")],
    "GAIN_15DB": [("JP1", "3"), ("R1", "1")],
}


def numero_do_pino(ref: str, pino) -> int:
    """Número (1..n) do pino, aceitando o número direto ou o nome."""
    if isinstance(pino, int):
        return pino
    return COMPONENTES[ref][2].index(pino) + 1


def nets_por_pino() -> dict:
    """{(ref, numero): net} — usado pelo montar_pcb.py para ligar os pads."""
    return {(ref, numero_do_pino(ref, p)): net for net, nos in NETS.items() for ref, p in nos}


def _q(texto: str) -> str:
    return '"' + texto.replace('"', '\\"') + '"'


def gerar() -> str:
    linhas = ['(export (version "E")', "  (design (source \"netlist.py\") (tool \"netlist.py\"))", "  (components"]
    for ref, (valor, footprint, _) in COMPONENTES.items():
        linhas.append(f"    (comp (ref {_q(ref)}) (value {_q(valor)}) (footprint {_q(footprint)}))")
    linhas.append("  )")
    linhas.append("  (nets")
    for codigo, (net, nos) in enumerate(NETS.items(), start=1):
        linhas.append(f"    (net (code {_q(str(codigo))}) (name {_q('/' + net)})")
        for ref, pino in nos:
            numero = numero_do_pino(ref, pino)
            nome = COMPONENTES[ref][2][numero - 1]
            linhas.append(f"      (node (ref {_q(ref)}) (pin {_q(str(numero))}) (pinfunction {_q(nome)}))")
        linhas.append("    )")
    linhas.append("  )")
    linhas.append(")")
    return "\n".join(linhas) + "\n"


if __name__ == "__main__":
    saida = Path(__file__).with_name("assistente.net")
    saida.write_text(gerar(), encoding="utf-8")
    print(f"gerado: {saida}")
