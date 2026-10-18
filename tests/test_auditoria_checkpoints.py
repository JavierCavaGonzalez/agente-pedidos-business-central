"""Auditoría de escrituras en el cliente del ERP, ciclo de vida de los checkpoints e idempotencia."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from agent_framework import Message

from agente_pedidos.agentes import crear_agente_asistente
from agente_pedidos.bc import ClienteApiV2, ClienteDemo, PedidoDuplicado
from agente_pedidos.cli import cmd_pendientes, cmd_procesar, cmd_reanudar
from agente_pedidos.herramientas import crear_herramienta_escritura
from agente_pedidos.middleware import AuditoriaHerramientas, SoloLectura
from agente_pedidos.workflow import REGISTRO_RESUELTAS, construir_workflow

CORREOS = Path(__file__).resolve().parents[1] / "ejemplos" / "correos"
PETICION = "Empresa: Adatum Corporation. Necesito 5 lámparas AMSTERDAM"


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    monkeypatch.setenv("BC_MODO", "demo")
    monkeypatch.setenv("AGENTE_AUDITORIA", str(tmp_path / "auditoria.jsonl"))
    monkeypatch.setenv("AGENTE_CHECKPOINTS", str(tmp_path / "checkpoints"))
    return tmp_path


def leer_auditoria(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def escrituras(eventos: list[dict]) -> list[dict]:
    return [e for e in eventos if e.get("herramienta") == "crear_pedido_venta"]


def checkpoint_de(salida: str) -> str:
    return salida.split("--checkpoint ")[1].split()[0]


# --- 1. auditoría de escrituras ---------------------------------------------------------------


async def test_un_pedido_creado_desde_el_workflow_queda_en_la_auditoria(entorno, capsys):
    assert await cmd_procesar(str(CORREOS / "01_pedido_pequeno.txt"), "si", "ana") == 0
    assert "Pedido creado: sí" in capsys.readouterr().out

    [escritura] = escrituras(leer_auditoria(entorno / "auditoria.jsonl"))
    assert escritura["evento"] == "escritura_erp" and escritura["origen"] == "codigo"
    assert escritura["argumentos"]["referencia_externa"] == "PO-2026-0418"
    assert escritura["resultado"]["number"].startswith("S-ORD")
    assert escritura["resultado"]["lineas"] == [
        {"articulo": "1928-S", "descripcion": "AMSTERDAM Lamp", "cantidad": 10.0, "importe": 559.0}
    ]


async def test_en_chat_la_escritura_deja_una_sola_linea(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    auditoria = AuditoriaHerramientas(tmp_path / "auditoria.jsonl")
    bc = ClienteDemo()
    bc.auditoria = auditoria  # el cliente del ERP y el middleware comparten registro
    agente = crear_agente_asistente(bc, middleware=[auditoria])
    sesion = agente.create_session()
    respuesta = await agente.run(PETICION, session=sesion)
    aprobacion = respuesta.user_input_requests[0].to_function_approval_response(approved=True)
    await agente.run(Message("user", [aprobacion]), session=sesion)

    [escritura] = escrituras(leer_auditoria(tmp_path / "auditoria.jsonl"))
    assert escritura["origen"] == "herramienta" and escritura["resultado"]["number"].startswith("S-ORD")
    assert [e["herramienta"] for e in auditoria.eventos] == ["buscar_clientes", "buscar_articulos", "crear_pedido_venta"]


async def test_una_escritura_bloqueada_por_solo_lectura_tambien_deja_su_linea(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    auditoria = AuditoriaHerramientas(tmp_path / "auditoria.jsonl")
    bc = ClienteDemo()
    bc.auditoria = auditoria
    agente = crear_agente_asistente(bc, middleware=[auditoria, SoloLectura(activo=True)])
    sesion = agente.create_session()
    respuesta = await agente.run(PETICION, session=sesion)
    aprobacion = respuesta.user_input_requests[0].to_function_approval_response(approved=True)
    await agente.run(Message("user", [aprobacion]), session=sesion)

    [linea] = escrituras(auditoria.eventos)
    assert "evento" not in linea  # la escribe el middleware: la escritura no llegó al ERP
    assert "bloqueada por política" in linea["resultado"]["error"]
    assert bc.pedidos == []


# --- 2. ciclo de vida de los checkpoints --------------------------------------------------------


async def test_reanudar_resuelve_la_aprobacion_y_no_se_puede_repetir(entorno, capsys):
    await cmd_procesar(str(CORREOS / "02_pedido_grande.txt"), "pendiente", "ana")
    salida = capsys.readouterr().out
    checkpoint = checkpoint_de(salida)
    assert "Coste hasta la parada:" in salida  # punto 3: el coste de lo ejecutado

    await cmd_pendientes()
    assert checkpoint in capsys.readouterr().out

    assert await cmd_reanudar(checkpoint, "si", "OK", "Javier") == 0
    assert "Pedido creado: sí" in capsys.readouterr().out

    await cmd_pendientes()
    assert "No hay aprobaciones pendientes." in capsys.readouterr().out

    assert await cmd_reanudar(checkpoint, "si", "otra vez", "Javier") == 1
    rechazo = capsys.readouterr().out
    assert f"No se reanuda el checkpoint {checkpoint}" in rechazo and "aprobada por Javier" in rechazo


async def test_una_aprobacion_resuelta_en_el_mismo_proceso_no_queda_pendiente(entorno, capsys):
    await cmd_procesar(str(CORREOS / "02_pedido_grande.txt"), "si", "ana")
    capsys.readouterr()
    await cmd_pendientes()
    assert "No hay aprobaciones pendientes." in capsys.readouterr().out

    # Aunque se pierda el registro, la cadena de checkpoints muestra que la ejecución continuó
    # (así se reconocen también los checkpoints anteriores a este cambio).
    (entorno / "checkpoints" / REGISTRO_RESUELTAS).unlink()
    await cmd_pendientes()
    assert "No hay aprobaciones pendientes." in capsys.readouterr().out


# --- 3. idempotencia de pedidos -----------------------------------------------------------------


async def test_el_mismo_correo_dos_veces_no_crea_dos_pedidos(monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    correo = (CORREOS / "01_pedido_pequeno.txt").read_text(encoding="utf-8")
    resultados = []
    for _ in range(2):
        piezas = construir_workflow(bc)
        resultados += [e.data async for e in piezas.workflow.run(correo, stream=True) if e.type == "output"]

    primero, segundo = resultados
    assert primero.creado and not segundo.creado
    assert segundo.numero_pedido == primero.numero_pedido
    assert "Ya existe el pedido" in segundo.mensaje
    assert len(bc.pedidos) == 1


async def test_la_herramienta_devuelve_el_duplicado_como_error_de_datos():
    bc = ClienteDemo()
    herramienta = crear_herramienta_escritura(bc, requiere_aprobacion=False)
    argumentos = {"numero_cliente": "10000", "lineas": [{"numero_articulo": "1928-S", "cantidad": 1}], "referencia_externa": "REF-1"}
    primero = await herramienta.invoke(arguments=argumentos, skip_parsing=True)
    segundo = await herramienta.invoke(arguments=argumentos, skip_parsing=True)
    assert "error" not in primero
    assert segundo == {"error": f"Ya existe el pedido {primero['number']} del cliente 10000 con la referencia REF-1; no se crea otro"}
    assert len(bc.pedidos) == 1


async def test_contra_la_api_un_pedido_existente_no_se_vuelve_a_crear():
    peticiones: list[tuple[str, str]] = []

    def api(peticion: httpx.Request) -> httpx.Response:
        if "oauth2" in peticion.url.path:
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        peticiones.append((peticion.method, peticion.url.params.get("$filter", "")))
        existente = {"id": "so1", "number": "101022", "customerNumber": "20000", "externalDocumentNumber": "TRY-5531"}
        return httpx.Response(200, json={"value": [existente]})

    bc = ClienteApiV2("tenant", "Sandbox", "app", "secreto", id_empresa="empresa-1")
    bc._http = httpx.AsyncClient(transport=httpx.MockTransport(api))
    with pytest.raises(PedidoDuplicado, match="101022"):
        await bc.crear_pedido_venta("20000", [{"numero_articulo": "1896-S", "cantidad": 3}], referencia_externa="TRY-5531")
    assert peticiones == [("GET", "customerNumber eq '20000' and externalDocumentNumber eq 'TRY-5531'")]  # ningún POST
    await bc.cerrar()
