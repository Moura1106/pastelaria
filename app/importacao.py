"""Leitura do extrato de vendas do Mercado Pago (CSV exportado das maquininhas Point e do Pix por QR)."""
import csv
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

# Tipo de pagamento detectado no extrato -> nome mostrado na tela
TIPOS = {"pix": "Pix", "debito": "Débito", "credito": "Crédito", "outro": "Outro"}
# Nomes de forma de pagamento sugeridos para cada tipo, em ordem de preferência
SUGESTOES = {"pix": ["pix"], "debito": ["débito", "debito"], "credito": ["crédito à vista", "crédito", "credito"]}
PREFIXO_ID = "mp:"


class ExtratoInvalido(Exception):
    pass


@dataclass
class Venda:
    id_externo: str
    momento: datetime
    tipo: str
    bruto: Decimal
    taxa: Decimal
    liquido: Decimal
    detalhe: str  # bandeira/meio como veio no arquivo, ex.: "Cartão de crédito Master"

    @property
    def data(self):
        return self.momento.date()


@dataclass
class Extrato:
    vendas: list = field(default_factory=list)
    ignoradas: list = field(default_factory=list)  # linhas que não são pagamento (estorno etc.)


def _texto(conteudo):
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            pass
    return conteudo.decode("latin-1")


def _valor(texto):
    texto = (texto or "").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return Decimal(texto).quantize(Decimal("0.01"))


def classificar(meio, detalhe, metodo):
    """Pix, débito ou crédito a partir das colunas CHARGE_METHOD, PAYMENT_METHOD_DETAIL e PAYMENT_METHOD."""
    tudo = f"{meio} {detalhe} {metodo}".lower()
    if "pix" in tudo or "qr" in meio.lower():
        return "pix"
    if "débito" in tudo or "debito" in tudo:
        return "debito"
    if "crédito" in tudo or "credito" in tudo:
        return "credito"
    # Cartão sem o tipo (ex.: só "Master"): a taxa bate com a do débito
    if detalhe or metodo:
        return "debito"
    return "outro"


def ler_extrato(conteudo):
    linhas = _texto(conteudo).splitlines()
    inicio = next((i for i, l in enumerate(linhas) if "OPERATION_DATETIME" in l and "PAYMENT_ID" in l), None)
    if inicio is None:
        raise ExtratoInvalido("Não reconheci este arquivo. Use o extrato de vendas do Mercado Pago em CSV.")

    cabecalho = linhas[inicio]
    separador = ";" if cabecalho.count(";") >= cabecalho.count(",") else ","
    extrato, vistos = Extrato(), set()
    for numero, reg in enumerate(csv.DictReader(linhas[inicio:], delimiter=separador), start=inicio + 2):
        if not any(isinstance(v, str) and v.strip() for v in reg.values()):
            continue
        movimento = (reg.get("MOVEMENT_TYPE") or "").strip()
        if movimento.lower() != "pagamento":
            extrato.ignoradas.append(f"Linha {numero}: {movimento or 'sem tipo'} de R$ {reg.get('GROSS_VALUE') or '?'}")
            continue
        try:
            momento = datetime.strptime(reg["OPERATION_DATETIME"].strip(), "%d-%m-%Y %H:%M:%S")
            bruto, liquido = _valor(reg["GROSS_VALUE"]), _valor(reg["NET"])
            pagamento_id = reg["PAYMENT_ID"].strip()
        except (KeyError, ValueError, InvalidOperation, AttributeError):
            raise ExtratoInvalido(f"Não consegui ler a linha {numero} do arquivo.") from None
        if not pagamento_id or bruto <= 0 or not 0 <= liquido <= bruto:
            raise ExtratoInvalido(f"A linha {numero} do arquivo tem valores estranhos. Confira o extrato.")

        id_externo = PREFIXO_ID + pagamento_id
        if id_externo in vistos:
            continue
        vistos.add(id_externo)

        meio = (reg.get("CHARGE_METHOD") or "").strip()
        detalhe = (reg.get("PAYMENT_METHOD_DETAIL") or "").strip()
        metodo = (reg.get("PAYMENT_METHOD") or "").strip()
        extrato.vendas.append(Venda(
            id_externo=id_externo, momento=momento, tipo=classificar(meio, detalhe, metodo),
            bruto=bruto, taxa=bruto - liquido, liquido=liquido,
            detalhe=" ".join(p for p in (detalhe, metodo) if p) or meio,
        ))

    if not extrato.vendas and not extrato.ignoradas:
        raise ExtratoInvalido("O arquivo não tem nenhuma venda.")
    extrato.vendas.sort(key=lambda v: v.momento)
    return extrato


def forma_sugerida(tipo, formas):
    """Forma de pagamento cadastrada que melhor combina com o tipo do extrato."""
    nomes = {f.nome.strip().lower(): f for f in formas}
    for sugestao in SUGESTOES.get(tipo, []):
        if sugestao in nomes:
            return nomes[sugestao]
    for sugestao in SUGESTOES.get(tipo, []):
        for nome, forma in nomes.items():
            if nome.startswith(sugestao):
                return forma
    return None
