"""Interfaz común de acceso a Business Central.

Separar la interfaz de las implementaciones es lo que permite que el agente, las
herramientas y el workflow sean idénticos en modo demo y en modo sandbox.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from .. import eventos


class ErrorBC(Exception):
    """Error devuelto por Business Central (o por el cliente de demostración)."""


class PedidoDuplicado(ErrorBC):
    """Ya existe un pedido del mismo cliente con la misma referencia externa: no se crea otro."""

    def __init__(self, pedido: dict[str, Any], numero_cliente: str, referencia: str) -> None:
        self.pedido = pedido
        super().__init__(
            f"Ya existe el pedido {pedido.get('number')} del cliente {numero_cliente} con la referencia "
            f"{referencia}; no se crea otro"
        )


class ClienteBC(ABC):
    """Operaciones mínimas que necesita el agente de pedidos.

    Lecturas: clientes, artículos y existencias. Escritura: crear un pedido de venta.
    Cualquier otra operación del ERP queda fuera del alcance del agente a propósito
    (principio de mínimo privilegio).

    La escritura (``crear_pedido_venta``) es común a todas las implementaciones: comprueba que
    no exista ya el pedido (idempotencia por cliente y referencia externa) y deja rastro en la
    auditoría, la pida el modelo o el código. Cada implementación solo aporta
    ``_crear_pedido_venta`` y ``_buscar_pedido_por_referencia``.
    """

    #: Registro de auditoría de las escrituras (``AuditoriaHerramientas``); lo asigna la aplicación.
    auditoria: Any = None
    #: ``demo`` o ``api``: aparece en los eventos de escritura de la oficina.
    modo: str = "?"

    @abstractmethod
    async def buscar_clientes(self, texto: str) -> list[dict[str, Any]]:
        """Devuelve clientes cuyo número o nombre contiene ``texto`` (máx. 10)."""

    @abstractmethod
    async def obtener_cliente(self, numero: str) -> dict[str, Any] | None:
        """Devuelve un cliente por número, o ``None`` si no existe."""

    @abstractmethod
    async def buscar_articulos(self, texto: str) -> list[dict[str, Any]]:
        """Devuelve artículos cuyo número o descripción contiene ``texto`` (máx. 10)."""

    @abstractmethod
    async def obtener_articulo(self, numero: str) -> dict[str, Any] | None:
        """Devuelve un artículo por número (con existencias y precio), o ``None``."""

    async def crear_pedido_venta(
        self,
        numero_cliente: str,
        lineas: list[dict[str, Any]],
        referencia_externa: str = "",
        fecha_entrega: str | None = None,
    ) -> dict[str, Any]:
        """Crea un pedido de venta con sus líneas y devuelve ``{"number": ..., "id": ...}``.

        ``lineas`` es una lista de ``{"numero_articulo": str, "cantidad": float}``. Si ya existe un
        pedido del cliente con la misma ``referencia_externa``, lanza ``PedidoDuplicado`` (un error
        de datos: las herramientas lo devuelven como ``{"error": ...}``) en lugar de crear otro.
        """
        referencia = (referencia_externa or "")[:35]
        argumentos = {
            "numero_cliente": numero_cliente,
            "lineas": lineas,
            "referencia_externa": referencia,
            "fecha_entrega": fecha_entrega,
        }
        inicio = time.monotonic()
        try:
            if referencia:
                existente = await self._buscar_pedido_por_referencia(numero_cliente, referencia)
                if existente:
                    raise PedidoDuplicado(existente, numero_cliente, referencia)
            pedido = await self._crear_pedido_venta(numero_cliente, lineas, referencia, fecha_entrega)
        except Exception as error:
            self._auditar_escritura(argumentos, inicio, error=f"{type(error).__name__}: {error}")
            eventos.emitir("erp_bloqueada", operacion="crear_pedido", motivo=eventos.resumir_error(error), modo=self.modo)
            raise
        self._auditar_escritura(argumentos, inicio, resultado=_resumen_pedido(pedido))
        eventos.emitir(
            "erp_escritura",
            operacion="crear_pedido",
            pedido=pedido.get("number"),
            importe=pedido.get("totalAmountExcludingTax"),
            cliente=numero_cliente,
            modo=self.modo,
        )
        return pedido

    def _auditar_escritura(self, argumentos: dict[str, Any], inicio: float, resultado: Any = None, error: str | None = None) -> None:
        if self.auditoria is not None:
            self.auditoria.registrar_escritura(
                "crear_pedido_venta", argumentos, resultado=resultado, error=error,
                duracion_ms=int((time.monotonic() - inicio) * 1000),
            )

    @abstractmethod
    async def _crear_pedido_venta(
        self, numero_cliente: str, lineas: list[dict[str, Any]], referencia_externa: str, fecha_entrega: str | None
    ) -> dict[str, Any]:
        """Crea de verdad el pedido (cabecera y líneas) y lo devuelve con sus totales."""

    @abstractmethod
    async def _buscar_pedido_por_referencia(self, numero_cliente: str, referencia_externa: str) -> dict[str, Any] | None:
        """Devuelve un pedido existente del cliente con esa referencia externa, o ``None``."""

    @abstractmethod
    async def cerrar(self) -> None:
        """Libera conexiones si las hay."""


def _resumen_pedido(pedido: dict[str, Any]) -> dict[str, Any]:
    """Lo que queda en la auditoría de un pedido creado: cabecera y líneas, sin volcar todo el registro."""
    return {
        "number": pedido.get("number"),
        "customerNumber": pedido.get("customerNumber"),
        "externalDocumentNumber": pedido.get("externalDocumentNumber"),
        "status": pedido.get("status"),
        "totalAmountExcludingTax": pedido.get("totalAmountExcludingTax"),
        "lineas": [
            {
                "articulo": linea.get("lineObjectNumber"),
                "descripcion": linea.get("description"),
                "cantidad": linea.get("quantity"),
                "importe": linea.get("amountExcludingTax"),
            }
            for linea in pedido.get("salesOrderLines", [])
        ],
    }
