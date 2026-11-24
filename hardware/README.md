# Hardware: placa de circuito e caixa

Design: [`docs/superpowers/specs/2026-11-23-placa-e-caixa-design.md`](../docs/superpowers/specs/2026-11-23-placa-e-caixa-design.md).
Tudo aqui é gerado por scripts a partir de **`medidas.json`** (fonte única de medidas, em mm).

## Ferramentas

- **KiCad 10**: desenho da placa (`pcbnew` em Python e `kicad-cli`). Instalado por usuário em
  `%LOCALAPPDATA%\Programs\KiCad\10.0`.
- **Java 25+** (Temurin) e **Freerouting 2.5** (`hardware/ferramentas/freerouting.jar`, fora do git):
  roteamento automático das trilhas.
- **OpenSCAD**: caixa (instalado só na etapa da caixa).

Os scripts da placa e os testes rodam com o Python que vem com o KiCad (com `pip install pytest`):

```
set KPY=%LOCALAPPDATA%\Programs\KiCad\10.0\bin\python.exe
```

## Gerar

```
%KPY% hardware/gerar_medidas_scad.py     # medidas.json -> caixa/medidas.scad
%KPY% hardware/placa/netlist.py          # ligações -> placa/assistente.net
%KPY% hardware/placa/montar_pcb.py       # contorno + componentes -> placa/assistente.kicad_pcb + posicoes.json
%KPY% hardware/placa/rotear.py           # Freerouting + planos de GND -> placa/assistente_final.kicad_pcb
```

## Medidas

Edite `medidas.json` e regenere o que depende dele. Os valores listados em `_a_confirmar`
ainda precisam ser medidos com régua antes de encomendar a placa.

## Testes

```
%KPY% -m pytest hardware/tests -v
```
