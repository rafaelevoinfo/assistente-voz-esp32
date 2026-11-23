"""Gera docs/potenciometro.svg: como ligar o potenciômetro de volume na YD-ESP32-S3.

Uso: python docs/gerar_potenciometro.py
"""
from pathlib import Path

W, H = 1100, 700
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       'font-family="Segoe UI, Arial, sans-serif">',
       f'<rect width="{W}" height="{H}" fill="#ffffff"/>']


def t(x, y, txt, tam=14, cor="#111827", peso="400", anc="start"):
    svg.append(f'<text x="{x}" y="{y}" font-size="{tam}" fill="{cor}" font-weight="{peso}" text-anchor="{anc}">{txt}</text>')


t(40, 46, "Potenciômetro de volume (10 kΩ)", 26, "#111827", "700")
t(40, 74, "Três pernas: as das pontas vão no 3V3 e no GND; a do meio (cursor) vai no GPIO10.", 15, "#4b5563")

# ---- potenciômetro visto de frente (eixo para você)
PX, PY = 170, 300
svg.append(f'<rect x="{PX - 110}" y="{PY - 110}" width="220" height="170" rx="14" fill="#1f2937"/>')
svg.append(f'<circle cx="{PX}" cy="{PY - 25}" r="58" fill="#4b5563" stroke="#111827" stroke-width="3"/>')
svg.append(f'<circle cx="{PX}" cy="{PY - 25}" r="30" fill="#9ca3af" stroke="#111827" stroke-width="3"/>')
svg.append(f'<line x1="{PX}" y1="{PY - 25}" x2="{PX}" y2="{PY - 52}" stroke="#111827" stroke-width="5" stroke-linecap="round"/>')
t(PX, PY - 140, "visto de frente (eixo para você)", 13, "#4b5563", "400", "middle")
PERNAS = [(PX - 70, "1", "#d97706"), (PX, "2", "#2563eb"), (PX + 70, "3", "#111827")]
for x, n, cor in PERNAS:
    svg.append(f'<rect x="{x - 6}" y="{PY + 60}" width="12" height="70" fill="#a8a29e"/>')
    t(x + 14, PY + 85, n, 15, cor, "700")
t(PX - 84, PY + 110, "ponta", 12, "#d97706", "600", "end")
t(PX + 12, PY + 110, "meio", 12, "#2563eb", "600")
t(PX + 84, PY + 110, "ponta", 12, "#111827", "600")

# ---- ESP32 (resumo)
EX, EY = 700, 170
svg.append(f'<rect x="{EX}" y="{EY}" width="300" height="300" rx="12" fill="#1f2937"/>')
t(EX + 150, EY + 32, "YD-ESP32-S3", 18, "#e5e7eb", "700", "middle")
PINOS = {"GND": EY + 100, "GPIO10": EY + 170, "3V3": EY + 240}
for nome, y in PINOS.items():
    svg.append(f'<circle cx="{EX}" cy="{y}" r="9" fill="#fbbf24" stroke="#111827" stroke-width="2"/>')
    t(EX + 22, y + 5, nome, 15, "#f9fafb", "700")
t(EX + 150, EY + 280, "GPIO10 fica ao lado do GPIO9 (DIN)", 12, "#9ca3af", "400", "middle")

# ---- fios: cada um desce até uma "pista" própria, sem sobrepor
def fio(x1, y1, x2, y2, cor, pista, coluna):
    yp = y1 + 60 + pista * 26
    svg.append(f'<polyline points="{x1},{y1} {x1},{yp} {coluna},{yp} {coluna},{y2} {x2 - 9},{y2}" fill="none" '
               f'stroke="{cor}" stroke-width="5" stroke-linejoin="round"/>')

fio(PX + 70, PY + 130, EX, PINOS["GND"], "#111827", 0, 610)
fio(PX, PY + 130, EX, PINOS["GPIO10"], "#2563eb", 1, 635)
fio(PX - 70, PY + 130, EX, PINOS["3V3"], "#d97706", 2, 660)

# ---- notas
t(40, H - 90, "• Perna 1 → 3V3   • Perna 2 (meio) → GPIO10   • Perna 3 → GND", 15, "#111827", "600")
t(40, H - 64, "• Se o volume aumentar girando para o lado \"errado\", troque as pernas 1 e 3 de lugar.", 14, "#111827")
t(40, H - 38, "⚠ Use o 3V3, NUNCA o 5Vin: o GPIO10 aguenta no máximo 3,3 V. O 3V3 e o GND podem ser os mesmos do microfone.",
  14, "#b91c1c", "600")

svg.append("</svg>")
saida = Path(__file__).with_name("potenciometro.svg")
saida.write_text("\n".join(svg), encoding="utf-8")
print(f"gerado: {saida}")
