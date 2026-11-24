"""Monta a placa (contorno + componentes posicionados + nets) a partir do netlist.py e do medidas.json.

Roda com o Python do KiCad:
  "%LOCALAPPDATA%\\Programs\\KiCad\\10.0\\bin\\python.exe" hardware/placa/montar_pcb.py
Gera hardware/placa/assistente.kicad_pcb (sem trilhas; o rotear.py roteia) e posicoes.json (para a caixa).

Coordenadas (mm, como no KiCad): x da esquerda para a direita; y de TRÁS (y=0, onde saem os
USB-C) para a FRENTE (y=D, lado do alto-falante). A placa fica deitada logo abaixo do topo.
"""
import json
import os
import sys
from pathlib import Path

import pcbnew

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import netlist  # noqa: E402

M = json.loads((AQUI.parent / "medidas.json").read_text(encoding="utf-8"))
LIB = Path(os.environ.get("KICAD10_FOOTPRINT_DIR")
           or Path(sys.executable).resolve().parents[1] / "share" / "kicad" / "footprints")

# ---------------------------------------------------------------- layout (mm)
W, D = 72.0, 68.0                 # largura x profundidade da placa
ESP_X = 3.0                       # borda esquerda da YD-ESP32-S3 (deixa 3 mm para o trilho)
ALTURA_SOQUETE = 8.5              # barra fêmea: a placa do ESP fica 8,5 mm acima da nossa
P = 2.54

esp = M["esp"]
ROW_ESQ = ESP_X + esp["largura"] / 2 - esp["pitch_fileiras"] / 2   # fileira sem ligações
ROW_DIR = ESP_X + esp["largura"] / 2 + esp["pitch_fileiras"] / 2   # fileira usada (FILEIRA_ESP)
PRIMEIRO_PINO_Y = (esp["comprimento"] - 21 * P) / 2                # pino 22 (GND), lado dos USB-C
ANTENA_Y0 = esp["comprimento"] - esp["antena"]["comprimento"]
ENTALHE = (ESP_X + 3.5, ESP_X + esp["largura"] - 3.5, ANTENA_Y0 - 1.0)  # x0, x1, y0 do recorte sob a antena

POT_PINOS_X = W - 8.0             # fileira de pinos do WH148 (paralela à borda direita)
POT_Y = 35.0                      # centro do corpo / eixo
AMP_PINOS_Y = 46.0                # fileira de pinos do MAX98357A (corpo para a frente)
AMP_X0 = 34.0
MIC_CENTRO = (50.0, 16.0)         # centro do módulo redondo (furo para cima)


def v(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def borda(placa, pontos):
    for (x0, y0), (x1, y1) in zip(pontos, pontos[1:] + pontos[:1]):
        s = pcbnew.PCB_SHAPE(placa)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(v(x0, y0))
        s.SetEnd(v(x1, y1))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.1))
        placa.Add(s)


