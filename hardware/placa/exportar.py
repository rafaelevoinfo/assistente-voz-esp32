"""Exporta a placa roteada: gerbers + furação (zip para a JLCPCB), STEP (para a caixa) e imagens.

Roda com o Python do KiCad, depois do rotear.py:
  "%LOCALAPPDATA%\\Programs\\KiCad\\10.0\\bin\\python.exe" hardware/placa/exportar.py
"""
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PCB = AQUI / "assistente_final.kicad_pcb"
FAB = AQUI / "fabricacao"
RENDERS = AQUI / "renders"
CLI = str(Path(sys.executable).with_name("kicad-cli.exe"))
CAMADAS = "F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts"


def cli(*args: str) -> None:
    subprocess.run([CLI, "pcb", *args], check=True, stdout=subprocess.DEVNULL)


def main() -> None:
    FAB.mkdir(exist_ok=True)
    RENDERS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        cli("export", "gerbers", "--layers", CAMADAS, "--no-protel-ext", "-o", tmp + "/", str(PCB))
        cli("export", "drill", "--format", "excellon", "--excellon-separate-th", "-o", tmp + "/", str(PCB))
        with zipfile.ZipFile(FAB / "assistente-gerbers.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for arquivo in sorted(Path(tmp).iterdir()):
                z.write(arquivo, arquivo.name)
    cli("export", "step", "--subst-models", "--force", "-o", str(FAB / "assistente.step"), str(PCB))
    for lado, nome in (("top", "topo"), ("bottom", "baixo")):
        cli("render", "--side", lado, "--quality", "high", "--background", "opaque",
            "--width", "1600", "--height", "1500", "-o", str(RENDERS / f"{nome}.png"), str(PCB))
    print(f"gerado: {FAB} e {RENDERS}")


if __name__ == "__main__":
    main()
