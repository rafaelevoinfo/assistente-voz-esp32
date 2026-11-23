"""Gera docs/capacitor.svg: como ligar o capacitor do MAX98357A na protoboard.

Uso: python docs/gerar_capacitor.py
"""
from pathlib import Path

W, H = 1300, 920
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       'font-family="Segoe UI, Arial, sans-serif">',
       f'<rect width="{W}" height="{H}" fill="#ffffff"/>']


def t(x, y, txt, tam=14, cor="#111827", peso="400", anc="start"):
    svg.append(f'<text x="{x}" y="{y}" font-size="{tam}" fill="{cor}" font-weight="{peso}" text-anchor="{anc}">{txt}</text>')


t(40, 46, "Capacitor do amplificador: em paralelo entre VIN e GND", 26, "#111827", "700")
t(40, 74, "Ele fica \"pendurado\" entre os dois fios de alimentação, como uma caixa d'água: guarda energia e "
  "entrega nos picos de volume.", 15, "#4b5563")

# ============================================================ 1. O CAPACITOR
t(40, 125, "1. Reconheça as pernas", 19, "#1d4ed8", "700")
CX, CY = 150, 175
svg.append(f'<rect x="{CX}" y="{CY}" width="80" height="130" rx="14" fill="#1e3a8a"/>')
svg.append(f'<rect x="{CX + 52}" y="{CY}" width="28" height="130" rx="0" fill="#cbd5e1"/>')
svg.append(f'<rect x="{CX + 52}" y="{CY}" width="28" height="130" rx="14" fill="#cbd5e1"/>')
for i in range(4):
    t(CX + 66, CY + 30 + i * 28, "−", 22, "#1e3a8a", "700", "middle")
t(CX + 20, CY + 72, "1000", 12, "#e0e7ff", "600", "middle")
t(CX + 20, CY + 88, "µF", 12, "#e0e7ff", "600", "middle")
# pernas: + longa (esquerda), − curta (direita, embaixo da faixa)
svg.append(f'<rect x="{CX + 18}" y="{CY + 130}" width="5" height="120" fill="#9ca3af"/>')
svg.append(f'<rect x="{CX + 60}" y="{CY + 130}" width="5" height="85" fill="#9ca3af"/>')
t(CX + 20, CY + 272, "+", 24, "#dc2626", "700", "middle")
t(CX + 62, CY + 237, "−", 24, "#111827", "700", "middle")
t(CX + 110, CY + 40, "← faixa clara com sinais \"−\"", 14, "#111827", "600")
t(CX + 110, CY + 60, "   = lado NEGATIVO", 14, "#111827")
t(CX + 110, CY + 200, "← perna curta (embaixo da faixa) = −  → vai no GND", 14, "#111827", "600")
t(CX + 110, CY + 250, "← perna longa = +  → vai no VIN (5V)", 14, "#dc2626", "600")
t(40, CY + 310, "⚠ Eletrolítico tem polaridade: invertido ele esquenta e pode estufar. A tensão escrita nele deve ser ≥ 10 V.",
  13, "#b91c1c", "600")

# ============================================================ 2. ESQUEMA
t(720, 125, "2. A ideia (esquema)", 19, "#1d4ed8", "700")
EX = 740
# fio 5V em cima e GND embaixo
svg.append(f'<line x1="{EX}" y1="190" x2="{EX + 480}" y2="190" stroke="#dc2626" stroke-width="6"/>')
svg.append(f'<line x1="{EX}" y1="350" x2="{EX + 480}" y2="350" stroke="#111827" stroke-width="6"/>')
t(EX, 178, "ESP32  5Vin", 14, "#dc2626", "700")
t(EX, 376, "ESP32  GND", 14, "#111827", "700")
# módulo à direita
svg.append(f'<rect x="{EX + 380}" y="160" width="110" height="220" rx="10" fill="#7c3aed"/>')
t(EX + 435, 270, "MAX", 15, "#fff", "700", "middle")
t(EX + 435, 288, "98357A", 15, "#fff", "700", "middle")
t(EX + 392, 208, "VIN", 13, "#fff", "700")
t(EX + 392, 342, "GND", 13, "#fff", "700")
# capacitor no meio, em paralelo
KX = EX + 250
svg.append(f'<line x1="{KX}" y1="190" x2="{KX}" y2="255" stroke="#6b7280" stroke-width="4"/>')
svg.append(f'<line x1="{KX}" y1="285" x2="{KX}" y2="350" stroke="#6b7280" stroke-width="4"/>')
svg.append(f'<line x1="{KX - 26}" y1="255" x2="{KX + 26}" y2="255" stroke="#111827" stroke-width="5"/>')
svg.append(f'<path d="M{KX - 26},{292} Q{KX},{276} {KX + 26},{292}" fill="none" stroke="#111827" stroke-width="5"/>')
t(KX + 34, 252, "+", 18, "#dc2626", "700")
t(KX + 34, 300, "−", 18, "#111827", "700")
svg.append(f'<circle cx="{KX}" cy="190" r="7" fill="#dc2626"/>')
svg.append(f'<circle cx="{KX}" cy="350" r="7" fill="#111827"/>')
t(KX - 40, 270, "C", 18, "#1d4ed8", "700", "end")
t(EX + 60, 420, "Os fios continuam indo direto ao módulo; o capacitor só é", 14, "#111827")
t(EX + 60, 440, "uma \"ponte\" a mais entre os dois, perto do módulo.", 14, "#111827")

