from datetime import date
from decimal import Decimal

from flask import Blueprint, render_template, request, send_file
from sqlalchemy import func, select

from . import db
from .models import Categoria, Despesa, Parcela, Receita
from .planilha import gerar_planilha
from .recorrencia import gerar_despesas_fixas
from .utils import mes_da_url, somar_meses

bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")

# Regime de caixa: uma compra parcelada pesa em cada mês pelo valor da parcela que vence nele.
MESES_COMPARATIVO = 6
MESES_COMPROMISSOS = 6


def _dec(valor):
    return Decimal(str(valor or 0))


def _entradas(inicio, fim):
    """(líquido, bruto, taxas) das vendas no período."""
    linha = db.session.execute(
        select(func.sum(Receita.valor_liquido), func.sum(Receita.valor_bruto), func.sum(Receita.taxa))
        .where(Receita.data >= inicio, Receita.data < fim)
    ).one()
    return tuple(_dec(v) for v in linha)


def _saidas(inicio, fim, somente_abertas=False):
    """(total, quantidade) das parcelas que vencem no período."""
    consulta = select(func.sum(Parcela.valor), func.count(Parcela.id)).where(
        Parcela.vencimento >= inicio, Parcela.vencimento < fim
    )
    if somente_abertas:
        consulta = consulta.where(Parcela.paga.is_(False))
    total, quantidade = db.session.execute(consulta).one()
    return _dec(total), quantidade


@bp.route("/planilha")
def planilha():
    """Baixa o Excel do mês (?mes=2026-10) ou do ano inteiro (?ano=2026)."""
    ano = request.args.get("ano", type=int)
    if ano and 2000 <= ano <= 2100:
        inicio, fim, nome = date(ano, 1, 1), date(ano + 1, 1, 1), f"caixa-{ano}.xlsx"
    else:
        inicio = mes_da_url(request.args.get("mes"))
        fim, nome = somar_meses(inicio, 1), f"caixa-{inicio:%Y-%m}.xlsx"
    gerar_despesas_fixas(ate=somar_meses(fim, -1))
    return send_file(gerar_planilha(inicio, fim), as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/")
def index():
    hoje = date.today()
    inicio = mes_da_url(request.args.get("mes"))
    fim = somar_meses(inicio, 1)
    gerar_despesas_fixas(ate=inicio)

    liquido, bruto, taxas = _entradas(inicio, fim)
    saidas, _ = _saidas(inicio, fim)
    a_pagar_no_mes, _ = _saidas(inicio, fim, somente_abertas=True)

    total_categoria = func.sum(Parcela.valor).label("total")
    categorias = [
        {"nome": nome, "total": _dec(total)}
        for nome, total in db.session.execute(
            select(Categoria.nome, total_categoria)
            .join(Despesa, Parcela.despesa_id == Despesa.id)
            .join(Categoria, Despesa.categoria_id == Categoria.id)
            .where(Parcela.vencimento >= inicio, Parcela.vencimento < fim)
            .group_by(Categoria.id, Categoria.nome)
            .order_by(total_categoria.desc())
        )
    ]

    comparativo = []
    for i in range(MESES_COMPARATIVO - 1, -1, -1):
        mes = somar_meses(inicio, -i)
        entradas = _entradas(mes, somar_meses(mes, 1))[0]
        saidas_mes = _saidas(mes, somar_meses(mes, 1))[0]
        comparativo.append({"mes": mes, "entradas": entradas, "saidas": saidas_mes,
                            "resultado": entradas - saidas_mes})

    # Compromissos sempre a partir do mês atual, independentemente do mês escolhido
    compromissos = []
    for i in range(MESES_COMPROMISSOS):
        mes = somar_meses(hoje.replace(day=1), i)
        total, quantidade = _saidas(mes, somar_meses(mes, 1), somente_abertas=True)
        compromissos.append({"mes": mes, "total": total, "quantidade": quantidade})

    return render_template(
        "relatorios/index.html",
        mes=inicio,
        anterior=somar_meses(inicio, -1),
        proximo=fim,
        resumo={"entradas": liquido, "bruto": bruto, "taxas": taxas, "saidas": saidas,
                "a_pagar": a_pagar_no_mes, "resultado": liquido - saidas},
        categorias=categorias,
        maior_categoria=max((c["total"] for c in categorias), default=Decimal(0)),
        comparativo=comparativo,
        maior_comparativo=max((max(m["entradas"], m["saidas"]) for m in comparativo), default=Decimal(0)),
        compromissos=compromissos,
        maior_compromisso=max((c["total"] for c in compromissos), default=Decimal(0)),
    )
