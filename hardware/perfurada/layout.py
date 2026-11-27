"""Mapa da placa perfurada (dupla face 7 x 9 cm, cortada para ~70 x 68 mm, furos a cada 2,54 mm).

Furos como (coluna, linha), vistos de CIMA: coluna 0 à esquerda, linha 0 atrás (lado dos USB-C).
As ligações vêm do mesmo netlist.py da placa do KiCad; cada net vira uma corrente de fios por baixo.
"""
import json
import math
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "placa"))
import netlist  # noqa: E402

PASSO = 2.54
MARGEM = 2.0                  # mm da borda da placa cortada até o centro do primeiro furo
GRADE = (27, 26)              # colunas x linhas usadas (~70 x 68 mm)

# Posição do pino 1 e como os pinos seguem, por componente.
_U1_DIR, _U1_ESQ = 11, 1      # fileiras do ESP32 a 10 furos (25,4 mm)


def _posicoes():
    p = {}
    # U1: pinos 1..22 na fileira da direita (usada), 23..44 na da esquerda; pino 22 (GND) atrás.
    for i in range(1, 23):
        p[("U1", i)] = (_U1_DIR, 1 + (22 - i))
        p[("U1", 22 + i)] = (_U1_ESQ, 1 + (22 - i))
    # U2: INMP441 visto de cima: GND VDD SD (linha 4) e L/R WS SCK (linha 7), a 3 furos (7,62 mm).
    for numero, (c, l) in {1: (19, 4), 2: (18, 4), 3: (17, 4), 4: (19, 7), 5: (18, 7), 6: (17, 7)}.items():
        p[("U2", numero)] = (c, l)
    # U3: MAX98357A, pinos LRC..VIN na linha 17, corpo para a frente.
    for i in range(1, 8):
        p[("U3", i)] = (12 + i, 17)
    # RV1: WH148 na borda direita (pinos a 2 furos, eixo para a direita).
    for i in range(1, 4):
        p[("RV1", i)] = (24, 7 + 2 * i)
    # C1/C2: "+" à esquerda, pinos a 2 furos (5 mm), atrás do amplificador.
    p[("C1", 1)], p[("C1", 2)] = (14, 13), (16, 13)
    p[("C2", 1)], p[("C2", 2)] = (19, 13), (21, 13)
    # JP1 (ganho) à direita do amplificador; R1 (100 k) abaixo, a 3 furos (7,62 mm).
    for i in range(1, 4):
        p[("JP1", i)] = (22, 16 + i)
    p[("R1", 1)], p[("R1", 2)] = (22, 21), (25, 21)
    return p


POSICOES = _posicoes()


def furo(ref: str, numero: int):
    return POSICOES[(ref, numero)]


def mm(col_lin):
    """Centro do furo em mm, a partir do canto de trás-esquerda da placa cortada."""
    c, l = col_lin
    return MARGEM + c * PASSO, MARGEM + l * PASSO


def _corrente(furos):
    """Liga os furos de uma net em corrente, sempre indo ao mais próximo ainda não ligado."""
    restantes = list(furos[1:])
    atual, fios = furos[0], []
    while restantes:
        proximo = min(restantes, key=lambda f: math.dist(f, atual))
        fios.append((atual, proximo))
        restantes.remove(proximo)
        atual = proximo
    return fios


def _fios():
    fios = []
    for net, nos in netlist.NETS.items():
        furos = [furo(ref, netlist.numero_do_pino(ref, p)) for ref, p in nos]
        fios += [(net, a, b) for a, b in _corrente(furos)]
    return fios


FIOS = _fios()
# Alimentação do amplificador (+5V e GND) com fio mais grosso (22 AWG); o resto, 26-30 AWG.
FIOS_GROSSOS = {(a, b) for net, a, b in FIOS if net in ("+5V", "GND")}


def posicoes_para_caixa() -> dict:
    medidas = json.loads((AQUI.parent / "medidas.json").read_text(encoding="utf-8"))
    esp = medidas["esp"]
    x_esp = mm((_U1_ESQ, 0))[0] - (esp["largura"] - esp["pitch_fileiras"]) / 2
    y_esp = mm(furo("U1", 22))[1] - (esp["comprimento"] - 21 * PASSO) / 2
    largura = MARGEM * 2 + (GRADE[0] - 1) * PASSO
    profundidade = MARGEM * 2 + (GRADE[1] - 1) * PASSO
    mic = [mm(furo("U2", n)) for n in (2, 5)]
    pot = mm(furo("RV1", 2))
    return {
        "placa": {"largura": round(largura, 2), "profundidade": round(profundidade, 2), "espessura": 1.6},
        "usb_c": {"x": round(x_esp + esp["usb_c"]["y"], 2), "y_borda": round(y_esp, 2),
                  "largura": esp["usb_c"]["largura"], "altura": esp["usb_c"]["altura"],
                  "altura_sobre_placa": 8.5 + 1.6 + esp["usb_c"]["altura"] / 2},
        "led": {"x": round(x_esp + esp["led"]["y"], 2), "y": round(y_esp + esp["led"]["x"], 2),
                "altura_sobre_placa": 8.5 + 1.6},
        "mic": {"furo_x": round((mic[0][0] + mic[1][0]) / 2, 2), "furo_y": round((mic[0][1] + mic[1][1]) / 2, 2),
                "altura_sobre_placa": 8.5 + 1.6},
        "pot": {"eixo_y": round(pot[1], 2), "eixo_dir": [1, 0], "corpo_borda_x": round(largura, 2),
                "eixo_altura_sobre_placa": medidas["pot"]["corpo_diametro"] / 2},
        "esp": {"x": round(x_esp, 2), "y": round(y_esp, 2), "comprimento": esp["comprimento"],
                "largura": esp["largura"]},
    }


if __name__ == "__main__":
    saida = AQUI / "posicoes.json"
    saida.write_text(json.dumps(posicoes_para_caixa(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"gerado: {saida} ({len(FIOS)} fios)")
