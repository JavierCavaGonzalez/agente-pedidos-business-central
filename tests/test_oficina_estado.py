"""Oficina: estado de los agentes y tablero derivados de secuencias de eventos (sin E/S)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ui.backend import estado

AHORA = datetime(2026, 10, 18, 16, 0, 0).astimezone()


def ev(tipo: str, hace_s: float, tarea: str | None = "t1", agente: str = "pedidos", **datos) -> dict:
    return {"ts": (AHORA - timedelta(seconds=hace_s)).isoformat(), "agente": agente, "tarea": tarea, "tipo": tipo, "datos": datos}


def agente(eventos: list[dict], **kwargs) -> dict:
    return estado.estado_agentes(eventos, AHORA, **kwargs)[0]


INICIO = [ev("tarea_iniciada", 60, origen="02_pedido_grande.txt", resumen="Asunto: …")]


def test_sin_eventos_el_agente_esta_libre():
    a = agente([])
    assert (a["estado"], a["tarea"], a["bocadillo"], a["desde"]) == ("libre", None, None, None)


def test_con_una_tarea_en_marcha_esta_trabajando_y_el_bocadillo_dice_el_paso():
    eventos = INICIO + [ev("paso", 50, nombre="interpretar", descripcion="Leyendo el correo")]
    a = agente(eventos)
    assert (a["estado"], a["tarea"], a["bocadillo"], a["desde"]) == ("trabajando", "t1", "Leyendo el correo", eventos[-1]["ts"])

    eventos.append(ev("herramienta", 45, nombre="buscar_clientes", argumentos={"texto": "Adatum"}, resultado="ok", duracion_ms=12))
    assert agente(eventos)["bocadillo"] == "Buscando cliente «Adatum»…"
    eventos.append(ev("herramienta", 44, nombre="buscar_articulos", argumentos={"texto": "PARIS"}, resultado="ErrorBC: 501", duracion_ms=12))
    assert agente(eventos)["bocadillo"] == "Buscando artículo «PARIS»: ErrorBC: 501"
    # Una llamada al modelo no cambia el bocadillo.
    eventos.append(ev("modelo_llamada", 43, modelo="gpt", tokens_entrada=10, tokens_salida=5, coste_eur=0.001))
    assert agente(eventos)["bocadillo"] == "Buscando artículo «PARIS»: ErrorBC: 501"


def test_esperando_aprobacion_hasta_que_se_resuelve():
    eventos = INICIO + [ev("aprobacion_solicitada", 30, checkpoint_id="cp", cliente="10000 Adatum", importe=5875.6, lineas=[], motivo="umbral")]
    a = agente(eventos)
    assert a["estado"] == "esperando_aprobacion" and a["bocadillo"] == "Esperando aprobación: 5.875,60 € · 10000 Adatum"
    eventos.append(ev("aprobacion_resuelta", 5, checkpoint_id="cp", decision="si", aprobador="Javier", comentario="OK"))
    assert agente(eventos)["estado"] == "trabajando"


def test_un_error_se_ve_como_error():
    a = agente(INICIO + [ev("error", 5, mensaje="RuntimeError: 401")])
    assert a["estado"] == "error" and a["bocadillo"] == "Error: RuntimeError: 401"


@pytest.mark.parametrize(
    ("hace_s", "resultado", "esperado"),
    [(3, "creado", "trabajando"), (3, "error", "error"), (10, "creado", "libre"), (30, "error", "libre")],
)
def test_una_tarea_terminada_se_ve_diez_segundos_y_luego_libre(hace_s, resultado, esperado):
    fin = ev("tarea_terminada", hace_s, resultado=resultado, pedido="S-ORD101001" if resultado == "creado" else None, coste_total_eur=0.0042, duracion_s=12)
    a = agente(INICIO + [fin])
    assert a["estado"] == esperado
    if esperado == "trabajando":
        assert a["bocadillo"] == "Hecho: pedido S-ORD101001 · coste 0,0042 €"
    if esperado in ("trabajando", "error") and hace_s < 10:
        assert a["resultado_reciente"] == {"resultado": resultado, "pedido": fin["datos"]["pedido"]}
    else:
        assert a["resultado_reciente"] is None
    if esperado == "libre":
        assert a["desde"] == fin["ts"]


def test_detenido_por_el_director_y_activado_otra_vez():
    eventos = INICIO + [ev("paso", 50, nombre="validar", descripcion="…"), ev("agente_detenido", 20, tarea=None, por="director")]
    assert agente(eventos)["estado"] == "detenido"
    eventos.append(ev("agente_activado", 10, tarea=None, por="director"))
    assert agente(eventos)["estado"] == "trabajando"
    # Una detención de otro día llega por «detenidos» (el backend la calcula con todo el registro).
    assert agente([], detenidos={"pedidos": "2026-10-17T09:00:00+02:00"})["estado"] == "detenido"


def test_con_varias_tareas_gana_la_que_trabaja_y_se_cuentan_las_aprobaciones():
    eventos = INICIO + [
        ev("aprobacion_solicitada", 40, checkpoint_id="cp", cliente="x", importe=1, lineas=[], motivo="m"),
        ev("tarea_iniciada", 20, tarea="t2", origen="01.txt", resumen="…"),
        ev("paso", 10, tarea="t2", nombre="interpretar", descripcion="Leyendo"),
    ]
    a = agente(eventos, pendientes_por_agente={"pedidos": 1})
    assert (a["estado"], a["tarea"], a["aprobaciones_pendientes"]) == ("trabajando", "t2", 1)


def test_una_aprobacion_sin_eventos_de_hoy_tambien_pone_al_agente_a_esperar():
    assert agente([], pendientes_por_agente={"pedidos": 1})["estado"] == "esperando_aprobacion"


def test_tablero_y_tareas_del_dia():
    eventos = INICIO + [
        ev("modelo_llamada", 55, modelo="gpt", tokens_entrada=1000, tokens_salida=100, coste_eur=0.0028),
        ev("modelo_llamada", 50, modelo="gpt", tokens_entrada=1200, tokens_salida=150, coste_eur=0.0036),
        ev("erp_escritura", 40, operacion="crear_pedido", pedido="101023", importe=3781.4, modo="api"),
        ev("tarea_terminada", 39, resultado="creado", pedido="101023", coste_total_eur=0.0064, duracion_s=21),
        ev("tarea_iniciada", 5, tarea="t2", origen="01.txt", resumen="…"),
        ev("modelo_llamada", 4, tarea="t2", modelo="gpt", tokens_entrada=500, tokens_salida=50, coste_eur=0.0014),
    ]
    aprobaciones = [{"agente": "pedidos", "checkpoint_id": "cp"}]
    foto = estado.foto(eventos, AHORA, aprobaciones, modo_erp="demo", modelo="azure_openai")
    assert foto["tablero"] == {
        "agentes_activos": 1,
        "tareas_en_curso": 1,
        "aprobaciones_pendientes": 1,
        "escrituras_erp_hoy": 1,
        "coste_hoy_eur": pytest.approx(0.0078),
        "llamadas_modelo_hoy": 3,
    }
    t1 = next(t for t in foto["tareas"] if t["id"] == "t1")
    assert (t1["estado"], t1["resultado"], t1["pedido"], t1["coste_eur"]) == ("terminada", "creado", "101023", pytest.approx(0.0064))
    assert [t["id"] for t in foto["tareas"]] == ["t2", "t1"]  # la más reciente primero
    assert foto["agentes"][0]["coste_hoy_eur"] == pytest.approx(0.0078)


def test_los_importes_se_redondean_igual_en_la_cli_el_backend_y_el_navegador():
    # 0,00375 se guarda en binario un pelo por debajo: con f"{x:.4f}" saldría 0,0037 en la CLI
    # y 0,0038 en el navegador. Todos redondean medio hacia arriba sobre el valor decimal.
    from agente_pedidos.observabilidad import ContadorCoste, redondear_eur

    assert str(redondear_eur(0.00375)) == "0.0038"
    assert estado.euros(0.00375, 4) == "0,0038 €" and estado.euros(5875.6) == "5.875,60 €"
    contador = ContadorCoste(precio_entrada_por_millon=1.0, precio_salida_por_millon=0.0, tokens_entrada=3750)
    assert contador.resumen().endswith("coste estimado 0.0038 €")


def test_las_preguntas_no_cuentan_como_tareas_ni_como_carga():
    eventos = INICIO + [
        ev("tarea_iniciada", 20, tarea="p1", origen="pregunta del director", clase="pregunta", resumen="¿En qué estado…?"),
        ev("modelo_llamada", 18, tarea="p1", modelo="gpt", tokens_entrada=900, tokens_salida=100, coste_eur=0.0023),
    ]
    foto = estado.foto(eventos, AHORA, [], modo_erp="demo", modelo="x")
    agente_ = foto["agentes"][0]
    assert (agente_["tareas_hoy"], agente_["preguntas_hoy"], agente_["tareas_en_curso"]) == (1, 1, 1)
    assert foto["tablero"]["tareas_en_curso"] == 1
    assert foto["preguntas"] == {"hoy": 1, "coste_eur": pytest.approx(0.0023)}
    assert {t["id"]: t["clase"] for t in foto["tareas"]} == {"t1": "pedido", "p1": "pregunta"}
