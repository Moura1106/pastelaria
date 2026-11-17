from datetime import date

from flask import Blueprint, render_template
from sqlalchemy import func, select

from . import db
from .models import Parcela, Receita
from .recorrencia import gerar_despesas_fixas
from .utils import somar_meses

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    gerar_despesas_fixas()
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    quantidade, liquido = db.session.execute(
        select(func.count(Receita.id), func.coalesce(func.sum(Receita.valor_liquido), 0))
        .where(Receita.data == hoje)
    ).one()

    a_pagar_mes = db.session.scalar(
        select(func.coalesce(func.sum(Parcela.valor), 0))
        .where(Parcela.paga.is_(False), Parcela.vencimento >= inicio_mes,
               Parcela.vencimento < somar_meses(inicio_mes, 1))
    )
    vencidas, valor_vencido = db.session.execute(
        select(func.count(Parcela.id), func.coalesce(func.sum(Parcela.valor), 0))
        .where(Parcela.paga.is_(False), Parcela.vencimento < hoje)
    ).one()

    return render_template(
        "index.html",
        hoje={"quantidade": quantidade, "liquido": liquido},
        contas={"a_pagar_mes": a_pagar_mes, "vencidas": vencidas, "valor_vencido": valor_vencido},
    )


@bp.route("/ajustes")
def ajustes():
    return render_template("ajustes.html")
