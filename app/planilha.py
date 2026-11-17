"""Gera a planilha Excel (.xlsx) de um período, para conferência e backup manual."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from . import db
from .models import Despesa, Parcela, Receita
from .utils import mes_ano, somar_meses

MOEDA = '"R$" #,##0.00'
DATA = "DD/MM/YYYY"
CABECALHO = Font(bold=True, color="FFFFFF")
FUNDO_CABECALHO = PatternFill("solid", fgColor="B45309")


def _aba(wb, titulo, colunas, linhas, formatos):
    """Cria uma aba com cabeçalho, filtros e larguras. `formatos` mapeia índice da coluna -> formato."""
    ws = wb.create_sheet(titulo)
    ws.append(colunas)
    for celula in ws[1]:
        celula.font, celula.fill = CABECALHO, FUNDO_CABECALHO
    for linha in linhas:
        ws.append(linha)
    for indice, formato in formatos.items():
        for (celula,) in ws.iter_rows(min_row=2, min_col=indice + 1, max_col=indice + 1):
            celula.number_format = formato
    for i, nome in enumerate(colunas, start=1):
        maior = max([len(nome)] + [len(str(c.value or "")) for (c,) in ws.iter_rows(min_row=2, min_col=i, max_col=i)])
        ws.column_dimensions[get_column_letter(i)].width = min(max(maior + 2, 12), 45)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    return ws


def gerar_planilha(inicio, fim):
    receitas = db.session.scalars(
        select(Receita).options(joinedload(Receita.forma_pagto), joinedload(Receita.categoria))
        .where(Receita.data >= inicio, Receita.data < fim).order_by(Receita.data, Receita.id)
    ).all()
    parcelas = db.session.scalars(
        select(Parcela).options(joinedload(Parcela.despesa).joinedload(Despesa.categoria),
                                joinedload(Parcela.despesa).joinedload(Despesa.forma_pagto))
        .where(Parcela.vencimento >= inicio, Parcela.vencimento < fim).order_by(Parcela.vencimento, Parcela.id)
    ).all()
    compras = db.session.scalars(
        select(Despesa).options(joinedload(Despesa.categoria), joinedload(Despesa.forma_pagto))
        .where(Despesa.data_compra >= inicio, Despesa.data_compra < fim).order_by(Despesa.data_compra, Despesa.id)
    ).all()

    wb = Workbook()
    wb.remove(wb.active)

    resumo = []
    mes = inicio
    while mes < fim:
        proximo = somar_meses(mes, 1)
        do_mes = [r for r in receitas if mes <= r.data < proximo]
        saidas = sum(p.valor for p in parcelas if mes <= p.vencimento < proximo)
        liquido = sum(r.valor_liquido for r in do_mes)
        resumo.append([mes_ano(mes).capitalize(), sum(r.valor_bruto for r in do_mes),
                       sum(r.taxa for r in do_mes), liquido, saidas, liquido - saidas])
        mes = proximo
    _aba(wb, "Resumo", ["Mês", "Vendido", "Taxas", "Entradas (líquido)", "Saídas", "Resultado"],
         resumo, {1: MOEDA, 2: MOEDA, 3: MOEDA, 4: MOEDA, 5: MOEDA})

    _aba(wb, "Vendas", ["Data", "Valor", "Forma de pagamento", "Taxa", "Líquido", "Categoria", "Observação"],
         [[r.data, r.valor_bruto, r.forma_pagto.nome, r.taxa, r.valor_liquido,
           r.categoria.nome if r.categoria else "", r.descricao or ""] for r in receitas],
         {0: DATA, 1: MOEDA, 3: MOEDA, 4: MOEDA})

    _aba(wb, "Contas",
         ["Vencimento", "Descrição", "Parcela", "Categoria", "Fornecedor", "Forma de pagamento", "Valor",
          "Situação", "Pago em"],
         [[p.vencimento, p.despesa.descricao, f"{p.numero}/{p.despesa.num_parcelas}", p.despesa.categoria.nome,
           p.despesa.fornecedor or "", p.despesa.forma_pagto.nome, p.valor,
           "Paga" if p.paga else "A pagar", p.data_pagamento] for p in parcelas],
         {0: DATA, 6: MOEDA, 8: DATA})

    _aba(wb, "Compras",
         ["Data", "Descrição", "Categoria", "Fornecedor", "Forma de pagamento", "Valor total", "Parcelas"],
         [[d.data_compra, d.descricao, d.categoria.nome, d.fornecedor or "", d.forma_pagto.nome,
           d.valor_total, d.num_parcelas] for d in compras],
         {0: DATA, 5: MOEDA})

    arquivo = BytesIO()
    wb.save(arquivo)
    arquivo.seek(0)
    return arquivo
