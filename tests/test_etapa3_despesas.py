from datetime import date, timedelta
from decimal import Decimal

import pytest

from app import db
from app.models import Categoria, Despesa, FormaPagamento, Parcela


@pytest.fixture
def cadastros(app):
    insumos = Categoria(nome="Insumos", tipo="despesa")
    credito = FormaPagamento(nome="Crédito parcelado", taxa_padrao=0)
    dinheiro = FormaPagamento(nome="Dinheiro", taxa_padrao=0)
    db.session.add_all([insumos, credito, dinheiro])
    db.session.commit()
    return {"insumos": insumos, "credito": credito, "dinheiro": dinheiro}


def _despesa(cadastros, **dados):
    base = {
        "descricao": "Massa de pastel",
        "valor_total": "1.000,00",
        "data_compra": "2026-10-27",
        "categoria_id": cadastros["insumos"].id,
        "forma_pagto_id": cadastros["credito"].id,
        "fornecedor": "Distribuidora Silva",
        "num_parcelas": "3",
        "primeiro_vencimento": "2026-11-10",
    }
    base.update(dados)
    return base


def _unica_despesa():
    return db.session.scalar(db.select(Despesa))


def test_compra_parcelada_gera_parcelas(logado, cadastros):
    resposta = logado.post("/despesas/nova", data=_despesa(cadastros))
    despesa = _unica_despesa()
    assert resposta.headers["Location"] == f"/despesas/{despesa.id}"
    assert despesa.fornecedor == "Distribuidora Silva"
    assert [(p.valor, p.vencimento, p.paga) for p in despesa.parcelas] == [
        (Decimal("333.33"), date(2026, 11, 10), False),
        (Decimal("333.33"), date(2026, 12, 10), False),
        (Decimal("333.34"), date(2027, 1, 10), False),
    ]
    pagina = logado.get(f"/despesas/{despesa.id}").get_data(as_text=True)
    assert "R$ 333,34" in pagina and "3ª parcela" in pagina


def test_parcelado_exige_vencimento(logado, cadastros):
    resposta = logado.post("/despesas/nova", data=_despesa(cadastros, primeiro_vencimento=""))
    assert "Informe o vencimento da 1ª parcela" in resposta.get_data(as_text=True)
    assert _unica_despesa() is None


def test_categoria_obrigatoria(logado, cadastros):
    resposta = logado.post("/despesas/nova", data=_despesa(cadastros, categoria_id="0"))
    assert "Escolha a categoria" in resposta.get_data(as_text=True)


def test_a_vista_ja_paga(logado, cadastros):
    logado.post("/despesas/nova", data=_despesa(
        cadastros, num_parcelas="1", primeiro_vencimento="", ja_paga="y", forma_pagto_id=cadastros["dinheiro"].id))
    parcela = _unica_despesa().parcelas[0]
    assert parcela.vencimento == date(2026, 10, 27)
    assert parcela.paga and parcela.data_pagamento == date(2026, 10, 27)


def test_a_vista_sem_marcar_paga(logado, cadastros):
    logado.post("/despesas/nova", data=_despesa(cadastros, num_parcelas="1", primeiro_vencimento="2026-11-05"))
    parcela = _unica_despesa().parcelas[0]
    assert parcela.vencimento == date(2026, 11, 5) and not parcela.paga


def test_pagar_e_desfazer_parcela(logado, cadastros):
    logado.post("/despesas/nova", data=_despesa(cadastros))
    parcela = _unica_despesa().parcelas[0]

    resposta = logado.post(f"/despesas/parcelas/{parcela.id}/pagar", data={"voltar": "/despesas/?mes=2026-11"})
    assert resposta.headers["Location"] == "/despesas/?mes=2026-11"
    db.session.refresh(parcela)
    assert parcela.paga and parcela.data_pagamento == date.today()

    logado.post(f"/despesas/parcelas/{parcela.id}/pagar", data={"voltar": "https://site-malicioso.com"})
    db.session.refresh(parcela)
    assert not parcela.paga and parcela.data_pagamento is None


