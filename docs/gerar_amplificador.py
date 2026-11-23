"""Gera docs/amplificador.svg: como soldar o MAX98357A e ligá-lo à YD-ESP32-S3 e ao alto-falante.

Uso: python docs/gerar_amplificador.py
"""
from pathlib import Path

W, H = 1400, 1040
COR = {"LRC": "#0891b2", "BCLK": "#db2777", "DIN": "#65a30d", "5V": "#dc2626", "GND": "#111827"}
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       'font-family="Segoe UI, Arial, sans-serif">',
       f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
       '<text x="40" y="46" font-size="28" font-weight="700" fill="#111827">Amplificador MAX98357A + alto-falante</text>',
       '<text x="40" y="74" font-size="15" fill="#4b5563">Passo 1: soldar o módulo · Passo 2: ligar na protoboard e no ESP32-S3 · '
       'Passo 3: conferir antes de ligar o USB</text>']


def t(x, y, txt, tam=14, cor="#111827", peso="400", anc="start"):
    svg.append(f'<text x="{x}" y="{y}" font-size="{tam}" fill="{cor}" font-weight="{peso}" text-anchor="{anc}">{txt}</text>')


def titulo_secao(x, y, n, txt):
    svg.append(f'<circle cx="{x + 16}" cy="{y - 7}" r="16" fill="#2563eb"/>')
    t(x + 16, y - 1, n, 17, "#fff", "700", "middle")
    t(x + 42, y, txt, 20, "#111827", "700")


# =====================================================================  PASSO 1: SOLDA
titulo_secao(40, 125, "1", "Soldar o módulo")

# --- módulo visto de cima (esquerda)
MX, MY, MW, MH = 70, 170, 330, 250
svg.append(f'<rect x="{MX}" y="{MY}" width="{MW}" height="{MH}" rx="12" fill="#7c3aed"/>')
t(MX + MW / 2, MY + MH / 2 - 6, "MAX98357A", 18, "#f5f3ff", "700", "middle")
t(MX + MW / 2, MY + MH / 2 + 16, "vista de cima (lado do chip)", 12, "#ddd6fe", "400", "middle")
svg.append(f'<rect x="{MX + MW / 2 - 22}" y="{MY + MH / 2 + 30}" width="44" height="34" rx="4" fill="#111827"/>')
t(MX + MW / 2, MY + MH / 2 + 52, "chip", 11, "#9ca3af", "400", "middle")
# borne do alto-falante (em cima)
BX = MX + MW / 2 - 50
svg.append(f'<rect x="{BX}" y="{MY - 34}" width="100" height="52" rx="6" fill="#16a34a" stroke="#14532d" stroke-width="2"/>')
for i, s in enumerate(["+", "−"]):
    cx = BX + 27 + i * 46
    svg.append(f'<circle cx="{cx}" cy="{MY - 8}" r="12" fill="#d1d5db" stroke="#374151" stroke-width="2"/>')
    svg.append(f'<line x1="{cx - 8}" y1="{MY - 8}" x2="{cx + 8}" y2="{MY - 8}" stroke="#374151" stroke-width="3"/>')
    t(cx, MY + 34, s, 20, "#fff", "700", "middle")
t(BX + 112, MY - 20, "borne de parafuso", 13, "#14532d", "600")
t(BX + 112, MY - 3, "(2 furos com + e −)", 12, "#4b5563")
# fileira de pinos (embaixo)
PINOS_AMP = ["LRC", "BCLK", "DIN", "GAIN", "SD", "GND", "VIN"]
passo = MW / (len(PINOS_AMP) + 1)
for i, p in enumerate(PINOS_AMP):
    px = MX + passo * (i + 1)
    usado = p not in ("GAIN", "SD")
    svg.append(f'<circle cx="{px}" cy="{MY + MH - 26}" r="9" fill="{"#fbbf24" if usado else "#c4b5fd"}" stroke="#111827" stroke-width="2"/>')
    t(px, MY + MH - 44, p, 11, "#fff", "700", "middle")
t(MX + MW / 2, MY + MH + 22, "barra de 7 pinos: solde os 7 (GAIN e SD ficam sem fio)", 12, "#4b5563", "400", "middle")

