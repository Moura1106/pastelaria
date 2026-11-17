import calendar
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, login_manager
from .utils import dividir_em_parcelas, somar_meses

Dinheiro = db.Numeric(10, 2)


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    falhas_login = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    bloqueado_ate = db.Column(db.DateTime)

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def conferir_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_active(self):
        return self.ativo


@login_manager.user_loader
def carregar_usuario(usuario_id):
    return db.session.get(Usuario, int(usuario_id))


class Categoria(db.Model):
    __tablename__ = "categorias"
    __table_args__ = (db.UniqueConstraint("nome", "tipo"),)

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(60), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # "receita" ou "despesa"
    ativa = db.Column(db.Boolean, nullable=False, default=True)


class FormaPagamento(db.Model):
    __tablename__ = "formas_pagto"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(40), unique=True, nullable=False)
    taxa_padrao = db.Column(db.Numeric(5, 2), nullable=False, default=0)  # em %
    ativa = db.Column(db.Boolean, nullable=False, default=True)


class Receita(db.Model):
    __tablename__ = "receitas"

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    descricao = db.Column(db.String(200))
    categoria_id = db.Column(db.ForeignKey("categorias.id"))
    forma_pagto_id = db.Column(db.ForeignKey("formas_pagto.id"), nullable=False)
    valor_bruto = db.Column(Dinheiro, nullable=False)
    taxa = db.Column(Dinheiro, nullable=False, default=0)  # valor em R$ descontado pela maquininha
    valor_liquido = db.Column(Dinheiro, nullable=False)
    origem = db.Column(db.String(10), nullable=False, default="manual")  # "manual" ou "importado"
    id_externo = db.Column(db.String(60), unique=True, index=True)  # id da venda no extrato importado; evita duplicar
    usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    categoria = db.relationship("Categoria")
    forma_pagto = db.relationship("FormaPagamento")
    usuario = db.relationship("Usuario")


class Despesa(db.Model):
    __tablename__ = "despesas"

    id = db.Column(db.Integer, primary_key=True)
    data_compra = db.Column(db.Date, nullable=False, index=True)
    descricao = db.Column(db.String(200), nullable=False)
    fornecedor = db.Column(db.String(120))
    categoria_id = db.Column(db.ForeignKey("categorias.id"), nullable=False)
    forma_pagto_id = db.Column(db.ForeignKey("formas_pagto.id"), nullable=False)
    valor_total = db.Column(Dinheiro, nullable=False)
    num_parcelas = db.Column(db.Integer, nullable=False, default=1)
    usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    fixa_id = db.Column(db.ForeignKey("despesas_fixas.id"), index=True)  # preenchido se veio de uma despesa fixa
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    categoria = db.relationship("Categoria")
    forma_pagto = db.relationship("FormaPagamento")
    usuario = db.relationship("Usuario")
    fixa = db.relationship("DespesaFixa", back_populates="despesas")
    parcelas = db.relationship(
        "Parcela",
        back_populates="despesa",
        cascade="all, delete-orphan",
        order_by="Parcela.numero",
    )

    def gerar_parcelas(self, primeiro_vencimento):
        """Recria as parcelas: uma por mês a partir do primeiro vencimento."""
        self.parcelas = [
            Parcela(numero=i, valor=valor, vencimento=somar_meses(primeiro_vencimento, i - 1))
            for i, valor in enumerate(dividir_em_parcelas(self.valor_total, self.num_parcelas), start=1)
        ]


class DespesaFixa(db.Model):
    """Conta que se repete todo mês (aluguel, luz...). Gera uma Despesa por mês."""

    __tablename__ = "despesas_fixas"

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    fornecedor = db.Column(db.String(120))
    categoria_id = db.Column(db.ForeignKey("categorias.id"), nullable=False)
    forma_pagto_id = db.Column(db.ForeignKey("formas_pagto.id"), nullable=False)
    valor = db.Column(Dinheiro, nullable=False)  # valor previsto; cada mês pode ser ajustado
    dia_vencimento = db.Column(db.Integer, nullable=False)
    inicio = db.Column(db.Date, nullable=False)  # primeiro mês (sempre dia 1)
    gerado_ate = db.Column(db.Date)  # último mês já gerado (dia 1)
    ativa = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    categoria = db.relationship("Categoria")
    forma_pagto = db.relationship("FormaPagamento")
    despesas = db.relationship("Despesa", back_populates="fixa")

    def vencimento_em(self, mes, dia=None):
        """Data de vencimento no mês informado; dia 31 vira o último dia em meses curtos."""
        dia = dia or self.dia_vencimento
        return mes.replace(day=min(dia, calendar.monthrange(mes.year, mes.month)[1]))

    def nova_despesa(self, mes):
        vencimento = self.vencimento_em(mes)
        despesa = Despesa(
            descricao=self.descricao, fornecedor=self.fornecedor, valor_total=self.valor,
            data_compra=vencimento, categoria_id=self.categoria_id, forma_pagto_id=self.forma_pagto_id,
            num_parcelas=1, fixa=self,
        )
        despesa.gerar_parcelas(vencimento)
        return despesa


class Parcela(db.Model):
    __tablename__ = "parcelas"

    id = db.Column(db.Integer, primary_key=True)
    despesa_id = db.Column(db.ForeignKey("despesas.id", ondelete="CASCADE"), nullable=False)
    numero = db.Column(db.Integer, nullable=False)
    valor = db.Column(Dinheiro, nullable=False)
    vencimento = db.Column(db.Date, nullable=False, index=True)
    paga = db.Column(db.Boolean, nullable=False, default=False)
    data_pagamento = db.Column(db.Date)

    despesa = db.relationship("Despesa", back_populates="parcelas")
