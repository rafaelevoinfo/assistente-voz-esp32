# Hardware: placa de circuito e caixa

Design: [`docs/superpowers/specs/2026-11-23-placa-e-caixa-design.md`](../docs/superpowers/specs/2026-11-23-placa-e-caixa-design.md).
Tudo aqui é gerado por scripts a partir de **`medidas.json`** (fonte única de medidas, em mm).

## Ferramentas

- **KiCad 9**: desenho da placa (`pcbnew` em Python e `kicad-cli`).
- **Java 17+** e **Freerouting** (`hardware/ferramentas/freerouting.jar`, fora do git): roteamento automático das trilhas.
- **OpenSCAD**: caixa (instalado só na etapa da caixa).

Os scripts da placa rodam com o Python que vem com o KiCad:
`"C:\Program Files\KiCad\9.0\bin\python.exe"`.

## Medidas

Edite `medidas.json` e regenere o que depende dele. Os valores listados em `_a_confirmar`
ainda precisam ser medidos com régua antes de encomendar a placa.

```
python hardware/gerar_medidas_scad.py      # medidas.json -> caixa/medidas.scad
```

## Testes

```
pytest hardware/tests -v
```
