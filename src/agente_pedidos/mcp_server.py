"""Servidor MCP opcional: expone las consultas de Business Central como herramientas MCP.

Sirve para dos cosas:
1. Mostrar cómo un agente de Agent Framework consume herramientas MCP (``MCPStdioTool``)
   en lugar de funciones locales: ver ``crear_herramienta_mcp()``.
2. Dejar que otros hosts MCP (VS Code, Claude, Copilot Studio) consulten el ERP simulado.

Solo expone lecturas: la escritura se queda fuera a propósito (mínimo privilegio).
Requiere el paquete ``mcp``:  ``pip install mcp``.

Arranque manual:  python -m agente_pedidos.mcp_server
"""

from __future__ import annotations

import sys
from typing import Any

from .bc import ClienteDemo


def construir_servidor() -> Any:
    from mcp.server.fastmcp import FastMCP

    bc = ClienteDemo()
    servidor = FastMCP("business-central-demo")

    @servidor.tool(name="buscar_clientes", description="Busca clientes de Business Central por nombre o número.")
    async def buscar_clientes(texto: str) -> list[dict[str, Any]]:
        return await bc.buscar_clientes(texto)

    @servidor.tool(name="buscar_articulos", description="Busca artículos de Business Central por palabras clave.")
    async def buscar_articulos(texto: str) -> list[dict[str, Any]]:
        return await bc.buscar_articulos(texto)

    @servidor.tool(name="obtener_cliente", description="Ficha de un cliente por su número exacto.")
    async def obtener_cliente(numero: str) -> dict[str, Any] | None:
        return await bc.obtener_cliente(numero)

    @servidor.tool(name="obtener_articulo", description="Ficha de un artículo por su número exacto.")
    async def obtener_articulo(numero: str) -> dict[str, Any] | None:
        return await bc.obtener_articulo(numero)

    return servidor


def crear_herramienta_mcp() -> Any:
    """Herramienta MCP para un agente de Agent Framework: lanza este mismo servidor por stdio.

    Uso::

        from agent_framework import Agent
        async with Agent(client=..., name="interprete", tools=[crear_herramienta_mcp()]) as agente:
            ...
    """
    import os

    from agent_framework import MCPStdioTool

    # El SDK de MCP arranca el subproceso con un entorno mínimo (sin PYTHONPATH): se pasa explícito.
    entorno = {"PYTHONPATH": os.environ.get("PYTHONPATH", "src")}
    return MCPStdioTool(
        name="business_central_demo",
        command=sys.executable,
        args=["-m", "agente_pedidos.mcp_server"],
        env=entorno,
        allowed_tools=["buscar_clientes", "buscar_articulos", "obtener_cliente", "obtener_articulo"],
    )


if __name__ == "__main__":
    construir_servidor().run(transport="stdio")
