"""Los agentes del ejemplo: cada uno es ``Agent`` + instrucciones + modelo + herramientas + middleware.

- ``interprete``: lee la petición del cliente y la traduce a un ``PedidoInterpretado``
  (salida estructurada). Solo tiene herramientas de lectura.
- ``redactor``: escribe la respuesta al cliente a partir del resultado. No tiene herramientas.
- ``asistente``: variante conversacional con la herramienta de escritura protegida por
  ``approval_mode="always_require"``; sirve para mostrar la aprobación a nivel de agente
  (el workflow usa, en cambio, la aprobación a nivel de grafo con ``request_info``).

Las instrucciones viven en ``prompts/*.md`` para que se puedan leer, versionar y revisar sin
abrir el código.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agent_framework import Agent

from .bc.base import ClienteBC
from .herramientas import crear_herramienta_escritura, crear_herramientas_lectura
from .modelo import crear_cliente_modelo

RUTA_PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


def leer_prompt(nombre: str) -> str:
    return (RUTA_PROMPTS / f"{nombre}.md").read_text(encoding="utf-8")


def crear_agente_interprete(bc: ClienteBC, middleware: Sequence[Any] = (), cliente_modelo: Any | None = None) -> Agent:
    return Agent(
        client=cliente_modelo or crear_cliente_modelo(papel="interprete"),
        name="interprete",
        description="Interpreta peticiones de pedido y las traduce a datos de Business Central.",
        instructions=leer_prompt("interprete"),
        tools=crear_herramientas_lectura(bc),
        middleware=list(middleware),
        default_options={"temperature": 0},
    )


def crear_agente_redactor(middleware: Sequence[Any] = (), cliente_modelo: Any | None = None) -> Agent:
    return Agent(
        client=cliente_modelo or crear_cliente_modelo(papel="redactor"),
        name="redactor",
        description="Redacta la respuesta al cliente.",
        instructions=leer_prompt("redactor"),
        middleware=list(middleware),
        default_options={"temperature": 0.3},
    )


def crear_agente_asistente(bc: ClienteBC, middleware: Sequence[Any] = (), cliente_modelo: Any | None = None) -> Agent:
    """Agente de chat con lectura libre y escritura que exige aprobación (ejemplo de approval_mode)."""
    return Agent(
        client=cliente_modelo or crear_cliente_modelo(papel="asistente"),
        name="asistente_pedidos",
        description="Asistente conversacional que consulta Business Central y crea pedidos con aprobación.",
        # Instrucciones propias: las del intérprete piden devolver solo el objeto estructurado, y un
        # modelo real que las obedece contesta con un JSON en lugar de confirmar el pedido.
        instructions=leer_prompt("asistente"),
        tools=[*crear_herramientas_lectura(bc), crear_herramienta_escritura(bc, requiere_aprobacion=True)],
        middleware=list(middleware),
        default_options={"temperature": 0},
    )
