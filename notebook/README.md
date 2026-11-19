# Player do notebook

Toca nos alto-falantes do notebook o áudio de resposta que a placa recebe do servidor. É uma solução **temporária**, até a placa ter um amplificador MAX98357A e um alto-falante próprios.

A placa repassa o áudio pela **USB serial**. O player:
- mostra os logs da placa (`[placa] ...`);
- toca o áudio (PCM 24 kHz, mono, 16 bits) com **300 ms de pré-buffer**, para o som não sair picotado;
- avisa a placa (`DONE`) quando termina de tocar, para ela abrir a janela de continuação;
- toca o **bipe de "estou ouvindo"** quando a placa manda `BEEP` (som gerado localmente, por cima do áudio);
- reabre a serial sozinho se a placa reiniciar.

O protocolo serial está em [`../docs/contrato.md` §2](../docs/contrato.md).

## Instalar

Requer Python 3.12+.

```bash
cd notebook
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Linux/macOS: .venv/bin/pip
```

## Rodar

```bash
.venv/Scripts/python player.py --porta COM4
```

- `--porta`: porta USB da placa. O padrão é `COM4`; veja a porta certa no Gerenciador de Dispositivos ou na Arduino IDE.
- **Feche o player antes de gravar o firmware** ou de abrir o Monitor Serial, porque eles disputam a mesma porta.
- `Ctrl+C` encerra.

## Testes

```bash
.venv/Scripts/python -m pytest -q
```

Testam o leitor do protocolo serial e o buffer de reprodução, sem precisar da placa nem de placa de som.
