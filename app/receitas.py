import base64
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from itertools import groupby

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from wtforms.fields.choices import SelectChoice

from . import db
from .forms import ImportarExtratoForm, ReceitaForm
from .importacao import TIPOS, ExtratoInvalido, forma_sugerida, ler_extrato
from .models import Categoria, FormaPagamento, Receita
from .utils import CENTAVO, brl, mes_da_url, somar_meses

bp = Blueprint("receitas", __name__, url_prefix="/vendas")


def _preparar_form(form, receita=None):
    """Preenche as opções dos selects. Itens desativados só aparecem se já estiverem no lançamento."""
    forma_atual = receita.forma_pagto_id if receita else None
    categoria_atual = receita.categoria_id if receita else None

    formas = db.session.scalars(
        select(FormaPagamento)
        .where(or_(FormaPagamento.ativa, FormaPagamento.id == forma_atual))
        .order_by(FormaPagamento.id)
    ).all()
    form.forma_pagto_id.choices = [
        SelectChoice(f.id, f.nome, render_kw={"data-taxa": str(f.taxa_padrao)}) for f in formas
    ]

    categorias = db.session.scalars(
        select(Categoria)
        .where(Categoria.tipo == "receita", or_(Categoria.ativa, Categoria.id == categoria_atual))
        .order_by(Categoria.id)
    ).all()
    form.categoria_id.choices = [SelectChoice(c.id, c.nome) for c in categorias]
    return formas, categorias


def _preencher(receita, form):
    """Copia o formulário para a receita. Sem taxa informada, usa a taxa padrão da forma de pagamento."""
    bruto = form.valor_bruto.data.quantize(CENTAVO)
    taxa = form.taxa.data
    if taxa is None:
        forma = db.session.get(FormaPagamento, form.forma_pagto_id.data)
        taxa = bruto * forma.taxa_padrao / 100
    taxa = Decimal(taxa).quantize(CENTAVO, rounding=ROUND_HALF_UP)

    if taxa > bruto:
        form.taxa.errors = [*form.taxa.errors, "A taxa não pode ser maior que o valor da venda."]
        return False

    receita.data = form.data.data
    receita.valor_bruto = bruto
    receita.taxa = taxa
    receita.valor_liquido = bruto - taxa
    receita.forma_pagto_id = form.forma_pagto_id.data
    receita.categoria_id = form.categoria_id.data
    receita.descricao = (form.descricao.data or "").strip() or None
    return True


@bp.route("/")
def lista():
    inicio = mes_da_url(request.args.get("mes"))
    fim = somar_meses(inicio, 1)
    receitas = db.session.scalars(
        select(Receita)
        .options(joinedload(Receita.forma_pagto), joinedload(Receita.categoria))
        .where(Receita.data >= inicio, Receita.data < fim)
        .order_by(Receita.data.desc(), Receita.id.desc())
    ).all()

    totais = {
        "bruto": sum((r.valor_bruto for r in receitas), Decimal(0)),
        "taxa": sum((r.taxa for r in receitas), Decimal(0)),
        "liquido": sum((r.valor_liquido for r in receitas), Decimal(0)),
        "quantidade": len(receitas),
    }

    por_forma = defaultdict(lambda: {"bruto": Decimal(0), "taxa": Decimal(0), "liquido": Decimal(0), "quantidade": 0})
    for r in receitas:
        item = por_forma[r.forma_pagto.nome]
        item["bruto"] += r.valor_bruto
        item["taxa"] += r.taxa
        item["liquido"] += r.valor_liquido
        item["quantidade"] += 1

    dias = []
    for dia, itens in groupby(receitas, key=lambda r: r.data):
        itens = list(itens)
        dias.append({"data": dia, "itens": itens, "total": sum((r.valor_liquido for r in itens), Decimal(0))})

    return render_template(
        "receitas/lista.html",
        mes=inicio,
        anterior=somar_meses(inicio, -1),
        proximo=fim,
        totais=totais,
        por_forma=sorted(por_forma.items(), key=lambda par: -par[1]["bruto"]),
        dias=dias,
    )


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    form = ReceitaForm()
    _, categorias = _preparar_form(form)

    if request.method == "GET":
        # Depois de "Salvar e lançar outra", mantém a data e a forma de pagamento
        if request.args.get("data"):
            try:
                form.data.data = date.fromisoformat(request.args["data"])
            except ValueError:
                pass
        form.forma_pagto_id.data = request.args.get("forma", type=int)
        vendas = next((c for c in categorias if c.nome == "Vendas"), categorias[0] if categorias else None)
        form.categoria_id.data = vendas.id if vendas else None

    if form.validate_on_submit():
        receita = Receita(origem="manual", usuario_id=current_user.id)
        if _preencher(receita, form):
            db.session.add(receita)
            db.session.commit()
            flash(f"Venda de {brl(receita.valor_bruto)} lançada.", "ok")
            if "outra" in request.form:
                return redirect(url_for(".nova", data=receita.data.isoformat(), forma=receita.forma_pagto_id))
            return redirect(url_for(".lista", mes=receita.data.strftime("%Y-%m")))

    return render_template("receitas/form.html", form=form, titulo="Lançar venda", receita=None)


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    receita = db.get_or_404(Receita, id)
    form = ReceitaForm(obj=receita)
    _preparar_form(form, receita)

    if form.validate_on_submit() and _preencher(receita, form):
        db.session.commit()
        flash("Venda atualizada.", "ok")
        return redirect(url_for(".lista", mes=receita.data.strftime("%Y-%m")))

    return render_template("receitas/form.html", form=form, titulo="Editar venda", receita=receita)


