"""Capa determinista (sw_*), SIN LLM. Incluye los 13 casos de la fase 2 de docs/PLAN.md."""
import json
from datetime import timedelta

from sqlalchemy import select, update

from app import db
from app.config import hoy_lima
from app.servicios import agenda, cotizacion, jefe, programados, solicitudes

S1, S2 = "sesion-1", "sesion-2"


def habil(n):
    d = hoy_lima() + timedelta(days=n)
    return (d + timedelta(days=1) if d.weekday() == 6 else d).isoformat()


def datos(placa="BXR-742", fecha=None, desc="mantenimiento de 10 000 km"):
    return {"telefono": "987654321", "placa": placa, "vehiculo": "Toyota Yaris 2020", "kilometraje": 10000,
            "fecha_deseada": fecha or habil(2), "descripcion_falla": desc}


def registrar(tipo="preventivo", conf=0.95, sesion=S1, **kw):
    return solicitudes.registrar(datos(**kw), tipo, conf, "normal", "general", sesion)


PREV_10K = [{"codigo": "MO-PREV-10K", "cantidad": 1}, {"codigo": "REP-ACE-5W30", "cantidad": 1},
            {"codigo": "REP-FILT-ACE", "cantidad": 1}, {"codigo": "REP-FILT-AIRE", "cantidad": 1}]


def cotizada(**kw):
    r = registrar(**kw)
    assert cotizacion.cotizar(r["clave"], PREV_10K, kw.get("sesion", S1))["ok"]
    return r["clave"]


# --- compuerta de riesgo ---------------------------------------------------------------
def test_preventivo_confianza_alta_va_a_cotizar():
    assert registrar(conf=0.95)["estado"] == "lista_para_cotizar"


def test_preventivo_confianza_baja_va_al_jefe():
    assert registrar(conf=0.85)["estado"] == "revision_jefe"


def test_correctivo_siempre_va_al_jefe():
    assert registrar(tipo="correctivo", conf=0.99)["estado"] == "revision_jefe"


def test_sintoma_detectado_aunque_el_agente_diga_preventivo():
    r = registrar(desc="Es solo mantenimiento, aunque se apaga en los semáforos")
    assert r["estado"] == "revision_jefe" and "síntomas" in r["motivo_revision"]


def test_confianza_invalida_se_trata_como_cero():
    assert registrar(conf="no-se")["estado"] == "revision_jefe"


# --- idempotencia y aislamiento --------------------------------------------------------
def test_registrar_dos_veces_es_idempotente():
    a, b = registrar(), registrar()
    assert b["ya_existia"] and a["clave"] == b["clave"]
    assert len(solicitudes.de_sesion(S1)) == 1


def test_otra_sesion_no_ve_datos():
    clave = registrar()["clave"]
    r = registrar(sesion=S2)
    assert r == {"ok": True, "ya_existia": True, "misma_sesion": False}
    assert solicitudes.consultar(clave, S2) == {"ok": True, "existe": True, "misma_sesion": False}
    assert solicitudes.consultar(clave, S1)["solicitud"]["estado"] == "lista_para_cotizar"


def test_contrato_invalido_no_escribe():
    r = solicitudes.registrar({**datos(), "telefono": "123"}, "preventivo", 1, "normal", "general", S1)
    assert not r["ok"] and r["error"] == "contrato"
    assert solicitudes.de_sesion(S1) == []


# --- cotización ------------------------------------------------------------------------
def test_no_se_cotiza_sin_aprobacion_del_jefe():
    clave = registrar(tipo="correctivo")["clave"]
    r = cotizacion.cotizar(clave, PREV_10K, S1)
    assert r["error"] == "estado_no_cotizable"


def test_total_10k_es_355_con_precios_del_catalogo():
    r = registrar()
    c = cotizacion.cotizar(r["clave"], PREV_10K, S1)
    assert c["ok"] and c["total"] == 355 and not c["requiere_proveedor"]
    assert "355" in c["texto_cliente"]


def test_codigo_inventado_no_guarda_nada():
    r = registrar()
    c = cotizacion.cotizar(r["clave"], PREV_10K + [{"codigo": "REP-INVENTADO", "cantidad": 1}], S1)
    assert c["error"] == "items_invalidos"
    assert solicitudes.consultar(r["clave"], S1)["solicitud"]["estado"] == "lista_para_cotizar"


def test_repuesto_sin_stock_marca_bajo_pedido():
    clave = registrar(tipo="correctivo", desc="golpeteo en la suspensión")["clave"]
    jefe.decidir(clave, "aprobar", "correctivo", "normal", "frenos_suspension", "Cambiar amortiguadores")
    c = cotizacion.cotizar(clave, [{"codigo": "MO-SUSP", "cantidad": 1}, {"codigo": "REP-AMORT", "cantidad": 2}], S1)
    assert c["ok"] and c["requiere_proveedor"]
    assert any(i["codigo"] == "REP-AMORT" and i["bajo_pedido"] for i in c["items"])


def test_otra_sesion_no_puede_cotizar():
    clave = registrar()["clave"]
    assert cotizacion.cotizar(clave, PREV_10K, S2)["error"] == "no_encontrada"


def test_catalogo_del_agente_no_expone_precios():
    fila = cotizacion.catalogo_para_agente()[0]
    assert "precio_unitario" not in fila and "stock" not in fila


