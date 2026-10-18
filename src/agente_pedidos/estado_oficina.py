"""Estado de la oficina para el asistente de chat (solo lectura).

Lo mismo que ve el director en la torre de control, resumido para el modelo: aprobaciones
pendientes (de los checkpoints), tareas del día con su paso actual y pedidos creados hoy (de
``eventos.jsonl``). No escribe nada y no habla con el ERP: así el asistente puede contestar
«¿en qué estado está el pedido de Adatum?» aunque ese pedido todavía no exista en Business Central.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import eventos
from .formato import euros
from .workflow import aprobaciones_pendientes, crear_storage


def _hora(ts: str | None) -> str | None:
    return datetime.fromisoformat(ts).astimezone().strftime("%H:%M") if ts else None


def _leer(datos: Any, clave: str, defecto: Any = None) -> Any:
    return datos.get(clave, defecto) if isinstance(datos, dict) else getattr(datos, clave, defecto)


async def estado_oficina(checkpoints: str | Path | None = None, ruta_eventos: str | Path | None = None, dia: date | None = None) -> dict[str, Any]:
    """Aprobaciones pendientes, tareas del día (sin las preguntas) y pedidos creados hoy."""
    storage = crear_storage(checkpoints or os.environ.get("AGENTE_CHECKPOINTS", "checkpoints"))
    pendientes = []
    for checkpoint in await aprobaciones_pendientes(storage):
        for evento in checkpoint.pending_request_info_events.values():
            datos = _leer(evento, "data")
            validado = _leer(datos, "pedido_validado", {}) or {}
            pendientes.append(
                {
                    "cliente": f"{_leer(datos, 'numero_cliente') or '?'} {_leer(datos, 'nombre_cliente') or ''}".strip(),
                    "importe": euros(_leer(datos, "total")),
                    "motivo": "; ".join(_leer(datos, "motivos", []) or []),
                    "referencia_cliente": validado.get("referencia_cliente"),
                    "lineas": [f"{l.get('cantidad'):g} × {l.get('numero_articulo')} {l.get('descripcion')} ({euros(l.get('importe'))})" for l in validado.get("lineas", [])],
                    "esperando_desde": _hora(checkpoint.timestamp),
                    "erp": "simulado" if _leer(datos, "modo_erp") == "demo" else "Business Central",
                    "tarea": _leer(datos, "tarea"),
                    "quien_decide": "el director, desde la oficina o con el comando reanudar",
                }
            )

    lista = eventos.leer_eventos(Path(ruta_eventos) if ruta_eventos else None, dia=dia or date.today())
    tareas: dict[str, dict[str, Any]] = {}
    for evento in lista:
        if not evento.get("tarea"):
            continue
        tarea = tareas.setdefault(evento["tarea"], {"tarea": evento["tarea"], "clase": "pedido", "paso_actual": None, "estado": "en curso"})
        tipo, datos = evento["tipo"], evento["datos"]
        if tipo == "tarea_iniciada":
            tarea.update(origen=datos.get("origen"), inicio=_hora(evento["ts"]), clase=datos.get("clase") or "pedido")
        elif tipo == "paso":
            tarea["paso_actual"] = datos.get("descripcion") or datos.get("nombre")
        elif tipo == "aprobacion_solicitada":
            tarea["estado"] = "esperando aprobación"
        elif tipo == "aprobacion_resuelta":
            tarea["estado"] = "en curso"
        elif tipo == "error":
            tarea["estado"] = "error"
        elif tipo == "tarea_terminada":
            tarea.update(estado="terminada", resultado=datos.get("resultado"), pedido=datos.get("pedido"))
    pedidos = [
        {"pedido": e["datos"].get("pedido"), "cliente": e["datos"].get("cliente"), "importe": euros(e["datos"].get("importe")), "hora": _hora(e["ts"]), "erp": "simulado" if e["datos"].get("modo") == "demo" else "Business Central"}
        for e in lista
        if e["tipo"] == "erp_escritura"
    ]
    return {
        "aprobaciones_pendientes": pendientes,
        "tareas_de_hoy": [{k: v for k, v in t.items() if k != "clase"} for t in tareas.values() if t["clase"] != "pregunta"],
        "pedidos_creados_hoy": pedidos,
    }
