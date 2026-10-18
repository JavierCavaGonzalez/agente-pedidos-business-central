"""Oficina: endpoints del backend y una prueba de extremo a extremo con el ERP simulado."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agente_pedidos import eventos
from agente_pedidos.cli import cmd_procesar, cmd_reanudar
from ui.backend.app import Config, _lineas_nuevas, crear_app

RAIZ = Path(__file__).resolve().parents[1]
CORREOS = RAIZ / "ejemplos" / "correos"


@pytest.fixture
def oficina(tmp_path, monkeypatch, eventos_temporales):
    # Los subprocesos heredan este entorno: modelo y ERP simulados, todo en carpetas temporales.
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    monkeypatch.setenv("BC_MODO", "demo")
    monkeypatch.setenv("AGENTE_SOLO_LECTURA", "0")
    monkeypatch.setenv("AGENTE_AUDITORIA", str(tmp_path / "auditoria.jsonl"))
    monkeypatch.setenv("AGENTE_CHECKPOINTS", str(tmp_path / "checkpoints"))
    config = Config(
        eventos=eventos_temporales,
        checkpoints=tmp_path / "checkpoints",
        bandeja=tmp_path / "bandeja",
        estaticos=RAIZ / "ui" / "static",
        erp_demo=tmp_path / "erp_demo_pedidos.json",
    )
    with TestClient(crear_app(config)) as cliente:
        cliente.config = config
        yield cliente


def esperar(condicion, segundos: float = 120, cada: float = 0.5):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        valor = condicion()
        if valor:
            return valor
        time.sleep(cada)
    raise AssertionError("La condición no se cumplió a tiempo")


def test_estado_inicial_con_la_oficina_vacia(oficina):
    foto = oficina.get("/api/estado").json()
    [pedidos] = foto["agentes"]
    assert (pedidos["id"], pedidos["nombre"], pedidos["rol"], pedidos["estado"]) == ("pedidos", "Agente de Pedidos", "Ventas", "libre")
    assert foto["tablero"] == {"agentes_activos": 0, "tareas_en_curso": 0, "aprobaciones_pendientes": 0, "escrituras_erp_hoy": 0, "coste_hoy_eur": 0, "llamadas_modelo_hoy": 0}
    assert (foto["modo_erp"], foto["modelo"]) == ("demo", "simulado")


def test_la_portada_y_los_correos_de_ejemplo(oficina):
    assert oficina.get("/").status_code == 200
    nombres = [c["nombre"] for c in oficina.get("/api/correos").json()]
    assert "02_pedido_grande.txt" in nombres and "06_cronus_es_grande.txt" in nombres


def test_un_agente_que_no_existe_o_detenido_no_recibe_tareas(oficina):
    assert oficina.post("/api/tareas", json={"agente": "compras", "correo": "hola"}).status_code == 404
    assert oficina.post("/api/agentes/pedidos/detener").status_code == 200
    assert oficina.get("/api/estado").json()["agentes"][0]["estado"] == "detenido"
    respuesta = oficina.post("/api/tareas", json={"agente": "pedidos", "correo": "hola"})
    assert respuesta.status_code == 409 and "detenido" in respuesta.json()["detail"]
    assert oficina.post("/api/agentes/pedidos/activar").status_code == 200
    assert oficina.get("/api/estado").json()["agentes"][0]["estado"] == "libre"
    # Las dos acciones del director quedan en el registro.
    assert [e["tipo"] for e in eventos.leer_eventos(oficina.config.eventos)] == ["agente_detenido", "agente_activado"]


async def test_una_aprobacion_ya_resuelta_devuelve_409(oficina, capsys):
    await cmd_procesar(str(CORREOS / "02_pedido_grande.txt"), "pendiente", "ana")
    [aprobacion] = oficina.get("/api/aprobaciones").json()
    assert aprobacion["cliente"] == "10000 Adatum Corporation" and aprobacion["importe"] == 5875.6
    assert [l["articulo"] for l in aprobacion["lineas"]] == ["1900-S", "1896-S"] and aprobacion["tarea"].startswith("tarea_")
    await cmd_reanudar(aprobacion["checkpoint_id"], "si", "OK", "Javier")

    respuesta = oficina.post(f"/api/aprobaciones/{aprobacion['checkpoint_id']}", json={"decision": "si", "aprobador": "Javier"})
    assert respuesta.status_code == 409 and "ya se resolvió" in respuesta.json()["detail"]
    assert oficina.get("/api/aprobaciones").json() == []
    assert oficina.post("/api/aprobaciones/no-existe", json={"decision": "si"}).status_code in (404, 409)
    assert oficina.post(f"/api/aprobaciones/{aprobacion['checkpoint_id']}", json={"decision": "quizas"}).status_code == 422


def test_lineas_nuevas_no_entrega_una_linea_a_medio_escribir(tmp_path):
    ruta = tmp_path / "e.jsonl"
    ruta.write_bytes(b'{"a": 1}\n{"b": 2')
    lineas, posicion = _lineas_nuevas(ruta, 0)
    assert lineas == ['{"a": 1}'] and posicion == len('{"a": 1}\n')
    with ruta.open("ab") as f:
        f.write(b"}\n")
    assert _lineas_nuevas(ruta, posicion) == (['{"b": 2}'], ruta.stat().st_size)


def test_de_extremo_a_extremo_asignar_esperar_aprobar_y_pedido_creado(oficina):
    correo = (CORREOS / "02_pedido_grande.txt").read_text(encoding="utf-8")
    respuesta = oficina.post("/api/tareas", json={"agente": "pedidos", "correo": correo, "origen": "02_pedido_grande.txt"})
    assert respuesta.status_code == 202
    tarea = respuesta.json()["tarea"]

    # El subproceso «procesar --aprobar pendiente» se para en la aprobación.
    [aprobacion] = esperar(lambda: oficina.get("/api/aprobaciones").json())
    assert aprobacion["tarea"] == tarea
    foto = oficina.get("/api/estado").json()
    assert foto["agentes"][0]["estado"] == "esperando_aprobacion"
    assert foto["tablero"]["aprobaciones_pendientes"] == 1 and foto["tablero"]["tareas_en_curso"] == 1

    # Aprobar desde la «tarjeta»: lanza «reanudar»; un segundo clic se rechaza.
    url = f"/api/aprobaciones/{aprobacion['checkpoint_id']}"
    assert oficina.post(url, json={"decision": "si", "aprobador": "Javier", "comentario": "OK"}).status_code == 202
    assert oficina.post(url, json={"decision": "si", "aprobador": "Javier"}).status_code == 409

    tarea_hecha = esperar(lambda: next((t for t in oficina.get("/api/estado").json()["tareas"] if t["id"] == tarea and t["estado"] == "terminada"), None))
    assert tarea_hecha["resultado"] == "creado" and tarea_hecha["pedido"].startswith("S-ORD")
    foto = oficina.get("/api/estado").json()
    assert foto["tablero"]["escrituras_erp_hoy"] == 1 and foto["tablero"]["aprobaciones_pendientes"] == 0
    assert foto["tablero"]["coste_hoy_eur"] == pytest.approx(tarea_hecha["coste_eur"]) and tarea_hecha["coste_eur"] > 0

    cronologia = oficina.get("/api/agentes/pedidos/cronologia").json()
    tipos = [e["tipo"] for e in cronologia["eventos"]]
    assert tipos[0] == "tarea_iniciada" and tipos[-1] == "tarea_terminada"
    assert {"aprobacion_solicitada", "aprobacion_resuelta", "erp_escritura"} <= set(tipos)
    assert cronologia["pedidos"][0]["pedido"] == tarea_hecha["pedido"]
    resuelta = next(e for e in cronologia["eventos"] if e["tipo"] == "aprobacion_resuelta")["datos"]
    assert (resuelta["aprobador"], resuelta["comentario"]) == ("Javier", "OK")

    # La aprobación hecha desde la pantalla queda también en la auditoría.
    auditoria = [json.loads(l) for l in (oficina.config.checkpoints.parent / "auditoria.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e.get("evento") == "escritura_erp" and e["resultado"]["number"] == tarea_hecha["pedido"] for e in auditoria)
    assert (oficina.config.bandeja / f"{tarea}.txt").read_text(encoding="utf-8") == correo
    assert next(t for t in oficina.get("/api/estado").json()["tareas"] if t["id"] == tarea)["origen"] == "02_pedido_grande.txt"


async def test_la_oficina_no_resuelve_una_aprobacion_de_otro_modo_de_erp(oficina, monkeypatch):
    await cmd_procesar(str(CORREOS / "02_pedido_grande.txt"), "pendiente", "ana")
    [aprobacion] = oficina.get("/api/aprobaciones").json()
    assert aprobacion["modo_erp"] == "demo"
    monkeypatch.setenv("BC_MODO", "api")
    respuesta = oficina.post(f"/api/aprobaciones/{aprobacion['checkpoint_id']}", json={"decision": "si", "aprobador": "Javier"})
    assert respuesta.status_code == 409 and "BC_MODO=demo" in respuesta.json()["detail"]


def test_la_foto_trae_los_paneles_y_preguntar_valida_el_agente(oficina, monkeypatch):
    monkeypatch.setenv("OFICINA_PRESUPUESTO_DIA_EUR", "0,50")
    foto = oficina.get("/api/estado").json()
    assert (foto["feed"], foto["pedidos"], foto["presupuesto_dia_eur"]) == ([], [], 0.5)
    assert (foto["erp"]["modo"], foto["erp"]["entorno"], foto["erp"]["enlace"]) == ("demo", "Simulación", None)
    agente = foto["agentes"][0]
    assert (agente["herramientas"], agente["tareas_en_curso"], agente["capacidad"]) == ([], 0, 3)
    assert oficina.post("/api/preguntas", json={"agente": "compras", "mensaje": "hola"}).status_code == 404
    assert oficina.post("/api/preguntas", json={"agente": "pedidos", "mensaje": ""}).status_code == 422