# --- agenda ----------------------------------------------------------------------------
def test_proponer_sabado_en_la_tarde_solo_15h_de_la_especialidad():
    clave = cotizada()
    d = hoy_lima() + timedelta(days=1)
    sabado = d + timedelta(days=(5 - d.weekday()) % 7)
    r = agenda.proponer(clave, S1, sabado.isoformat(), "tarde")
    assert r["ok"] and len(r["opciones"]) == 3
    assert all(o["hora"] == "15:00" and o["mecanico"] == "Técnico A" for o in r["opciones"])
    assert r["opciones"][0]["fecha"] == sabado.isoformat()


def test_reservar_turno_no_propuesto():
    clave = cotizada()
    agenda.proponer(clave, S1)
    assert agenda.reservar(clave, S1, turno_id="T-000000-08-A")["error"] == "turno_no_propuesto"


def test_reservar_dos_veces_es_idempotente():
    clave = cotizada()
    agenda.proponer(clave, S1)
    a = agenda.reservar(clave, S1, opcion=2)
    b = agenda.reservar(clave, S1, opcion=2)
    assert a["ok"] and b["ok"] and b["ya_reservado"]
    assert solicitudes.consultar(clave, S1)["solicitud"]["estado"] == "agendada"


def test_reservar_turno_ocupado():
    clave = cotizada()
    op = agenda.proponer(clave, S1)["opciones"][0]
    with db.engine().begin() as c:
        c.execute(update(db.agenda).where(db.agenda.c.turno_id == op["turno_id"])
                  .values(estado="reservado", clave_solicitud="TEST-OCUPADO"))
    assert agenda.reservar(clave, S1, opcion=1)["error"] == "turno_ocupado"
    assert solicitudes.consultar(clave, S1)["solicitud"]["estado"] == "cotizada"


def test_especialidad_del_turno_viene_de_la_fila():
    clave = registrar(tipo="correctivo", desc="chirría al frenar")["clave"]
    jefe.decidir(clave, "aprobar", "correctivo", "alta", "frenos_suspension", "Cambiar pastillas")
    cotizacion.cotizar(clave, [{"codigo": "MO-FRENOS", "cantidad": 1}], S1)
    assert all(o["mecanico"] == "Técnico C" for o in agenda.proponer(clave, S1)["opciones"])


def test_agenda_se_genera_desde_hoy_sin_domingos():
    filas = agenda.ver_agenda(dias=14)
    assert filas and filas[0]["fecha"] >= hoy_lima().isoformat()
    from datetime import date
    assert all(date.fromisoformat(f["fecha"]).weekday() != 6 for f in filas)


# --- jefe, SLA, seguimiento, rechazo ----------------------------------------------------
def test_jefe_aprueba_por_clave_y_guarda_ambas_clasificaciones():
    clave = registrar(tipo="correctivo", conf=0.8)["clave"]
    assert jefe.decidir(clave, "aprobar", "correctivo", "alta", "motor_electrico", "Escanear")["ok"]
    f = solicitudes.consultar(clave, S1)["solicitud"]
    assert f["estado"] == "validada_jefe" and f["especialidad"] == "motor_electrico"
    assert jefe.metricas_acuerdo()["casos_decididos"] == 1


def test_jefe_no_aprueba_sin_observacion():
    clave = registrar(tipo="correctivo")["clave"]
    assert jefe.decidir(clave, "aprobar", observacion="")["error"] == "observacion_requerida"


def _envejecer(clave, horas):
    with db.engine().begin() as c:
        ts = c.execute(select(db.solicitudes.c.ts_estado).where(db.solicitudes.c.clave == clave)).scalar()
        c.execute(update(db.solicitudes).where(db.solicitudes.c.clave == clave).values(ts_estado=ts - timedelta(hours=horas)))


def test_sla_2h_escala_a_recepcion():
    clave = registrar(tipo="correctivo")["clave"]
    _envejecer(clave, 3)
    assert clave in programados.vencer_sla_revision()
    assert solicitudes.consultar(clave, S1)["solicitud"]["estado"] == "escalada_recepcion"
    assert jefe.decidir(clave, "aprobar", observacion="ok")["ok"]


def test_seguimiento_48h():
    clave = cotizada()
    _envejecer(clave, 49)
    assert clave in programados.seguimiento_48h()
    agenda.proponer(clave, S1)
    assert agenda.reservar(clave, S1, opcion=1)["ok"]


def test_rechazar_y_transicion_invalida():
    clave = cotizada()
    agenda.proponer(clave, S1)
    agenda.reservar(clave, S1, opcion=1)
    r = solicitudes.rechazar(clave, S1)
    assert r["error"] == "transicion_invalida" and r["estado_actual"] == "agendada"
    clave2 = cotizada(placa="ZZZ-111")
    assert solicitudes.rechazar(clave2, S1)["estado"] == "rechazada"


def test_historial_registra_cada_transicion():
    clave = cotizada()
    with db.engine().connect() as c:
        estados = [r.estado_nuevo for r in c.execute(select(db.historial).where(db.historial.c.clave == clave)
                                                     .order_by(db.historial.c.id))]
    assert estados == ["lista_para_cotizar", "cotizada"]


def test_turnos_propuestos_se_guardan_como_json_texto():
    clave = cotizada()
    agenda.proponer(clave, S1)
    fila = solicitudes.de_sesion(S1)[0]
    assert isinstance(fila["turnos_propuestos"], str) and json.loads(fila["turnos_propuestos"])[0]["opcion"] == 1
