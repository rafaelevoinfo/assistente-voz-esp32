"""Desenha o mapa de montagem da placa perfurada: cima.svg, baixo.svg (espelhada) e fios.md.

Uso: python hardware/perfurada/desenhar.py   (depois converta os .svg em .png com o Edge headless,
     como os outros diagramas de docs/)
"""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import layout  # noqa: E402
from layout import netlist  # noqa: E402

M = json.loads((AQUI.parent / "medidas.json").read_text(encoding="utf-8"))
ESCALA = 11          # px por mm
BORDA = 60           # px de margem em volta da placa (para os números das colunas/linhas)
COR = {"+3V3": "#d97706", "+5V": "#dc2626", "GND": "#111827", "I2S_WS": "#2563eb", "I2S_SCK": "#7c3aed",
       "I2S_SD": "#059669", "AMP_LRC": "#0891b2", "AMP_BCLK": "#db2777", "AMP_DIN": "#65a30d",
       "VOL": "#ea580c", "GAIN": "#64748b", "GAIN_15DB": "#a855f7"}
NOME_NET = {"+3V3": "3V3", "+5V": "5V", "GND": "GND", "I2S_WS": "WS (GPIO4)", "I2S_SCK": "SCK (GPIO5)",
            "I2S_SD": "SD (GPIO8)", "AMP_LRC": "LRC (GPIO6)", "AMP_BCLK": "BCLK (GPIO7)",
            "AMP_DIN": "DIN (GPIO9)", "VOL": "volume (GPIO10)", "GAIN": "ganho", "GAIN_15DB": "ganho 15 dB"}
POS = layout.posicoes_para_caixa()
LARG, PROF = POS["placa"]["largura"], POS["placa"]["profundidade"]


def nome_pino(ref, numero):
    return netlist.COMPONENTES[ref][2][numero - 1]


