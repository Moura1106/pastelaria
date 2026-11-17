from datetime import date
from decimal import Decimal

import pytest

from app import db
from app.models import Categoria, Despesa, DespesaFixa, FormaPagamento
from app.recorrencia import HORIZONTE_MESES, gerar_despesas_fixas, mes_atual
from app.utils import somar_meses


@pytest.fixture
def cadastros(app):
    aluguel = Categoria(nome="Aluguel", tipo="despesa")
    energia = Categoria(nome="Energia", tipo="despesa")
    pix = FormaPagamento(nome="Pix", taxa_padrao=0)
    db.session.add_all([aluguel, energia, pix])
    db.session.commit()
    return {"aluguel": aluguel, "energia": energia, "pix": pix}


def _fixa(cadastros, **dados):
    base = {
        "descricao": "Aluguel",
        "valor": "1.500,00",
        "dia_vencimento": "10",
        "categoria_id": cadastros["aluguel"].id,
        "forma_pagto_id": cadastros["pix"].id,
        "fornecedor": "",
        "inicio": mes_atual().strftime("%Y-%m"),
    }
    base.update(dados)
    return base


def _contas(fixa_id=None):
    consulta = db.select(Despesa).order_by(Despesa.data_compra)
    if fixa_id:
        consulta = consulta.where(Despesa.fixa_id == fixa_id)
    return db.session.scalars(consulta).all()


def test_cadastro_lanca_contas_ate_o_horizonte(logado, cadastros):
    logado.post("/despesas/fixas/", data=_fixa(cadastros))
    contas = _contas()
    assert len(contas) == HORIZONTE_MESES
    assert contas[0].data_compra == mes_atual().replace(day=10)
    assert all(c.valor_total == Decimal("1500.00") and not c.parcelas[0].paga for c in contas)
    assert all(c.fixa_id for c in contas)


def test_geracao_nao_duplica(logado, cadastros):
    logado.post("/despesas/fixas/", data=_fixa(cadastros))
    gerar_despesas_fixas()
    logado.get("/")
    logado.get("/despesas/")
    assert len(_contas()) == HORIZONTE_MESES


def test_ver_mes_distante_lanca_ate_ele(logado, cadastros):
    logado.post("/despesas/fixas/", data=_fixa(cadastros))
    distante = somar_meses(mes_atual(), 8)
    pagina = logado.get(f"/despesas/?mes={distante.strftime('%Y-%m')}").get_data(as_text=True)
    assert "Aluguel" in pagina and "fixa" in pagina
    assert len(_contas()) == 9


def test_dia_31_em_mes_curto(app, cadastros):
    fixa = DespesaFixa(descricao="Internet", valor=Decimal("100"), dia_vencimento=31,
                       categoria_id=cadastros["energia"].id, forma_pagto_id=cadastros["pix"].id,
                       inicio=date(2027, 2, 1))
    assert fixa.vencimento_em(date(2027, 2, 1)) == date(2027, 2, 28)


def test_comeca_em_mes_passado(logado, cadastros):
    inicio = somar_meses(mes_atual(), -2)
    logado.post("/despesas/fixas/", data=_fixa(cadastros, inicio=inicio.strftime("%Y-%m")))
    assert _contas()[0].data_compra == inicio.replace(day=10)
    assert len(_contas()) == HORIZONTE_MESES + 2


