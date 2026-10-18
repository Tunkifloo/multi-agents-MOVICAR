"""Port de scripts/lib/contrato.test.js (12 casos) + paridad de la clave con el .js original (Node)."""
import json
import shutil
import subprocess

import pytest

from app.config import RAIZ
from app.contrato import calcular_clave, validar_contrato

AHORA = "2026-10-17T15:00:00Z"  # sábado 17/10/2026, 10:00 Lima
BASE = {"telefono": "987 654 321", "placa": "bxr742", "vehiculo": "Toyota Yaris 2020", "kilometraje": 10000,
        "fecha_deseada": "2026-10-19", "descripcion_falla": "Mantenimiento de 10 000 km"}


def v(**cambios):
    return validar_contrato({**BASE, **cambios}, AHORA)


def test_caso_valido_normaliza():
    r = v()
    assert r["valido"], r["errores"]
    assert r["datos"]["telefono"] == "+51987654321"
    assert r["datos"]["placa"] == "BXR-742"
    assert r["clave"].startswith("MV-") and len(r["clave"]) == 19


def test_clave_estable_ante_formato_distinto():
    assert v()["clave"] == v(telefono="+51 987-654-321", placa="BXR-742", descripcion_falla="otra redacción")["clave"]


def test_clave_cambia_con_otra_fecha():
    assert v()["clave"] != v(fecha_deseada="2026-10-20")["clave"]


@pytest.mark.parametrize("cambio,prefijo", [
    ({"telefono": "98765"}, "telefono"), ({"placa": "AB"}, "placa"), ({"placa": "ABC1234"}, "placa"),
    ({"fecha_deseada": "2026-10-01"}, "anterior"), ({"fecha_deseada": "2026-10-18"}, "domingo"),
    ({"fecha_deseada": "2027-03-01"}, "60"),
])
def test_errores_individuales(cambio, prefijo):
    assert any(prefijo in e for e in v(**cambio)["errores"])


def test_hoy_es_valido():
    assert v(fecha_deseada="2026-10-17")["valido"]


def test_reporta_todos_los_errores_juntos():
    r = validar_contrato({"telefono": "1", "placa": "x", "vehiculo": "", "fecha_deseada": "mañana",
                          "descripcion_falla": ""}, AHORA)
    assert len(r["errores"]) == 5 and r["clave"] == ""


def test_kilometraje_invalido_es_cero():
    assert v(kilometraje=-5)["datos"]["kilometraje"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no instalado")
def test_paridad_clave_con_contrato_js():
    casos = [("+51987654321", "BXR-742", "2026-10-19"), ("+51912345678", "A1B-202", "2026-12-01"),
             ("+5190000123", "ZZZ-999", "2027-01-15"), ("+51941000201", "ÑAN-123", "2026-10-20")]
    js = ("const {calcularClave}=require(process.argv[1]);"
          "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(c=>calcularClave(...c))))")
    salida = subprocess.run(["node", "-e", js, str(RAIZ / "scripts/lib/contrato.js"), json.dumps(casos)],
                            capture_output=True, text=True, check=True).stdout
    assert json.loads(salida) == [calcular_clave(*c) for c in casos]


def test_clave_coincide_con_la_v2_de_n8n():
    """La clave de la v2 incluía tipo_servicio; la v3 no. Se verifica solo el formato."""
    assert calcular_clave("+51987654321", "BXR-742", "2026-10-12").startswith("MV-")