# --- vista lateral: como a barra entra (direita)
SX, SY = 460, 200
t(SX, SY - 20, "Vista de lado: a barra de pinos", 15, "#111827", "700")
# protoboard
svg.append(f'<rect x="{SX}" y="{SY + 150}" width="330" height="48" rx="6" fill="#f5f5f4" stroke="#a8a29e" stroke-width="2"/>')
t(SX + 165, SY + 180, "protoboard", 13, "#78716c", "400", "middle")
# placa do módulo
svg.append(f'<rect x="{SX + 40}" y="{SY + 52}" width="250" height="14" rx="3" fill="#7c3aed"/>')
t(SX + 165, SY + 14, "módulo (chip para cima)", 12, "#7c3aed", "600", "middle")
# pinos
for i in range(7):
    px = SX + 70 + i * 32
    svg.append(f'<rect x="{px - 3}" y="{SY + 30}" width="6" height="22" fill="#a16207"/>')     # ponta curta (em cima)
    svg.append(f'<rect x="{px - 3}" y="{SY + 66}" width="6" height="96" fill="#a16207"/>')     # ponta longa (embaixo)
    svg.append(f'<rect x="{px - 8}" y="{SY + 78}" width="16" height="16" fill="#111827"/>')   # plástico preto
    svg.append(f'<path d="M{px - 9},{SY + 52} L{px + 9},{SY + 52} L{px + 4},{SY + 38} L{px - 4},{SY + 38} Z" fill="#9ca3af"/>')  # solda
t(SX + 300, SY + 46, "← solde aqui", 12, "#b45309", "600")
t(SX + 300, SY + 91, "← plástico preto", 12, "#4b5563")
t(SX + 300, SY + 132, "← ponta longa", 12, "#4b5563")
t(SX + 314, SY + 147, "na protoboard", 12, "#4b5563")

# --- instruções de solda
IX = 920
passos = [
    ("Barra de pinos", [
        "Encaixe a barra na protoboard (ponta longa para baixo)",
        "e apoie o módulo por cima, chip para cima. A protoboard",
        "segura tudo reto enquanto você solda.",
        "Solde 1 pino de uma ponta, confira se está reto,",
        "depois a outra ponta, e então os do meio."]),
    ("Borne do alto-falante", [
        "Encaixe o borne verde por cima, com os furos dos fios",
        "virados para FORA da placa, e solde os 2 pinos por baixo."]),
    ("Fios do alto-falante", [
        "Se o alto-falante não tiver fios: solde um fio vermelho no",
        "terminal marcado + (ou ponto vermelho) e um preto no outro.",
        "Desencape ~5 mm, prenda no borne: vermelho no +, preto no −,",
        "e aperte o parafuso. A polaridade só inverte a fase do som."]),
    ("Ponto de solda bom", [
        "Ferro em ~330 °C, encoste no pino E na ilha ao mesmo tempo,",
        "2 s, aí encoste o estanho. Fica um cone brilhante.",
        "Cuidado para não emendar dois pinos vizinhos com estanho."]),
]
y = 170
for i, (cab, linhas) in enumerate(passos):
    t(IX, y, f"{chr(97 + i)}) {cab}", 15, "#1d4ed8", "700")
    y += 21
    for linha in linhas:
        t(IX + 18, y, linha, 13, "#111827")
        y += 19
    y += 12

# =====================================================================  PASSO 2: LIGAÇÕES
Y2 = 560
titulo_secao(40, Y2, "2", "Ligar no ESP32-S3 (fios na protoboard)")

# placa (resumida)
PX, PY = 70, Y2 + 40
svg.append(f'<rect x="{PX}" y="{PY}" width="380" height="300" rx="12" fill="#1f2937"/>')
t(PX + 190, PY + 30, "YD-ESP32-S3", 18, "#e5e7eb", "700", "middle")
t(PX + 190, PY + 50, "(pinos usados; nomes como na serigrafia)", 12, "#9ca3af", "400", "middle")
PINOS_ESP = [("6", "LRC"), ("7", "BCLK"), ("9", "DIN"), ("5Vin", "5V"), ("GND", "GND")]
ESP_Y = {}
for i, (p, k) in enumerate(PINOS_ESP):
    py = PY + 90 + i * 44
    ESP_Y[k] = py
    rotulo = p if not p.isdigit() else f"GPIO{p}"
    t(PX + 340, py + 5, rotulo, 14, "#f9fafb", "600", "end")
    svg.append(f'<circle cx="{PX + 365}" cy="{py}" r="9" fill="#fbbf24" stroke="#111827" stroke-width="2"/>')

