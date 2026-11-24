"""Task 5: arquivos para a fábrica (JLCPCB), imagens para revisão e STEP para a caixa."""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("pcbnew", reason="rode com o Python do KiCad")

HW = Path(__file__).resolve().parents[1]
FAB = HW / "placa" / "fabricacao"


@pytest.fixture(scope="module")
def exportado():
    subprocess.run([sys.executable, str(HW / "placa" / "exportar.py")], check=True)
    return FAB


def test_zip_tem_camadas(exportado):
    with zipfile.ZipFile(exportado / "assistente-gerbers.zip") as z:
        nomes = " ".join(z.namelist())
    for camada in ("F_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Silkscreen", "Edge_Cuts"):
        assert camada in nomes, camada
    assert re.search(r"\.drl\b", nomes), "falta o arquivo de furação"


def test_step_existe_e_tem_tamanho_da_placa(exportado):
    step = exportado / "assistente.step"
    assert step.exists() and step.stat().st_size > 10_000


def test_renders_para_revisao(exportado):
    for lado in ("topo", "baixo"):
        png = HW / "placa" / "renders" / f"{lado}.png"
        assert png.exists() and png.stat().st_size > 20_000, lado
