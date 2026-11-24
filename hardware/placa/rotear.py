"""Roteia a placa: monta (montar_pcb.py), roteia com o Freerouting, cria os planos de GND e salva.

Roda com o Python do KiCad (precisa de Java e de hardware/ferramentas/freerouting.jar):
  "%LOCALAPPDATA%\\Programs\\KiCad\\10.0\\bin\\python.exe" hardware/placa/rotear.py
Gera hardware/placa/assistente_final.kicad_pcb.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import montar_pcb  # noqa: E402

FREEROUTING = AQUI.parent / "ferramentas" / "freerouting.jar"
SAIDA = AQUI / "assistente_final.kicad_pcb"
FOLGA_BORDA_GND = 0.5   # mm entre o plano de GND e a borda da placa


def java() -> str:
    """O Freerouting 2.5 exige Java 25+: prefere o Temurin mais novo instalado."""
    candidatos = sorted(glob.glob(r"C:\Program Files\Eclipse Adoptium\*\bin\java.exe"),
                        key=lambda c: [int(n) for n in c.split("jre-")[-1].split("-")[0].split(".") if n.isdigit()],
                        reverse=True)
    if candidatos:
        return candidatos[0]
    achado = shutil.which("java")
    if not achado:
        sys.exit("Java não encontrado (instale o Temurin 25+)")
    return achado


def regras(placa: pcbnew.BOARD) -> None:
    ds = placa.GetDesignSettings()
    ns = ds.m_NetSettings
    padrao = ns.GetDefaultNetclass()
    padrao.SetTrackWidth(pcbnew.FromMM(0.3))
    padrao.SetClearance(pcbnew.FromMM(0.2))
    padrao.SetViaDiameter(pcbnew.FromMM(0.8))
    padrao.SetViaDrill(pcbnew.FromMM(0.4))
    potencia = pcbnew.NETCLASS("Potencia")
    potencia.SetTrackWidth(pcbnew.FromMM(1.0))
    potencia.SetClearance(pcbnew.FromMM(0.25))
    potencia.SetViaDiameter(pcbnew.FromMM(1.0))
    potencia.SetViaDrill(pcbnew.FromMM(0.5))
    ns.SetNetclass("Potencia", potencia)
    for net in ("/+5V", "/GND"):
        ns.SetNetclassPatternAssignment(net, "Potencia")
    ns.RecomputeEffectiveNetclasses()
    placa.SynchronizeNetsAndNetClasses(True)


def rotear(placa: pcbnew.BOARD) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dsn, ses = os.path.join(tmp, "placa.dsn"), os.path.join(tmp, "placa.ses")
        assert pcbnew.ExportSpecctraDSN(placa, dsn), "falha ao exportar o DSN"
        subprocess.run([java(), "-jar", str(FREEROUTING), "-de", dsn, "-do", ses, "--router.autorouter.max_passes=100",
                        "--gui.enabled=false"], check=True, timeout=900)
        assert os.path.exists(ses), "o Freerouting não gerou o .ses"
        assert pcbnew.ImportSpecctraSES(placa, ses), "falha ao importar o SES"


def remover_trilhas_gnd(placa: pcbnew.BOARD) -> None:
    """O GND vai pelos planos das duas camadas (bem mais largos que qualquer trilha). As trilhas de
    GND do Freerouting saem estreitadas entre os pinos e ocupam o lugar dos raios térmicos."""
    for t in list(placa.GetTracks()):
        if t.GetNetname() == "/GND":
            placa.Remove(t)


def planos_gnd(placa: pcbnew.BOARD) -> None:
    gnd = placa.FindNet("/GND")
    caixa = placa.GetBoardEdgesBoundingBox()
    for camada in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(placa)
        z.SetLayer(camada)
        z.SetNet(gnd)
        z.SetZoneName(f"GND_{'F' if camada == pcbnew.F_Cu else 'B'}")
        z.SetLocalClearance(pcbnew.FromMM(0.3))
        z.SetMinThickness(pcbnew.FromMM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        contorno = z.Outline()
        contorno.NewOutline()
        for x, y in ((caixa.GetLeft(), caixa.GetTop()), (caixa.GetRight(), caixa.GetTop()),
                     (caixa.GetRight(), caixa.GetBottom()), (caixa.GetLeft(), caixa.GetBottom())):
            contorno.Append(x, y)
        placa.Add(z)
    # Os pinos GND e L/R do mic ficam espremidos entre trilhas: sem espaço para 2 raios térmicos.
    for pad in placa.FindFootprintByReference("U2").Pads():
        if pad.GetNetname() == "/GND":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    ds = placa.GetDesignSettings()
    ds.m_CopperEdgeClearance = pcbnew.FromMM(FOLGA_BORDA_GND)
    pcbnew.ZONE_FILLER(placa).Fill(placa.Zones())


def main() -> None:
    placa = montar_pcb.montar()
    regras(placa)
    rotear(placa)
    remover_trilhas_gnd(placa)
    planos_gnd(placa)
    pcbnew.SaveBoard(str(SAIDA), placa)
    print(f"gerado: {SAIDA}")


if __name__ == "__main__":
    main()
