import pathlib
import sys

# Permite importar os modulos do projeto (data, modules, utils) sem instalar o pacote.
RAIZ = pathlib.Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
