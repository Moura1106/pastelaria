"""Dados 100% fictícios para demonstrar o sistema (comando `flask dados-demo`).

Tudo aqui é inventado: nomes, fornecedores, valores e IDs de extrato. Os números são gerados
com uma semente fixa, então o resultado é o mesmo em qualquer máquina.
"""
import random
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select

from . import db
from .models import Categoria, Despesa, DespesaFixa, FormaPagamento, Parcela, Receita, Usuario
from .recorrencia import gerar_despesas_fixas
from .utils import CENTAVO, somar_meses

EMAIL_DEMO = "demo@exemplo.com"
SENHA_DEMO = "demo12345"

# Taxas fictícias, em %
TAXAS = {"Dinheiro": "0", "Pix": "0.99", "Débito": "1.99", "Crédito à vista": "4.49", "Crédito parcelado": "5.99"}

FORNECEDORES = {
    "Insumos": ["Atacado Boa Massa", "Hortifruti Central"],
    "Carnes": ["Frigorífico Exemplo"],
    "Bebidas": ["Distribuidora Gelada"],
    "Gás e carvão": ["Gás e Carvão Ltda"],
    "Embalagens": ["Embalagens Modelo"],
}

CABECALHO_CSV = ("OPERATION_DATETIME;RELEASE_DATETIME;MOVEMENT_TYPE;PAYMENT_ID;LOCAL;CHARGE_METHOD;"
                 "PAYMENT_METHOD_DETAIL;PAYMENT_METHOD;GROSS_VALUE;SALES_DISCOUNTS;NET;SEGMENTATION_DETAIL")


def _dinheiro(valor):
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _virgula(valor):
    return f"{valor:.2f}".replace(".", ",")


def banco_esta_vazio():
    return all(
        db.session.scalar(select(func.count(modelo.id))) == 0
        for modelo in (Usuario, Receita, Despesa, DespesaFixa)
    )


