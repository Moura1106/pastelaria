"""Backup do banco SQLite: cópia consistente, compactada, guardando os últimos 30 dias.

Roda sozinho no primeiro acesso de cada dia (a conta gratuita do PythonAnywhere não tem tarefas agendadas)
e também pelo comando `flask backup`.
"""
import gzip
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import date

from sqlalchemy.engine import make_url

DIAS_GUARDADOS = 30


def caminho_sqlite(uri):
    """Arquivo do banco, se for SQLite em arquivo; senão None."""
    url = make_url(uri)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        return url.database
    return None


def arquivo_do_dia(pasta, dia):
    return os.path.join(pasta, f"pastelaria-{dia:%Y-%m-%d}.db.gz")


def fazer_backup(banco, pasta, dia=None):
    if not os.path.isfile(banco):
        raise FileNotFoundError(f"Banco não encontrado: {banco}")
    os.makedirs(pasta, exist_ok=True)
    destino = arquivo_do_dia(pasta, dia or date.today())

    with tempfile.TemporaryDirectory(dir=pasta) as temporaria:
        copia = os.path.join(temporaria, "copia.db")
        origem, alvo = sqlite3.connect(banco), sqlite3.connect(copia)
        try:
            origem.backup(alvo)  # API de backup do SQLite: não corrompe se alguém estiver lançando algo
        finally:
            origem.close()
            alvo.close()
        compactado = os.path.join(temporaria, "copia.db.gz")
        with open(copia, "rb") as entrada, gzip.open(compactado, "wb") as saida:
            shutil.copyfileobj(entrada, saida)
        os.replace(compactado, destino)  # troca atômica: nunca fica um backup pela metade

    limite = time.time() - DIAS_GUARDADOS * 86400
    for nome in os.listdir(pasta):
        caminho = os.path.join(pasta, nome)
        if nome.startswith("pastelaria-") and nome.endswith(".db.gz") and os.path.getmtime(caminho) < limite:
            os.remove(caminho)
    return destino


def registrar_backup_automatico(app):
    """Faz o backup do dia no primeiro acesso, se PASTA_BACKUPS estiver configurada e o banco for SQLite."""
    pasta = app.config.get("PASTA_BACKUPS")
    banco = caminho_sqlite(str(app.config["SQLALCHEMY_DATABASE_URI"]))
    if not pasta or not banco:
        return

    ultimo_dia = {"valor": None}

    @app.before_request
    def backup_do_dia():
        hoje = date.today()
        if ultimo_dia["valor"] == hoje:
            return
        ultimo_dia["valor"] = hoje
        if not os.path.exists(arquivo_do_dia(pasta, hoje)):
            try:
                fazer_backup(banco, pasta, hoje)
            except Exception:  # o backup nunca pode impedir o uso do sistema
                app.logger.exception("Falha no backup automático")
