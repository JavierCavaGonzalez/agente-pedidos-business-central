"""Aprobación por consola: sin terminal o sin respuesta, la escritura se deniega y queda en la auditoría."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from agente_pedidos.cli import cmd_chat, cmd_procesar

CORREO_GRANDE = Path(__file__).resolve().parents[1] / "ejemplos" / "correos" / "02_pedido_grande.txt"


class ConsolaMuda(io.StringIO):
    """Stdin que dice ser una terminal pero no devuelve nada (como NUL en Windows)."""

    def isatty(self) -> bool:
        return True


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_PROVEEDOR", "simulado")
    monkeypatch.setenv("BC_MODO", "demo")
    monkeypatch.setenv("AGENTE_AUDITORIA", str(tmp_path / "auditoria.jsonl"))
    monkeypatch.setenv("AGENTE_CHECKPOINTS", str(tmp_path / "checkpoints"))
    monkeypatch.delenv("CHAT_APROBAR", raising=False)
    return tmp_path


def leer_auditoria(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


async def test_procesar_sin_terminal_deniega_aunque_llegue_un_si_por_tuberia(entorno, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("s\n"))  # una tubería no es una persona delante

    assert await cmd_procesar(str(CORREO_GRANDE), "preguntar", "ana") == 0

    salida = capsys.readouterr().out
    assert "Aprobación denegada: no hay terminal para preguntar" in salida
    assert "Pedido creado: no" in salida
    denegaciones = [e for e in leer_auditoria(entorno / "auditoria.jsonl") if e.get("evento") == "aprobacion_denegada"]
    assert len(denegaciones) == 1 and "02_pedido_grande.txt" in denegaciones[0]["solicitud"]


async def test_chat_con_eof_en_la_consola_deniega_y_no_crea_el_pedido(entorno, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", ConsolaMuda())

    def sin_respuesta(_pregunta: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", sin_respuesta)

    assert await cmd_chat("Empresa: Adatum Corporation. Necesito 5 lámparas AMSTERDAM", "ana") == 0

    salida = capsys.readouterr().out
    assert "Aprobación denegada: la consola no devolvió respuesta (EOF)" in salida
    assert "S-ORD" not in salida
    eventos = leer_auditoria(entorno / "auditoria.jsonl")
    assert [e["solicitud"] for e in eventos if e.get("evento") == "aprobacion_denegada"] == ["crear_pedido_venta (chat)"]
    # La herramienta de escritura no llega a ejecutarse: solo constan las lecturas.
    assert [e["herramienta"] for e in eventos if "herramienta" in e] == ["buscar_clientes", "buscar_articulos"]
