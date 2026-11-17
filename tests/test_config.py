import pytest

from config import mysql_pythonanywhere


def test_le_senha_do_my_cnf(tmp_path, monkeypatch):
    monkeypatch.setenv("USER", "UsuarioExemplo")
    cnf = tmp_path / ".my.cnf"
    cnf.write_text('[client]\npassword = "S3nh@%com$imbolos"\n')

    url = mysql_pythonanywhere("UsuarioExemplo$pastelaria", str(cnf))
    assert url.username == "UsuarioExemplo"
    assert url.password == "S3nh@%com$imbolos"
    assert url.host == "UsuarioExemplo.mysql.pythonanywhere-services.com"
    assert url.database == "UsuarioExemplo$pastelaria"


def test_sem_my_cnf(tmp_path):
    with pytest.raises(RuntimeError, match="Databases"):
        mysql_pythonanywhere("x$pastelaria", str(tmp_path / "nao-existe.cnf"))
