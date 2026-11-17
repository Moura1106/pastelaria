import gzip
import os
import sqlite3
from datetime import date

from app import create_app
from app.backup import arquivo_do_dia, caminho_sqlite, fazer_backup
from config import TestConfig


def _banco(tmp_path):
    caminho = tmp_path / "pastelaria.db"
    con = sqlite3.connect(caminho)
    con.execute("create table vendas (valor)")
    con.execute("insert into vendas values (10)")
    con.commit()
    con.close()
    return str(caminho)


def test_backup_e_restauracao(tmp_path):
    destino = fazer_backup(_banco(tmp_path), str(tmp_path / "backups"), date(2026, 10, 28))
    assert destino.endswith("pastelaria-2026-10-28.db.gz")

    restaurado = tmp_path / "restaurado.db"
    restaurado.write_bytes(gzip.open(destino).read())
    assert sqlite3.connect(restaurado).execute("select valor from vendas").fetchone() == (10,)


def test_apaga_backups_antigos(tmp_path):
    pasta = tmp_path / "backups"
    pasta.mkdir()
    antigo = pasta / "pastelaria-2020-01-01.db.gz"
    antigo.write_bytes(b"x")
    os.utime(antigo, (0, 0))
    fazer_backup(_banco(tmp_path), str(pasta))
    assert not antigo.exists()


def test_caminho_sqlite():
    assert caminho_sqlite("sqlite:////home/x/dados/pastelaria.db") == "/home/x/dados/pastelaria.db"
    assert caminho_sqlite("sqlite://") is None
    assert caminho_sqlite("mysql+pymysql://u:s@h/b") is None


def test_backup_automatico_no_primeiro_acesso(tmp_path):
    banco, pasta = _banco(tmp_path), str(tmp_path / "backups")

    class Config(TestConfig):
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + banco
        PASTA_BACKUPS = pasta

    cliente = create_app(Config).test_client()
    cliente.get("/entrar")
    assert os.path.exists(arquivo_do_dia(pasta, date.today()))
