import os

import click
from sqlalchemy import func, select

from . import db
from .backup import caminho_sqlite, fazer_backup
from .models import Categoria, FormaPagamento, Usuario

CATEGORIAS_DESPESA = [
    "Insumos", "Carnes", "Bebidas", "Gás e carvão", "Embalagens", "Aluguel", "Energia",
    "Água", "Internet e telefone", "Funcionários", "Impostos e taxas", "Manutenção", "Outros",
]
CATEGORIAS_RECEITA = ["Vendas", "Outros"]
# Taxas começam em 0: devem ser preenchidas com as taxas reais da maquininha pela tela de Pagamentos
FORMAS_PAGAMENTO = ["Dinheiro", "Pix", "Débito", "Crédito à vista", "Crédito parcelado"]


def registrar_comandos(app):
    @app.cli.command("backup")
    def backup():
        """Faz agora um backup do banco SQLite na PASTA_BACKUPS (padrão ~/backups)."""
        banco = caminho_sqlite(str(app.config["SQLALCHEMY_DATABASE_URI"]))
        if not banco:
            raise click.ClickException("O backup automático só funciona com banco SQLite.")
        pasta = app.config.get("PASTA_BACKUPS") or os.path.expanduser("~/backups")
        click.echo(f"Backup salvo em {fazer_backup(banco, pasta)}")

    @app.cli.command("dados-iniciais")
    def dados_iniciais():
        """Cadastra as categorias e formas de pagamento padrão (só se estiverem vazias)."""
        if db.session.scalar(select(func.count(Categoria.id))) == 0:
            db.session.add_all(Categoria(nome=n, tipo="despesa") for n in CATEGORIAS_DESPESA)
            db.session.add_all(Categoria(nome=n, tipo="receita") for n in CATEGORIAS_RECEITA)
            click.echo("Categorias padrão cadastradas.")
        if db.session.scalar(select(func.count(FormaPagamento.id))) == 0:
            db.session.add_all(FormaPagamento(nome=n, taxa_padrao=0) for n in FORMAS_PAGAMENTO)
            click.echo("Formas de pagamento padrão cadastradas.")
        db.session.commit()

    @app.cli.command("dados-demo")
    @click.option("--csv", "destino_csv", default="demo/extrato_mercado_pago_demo.csv", show_default=True,
                  help="Onde gravar o extrato falso para testar a importação.")
    def dados_demo(destino_csv):
        """Popula um banco VAZIO com dados fictícios (usuário demo@exemplo.com) e gera um extrato CSV falso."""
        from .demo import EMAIL_DEMO, SENHA_DEMO, banco_esta_vazio, gerar_csv_demo, gerar_dados_demo

        if not banco_esta_vazio():
            raise click.ClickException("O banco já tem dados. Use um banco novo para a demonstração.")
        gerar_dados_demo()
        os.makedirs(os.path.dirname(destino_csv) or ".", exist_ok=True)
        qtd = gerar_csv_demo(destino_csv)
        click.echo(f"Dados fictícios criados. Login: {EMAIL_DEMO} / senha: {SENHA_DEMO}")
        click.echo(f"Extrato falso com {qtd} vendas gravado em {destino_csv}")

    @app.cli.command("criar-usuario")
    @click.option("--nome", prompt="Nome")
    @click.option("--email", prompt="E-mail")
    @click.password_option("--senha", prompt="Senha", confirmation_prompt="Repita a senha")
    def criar_usuario(nome, email, senha):
        """Cria um usuário (não existe cadastro aberto pelo site)."""
        email = email.strip().lower()
        if len(senha) < 8:
            raise click.ClickException("A senha precisa ter pelo menos 8 caracteres.")
        if db.session.scalar(select(Usuario.id).where(func.lower(Usuario.email) == email)):
            raise click.ClickException(f"Já existe um usuário com o e-mail {email}.")
        usuario = Usuario(nome=nome.strip(), email=email)
        usuario.definir_senha(senha)
        db.session.add(usuario)
        db.session.commit()
        click.echo(f"Usuário {usuario.nome} criado.")

    @app.cli.command("trocar-senha")
    @click.option("--email", prompt="E-mail")
    @click.password_option("--senha", prompt="Nova senha", confirmation_prompt="Repita a senha")
    def trocar_senha(email, senha):
        """Troca a senha de um usuário."""
        usuario = db.session.scalar(select(Usuario).where(func.lower(Usuario.email) == email.strip().lower()))
        if not usuario:
            raise click.ClickException("Usuário não encontrado.")
        if len(senha) < 8:
            raise click.ClickException("A senha precisa ter pelo menos 8 caracteres.")
        usuario.definir_senha(senha)
        db.session.commit()
        click.echo("Senha alterada.")
