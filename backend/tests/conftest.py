import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="movicar-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["MODO_PRUEBAS"] = "true"
os.environ["TEST_TOKEN"] = "token-pruebas"
os.environ["JEFE_USUARIO"] = "jefe"
os.environ["JEFE_CLAVE"] = "clave-pruebas"

from app import db  # noqa: E402


@pytest.fixture(autouse=True)
def bd_limpia():
    """Cada prueba arranca con catálogo real y agenda generada desde hoy."""
    db.metadata.drop_all(db.engine())
    db.inicializar()
    yield
