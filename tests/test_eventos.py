"""Capa de eventos: formato, resúmenes sin datos sensibles y secuencias de procesar/reanudar."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

from agente_pedidos import cli, eventos
from agente_pedidos.observabilidad import redondear_eur
from agente_pedidos.cli import cmd_procesar, cmd_reanudar

CORREOS = Path(__file__).resolve().parents[1] / "ejemplos" / "correos"


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    monkeypatch.setenv("BC_MODO", "demo")
    monkeypatch.setenv("AGENTE_AUDITORIA", str(tmp_path / "auditoria.jsonl"))
    monkeypatch.setenv("AGENTE_CHECKPOINTS", str(tmp_path / "checkpoints"))
    monkeypatch.delenv("AGENTE_TAREA", raising=False)
    eventos.fijar_tarea(None)
    return tmp_path


def tipos(lista: list[dict]) -> list[str]:
    return [e["tipo"] for e in lista]


def sin_ruido(lista: list[dict]) -> list[str]:
    """La secuencia de la tarea sin las llamadas al modelo ni a herramientas (que dependen del modelo)."""
    return [e["tipo"] if e["tipo"] != "paso" else f"paso:{e['datos']['nombre']}" for e in lista if e["tipo"] not in ("modelo_llamada", "herramienta")]


# --- formato y resúmenes --------------------------------------------------------------------------


def test_un_evento_lleva_hora_con_zona_agente_tarea_tipo_y_datos(eventos_temporales):
    eventos.fijar_tarea("tarea_20261018_ab12")
    evento = eventos.emitir("paso", nombre="validar", descripcion="Comprobando")
    assert datetime.fromisoformat(evento["ts"]).tzinfo is not None
    assert evento == {**evento, "agente": "pedidos", "tarea": "tarea_20261018_ab12", "tipo": "paso", "datos": {"nombre": "validar", "descripcion": "Comprobando"}}
    assert eventos.leer_eventos(eventos_temporales) == [evento]
    eventos.fijar_tarea(None)


def test_un_tipo_desconocido_no_se_escribe():
    with pytest.raises(ValueError):
        eventos.emitir("inventado")


def test_el_id_de_tarea_lleva_la_fecha_y_cuatro_hex():
    assert re.fullmatch(r"tarea_\d{8}_[0-9a-f]{4}", eventos.nueva_tarea_id())


def test_los_resumenes_no_dejan_pasar_datos_sensibles():
    correo = "De: ana@contoso.com\nAsunto: Pedido\nEmpresa: Adatum\n\nEscribid a compras@adatum.example\nMás texto"
    assert eventos.resumir_correo(correo) == "Asunto: Pedido · Empresa: Adatum · Escribid a [correo]"
    error = RuntimeError("401 en https://api.businesscentral.dynamics.com/v2.0/0f3a…/x tenant 1b2c3d4e-0000-1111-2222-333344445555\ntraza")
    assert eventos.resumir_error(error) == "RuntimeError: 401 en <url> tenant <id>"
    assert eventos.resumir_argumentos({"texto": "Adatum", "client_secret": "s3cr3t"}) == {"texto": "Adatum", "client_secret": "***"}


# --- secuencias con el ERP simulado ---------------------------------------------------------------


async def test_procesar_sin_aprobacion_produce_la_secuencia_esperada(entorno, eventos_temporales, capsys):
    await cmd_procesar(str(CORREOS / "01_pedido_pequeno.txt"), "si", "ana")
    lista = eventos.leer_eventos(eventos_temporales)

    assert sin_ruido(lista) == [
        "tarea_iniciada",
        "paso:interpretar",
        "paso:validar",
        "paso:politica",
        "paso:crear_pedido",
        "erp_escritura",
        "paso:redactar",
        "tarea_terminada",
    ]
    assert len({e["tarea"] for e in lista}) == 1 and lista[0]["tarea"].startswith("tarea_")
    assert lista[0]["datos"] == {"origen": "01_pedido_pequeno.txt", "resumen": "Asunto: Pedido de lámparas · Empresa: Alpine Ski House · Hola,"}
    assert {"herramienta", "modelo_llamada"} <= set(tipos(lista))
    escritura = next(e for e in lista if e["tipo"] == "erp_escritura")["datos"]
    assert escritura["operacion"] == "crear_pedido" and escritura["modo"] == "demo" and escritura["importe"] == 559.0
    fin = lista[-1]["datos"]
    assert fin["resultado"] == "creado" and fin["pedido"] == escritura["pedido"]

    # El coste de la tarea (suma de sus llamadas al modelo) es el mismo que imprime la CLI.
    coste_cli = float(re.search(r"coste estimado ([\d.]+) €", capsys.readouterr().out).group(1))
    suma = sum(e["datos"]["coste_eur"] for e in lista if e["tipo"] == "modelo_llamada")
    assert fin["coste_total_eur"] == pytest.approx(suma) and float(redondear_eur(suma)) == coste_cli


async def test_procesar_pendiente_y_reanudar_siguen_en_la_misma_tarea(entorno, eventos_temporales, capsys):
    await cmd_procesar(str(CORREOS / "02_pedido_grande.txt"), "pendiente", "ana")
    hasta_la_parada = eventos.leer_eventos(eventos_temporales)
    assert sin_ruido(hasta_la_parada)[-3:] == ["paso:politica", "paso:aprobacion_humana", "aprobacion_solicitada"]
    solicitud = hasta_la_parada[-1]["datos"]
    assert solicitud["cliente"] == "10000 Adatum Corporation" and solicitud["importe"] == 5875.6
    assert solicitud["lineas"] == ["20 × 1900-S PARIS Guest Chair, black", "2 × 1896-S ATHENS Desk"]
    assert "supera el umbral" in solicitud["motivo"]
    assert "tarea_terminada" not in tipos(hasta_la_parada)
    capsys.readouterr()

    eventos.fijar_tarea(None)  # «reanudar» es otro proceso: debe recuperar la tarea del checkpoint
    await cmd_reanudar(solicitud["checkpoint_id"], "si", "OK", "Javier")
    lista = eventos.leer_eventos(eventos_temporales)
    reanudacion = lista[len(hasta_la_parada):]
    assert sin_ruido(reanudacion) == ["aprobacion_resuelta", "paso:crear_pedido", "erp_escritura", "paso:redactar", "tarea_terminada"]
    assert {e["tarea"] for e in lista} == {hasta_la_parada[0]["tarea"]}
    assert reanudacion[0]["datos"] == {"checkpoint_id": solicitud["checkpoint_id"], "decision": "si", "aprobador": "Javier", "comentario": "OK"}
    fin = lista[-1]["datos"]
    assert fin["resultado"] == "creado"
    # El coste total incluye lo gastado antes de la parada y después.
    assert fin["coste_total_eur"] == pytest.approx(sum(e["datos"]["coste_eur"] for e in lista if e["tipo"] == "modelo_llamada"))
    assert any(e["tipo"] == "modelo_llamada" for e in hasta_la_parada) and any(e["tipo"] == "modelo_llamada" for e in reanudacion)


async def test_denegar_termina_la_tarea_como_denegada_sin_escribir(entorno, eventos_temporales):
    await cmd_procesar(str(CORREOS / "02_pedido_grande.txt"), "pendiente", "ana")
    checkpoint = next(e for e in eventos.leer_eventos(eventos_temporales) if e["tipo"] == "aprobacion_solicitada")["datos"]["checkpoint_id"]
    await cmd_reanudar(checkpoint, "no", "Facturas pendientes", "Javier")
    lista = eventos.leer_eventos(eventos_temporales)
    assert "erp_escritura" not in tipos(lista)
    assert lista[-1]["tipo"] == "tarea_terminada" and lista[-1]["datos"]["resultado"] == "denegado"


async def test_un_rechazo_por_validacion_bloquea_la_escritura(entorno, eventos_temporales):
    await cmd_procesar(str(CORREOS / "03_cliente_bloqueado.txt"), "si", "ana")
    lista = eventos.leer_eventos(eventos_temporales)
    bloqueo = next(e for e in lista if e["tipo"] == "erp_bloqueada")["datos"]
    assert "bloqueado" in bloqueo["motivo"]
    assert lista[-1]["datos"]["resultado"] == "rechazado" and lista[-1]["datos"]["pedido"] is None


async def test_un_error_queda_como_evento_sin_secretos_y_cierra_la_tarea(entorno, eventos_temporales, monkeypatch):
    def falla(*_args, **_kwargs):
        raise RuntimeError("401 Unauthorized en https://login.microsoftonline.com/mi-tenant/oauth2")

    monkeypatch.setattr(cli, "crear_cliente_bc", falla)
    with pytest.raises(RuntimeError):
        await cmd_procesar(str(CORREOS / "01_pedido_pequeno.txt"), "si", "ana")
    lista = eventos.leer_eventos(eventos_temporales)
    assert tipos(lista) == ["tarea_iniciada", "error", "tarea_terminada"]
    assert lista[1]["datos"]["mensaje"] == "RuntimeError: 401 Unauthorized en <url>"
    assert lista[2]["datos"]["resultado"] == "error"


async def test_la_oficina_puede_fijar_el_id_de_la_tarea(entorno, eventos_temporales, monkeypatch):
    monkeypatch.setenv("AGENTE_TAREA", "tarea_20261018_beef")
    await cmd_procesar(str(CORREOS / "01_pedido_pequeno.txt"), "si", "ana")
    assert {e["tarea"] for e in eventos.leer_eventos(eventos_temporales)} == {"tarea_20261018_beef"}
