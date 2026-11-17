from flask import Blueprint, flash, redirect, render_template, url_for
from sqlalchemy import func, select

from . import db
from .forms import CategoriaForm, FormaPagamentoForm
from .models import Categoria, FormaPagamento

bp = Blueprint("cadastros", __name__, url_prefix="/cadastros")

# Itens não são excluídos, só desativados: assim o histórico dos lançamentos antigos continua correto.


# ---------- Categorias ----------

def _categoria_existe(nome, tipo, ignorar_id=None):
    consulta = select(Categoria.id).where(func.lower(Categoria.nome) == nome.lower(), Categoria.tipo == tipo)
    if ignorar_id:
        consulta = consulta.where(Categoria.id != ignorar_id)
    return db.session.scalar(consulta) is not None


@bp.route("/categorias", methods=["GET", "POST"])
def categorias():
    form = CategoriaForm()
    if form.validate_on_submit():
        nome = form.nome.data.strip()
        if _categoria_existe(nome, form.tipo.data):
            flash(f"Já existe a categoria “{nome}”.", "erro")
        else:
            db.session.add(Categoria(nome=nome, tipo=form.tipo.data))
            db.session.commit()
            flash(f"Categoria “{nome}” adicionada.", "ok")
            return redirect(url_for(".categorias"))

    todas = db.session.scalars(select(Categoria).order_by(Categoria.ativa.desc(), Categoria.nome)).all()
    return render_template(
        "cadastros/categorias.html",
        form=form,
        despesas=[c for c in todas if c.tipo == "despesa"],
        receitas=[c for c in todas if c.tipo == "receita"],
    )


@bp.route("/categorias/<int:id>/editar", methods=["GET", "POST"])
def editar_categoria(id):
    categoria = db.get_or_404(Categoria, id)
    form = CategoriaForm(obj=categoria)
    del form.tipo  # o tipo não muda depois de criado, para não bagunçar lançamentos antigos

    if form.validate_on_submit():
        nome = form.nome.data.strip()
        if _categoria_existe(nome, categoria.tipo, ignorar_id=categoria.id):
            flash(f"Já existe a categoria “{nome}”.", "erro")
        else:
            categoria.nome = nome
            db.session.commit()
            flash("Categoria atualizada.", "ok")
            return redirect(url_for(".categorias"))

    return render_template("cadastros/editar.html", form=form, titulo="Editar categoria",
                           voltar=url_for(".categorias"))


@bp.post("/categorias/<int:id>/alternar")
def alternar_categoria(id):
    categoria = db.get_or_404(Categoria, id)
    categoria.ativa = not categoria.ativa
    db.session.commit()
    flash(f"Categoria “{categoria.nome}” {'reativada' if categoria.ativa else 'desativada'}.", "ok")
    return redirect(url_for(".categorias"))


# ---------- Formas de pagamento ----------

def _forma_existe(nome, ignorar_id=None):
    consulta = select(FormaPagamento.id).where(func.lower(FormaPagamento.nome) == nome.lower())
    if ignorar_id:
        consulta = consulta.where(FormaPagamento.id != ignorar_id)
    return db.session.scalar(consulta) is not None


@bp.route("/pagamentos", methods=["GET", "POST"])
def formas():
    form = FormaPagamentoForm()
    if form.validate_on_submit():
        nome = form.nome.data.strip()
        if _forma_existe(nome):
            flash(f"Já existe a forma de pagamento “{nome}”.", "erro")
        else:
            db.session.add(FormaPagamento(nome=nome, taxa_padrao=form.taxa_padrao.data or 0))
            db.session.commit()
            flash(f"Forma de pagamento “{nome}” adicionada.", "ok")
            return redirect(url_for(".formas"))

    lista = db.session.scalars(
        select(FormaPagamento).order_by(FormaPagamento.ativa.desc(), FormaPagamento.nome)
    ).all()
    return render_template("cadastros/formas.html", form=form, formas=lista)


@bp.route("/pagamentos/<int:id>/editar", methods=["GET", "POST"])
def editar_forma(id):
    forma = db.get_or_404(FormaPagamento, id)
    form = FormaPagamentoForm(obj=forma)

    if form.validate_on_submit():
        nome = form.nome.data.strip()
        if _forma_existe(nome, ignorar_id=forma.id):
            flash(f"Já existe a forma de pagamento “{nome}”.", "erro")
        else:
            forma.nome = nome
            forma.taxa_padrao = form.taxa_padrao.data or 0
            db.session.commit()
            flash("Forma de pagamento atualizada.", "ok")
            return redirect(url_for(".formas"))

    return render_template("cadastros/editar.html", form=form, titulo="Editar forma de pagamento",
                           voltar=url_for(".formas"))


@bp.post("/pagamentos/<int:id>/alternar")
def alternar_forma(id):
    forma = db.get_or_404(FormaPagamento, id)
    forma.ativa = not forma.ativa
    db.session.commit()
    flash(f"“{forma.nome}” {'reativada' if forma.ativa else 'desativada'}.", "ok")
    return redirect(url_for(".formas"))
