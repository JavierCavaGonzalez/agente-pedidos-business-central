"""Enlaces a Business Central para la oficina (solo con ``BC_MODO=api``).

El navegador nunca recibe credenciales: solo la URL pública del cliente web de Business Central,
que se construye con el tenant, el entorno y la empresa de ``.env``. El inicio de sesión lo pide
Business Central a quien abre el enlace, con sus propios permisos.

Pedido de venta: página 42 (ficha de pedido de venta) filtrada por su número::

    https://businesscentral.dynamics.com/<tenant>/<entorno>?company=<empresa>&page=42&filter='No.' IS '<número>'
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import quote, urlencode

BASE = "https://businesscentral.dynamics.com"
PAGINA_PEDIDO_VENTA = 42


def _datos(entorno: Mapping[str, str] | None) -> tuple[str, str, str] | None:
    entorno = os.environ if entorno is None else entorno
    if entorno.get("BC_MODO", "demo") != "api":
        return None  # simulación: no hay pedido real que abrir
    tenant, nombre = entorno.get("BC_TENANT_ID", "").strip(), entorno.get("BC_ENVIRONMENT", "").strip()
    if not tenant or not nombre:
        return None
    return tenant, nombre, entorno.get("BC_COMPANY_NAME", "").strip()


def enlace_inicio(entorno: Mapping[str, str] | None = None) -> str | None:
    """Business Central en el entorno y la empresa configurados, o ``None`` en simulación."""
    datos = _datos(entorno)
    if datos is None:
        return None
    tenant, nombre, empresa = datos
    url = f"{BASE}/{quote(tenant, safe='')}/{quote(nombre, safe='')}"
    return f"{url}?{urlencode({'company': empresa}, quote_via=quote)}" if empresa else url


def enlace_pedido(numero: str | None, entorno: Mapping[str, str] | None = None) -> str | None:
    """Ficha del pedido de venta ``numero`` en Business Central, o ``None`` en simulación o sin número."""
    inicio = enlace_inicio(entorno)
    if inicio is None or not numero:
        return None
    parametros = urlencode({"page": PAGINA_PEDIDO_VENTA, "filter": f"'No.' IS '{numero}'"}, quote_via=quote)
    return f"{inicio}{'&' if '?' in inicio else '?'}{parametros}"


def descripcion(entorno: Mapping[str, str] | None = None) -> dict[str, str | None]:
    """Lo que la oficina muestra del ERP: modo, entorno, empresa y enlace (nunca credenciales)."""
    entorno = os.environ if entorno is None else entorno
    modo = entorno.get("BC_MODO", "demo")
    if modo != "api":
        return {"modo": "demo", "entorno": "Simulación", "empresa": "CRONUS (datos de ejemplo)", "enlace": None}
    return {
        "modo": "api",
        "entorno": entorno.get("BC_ENVIRONMENT") or None,
        "empresa": entorno.get("BC_COMPANY_NAME") or entorno.get("BC_COMPANY_ID") or None,
        "enlace": enlace_inicio(entorno),
    }
