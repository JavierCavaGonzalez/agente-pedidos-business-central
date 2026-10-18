"""Cliente real de Business Central contra una API simulada con httpx.MockTransport (sin red)."""

from __future__ import annotations

import re

import httpx
import pytest

from agente_pedidos.bc import ClienteApiV2
from agente_pedidos.bc.base import ErrorBC
from agente_pedidos.bc.cliente_api import _palabras_clave

# La API real devuelve el valor en blanco del enum 'blocked' (no bloqueado) como '_x0020_'.
ADATUM = {"id": "c1", "number": "10000", "displayName": "Adatum Corporation", "blocked": "_x0020_"}
ADATUM_NORMALIZADO = {**ADATUM, "blocked": ""}
RELECLOUD = {"id": "c5", "number": "50000", "displayName": "Relecloud", "blocked": "All"}
LAMPARA = {"id": "i1", "number": "1928-S", "displayName": "AMSTERDAM Lamp", "inventory": 60, "unitPrice": 55.9}
# Catálogo como el de CRONUS ES: nombres en español y con tildes.
CATALOGO_ES = [
    {"id": "e1", "number": "1896-S", "displayName": "Mesa ATENAS", "blocked": False},
    {"id": "e2", "number": "1928-S", "displayName": "Lámpara ÁMSTERDAM", "blocked": False},
    {"id": "e3", "number": "1929-S", "displayName": "Lámpara de pie MÚNICH", "blocked": False},
]


def campos_unidos_por_or(filtro: str) -> set[str]:
    """Campos distintos que aparecen en un filtro con 'or' (la API real no lo admite)."""
    if not re.search(r"\sor\s", filtro, re.IGNORECASE):
        return set()
    return set(re.findall(r"contains\((\w+),", filtro)) | set(re.findall(r"(\w+) eq ", filtro))


class ApiFalsa:
    """Imita la API v2.0: token, y GET de customers/items con la restricción del 'or' entre campos."""

    def __init__(self, clientes: list[dict] | None = None, articulos: list[dict] | None = None) -> None:
        self.filtros: list[str] = []
        self.clientes = clientes if clientes is not None else [ADATUM]
        self.articulos = articulos if articulos is not None else [LAMPARA]

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        if "oauth2" in peticion.url.path:
            return httpx.Response(200, json={"access_token": "token-de-prueba", "expires_in": 3600})
        filtro = peticion.url.params.get("$filter", "")
        self.filtros.append(filtro)
        if len(campos_unidos_por_or(filtro)) > 1:
            mensaje = "The 'OR' operator is not supported on distinct fields on an OData filter."
            return httpx.Response(501, json={"error": {"code": "NotImplemented", "message": mensaje}})
        registros = self.clientes if peticion.url.path.endswith("/customers") else self.articulos
        if "number eq" in filtro:
            numero = re.search(r"number eq '([^']*)'", filtro).group(1)
            return httpx.Response(200, json={"value": [r for r in registros if r["number"] == numero]})
        # Como el 'contains' real: distingue mayúsculas y tildes.
        palabras = re.findall(r"contains\(displayName,'([^']*)'\)", filtro)
        return httpx.Response(200, json={"value": [r for r in registros if all(p in r["displayName"] for p in palabras)]})


@pytest.fixture
def api():
    return ApiFalsa()


@pytest.fixture
def bc(api):
    cliente = ClienteApiV2("tenant", "Sandbox", "app", "secreto", id_empresa="empresa-1")
    cliente._http = httpx.AsyncClient(transport=httpx.MockTransport(api))
    return cliente


def test_la_api_falsa_rechaza_or_entre_campos_como_la_real():
    # El filtro que usaba la primera versión y que Business Central rechazó con 501.
    assert campos_unidos_por_or("contains(displayName,'Adatum') or number eq 'Adatum'") == {"displayName", "number"}
    assert campos_unidos_por_or("contains(displayName,'AMSTERDAM') and contains(displayName,'Lamp')") == set()


async def test_buscar_por_nombre_solo_filtra_por_displayname(bc, api):
    assert await bc.buscar_clientes("Adatum Corporation") == [ADATUM_NORMALIZADO]
    assert await bc.buscar_articulos("AMSTERDAM Lamp") == [LAMPARA]
    assert api.filtros == [
        "contains(displayName,'Adatum Corporation')",
        "contains(displayName,'AMSTERDAM') and contains(displayName,'Lamp')",
    ]
    await bc.cerrar()


@pytest.mark.parametrize("codigo", ["1928-S", "10000"])
async def test_un_texto_con_forma_de_codigo_busca_tambien_por_numero_sin_duplicados(bc, api, codigo):
    buscar = bc.buscar_articulos if "-" in codigo else bc.buscar_clientes
    resultado = await buscar(codigo)
    assert api.filtros == [f"number eq '{codigo}'", f"contains(displayName,'{codigo}')"]
    assert all(len(campos_unidos_por_or(f)) <= 1 for f in api.filtros)
    assert len(resultado) <= 1  # si el nombre también coincidiera, no aparecería dos veces
    await bc.cerrar()