# ============================================================ 3. NA PROTOBOARD
Y3 = 520
t(40, Y3, "3. Na protoboard (vista de cima)", 19, "#1d4ed8", "700")
PX, PY, PW = 60, Y3 + 30, 1180
svg.append(f'<rect x="{PX}" y="{PY}" width="{PW}" height="300" rx="10" fill="#f5f5f4" stroke="#a8a29e" stroke-width="2"/>')
COLS = 34
PASSO = 32
X0 = PX + 40
LIN_Y = [PY + 60 + i * 26 for i in range(5)]  # 5 furos por coluna (a-e), ligados verticalmente
for c in range(COLS):
    x = X0 + c * PASSO
    for y in LIN_Y:
        svg.append(f'<rect x="{x - 4}" y="{y - 4}" width="8" height="8" rx="1" fill="#d6d3d1"/>')
t(X0 - 26, LIN_Y[0] + 5, "a", 11, "#78716c")
t(X0 - 26, LIN_Y[4] + 5, "e", 11, "#78716c")
t(PX + PW - 10, PY + 30, "cada coluna de 5 furos é ligada por dentro (a até e)", 12, "#78716c", "400", "end")

# módulo encaixado na linha "a", 7 pinos nas colunas 18..24
PINOS = ["LRC", "BCLK", "DIN", "GAIN", "SD", "GND", "VIN"]
C0 = 18
col = {p: C0 + i for i, p in enumerate(PINOS)}
xm = lambda p: X0 + col[p] * PASSO
svg.append(f'<rect x="{xm("LRC") - 22}" y="{PY + 4}" width="{6 * PASSO + 44}" height="50" rx="6" fill="#7c3aed" opacity="0.92"/>')
t((xm("LRC") + xm("VIN")) / 2, PY + 26, "MAX98357A (pinos na fileira a)", 13, "#fff", "700", "middle")
for p in PINOS:
    svg.append(f'<circle cx="{xm(p)}" cy="{LIN_Y[0]}" r="7" fill="#fbbf24" stroke="#111827" stroke-width="2"/>')
    t(xm(p), PY + 48, p, 10, "#fff", "700", "middle")

# destaca as colunas do GND e do VIN
for p, cor in (("GND", "#111827"), ("VIN", "#dc2626")):
    svg.append(f'<rect x="{xm(p) - 12}" y="{LIN_Y[0] - 12}" width="24" height="{LIN_Y[4] - LIN_Y[0] + 24}" rx="6" '
               f'fill="none" stroke="{cor}" stroke-width="2.5" stroke-dasharray="5 3"/>')

# capacitor em pé, visto de cima: um círculo entre as colunas do GND e do VIN (fileira c)
yc = LIN_Y[2]
cxm = (xm("GND") + xm("VIN")) / 2
R = 30
svg.append(f'<circle cx="{cxm}" cy="{yc}" r="{R}" fill="#1e3a8a" stroke="#0f172a" stroke-width="2"/>')
svg.append(f'<path d="M{cxm},{yc - R} A{R},{R} 0 0 0 {cxm},{yc + R} Z" fill="#cbd5e1"/>')
t(cxm - 14, yc + 6, "−", 18, "#1e3a8a", "700", "middle")
t(cxm + 14, yc + 6, "+", 18, "#fff", "700", "middle")
svg.append(f'<circle cx="{xm("GND")}" cy="{yc}" r="4" fill="#111827"/>')
svg.append(f'<circle cx="{xm("VIN")}" cy="{yc}" r="4" fill="#fecaca"/>')
t(xm("GND") - R - 8, yc - 8, "perna − (lado da faixa)", 13, "#111827", "700", "end")
t(xm("GND") - R - 8, yc + 10, "na coluna do GND", 13, "#111827", "400", "end")
t(xm("VIN") + R + 8, yc - 8, "perna + na", 13, "#dc2626", "700")
t(xm("VIN") + R + 8, yc + 10, "coluna do VIN", 13, "#dc2626", "400")
t(xm("VIN") + R + 8, yc + 30, "(capacitor em pé, visto de cima)", 12, "#1e3a8a", "600")

# fios do ESP chegando nas mesmas colunas (fileira e)
for p, cor, rot in (("GND", "#111827", "fio do GND do ESP32"), ("VIN", "#dc2626", "fio do 5Vin do ESP32")):
    x = xm(p)
    svg.append(f'<circle cx="{x}" cy="{LIN_Y[4]}" r="6" fill="{cor}"/>')
svg.append(f'<path d="M{xm("GND")},{LIN_Y[4]} L{xm("GND")},{PY + 300 + 30}" fill="none" stroke="#111827" stroke-width="5"/>')
svg.append(f'<path d="M{xm("VIN")},{LIN_Y[4]} L{xm("VIN")},{PY + 300 + 30}" fill="none" stroke="#dc2626" stroke-width="5"/>')
t(xm("GND") - 10, PY + 322, "fio do GND do ESP32", 13, "#111827", "700", "end")
t(xm("VIN") + 10, PY + 322, "fio do 5Vin do ESP32", 13, "#dc2626", "700")

# explicação à esquerda
t(X0, PY + 210, "Como fica: na mesma coluna do pino GND do módulo", 14, "#111827", "600")
t(X0, PY + 230, "entram a perna − do capacitor e o fio de GND do ESP32.", 14, "#111827")
t(X0, PY + 250, "Na coluna do VIN, a perna + e o fio do 5Vin.", 14, "#111827")

svg.append("</svg>")
saida = Path(__file__).with_name("capacitor.svg")
saida.write_text("\n".join(svg), encoding="utf-8")
print(f"gerado: {saida}")
