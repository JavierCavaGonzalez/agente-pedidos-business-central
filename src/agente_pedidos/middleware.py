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
from contextvars import ContextVar
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

from . import eventos
from .observabilidad import ContadorCoste

HERRAMIENTAS_ESCRITURA = ("crear_", "modificar_", "borrar_", "registrar_")

# Herramienta en ejecución. Si durante la llamada el cliente del ERP audita la escritura, lo
# anota aquí y el middleware no escribe una segunda línea para la misma operación.
_HERRAMIENTA_EN_CURSO: ContextVar[dict[str, bool] | None] = ContextVar("herramienta_en_curso", default=None)


class AuditoriaHerramientas(FunctionMiddleware):
    """Escribe un registro de auditoría por cada herramienta ejecutada y por cada escritura en el ERP.

    Las escrituras las registra el propio cliente del ERP (``ClienteBC.crear_pedido_venta``) con
    ``registrar_escritura``, así que dejan rastro tanto si las pide el modelo (``chat``) como si
    las hace el código del workflow (``procesar``). Cuando la escritura llega a través de una
    herramienta, esa línea sustituye a la de la herramienta: una operación, una línea.
    """

    def __init__(self, ruta: Path | str | None = None) -> None:
        self.ruta = Path(ruta or os.environ.get("AGENTE_AUDITORIA", "auditoria.jsonl"))
        self.eventos: list[dict[str, Any]] = []  # copia en memoria (útil en pruebas y en la CLI)

    async def process(self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        inicio = datetime.now(timezone.utc)
        argumentos = context.arguments
        if not isinstance(argumentos, dict):
            argumentos = {"valor": str(argumentos)}
        fallo: str | None = None
        marca = {"auditada_por_el_erp": False}
        token = _HERRAMIENTA_EN_CURSO.set(marca)
        try:
            await call_next()
        except Exception as error:
            fallo = f"{type(error).__name__}: {error}"
            raise
        finally:
            _HERRAMIENTA_EN_CURSO.reset(token)
            if not marca["auditada_por_el_erp"]:
                self._registrar_herramienta(context, inicio, argumentos, fallo)
            # Registro operativo para la oficina (además de la auditoría).
            eventos.emitir(
                "herramienta",
                nombre=context.function.name,
                argumentos=eventos.resumir_argumentos(argumentos),
                resultado=_resultado_breve(context.result, fallo),
                duracion_ms=int((datetime.now(timezone.utc) - inicio).total_seconds() * 1000),
            )

    def _registrar_herramienta(
        self, context: FunctionInvocationContext, inicio: datetime, argumentos: dict[str, Any], fallo: str | None
    ) -> None:
        # También se registra la herramienta que falla: en un ERP, el intento cuenta tanto como el éxito.
        evento: dict[str, Any] = {
            "instante": inicio.isoformat(),
            "herramienta": context.function.name,
            "argumentos": argumentos,
            "resultado": None if fallo else _resumir(context.result),
            "duracion_ms": int((datetime.now(timezone.utc) - inicio).total_seconds() * 1000),
        }
        if fallo:
            evento["error"] = fallo
        self.registrar(evento)

    def registrar_escritura(
        self,
        operacion: str,
        argumentos: dict[str, Any],
        resultado: Any = None,
        error: str | None = None,
        duracion_ms: int | None = None,
    ) -> None:
        """Registra una escritura en el ERP, la pida una herramienta o el código del workflow."""
        marca = _HERRAMIENTA_EN_CURSO.get()
        evento: dict[str, Any] = {
            "herramienta": operacion,
            "evento": "escritura_erp",
            "origen": "herramienta" if marca is not None else "codigo",
            "argumentos": argumentos,
            "resultado": None if error else _resumir(resultado),
            "duracion_ms": duracion_ms,
        }
        if error:
            evento["error"] = error
        self.registrar(evento)
        if marca is not None:
            marca["auditada_por_el_erp"] = True

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
            eventos.emitir("erp_bloqueada", operacion=nombre, motivo="Modo solo lectura (AGENTE_SOLO_LECTURA=1)")
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


class EventosModelo(ChatMiddleware):
    """Emite un evento ``modelo_llamada`` por cada llamada al modelo, con tokens y coste."""

    def __init__(self, contador: ContadorCoste | None = None) -> None:
        self.tarifa = contador or ContadorCoste()  # solo se usan sus precios

    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        await call_next()
        respuesta = context.result
        uso = getattr(respuesta, "usage_details", None) or {}
        entrada = int(_leer(uso, "input_token_count") or 0)
        salida = int(_leer(uso, "output_token_count") or 0)
        coste = entrada / 1_000_000 * self.tarifa.precio_entrada_por_millon + salida / 1_000_000 * self.tarifa.precio_salida_por_millon
        modelo = getattr(respuesta, "model", None) or getattr(context.client, "model", None) or type(context.client).__name__
        eventos.emitir("modelo_llamada", modelo=str(modelo), tokens_entrada=entrada, tokens_salida=salida, coste_eur=round(coste, 6))


def _leer(uso: Any, clave: str) -> Any:
    return uso.get(clave) if isinstance(uso, dict) else getattr(uso, clave, None)


def _resultado_breve(resultado: Any, fallo: str | None) -> str:
    """«ok» o el error (resumido), para el evento ``herramienta``."""
    if fallo:
        return eventos.resumir_error(fallo)
    resumido = _resumir(resultado)
    if isinstance(resumido, dict) and resumido.get("error"):
        return eventos.resumir_error(str(resumido["error"]))
    return "ok"


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
