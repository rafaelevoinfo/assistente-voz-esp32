"""Gera docs/ligacoes.svg: diagrama de ligações da placa (YD-ESP32-S3) com o INMP441 e o MAX98357A.

Uso: python docs/gerar_ligacoes.py
"""
from pathlib import Path

# Fileira de baixo da YD-ESP32-S3 (mesma ordem da serigrafia, da esquerda para a direita)
PINOS = ["3V3", "3V3", "RST", "4", "5", "6", "7", "15", "16", "17", "18", "8", "3", "46",
         "9", "10", "11", "12", "13", "14", "5Vin", "GND"]

W, H = 1180, 760
X0, PASSO, Y_PINO = 120, 44, 250  # posição dos pinos na placa

COR = {"3V3": "#d97706", "5V": "#dc2626", "GND": "#111827", "WS": "#2563eb", "SCK": "#7c3aed",
       "SD": "#059669", "LRC": "#0891b2", "BCLK": "#db2777", "DIN": "#65a30d"}


def xp(nome, ocorrencia=0):
    idx = [i for i, p in enumerate(PINOS) if p == nome][ocorrencia]
    return X0 + idx * PASSO


svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       'font-family="Segoe UI, Arial, sans-serif">',
       f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
       '<text x="40" y="44" font-size="26" font-weight="700" fill="#111827">Ligações: assistente de voz "Hi ESP"</text>',
       '<text x="40" y="72" font-size="15" fill="#4b5563">Placa YD-ESP32-S3 N16R8 vista de cima · linha cheia = já montado · '
       'linha tracejada = MAX98357A (quando chegar)</text>']

# ---- placa
svg.append(f'<rect x="{X0 - 40}" y="100" width="{PASSO * len(PINOS) + 40}" height="170" rx="10" fill="#1f2937"/>')
svg.append(f'<text x="{X0 + 380}" y="165" font-size="20" fill="#e5e7eb" font-weight="600">ESP32-S3 (YD-ESP32-S3 N16R8)</text>')
svg.append(f'<text x="{X0 + 380}" y="190" font-size="13" fill="#9ca3af">fileira de pinos de baixo · USB-C à direita</text>')
# jumpers e LED
svg.append(f'<rect x="{X0 + 20}" y="125" width="170" height="70" rx="6" fill="#374151"/>')
svg.append(f'<text x="{X0 + 30}" y="147" font-size="13" fill="#fbbf24" font-weight="600">Jumpers fechados (solda):</text>')
svg.append(f'<text x="{X0 + 30}" y="167" font-size="13" fill="#e5e7eb">• RGB  → LED no GPIO48</text>')
svg.append(f'<text x="{X0 + 30}" y="185" font-size="13" fill="#e5e7eb">• IN-OUT → 5V no pino 5Vin</text>')
svg.append(f'<circle cx="{X0 + 260}" cy="150" r="13" fill="#22c55e" stroke="#e5e7eb" stroke-width="2"/>')
svg.append(f'<text x="{X0 + 238}" y="186" font-size="12" fill="#e5e7eb">LED RGB</text>')
for i, p in enumerate(PINOS):
    x = X0 + i * PASSO
    usado = p in ("3V3", "4", "5", "6", "7", "8", "9", "5Vin", "GND")
    svg.append(f'<circle cx="{x}" cy="{Y_PINO}" r="9" fill="{"#fbbf24" if usado else "#6b7280"}" stroke="#111827" stroke-width="2"/>')
    svg.append(f'<text x="{x}" y="{Y_PINO - 18}" font-size="12" text-anchor="middle" fill="#f9fafb">{p}</text>')
svg.append(f'<rect x="{X0 + PASSO * len(PINOS) - 10}" y="150" width="34" height="60" rx="6" fill="#9ca3af"/>')
svg.append(f'<text x="{X0 + PASSO * len(PINOS) - 20}" y="185" font-size="12" text-anchor="end" fill="#e5e7eb">USB-C (alimentação) →</text>')


def modulo(x, y, w, titulo, pinos, sub=""):
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="130" rx="10" fill="#f3f4f6" stroke="#9ca3af" stroke-width="2"/>')
    svg.append(f'<text x="{x + w / 2}" y="{y + 100}" font-size="18" text-anchor="middle" font-weight="700" fill="#111827">{titulo}</text>')
    if sub:
        svg.append(f'<text x="{x + w / 2}" y="{y + 120}" font-size="12" text-anchor="middle" fill="#4b5563">{sub}</text>')
    pos = {}
    passo = w / (len(pinos) + 1)
    for i, p in enumerate(pinos):
        px = x + passo * (i + 1)
        svg.append(f'<circle cx="{px}" cy="{y}" r="8" fill="#fbbf24" stroke="#111827" stroke-width="2"/>')
        svg.append(f'<text x="{px}" y="{y + 30}" font-size="13" text-anchor="middle" font-weight="600" fill="#111827">{p}</text>')
        pos[p] = px
    return pos


