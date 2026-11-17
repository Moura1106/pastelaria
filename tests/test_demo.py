from sqlalchemy import func, select

from app import db
from app.demo import banco_esta_vazio, gerar_csv_demo, gerar_dados_demo
from app.importacao import ler_extrato
from app.models import Despesa, Receita


def test_dados_demo_populam_o_banco(app):
    gerar_dados_demo()
    assert not banco_esta_vazio()
    assert db.session.scalar(select(func.count(Receita.id))) > 100
    assert db.session.scalar(select(func.count(Despesa.id))) > 10
    # nenhuma venda com líquido maior que o bruto
    assert db.session.scalar(select(func.count(Receita.id)).where(Receita.valor_liquido > Receita.valor_bruto)) == 0


def test_csv_demo_e_lido_pelo_importador(tmp_path):
    arquivo = tmp_path / "extrato.csv"
    qtd = gerar_csv_demo(arquivo)
    extrato = ler_extrato(arquivo.read_bytes())
    assert len(extrato.vendas) == qtd > 0
    assert all(v.id_externo.startswith("mp:9") for v in extrato.vendas)
