"""API sin LLM: autenticación del personal, bandeja del jefe, utilidad de pruebas y vistas."""
import base64

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.servicios import solicitudes
from tests.test_servicios import S1, registrar

AUTH = {"Authorization": "Basic " + base64.b64encode(b"jefe:clave-pruebas").decode()}
TOKEN = {"X-Test-Token": "token-pruebas"}


@pytest.fixture
def cli():
    with TestClient(app) as c:
        yield c


def test_salud(cli):
    r = cli.get("/api/salud").json()
    assert r["ok"] and r["umbral_confianza"] == 0.9


def test_vistas_del_personal_requieren_credenciales(cli):
    for ruta in ("/api/jefe/pendientes", "/api/solicitudes", "/api/agenda", "/api/fallos", "/api/catalogo"):
        assert cli.get(ruta).status_code == 401
        assert cli.get(ruta, headers=AUTH).status_code == 200


def test_bandeja_del_jefe_aprueba_por_clave(cli):
    clave = registrar(tipo="correctivo", desc="chirría al frenar")["clave"]
    pend = cli.get("/api/jefe/pendientes", headers=AUTH).json()
    assert [p["clave"] for p in pend] == [clave] and pend[0]["sla_vencido"] is False
    r = cli.post("/api/jefe/decision", headers=AUTH, json={"clave": clave, "decision": "aprobar",
                 "tipo_servicio": "correctivo", "prioridad": "alta", "especialidad": "frenos_suspension",
                 "observacion": "Cambiar pastillas delanteras"}).json()
    assert r["estado"] == "validada_jefe"
    det = cli.get(f"/api/solicitudes/{clave}", headers=AUTH).json()
    assert [h["estado_nuevo"] for h in det["historial"]] == ["revision_jefe", "validada_jefe"]


def test_utilidad_de_pruebas_protegida_por_token(cli):
    assert cli.post("/api/pruebas", json={"accion": "listar"}).status_code == 404
    assert cli.post("/api/pruebas", json={"accion": "listar"}, headers=TOKEN).status_code == 200


def test_utilidad_reset_solo_borra_telefonos_de_prueba(cli):
    registrar()  # celular real ficticio +51987654321: reset no lo toca
    solicitudes.registrar({"telefono": "+5190000123", "placa": "TST-001", "vehiculo": "Kia Rio 2019",
                           "fecha_deseada": registrar.__globals__["habil"](3), "descripcion_falla": "aceite"},
                          "preventivo", 1, "normal", "general", "s-test")
    r = cli.post("/api/pruebas", json={"accion": "reset"}, headers=TOKEN).json()
    assert r["borradas"] == 1 and len(solicitudes.de_sesion(S1)) == 1


def test_conversaciones(cli):
    c = cli.post("/api/conversaciones").json()
    assert c["session_id"].startswith("web-")
    assert any(x["session_id"] == c["session_id"] for x in cli.get("/api/conversaciones").json())
    assert cli.get(f"/api/conversaciones/{c['session_id']}/solicitud").json() == {"existe": False}
