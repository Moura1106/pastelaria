from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook

from app import db
from app.auth import MAX_TENTATIVAS
from app.models import Categoria, Despesa, FormaPagamento, Receita, Usuario


def _entrar(client, senha):
    return client.post("/entrar", data={"email": "teste@exemplo.com", "senha": senha})


def _usuario():
    return db.session.scalar(db.select(Usuario))


# ---------- Bloqueio de login ----------

def test_bloqueia_depois_de_muitas_tentativas(client):
    for _ in range(MAX_TENTATIVAS):
        _entrar(client, "errada")
    assert _usuario().bloqueado_ate > datetime.now()

    resposta = _entrar(client, "senha-segura")  # nem a senha certa entra enquanto bloqueado
    assert "Muitas tentativas" in resposta.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_login_certo_zera_tentativas(client):
    _entrar(client, "errada")
    _entrar(client, "errada")
    _entrar(client, "senha-segura")
    assert _usuario().falhas_login == 0


# ---------- Minha conta ----------

def test_trocar_senha(logado):
    resposta = logado.post("/minha-conta", data={"senha_atual": "errada", "nova_senha": "nova-senha-123",
                                                 "confirmar": "nova-senha-123"})
    assert "Senha atual incorreta" in resposta.get_data(as_text=True)

    resposta = logado.post("/minha-conta", data={"senha_atual": "senha-segura", "nova_senha": "curta",
                                                 "confirmar": "curta"})
    assert "pelo menos 8" in resposta.get_data(as_text=True)

    logado.post("/minha-conta", data={"senha_atual": "senha-segura", "nova_senha": "nova-senha-123",
                                      "confirmar": "nova-senha-123"})
    assert _usuario().conferir_senha("nova-senha-123")


# ---------- Planilha ----------

def test_planilha_do_mes(logado, app):
    insumos = Categoria(nome="Insumos", tipo="despesa")
    pix = FormaPagamento(nome="Pix", taxa_padrao=0)
    db.session.add_all([insumos, pix])
    db.session.flush()
    db.session.add(Receita(data=date(2026, 10, 5), valor_bruto=Decimal("100"), taxa=Decimal("0"),
                           valor_liquido=Decimal("100"), forma_pagto_id=pix.id))
    massa = Despesa(descricao="Massa", data_compra=date(2026, 10, 1), valor_total=Decimal("90"), num_parcelas=3,
                    categoria_id=insumos.id, forma_pagto_id=pix.id, fornecedor="Silva")
    massa.gerar_parcelas(date(2026, 10, 10))
    db.session.add(massa)
    db.session.commit()

    resposta = logado.get("/relatorios/planilha?mes=2026-10")
    assert resposta.status_code == 200
    assert "caixa-2026-10.xlsx" in resposta.headers["Content-Disposition"]

    wb = load_workbook(BytesIO(resposta.data))
    assert wb.sheetnames == ["Resumo", "Vendas", "Contas", "Compras"]
    assert [c.value for c in wb["Resumo"][2]] == ["Outubro de 2026", 100, 0, 100, 30, 70]
    assert wb["Contas"].max_row == 2 and wb["Contas"]["C2"].value == "1/3"
    assert wb["Compras"]["F2"].value == 90


def test_planilha_do_ano(logado):
    resposta = logado.get("/relatorios/planilha?ano=2026")
    wb = load_workbook(BytesIO(resposta.data))
    assert wb["Resumo"].max_row == 13  # cabeçalho + 12 meses


# ---------- Diversos ----------

def test_ajustes_e_erro_404(logado):
    assert "Minha conta" in logado.get("/ajustes").get_data(as_text=True)
    resposta = logado.get("/despesas/99999")
    assert resposta.status_code == 404 and "não encontrada" in resposta.get_data(as_text=True)


def test_icones_existem(client):
    for arquivo in ("icone-192.png", "icone-512.png", "apple-touch-icon.png", "manifest.json"):
        assert client.get(f"/static/{arquivo}").status_code == 200
