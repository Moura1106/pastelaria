from datetime import date
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload
from wtforms.fields.choices import SelectChoice

from . import db
from .auth import destino_seguro
from .forms import MAX_PARCELAS, OPCOES_PARCELAS, DespesaForm
from .models import Categoria, Despesa, FormaPagamento, Parcela
from .recorrencia import gerar_despesas_fixas
from .utils import CENTAVO, brl, mes_da_url, somar_meses

bp = Blueprint("despesas", __name__, url_prefix="/despesas")


def preparar_opcoes(form, registro=None):
    """Preenche as opções dos selects e devolve os fornecedores já usados (para autocompletar).

    Serve para despesas e despesas fixas; `registro` é o item em edição, se houver.
    """
    categoria_atual = registro.categoria_id if registro else None
    forma_atual = registro.forma_pagto_id if registro else None

    categorias = db.session.scalars(
        select(Categoria)
        .where(Categoria.tipo == "despesa", or_(Categoria.ativa, Categoria.id == categoria_atual))
        .order_by(Categoria.nome)
    ).all()
    form.categoria_id.choices = [SelectChoice(0, "Escolha...")] + [SelectChoice(c.id, c.nome) for c in categorias]

    formas = db.session.scalars(
        select(FormaPagamento)
        .where(or_(FormaPagamento.ativa, FormaPagamento.id == forma_atual))
        .order_by(FormaPagamento.id)
    ).all()
    form.forma_pagto_id.choices = [SelectChoice(f.id, f.nome) for f in formas]

    # Compras antigas lançadas em mais de 50x continuam editáveis
    parcelas_atuais = getattr(registro, "num_parcelas", 1)
    if hasattr(form, "num_parcelas") and parcelas_atuais > MAX_PARCELAS:
        form.num_parcelas.choices = [*OPCOES_PARCELAS, SelectChoice(parcelas_atuais, f"{parcelas_atuais}x")]

    return db.session.scalars(
        select(Despesa.fornecedor).where(Despesa.fornecedor.is_not(None)).distinct().order_by(Despesa.fornecedor)
    ).all()


def _vencimento_valido(form):
    if form.num_parcelas.data > 1 and not form.primeiro_vencimento.data:
        form.primeiro_vencimento.errors = [*form.primeiro_vencimento.errors,
                                           "Informe o vencimento da 1ª parcela."]
        return False
    return True


def _preencher(despesa, form):
    despesa.descricao = form.descricao.data.strip()
    despesa.fornecedor = (form.fornecedor.data or "").strip() or None
    despesa.valor_total = form.valor_total.data.quantize(CENTAVO)
    despesa.data_compra = form.data_compra.data
    despesa.categoria_id = form.categoria_id.data
    despesa.forma_pagto_id = form.forma_pagto_id.data
    despesa.num_parcelas = form.num_parcelas.data


def _resumo_parcelas(parcelas, hoje):
    return {
        "total": sum((p.valor for p in parcelas), Decimal(0)),
        "pago": sum((p.valor for p in parcelas if p.paga), Decimal(0)),
        "a_pagar": sum((p.valor for p in parcelas if not p.paga), Decimal(0)),
        "vencido": sum((p.valor for p in parcelas if not p.paga and p.vencimento < hoje), Decimal(0)),
    }