def test_contas_do_mes(logado, cadastros):
    logado.post("/despesas/nova", data=_despesa(cadastros))
    pagina = logado.get("/despesas/?mes=2026-12").get_data(as_text=True)
    assert "Massa de pastel" in pagina and "2/3" in pagina
    assert "R$ 333,33" in pagina

    compras = logado.get("/despesas/?mes=2026-10&ver=compras").get_data(as_text=True)
    assert "R$ 1.000,00" in compras and "em 3x" in compras


def test_editar_recalcula_e_mantem_pagas(logado, cadastros):
    logado.post("/despesas/nova", data=_despesa(cadastros))
    despesa = _unica_despesa()
    logado.post(f"/despesas/parcelas/{despesa.parcelas[0].id}/pagar")

    logado.post(f"/despesas/{despesa.id}/editar", data=_despesa(cadastros, valor_total="1200", num_parcelas="4"))
    db.session.expire_all()
    despesa = _unica_despesa()
    assert [p.valor for p in despesa.parcelas] == [Decimal("300.00")] * 4
    assert [p.paga for p in despesa.parcelas] == [True, False, False, False]
    assert db.session.scalar(db.select(db.func.count(Parcela.id))) == 4


def test_editar_so_descricao_nao_mexe_nas_parcelas(logado, cadastros):
    logado.post("/despesas/nova", data=_despesa(cadastros))
    despesa = _unica_despesa()
    ids = [p.id for p in despesa.parcelas]
    logado.post(f"/despesas/{despesa.id}/editar", data=_despesa(cadastros, descricao="Massa de pastel 5kg"))
    db.session.expire_all()
    despesa = _unica_despesa()
    assert despesa.descricao == "Massa de pastel 5kg"
    assert [p.id for p in despesa.parcelas] == ids


def test_excluir_remove_parcelas(logado, cadastros):
    logado.post("/despesas/nova", data=_despesa(cadastros))
    resposta = logado.post(f"/despesas/{_unica_despesa().id}/excluir")
    assert resposta.status_code == 302
    assert db.session.scalar(db.select(db.func.count(Parcela.id))) == 0


def test_inicio_avisa_contas_vencidas(logado, cadastros):
    ontem = date.today() - timedelta(days=1)
    logado.post("/despesas/nova", data=_despesa(
        cadastros, num_parcelas="1", data_compra=ontem.isoformat(), primeiro_vencimento=ontem.isoformat()))
    assert "1 conta vencida" in logado.get("/").get_data(as_text=True)


def test_parcelas_em_lista_de_1_a_50(logado, cadastros):
    pagina = logado.get("/despesas/nova").get_data(as_text=True)
    assert '<select id="num_parcelas"' in pagina
    assert '<option value="50">50x</option>' in pagina and 'value="51"' not in pagina
    logado.post("/despesas/nova", data=_despesa(cadastros, num_parcelas="51"))
    assert _unica_despesa() is None


def test_compra_antiga_em_mais_de_50x_continua_editavel(logado, cadastros):
    despesa = Despesa(descricao="Freezer", valor_total=Decimal("1800"), data_compra=date(2026, 10, 1),
                      categoria_id=cadastros["insumos"].id, forma_pagto_id=cadastros["credito"].id, num_parcelas=60)
    despesa.gerar_parcelas(date(2026, 11, 10))
    db.session.add(despesa)
    db.session.commit()
    pagina = logado.get(f"/despesas/{despesa.id}/editar").get_data(as_text=True)
    assert '<option selected value="60">60x</option>' in pagina
    logado.post(f"/despesas/{despesa.id}/editar", data=_despesa(cadastros, descricao="Freezer novo", num_parcelas="60"))
    db.session.expire_all()
    assert _unica_despesa().descricao == "Freezer novo" and len(_unica_despesa().parcelas) == 60
