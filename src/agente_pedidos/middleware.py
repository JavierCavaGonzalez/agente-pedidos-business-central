"""Middleware: la aduana entre lo que el modelo decide y lo que el código ejecuta.

Agent Framework ofrece tres puntos de interceptación (cap. 4.9 del libro):
- middleware de función: alrededor de cada llamada a una herramienta;
- middleware de chat: alrededor de cada llamada al modelo;
- middleware de agente: alrededor de cada ejecución completa del agente.

Aquí hay tres piezas pequeñas y útiles para un ERP:
1. ``AuditoriaHerramientas``: registra cada herramienta llamada, sus argumentos y un resumen
   del resultado en un fichero JSONL (una línea por evento). Es el «audit trail» del cap. 13.5.
2. ``SoloLectura``: bloquea cualquier herramienta de escritura cuando ``AGENTE_SOLO_LECTURA=1``.
   La herramienta no llega a ejecutarse; el modelo recibe un error de política como dato.
3. ``PresupuestoLlamadas``: limita el número de llamadas al modelo por ejecución. Si se supera,
   devuelve una respuesta fija en lugar de seguir gastando (terminación por presupuesto, cap. 2.5.1).
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_framework import (
    ChatContext,
    ChatMiddleware,
    ChatResponse,
    FunctionInvocationContext,
    FunctionMiddleware,
    Message,
)

HERRAMIENTAS_ESCRITURA = ("crear_", "modificar_", "borrar_", "registrar_")


class AuditoriaHerramientas(FunctionMiddleware):
    """Escribe un registro de auditoría por cada herramienta ejecutada."""

    def __init__(self, ruta: Path | str | None = None) -> None:
        self.ruta = Path(ruta or os.environ.get("AGENTE_AUDITORIA", "auditoria.jsonl"))
        self.eventos: list[dict[str, Any]] = []  # copia en memoria (útil en pruebas y en la CLI)

    async def process(self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        inicio = datetime.now(timezone.utc)
        argumentos = context.arguments
        if not isinstance(argumentos, dict):
            argumentos = {"valor": str(argumentos)}
        await call_next()
        self.registrar({
            "instante": inicio.isoformat(),
            "herramienta": context.function.name,
            "argumentos": argumentos,
            "resultado": _resumir(context.result),
            "duracion_ms": int((datetime.now(timezone.utc) - inicio).total_seconds() * 1000),
        })

    def registrar(self, evento: dict[str, Any]) -> None:
        """Añade un evento al registro (herramientas y también decisiones como una aprobación denegada)."""
        evento = {"instante": datetime.now(timezone.utc).isoformat(), **evento}
        self.eventos.append(evento)
        with self.ruta.open("a", encoding="utf-8") as fichero:
            fichero.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")


class SoloLectura(FunctionMiddleware):
    """Impide las escrituras en el ERP sin tocar las herramientas ni las instrucciones."""

    def __init__(self, activo: bool | None = None) -> None:
        self.activo = activo if activo is not None else os.environ.get("AGENTE_SOLO_LECTURA", "0") == "1"
        self.bloqueadas: list[str] = []

    async def process(self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        nombre = context.function.name
        if self.activo and nombre.startswith(HERRAMIENTAS_ESCRITURA):
            self.bloqueadas.append(nombre)
            # Al no llamar a call_next() la herramienta no se ejecuta; el modelo recibe esto como resultado.
            context.result = {"error": f"La herramienta '{nombre}' está bloqueada por política: el agente está en modo solo lectura."}
            return
        await call_next()


class PresupuestoLlamadas(ChatMiddleware):
    """Corta la ejecución cuando el agente ha llamado al modelo demasiadas veces."""

    def __init__(self, maximo: int | None = None) -> None:
        self.maximo = maximo if maximo is not None else int(os.environ.get("AGENTE_MAX_LLAMADAS_MODELO", "12"))
        self.llamadas = 0

    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        self.llamadas += 1
        if self.llamadas > self.maximo:
            context.result = ChatResponse(
                messages=[Message("assistant", [f"Presupuesto agotado: se ha superado el máximo de {self.maximo} llamadas al modelo en esta ejecución."])]
            )
            return
        await call_next()


def _resumir(resultado: Any) -> Any:
    """Guarda en la auditoría un resumen del resultado, no volcados enormes."""
    if isinstance(resultado, list) and len(resultado) == 1 and isinstance(resultado[0], str):
        try:  # el framework entrega a veces el resultado ya serializado en JSON
            resultado = json.loads(resultado[0])
        except json.JSONDecodeError:
            pass
    if isinstance(resultado, list):
        return {"tipo": "lista", "elementos": len(resultado), "primeros": resultado[:3]}
    if isinstance(resultado, dict):
        return resultado
    texto = str(resultado)
    return texto if len(texto) <= 500 else texto[:500] + "…"