class Desenho:
    def __init__(self, espelhar: bool, titulo: str, subtitulo: str):
        self.espelhar = espelhar
        self.w = int(LARG * ESCALA + 2 * BORDA + 260)
        self.h = int(PROF * ESCALA + 2 * BORDA + 90)
        self.s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                  f'viewBox="0 0 {self.w} {self.h}" font-family="Segoe UI, Arial, sans-serif">',
                  f'<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>',
                  f'<text x="20" y="30" font-size="22" font-weight="700" fill="#111827">{titulo}</text>',
                  f'<text x="20" y="54" font-size="14" fill="#4b5563">{subtitulo}</text>']
        self.oy = 80

    def xy(self, x_mm, y_mm):
        if self.espelhar:
            x_mm = LARG - x_mm
        return BORDA + x_mm * ESCALA, self.oy + BORDA + y_mm * ESCALA

    def furo_xy(self, cl):
        return self.xy(*layout.mm(cl))

    def add(self, el):
        self.s.append(el)

    def placa(self):
        x0, y0 = self.xy(0, 0)
        x1, y1 = self.xy(LARG, PROF)
        x0, x1 = min(x0, x1), max(x0, x1)
        self.add(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="6" fill="#2f6b3a"/>')
        colunas, linhas = layout.GRADE
        for c in range(colunas):
            for l in range(linhas):
                x, y = self.furo_xy((c, l))
                self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#c8a25a"/>'
                         f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="#1f2937"/>')
        for c in range(0, colunas, 2):
            x, _ = self.furo_xy((c, 0))
            self.add(f'<text x="{x:.1f}" y="{y0 - 10}" font-size="11" text-anchor="middle" fill="#6b7280">{c}</text>')
        for l in range(0, linhas, 2):
            _, y = self.furo_xy((0, l))
            xl = x0 - 12
            self.add(f'<text x="{xl}" y="{y + 4:.1f}" font-size="11" text-anchor="end" fill="#6b7280">{l}</text>')
        lado = "direita" if self.espelhar else "esquerda"
        self.add(f'<text x="{(x0 + x1) / 2}" y="{y0 - 28}" font-size="13" text-anchor="middle" fill="#111827" '
                 f'font-weight="600">TRÁS (USB-C) · colunas</text>')
        self.add(f'<text x="{(x0 + x1) / 2}" y="{y1 + 24}" font-size="13" text-anchor="middle" fill="#111827" '
                 f'font-weight="600">FRENTE (alto-falante)</text>')
        if self.espelhar:
            self.add(f'<text x="{x0 - 40}" y="{(y0 + y1) / 2 - 40}" font-size="12" text-anchor="end" '
                     f'fill="#111827">← eixo do volume</text>')
        else:
            self.add(f'<text x="{x1 + 12}" y="{(y0 + y1) / 2}" font-size="12" fill="#111827">eixo do volume →</text>')
        _ = lado

    def fim(self, caminho: Path):
        self.add("</svg>")
        caminho.write_text("\n".join(self.s), encoding="utf-8")


def contornos(d: Desenho):
    """Onde cada peça encaixa (vista de cima)."""
    e = POS["esp"]
    x0, y0 = d.xy(e["x"], e["y"])
    x1, y1 = d.xy(e["x"] + e["largura"], e["y"] + e["comprimento"])
    d.add(f'<rect x="{min(x0, x1)}" y="{y0}" width="{abs(x1 - x0)}" height="{y1 - y0}" fill="#111827" '
          f'fill-opacity="0.35" stroke="#f9fafb" stroke-width="2" stroke-dasharray="6 4"/>')
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    d.add(f'<text x="{cx}" y="{cy}" font-size="16" text-anchor="middle" fill="#f9fafb" font-weight="700" '
          f'transform="rotate(-90 {cx} {cy})">ESP32 (USB-C para trás)</text>')
    # mic
    mx, my = d.xy(POS["mic"]["furo_x"], POS["mic"]["furo_y"])
    d.add(f'<circle cx="{mx}" cy="{my}" r="{M["mic"]["diametro"] / 2 * ESCALA}" fill="#111827" fill-opacity="0.35" '
          f'stroke="#f9fafb" stroke-width="2" stroke-dasharray="6 4"/>')
    # amplificador: dos pinos para a frente
    a0 = layout.mm(layout.furo("U3", 1))
    a1 = layout.mm(layout.furo("U3", 7))
    xa0, ya0 = d.xy(a0[0] - 2, a0[1] - 1.5)
    xa1, ya1 = d.xy(a1[0] + 2, a0[1] - 1.5 + M["amp"]["comprimento"])
    d.add(f'<rect x="{min(xa0, xa1)}" y="{ya0}" width="{abs(xa1 - xa0)}" height="{ya1 - ya0}" fill="#7c3aed" '
          f'fill-opacity="0.35" stroke="#f9fafb" stroke-width="2" stroke-dasharray="6 4"/>')
    xt, yt = d.xy((a0[0] + a1[0]) / 2, a0[1] + 9)
    d.add(f'<text x="{xt}" y="{yt}" font-size="14" text-anchor="middle" fill="#f9fafb" font-weight="700">AMP</text>')
    d.add(f'<text x="{xt}" y="{yt + 18}" font-size="11" text-anchor="middle" fill="#f9fafb">borne do alto-falante na frente</text>')
    # capacitores
    for c in ("C1", "C2"):
        p1, p2 = layout.mm(layout.furo(c, 1)), layout.mm(layout.furo(c, 2))
        xc, yc = d.xy((p1[0] + p2[0]) / 2, p1[1])
        d.add(f'<circle cx="{xc}" cy="{yc}" r="{5 * ESCALA}" fill="#1e3a8a" fill-opacity="0.35" stroke="#f9fafb" '
              f'stroke-width="2" stroke-dasharray="6 4"/>')
        xp, yp = d.furo_xy(layout.furo(c, 1))
        d.add(f'<text x="{xp}" y="{yp - 9}" font-size="15" text-anchor="middle" fill="#fde047" font-weight="700">+</text>')
        d.add(f'<text x="{xc}" y="{yc + 30}" font-size="12" text-anchor="middle" fill="#f9fafb" font-weight="700">{c}</text>')
    # potenciômetro
    p = [layout.mm(layout.furo("RV1", i)) for i in (1, 3)]
    xr0, yr0 = d.xy(p[0][0] - 1.5, p[0][1] - 3)
    xr1, yr1 = d.xy(LARG, p[1][1] + 3)
    d.add(f'<rect x="{min(xr0, xr1)}" y="{yr0}" width="{abs(xr1 - xr0)}" height="{yr1 - yr0}" fill="#78716c" '
          f'fill-opacity="0.45" stroke="#f9fafb" stroke-width="2" stroke-dasharray="6 4"/>')
    for ref, n in (("JP1", 1), ("R1", 1)):
        x, y = d.furo_xy(layout.furo(ref, n))
        d.add(f'<text x="{x - 14 if not d.espelhar else x + 14}" y="{y + 4}" font-size="12" '
              f'text-anchor="{"end" if not d.espelhar else "start"}" fill="#f9fafb" font-weight="700">{ref}</text>')


def pinos(d: Desenho, com_nomes: bool):
    for (ref, n), cl in layout.POSICOES.items():
        x, y = d.furo_xy(cl)
        usado = any((ref, n) == (r, netlist.numero_do_pino(r, p)) for nos in netlist.NETS.values() for r, p in nos)
        cor = "#fbbf24" if usado else "#e5e7eb"
        d.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{cor}" stroke="#111827" stroke-width="1.5"/>')
        if com_nomes and ref in ("U2", "U3", "RV1", "JP1"):
            nome = nome_pino(ref, n) if ref in ("U2", "U3") else str(n)
            d.add(f'<text x="{x:.1f}" y="{y - 9:.1f}" font-size="9.5" text-anchor="middle" fill="#f9fafb" '
                  f'font-weight="700">{nome}</text>')


def legenda(d: Desenho, nets):
    x = BORDA + LARG * ESCALA + 70
    y = d.oy + BORDA + 10
    d.add(f'<text x="{x}" y="{y}" font-size="14" font-weight="700" fill="#111827">Fios</text>')
    for i, net in enumerate(nets):
        yy = y + 24 + i * 22
        d.add(f'<line x1="{x}" y1="{yy - 4}" x2="{x + 26}" y2="{yy - 4}" stroke="{COR[net]}" stroke-width="5"/>'
              f'<text x="{x + 34}" y="{yy}" font-size="12" fill="#111827">{NOME_NET[net]}</text>')


def main() -> None:
    # ---------------------------------------------------------- vista de cima
    cima = Desenho(False, "Placa perfurada — vista de CIMA (lado das peças)",
                   "Onde soldar cada barra de pinos fêmea e cada peça. Pinos amarelos têm fio; cinza só seguram a placa.")
    cima.placa()
    contornos(cima)
    pinos(cima, com_nomes=True)
    cima.fim(AQUI / "cima.svg")

    # --------------------------------------------------- vista de baixo (fios)
    baixo = Desenho(True, "Placa perfurada — vista de BAIXO (lado da solda, ESPELHADA)",
                    "Placa virada: os fios passam por aqui. Use fio ENCAPADO (os fios cruzam outras ilhas). Números = lista em fios.md.")
    baixo.placa()
    pinos(baixo, com_nomes=False)
    for i, (net, a, b) in enumerate(layout.FIOS, start=1):
        xa, ya = baixo.furo_xy(a)
        xb, yb = baixo.furo_xy(b)
        grosso = (a, b) in layout.FIOS_GROSSOS
        baixo.add(f'<line x1="{xa:.1f}" y1="{ya:.1f}" x2="{xb:.1f}" y2="{yb:.1f}" stroke="{COR[net]}" '
                  f'stroke-width="{6 if grosso else 3.5}" stroke-linecap="round" stroke-opacity="0.9"/>')
        mx, my = (xa + xb) / 2, (ya + yb) / 2
        baixo.add(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="9" fill="#ffffff" stroke="{COR[net]}" stroke-width="2"/>'
                  f'<text x="{mx:.1f}" y="{my + 4:.1f}" font-size="10" text-anchor="middle" font-weight="700" '
                  f'fill="#111827">{i}</text>')
    legenda(baixo, list(COR))
    baixo.fim(AQUI / "baixo.svg")

    # ------------------------------------------------------------ lista de fios
    pino_do_furo = {cl: (ref, n) for (ref, n), cl in layout.POSICOES.items()}
    linhas = ["# Placa perfurada: lista de fios", "",
              "Furos como **(coluna, linha)**, contados na vista de CIMA a partir do canto de trás-esquerda "
              "(coluna 0 à esquerda, linha 0 do lado dos USB-C). Na vista de baixo a placa fica espelhada: "
              "a coluna 0 passa para a direita. Fios **grossos** (22 AWG) são a alimentação; os demais, 26-30 AWG.",
              "", "**Use sempre fio encapado (cabinho):** os fios passam por cima de outras ilhas e, nus, dariam curto. "
              "Desencape só ~2 mm nas pontas, passe pelo furo ao lado do pino e solde junto com ele.",
              "", "| Nº | Ligação | De | Para | Fio |", "|---|---|---|---|---|"]
    for i, (net, a, b) in enumerate(layout.FIOS, start=1):
        ra, na = pino_do_furo[a]
        rb, nb = pino_do_furo[b]
        de = f"{ra} {nome_pino(ra, na)} ({a[0]}, {a[1]})"
        para = f"{rb} {nome_pino(rb, nb)} ({b[0]}, {b[1]})"
        linhas.append(f"| {i} | {NOME_NET[net]} | {de} | {para} | {'grosso' if (a, b) in layout.FIOS_GROSSOS else 'fino'} |")
    linhas += ["", "U1 = ESP32 · U2 = microfone · U3 = amplificador · RV1 = potenciômetro · "
               "C1/C2 = capacitores (\"+\" à esquerda) · JP1 = jumper de ganho (1-2 = 12 dB) · R1 = 100 kΩ", ""]
    (AQUI / "fios.md").write_text("\n".join(linhas), encoding="utf-8")
    print(f"gerado: cima.svg, baixo.svg, fios.md ({len(layout.FIOS)} fios)")


if __name__ == "__main__":
    main()
