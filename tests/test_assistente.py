import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import assistente, db
from app.models import Categoria, Despesa, FormaPagamento, Receita


@pytest.fixture
def dados(app):
    vendas = Categoria(nome="Vendas", tipo="receita")
    insumos = Categoria(nome="Insumos", tipo="despesa")
    pix = FormaPagamento(nome="Pix", taxa_padrao=0)
    credito = FormaPagamento(nome="Crédito", taxa_padrao=0)
    db.session.add_all([vendas, insumos, pix, credito])
    db.session.commit()
    for dia, forma, bruto, taxa in [(date(2026, 10, 5), pix, "100.00", "0.50"), (date(2026, 10, 6), credito, "50.00", "1.95"),
                                    (date(2026, 11, 2), pix, "80.00", "0.40")]:
        db.session.add(Receita(data=dia, forma_pagto_id=forma.id, categoria_id=vendas.id, valor_bruto=Decimal(bruto),
                               taxa=Decimal(taxa), valor_liquido=Decimal(bruto) - Decimal(taxa)))
    compra = Despesa(descricao="Massa de pastel", fornecedor="Silva", valor_total=Decimal("300"), num_parcelas=3,
                     data_compra=date(2026, 10, 1), categoria_id=insumos.id, forma_pagto_id=credito.id)
    compra.gerar_parcelas(date(2026, 10, 10))
    compra.parcelas[0].paga = True
    db.session.add(compra)
    db.session.commit()


def _consulta(nome, **entrada):
    dados, erro = assistente.executar_ferramenta(nome, {"inicio": "2026-10-01", "ate": "2026-10-31", **entrada})
    assert erro is None
    return dados


def test_resumo_do_periodo(dados):
    r = _consulta("resumo_periodo")
    assert r["quantidade_vendas"] == 2 and r["vendas_bruto"] == 150.0 and r["taxas"] == 2.45
    assert r["vendas_liquido"] == 147.55 and r["saidas"] == 100.0 and r["falta_pagar"] == 0.0
    assert r["resultado"] == 47.55


def test_periodo_inclui_o_ultimo_dia(dados):
    assert _consulta("resumo_periodo", inicio="2026-10-06", ate="2026-10-06")["quantidade_vendas"] == 1


def test_falta_pagar_em_meses_futuros(dados):
    r = _consulta("resumo_periodo", inicio="2026-11-01", ate="2026-12-31")
    assert r["saidas"] == 200.0 and r["falta_pagar"] == 200.0


def test_vendas_por_forma_e_por_dia(dados):
    formas = _consulta("vendas_por_forma_pagamento")["formas"]
    assert [(f["forma"], f["bruto"], f["liquido"]) for f in formas] == [("Pix", 100.0, 99.5), ("Crédito", 50.0, 48.05)]
    dias = _consulta("vendas_por_dia")["dias"]
    assert [d["data"] for d in dias] == ["2026-10-05", "2026-10-06"]


def test_despesas_por_categoria_e_fornecedor(dados):
    assert _consulta("despesas_por_categoria")["categorias"] == [{"categoria": "Insumos", "total": 100.0, "parcelas": 1}]
    assert _consulta("despesas_por_fornecedor")["fornecedores"][0]["fornecedor"] == "Silva"


def test_lista_de_parcelas_abertas(dados):
    todas = _consulta("parcelas_do_periodo", inicio="2026-10-01", ate="2026-12-31", somente_abertas=False)["parcelas"]
    abertas = _consulta("parcelas_do_periodo", inicio="2026-10-01", ate="2026-12-31", somente_abertas=True)["parcelas"]
    assert [p["parcela"] for p in todas] == ["1/3", "2/3", "3/3"] and todas[0]["paga"] is True
    assert [p["parcela"] for p in abertas] == ["2/3", "3/3"]


@pytest.mark.parametrize("entrada", [
    {"inicio": "ontem", "ate": "2026-10-31"},
    {"inicio": "2026-10-31", "ate": "2026-10-01"},
    {"inicio": "2000-01-01", "ate": "2026-10-01"},
    {"inicio": "2026-10-01"},
])
def test_pedidos_invalidos_viram_erro(dados, entrada):
    resultado, erro = assistente.executar_ferramenta("resumo_periodo", entrada)
    assert resultado is None and erro.startswith("Pedido inválido")


def test_ferramenta_desconhecida_nao_executa(dados):
    assert assistente.executar_ferramenta("apagar_tudo", {})[1].startswith("Ferramenta desconhecida")


def test_consultas_nao_alteram_o_caixa(dados):
    antes = (len(db.session.scalars(db.select(Receita)).all()), len(db.session.scalars(db.select(Despesa)).all()))
    for nome in assistente._CONSULTAS:
        _consulta(nome, **({"somente_abertas": False} if nome == "parcelas_do_periodo" else {}))
    depois = (len(db.session.scalars(db.select(Receita)).all()), len(db.session.scalars(db.select(Despesa)).all()))
    assert antes == depois


def test_todas_as_ferramentas_tem_consulta():
    assert {f["name"] for f in assistente.FERRAMENTAS} == set(assistente._CONSULTAS)


# ---------- conversa com a IA (cliente de mentira) ----------

