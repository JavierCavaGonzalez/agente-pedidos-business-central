"""Registro operativo de eventos: lo que la oficina de agentes dibuja.

Cada línea de ``eventos.jsonl`` (ruta en ``AGENTE_EVENTOS``) es un evento::

    {"ts": "2026-10-18T14:03:12.481+02:00", "agente": "pedidos", "tarea": "tarea_20261018_a3f9",
     "tipo": "paso", "datos": {"nombre": "validar", "descripcion": "..."}}

Principio: *nada sin rastro*. La interfaz solo dibuja lo que está aquí. ``auditoria.jsonl``
sigue siendo el registro de auditoría; este es el registro operativo, pensado para leerse en
vivo. Nunca lleva secretos: los argumentos y los errores se resumen antes de escribirse.

Tipos: ``tarea_iniciada``, ``paso``, ``modelo_llamada``, ``herramienta``,
``aprobacion_solicitada``, ``aprobacion_resuelta``, ``erp_escritura``, ``erp_bloqueada``,
``tarea_terminada``, ``error`` y, desde la oficina, ``agente_detenido`` y ``agente_activado``.

La tarea en curso viaja en una ``ContextVar`` (``fijar_tarea``): la CLI la fija al empezar y
el workflow y el middleware la leen sin tener que pasarla de mano en mano.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
from contextvars import ContextVar
from datetime import date, datetime
from pathlib import Path
from typing import Any

AGENTE_PEDIDOS = "pedidos"

TIPOS = (
    "tarea_iniciada",
    "paso",
    "modelo_llamada",
    "herramienta",
    "aprobacion_solicitada",
    "aprobacion_resuelta",
    "erp_escritura",
    "erp_bloqueada",
    "tarea_terminada",
    "error",
    "agente_detenido",
    "agente_activado",
)

_TAREA: ContextVar[str | None] = ContextVar("tarea", default=None)
_CERROJO = threading.Lock()
_CORREO = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def ruta_eventos() -> Path:
    return Path(os.environ.get("AGENTE_EVENTOS", "eventos.jsonl"))


def nueva_tarea_id() -> str:
    """``tarea_<AAAAMMDD>_<4 hex>``: legible, ordenable por fecha y sin colisiones prácticas en un día."""
    return f"tarea_{date.today():%Y%m%d}_{secrets.token_hex(2)}"


def fijar_tarea(tarea: str | None) -> None:
    _TAREA.set(tarea)


def tarea_actual() -> str | None:
    return _TAREA.get()


def emitir(tipo: str, agente: str = AGENTE_PEDIDOS, tarea: str | None = None, *, fichero: Path | None = None, **datos: Any) -> dict[str, Any]:
    """Añade un evento a ``eventos.jsonl`` (o a ``fichero``) y lo devuelve. Nunca interrumpe al agente si falla."""
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de evento desconocido: {tipo}")
    evento = {
        "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "agente": agente,
        "tarea": tarea if tarea is not None else tarea_actual(),
        "tipo": tipo,
        "datos": datos,
    }
    linea = json.dumps(evento, ensure_ascii=False, default=str) + "\n"
    try:
        ruta = fichero or ruta_eventos()
        # Una sola escritura por línea en modo «append»: varios procesos (procesar, reanudar,
        # el backend) pueden escribir a la vez sin mezclar líneas.
        # newline="\n": el mismo formato en Windows que en Linux (sin \r\n).
        with _CERROJO, ruta.open("a", encoding="utf-8", newline="\n") as fichero:
            fichero.write(linea)
    except OSError:
        pass  # el registro operativo no puede tumbar una escritura en el ERP
    return evento


def leer_eventos(ruta: Path | None = None, dia: date | None = None) -> list[dict[str, Any]]:
    """Eventos del fichero (todos, o solo los de ``dia`` según su hora local)."""
    ruta = ruta or ruta_eventos()
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    eventos = []
    for linea in lineas:
        try:
            evento = json.loads(linea)
        except json.JSONDecodeError:
            continue  # una línea a medio escribir: se leerá completa en la siguiente pasada
        if dia is None or datetime.fromisoformat(evento["ts"]).date() == dia:
            eventos.append(evento)
    return eventos


# --- resúmenes sin datos sensibles -------------------------------------------------------------


def resumir_correo(texto: str, max_caracteres: int = 160) -> str:
    """Primeras líneas útiles del correo, sin remitente ni direcciones de correo."""
    utiles = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.lower().startswith(("de:", "from:", "para:", "to:", "cc:")):
            continue
        utiles.append(_CORREO.sub("[correo]", linea))
        if len(utiles) == 3:
            break
    resumen = " · ".join(utiles)
    return resumen if len(resumen) <= max_caracteres else resumen[: max_caracteres - 1] + "…"


def resumir_argumentos(argumentos: dict[str, Any], max_caracteres: int = 80) -> dict[str, Any]:
    """Argumentos de una herramienta, recortados y sin claves que parezcan secretos."""
    resumen: dict[str, Any] = {}
    for clave, valor in argumentos.items():
        if any(s in clave.lower() for s in ("secret", "token", "password", "clave", "key")):
            resumen[clave] = "***"
        elif isinstance(valor, str):
            resumen[clave] = valor if len(valor) <= max_caracteres else valor[: max_caracteres - 1] + "…"
        elif isinstance(valor, list):
            resumen[clave] = valor[:5]
        else:
            resumen[clave] = valor
    return resumen


def resumir_error(error: BaseException | str, max_caracteres: int = 300) -> str:
    """Tipo y mensaje del error, sin traza y sin URLs (pueden llevar el tenant)."""
    texto = error if isinstance(error, str) else f"{type(error).__name__}: {error}"
    texto = re.sub(r"https?://\S+", "<url>", texto)
    texto = re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "<id>", texto)
    texto = texto.splitlines()[0] if texto else texto
    return texto if len(texto) <= max_caracteres else texto[: max_caracteres - 1] + "…"
