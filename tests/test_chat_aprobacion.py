"""Aprobación a nivel de agente (``approval_mode="always_require"``) y middleware, en modo simulado."""

from __future__ import annotations

import pytest
from agent_framework import Message

from agente_pedidos.agentes import crear_agente_asistente
from agente_pedidos.bc import ClienteDemo
from agente_pedidos.middleware import AuditoriaHerramientas, PresupuestoLlamadas, SoloLectura

PETICION = "Empresa: Adatum Corporation. Necesito 5 lámparas AMSTERDAM"


@pytest.mark.asyncio
async def test_la_escritura_se_detiene_hasta_que_una_persona_aprueba(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    auditoria = AuditoriaHerramientas(tmp_path / "auditoria.jsonl")
    agente = crear_agente_asistente(bc, middleware=[auditoria])
    sesion = agente.create_session()

    respuesta = await agente.run(PETICION, session=sesion)
    assert len(respuesta.user_input_requests) == 1
    peticion = respuesta.user_input_requests[0]
    assert peticion.function_call.name == "crear_pedido_venta"
    argumentos = peticion.function_call.parse_arguments()
    assert argumentos["numero_cliente"] == "10000"
    assert argumentos["lineas"] == [{"numero_articulo": "1928-S", "cantidad": 5.0}]
    assert bc.pedidos == []  # todavía no se ha escrito nada

    aprobacion = peticion.to_function_approval_response(approved=True)
    final = await agente.run(Message("user", [aprobacion]), session=sesion)
    assert "S-ORD" in (final.text or "")
    assert len(bc.pedidos) == 1 and bc.pedidos[0]["totalAmountExcludingTax"] == pytest.approx(5 * 55.9)
    assert [e["herramienta"] for e in auditoria.eventos] == ["buscar_clientes", "buscar_articulos", "crear_pedido_venta"]


@pytest.mark.asyncio
async def test_el_rechazo_no_ejecuta_la_herramienta(monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    agente = crear_agente_asistente(bc)
    sesion = agente.create_session()
    respuesta = await agente.run(PETICION, session=sesion)
    rechazo = respuesta.user_input_requests[0].to_function_approval_response(approved=False)
    final = await agente.run(Message("user", [rechazo]), session=sesion)
    assert bc.pedidos == []
    assert "rejected" in (final.text or "").lower() or "no se ha creado" in (final.text or "").lower()


@pytest.mark.asyncio
async def test_el_middleware_solo_lectura_bloquea_aunque_se_apruebe(monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    solo_lectura = SoloLectura(activo=True)
    agente = crear_agente_asistente(bc, middleware=[solo_lectura])
    sesion = agente.create_session()
    respuesta = await agente.run(PETICION, session=sesion)
    aprobacion = respuesta.user_input_requests[0].to_function_approval_response(approved=True)
    final = await agente.run(Message("user", [aprobacion]), session=sesion)
    assert bc.pedidos == []
    assert solo_lectura.bloqueadas == ["crear_pedido_venta"]
    assert "bloqueada por política" in (final.text or "")


@pytest.mark.asyncio
async def test_el_presupuesto_de_llamadas_corta_la_ejecucion(monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    presupuesto = PresupuestoLlamadas(maximo=1)  # solo una llamada al modelo: no da tiempo a terminar
    agente = crear_agente_asistente(bc, middleware=[presupuesto])
    respuesta = await agente.run(PETICION, session=agente.create_session())
    assert "Presupuesto agotado" in (respuesta.text or "")
    assert bc.pedidos == []
