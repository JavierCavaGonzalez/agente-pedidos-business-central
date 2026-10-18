"""Herramientas (tools) que el agente puede usar sobre Business Central.

Cada herramienta es una función normal de Python con el decorador ``@tool`` de Agent
Framework: el framework lee el nombre, la descripción y los parámetros anotados y se los
presenta al modelo como un esquema (cap. 4.6 del libro). El modelo decide *cuándo* llamarlas;
el código decide *qué* hacen y con qué permisos.

Diseño deliberado (cap. 11.3.4: «Better to have 10 excellent tools than 50 mediocre ones»):
- Pocas herramientas, específicas del dominio y con nombres en español.
- Las de lectura y la de escritura están separadas. La de escritura exige aprobación humana
  (``approval_mode="always_require"``), que es el control más directo que ofrece el framework
  a nivel de agente. En el workflow la escritura no la hace el modelo, sino un nodo de código.
"""

from __future__ import annotations

from typing import Annotated, Any

from agent_framework import FunctionTool, tool
from pydantic import Field

from .bc.base import ClienteBC, ErrorBC


def crear_herramientas_lectura(bc: ClienteBC) -> list[FunctionTool]:
    """Herramientas de solo lectura: el modelo puede llamarlas sin aprobación.

    Como la de escritura, devuelven los errores del ERP como datos (``{"error": ...}``): así el
    modelo sabe que ha fallado el sistema, y no el nombre que le dieron, y puede explicarlo.
    """

    @tool(name="buscar_clientes", description="Busca clientes de Business Central por nombre o número. Devuelve hasta 10 candidatos.")
    async def buscar_clientes(
        texto: Annotated[str, Field(description="Texto a buscar en el nombre o el número de cliente")],
    ) -> list[dict[str, Any]] | dict[str, str]:
        try:
            return _resumir_clientes(await bc.buscar_clientes(texto))
        except ErrorBC as error:
            return {"error": str(error)}

    @tool(name="obtener_cliente", description="Devuelve la ficha de un cliente de Business Central a partir de su número exacto.")
    async def obtener_cliente(
        numero: Annotated[str, Field(description="Número de cliente, por ejemplo 10000")],
    ) -> dict[str, Any] | None:
        try:
            cliente = await bc.obtener_cliente(numero)
        except ErrorBC as error:
            return {"error": str(error)}
        return _resumir_clientes([cliente])[0] if cliente else None

    @tool(name="buscar_articulos", description="Busca artículos de Business Central por palabras clave (modelo, color, tipo). Devuelve hasta 10 candidatos con precio y existencias.")
    async def buscar_articulos(
        texto: Annotated[str, Field(description="Palabras clave a buscar en el número o la descripción del artículo")],
    ) -> list[dict[str, Any]] | dict[str, str]:
        try:
            return _resumir_articulos(await bc.buscar_articulos(texto))
        except ErrorBC as error:
            return {"error": str(error)}

    @tool(name="obtener_articulo", description="Devuelve la ficha de un artículo de Business Central a partir de su número exacto.")
    async def obtener_articulo(
        numero: Annotated[str, Field(description="Número de artículo, por ejemplo 1900-S")],
    ) -> dict[str, Any] | None:
        try:
            articulo = await bc.obtener_articulo(numero)
        except ErrorBC as error:
            return {"error": str(error)}
        return _resumir_articulos([articulo])[0] if articulo else None

    return [buscar_clientes, obtener_cliente, buscar_articulos, obtener_articulo]


def crear_herramienta_escritura(bc: ClienteBC, requiere_aprobacion: bool = True) -> FunctionTool:
    """Herramienta de escritura: crea un pedido de venta. Por defecto exige aprobación humana.

    Es la única herramienta que cambia el estado del ERP. Con ``approval_mode="always_require"``
    el agente se detiene antes de ejecutarla y devuelve una petición de aprobación
    (``respuesta.user_input_requests``); la persona ve el nombre de la herramienta y los
    argumentos exactos con los que se va a llamar, no un resumen redactado por el modelo.
    """

    @tool(
        name="crear_pedido_venta",
        description=(
            "Crea un pedido de venta en Business Central para un cliente con una lista de líneas "
            "(numero_articulo y cantidad). Es una escritura en el ERP y requiere aprobación."
        ),
        approval_mode="always_require" if requiere_aprobacion else "never_require",
    )
    async def crear_pedido_venta(
        numero_cliente: Annotated[str, Field(description="Número del cliente en Business Central")],
        lineas: Annotated[
            list[dict[str, Any]],
            Field(description="Líneas del pedido: lista de objetos con numero_articulo (str) y cantidad (número)"),
        ],
        referencia_externa: Annotated[str, Field(description="Referencia del cliente (opcional)")] = "",
        fecha_entrega: Annotated[str | None, Field(description="Fecha de entrega solicitada AAAA-MM-DD (opcional)")] = None,
    ) -> dict[str, Any]:
        try:
            pedido = await bc.crear_pedido_venta(numero_cliente, lineas, referencia_externa, fecha_entrega)
        except ErrorBC as error:
            # Los errores de negocio vuelven al modelo como datos, no como excepciones (cap. 11.3.4).
            return {"error": str(error)}
        return {
            "number": pedido["number"],
            "customerNumber": pedido["customerNumber"],
            "customerName": pedido.get("customerName", ""),
            "totalAmountExcludingTax": pedido.get("totalAmountExcludingTax", 0),
            "status": pedido.get("status", ""),
            "lineas": len(pedido.get("salesOrderLines", [])),
        }

    return crear_pedido_venta


# --- reducimos lo que ve el modelo a lo necesario (context engineering, cap. 4.12) ---------


def _resumir_clientes(clientes: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    return [
        {
            "number": c["number"],
            "displayName": c.get("displayName", ""),
            "blocked": (c.get("blocked") or " ").strip(),
            "creditLimit": c.get("creditLimit", 0),
            "balanceDue": c.get("balanceDue", 0),
        }
        for c in clientes
        if c
    ]


def _resumir_articulos(articulos: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    return [
        {
            "number": a["number"],
            "displayName": a.get("displayName", ""),
            "blocked": bool(a.get("blocked", False)),
            "inventory": a.get("inventory", 0),
            "unitPrice": a.get("unitPrice", 0),
        }
        for a in articulos
        if a
    ]
