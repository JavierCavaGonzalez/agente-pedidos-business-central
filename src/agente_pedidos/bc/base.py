"""Interfaz común de acceso a Business Central.

Separar la interfaz de las implementaciones es lo que permite que el agente, las
herramientas y el workflow sean idénticos en modo demo y en modo sandbox.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ErrorBC(Exception):
    """Error devuelto por Business Central (o por el cliente de demostración)."""


class ClienteBC(ABC):
    """Operaciones mínimas que necesita el agente de pedidos.

    Lecturas: clientes, artículos y existencias. Escritura: crear un pedido de venta.
    Cualquier otra operación del ERP queda fuera del alcance del agente a propósito
    (principio de mínimo privilegio).
    """

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

    @abstractmethod
    async def crear_pedido_venta(
        self,
        numero_cliente: str,
        lineas: list[dict[str, Any]],
        referencia_externa: str = "",
        fecha_entrega: str | None = None,
    ) -> dict[str, Any]:
        """Crea un pedido de venta con sus líneas y devuelve ``{"number": ..., "id": ...}``.

        ``lineas`` es una lista de ``{"numero_articulo": str, "cantidad": float}``.
        """

    @abstractmethod
    async def cerrar(self) -> None:
        """Libera conexiones si las hay."""
