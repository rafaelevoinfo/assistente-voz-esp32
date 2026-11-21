import json

from voz.memoria import Historico, Memoria, Troca


def nomes(pasta):
    return sorted(p.name for p in pasta.glob("historico*.jsonl"))


def test_registra_e_le_ultimas(tmp_path):
    h = Historico(tmp_path)
    for i in range(7):
        h.registrar(f"p{i}", f"r{i}")
    ult = h.ultimas(5)
    assert [t.pergunta for t in ult] == ["p2", "p3", "p4", "p5", "p6"]  # mais antiga primeiro
    assert ult[-1] == Troca(ts=ult[-1].ts, origem="conversa", pergunta="p6", resposta="r6")


def test_grava_uma_troca_por_linha_em_jsonl(tmp_path):
    h = Historico(tmp_path)
    h.registrar("pedido X", "feito", origem="claude_code")
    linha = json.loads((tmp_path / "historico.jsonl").read_text(encoding="utf-8").strip())
    assert linha["origem"] == "claude_code"
    assert linha["pergunta"] == "pedido X" and linha["resposta"] == "feito"
    assert "ts" in linha


def test_rotaciona_ao_atingir_limite(tmp_path):
    h = Historico(tmp_path, max_bytes=300)
    for i in range(10):
        h.registrar(f"pergunta {i}", "x" * 50)
    assert (tmp_path / "historico.1.jsonl").exists()
    assert (tmp_path / "historico.jsonl").stat().st_size <= 300
    for p in tmp_path.glob("historico*.jsonl"):
        assert p.stat().st_size <= 300


def test_mantem_no_maximo_7_arquivos(tmp_path):
    h = Historico(tmp_path, max_bytes=120, max_arquivos=7)
    for i in range(60):
        h.registrar(f"p{i}", "r" * 40)
    assert nomes(tmp_path) == ["historico.1.jsonl", "historico.2.jsonl", "historico.3.jsonl",
                               "historico.4.jsonl", "historico.5.jsonl", "historico.6.jsonl", "historico.jsonl"]


def test_completa_com_o_arquivo_imediatamente_anterior(tmp_path):
    h = Historico(tmp_path, max_bytes=10_000)
    for i in range(4):
        h.registrar(f"antiga{i}", "r")
    h.rotacionar()
    h.registrar("nova0", "r")
    h.registrar("nova1", "r")
    assert [t.pergunta for t in h.ultimas(5)] == ["antiga1", "antiga2", "antiga3", "nova0", "nova1"]


def test_ignora_linhas_corrompidas(tmp_path):
    (tmp_path / "historico.jsonl").write_text(
        '{"ts":"2026-11-18T10:00:00","origem":"conversa","pergunta":"a","resposta":"b"}\n'
        "lixo que não é json\n"
        '{"ts":"2026-11-18T10:01:00","origem":"conversa","pergunta":"c","resposta":"d"}\n',
        encoding="utf-8",
    )
    assert [t.pergunta for t in Historico(tmp_path).ultimas(5)] == ["a", "c"]


def test_historico_vazio(tmp_path):
    assert Historico(tmp_path).ultimas(5) == []


def test_cria_a_pasta_se_nao_existir(tmp_path):
    h = Historico(tmp_path / "nova" / "pasta")
    h.registrar("p", "r")
    assert (tmp_path / "nova" / "pasta" / "historico.jsonl").exists()


# ----------------------------------------------------------------- Memoria

def test_memoria_inclui_trocas(tmp_path):
    m = Memoria(tmp_path)
    m.registrar_conversa("quanto é 2+2?", "Quatro.")
    m.registrar_tarefa("ajuste a página de pedidos", "Pronto, abri o PR 42.")
    texto = m.texto_para_sessao()
    assert "quanto é 2+2?" in texto and "Quatro." in texto
    assert "ajuste a página de pedidos" in texto and "PR 42" in texto
    assert "referência" in texto.lower()


def test_memoria_ignora_instrucoes_na_pasta(tmp_path):
    (tmp_path / "CONTEXTO.md").write_text("sobra antiga", encoding="utf-8")
    assert Memoria(tmp_path).texto_para_sessao() is None


def test_memoria_vazia_devolve_none(tmp_path):
    assert Memoria(tmp_path).texto_para_sessao() is None


def test_memoria_ignora_troca_vazia(tmp_path):
    m = Memoria(tmp_path)
    m.registrar_conversa("  ", "")
    assert Historico(tmp_path).ultimas(5) == []