def fio(x1, x2, y2, cor, nivel, tracejado=False):
    """Fio do pino da placa (x1) até o pino do módulo (x2, y2), com uma 'pista' horizontal no nível dado."""
    y_pista = Y_PINO + 40 + nivel * 16
    traco = ' stroke-dasharray="9 6"' if tracejado else ""
    svg.append(f'<polyline points="{x1},{Y_PINO + 9} {x1},{y_pista} {x2},{y_pista} {x2},{y2 - 8}" fill="none" '
               f'stroke="{cor}" stroke-width="4" stroke-linejoin="round"{traco}/>')


# ---- INMP441 (montado)
Y_MOD = 520
mic = modulo(120, Y_MOD, 420, "INMP441 (microfone)", ["VDD", "GND", "L/R", "WS", "SCK", "SD"],
             "furo do mic para cima · L/R no GND = canal esquerdo")
fio(xp("3V3"), mic["VDD"], Y_MOD, COR["3V3"], 0)
fio(xp("4"), mic["WS"], Y_MOD, COR["WS"], 1)
fio(xp("5"), mic["SCK"], Y_MOD, COR["SCK"], 2)
fio(xp("8"), mic["SD"], Y_MOD, COR["SD"], 3)
fio(xp("GND"), mic["GND"], Y_MOD, COR["GND"], 9)
svg.append(f'<polyline points="{mic["GND"]},{Y_MOD - 8} {mic["GND"]},{Y_MOD - 30} {mic["L/R"]},{Y_MOD - 30} {mic["L/R"]},{Y_MOD - 8}" '
           f'fill="none" stroke="{COR["GND"]}" stroke-width="4"/>')

# ---- MAX98357A (futuro, tracejado)
amp = modulo(620, Y_MOD, 440, "MAX98357A (amplificador)", ["LRC", "BCLK", "DIN", "GAIN", "SD", "GND", "VIN"],
             "GAIN e SD soltos · alto-falante nos bornes + e −")
fio(xp("6"), amp["LRC"], Y_MOD, COR["LRC"], 4, True)
fio(xp("7"), amp["BCLK"], Y_MOD, COR["BCLK"], 5, True)
fio(xp("9"), amp["DIN"], Y_MOD, COR["DIN"], 6, True)
fio(xp("5Vin"), amp["VIN"], Y_MOD, COR["5V"], 7, True)
fio(xp("GND"), amp["GND"], Y_MOD, COR["GND"], 8, True)
# capacitor junto ao VIN/GND
cx = (amp["GND"] + amp["VIN"]) / 2
svg.append(f'<rect x="{cx - 16}" y="{Y_MOD - 62}" width="32" height="22" rx="4" fill="#1d4ed8"/>')
svg.append(f'<text x="{cx}" y="{Y_MOD - 46}" font-size="10" text-anchor="middle" fill="#fff">C</text>')
svg.append(f'<text x="{cx - 26}" y="{Y_MOD - 54}" font-size="12" text-anchor="end" fill="#1d4ed8">capacitor 470–1000 µF entre VIN e GND</text>')
svg.append(f'<text x="{cx - 26}" y="{Y_MOD - 39}" font-size="12" text-anchor="end" fill="#1d4ed8">(faixa "−" no GND, perto do módulo)</text>')
# alto-falante
svg.append(f'<circle cx="1110" cy="{Y_MOD + 65}" r="38" fill="#e5e7eb" stroke="#374151" stroke-width="3" stroke-dasharray="7 5"/>')
svg.append(f'<text x="1110" y="{Y_MOD + 70}" font-size="13" text-anchor="middle" fill="#111827">alto-</text>')
svg.append(f'<text x="1110" y="{Y_MOD + 86}" font-size="13" text-anchor="middle" fill="#111827">falante</text>')
svg.append(f'<line x1="1060" y1="{Y_MOD + 55}" x2="1072" y2="{Y_MOD + 55}" stroke="#374151" stroke-width="3" stroke-dasharray="4 3"/>')
svg.append(f'<text x="1110" y="{Y_MOD + 125}" font-size="12" text-anchor="middle" fill="#4b5563">4 Ω, 3 W</text>')

# ---- legenda
legenda = [("3V3", "3V3"), ("5V", "5Vin"), ("GND", "GND"), ("WS", "WS → GPIO4"), ("SCK", "SCK → GPIO5"),
           ("SD", "SD → GPIO8"), ("LRC", "LRC → GPIO6"), ("BCLK", "BCLK → GPIO7"), ("DIN", "DIN → GPIO9")]
for i, (k, txt) in enumerate(legenda):
    x = 40 + i * 125
    svg.append(f'<line x1="{x}" y1="{H - 30}" x2="{x + 26}" y2="{H - 30}" stroke="{COR[k]}" stroke-width="5"/>')
    svg.append(f'<text x="{x + 32}" y="{H - 25}" font-size="13" fill="#111827">{txt}</text>')
svg.append(f'<text x="40" y="{H - 52}" font-size="13" fill="#b91c1c" font-weight="600">⚠ VDD do microfone no 3V3, nunca no 5V. '
           'Com o IN-OUT fechado, não ligue fonte externa no 5Vin junto com o USB.</text>')
svg.append("</svg>")

saida = Path(__file__).with_name("ligacoes.svg")
saida.write_text("\n".join(svg), encoding="utf-8")
print(f"gerado: {saida}")
