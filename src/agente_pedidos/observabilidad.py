"""Observabilidad: trazas OpenTelemetry y cuenta de tokens y coste.

Agent Framework instrumenta por defecto cada ejecución de agente, cada llamada al modelo y
cada herramienta con OpenTelemetry (convenciones GenAI: ``invoke_agent``, ``chat``,
``execute_tool``) (cap. 4.10 del libro). Solo hay que decirle a dónde exportar:

- ``OTEL_EXPORTER_OTLP_ENDPOINT`` (por ejemplo ``http://localhost:4317`` con Aspire Dashboard);
- ``ENABLE_CONSOLE_EXPORTERS=1`` para ver las trazas por consola;
- ``ENABLE_SENSITIVE_DATA=1`` para incluir el contenido de los mensajes (nunca en producción);
- ``APPLICATIONINSIGHTS_CONNECTION_STRING`` para Azure Monitor / Application Insights.

El framework cuenta tokens, pero no sabe cuánto cuesta cada uno: el precio lo pone la
aplicación. ``ContadorCoste`` acumula los ``usage_details`` de cada respuesta y los convierte
a euros con una tarifa configurable por variables de entorno.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def redondear_eur(importe: float, decimales: int = 4) -> Decimal:
    """Redondeo «medio hacia arriba» sobre el valor decimal: 0,00375 -> 0,0038.

    Con ``f"{x:.4f}"`` el resultado depende de cómo se guardó el número en binario (0,00375 sale
    «0,0037») y no coincidiría con la oficina. La CLI, el backend y el navegador redondean así.
    """
    return Decimal(str(importe)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def configurar_observabilidad(nombre_servicio: str = "agente-pedidos-bc") -> bool:
    """Activa la exportación de trazas si hay algún destino configurado. Devuelve True si lo hizo."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    consola = os.environ.get("ENABLE_CONSOLE_EXPORTERS", "0") == "1"
    app_insights = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")

    if app_insights:
        # Exportación a Azure Monitor (requiere el paquete azure-monitor-opentelemetry).
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=app_insights)
        return True

    if endpoint or consola:
        from agent_framework.observability import configure_otel_providers

        configure_otel_providers(
            service_name=nombre_servicio,
            otlp_endpoint=endpoint,
            enable_sensitive_data=os.environ.get("ENABLE_SENSITIVE_DATA", "0") == "1",
            enable_console_exporters=consola,
        )
        return True
    return False


@dataclass
class ContadorCoste:
    """Acumula tokens de entrada y salida y los valora con una tarifa (euros por millón de tokens)."""

    precio_entrada_por_millon: float = field(default_factory=lambda: float(os.environ.get("PRECIO_ENTRADA_EUR_POR_MILLON", "2.0")))
    precio_salida_por_millon: float = field(default_factory=lambda: float(os.environ.get("PRECIO_SALIDA_EUR_POR_MILLON", "8.0")))
    tokens_entrada: int = 0
    tokens_salida: int = 0
    llamadas: int = 0

    def registrar(self, respuesta: Any) -> None:
        """Acepta cualquier objeto con ``usage_details`` (AgentResponse, ChatResponse)."""
        uso = getattr(respuesta, "usage_details", None)
        if not uso:
            return
        self.llamadas += 1
        self.tokens_entrada += int(_leer(uso, "input_token_count") or 0)
        self.tokens_salida += int(_leer(uso, "output_token_count") or 0)

    @property
    def coste_eur(self) -> float:
        return round(
            self.tokens_entrada / 1_000_000 * self.precio_entrada_por_millon
            + self.tokens_salida / 1_000_000 * self.precio_salida_por_millon,
            6,
        )

    def resumen(self) -> str:
        return (
            f"{self.llamadas} respuesta(s) de agente, {self.tokens_entrada} tokens de entrada, "
            f"{self.tokens_salida} de salida, coste estimado {redondear_eur(self.coste_eur)} €"
        )


def _leer(uso: Any, clave: str) -> Any:
    if isinstance(uso, dict):
        return uso.get(clave)
    return getattr(uso, clave, None)