def pad_tht(fp, numero, x, y, diametro=1.7, furo=1.0, quadrado=False):
    p = pcbnew.PAD(fp)
    p.SetNumber(str(numero))
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetShape(pcbnew.PAD_SHAPE_RECT if quadrado else pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(v(diametro, diametro))
    p.SetDrillSize(v(furo, furo))
    p.SetLayerSet(pcbnew.PAD.PTHMask())
    p.SetPosition(v(x, y))
    fp.Add(p)


def footprint_proprio(placa, ref, valor, pads):
    """pads: [(numero, x, y)] em coordenadas absolutas da placa."""
    fp = pcbnew.FOOTPRINT(placa)
    fp.SetReference(ref)
    fp.SetValue(valor)
    fp.SetFPIDAsString(netlist.COMPONENTES[ref][1])
    x0, y0 = pads[0][1], pads[0][2]
    fp.SetPosition(v(x0, y0))
    fp.Reference().SetVisible(False)   # a serigrafia própria (serigrafia()) já identifica o módulo
    fp.Value().SetVisible(False)
    placa.Add(fp)
    for numero, x, y in pads:
        pad_tht(fp, numero, x, y, quadrado=(numero == 1))
    return fp


def footprint_da_lib(placa, ref, x, y, graus=0.0):
    lib, nome = netlist.COMPONENTES[ref][1].split(":")
    fp = pcbnew.FootprintLoad(str(LIB / f"{lib}.pretty"), nome)
    assert fp, f"footprint {lib}:{nome} não encontrado em {LIB}"
    fp.SetReference(ref)
    fp.SetValue(netlist.COMPONENTES[ref][0])
    placa.Add(fp)
    fp.SetPosition(v(x, y))
    fp.SetOrientationDegrees(graus)
    return fp


def area_antena(placa):
    z = pcbnew.ZONE(placa)
    z.SetIsRuleArea(True)
    z.SetZoneName("ANTENA")
    for setar in ("SetDoNotAllowTracks", "SetDoNotAllowVias", "SetDoNotAllowZoneFills",
                  "SetDoNotAllowPads", "SetDoNotAllowFootprints"):
        getattr(z, setar)(True)
    z.SetLayerSet(pcbnew.LSET.AllCuMask())
    x0, x1 = ESP_X + 4.0, ESP_X + esp["largura"] - 4.0
    y0, y1 = ANTENA_Y0, esp["comprimento"]
    contorno = z.Outline()
    contorno.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        contorno.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    placa.Add(z)


def texto(placa, x, y, conteudo, altura=1.0, graus=0.0):
    t = pcbnew.PCB_TEXT(placa)
    t.SetText(conteudo)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetPosition(v(x, y))
    t.SetTextSize(v(altura, altura))
    t.SetTextThickness(pcbnew.FromMM(0.15))
    t.SetTextAngleDegrees(graus)
    placa.Add(t)


def linha(placa, x0, y0, x1, y1):
    s = pcbnew.PCB_SHAPE(placa)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(v(x0, y0))
    s.SetEnd(v(x1, y1))
    s.SetLayer(pcbnew.F_SilkS)
    s.SetWidth(pcbnew.FromMM(0.15))
    placa.Add(s)


def retangulo(placa, x0, y0, x1, y1):
    s = pcbnew.PCB_SHAPE(placa)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(v(x0, y0))
    s.SetEnd(v(x1, y1))
    s.SetLayer(pcbnew.F_SilkS)
    s.SetWidth(pcbnew.FromMM(0.15))
    placa.Add(s)


def circulo(placa, cx, cy, raio):
    s = pcbnew.PCB_SHAPE(placa)
    s.SetShape(pcbnew.SHAPE_T_CIRCLE)
    s.SetCenter(v(cx, cy))
    s.SetEnd(v(cx + raio, cy))
    s.SetLayer(pcbnew.F_SilkS)
    s.SetWidth(pcbnew.FromMM(0.15))
    placa.Add(s)


def serigrafia(placa):
    """Onde cada módulo encaixa e como usar o jumper de ganho (impresso na placa)."""
    # contorno do ESP: 3 lados (o 4º cairia no entalhe da antena)
    for (xa, ya), (xb, yb) in (((ESP_X, esp["comprimento"]), (ESP_X, 0.5)),
                               ((ESP_X, 0.5), (ESP_X + esp["largura"], 0.5)),
                               ((ESP_X + esp["largura"], 0.5), (ESP_X + esp["largura"], esp["comprimento"]))):
        linha(placa, xa, ya, xb, yb)
    texto(placa, ESP_X + esp["largura"] / 2, 30, "ESP32 (YD-ESP32-S3)", 1.2, 90)
    texto(placa, ESP_X + esp["largura"] / 2, 2.2, "USB-C p/ tras", 1.0)
    texto(placa, ESP_X + esp["largura"] / 2, ANTENA_Y0 - 3, "antena ->", 0.9)
    raio_mic = M["mic"]["diametro"] / 2
    circulo(placa, MIC_CENTRO[0], MIC_CENTRO[1], raio_mic)
    meia_mic = M["mic"]["pitch_fileiras"] / 2
    texto(placa, MIC_CENTRO[0], MIC_CENTRO[1] - meia_mic - 2.0, "SD VDD GND", 0.7)
    texto(placa, MIC_CENTRO[0], MIC_CENTRO[1] + meia_mic + 2.0, "SCK WS L/R", 0.7)
    texto(placa, MIC_CENTRO[0] + 9.5, MIC_CENTRO[1] - 1, "MIC", 1.2)
    texto(placa, MIC_CENTRO[0] + 9.5, MIC_CENTRO[1] + 1, "furo p/", 0.8)
    texto(placa, MIC_CENTRO[0] + 9.5, MIC_CENTRO[1] + 2.4, "cima", 0.8)
    amp_x1 = AMP_X0 + 6 * P
    retangulo(placa, AMP_X0 - 2.2, AMP_PINOS_Y - 1.6, amp_x1 + 2.2, AMP_PINOS_Y + M["amp"]["comprimento"] - 1.6)
    texto(placa, (AMP_X0 + amp_x1) / 2, AMP_PINOS_Y + 7, "AMP MAX98357A", 1.0)
    texto(placa, (AMP_X0 + amp_x1) / 2, AMP_PINOS_Y + 14, "ALTO-FALANTE no borne", 0.8)
    corpo = M["pot"]["corpo_diametro"]
    retangulo(placa, POT_PINOS_X - 1.5, POT_Y - corpo / 2, W - 0.5, POT_Y + corpo / 2)
    texto(placa, POT_PINOS_X - 4, POT_Y, "VOLUME", 1.0, 90)
    texto(placa, 57.6, 49.0, "1", 0.8)
    texto(placa, 57.6, 54.1, "3", 0.8)
    texto(placa, 65.0, 47.5, "GANHO", 1.0)
    texto(placa, 65.0, 49.5, "1-2: 12dB", 0.75)
    texto(placa, 65.0, 50.9, "(recomendado)", 0.6)
    texto(placa, 65.0, 52.5, "2-3: 15dB", 0.75)
    texto(placa, 65.0, 54.0, "solto: 9dB", 0.75)


def ligar_nets(placa):
    nets = {}
    for nome in netlist.NETS:
        n = pcbnew.NETINFO_ITEM(placa, "/" + nome)
        placa.Add(n)
        nets[nome] = n
    por_pino = netlist.nets_por_pino()
    for fp in placa.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            nome = por_pino.get((ref, int(pad.GetNumber()))) if pad.GetNumber().isdigit() else None
            if nome:
                pad.SetNet(nets[nome])


def montar() -> pcbnew.BOARD:
    placa = pcbnew.BOARD()
    x0, x1, ye = ENTALHE
    borda(placa, [(0, 0), (W, 0), (W, D), (x1, D), (x1, ye), (x0, ye), (x0, D), (0, D)])

    # U1: YD-ESP32-S3 em 2 barras fêmea 1x22; pinos 1..22 na fileira da direita (usada),
    # 23..44 na da esquerda. Pino 22 (GND) do lado dos USB-C (y pequeno).
    pads_esp = [(i, ROW_DIR, PRIMEIRO_PINO_Y + (22 - i) * P) for i in range(1, 23)]
    pads_esp += [(22 + i, ROW_ESQ, PRIMEIRO_PINO_Y + (22 - i) * P) for i in range(1, 23)]
    footprint_proprio(placa, "U1", "YD-ESP32-S3", pads_esp)

    # U2: INMP441 redondo, mais para trás e à direita (longe do alto-falante). Duas fileiras de 3
    # frente a frente: 1-3 = SD, VDD, GND (lado de trás); 4-6 = SCK, WS, L/R (lado da frente).
    meia = M["mic"]["pitch_fileiras"] / 2
    footprint_proprio(placa, "U2", "INMP441",
                      [(i, MIC_CENTRO[0] + (i - 2) * P, MIC_CENTRO[1] - meia) for i in range(1, 4)]
                      + [(i, MIC_CENTRO[0] + (i - 5) * P, MIC_CENTRO[1] + meia) for i in range(4, 7)])

    # U3: MAX98357A (1x7) perto da frente; corpo e borne do alto-falante para a frente.
    footprint_proprio(placa, "U3", "MAX98357A",
                      [(i, AMP_X0 + (i - 1) * P, AMP_PINOS_Y) for i in range(1, 8)])

    # RV1: WH148 deitado na borda direita, eixo para +x; 3 pinos a cada pot.pitch_pinos ao longo de y.
    pp = M["pot"]["pitch_pinos"]
    footprint_proprio(placa, "RV1", "B10K WH148",
                      [(i, POT_PINOS_X, POT_Y + (i - 2) * pp) for i in range(1, 4)])

    # C1/C2: eletrolíticos atrás dos pinos do amplificador, mesma rotação ("+" à esquerda).
    footprint_da_lib(placa, "C1", 35.0, 38.0)
    footprint_da_lib(placa, "C2", 46.0, 38.0)
    # JP1 (ganho) e R1 (100 k do 15 dB) à direita do amplificador.
    footprint_da_lib(placa, "JP1", 55.0, 49.0)
    footprint_da_lib(placa, "R1", 53.0, 60.0)

    area_antena(placa)
    serigrafia(placa)
    ligar_nets(placa)
    return placa


def posicoes() -> dict:
    """O que a caixa precisa saber da placa (mm, coordenadas da placa)."""
    topo_esp = ALTURA_SOQUETE + 1.6
    return {
        "placa": {"largura": W, "profundidade": D, "espessura": 1.6,
                  "entalhe_antena": {"x0": ENTALHE[0], "x1": ENTALHE[1], "y0": ENTALHE[2]}},
        "usb_c": {"x": ESP_X + esp["usb_c"]["y"], "y_borda": 0.0, "largura": esp["usb_c"]["largura"],
                  "altura": esp["usb_c"]["altura"], "altura_sobre_placa": topo_esp + esp["usb_c"]["altura"] / 2},
        "led": {"x": ESP_X + esp["led"]["y"], "y": esp["led"]["x"], "altura_sobre_placa": topo_esp},
        "mic": {"furo_x": MIC_CENTRO[0] + M["mic"]["furo"]["x"], "furo_y": MIC_CENTRO[1] + M["mic"]["furo"]["y"],
                "altura_sobre_placa": ALTURA_SOQUETE + 1.6},
        "pot": {"eixo_y": POT_Y, "eixo_dir": [1, 0], "corpo_borda_x": W,
                "eixo_altura_sobre_placa": M["pot"]["corpo_diametro"] / 2},
        "esp": {"x": ESP_X, "comprimento": esp["comprimento"], "largura": esp["largura"]},
    }


if __name__ == "__main__":
    placa = montar()
    saida = AQUI / "assistente.kicad_pcb"
    pcbnew.SaveBoard(str(saida), placa)
    (AQUI / "posicoes.json").write_text(json.dumps(posicoes(), indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    print(f"gerado: {saida}")
