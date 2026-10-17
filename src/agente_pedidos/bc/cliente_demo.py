"""Cliente de demostración: simula Business Central con datos en memoria.

Carga ``datos_demo.json`` (clientes y artículos con nombres del típico entorno CRONUS)
y mantiene los pedidos creados en memoria. Sirve para ejecutar el ejemplo sin tener un
sandbox de Business Central y para las pruebas automáticas.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .base import ClienteBC, ErrorBC

RUTA_DATOS = Path(__file__).with_name("datos_demo.json")


class ClienteDemo(ClienteBC):
    _siguiente_numero = 101001  # compartido entre instancias para que los números no se repitan en una misma ejecución

    def __init__(self, ruta_datos: Path | None = None) -> None:
        datos = json.loads((ruta_datos or RUTA_DATOS).read_text(encoding="utf-8"))
        self.empresa: dict[str, Any] = datos["empresa"]
        self.clientes: list[dict[str, Any]] = datos["clientes"]
        self.articulos: list[dict[str, Any]] = datos["articulos"]
        self.pedidos: list[dict[str, Any]] = list(datos.get("pedidos", []))

    # --- lecturas -----------------------------------------------------------------
    async def buscar_clientes(self, texto: str) -> list[dict[str, Any]]:
        t = texto.strip().lower()
        if not t:
            return []
        return [c for c in self.clientes if t in c["number"].lower() or t in c["displayName"].lower()][:10]

    async def obtener_cliente(self, numero: str) -> dict[str, Any] | None:
        return next((c for c in self.clientes if c["number"] == numero.strip()), None)

    async def buscar_articulos(self, texto: str) -> list[dict[str, Any]]:
        palabras = [p for p in texto.strip().lower().split() if p]
        if not palabras:
            return []
        resultados = []
        for a in self.articulos:
            nombre = f"{a['number']} {a['displayName']}".lower()
            if all(p in nombre for p in palabras):
                resultados.append(a)
        if not resultados:  # búsqueda más laxa: cualquiera de las palabras
            for a in self.articulos:
                nombre = f"{a['number']} {a['displayName']}".lower()
                if any(p in nombre for p in palabras):
                    resultados.append(a)
        return resultados[:10]

    async def obtener_articulo(self, numero: str) -> dict[str, Any] | None:
        return next((a for a in self.articulos if a["number"] == numero.strip()), None)

    # --- escritura ----------------------------------------------------------------
    async def crear_pedido_venta(
        self,
        numero_cliente: str,
        lineas: list[dict[str, Any]],
        referencia_externa: str = "",
        fecha_entrega: str | None = None,
    ) -> dict[str, Any]:
        cliente = await self.obtener_cliente(numero_cliente)
        if cliente is None:
            raise ErrorBC(f"El cliente {numero_cliente} no existe")
        if cliente.get("blocked", " ").strip():
            raise ErrorBC(f"El cliente {numero_cliente} está bloqueado ({cliente['blocked']})")
        if not lineas:
            raise ErrorBC("Un pedido necesita al menos una línea")
        lineas_pedido = []
        for linea in lineas:
            articulo = await self.obtener_articulo(linea["numero_articulo"])
            if articulo is None:
                raise ErrorBC(f"El artículo {linea['numero_articulo']} no existe")
            if articulo.get("blocked"):
                raise ErrorBC(f"El artículo {articulo['number']} está bloqueado")
            cantidad = float(linea["cantidad"])
            if cantidad <= 0:
                raise ErrorBC("La cantidad debe ser mayor que cero")
            lineas_pedido.append(
                {
                    "lineType": "Item",
                    "lineObjectNumber": articulo["number"],
                    "description": articulo["displayName"],
                    "quantity": cantidad,
                    "unitPrice": articulo["unitPrice"],
                    "amountExcludingTax": round(cantidad * articulo["unitPrice"], 2),
                }
            )
        numero = f"S-ORD{ClienteDemo._siguiente_numero}"
        ClienteDemo._siguiente_numero += 1
        pedido = {
            "id": f"so-{numero}",
            "number": numero,
            "customerNumber": cliente["number"],
            "customerName": cliente["displayName"],
            "orderDate": date.today().isoformat(),
            "requestedDeliveryDate": fecha_entrega,
            "externalDocumentNumber": referencia_externa[:35],
            "status": "Draft",
            "totalAmountExcludingTax": round(sum(l["amountExcludingTax"] for l in lineas_pedido), 2),
            "salesOrderLines": lineas_pedido,
        }
        self.pedidos.append(pedido)
        return pedido

    async def cerrar(self) -> None:  # nada que cerrar en memoria
        return None