async def test_mismo_registro_por_numero_y_por_nombre_aparece_una_vez(bc, api, monkeypatch):
    # El número 1928-S está también en el nombre: las dos peticiones devuelven el mismo artículo.
    monkeypatch.setitem(LAMPARA, "displayName", "AMSTERDAM Lamp 1928-S")
    assert await bc.buscar_articulos("1928-S") == [LAMPARA]
    assert len(api.filtros) == 2
    await bc.cerrar()


async def test_un_error_de_la_api_llega_como_errorbc_con_el_codigo(bc, api):
    # Se fuerza un filtro con 'or' entre campos para ver cómo llega el 501 de la API.
    async def con_or(entidad, filtro_nombre, texto, campos):
        empresa = await bc._ruta_empresa()
        await bc._peticion("GET", f"{empresa}/{entidad}", params={"$filter": f"{filtro_nombre} or number eq '{texto}'"})

    bc._buscar = con_or
    with pytest.raises(ErrorBC, match="501"):
        await bc.buscar_clientes("Adatum")
    await bc.cerrar()


async def test_blocked_x0020_se_normaliza_a_vacio_y_un_bloqueo_real_se_conserva(api):
    api.clientes = [ADATUM, RELECLOUD]
    bc = ClienteApiV2("tenant", "Sandbox", "app", "secreto", id_empresa="empresa-1")
    bc._http = httpx.AsyncClient(transport=httpx.MockTransport(api))
    assert (await bc.buscar_clientes("Adatum"))[0]["blocked"] == ""
    assert (await bc.obtener_cliente("10000"))["blocked"] == ""
    assert (await bc.obtener_cliente("50000"))["blocked"] == "All"
    await bc.cerrar()


def test_palabras_clave_ignora_cortas_y_vacias_y_pasa_a_singular():
    assert _palabras_clave("2 lámparas de pie para la oficina AMSTERDAM") == ["lámpara", "pie", "oficina", "AMSTERDAM"]
    assert _palabras_clave("de la con un") == []


@pytest.mark.parametrize("texto", ["2 lámparas AMSTERDAM", "AMSTERDAM lámpara", "lampara de Ámsterdam"])
async def test_busqueda_de_articulos_tolerante_a_mayusculas_tildes_e_idioma(texto):
    api = ApiFalsa(articulos=CATALOGO_ES)
    bc = ClienteApiV2("tenant", "Sandbox", "app", "secreto", id_empresa="empresa-1")
    bc._http = httpx.AsyncClient(transport=httpx.MockTransport(api))

    resultado = await bc.buscar_articulos(texto)

    assert resultado and resultado[0]["number"] == "1928-S"  # la que coincide en más palabras, primero
    assert all(len(campos_unidos_por_or(f)) <= 1 for f in api.filtros)
    assert not any("'de'" in f or "'2'" in f for f in api.filtros[1:])  # el desglose ignora cortas y vacías
    await bc.cerrar()


async def test_si_la_busqueda_completa_encuentra_algo_no_se_desglosa(api, bc):
    assert await bc.buscar_articulos("AMSTERDAM Lamp") == [LAMPARA]
    assert len(api.filtros) == 1
    await bc.cerrar()


@pytest.mark.parametrize("texto", ["adatum", "ADATUM CORPORATION", "corporation adatum"])
async def test_busqueda_de_clientes_tolerante_a_mayusculas(texto):
    api = ApiFalsa(clientes=[ADATUM, RELECLOUD])
    bc = ClienteApiV2("tenant", "Sandbox", "app", "secreto", id_empresa="empresa-1")
    bc._http = httpx.AsyncClient(transport=httpx.MockTransport(api))

    resultado = await bc.buscar_clientes(texto)

    assert resultado and resultado[0]["number"] == "10000"
    assert resultado[0]["blocked"] == ""  # también normalizado por el camino del desglose
    assert all(len(campos_unidos_por_or(f)) <= 1 for f in api.filtros)
    await bc.cerrar()


async def test_busqueda_de_clientes_tolerante_a_tildes():
    ibanez = {"id": "c9", "number": "60000", "displayName": "Muebles Ibáñez", "blocked": "_x0020_"}
    api = ApiFalsa(clientes=[ADATUM, ibanez])
    bc = ClienteApiV2("tenant", "Sandbox", "app", "secreto", id_empresa="empresa-1")
    bc._http = httpx.AsyncClient(transport=httpx.MockTransport(api))

    # «ibanez» sin tilde no coincide en el servidor, pero «muebles» sí, y el orden se decide sin tildes.
    assert (await bc.buscar_clientes("muebles ibanez"))[0]["number"] == "60000"
    await bc.cerrar()
