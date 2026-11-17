"""Gera dist/pastelaria.zip para enviar ao PythonAnywhere (sem venv, banco local, .env e caches).

Uso, na pasta do projeto:  .venv\\Scripts\\python deploy\\empacotar.py
"""
import os
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "dist", "pastelaria.zip")
# Extratos de exemplo têm dados reais de vendas: ficam só no computador
IGNORAR_PASTAS = {".venv", "__pycache__", ".pytest_cache", ".git", "dist", "ARQUIVO CSV", "exemplos"}
IGNORAR_ARQUIVOS = {".env", "pastelaria.db"}

os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
with zipfile.ZipFile(DESTINO, "w", zipfile.ZIP_DEFLATED) as zf:
    for pasta, subpastas, arquivos in os.walk(RAIZ):
        subpastas[:] = [p for p in subpastas if p not in IGNORAR_PASTAS]
        for nome in arquivos:
            if nome in IGNORAR_ARQUIVOS or nome.endswith(".pyc"):
                continue
            caminho = os.path.join(pasta, nome)
            # Barras normais: o unzip do Linux trata "\" como parte do nome do arquivo
            zf.write(caminho, "pastelaria/" + os.path.relpath(caminho, RAIZ).replace(os.sep, "/"))

print(f"Pacote criado: {DESTINO}")
