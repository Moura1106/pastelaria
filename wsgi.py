import os

from dotenv import load_dotenv

# Caminho explícito: no PythonAnywhere o servidor não roda a partir da pasta do projeto
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from app import create_app  # noqa: E402  (precisa vir depois do load_dotenv)

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