def test_editar_fixa_respeita_ajuste_manual(logado, cadastros):
    logado.post("/despesas/fixas/", data=_fixa(cadastros, descricao="Luz", valor="300",
                                                categoria_id=cadastros["energia"].id))
    fixa = db.session.scalar(db.select(DespesaFixa))
    contas = _contas(fixa.id)

    # Conta do próximo mês veio diferente e foi ajustada à mão
    ajustada = contas[1]
    logado.post(f"/despesas/{ajustada.id}/editar", data={
        "descricao": "Luz", "valor_total": "352,40", "data_compra": ajustada.data_compra.isoformat(),
        "categoria_id": cadastros["energia"].id, "forma_pagto_id": cadastros["pix"].id,
        "fornecedor": "", "num_parcelas": "1", "primeiro_vencimento": ajustada.data_compra.isoformat(),
    })
    # A conta deste mês já foi paga
    logado.post(f"/despesas/parcelas/{contas[0].parcelas[0].id}/pagar")

    logado.post(f"/despesas/fixas/{fixa.id}/editar", data=_fixa(
        cadastros, descricao="Energia elétrica", valor="320", dia_vencimento="15",
        categoria_id=cadastros["energia"].id))

    db.session.expire_all()
    contas = _contas(fixa.id)
    assert contas[0].valor_total == Decimal("300.00") and contas[0].descricao == "Luz"   # paga: não muda
    assert contas[1].valor_total == Decimal("352.40")                                    # ajuste mantido
    assert contas[1].descricao == "Energia elétrica"
    assert contas[2].valor_total == Decimal("320.00") and contas[2].parcelas[0].valor == Decimal("320.00")
    assert contas[2].parcelas[0].vencimento.day == 15


def test_desativar_remove_futuras_e_reativar_volta(logado, cadastros):
    logado.post("/despesas/fixas/", data=_fixa(cadastros))
    fixa = db.session.scalar(db.select(DespesaFixa))
    logado.post(f"/despesas/parcelas/{_contas()[2].parcelas[0].id}/pagar")  # uma futura já paga

    logado.post(f"/despesas/fixas/{fixa.id}/alternar")
    contas = _contas()
    assert [c.data_compra.replace(day=1) for c in contas] == [mes_atual(), somar_meses(mes_atual(), 2)]

    logado.get("/despesas/")  # não deve gerar nada enquanto desativada
    assert len(_contas()) == 2

    logado.post(f"/despesas/fixas/{fixa.id}/alternar")
    meses = [c.data_compra.replace(day=1) for c in _contas()]
    assert meses == [somar_meses(mes_atual(), i) for i in range(HORIZONTE_MESES)]


def test_excluir_conta_de_um_mes_nao_volta(logado, cadastros):
    logado.post("/despesas/fixas/", data=_fixa(cadastros))
    logado.post(f"/despesas/{_contas()[1].id}/excluir")
    logado.get("/")
    assert len(_contas()) == HORIZONTE_MESES - 1


def test_excluir_fixa_por_engano(logado, cadastros):
    logado.post("/despesas/fixas/", data=_fixa(cadastros))
    fixa = db.session.scalar(db.select(DespesaFixa))
    logado.post(f"/despesas/fixas/{fixa.id}/excluir")
    assert db.session.scalar(db.select(DespesaFixa)) is None
    assert _contas() == []
    logado.get("/")  # não pode voltar a gerar nada
    assert _contas() == []


def test_excluir_fixa_mantem_contas_pagas(logado, cadastros):
    logado.post("/despesas/fixas/", data=_fixa(cadastros))
    fixa = db.session.scalar(db.select(DespesaFixa))
    paga = _contas()[0]
    logado.post(f"/despesas/parcelas/{paga.parcelas[0].id}/pagar")

    resposta = logado.post(f"/despesas/fixas/{fixa.id}/excluir", follow_redirects=True)
    assert "1 conta(s) já paga(s) ficaram no histórico" in resposta.get_data(as_text=True)
    db.session.expire_all()
    restantes = _contas()
    assert len(restantes) == 1 and restantes[0].id == paga.id and restantes[0].fixa_id is None
    assert logado.get(f"/despesas/{paga.id}").status_code == 200


def test_fixa_entra_nos_relatorios(logado, cadastros):
    logado.post("/despesas/fixas/", data=_fixa(cadastros))
    pagina = logado.get("/relatorios/").get_data(as_text=True)
    assert "Aluguel" in pagina and "R$ 1.500,00" in pagina
