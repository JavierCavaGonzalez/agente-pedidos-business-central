"""Cliente real de Business Central: API estándar v2.0 con autenticación OAuth 2.0.

Flujo de autenticación: *client credentials* (servicio a servicio). La aplicación
registrada en Microsoft Entra ID se da de alta en Business Central (página
«Aplicaciones de Microsoft Entra») con los conjuntos de permisos mínimos que necesita el
agente. Así el ERP ejecuta cada operación con la identidad de la aplicación, no con la de
una persona.

Endpoints usados (todos de la API v2.0 estándar, sin extensiones AL):
- GET  /companies
- GET  /companies({id})/customers
- GET  /companies({id})/items
- POST /companies({id})/salesOrders
- POST /companies({id})/salesOrders({id})/salesOrderLines
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .base import ClienteBC, ErrorBC

URL_API = "https://api.businesscentral.dynamics.com/v2.0/{tenant}/{entorno}/api/v2.0"
URL_TOKEN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
AMBITO = "https://api.businesscentral.dynamics.com/.default"


def _escapar_odata(texto: str) -> str:
    """Escapa comillas simples para usarlas dentro de un filtro OData."""
    return texto.replace("'", "''")


class ClienteApiV2(ClienteBC):
    def __init__(
        self,
        tenant_id: str,
        entorno: str,
        client_id: str,
        client_secret: str,
        nombre_empresa: str | None = None,
        id_empresa: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not all([tenant_id, entorno, client_id, client_secret]):
            raise ErrorBC("Faltan BC_TENANT_ID, BC_ENVIRONMENT, BC_CLIENT_ID o BC_CLIENT_SECRET")
        if not (nombre_empresa or id_empresa):
            raise ErrorBC("Indica BC_COMPANY_NAME o BC_COMPANY_ID")
        self._tenant = tenant_id
        self._entorno = entorno
        self._client_id = client_id
        self._client_secret = client_secret
        self._nombre_empresa = nombre_empresa
        self._id_empresa = id_empresa
        self._token: str | None = None
        self._token_expira = 0.0
        self._http = httpx.AsyncClient(timeout=timeout)

    @classmethod
    def desde_entorno(cls) -> "ClienteApiV2":
        """Construye el cliente a partir de las variables de entorno (ver .env.example)."""
        import os

        return cls(
            tenant_id=os.environ.get("BC_TENANT_ID", ""),
            entorno=os.environ.get("BC_ENVIRONMENT", ""),
            client_id=os.environ.get("BC_CLIENT_ID", ""),
            client_secret=os.environ.get("BC_CLIENT_SECRET", ""),
            nombre_empresa=os.environ.get("BC_COMPANY_NAME") or None,
            id_empresa=os.environ.get("BC_COMPANY_ID") or None,
        )

    # --- infraestructura ----------------------------------------------------------
    @property
    def _base(self) -> str:
        return URL_API.format(tenant=self._tenant, entorno=self._entorno)

    async def _obtener_token(self) -> str:
        if self._token and time.time() < self._token_expira - 60:
            return self._token
        respuesta = await self._http.post(
            URL_TOKEN.format(tenant=self._tenant),
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": AMBITO,
            },
        )
        if respuesta.status_code != 200:
            raise ErrorBC(f"No se pudo obtener el token de Entra ID: {respuesta.status_code} {respuesta.text[:300]}")
        datos = respuesta.json()
        self._token = datos["access_token"]
        self._token_expira = time.time() + float(datos.get("expires_in", 3600))
        return self._token

    async def _peticion(self, metodo: str, ruta: str, **kwargs: Any) -> Any:
        token = await self._obtener_token()
        cabeceras = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if metodo in ("POST", "PATCH"):
            cabeceras["Content-Type"] = "application/json"
        respuesta = await self._http.request(metodo, f"{self._base}{ruta}", headers=cabeceras, **kwargs)
        if respuesta.status_code >= 400:
            mensaje = respuesta.text[:500]
            try:
                mensaje = respuesta.json().get("error", {}).get("message", mensaje)
            except ValueError:
                pass
            raise ErrorBC(f"Business Central respondió {respuesta.status_code}: {mensaje}")
        if respuesta.status_code == 204 or not respuesta.content:
            return None
        return respuesta.json()

    async def _ruta_empresa(self) -> str:
        if self._id_empresa:
            return f"/companies({self._id_empresa})"
        datos = await self._peticion("GET", "/companies")
        for empresa in datos.get("value", []):
            if empresa.get("name") == self._nombre_empresa or empresa.get("displayName") == self._nombre_empresa:
                self._id_empresa = empresa["id"]
                return f"/companies({self._id_empresa})"
        nombres = ", ".join(e.get("name", "?") for e in datos.get("value", []))
        raise ErrorBC(f"No existe la empresa '{self._nombre_empresa}'. Empresas disponibles: {nombres}")

    # --- lecturas -----------------------------------------------------------------
    async def buscar_clientes(self, texto: str) -> list[dict[str, Any]]:
        t = _escapar_odata(texto.strip())
        if not t:
            return []
        empresa = await self._ruta_empresa()
        filtro = f"contains(displayName,'{t}') or number eq '{t}'"
        datos = await self._peticion(
            "GET",
            f"{empresa}/customers",
            params={"$filter": filtro, "$top": 10, "$select": "id,number,displayName,email,blocked,creditLimit,balanceDue"},
        )
        return datos.get("value", [])

    async def obtener_cliente(self, numero: str) -> dict[str, Any] | None:
        empresa = await self._ruta_empresa()
        datos = await self._peticion(
            "GET",
            f"{empresa}/customers",
            params={"$filter": f"number eq '{_escapar_odata(numero.strip())}'", "$top": 1},
        )
        valores = datos.get("value", [])
        return valores[0] if valores else None

    async def buscar_articulos(self, texto: str) -> list[dict[str, Any]]:
        palabras = [_escapar_odata(p) for p in texto.strip().split() if p]
        if not palabras:
            return []
        empresa = await self._ruta_empresa()
        filtro = " and ".join(f"contains(displayName,'{p}')" for p in palabras)
        filtro = f"({filtro}) or number eq '{_escapar_odata(texto.strip())}'"
        datos = await self._peticion(
            "GET",
            f"{empresa}/items",
            params={
                "$filter": filtro,
                "$top": 10,
                "$select": "id,number,displayName,type,blocked,inventory,unitPrice,baseUnitOfMeasureCode",
            },
        )
        return datos.get("value", [])

    async def obtener_articulo(self, numero: str) -> dict[str, Any] | None:
        empresa = await self._ruta_empresa()
        datos = await self._peticion(
            "GET",
            f"{empresa}/items",
            params={"$filter": f"number eq '{_escapar_odata(numero.strip())}'", "$top": 1},
        )
        valores = datos.get("value", [])
        return valores[0] if valores else None

    # --- escritura ----------------------------------------------------------------
    async def crear_pedido_venta(
        self,
        numero_cliente: str,
        lineas: list[dict[str, Any]],
        referencia_externa: str = "",
        fecha_entrega: str | None = None,
    ) -> dict[str, Any]:
        if not lineas:
            raise ErrorBC("Un pedido necesita al menos una línea")
        empresa = await self._ruta_empresa()
        cabecera: dict[str, Any] = {"customerNumber": numero_cliente}
        if referencia_externa:
            cabecera["externalDocumentNumber"] = referencia_externa[:35]
        if fecha_entrega:
            cabecera["requestedDeliveryDate"] = fecha_entrega
        pedido = await self._peticion("POST", f"{empresa}/salesOrders", json=cabecera)
        for linea in lineas:
            await self._peticion(
                "POST",
                f"{empresa}/salesOrders({pedido['id']})/salesOrderLines",
                json={
                    "lineType": "Item",
                    "lineObjectNumber": linea["numero_articulo"],
                    "quantity": float(linea["cantidad"]),
                },
            )
        # Releemos el pedido para devolver totales calculados por Business Central.
        completo = await self._peticion("GET", f"{empresa}/salesOrders({pedido['id']})", params={"$expand": "salesOrderLines"})
        return completo or pedido

    async def cerrar(self) -> None:
        await self._http.aclose()