@bp.route("/")
def lista():
    hoje = date.today()
    inicio = mes_da_url(request.args.get("mes"))
    fim = somar_meses(inicio, 1)
    ver = "compras" if request.args.get("ver") == "compras" else "contas"
    gerar_despesas_fixas(ate=inicio)
    contexto = {"mes": inicio, "anterior": somar_meses(inicio, -1), "proximo": fim, "ver": ver, "hoje": hoje}

    if ver == "compras":
        despesas = db.session.scalars(
            select(Despesa)
            .options(joinedload(Despesa.categoria), joinedload(Despesa.forma_pagto))
            .where(Despesa.data_compra >= inicio, Despesa.data_compra < fim)
            .order_by(Despesa.data_compra.desc(), Despesa.id.desc())
        ).all()
        contexto.update(despesas=despesas, total_compras=sum((d.valor_total for d in despesas), Decimal(0)))
    else:
        parcelas = db.session.scalars(
            select(Parcela)
            .options(joinedload(Parcela.despesa).joinedload(Despesa.categoria))
            .where(Parcela.vencimento >= inicio, Parcela.vencimento < fim)
            .order_by(Parcela.paga, Parcela.vencimento, Parcela.id)
        ).all()
        # Parcelas esquecidas em meses anteriores ao que está sendo visto
        atrasadas_antes = db.session.execute(
            select(func.count(Parcela.id), func.min(Parcela.vencimento))
            .where(Parcela.paga.is_(False), Parcela.vencimento < inicio)
        ).one()
        contexto.update(parcelas=parcelas, totais=_resumo_parcelas(parcelas, hoje), atrasadas_antes=atrasadas_antes)

    return render_template("despesas/lista.html", **contexto)


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    form = DespesaForm()
    fornecedores = preparar_opcoes(form)

    if form.validate_on_submit() and _vencimento_valido(form):
        despesa = Despesa(usuario_id=current_user.id)
        _preencher(despesa, form)
        despesa.gerar_parcelas(form.primeiro_vencimento.data or despesa.data_compra)
        if despesa.num_parcelas == 1 and form.ja_paga.data:
            parcela = despesa.parcelas[0]
            parcela.paga = True
            parcela.data_pagamento = min(parcela.vencimento, date.today())
        db.session.add(despesa)
        db.session.commit()

        texto = brl(despesa.valor_total)
        if despesa.num_parcelas > 1:
            texto += f" em {despesa.num_parcelas}x"
        flash(f"Despesa “{despesa.descricao}” de {texto} lançada.", "ok")
        if "outra" in request.form:
            return redirect(url_for(".nova"))
        return redirect(url_for(".detalhe", id=despesa.id))

    return render_template("despesas/form.html", form=form, fornecedores=fornecedores,
                           titulo="Lançar despesa", despesa=None)


@bp.route("/<int:id>")
def detalhe(id):
    despesa = db.get_or_404(Despesa, id)
    return render_template("despesas/detalhe.html", despesa=despesa, hoje=date.today(),
                           totais=_resumo_parcelas(despesa.parcelas, date.today()))


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    despesa = db.get_or_404(Despesa, id)
    form = DespesaForm(obj=despesa)
    del form.ja_paga  # na edição, o pagamento é marcado parcela por parcela
    fornecedores = preparar_opcoes(form, despesa)
    vencimento_atual = despesa.parcelas[0].vencimento if despesa.parcelas else despesa.data_compra
    if request.method == "GET":
        form.primeiro_vencimento.data = vencimento_atual

    if form.validate_on_submit() and _vencimento_valido(form):
        antes = (despesa.valor_total, despesa.num_parcelas, vencimento_atual)
        _preencher(despesa, form)
        vencimento = form.primeiro_vencimento.data or despesa.data_compra
        if (despesa.valor_total, despesa.num_parcelas, vencimento) != antes:
            # Recalcula as parcelas, mantendo marcadas as que já tinham sido pagas
            pagas = {p.numero: p.data_pagamento for p in despesa.parcelas if p.paga}
            despesa.gerar_parcelas(vencimento)
            for parcela in despesa.parcelas:
                if parcela.numero in pagas:
                    parcela.paga, parcela.data_pagamento = True, pagas[parcela.numero]
        db.session.commit()
        flash("Despesa atualizada.", "ok")
        return redirect(url_for(".detalhe", id=despesa.id))

    return render_template("despesas/form.html", form=form, fornecedores=fornecedores,
                           titulo="Editar despesa", despesa=despesa)


@bp.post("/<int:id>/excluir")
def excluir(id):
    despesa = db.get_or_404(Despesa, id)
    mes, descricao = despesa.data_compra.strftime("%Y-%m"), despesa.descricao
    db.session.delete(despesa)
    db.session.commit()
    flash(f"Despesa “{descricao}” excluída, com todas as parcelas.", "ok")
    return redirect(url_for(".lista", mes=mes, ver="compras"))


@bp.post("/parcelas/<int:id>/pagar")
def pagar_parcela(id):
    parcela = db.get_or_404(Parcela, id)
    parcela.paga = not parcela.paga
    parcela.data_pagamento = date.today() if parcela.paga else None
    db.session.commit()

    nome = parcela.despesa.descricao
    if parcela.despesa.num_parcelas > 1:
        nome += f" ({parcela.numero}/{parcela.despesa.num_parcelas})"
    flash(f"{nome}: {'marcada como paga' if parcela.paga else 'voltou para a pagar'}.", "ok")
    return redirect(destino_seguro(request.form.get("voltar")))
