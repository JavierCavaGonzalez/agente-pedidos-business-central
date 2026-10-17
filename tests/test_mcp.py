"""El agente consume las lecturas de Business Central a través de un servidor MCP (opcional).

Se omite si el paquete ``mcp`` no está instalado. Arranca el servidor de ``mcp_server.py``
como subproceso por stdio y comprueba que el agente descubre y usa sus herramientas.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")

from agent_framework import Agent  # noqa: E402

from agente_pedidos.mcp_server import crear_herramienta_mcp  # noqa: E402
from agente_pedidos.modelo import crear_cliente_modelo  # noqa: E402


@pytest.mark.asyncio
async def test_el_agente_usa_las_herramientas_del_servidor_mcp(monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    monkeypatch.setenv("PYTHONPATH", "src")
    herramienta = crear_herramienta_mcp()
    async with Agent(client=crear_cliente_modelo("interprete"), name="interprete_mcp", instructions="Interpreta pedidos.", tools=[herramienta]) as agente:
        assert {f.name for f in herramienta.functions} == {"buscar_clientes", "buscar_articulos", "obtener_cliente", "obtener_articulo"}
        respuesta = await agente.run("Empresa: Alpine Ski House. Necesito 10 lámparas AMSTERDAM")
    assert '"numero_cliente": "40000"' in (respuesta.text or "")
    assert '"numero_articulo": "1928-S"' in (respuesta.text or "")