# módulo (resumido)
AX, AY = 760, Y2 + 40
svg.append(f'<rect x="{AX}" y="{AY}" width="260" height="300" rx="12" fill="#7c3aed"/>')
t(AX + 130, AY + 30, "MAX98357A", 18, "#f5f3ff", "700", "middle")
AMP_Y = {}
for i, (p, k) in enumerate([("LRC", "LRC"), ("BCLK", "BCLK"), ("DIN", "DIN"), ("VIN", "5V"), ("GND", "GND")]):
    py = AY + 90 + i * 44
    AMP_Y[k] = py
    svg.append(f'<circle cx="{AX - 0}" cy="{py}" r="9" fill="#fbbf24" stroke="#111827" stroke-width="2"/>')
    t(AX + 20, py + 5, p, 14, "#fff", "700")
t(AX + 130, AY + 282, "GAIN e SD: sem fio", 12, "#ddd6fe", "400", "middle")

# fios
for k in ["LRC", "BCLK", "DIN", "5V", "GND"]:
    x1, y1, x2, y2 = PX + 374, ESP_Y[k], AX - 9, AMP_Y[k]
    svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{COR[k]}" stroke-width="5" stroke-linecap="round"/>')

# capacitor entre VIN e GND, perto do módulo
CX = AX - 90
svg.append(f'<line x1="{CX}" y1="{AMP_Y["5V"]}" x2="{CX}" y2="{AMP_Y["GND"]}" stroke="#6b7280" stroke-width="3"/>')
svg.append(f'<rect x="{CX - 15}" y="{(AMP_Y["5V"] + AMP_Y["GND"]) / 2 - 16}" width="30" height="32" rx="5" fill="#1d4ed8" stroke="#fff" stroke-width="2"/>')
t(CX, (AMP_Y["5V"] + AMP_Y["GND"]) / 2 + 5, "C", 13, "#fff", "700", "middle")
t(CX - 60, AMP_Y["GND"] + 48, "capacitor eletrolítico 470–1000 µF (ou 3–4 × 100 µF em paralelo)", 12, "#1d4ed8", "600", "middle")
t(CX - 60, AMP_Y["GND"] + 66, "entre VIN e GND, colado no módulo · perna da faixa \"−\" no GND", 12, "#1d4ed8", "400", "middle")

# alto-falante
svg.append(f'<rect x="{AX + 75}" y="{AY - 2}" width="110" height="16" rx="3" fill="#16a34a"/>')
svg.append(f'<path d="M{AX + 105},{AY - 2} C{AX + 105},{AY - 40} {AX + 230},{AY - 30} {AX + 290},{AY + 40}" fill="none" stroke="#dc2626" stroke-width="4"/>')
svg.append(f'<path d="M{AX + 155},{AY - 2} C{AX + 155},{AY - 25} {AX + 220},{AY - 10} {AX + 290},{AY + 60}" fill="none" stroke="#111827" stroke-width="4"/>')
svg.append(f'<circle cx="{AX + 330}" cy="{AY + 60}" r="46" fill="#e5e7eb" stroke="#374151" stroke-width="3"/>')
svg.append(f'<circle cx="{AX + 330}" cy="{AY + 60}" r="20" fill="#9ca3af"/>')
t(AX + 330, AY + 130, "alto-falante", 13, "#111827", "600", "middle")
t(AX + 330, AY + 147, "4–8 Ω, até 3 W", 12, "#4b5563", "400", "middle")

# tabela resumo
TX, TY = 1060, Y2 + 240
t(TX, TY - 10, "Resumo", 15, "#111827", "700")
linhas = [("LRC", "GPIO6", "LRC"), ("BCLK", "GPIO7", "BCLK"), ("DIN", "GPIO9", "DIN"),
          ("VIN", "5Vin", "5V"), ("GND", "GND", "GND")]
for i, (a, b, k) in enumerate(linhas):
    yy = TY + 14 + i * 22
    svg.append(f'<line x1="{TX}" y1="{yy - 5}" x2="{TX + 24}" y2="{yy - 5}" stroke="{COR[k]}" stroke-width="5"/>')
    t(TX + 32, yy, f"{a}  →  {b}", 14, "#111827", "600")

# =====================================================================  PASSO 3: AVISOS
YA = H - 70
titulo_secao(40, YA - 8, "3", "Antes de ligar o USB")
t(78, YA + 20, "• VIN do amplificador no 5Vin (5 V), não no 3V3.  • O GND do amplificador e o do microfone vão no MESMO GND "
  "(use a trilha azul da protoboard).", 13, "#111827")
t(78, YA + 42, "• Com o jumper IN-OUT fechado, nunca ligue fonte externa no 5Vin com o USB conectado.  "
  "• O microfone (INMP441) continua como está.", 13, "#b91c1c", "600")

svg.append("</svg>")
saida = Path(__file__).with_name("amplificador.svg")
saida.write_text("\n".join(svg), encoding="utf-8")
print(f"gerado: {saida}")
