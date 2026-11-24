"""Leitor mínimo de S-expressions (formato dos arquivos do KiCad), só para os testes."""
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')


def ler(texto: str):
    pilha = [[]]
    pos = 0
    while True:
        m = _TOKEN.match(texto, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        abre, fecha, aspas, atomo = m.groups()
        if abre:
            pilha.append([])
        elif fecha:
            lista = pilha.pop()
            pilha[-1].append(lista)
        elif aspas is not None:
            pilha[-1].append(aspas)
        else:
            pilha[-1].append(atomo)
    return pilha[0][0]


def filhos(no, nome):
    return [x for x in no if isinstance(x, list) and x and x[0] == nome]


def valor(no, nome, padrao=None):
    achados = filhos(no, nome)
    return achados[0][1] if achados and len(achados[0]) > 1 else padrao