@bp.post("/<int:id>/excluir")
def excluir(id):
    receita = db.get_or_404(Receita, id)
    mes, valor = receita.data.strftime("%Y-%m"), receita.valor_bruto
    db.session.delete(receita)
    db.session.commit()
    flash(f"Venda de {brl(valor)} excluída.", "ok")
    return redirect(url_for(".lista", mes=mes))


# ---------- Importação do extrato do Mercado Pago ----------

def _formas_ativas():
    return db.session.scalars(select(FormaPagamento).where(FormaPagamento.ativa).order_by(FormaPagamento.id)).all()


def _ja_importadas(extrato):
    ids = [v.id_externo for v in extrato.vendas]
    if not ids:
        return set()
    return set(db.session.scalars(select(Receita.id_externo).where(Receita.id_externo.in_(ids))))


def _somar(vendas):
    return {
        "quantidade": len(vendas),
        "bruto": sum((v.bruto for v in vendas), Decimal(0)),
        "taxa": sum((v.taxa for v in vendas), Decimal(0)),
        "liquido": sum((v.liquido for v in vendas), Decimal(0)),
    }


def _previa(extrato, arquivo, escolhas=None, erro=None):
    """Mostra o que vai entrar. O arquivo volta escondido no formulário e é lido de novo ao confirmar."""
    formas = _formas_ativas()
    existentes = _ja_importadas(extrato)
    novas = [v for v in extrato.vendas if v.id_externo not in existentes]
    escolhas = escolhas or {}

    tipos = []
    for tipo in TIPOS:
        do_tipo = [v for v in novas if v.tipo == tipo]
        if do_tipo:
            sugerida = escolhas.get(tipo) or getattr(forma_sugerida(tipo, formas), "id", None)
            tipos.append({"chave": tipo, "nome": TIPOS[tipo], "forma_id": sugerida, **_somar(do_tipo)})

    dias = []
    for dia, itens in groupby(extrato.vendas, key=lambda v: v.data):
        itens = [(v, v.id_externo in existentes) for v in itens]
        dias.append({"data": dia, "itens": itens, "total": sum((v.liquido for v, repetida in itens if not repetida), Decimal(0))})

    return render_template(
        "receitas/importar_previa.html",
        arquivo=arquivo, formas=formas, tipos=tipos, dias=dias, totais=_somar(novas),
        repetidas=len(existentes), ignoradas=extrato.ignoradas, tipos_nomes=TIPOS, erro=erro,
    )


@bp.route("/importar", methods=["GET", "POST"])
def importar():
    form = ImportarExtratoForm()
    if form.validate_on_submit():
        conteudo = form.arquivo.data.read()
        try:
            extrato = ler_extrato(conteudo)
        except ExtratoInvalido as erro:
            form.arquivo.errors = [*form.arquivo.errors, str(erro)]
        else:
            return _previa(extrato, base64.b64encode(conteudo).decode("ascii"))
    return render_template("receitas/importar.html", form=form)


@bp.post("/importar/confirmar")
def confirmar_importacao():
    arquivo = request.form.get("arquivo", "")
    try:
        extrato = ler_extrato(base64.b64decode(arquivo, validate=True))
    except (ValueError, ExtratoInvalido):
        flash("Não consegui ler o arquivo de novo. Envie o extrato outra vez.", "erro")
        return redirect(url_for(".importar"))

    existentes = _ja_importadas(extrato)
    novas = [v for v in extrato.vendas if v.id_externo not in existentes]
    if not novas:
        flash("Todas as vendas deste arquivo já estavam no sistema. Nada foi importado.", "info")
        return redirect(url_for(".importar"))

    formas = {f.id for f in _formas_ativas()}
    escolhas = {v.tipo: request.form.get(f"forma_{v.tipo}", type=int) for v in novas}
    if any(forma not in formas for forma in escolhas.values()):
        return _previa(extrato, arquivo, escolhas, erro="Escolha a forma de pagamento de cada tipo de venda.")

    categorias = db.session.scalars(
        select(Categoria).where(Categoria.tipo == "receita", Categoria.ativa).order_by(Categoria.id)
    ).all()
    categoria = next((c for c in categorias if c.nome == "Vendas"), categorias[0] if categorias else None)

    for v in novas:
        db.session.add(Receita(
            data=v.data, descricao=f"Mercado Pago {v.momento:%H:%M} · {v.detalhe}"[:200],
            categoria_id=categoria.id if categoria else None, forma_pagto_id=escolhas[v.tipo],
            valor_bruto=v.bruto, taxa=v.taxa, valor_liquido=v.liquido,
            origem="importado", id_externo=v.id_externo, usuario_id=current_user.id,
        ))
    try:
        db.session.commit()
    except IntegrityError:
        # Confirmação enviada duas vezes: a primeira já gravou
        db.session.rollback()
        flash("Essas vendas já tinham sido importadas.", "info")
        return redirect(url_for(".lista", mes=novas[-1].data.strftime("%Y-%m")))

    total = _somar(novas)
    mensagem = f"{total['quantidade']} vendas importadas, somando {brl(total['bruto'])}."
    if existentes:
        mensagem += f" {len(existentes)} já estavam no sistema e foram puladas."
    flash(mensagem, "ok")
    return redirect(url_for(".lista", mes=novas[-1].data.strftime("%Y-%m")))
