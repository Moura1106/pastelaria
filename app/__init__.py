import os

from flask import Flask, render_template, request
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import MetaData

# Nomes previsíveis para chaves e índices; sem isso, migrações no SQLite falham ao criar chaves estrangeiras
db = SQLAlchemy(metadata=MetaData(naming_convention={
    "ix": "ix_%(column_0_label)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}))
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

# Páginas que podem ser abertas sem estar logado
ROTAS_PUBLICAS = {"auth.login", "static"}


def create_app(config_class="config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_class)
    em_producao = os.environ.get("DATABASE_URL") or os.environ.get("MYSQL_BANCO")
    if em_producao and app.config["SECRET_KEY"] == "dev-troque-esta-chave":
        raise RuntimeError("Defina uma SECRET_KEY própria no arquivo .env antes de rodar em produção.")

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Entre para continuar."
    login_manager.login_message_category = "info"

    from . import models  # noqa: F401  (registra os modelos)
    from .assistente import bp as assistente_bp
    from .auth import bp as auth_bp
    from .backup import registrar_backup_automatico
    from .cadastros import bp as cadastros_bp
    from .comandos import registrar_comandos
    from .despesas import bp as despesas_bp
    from .fixas import bp as fixas_bp
    from .main import bp as main_bp
    from .receitas import bp as receitas_bp
    from .relatorios import bp as relatorios_bp
    from .utils import brl, data_br, mes_ano, mes_curto, pct

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(cadastros_bp)
    app.register_blueprint(receitas_bp)
    app.register_blueprint(despesas_bp)
    app.register_blueprint(fixas_bp)
    app.register_blueprint(relatorios_bp)
    app.register_blueprint(assistente_bp)
    registrar_comandos(app)
    registrar_backup_automatico(app)

    for filtro in (brl, pct, data_br, mes_ano, mes_curto):
        app.add_template_filter(filtro)

    # Tudo exige login, exceto o que estiver em ROTAS_PUBLICAS
    @app.before_request
    def exigir_login():
        if request.endpoint is None or request.endpoint in ROTAS_PUBLICAS:
            return None
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        return None

    @app.errorhandler(404)
    def nao_encontrado(_erro):
        return render_template("erro.html", titulo="Página não encontrada",
                               mensagem="O endereço não existe ou o item foi excluído."), 404

    @app.errorhandler(500)
    def erro_interno(_erro):
        db.session.rollback()
        return render_template("erro.html", titulo="Algo deu errado",
                               mensagem="Nada foi salvo nessa operação. Tente de novo; se continuar, avise quem cuida do sistema."), 500

    @app.after_request
    def cabecalhos_seguranca(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("Referrer-Policy", "same-origin")
        return resposta

    return app
