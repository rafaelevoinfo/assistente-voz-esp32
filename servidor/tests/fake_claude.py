"""Claude Code falso para os testes: o comportamento depende do pedido (argv após -p)."""

import json
import sys
import time

args = sys.argv[1:]
pedido = args[args.index("-p") + 1] if "-p" in args else ""

if pedido == "dormir":
    time.sleep(10)
elif pedido == "lixo":
    print("isto não é json")
elif pedido == "falhar":
    print(json.dumps({"result": "deu ruim", "is_error": False}))
    sys.exit(3)
elif pedido == "erro-json":
    print(json.dumps({"result": "Não consegui acessar o repositório.", "is_error": True}))
elif pedido == "eco-args":
    print(json.dumps({"result": " ".join(args), "is_error": False}))
else:
    print(json.dumps({"type": "result", "result": "Feito.", "is_error": False}))
