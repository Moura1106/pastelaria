import configparser
import os
from datetime import timedelta

from sqlalchemy.engine import URL

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def mysql_pythonanywhere(banco, arquivo_cnf="~/.my.cnf"):
    """Conexão com o MySQL do PythonAnywhere usando a senha do ~/.my.cnf.

    O PythonAnywhere cria esse arquivo ao definir a senha do banco, então a senha não precisa ir para o .env.
    """
    cnf = configparser.RawConfigParser()
    if not cnf.read(os.path.expanduser(arquivo_cnf)) or not cnf.has_option("client", "password"):
        raise RuntimeError("Não encontrei a senha do MySQL em ~/.my.cnf. Defina a senha na aba Databases.")

    def valor(chave, padrao=None):
        texto = cnf.get("client", chave, fallback=padrao)
        return texto.strip().strip("'\"") if texto else texto

    usuario = valor("user", os.environ.get("USER"))
    return URL.create(
        "mysql+pymysql",
        username=usuario,
        password=valor("password"),
        host=valor("host", f"{usuario}.mysql.pythonanywhere-services.com"),
        database=banco,
        query={"charset": "utf8mb4"},
    )


def _url_do_banco():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if os.environ.get("MYSQL_BANCO"):
        return mysql_pythonanywhere(os.environ["MYSQL_BANCO"])
    return "sqlite:///" + os.path.join(BASE_DIR, "pastelaria.db")


class Config:
    # Em produção, SECRET_KEY e o banco (DATABASE_URL ou MYSQL_BANCO) vêm do arquivo .env
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-troque-esta-chave"
    SQLALCHEMY_DATABASE_URI = _url_do_banco()
    # O MySQL do PythonAnywhere encerra conexões ociosas depois de ~300s
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_recycle": 280, "pool_pre_ping": True}
    # Se definida, o sistema guarda ali um backup do banco SQLite por dia (ver app/backup.py)
    PASTA_BACKUPS = os.environ.get("PASTA_BACKUPS")
    # Assistente "Perguntar": sem a chave, a tela some do menu. Defina um limite de gasto no painel da Anthropic.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    MODELO_ASSISTENTE = os.environ.get("MODELO_ASSISTENTE") or "claude-haiku-5-5"
    # Limite de envio (o extrato de um mês tem bem menos que isso)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # Mantém o login por 30 dias para ela não precisar digitar a senha todo dia
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    ANTHROPIC_API_KEY = None
