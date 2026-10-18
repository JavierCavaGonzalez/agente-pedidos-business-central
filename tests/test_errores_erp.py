"""Errores del ERP: las lecturas los devuelven como datos y la auditoría registra también los fallos."""

from __future__ import annotations

import pytest

from agente_pedidos.agentes import crear_agente_interprete
from agente_pedidos.bc import ClienteDemo
from agente_pedidos.bc.base import ErrorBC
from agente_pedidos.herramientas import crear_herramientas_lectura
from agente_pedidos.middleware import AuditoriaHerramientas

MENSAJE_501 = "Business Central respondió 501: The 'OR' operator is not supported on distinct fields on an OData filter."


class ErpQueFalla(ClienteDemo):
    """Business Central que responde con error a todas las lecturas."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def buscar_clientes(self, texto):
        raise self.error

    async def obtener_cliente(self, numero):
        raise self.error

    async def buscar_articulos(self, texto):
        raise self.error

    async def obtener_articulo(self, numero):
        raise self.error


@pytest.mark.parametrize(
    ("nombre", "argumentos"),
    [
        ("buscar_clientes", {"texto": "Adatum"}),
        ("obtener_cliente", {"numero": "10000"}),
        ("buscar_articulos", {"texto": "AMSTERDAM"}),
        ("obtener_articulo", {"numero": "1928-S"}),
    ],
)
async def test_las_lecturas_devuelven_el_error_del_erp_como_dato(nombre, argumentos):
    herramientas = {h.name: h for h in crear_herramientas_lectura(ErpQueFalla(ErrorBC(MENSAJE_501)))}
    resultado = await herramientas[nombre].invoke(arguments=argumentos, skip_parsing=True)
    assert resultado == {"error": MENSAJE_501}


async def test_la_auditoria_registra_la_herramienta_que_falla_con_su_error(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    auditoria = AuditoriaHerramientas(tmp_path / "auditoria.jsonl")
    # Un fallo inesperado (no un ErrorBC): la herramienta lanza la excepción y el framework se la pasa al modelo.
    agente = crear_agente_interprete(ErpQueFalla(RuntimeError("tiempo de espera agotado")), middleware=[auditoria])

    await agente.run("Empresa: Adatum Corporation. Necesito 5 lámparas AMSTERDAM", session=agente.create_session())

    fallos = [e for e in auditoria.eventos if "error" in e]
    assert fallos, "la herramienta que falla debe quedar en la auditoría"
    assert fallos[0]["herramienta"] == "buscar_clientes"
    assert fallos[0]["error"] == "RuntimeError: tiempo de espera agotado"
    assert fallos[0]["resultado"] is None
    assert len((tmp_path / "auditoria.jsonl").read_text(encoding="utf-8").splitlines()) == len(auditoria.eventos)
