"""Task 4: placa roteada (Freerouting) + planos de GND, com DRC limpo (Python do KiCad)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pcbnew = pytest.importorskip("pcbnew", reason="rode com o Python do KiCad")

HW = Path(__file__).resolve().parents[1]
FINAL = HW / "placa" / "assistente_final.kicad_pcb"
KICAD_CLI = Path(sys.executable).with_name("kicad-cli.exe")


@pytest.fixture(scope="module")
def placa():
    subprocess.run([sys.executable, str(HW / "placa" / "rotear.py")], check=True)
    return pcbnew.LoadBoard(str(FINAL))


def test_drc_limpo(placa, tmp_path):
    relatorio = tmp_path / "drc.json"
    subprocess.run([str(KICAD_CLI), "pcb", "drc", "--format", "json", "--severity-error",
                    "--refill-zones", "-o", str(relatorio), str(FINAL)], check=True)
    drc = json.loads(relatorio.read_text(encoding="utf-8"))
    erros = [f'{v["type"]}: {v["description"]}' for v in drc.get("violations", [])]
    assert erros == [], "\n".join(erros)
    assert drc.get("unconnected_items", []) == [], f'{len(drc["unconnected_items"])} ligações faltando'


def test_trilhas_de_potencia_largas(placa):
    finas = [(t.GetNetname(), pcbnew.ToMM(t.GetWidth())) for t in placa.GetTracks()
             if t.GetNetname().lstrip("/") in ("+5V", "GND") and not isinstance(t, pcbnew.PCB_VIA)
             and pcbnew.ToMM(t.GetWidth()) < 1.0]
    assert finas == []


def test_sem_cobre_na_antena(placa):
    antena = [z for z in placa.Zones() if z.GetIsRuleArea() and z.GetZoneName() == "ANTENA"][0]
    caixa = antena.GetBoundingBox()
    invasores = [f"{t.GetClass()} {t.GetNetname()}" for t in placa.GetTracks()
                 if t.GetBoundingBox().Intersects(caixa)]
    for z in placa.Zones():
        if z.GetIsRuleArea():
            continue
        for camada in (pcbnew.F_Cu, pcbnew.B_Cu):
            if z.IsOnLayer(camada) and z.HasFilledPolysForLayer(camada):
                preenchido = z.GetFilledPolysList(camada)
                if preenchido.BBox().Intersects(caixa) and any(
                        preenchido.Contains(pcbnew.VECTOR2I(x, y))
                        for x in range(caixa.GetLeft(), caixa.GetRight(), pcbnew.FromMM(0.5))
                        for y in range(caixa.GetTop(), caixa.GetBottom(), pcbnew.FromMM(0.5))):
                    invasores.append(f"zona {z.GetNetname()} na camada {camada}")
    assert invasores == []


def test_planos_de_gnd_nas_duas_camadas(placa):
    camadas = {c for z in placa.Zones() if not z.GetIsRuleArea() and z.GetNetname().lstrip("/") == "GND"
               for c in (pcbnew.F_Cu, pcbnew.B_Cu) if z.IsOnLayer(c)}
    assert camadas == {pcbnew.F_Cu, pcbnew.B_Cu}
