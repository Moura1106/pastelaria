from datetime import datetime, timedelta
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func, select

from . import db
from .forms import LoginForm, TrocarSenhaForm
from .models import Usuario

bp = Blueprint("auth", __name__)

# Depois de tantas senhas erradas seguidas, o login daquele e-mail fica travado por um tempo
MAX_TENTATIVAS = 5
TEMPO_BLOQUEIO = timedelta(minutes=15)


def destino_seguro(destino):
    """Só aceita redirecionar para páginas do próprio sistema."""
    if not destino or not destino.startswith("/") or destino.startswith("//") or "\\" in destino:
        return url_for("main.index")
    partes = urlsplit(destino)
    return destino if not partes.scheme and not partes.netloc else url_for("main.index")


@bp.route("/entrar", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        usuario = db.session.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
        agora = datetime.now()

        if usuario and usuario.bloqueado_ate and usuario.bloqueado_ate > agora:
            flash("Muitas tentativas com a senha errada. Espere alguns minutos e tente de novo.", "erro")
        elif usuario and usuario.ativo and usuario.conferir_senha(form.senha.data):
            usuario.falhas_login, usuario.bloqueado_ate = 0, None
            db.session.commit()
            login_user(usuario, remember=form.lembrar.data)
            return redirect(destino_seguro(request.args.get("next")))
        else:
            if usuario:
                usuario.falhas_login += 1
                if usuario.falhas_login >= MAX_TENTATIVAS:
                    usuario.falhas_login, usuario.bloqueado_ate = 0, agora + TEMPO_BLOQUEIO
                db.session.commit()
            flash("E-mail ou senha incorretos.", "erro")

    return render_template("login.html", form=form)


@bp.post("/sair")
def logout():
    logout_user()
    flash("Você saiu do sistema.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/minha-conta", methods=["GET", "POST"])
def minha_conta():
    form = TrocarSenhaForm()
    if form.validate_on_submit():
        if not current_user.conferir_senha(form.senha_atual.data):
            form.senha_atual.errors = [*form.senha_atual.errors, "Senha atual incorreta."]
        else:
            current_user.definir_senha(form.nova_senha.data)
            db.session.commit()
            flash("Senha alterada.", "ok")
            return redirect(url_for("main.ajustes"))
    return render_template("minha_conta.html", form=form)
