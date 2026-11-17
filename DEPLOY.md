# Publicar no PythonAnywhere

Guia para colocar o Caixa da Pastelaria no ar. Onde aparecer `SEU_USUARIO`, use o seu usuário do PythonAnywhere.

> **Conta gratuita:** permite 1 site e **não tem MySQL**. O sistema usa **SQLite** (um arquivo de banco),
> que atende bem poucos usuários. O banco fica em `~/dados/pastelaria.db`, separado do código,
> para que atualizar o sistema nunca apague os dados.
> Num plano pago dá para usar MySQL: em vez de `DATABASE_URL`, coloque `MYSQL_BANCO='SEU_USUARIO$pastelaria'` no `.env`
> (a senha é lida do `~/.my.cnf`, criado ao definir a senha na aba Databases).

---

## 1. Enviar o código

1. No computador, na pasta do projeto: `.venv\Scripts\python deploy\empacotar.py`
   (gera `dist\pastelaria.zip`, sem o banco local, o `.env` e a `.venv`).
2. No PythonAnywhere, aba **Files**: envie o `pastelaria.zip` para `/home/SEU_USUARIO/`.
3. Num **Bash console**:
   ```bash
   cd ~ && unzip -o -q pastelaria.zip && rm pastelaria.zip
   ```

## 2. Instalar e configurar (Bash console)

```bash
python3.11 -m venv ~/.virtualenvs/pastelaria
source ~/.virtualenvs/pastelaria/bin/activate
pip install -r ~/pastelaria/requirements.txt
mkdir -p ~/dados

printf "SECRET_KEY=%s\nDATABASE_URL=sqlite:////home/$USER/dados/pastelaria.db\nPASTA_BACKUPS=/home/$USER/backups\nCOOKIE_SECURE=1\n" \
  "$(python -c 'import secrets;print(secrets.token_hex(32))')" > ~/pastelaria/.env
chmod 600 ~/pastelaria/.env

cd ~/pastelaria && export FLASK_APP=wsgi
flask db upgrade
flask dados-iniciais
flask criar-usuario     # usuária principal
flask criar-usuario     # segundo usuário
```

## 3. Criar o site

Aba **Web** → **Add a new web app** → **Manual configuration** → **Python 3.11**. Depois, na mesma aba:

| Campo | Valor |
|---|---|
| Source code | `/home/SEU_USUARIO/pastelaria` |
| Virtualenv | `/home/SEU_USUARIO/.virtualenvs/pastelaria` |
| Static files | URL `/static/` → Directory `/home/SEU_USUARIO/pastelaria/app/static` |
| Force HTTPS | **Enabled** |

Arquivo WSGI (no Bash console):
```bash
sed "s/SEU_USUARIO/$USER/" ~/pastelaria/deploy/wsgi_pythonanywhere.py > /var/www/$(echo $USER | tr A-Z a-z)_pythonanywhere_com_wsgi.py
```
Clique em **Reload** na aba Web e abra `https://SEU_USUARIO.pythonanywhere.com`.
Se der erro, veja o **Error log** na aba Web.

## 4. Backup diário

A conta gratuita não tem tarefas agendadas, então o próprio sistema faz o backup: **no primeiro acesso de cada dia**
ele guarda uma cópia do banco em `PASTA_BACKUPS` (`~/backups`, últimos 30 dias). Para fazer um backup na hora,
no Bash console (virtualenv ativo, na pasta do projeto, `FLASK_APP=wsgi`): `flask backup`.

Além disso, de vez em quando baixe a **planilha do ano** em Relatórios e guarde no computador.

**Restaurar um backup** (só em caso de perda de dados; substitui o banco atual):
```bash
gunzip -c ~/backups/pastelaria-AAAA-MM-DD.db.gz > ~/dados/pastelaria.db
```
e clique em **Reload** na aba Web.

## 5. Instalar no celular

- **Android (Chrome):** abra o endereço → menu ⋮ → **Adicionar à tela inicial**.
- **iPhone (Safari):** abra o endereço → botão Compartilhar → **Adicionar à Tela de Início**.

Ela entra uma vez com "Manter conectado" marcado e fica logada por 30 dias naquele aparelho.

## 6. Manutenção

- **Conta gratuita:** o site precisa ser renovado **todo mês**. Entre no PythonAnywhere e, na aba Web, clique em
  "Run until 1 month from today" (a aba mostra até quando o site está ativo; o PythonAnywhere manda um
  e-mail uma semana antes de desativar).
- **Atualizar o sistema** depois de mudanças: gere e envie o zip (passo 1) e, no Bash console:
  ```bash
  source ~/.virtualenvs/pastelaria/bin/activate && cd ~/pastelaria && export FLASK_APP=wsgi
  flask backup
  pip install -r requirements.txt
  flask db upgrade
  ```
  e clique em **Reload** na aba Web.
- **Esqueceram a senha:** no Bash console, `flask trocar-senha` (com o virtualenv ativo, na pasta do projeto e `FLASK_APP=wsgi`).
- **Login travado:** depois de 5 senhas erradas seguidas, aquele e-mail fica bloqueado por 15 minutos.
