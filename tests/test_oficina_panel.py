"""Oficina: datos de los paneles (seguimiento de tarea, pedidos del día, feed, herramientas) y «Preguntar al agente»."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from agente_pedidos import eventos
from agente_pedidos.cli import cmd_chat, cmd_procesar, cmd_reanudar
from agente_pedidos.workflow import aprobaciones_pendientes, crear_storage
from ui.backend import business_central, estado

CORREOS = Path(__file__).resolve().parents[1] / "ejemplos" / "correos"
AHORA = datetime(2026, 10, 18, 16, 0, 0).astimezone()


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    monkeypatch.setenv("BC_MODO", "demo")
    monkeypatch.setenv("AGENTE_AUDITORIA", str(tmp_path / "auditoria.jsonl"))
    monkeypatch.setenv("AGENTE_CHECKPOINTS", str(tmp_path / "checkpoints"))
    monkeypatch.delenv("AGENTE_TAREA", raising=False)
    eventos.fijar_tarea(None)
    return tmp_path


def ev(tipo: str, hace_s: float, tarea: str | None = "t1", **datos) -> dict:
    return {"ts": (AHORA - timedelta(seconds=hace_s)).isoformat(), "agente": "pedidos", "tarea": tarea, "tipo": tipo, "datos": datos}


def pasos(seguimiento: dict) -> dict[str, str]:
    return {p["clave"]: p["estado"] for p in seguimiento["pasos"]}


def unica_tarea(fichero: Path) -> estado.Tarea:
    [tarea] = estado.agrupar_tareas(eventos.leer_eventos(fichero)).values()
    return tarea


async def test_seguimiento_de_un_pedido_grande_parado_en_la_aprobacion_y_despues_creado(entorno, eventos_temporales, capsys):
    await cmd_procesar(str(CORREOS / "02_pedido_grande.txt"), "pendiente", "ana")
    parado = estado.seguimiento(unica_tarea(eventos_temporales), datetime.now().astimezone())
    assert pasos(parado) == {"recibido": "hecho", "interpretado": "hecho", "validado": "hecho", "aprobacion": "actual", "creado": "pendiente", "respondido": "pendiente"}
    assert parado["actual"] == "aprobacion" and parado["cliente"].startswith("10000") and parado["total"] > 3000
    assert parado["lineas"] and {"articulo", "descripcion", "cantidad", "importe"} <= set(parado["lineas"][0])
    assert all(p["duracion_s"] is not None for p in parado["pasos"][:4])

    [checkpoint] = await aprobaciones_pendientes(crear_storage(entorno / "checkpoints"))
    await cmd_reanudar(checkpoint.checkpoint_id, "si", "", "ana")
    hecho = estado.seguimiento(unica_tarea(eventos_temporales), datetime.now().astimezone())
    assert set(pasos(hecho).values()) == {"hecho"} and hecho["actual"] is None
    notas = {p["clave"]: p["nota"] for p in hecho["pasos"]}
    assert notas["aprobacion"] == "Aprobado por ana" and notas["creado"].startswith("Pedido S-ORD")


async def test_seguimiento_de_un_pedido_pequeno_sin_aprobacion(entorno, eventos_temporales, capsys):
    await cmd_procesar(str(CORREOS / "01_pedido_pequeno.txt"), "si", "ana")
    seguimiento = estado.seguimiento(unica_tarea(eventos_temporales), datetime.now().astimezone())
    assert pasos(seguimiento)["aprobacion"] == "omitido" and pasos(seguimiento)["creado"] == "hecho"
    assert next(p["nota"] for p in seguimiento["pasos"] if p["clave"] == "aprobacion") == "No hacía falta"


def test_seguimiento_de_un_pedido_denegado_y_de_uno_rechazado():
    base = [ev("tarea_iniciada", 60), ev("paso", 50, nombre="interpretar"), ev("paso", 40, nombre="validar")]
    denegado = base + [
        ev("paso", 39, nombre="politica", descripcion="Necesita aprobación"),
        ev("aprobacion_solicitada", 38, importe=5000),
        ev("aprobacion_resuelta", 20, decision="no", aprobador="Javier"),
        ev("paso", 19, nombre="rechazar", descripcion="Denegado por Javier"),
        ev("paso", 18, nombre="redactar"),
        ev("tarea_terminada", 10, resultado="denegado"),
    ]
    s = estado.seguimiento(next(iter(estado.agrupar_tareas(denegado).values())), AHORA)
    assert pasos(s) == {"recibido": "hecho", "interpretado": "hecho", "validado": "hecho", "aprobacion": "fallido", "creado": "omitido", "respondido": "hecho"}
    rechazado = base + [ev("paso", 39, nombre="politica", descripcion="No se puede crear: cliente bloqueado"), ev("paso", 38, nombre="rechazar", descripcion="No se crea: cliente bloqueado")]
    s = estado.seguimiento(next(iter(estado.agrupar_tareas(rechazado).values())), AHORA)
    assert pasos(s)["validado"] == "fallido" and "bloqueado" in next(p["nota"] for p in s["pasos"] if p["clave"] == "validado")


def test_pedidos_del_dia_con_cliente_y_enlace_solo_en_modo_api():
    api = {"BC_MODO": "api", "BC_TENANT_ID": "t", "BC_ENVIRONMENT": "TEST29", "BC_COMPANY_NAME": "CRONUS ES"}
    lista = [
        ev("tarea_iniciada", 60),
        ev("paso", 50, nombre="politica", descripcion="Dentro de la política", cliente="10000 Adatum Corporation", total=3781.4, lineas=[]),
        ev("erp_escritura", 40, operacion="crear_pedido", pedido="101023", importe=3781.4, cliente="10000", modo="api"),
        ev("erp_escritura", 30, tarea="t2", operacion="crear_pedido", pedido="S-ORD101001", importe=559.0, cliente="20000", modo="demo"),
    ]
    foto = estado.foto(lista, AHORA, [], modo_erp="api", modelo="x", enlace_pedido=lambda n: business_central.enlace_pedido(n, api))
    simulado, real = foto["pedidos"]
    assert (real["pedido"], real["cliente"], real["estado_bc"]) == ("101023", "10000 Adatum Corporation", "Abierto")
    assert real["enlace"].endswith("page=42&filter=%27No.%27%20IS%20%27101023%27")
    assert simulado["enlace"] is None and simulado["cliente"] == "20000"
    assert foto["erp"]["escrituras_hoy"] == 2 and foto["erp"]["ultima_escritura"]["pedido"] == "S-ORD101001"
    assert foto["agentes"][0]["pedidos_hoy"] == foto["pedidos"]


def test_feed_categorias_errores_y_herramientas():
    lista = [
        ev("tarea_iniciada", 60, origen="02_pedido_grande.txt"),
        ev("herramienta", 55, nombre="buscar_clientes", argumentos={"texto": "Adatum"}, resultado="ok"),
        ev("herramienta", 54, nombre="buscar_articulos", argumentos={"texto": "X"}, resultado="ErrorBC: 404"),
        ev("modelo_llamada", 53, modelo="gpt", tokens_entrada=1200, tokens_salida=100, coste_eur=0.0021),
        ev("aprobacion_solicitada", 50, importe=5875.6, motivo="supera 3.000 €"),
    ]
    filas = estado.feed(lista)
    assert [f["categoria"] for f in filas] == ["aprobaciones", "modelo", "bc", "bc", "tareas"]
    assert filas[0]["texto"] == "Aprobación solicitada · 5.875,60 € · supera 3.000 €"
    assert filas[1]["texto"] == "Llamada al modelo · 1.300 tokens · 0,0021 €"
    assert filas[2]["error"] and not filas[3]["error"]
    assert estado.herramientas(lista) == [{"nombre": "buscar_clientes", "llamadas": 1, "errores": 0}, {"nombre": "buscar_articulos", "llamadas": 1, "errores": 1}]
    assert len(estado.feed(lista * 50, limite=80)) == 80


async def test_preguntar_al_agente_deja_la_respuesta_y_su_coste_en_eventos(entorno, eventos_temporales, monkeypatch, capsys):
    monkeypatch.setenv("CHAT_APROBAR", "no")  # sin terminal: la escritura protegida se deniega
    await cmd_chat("Empresa: Adatum Corporation. Necesito 5 lámparas AMSTERDAM", "Director")
    lista = eventos.leer_eventos(eventos_temporales)
    assert lista[0]["tipo"] == "tarea_iniciada" and lista[0]["datos"]["clase"] == "pregunta"
    respuesta = next(e for e in lista if e["tipo"] == "respuesta_agente")["datos"]
    fin = lista[-1]
    assert fin["tipo"] == "tarea_terminada" and fin["datos"]["resultado"] == "respondido"
    assert respuesta["coste_eur"] == pytest.approx(sum(e["datos"]["coste_eur"] for e in lista if e["tipo"] == "modelo_llamada"))
    assert not any(e["tipo"] == "erp_escritura" for e in lista)
    tarea = unica_tarea(eventos_temporales)
    assert estado.seguimiento(tarea, AHORA) is None
    assert any(f["texto"].startswith("Respuesta: ") for f in estado.feed(lista))


async def test_estado_oficina_da_al_asistente_la_aprobacion_pendiente_con_importe_y_motivo(entorno, eventos_temporales, monkeypatch, capsys):
    from agente_pedidos.estado_oficina import estado_oficina

    await cmd_procesar(str(CORREOS / "02_pedido_grande.txt"), "pendiente", "ana")
    estado_hoy = await estado_oficina()
    [pendiente] = estado_hoy["aprobaciones_pendientes"]
    assert pendiente["cliente"] == "10000 Adatum Corporation" and pendiente["importe"] == "5.875,60 €"
    assert pendiente["motivo"] == "El importe 5.875,60 € supera el umbral de 3.000,00 €" and pendiente["erp"] == "simulado"
    [tarea] = estado_hoy["tareas_de_hoy"]
    assert tarea["estado"] == "esperando aprobación" and tarea["paso_actual"] == "Esperando la decisión del director"
    assert estado_hoy["pedidos_creados_hoy"] == []

    # La pregunta por chat usa la herramienta (solo lectura) y contesta con estado, importe y motivo; no cuenta como tarea
    monkeypatch.setenv("CHAT_APROBAR", "no")
    eventos.fijar_tarea(None)
    await cmd_chat("¿En qué estado está el pedido de Adatum Corporation que espera aprobación?", "Director")
    lista = eventos.leer_eventos(eventos_temporales)
    respuesta = next(e for e in lista if e["tipo"] == "respuesta_agente")["datos"]["texto"]
    assert "esperando aprobación" in respuesta and "5.875,60 €" in respuesta and "supera el umbral de 3.000,00 €" in respuesta
    assert any(e["tipo"] == "herramienta" and e["datos"]["nombre"] == "estado_oficina" for e in lista)
    assert not any(e["tipo"] == "erp_escritura" for e in lista)
    assert len((await estado_oficina())["tareas_de_hoy"]) == 1  # la pregunta no es una tarea
