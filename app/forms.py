from datetime import date
from decimal import Decimal

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (BooleanField, DateField, DecimalField, IntegerField, MonthField, PasswordField,
                     SelectField, StringField, TextAreaField)
from wtforms.fields.choices import SelectChoice
from wtforms.validators import DataRequired, EqualTo, InputRequired, Length, NumberRange, Optional


class DecimalBR(DecimalField):
    """Campo decimal que aceita vírgula: '2,99', '1.234,56' ou '2.99'."""

    def process_formdata(self, valuelist):
        if valuelist and valuelist[0]:
            texto = valuelist[0].replace("R$", "").replace("%", "").strip()
            if "," in texto:
                texto = texto.replace(".", "").replace(",", ".")
            valuelist = [texto]
        super().process_formdata(valuelist)

    def _value(self):
        return super()._value().replace(".", ",")


class LoginForm(FlaskForm):
    email = StringField("E-mail", validators=[DataRequired(), Length(max=120)],
                        render_kw={"type": "email", "autocomplete": "username"})
    senha = PasswordField("Senha", validators=[DataRequired()],
                          render_kw={"autocomplete": "current-password"})
    lembrar = BooleanField("Manter conectado neste aparelho", default=True)


class TrocarSenhaForm(FlaskForm):
    senha_atual = PasswordField("Senha atual", validators=[DataRequired()],
                                render_kw={"autocomplete": "current-password"})
    nova_senha = PasswordField("Nova senha", validators=[
        DataRequired(), Length(min=8, message="A senha precisa ter pelo menos 8 caracteres.")],
        render_kw={"autocomplete": "new-password"})
    confirmar = PasswordField("Repita a nova senha", validators=[
        DataRequired(), EqualTo("nova_senha", message="As senhas não são iguais.")],
        render_kw={"autocomplete": "new-password"})


class CategoriaForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(max=60)])
    tipo = SelectField("Tipo", choices=[SelectChoice("despesa", "Despesa"), SelectChoice("receita", "Receita")])


class ReceitaForm(FlaskForm):
    # As opções de forma de pagamento e categoria são preenchidas na view
    data = DateField("Data", validators=[DataRequired(message="Informe a data.")], default=date.today)
    valor_bruto = DecimalBR(
        "Valor da venda (R$)",
        places=2,
        validators=[DataRequired(message="Informe o valor."),
                    NumberRange(min=Decimal("0.01"), message="O valor precisa ser maior que zero.")],
        render_kw={"inputmode": "decimal", "placeholder": "0,00", "autofocus": True},
    )
    forma_pagto_id = SelectField("Forma de pagamento", coerce=int)
    taxa = DecimalBR(
        "Taxa da maquininha (R$)",
        places=2,
        validators=[Optional(), NumberRange(min=0, message="A taxa não pode ser negativa.")],
        render_kw={"inputmode": "decimal", "placeholder": "calculada automaticamente"},
    )
    categoria_id = SelectField("Categoria", coerce=int)
    descricao = StringField("Observação (opcional)", validators=[Optional(), Length(max=200)])


class PerguntaForm(FlaskForm):
    pergunta = TextAreaField("Sua pergunta", validators=[
        DataRequired(message="Escreva a pergunta."),
        Length(max=500, message="Use no máximo 500 letras."),
    ], render_kw={"rows": 3, "placeholder": "Ex.: quanto vendi esta semana?", "maxlength": 500})


class ImportarExtratoForm(FlaskForm):
    arquivo = FileField("Extrato do Mercado Pago (.csv)", validators=[
        FileRequired(message="Escolha o arquivo do extrato."),
        FileAllowed(["csv"], message="O arquivo precisa ser .csv."),
    ], render_kw={"accept": ".csv,text/csv"})


MAX_PARCELAS = 50
OPCOES_PARCELAS = [SelectChoice(1, "1x (à vista)")] + [SelectChoice(n, f"{n}x") for n in range(2, MAX_PARCELAS + 1)]


class DespesaForm(FlaskForm):
    # As opções de categoria e forma de pagamento são preenchidas na view
    descricao = StringField("Descrição", validators=[DataRequired(message="Informe o que foi comprado."), Length(max=200)],
                            render_kw={"placeholder": "Ex.: Massa de pastel", "autofocus": True})
    valor_total = DecimalBR(
        "Valor total (R$)",
        places=2,
        validators=[DataRequired(message="Informe o valor."),
                    NumberRange(min=Decimal("0.01"), message="O valor precisa ser maior que zero.")],
        render_kw={"inputmode": "decimal", "placeholder": "0,00"},
    )
    data_compra = DateField("Data da compra", validators=[DataRequired(message="Informe a data.")], default=date.today)
    categoria_id = SelectField("Categoria", coerce=int, validators=[DataRequired(message="Escolha a categoria.")])
    forma_pagto_id = SelectField("Forma de pagamento", coerce=int)
    fornecedor = StringField("Fornecedor (opcional)", validators=[Optional(), Length(max=120)],
                             render_kw={"list": "fornecedores", "autocomplete": "off"})
    num_parcelas = SelectField("Parcelas", coerce=int, default=1, choices=OPCOES_PARCELAS)
    primeiro_vencimento = DateField("Vencimento da 1ª parcela", validators=[Optional()])
    ja_paga = BooleanField("Já está paga", default=True)


class DespesaFixaForm(FlaskForm):
    # As opções de categoria e forma de pagamento são preenchidas na view
    descricao = StringField("Descrição", validators=[DataRequired(message="Informe a conta."), Length(max=200)],
                            render_kw={"placeholder": "Ex.: Aluguel", "autofocus": True})
    valor = DecimalBR(
        "Valor mensal (R$)",
        places=2,
        validators=[DataRequired(message="Informe o valor."),
                    NumberRange(min=Decimal("0.01"), message="O valor precisa ser maior que zero.")],
        render_kw={"inputmode": "decimal", "placeholder": "0,00"},
    )
    dia_vencimento = IntegerField("Vence todo dia",
                                  validators=[InputRequired(message="Informe o dia."),
                                              NumberRange(min=1, max=31, message="Use um dia de 1 a 31.")],
                                  render_kw={"min": 1, "max": 31, "inputmode": "numeric"})
    categoria_id = SelectField("Categoria", coerce=int, validators=[DataRequired(message="Escolha a categoria.")])
    forma_pagto_id = SelectField("Forma de pagamento", coerce=int)
    fornecedor = StringField("Fornecedor (opcional)", validators=[Optional(), Length(max=120)],
                             render_kw={"list": "fornecedores", "autocomplete": "off"})
    inicio = MonthField("A partir de", validators=[DataRequired(message="Informe o mês.")], default=date.today)


class FormaPagamentoForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(max=40)])
    taxa_padrao = DecimalBR(
        "Taxa da maquininha (%)",
        places=2,
        validators=[Optional(), NumberRange(min=0, max=100, message="Use um valor entre 0 e 100.")],
        render_kw={"inputmode": "decimal", "placeholder": "0,00"},
    )
