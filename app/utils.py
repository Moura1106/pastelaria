import calendar
from datetime import date
from decimal import ROUND_DOWN, Decimal

CENTAVO = Decimal("0.01")

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def mes_ano(data):
    """date(2026, 10, 1) -> 'outubro de 2026'."""
    return f"{MESES[data.month - 1]} de {data.year}"


def mes_curto(data):
    """date(2026, 10, 1) -> 'out/26'."""
    return f"{MESES[data.month - 1][:3]}/{data.year % 100:02d}"


def data_br(data, com_dia_semana=False):
    """date(2026, 10, 27) -> '27/10/2026' (ou 'ter, 27/10/2026')."""
    texto = data.strftime("%d/%m/%Y")
    return f"{DIAS_SEMANA[data.weekday()]}, {texto}" if com_dia_semana else texto


def mes_da_url(texto):
    """'2026-10' -> date(2026, 10, 1); texto inválido -> primeiro dia do mês atual."""
    try:
        ano, mes = map(int, (texto or "").split("-"))
        return date(ano, mes, 1)
    except ValueError:
        return date.today().replace(day=1)


def brl(valor):
    """Formata um valor como moeda brasileira: 1234.5 -> 'R$ 1.234,50'."""
    if valor is None:
        return "—"
    valor = Decimal(valor)
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {texto}" if valor < 0 else f"R$ {texto}"


def pct(valor):
    """Formata um percentual: 2.5 -> '2,50%'."""
    if valor is None:
        return "—"
    return f"{Decimal(valor):.2f}".replace(".", ",") + "%"


def dividir_em_parcelas(total, quantidade):
    """Divide um valor em parcelas; a última fica com a sobra dos centavos.

    dividir_em_parcelas(1000, 3) -> [333.33, 333.33, 333.34]
    """
    if quantidade < 1:
        raise ValueError("A quantidade de parcelas deve ser pelo menos 1.")
    total = Decimal(total).quantize(CENTAVO)
    base = (total / quantidade).quantize(CENTAVO, rounding=ROUND_DOWN)
    parcelas = [base] * quantidade
    parcelas[-1] = total - base * (quantidade - 1)
    return parcelas


def somar_meses(data, meses):
    """Soma meses a uma data, ajustando o dia quando o mês é mais curto (31/01 + 1 -> 28/02)."""
    indice = data.month - 1 + meses
    ano, mes = data.year + indice // 12, indice % 12 + 1
    dia = min(data.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)