def _usa(nome, entrada, id="t1"):
    bloco = SimpleNamespace(type="tool_use", id=id, name=nome, input=entrada)
    return SimpleNamespace(stop_reason="tool_use", content=[bloco], usage=SimpleNamespace(input_tokens=1000, output_tokens=50))


def _fala(texto, parada="end_turn"):
    bloco = SimpleNamespace(type="text", text=texto)
    return SimpleNamespace(stop_reason=parada, content=[bloco], usage=SimpleNamespace(input_tokens=1200, output_tokens=80))


class ClienteFalso:
    def __init__(self, *respostas):
        self.respostas, self.pedidos = list(respostas), []
        self.messages = self

    def create(self, **pedido):
        self.pedidos.append({**pedido, "messages": list(pedido["messages"])})
        return self.respostas.pop(0)


def test_ia_consulta_e_responde(app, dados):
    cliente = ClienteFalso(
        _usa("resumo_periodo", {"inicio": "2026-10-01", "ate": "2026-10-31"}),
        _fala("Em outubro você vendeu R$ 150,00."),
    )
    texto, entrada, saida = assistente.perguntar("Quanto vendi em outubro?", cliente, hoje=date(2026, 10, 29))
    assert texto == "Em outubro você vendeu R$ 150,00." and (entrada, saida) == (2200, 130)

    primeiro, segundo = cliente.pedidos
    assert primeiro["model"] == "claude-haiku-5-5" and primeiro["output_config"] == {"effort": "low"}
    assert "29/10/2026" in primeiro["system"] and "temperature" not in primeiro
    resultado = segundo["messages"][-1]["content"][0]
    assert resultado["tool_use_id"] == "t1" and json.loads(resultado["content"])["vendas_bruto"] == 150.0


def test_erro_de_consulta_volta_para_a_ia(app, dados):
    cliente = ClienteFalso(_usa("resumo_periodo", {"inicio": "x", "ate": "y"}), _fala("Não entendi as datas."))
    assistente.perguntar("?", cliente)
    resultado = cliente.pedidos[1]["messages"][-1]["content"][0]
    assert resultado["is_error"] is True and "Pedido inválido" in resultado["content"]


def test_limite_de_consultas_por_pergunta(app, dados):
    entrada = {"inicio": "2026-10-01", "ate": "2026-10-31"}
    cliente = ClienteFalso(*[_usa("resumo_periodo", entrada, id=f"t{i}") for i in range(assistente.MAX_VOLTAS)])
    with pytest.raises(assistente.RespostaIndisponivel):
        assistente.perguntar("loop", cliente)


def test_recusa_e_resposta_cortada(app, dados):
    with pytest.raises(assistente.RespostaIndisponivel):
        assistente.perguntar("x", ClienteFalso(_fala("", parada="refusal")))
    texto, *_ = assistente.perguntar("x", ClienteFalso(_fala("Parte da resposta", parada="max_tokens")))
    assert texto.startswith("Parte da resposta") and "foi cortada" in texto


# ---------- tela ----------

def test_sem_chave_a_tela_avisa_e_sai_do_menu(logado):
    pagina = logado.get("/perguntar/").get_data(as_text=True)
    assert "ainda não foi ligado" in pagina
    assert 'href="/perguntar/"' not in logado.get("/").get_data(as_text=True)


def test_com_chave_aparece_no_menu_e_responde(app, logado, dados, monkeypatch):
    app.config["ANTHROPIC_API_KEY"] = "chave-de-teste"
    cliente = ClienteFalso(_fala("Tudo certo <b>neste</b> mês."))
    monkeypatch.setattr(assistente, "obter_cliente", lambda: cliente)

    assert 'href="/perguntar/"' in logado.get("/").get_data(as_text=True)
    pagina = logado.post("/perguntar/", data={"pergunta": "Como estou?"}).get_data(as_text=True)
    assert "Tudo certo &lt;b&gt;neste&lt;/b&gt; mês." in pagina  # texto da IA nunca vira HTML


def test_pergunta_vazia_ou_grande_demais(app, logado, monkeypatch):
    app.config["ANTHROPIC_API_KEY"] = "chave-de-teste"
    monkeypatch.setattr(assistente, "obter_cliente", lambda: pytest.fail("não deveria chamar a IA"))
    assert "Escreva a pergunta" in logado.post("/perguntar/", data={"pergunta": "  "}).get_data(as_text=True)
    assert "no máximo 500" in logado.post("/perguntar/", data={"pergunta": "a" * 501}).get_data(as_text=True)


def test_falha_da_api_mostra_aviso_amigavel(app, logado, monkeypatch):
    import anthropic
    app.config["ANTHROPIC_API_KEY"] = "chave-de-teste"

    class Quebrado:
        class messages:
            @staticmethod
            def create(**_):
                raise anthropic.APIConnectionError(request=None)

    monkeypatch.setattr(assistente, "obter_cliente", lambda: Quebrado)
    pagina = logado.post("/perguntar/", data={"pergunta": "Como estou?"}).get_data(as_text=True)
    assert "não conseguiu responder agora" in pagina


def test_tela_exige_login(client):
    assert client.get("/perguntar/").status_code == 302
