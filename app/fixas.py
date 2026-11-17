from flask import Blueprint, flash, redirect, render_template, url_for
from sqlalchemy import select

from . import db
from .despesas import preparar_opcoes
from .forms import DespesaFixaForm
from .models import Despesa, DespesaFixa
from .recorrencia import gerar_despesas_fixas, mes_atual as _mes_atual
from .utils import CENTAVO, somar_meses

bp = Blueprint("fixas", __name__, url_prefix="/despesas/fixas")


def _instancias(fixa, desde):
    """Despesas geradas pela fixa com vencimento a partir do mês `desde`."""
    return db.session.scalars(
        select(Despesa).where(Despesa.fixa_id == fixa.id, Despesa.data_compra >= desde)
    ).all()


def _aplicar_alteracoes(fixa, valor_antigo, dia_antigo):
    """Leva as mudanças da fixa para as contas em aberto deste mês em diante.

    Valor e vencimento só mudam onde ainda estavam iguais aos antigos,
    para não desfazer um ajuste feito à mão (ex.: a conta de luz que veio diferente).
    """
    for despesa in _instancias(fixa, _mes_atual()):
        if not despesa.parcelas or any(p.paga for p in despesa.parcelas):
            continue
        parcela = despesa.parcelas[0]
        despesa.descricao = fixa.descricao
        despesa.fornecedor = fixa.fornecedor
        despesa.categoria_id = fixa.categoria_id
        despesa.forma_pagto_id = fixa.forma_pagto_id
        if despesa.valor_total == valor_antigo:
            despesa.valor_total = parcela.valor = fixa.valor
        mes = parcela.vencimento.replace(day=1)
        if parcela.vencimento == fixa.vencimento_em(mes, dia_antigo):
            parcela.vencimento = despesa.data_compra = fixa.vencimento_em(mes)


@bp.route("/", methods=["GET", "POST"])
def lista():
    form = DespesaFixaForm()
    fornecedores = preparar_opcoes(form)

    if form.validate_on_submit():
        fixa = DespesaFixa(inicio=form.inicio.data.replace(day=1))
        _preencher(fixa, form)
        db.session.add(fixa)
        db.session.commit()
        gerar_despesas_fixas()
        flash(f"Despesa fixa “{fixa.descricao}” cadastrada. As contas de cada mês já foram lançadas.", "ok")
        return redirect(url_for(".lista"))

    fixas = db.session.scalars(
        select(DespesaFixa).order_by(DespesaFixa.ativa.desc(), DespesaFixa.dia_vencimento, DespesaFixa.descricao)
    ).all()
    return render_template("fixas/lista.html", form=form, fornecedores=fornecedores, fixas=fixas)


def _preencher(fixa, form):
    fixa.descricao = form.descricao.data.strip()
    fixa.fornecedor = (form.fornecedor.data or "").strip() or None
    fixa.valor = form.valor.data.quantize(CENTAVO)
    fixa.dia_vencimento = form.dia_vencimento.data
    fixa.categoria_id = form.categoria_id.data
    fixa.forma_pagto_id = form.forma_pagto_id.data


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    fixa = db.get_or_404(DespesaFixa, id)
    form = DespesaFixaForm(obj=fixa)
    del form.inicio  # o mês de início não muda depois de cadastrada
    fornecedores = preparar_opcoes(form, fixa)

    if form.validate_on_submit():
        valor_antigo, dia_antigo = fixa.valor, fixa.dia_vencimento
        _preencher(fixa, form)
        _aplicar_alteracoes(fixa, valor_antigo, dia_antigo)
        db.session.commit()
        flash("Despesa fixa atualizada. As contas em aberto deste mês em diante foram ajustadas.", "ok")
        return redirect(url_for(".lista"))

    return render_template("fixas/editar.html", form=form, fornecedores=fornecedores, fixa=fixa)


@bp.post("/<int:id>/excluir")
def excluir(id):
    """Apaga a fixa e as contas dela ainda não pagas; as pagas viram despesas comuns (o dinheiro já saiu)."""
    fixa = db.get_or_404(DespesaFixa, id)
    descricao, removidas, mantidas = fixa.descricao, 0, 0
    for despesa in list(fixa.despesas):
        if any(p.paga for p in despesa.parcelas):
            despesa.fixa = None
            mantidas += 1
        else:
            db.session.delete(despesa)
            removidas += 1
    db.session.delete(fixa)
    db.session.commit()

    texto = f"Despesa fixa “{descricao}” excluída, com {removidas} conta(s) em aberto."
    if mantidas:
        texto += f" {mantidas} conta(s) já paga(s) ficaram no histórico."
    flash(texto, "ok")
    return redirect(url_for(".lista"))


@bp.post("/<int:id>/alternar")
def alternar(id):
    fixa = db.get_or_404(DespesaFixa, id)
    mes_atual = _mes_atual()

    if fixa.ativa:
        # Remove as contas futuras ainda não pagas; a deste mês continua
        removidas = 0
        for despesa in _instancias(fixa, somar_meses(mes_atual, 1)):
            if not any(p.paga for p in despesa.parcelas):
                db.session.delete(despesa)
                removidas += 1
        fixa.ativa = False
        fixa.gerado_ate = mes_atual
        db.session.commit()
        flash(f"“{fixa.descricao}” desativada. {removidas} conta(s) futura(s) removida(s).", "ok")
    else:
        # Volta a lançar a partir deste mês, sem preencher os meses em que ficou parada
        fixa.ativa = True
        fixa.gerado_ate = somar_meses(mes_atual, -1)
        db.session.commit()
        gerar_despesas_fixas()
        flash(f"“{fixa.descricao}” reativada.", "ok")

    return redirect(url_for(".lista"))
