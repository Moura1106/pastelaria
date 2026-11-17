from datetime import date
from decimal import Decimal

import pytest

from app import db
from app.models import Categoria, FormaPagamento, Receita


@pytest.fixture
def cadastros(app):
    vendas = Categoria(nome="Vendas", tipo="receita")
    dinheiro = FormaPagamento(nome="Dinheiro", taxa_padrao=0)
    credito = FormaPagamento(nome="Crédito", taxa_padrao=Decimal("3.15"))
    db.session.add_all([vendas, dinheiro, credito])
    db.session.commit()
    return {"vendas": vendas, "dinheiro": dinheiro, "credito": credito}


def _venda(cadastros, **dados):
    base = {
        "data": "2026-10-27",
        "valor_bruto": "100,00",
        "forma_pagto_id": cadastros["credito"].id,
        "categoria_id": cadastros["vendas"].id,
        "taxa": "",
        "descricao": "",
    }
    base.update(dados)
    return base


def test_taxa_calculada_pela_forma_de_pagamento(logado, cadastros):
    logado.post("/vendas/nova", data=_venda(cadastros))
    receita = db.session.scalar(db.select(Receita))
    assert receita.valor_bruto == Decimal("100.00")
    assert receita.taxa == Decimal("3.15")
    assert receita.valor_liquido == Decimal("96.85")
    assert receita.origem == "manual"


def test_taxa_informada_manualmente(logado, cadastros):
    logado.post("/vendas/nova", data=_venda(cadastros, valor_bruto="1.234,56", taxa="10,00"))
    receita = db.session.scalar(db.select(Receita))
    assert receita.valor_bruto == Decimal("1234.56")
    assert receita.valor_liquido == Decimal("1224.56")


def test_taxa_maior_que_valor(logado, cadastros):
    resposta = logado.post("/vendas/nova", data=_venda(cadastros, valor_bruto="10", taxa="20"))
    assert "não pode ser maior" in resposta.get_data(as_text=True)
    assert db.session.scalar(db.select(db.func.count(Receita.id))) == 0


def test_salvar_e_lancar_outra_mantem_data_e_forma(logado, cadastros):
    resposta = logado.post("/vendas/nova", data=_venda(cadastros, outra="1"))
    assert resposta.status_code == 302
    assert "data=2026-10-27" in resposta.headers["Location"]
    assert f"forma={cadastros['credito'].id}" in resposta.headers["Location"]


def test_lista_do_mes_soma_totais(logado, cadastros):
    logado.post("/vendas/nova", data=_venda(cadastros))
    logado.post("/vendas/nova", data=_venda(cadastros, valor_bruto="50", forma_pagto_id=cadastros["dinheiro"].id))
    logado.post("/vendas/nova", data=_venda(cadastros, data="2026-11-02"))  # outro mês, fica de fora

    pagina = logado.get("/vendas/?mes=2026-10").get_data(as_text=True)
    assert "outubro de 2026" in pagina
    assert "R$ 150,00" in pagina   # vendido
    assert "R$ 146,85" in pagina   # líquido


def test_editar_e_excluir(logado, cadastros):
    logado.post("/vendas/nova", data=_venda(cadastros))
    receita = db.session.scalar(db.select(Receita))

    logado.post(f"/vendas/{receita.id}/editar",
                data=_venda(cadastros, valor_bruto="200", forma_pagto_id=cadastros["dinheiro"].id))
    db.session.refresh(receita)
    assert receita.valor_liquido == Decimal("200.00")

    logado.post(f"/vendas/{receita.id}/excluir")
    assert db.session.get(Receita, receita.id) is None


def test_inicio_mostra_vendas_de_hoje(logado, cadastros):
    logado.post("/vendas/nova", data=_venda(cadastros, data=date.today().isoformat()))
    assert "R$ 96,85" in logado.get("/").get_data(as_text=True)
