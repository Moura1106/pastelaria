import pytest

from app import create_app, db
from app.models import Usuario


@pytest.fixture
def app():
    app = create_app("config.TestConfig")
    with app.app_context():
        db.create_all()
        usuario = Usuario(nome="Teste", email="teste@exemplo.com")
        usuario.definir_senha("senha-segura")
        db.session.add(usuario)
        db.session.commit()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logado(client):
    client.post("/entrar", data={"email": "teste@exemplo.com", "senha": "senha-segura"})
    return client
