from datetime import date
from decimal import Decimal

from app import db
from app.models import Categoria, Despesa, FormaPagamento
from app.utils import brl, dividir_em_parcelas, somar_meses


# ---------- Utilitários ----------

def test_dividir_em_parcelas_soma_bate():
    parcelas = dividir_em_parcelas(Decimal("1000"), 3)
    assert parcelas == [Decimal("333.33"), Decimal("333.33"), Decimal("333.34")]
    assert sum(parcelas) == Decimal("1000.00")


def test_somar_meses_ajusta_fim_do_mes():
    assert somar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert somar_meses(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_brl():
    assert brl(Decimal("1234.5")) == "R$ 1.234,50"
    assert brl(Decimal("-10")) == "-R$ 10,00"


def test_gerar_parcelas(app):
    despesa = Despesa(valor_total=Decimal("1000"), num_parcelas=3)
    despesa.gerar_parcelas(date(2026, 11, 10))
    assert [p.vencimento for p in despesa.parcelas] == [date(2026, 11, 10), date(2026, 12, 10), date(2027, 1, 10)]
    assert sum(p.valor for p in despesa.parcelas) == Decimal("1000.00")


# ---------- Login ----------

def test_paginas_exigem_login(client):
    resposta = client.get("/cadastros/categorias")
    assert resposta.status_code == 302
    assert "/entrar" in resposta.headers["Location"]


def test_login_senha_errada(client):
    resposta = client.post("/entrar", data={"email": "teste@exemplo.com", "senha": "errada"})
    assert "incorretos" in resposta.get_data(as_text=True)


def test_login_ok_e_ignora_redirect_externo(client):
    resposta = client.post("/entrar?next=//site-malicioso.com",
                           data={"email": "TESTE@exemplo.com", "senha": "senha-segura"})
    assert resposta.status_code == 302
    assert resposta.headers["Location"] == "/"


def test_logout(logado):
    logado.post("/sair")
    assert logado.get("/").status_code == 302


# ---------- Cadastros ----------

def test_cria_edita_e_desativa_categoria(logado, app):
    logado.post("/cadastros/categorias", data={"nome": "Carvão", "tipo": "despesa"})
    categoria = db.session.scalar(db.select(Categoria).filter_by(nome="Carvão"))
    assert categoria.tipo == "despesa" and categoria.ativa

    logado.post(f"/cadastros/categorias/{categoria.id}/editar", data={"nome": "Carvão e lenha"})
    logado.post(f"/cadastros/categorias/{categoria.id}/alternar")
    db.session.refresh(categoria)
    assert categoria.nome == "Carvão e lenha" and not categoria.ativa


def test_categoria_duplicada(logado):
    logado.post("/cadastros/categorias", data={"nome": "Gás", "tipo": "despesa"})
    resposta = logado.post("/cadastros/categorias", data={"nome": "gás", "tipo": "despesa"})
    assert "Já existe" in resposta.get_data(as_text=True)


def test_forma_pagamento_aceita_virgula(logado):
    logado.post("/cadastros/pagamentos", data={"nome": "Crédito", "taxa_padrao": "3,15"})
    forma = db.session.scalar(db.select(FormaPagamento).filter_by(nome="Crédito"))
    assert forma.taxa_padrao == Decimal("3.15")
    assert "3,15%" in logado.get("/cadastros/pagamentos").get_data(as_text=True)
