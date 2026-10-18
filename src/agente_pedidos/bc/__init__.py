"""Acceso a Business Central: cliente real (API v2.0) y cliente de demostración (datos simulados).

Las dos clases implementan la misma interfaz (``ClienteBC``), de modo que el resto del
programa no sabe si está hablando con un ERP real o con datos simulados.
"""

from .base import ClienteBC, ErrorBC, PedidoDuplicado
from .cliente_demo import ClienteDemo
from .cliente_api import ClienteApiV2

__all__ = ["ClienteBC", "ErrorBC", "PedidoDuplicado", "ClienteDemo", "ClienteApiV2"]
