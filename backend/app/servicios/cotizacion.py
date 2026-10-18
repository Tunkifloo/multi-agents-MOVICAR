"""consultar_catalogo (solo lectura, SIN precios) · sw_cotizar.

Defecto 1 de la v2: calcular_cotizacion recibía precio y stock transcritos por el LLM.
Aquí el agente envía solo {codigo, cantidad}; el precio y el stock se leen del tarifario.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from ..config import reglas
from ..db import catalogo, engine
from .estados import TransicionInvalida, cambiar_estado
from .solicitudes import leer


def catalogo_para_agente() -> list[dict[str, Any]]:
    """Lo que ve el agente cotizador: códigos y reglas de uso. Nunca precio ni stock."""
    with engine().connect() as c:
        filas = c.execute(select(catalogo.c.codigo, catalogo.c.concepto, catalogo.c.tipo, catalogo.c.categoria,
                                 catalogo.c.especialidad, catalogo.c.aplica_a).order_by(catalogo.c.codigo)).all()
    return [dict(f._mapping) for f in filas]


def catalogo_completo() -> list[dict[str, Any]]:
    with engine().connect() as c:
        return [dict(f._mapping) for f in c.execute(select(catalogo).order_by(catalogo.c.codigo)).all()]


def _soles(x: float) -> str:
    return f"S/ {x:,.2f}".replace(",", " ")


def texto_cotizacion(items: list[dict], total: float, bajo_pedido: list[str]) -> str:
    """Bloque Markdown generado por código: el orquestador lo pega tal cual (no transcribe montos)."""
    lineas = []
    for i in items:
        cant = f" × {i['cantidad']}" if i["cantidad"] > 1 else ""
        marca = " *(bajo pedido)*" if i["bajo_pedido"] else ""
        lineas.append(f"- {i['concepto']}{cant}: **{_soles(i['subtotal'])}**{marca}")
    lineas.append(f"\n**Total referencial: {_soles(total)}** (sujeto a revisión en el taller)")
    if bajo_pedido:
        lineas.append("\n⚠️ Repuestos bajo pedido: " + ", ".join(bajo_pedido)
                      + ". El precio y el plazo se confirman con el proveedor.")
    return "\n".join(lineas)


def cotizar(clave: str, items: list[dict[str, Any]], session_id: str) -> dict[str, Any]:
    with engine().begin() as c:
        f = leer(c, clave)
        if not f or f["session_id"] != session_id:
            return {"ok": False, "error": "no_encontrada", "mensaje": "No existe una solicitud de esta sesión con esa clave."}
        if f["estado"] not in reglas()["estados_cotizables"]:
            return {"ok": False, "error": "estado_no_cotizable", "estado_actual": f["estado"],
                    "mensaje": "La solicitud aún no puede cotizarse (requiere validación del jefe de taller)."}

        precios = {r.codigo: r for r in c.execute(select(catalogo)).all()}
        agrupado: dict[str, int] = {}
        errores = []
        for it in items or []:
            codigo = str((it or {}).get("codigo", "")).strip().upper()
            if codigo not in precios:
                errores.append({"codigo": codigo, "error": "codigo_inexistente"})
                continue
            try:
                cant = int(round(float((it or {}).get("cantidad", 1))))
            except (TypeError, ValueError):
                cant = 1
            agrupado[codigo] = min(10, max(1, agrupado.get(codigo, 0) + max(1, cant)))
        if errores or not agrupado:
            return {"ok": False, "error": "items_invalidos",
                    "detalle": errores or [{"error": "lista_vacia"}],
                    "mensaje": "Hay códigos que no existen en el catálogo o la lista está vacía."}

        detalle = []
        for codigo, cant in agrupado.items():
            p = precios[codigo]
            subtotal = round(cant * float(p.precio_unitario), 2)
            detalle.append({"codigo": codigo, "concepto": p.concepto, "tipo": p.tipo, "cantidad": cant,
                            "precio_unitario": float(p.precio_unitario), "subtotal": subtotal,
                            "bajo_pedido": p.tipo == "repuesto" and int(p.stock) < cant})
        # mano de obra primero, como en una proforma
        detalle.sort(key=lambda i: (i["tipo"] != "mano_obra", i["codigo"]))
        total = round(sum(i["subtotal"] for i in detalle), 2)
        bajo_pedido = [i["concepto"] for i in detalle if i["bajo_pedido"]]
        try:
            cambiar_estado(c, f, "cotizada", "sw_cotizar",
                           campos={"total_cotizacion": total,
                                   "cotizacion_detalle": json.dumps(detalle, ensure_ascii=False),
                                   "requiere_proveedor": bool(bajo_pedido)},
                           detalle={"total": total, "items": [i["codigo"] for i in detalle]})
        except TransicionInvalida as e:
            return {"ok": False, "error": "transicion_invalida", "estado_actual": e.actual}

    return {"ok": True, "items": detalle, "total": total, "repuestos_bajo_pedido": bajo_pedido,
            "requiere_proveedor": bool(bajo_pedido),
            "texto_cliente": texto_cotizacion(detalle, total, bajo_pedido)}
