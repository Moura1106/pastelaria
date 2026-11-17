from datetime import date
from decimal import Decimal

import pytest

from app import db
from app.models import Categoria, Despesa, FormaPagamento, Receita
from app.utils import mes_curto, somar_meses


@pytest.fixture
def dados(app):
    """Outubro/2026: vendas de 1.000 (taxa 30) e massa de 900 em 3x a partir de out + gás 120 à vista."""
    insumos = Categoria(nome="Insumos", tipo="despesa")
    gas = Categoria(nome="Gás e carvão", tipo="despesa")
    vendas = Categoria(nome="Vendas", tipo="receita")
    credito = FormaPagamento(nome="Crédito", taxa_padrao=3)
    db.session.add_all([insumos, gas, vendas, credito])
    db.session.flush()

    db.session.add(Receita(data=date(2026, 10, 5), valor_bruto=Decimal("1000"), taxa=Decimal("30"),
                           valor_liquido=Decimal("970"), forma_pagto_id=credito.id, categoria_id=vendas.id))
    massa = Despesa(descricao="Massa", data_compra=date(2026, 10, 1), valor_total=Decimal("900"),
                    num_parcelas=3, categoria_id=insumos.id, forma_pagto_id=credito.id)
    massa.gerar_parcelas(date(2026, 10, 10))
    botijao = Despesa(descricao="Botijão", data_compra=date(2026, 10, 3), valor_total=Decimal("120"),
                      num_parcelas=1, categoria_id=gas.id, forma_pagto_id=credito.id)
    botijao.gerar_parcelas(date(2026, 10, 3))
    db.session.add_all([massa, botijao])
    db.session.commit()


def test_resultado_do_mes_usa_parcela(logado, dados):
    pagina = logado.get("/relatorios/?mes=2026-10").get_data(as_text=True)
    assert "R$ 970,00" in pagina        # entradas líquidas
    assert "R$ 420,00" in pagina        # saídas: parcela de 300 + botijão de 120
    assert "Sobrou" in pagina and "R$ 550,00" in pagina


def test_gastos_por_categoria(logado, dados):
    pagina = logado.get("/relatorios/?mes=2026-10").get_data(as_text=True)
    assert pagina.index("Insumos") < pagina.index("Gás e carvão")  # maior gasto primeiro
    assert "71%" in pagina  # 300 de 420


def test_mes_com_prejuizo(logado, dados):
    pagina = logado.get("/relatorios/?mes=2026-11").get_data(as_text=True)
    assert "Faltou" in pagina and "-R$ 300,00" in pagina


def test_comparativo_e_compromissos(logado, dados):
    pagina = logado.get("/relatorios/?mes=2026-12").get_data(as_text=True)
    assert "out/26" in pagina and "dez/26" in pagina
    atual = date.today().replace(day=1)
    assert mes_curto(atual) in pagina and mes_curto(somar_meses(atual, 5)) in pagina


def test_relatorio_vazio(logado):
    resposta = logado.get("/relatorios/")
    assert resposta.status_code == 200
    assert "Nenhuma despesa" in resposta.get_data(as_text=True)