def gerar_dados_demo(hoje=None, dias=75):
    """Cadastra usuário, cadastros básicos, vendas, despesas, parcelas e contas fixas fictícias."""
    hoje = hoje or date.today()
    sorteio = random.Random(42)

    usuario = Usuario(nome="Usuária Demo", email=EMAIL_DEMO)
    usuario.definir_senha(SENHA_DEMO)
    db.session.add(usuario)

    categorias = {}
    if db.session.scalar(select(func.count(Categoria.id))) == 0:
        from .comandos import CATEGORIAS_DESPESA, CATEGORIAS_RECEITA
        db.session.add_all(Categoria(nome=n, tipo="despesa") for n in CATEGORIAS_DESPESA)
        db.session.add_all(Categoria(nome=n, tipo="receita") for n in CATEGORIAS_RECEITA)
    if db.session.scalar(select(func.count(FormaPagamento.id))) == 0:
        db.session.add_all(FormaPagamento(nome=n, taxa_padrao=Decimal(t)) for n, t in TAXAS.items())
    db.session.flush()
    for c in db.session.scalars(select(Categoria)):
        categorias[(c.nome, c.tipo)] = c
    formas = {f.nome: f for f in db.session.scalars(select(FormaPagamento))}

    # --- Vendas: de 8 a 16 por dia, fechando às segundas ---
    pesos = [("Dinheiro", 25), ("Pix", 30), ("Débito", 20), ("Crédito à vista", 25)]
    nomes, valores_peso = zip(*pesos)
    for d in range(dias, -1, -1):
        dia = hoje - timedelta(days=d)
        if dia.weekday() == 0:
            continue
        for _ in range(sorteio.randint(8, 16)):
            forma = formas[sorteio.choices(nomes, weights=valores_peso)[0]]
            bruto = _dinheiro(sorteio.choice([8, 10, 12, 15, 18, 20, 25, 30, 45, 60]) + sorteio.choice([0, 0, 0.5]))
            taxa = _dinheiro(bruto * forma.taxa_padrao / 100)
            db.session.add(Receita(
                data=dia, descricao="Venda do dia", categoria=categorias[("Vendas", "receita")], forma_pagto=forma,
                valor_bruto=bruto, taxa=taxa, valor_liquido=bruto - taxa, origem="manual", usuario=usuario,
            ))

    # --- Despesas avulsas: à vista e parceladas ---
    categorias_compra = list(FORNECEDORES)
    for d in range(dias, 0, -1):
        dia = hoje - timedelta(days=d)
        if dia.weekday() not in (1, 4):  # compras às terças e sextas
            continue
        nome_categoria = sorteio.choice(categorias_compra)
        parcelado = sorteio.random() < 0.3
        forma = formas["Crédito parcelado" if parcelado else sorteio.choice(["Dinheiro", "Pix", "Débito"])]
        despesa = Despesa(
            data_compra=dia, descricao=f"Compra de {nome_categoria.lower()}",
            fornecedor=sorteio.choice(FORNECEDORES[nome_categoria]),
            categoria=categorias[(nome_categoria, "despesa")], forma_pagto=forma,
            valor_total=_dinheiro(sorteio.randint(80, 600)), num_parcelas=3 if parcelado else 1, usuario=usuario,
        )
        despesa.gerar_parcelas(dia if not parcelado else somar_meses(dia, 1))
        for parcela in despesa.parcelas:  # o que venceu há mais de 3 dias foi pago; o resto fica em aberto
            if parcela.vencimento < hoje - timedelta(days=3):
                parcela.paga, parcela.data_pagamento = True, parcela.vencimento
        db.session.add(despesa)

    # --- Contas fixas (geradas mês a mês pelo mesmo código que o sistema usa de verdade) ---
    inicio = somar_meses(hoje.replace(day=1), -2)
    for descricao, fornecedor, categoria, valor, dia_venc in [
        ("Aluguel do ponto", "Imobiliária Exemplo", "Aluguel", 1800, 5),
        ("Conta de energia", "Companhia de Energia Exemplo", "Energia", 420, 15),
        ("Internet", "Provedor Exemplo", "Internet e telefone", 120, 10),
    ]:
        db.session.add(DespesaFixa(
            descricao=descricao, fornecedor=fornecedor, categoria=categorias[(categoria, "despesa")],
            forma_pagto=formas["Pix"], valor=_dinheiro(valor), dia_vencimento=dia_venc, inicio=inicio,
        ))
    db.session.commit()
    gerar_despesas_fixas()

    for parcela in db.session.scalars(select(Parcela).join(Despesa).where(Despesa.fixa_id.is_not(None))):
        if parcela.vencimento < hoje - timedelta(days=3):
            parcela.paga, parcela.data_pagamento = True, parcela.vencimento
    db.session.commit()
    return usuario


def gerar_csv_demo(destino, hoje=None):
    """Escreve um extrato falso no formato do Mercado Pago, para testar a tela de importação."""
    hoje = hoje or date.today()
    sorteio = random.Random(7)
    meios = [
        ("Point", "Cartão de débito", "Visa débito", Decimal("1.99")),
        ("Point", "Cartão de crédito", "Master", Decimal("4.49")),
        ("Código QR", "Pix", "", Decimal("0.99")),
    ]
    linhas, pagamento_id = [], 9_000_001
    for d in (3, 2, 1):
        dia = hoje - timedelta(days=d)
        for _ in range(sorteio.randint(6, 10)):
            momento = datetime.combine(dia, time(sorteio.randint(11, 21), sorteio.randint(0, 59), sorteio.randint(0, 59)))
            meio, detalhe, metodo, taxa_pct = sorteio.choice(meios)
            bruto = _dinheiro(sorteio.choice([10, 15, 20, 25, 30, 40, 55]))
            liquido = bruto - _dinheiro(bruto * taxa_pct / 100)
            data_txt = momento.strftime("%d-%m-%Y %H:%M:%S")
            linhas.append(";".join([
                data_txt, data_txt, "Pagamento", str(pagamento_id), "Loja Demo", meio, detalhe, metodo,
                _virgula(bruto), _virgula(liquido - bruto), _virgula(liquido), "QR" if meio == "Código QR" else "null",
            ]))
            pagamento_id += 1
    with open(destino, "w", encoding="utf-8", newline="") as arq:
        arq.write(CABECALHO_CSV + "\n" + "\n".join(linhas) + "\n")
    return len(linhas)
