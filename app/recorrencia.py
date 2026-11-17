from datetime import date

from sqlalchemy import select

from . import db
from .models import Despesa, DespesaFixa
from .utils import somar_meses

# Quantos meses à frente (contando o atual) as contas fixas já ficam lançadas,
# para aparecerem em "Contas a pagar nos próximos meses"
HORIZONTE_MESES = 6


def mes_atual():
    return date.today().replace(day=1)


def gerar_despesas_fixas(ate=None):
    """Lança as contas fixas que ainda faltam até o horizonte (ou até o mês `ate`, se for depois).

    É chamada ao abrir as telas que mostram contas; não repete o que já foi lançado.
    """
    limite = somar_meses(mes_atual(), HORIZONTE_MESES - 1)
    if ate and ate.replace(day=1) > limite:
        limite = ate.replace(day=1)

    criou = False
    for fixa in db.session.scalars(select(DespesaFixa).where(DespesaFixa.ativa)):
        mes = max(fixa.inicio, somar_meses(fixa.gerado_ate, 1)) if fixa.gerado_ate else fixa.inicio
        while mes <= limite:
            ja_existe = db.session.scalar(
                select(Despesa.id).where(Despesa.fixa_id == fixa.id, Despesa.data_compra >= mes,
                                         Despesa.data_compra < somar_meses(mes, 1))
            )
            if not ja_existe:
                db.session.add(fixa.nova_despesa(mes))
            fixa.gerado_ate = mes
            criou = True
            mes = somar_meses(mes, 1)
    if criou:
        db.session.commit()
