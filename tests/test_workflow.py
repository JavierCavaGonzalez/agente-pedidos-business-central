"""Pruebas del workflow completo en modo simulado (sin modelo real ni Business Central real).

Siguen la recomendación del libro (cap. 14.7): probar cada pieza con dobles de prueba.
Aquí el modelo es el ``ClienteSimulado`` y el ERP es ``ClienteDemo``; lo que se verifica es
el reparto de decisiones: qué crea el código solo, qué espera a una persona y qué rechaza.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agente_pedidos.bc import ClienteDemo
from agente_pedidos.esquemas import DecisionHumana, ResultadoPedido
from agente_pedidos.middleware import AuditoriaHerramientas, SoloLectura
from agente_pedidos.politicas import Politica
from agente_pedidos.workflow import construir_workflow, crear_storage, dibujar_mermaid

CORREOS = Path(__file__).resolve().parents[1] / "ejemplos" / "correos"


async def ejecutar(workflow, correo: str):
    """Ejecuta hasta el final o hasta una petición de aprobación. Devuelve (salidas, petición pendiente)."""
    salidas: list[ResultadoPedido] = []
    pendiente = None
    pasos: list[str] = []
    async for evento in workflow.run(correo, stream=True):
        if evento.type == "executor_invoked":
            pasos.append(evento.executor_id)
        elif evento.type == "request_info":
            pendiente = evento
        elif evento.type == "output":
            salidas.append(evento.data)
    return salidas, pendiente, pasos


@pytest.mark.asyncio
async def test_pedido_pequeno_se_crea_sin_aprobacion(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    auditoria = AuditoriaHerramientas(tmp_path / "auditoria.jsonl")
    piezas = construir_workflow(bc, Politica(umbral_aprobacion=3000, aprobar_siempre=False), middleware=[auditoria])
    salidas, pendiente, pasos = await ejecutar(piezas.workflow, (CORREOS / "01_pedido_pequeno.txt").read_text(encoding="utf-8"))

    assert pendiente is None
    assert pasos == ["interpretar", "validar", "crear_pedido", "redactar"]
    assert len(salidas) == 1 and salidas[0].creado
    assert salidas[0].numero_cliente == "40000"
    assert salidas[0].total == pytest.approx(10 * 55.9)
    assert "Departamento comercial" in salidas[0].respuesta_cliente
    assert len(bc.pedidos) == 1 and bc.pedidos[0]["requestedDeliveryDate"] == "2026-12-15"
    assert bc.pedidos[0]["externalDocumentNumber"] == "PO-2026-0418"
    # la auditoría registra las lecturas que hizo el modelo
    assert [e["herramienta"] for e in auditoria.eventos] == ["buscar_clientes", "buscar_articulos"]
    assert piezas.contador.tokens_entrada > 0 and piezas.contador.coste_eur > 0


@pytest.mark.asyncio
async def test_pedido_grande_espera_aprobacion_y_se_reanuda_desde_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    storage = crear_storage(tmp_path / "checkpoints")
    piezas = construir_workflow(bc, Politica(umbral_aprobacion=3000), storage)
    salidas, pendiente, pasos = await ejecutar(piezas.workflow, (CORREOS / "02_pedido_grande.txt").read_text(encoding="utf-8"))

    assert salidas == [] and pendiente is not None
    assert pasos == ["interpretar", "validar", "aprobacion_humana"]
    solicitud = pendiente.data
    assert solicitud.total == pytest.approx(20 * 193.7 + 2 * 1000.8)
    assert "supera el umbral" in " ".join(solicitud.motivos)
    assert "1900-S" in solicitud.resumen and "1896-S" in solicitud.resumen
    assert bc.pedidos == []  # nada se ha escrito todavía

    checkpoint = await piezas.workflow.resolve_pause_checkpoint_id([pendiente.request_id])
    assert checkpoint is not None

    # Reanudar en una instancia NUEVA del workflow, como haría otro proceso horas después.
    piezas2 = construir_workflow(bc, Politica(umbral_aprobacion=3000), storage)
    salidas2 = []
    async for evento in piezas2.workflow.run(
        stream=True,
        checkpoint_id=checkpoint,
        responses={pendiente.request_id: DecisionHumana(aprobado=True, comentario="ok", aprobador="Ana")},
    ):
        if evento.type == "output":
            salidas2.append(evento.data)
    assert len(salidas2) == 1 and salidas2[0].creado
    assert "Aprobado por Ana" in salidas2[0].mensaje
    assert len(bc.pedidos) == 1 and bc.pedidos[0]["customerNumber"] == "10000"


@pytest.mark.asyncio
async def test_rechazo_humano_no_escribe_en_el_erp(monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    piezas = construir_workflow(bc, Politica(umbral_aprobacion=3000))
    _, pendiente, _ = await ejecutar(piezas.workflow, (CORREOS / "02_pedido_grande.txt").read_text(encoding="utf-8"))
    resultado = await piezas.workflow.run(responses={pendiente.request_id: DecisionHumana(aprobado=False, comentario="Sin crédito", aprobador="Ana")})
    salidas = resultado.get_outputs()
    assert len(salidas) == 1 and not salidas[0].creado
    assert "rechazado por Ana" in salidas[0].mensaje and "Sin crédito" in salidas[0].mensaje
    assert bc.pedidos == []


@pytest.mark.asyncio
async def test_cliente_bloqueado_se_rechaza_por_codigo(monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    piezas = construir_workflow(bc, Politica())
    salidas, pendiente, pasos = await ejecutar(piezas.workflow, (CORREOS / "03_cliente_bloqueado.txt").read_text(encoding="utf-8"))
    assert pendiente is None
    assert pasos == ["interpretar", "validar", "rechazar", "redactar"]
    assert not salidas[0].creado and "bloqueado" in salidas[0].mensaje
    assert bc.pedidos == []


@pytest.mark.asyncio
async def test_articulo_ambiguo_se_rechaza_con_explicacion(monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    piezas = construir_workflow(bc, Politica())
    salidas, pendiente, _ = await ejecutar(piezas.workflow, (CORREOS / "04_con_dudas.txt").read_text(encoding="utf-8"))
    assert pendiente is None
    assert not salidas[0].creado and "no identificado" in salidas[0].mensaje
    assert bc.pedidos == []


@pytest.mark.asyncio
async def test_politica_aprobar_siempre_detiene_incluso_pedidos_pequenos(monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    piezas = construir_workflow(bc, Politica(aprobar_siempre=True))
    salidas, pendiente, _ = await ejecutar(piezas.workflow, (CORREOS / "01_pedido_pequeno.txt").read_text(encoding="utf-8"))
    assert salidas == [] and pendiente is not None
    assert any("aprobación humana para toda escritura" in m for m in pendiente.data.motivos)


@pytest.mark.asyncio
async def test_el_modo_solo_lectura_no_afecta_al_workflow_pero_si_a_las_herramientas(monkeypatch):
    """El workflow escribe con código (no con una herramienta del modelo), así que SoloLectura no lo bloquea;
    sí bloquea la herramienta crear_pedido_venta del agente asistente (ver test_chat_aprobacion)."""
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    bc = ClienteDemo()
    piezas = construir_workflow(bc, Politica(), middleware=[SoloLectura(activo=True)])
    salidas, _, _ = await ejecutar(piezas.workflow, (CORREOS / "01_pedido_pequeno.txt").read_text(encoding="utf-8"))
    assert salidas[0].creado


def test_el_grafo_se_dibuja():
    mermaid = dibujar_mermaid(construir_workflow(ClienteDemo()).workflow)
    for nodo in ("interpretar", "validar", "aprobacion_humana", "crear_pedido", "rechazar", "redactar"):
        assert nodo in mermaid
