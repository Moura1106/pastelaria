# Conteúdo para colar no arquivo WSGI do PythonAnywhere (aba Web > "WSGI configuration file").
# Troque SEU_USUARIO pelo seu usuário do PythonAnywhere.
import sys

CAMINHO = "/home/SEU_USUARIO/pastelaria"
if CAMINHO not in sys.path:
    sys.path.insert(0, CAMINHO)

from wsgi import app as application  # noqa: E402,F401
