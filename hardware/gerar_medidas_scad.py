"""Converte hardware/medidas.json em variáveis OpenSCAD (esp.usb_c.x -> esp_usb_c_x = 0;).

Uso: python hardware/gerar_medidas_scad.py [saida.scad]   (padrão: hardware/caixa/medidas.scad)
"""
import json
import sys
from pathlib import Path

HW = Path(__file__).resolve().parent


def achatar(d: dict, prefixo: str = ""):
    for chave, v in d.items():
        if chave.startswith("_"):
            continue
        nome = f"{prefixo}_{chave}" if prefixo else chave
        if isinstance(v, dict):
            yield from achatar(v, nome)
        else:
            yield nome, v


def main() -> None:
    saida = Path(sys.argv[1]) if len(sys.argv) > 1 else HW / "caixa" / "medidas.scad"
    medidas = json.loads((HW / "medidas.json").read_text(encoding="utf-8"))
    linhas = ["// Gerado por hardware/gerar_medidas_scad.py a partir de medidas.json. Não edite."]
    linhas += [f"{nome} = {v};" for nome, v in achatar(medidas)]
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text("\n".join(linhas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
