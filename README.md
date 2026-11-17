# Caixa da Pastelaria

Sistema web para controlar **vendas, despesas e contas a pagar** de um pequeno comércio de alimentação
(pastelaria e espetaria). Nasceu para substituir o caderno de papel de uma família: precisava ser simples
o bastante para quem não é técnico e funcionar bem no celular.

> Este repositório usa **somente dados fictícios**. O comando `flask dados-demo` cria um banco de exemplo para
> você explorar o sistema.

<p>
  <img src="docs/img/01-inicio.png" width="210" alt="Tela inicial">
  <img src="docs/img/02-vendas.png" width="210" alt="Vendas do mês">
  <img src="docs/img/05-despesa-parcelada.png" width="210" alt="Despesa parcelada">
</p>

## O que o sistema faz

- **Vendas:** lançamento manual com taxa da maquininha calculada automaticamente por forma de pagamento
  (dinheiro, Pix, débito, crédito) e resumo do mês.
- **Importação de extrato:** lê o CSV de vendas do Mercado Pago, mostra uma prévia para conferência e grava
  sem duplicar (cada venda é identificada pelo `PAYMENT_ID`). A taxa real de cada venda vem do extrato.
- **Despesas e parcelas:** compras à vista ou parceladas; cada parcela vira uma conta do mês, com botão
  "Paguei" e aviso de contas vencidas.
- **Despesas fixas:** aluguel, energia, internet... são lançadas sozinhas mês a mês, e o valor de cada mês
  pode ser ajustado sem perder o padrão.
- **Relatórios:** entradas, saídas e sobra por mês (regime de caixa: compra parcelada conta pela parcela
  que vence no mês), gastos por categoria, gráfico dos últimos 6 meses e contas dos próximos meses.
- **Planilha Excel** do mês ou do ano, para conferência e cópia de segurança.
- **Assistente "Perguntar"** (opcional): perguntas em português sobre o caixa, respondidas pela API da
  Anthropic com consultas **somente leitura**. Só aparece se `ANTHROPIC_API_KEY` estiver configurada.
- **Segurança básica:** login obrigatório (sem cadastro aberto), senhas com hash, proteção CSRF e bloqueio
  temporário após tentativas erradas.

<p>
  <img src="docs/img/07-relatorios.png" width="210" alt="Relatórios">
  <img src="docs/img/06-contas-fixas.png" width="210" alt="Despesas fixas">
  <img src="docs/img/08-importar-extrato.png" width="210" alt="Importação de extrato">
</p>

## Tecnologias

Python 3.11 · Flask · SQLAlchemy · Flask-Migrate (Alembic) · Flask-Login · Flask-WTF · SQLite (MySQL opcional)
· openpyxl (Excel) · Jinja2 + CSS próprio (mobile-first, com manifest para adicionar à tela inicial do celular)
· pytest

## Rodar no computador (com dados fictícios)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.exemplo .env              # e preencha a SECRET_KEY
.\.venv\Scripts\flask db upgrade    # cria as tabelas
.\.venv\Scripts\flask dados-demo    # usuário, vendas, despesas e um extrato CSV falso
.\.venv\Scripts\flask run
```

Abra http://127.0.0.1:5000 e entre com `demo@exemplo.com` / `demo12345`.

O `dados-demo` também grava `demo/extrato_mercado_pago_demo.csv`: use-o em **Vendas → Importar extrato**
para testar a importação. O comando recusa rodar se o banco já tiver dados, para nunca misturar a demonstração
com informações reais.

No Linux/macOS, troque `.\.venv\Scripts\` por `.venv/bin/` e `copy` por `cp`.

## Comandos

| Comando | O que faz |
|---|---|
| `flask db upgrade` | Aplica as migrações no banco |
| `flask db migrate -m "..."` | Gera migração depois de mudar `app/models.py` |
| `flask dados-demo` | Popula um banco vazio com dados fictícios |
| `flask dados-iniciais` | Cadastra só as categorias e formas de pagamento padrão |
| `flask criar-usuario` | Cria um login (não há cadastro aberto no site) |
| `flask trocar-senha` | Troca a senha de um usuário |
| `flask backup` | Copia o banco SQLite para a pasta de backups |

## Testes

```powershell
.\.venv\Scripts\pip install pytest
.\.venv\Scripts\python -m pytest
```

São 96 testes automatizados (login, vendas, despesas, parcelas, despesas fixas, relatórios, importação de
extrato, planilha, backup, assistente e dados de demonstração).

## Estrutura

- `app/models.py` — tabelas (usuários, categorias, formas de pagamento, receitas, despesas, parcelas, fixas)
- `app/receitas.py`, `app/despesas.py`, `app/fixas.py` — telas e regras de vendas, despesas e contas fixas
- `app/importacao.py` — leitura do extrato CSV do Mercado Pago
- `app/relatorios.py`, `app/planilha.py` — relatórios e exportação para Excel
- `app/assistente.py` — assistente de IA com ferramentas somente leitura
- `app/demo.py` — gerador de dados fictícios
- `migrations/` — histórico de mudanças do banco (Alembic)
- `tests/` — testes com pytest

## Publicação

O guia [DEPLOY.md](DEPLOY.md) descreve como publicar no PythonAnywhere (conta gratuita, SQLite, backup
automático no primeiro acesso do dia).
