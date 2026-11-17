import base64
import io
from datetime import date
from decimal import Decimal

import pytest

from app import db
from app.importacao import ExtratoInvalido, classificar, ler_extrato
from app.models import Categoria, FormaPagamento, Receita

CABECALHO = ("OPERATION_DATETIME;RELEASE_DATETIME;MOVEMENT_TYPE;PAYMENT_ID;LOCAL;CHARGE_METHOD;"
             "PAYMENT_METHOD_DETAIL;PAYMENT_METHOD;GROSS_VALUE;SALES_DISCOUNTS;NET;SEGMENTATION_DETAIL")
LINHAS = [
    "15-10-2026 11:15:20;15-10-2026 11:15:19;Pagamento;1001;Loja;Point;Master;;30,00;-0,50;29,50;null",
    "15-10-2026 14:20:10;15-10-2026 14:20:08;Pagamento;1002;Loja;Point;Cartão de crédito;Master;25,00;-0,97;24,03;null",
    "15-10-2026 16:05:30;15-10-2026 16:05:29;Pagamento;1003;Loja;Código QR;Pix;;20,00;-0,10;19,90;QR",
    "16-10-2026 19:45:00;16-10-2026 19:44:58;Pagamento;1004;Loja;Point;Cartão de débito;Visa débito;7,00;-0,12;6,88;null",
]


def _csv(*linhas, codificacao="utf-8"):
    return ("\n" + CABECALHO + "\n" + "\n".join(linhas) + "\n").encode(codificacao)


@pytest.fixture
def cadastros(app):
    vendas = Categoria(nome="Vendas", tipo="receita")
    formas = {n: FormaPagamento(nome=n, taxa_padrao=0) for n in ["Dinheiro", "Pix", "Débito", "Crédito à vista"]}
    db.session.add_all([vendas, *formas.values()])
    db.session.commit()
    return {"vendas": vendas, **formas}


def _enviar(logado, conteudo, nome="extrato.csv"):
    return logado.post("/vendas/importar", data={"arquivo": (io.BytesIO(conteudo), nome)},
                       content_type="multipart/form-data")


def _confirmar(logado, conteudo, cadastros, **formas):
    dados = {"arquivo": base64.b64encode(conteudo).decode(),
             "forma_pix": cadastros["Pix"].id, "forma_debito": cadastros["Débito"].id,
             "forma_credito": cadastros["Crédito à vista"].id}
    dados.update(formas)
    return logado.post("/vendas/importar/confirmar", data=dados, follow_redirects=True)


def test_le_o_extrato_do_mercado_pago():
    extrato = ler_extrato(_csv(*LINHAS))
    assert [v.tipo for v in extrato.vendas] == ["debito", "credito", "pix", "debito"]
    primeira = extrato.vendas[0]
    assert primeira.id_externo == "mp:1001" and primeira.data == date(2026, 10, 15)
    assert (primeira.bruto, primeira.taxa, primeira.liquido) == (Decimal("30.00"), Decimal("0.50"), Decimal("29.50"))


def test_arquivo_em_cp1252():
    extrato = ler_extrato(_csv(LINHAS[1], codificacao="cp1252"))
    assert extrato.vendas[0].tipo == "credito"


def test_classificar_cartao_sem_tipo_vira_debito():
    assert classificar("Point", "Master", "") == "debito"
    assert classificar("Código QR", "Pix", "") == "pix"
    assert classificar("Point", "", "") == "outro"


def test_ignora_estorno_e_linhas_repetidas():
    estorno = "24-10-2026 10:00:00;24-10-2026 10:00:00;Reembolso;1005;Loja;Point;Master;;-30,00;0,00;-30,00;null"
    extrato = ler_extrato(_csv(LINHAS[0], LINHAS[0], estorno))
    assert len(extrato.vendas) == 1
    assert len(extrato.ignoradas) == 1 and "Reembolso" in extrato.ignoradas[0]


def test_arquivo_que_nao_e_extrato():
    with pytest.raises(ExtratoInvalido):
        ler_extrato(b"nome;valor\nfulano;10\n")


def test_previa_nao_grava_nada(logado, cadastros):
    resposta = _enviar(logado, _csv(*LINHAS))
    pagina = resposta.get_data(as_text=True)
    assert resposta.status_code == 200
    assert "Confirmar importação" in pagina and "R$ 82,00" in pagina
    assert db.session.scalar(db.select(Receita)) is None


def test_previa_sugere_as_formas_cadastradas(logado, cadastros):
    pagina = _enviar(logado, _csv(*LINHAS)).get_data(as_text=True)
    assert f'<option value="{cadastros["Crédito à vista"].id}" selected>' in pagina
    assert f'<option value="{cadastros["Pix"].id}" selected>' in pagina


def test_confirmar_grava_com_a_taxa_do_extrato(logado, cadastros):
    resposta = _confirmar(logado, _csv(*LINHAS), cadastros)
    assert "4 vendas importadas" in resposta.get_data(as_text=True)
    receitas = db.session.scalars(db.select(Receita).order_by(Receita.id)).all()
    assert len(receitas) == 4
    credito = receitas[1]
    assert credito.forma_pagto_id == cadastros["Crédito à vista"].id
    assert (credito.valor_bruto, credito.taxa, credito.valor_liquido) == (Decimal("25.00"), Decimal("0.97"), Decimal("24.03"))
    assert credito.origem == "importado" and credito.categoria_id == cadastros["vendas"].id
    assert credito.descricao.startswith("Mercado Pago 14:20")


def test_importar_de_novo_nao_duplica(logado, cadastros):
    _confirmar(logado, _csv(*LINHAS[:2]), cadastros)
    pagina = _enviar(logado, _csv(*LINHAS)).get_data(as_text=True)
    assert "2 vendas deste arquivo já estavam" in pagina
    resposta = _confirmar(logado, _csv(*LINHAS), cadastros)
    assert "2 vendas importadas" in resposta.get_data(as_text=True)
    assert len(db.session.scalars(db.select(Receita)).all()) == 4

    resposta = _confirmar(logado, _csv(*LINHAS), cadastros)
    assert "Nada foi importado" in resposta.get_data(as_text=True)
    assert len(db.session.scalars(db.select(Receita)).all()) == 4


def test_forma_invalida_volta_para_a_previa(logado, cadastros):
    resposta = _confirmar(logado, _csv(*LINHAS), cadastros, forma_pix="")
    assert "Escolha a forma de pagamento" in resposta.get_data(as_text=True)
    assert db.session.scalar(db.select(Receita)) is None


def test_envio_de_arquivo_errado(logado, cadastros):
    pagina = _enviar(logado, b"qualquer coisa").get_data(as_text=True)
    assert "Não reconheci este arquivo" in pagina
    pagina = _enviar(logado, _csv(*LINHAS), nome="extrato.pdf").get_data(as_text=True)
    assert "precisa ser .csv" in pagina


def test_arquivo_adulterado_na_confirmacao(logado, cadastros):
    resposta = logado.post("/vendas/importar/confirmar", data={"arquivo": "@@@"}, follow_redirects=True)
    assert "Envie o extrato outra vez" in resposta.get_data(as_text=True)
