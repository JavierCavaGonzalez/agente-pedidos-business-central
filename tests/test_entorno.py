"""Lectura de .env: los comentarios al final de línea no deben colarse en los valores."""

from __future__ import annotations

import os

import pytest

from agente_pedidos.cli import cargar_entorno
from agente_pedidos.middleware import PresupuestoLlamadas, SoloLectura

CLAVES = ["AGENTE_SOLO_LECTURA", "AGENTE_MAX_LLAMADAS_MODELO", "AGENTE_AUDITORIA", "CON_ALMOHADILLA", "VACIA", "SIN_ESPACIO"]


@pytest.fixture
def entorno_limpio(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for clave in CLAVES:
        monkeypatch.delenv(clave, raising=False)  # monkeypatch las borra también al terminar
    return tmp_path


def test_un_comentario_al_final_de_linea_no_desactiva_el_solo_lectura(entorno_limpio):
    (entorno_limpio / ".env").write_text(
        "AGENTE_SOLO_LECTURA=1   # 1 = bloquea toda herramienta de escritura\n"
        "AGENTE_MAX_LLAMADAS_MODELO=12    # tope de llamadas al modelo por ejecución\n",
        encoding="utf-8",
    )
    cargar_entorno()

    assert SoloLectura().activo is True
    assert PresupuestoLlamadas().maximo == 12


def test_entre_comillas_se_conserva_la_almohadilla(entorno_limpio):
    (entorno_limpio / ".env").write_text(
        'CON_ALMOHADILLA="clave # con almohadilla"  # comentario\n'
        "VACIA=   # sin valor\n"
        "SIN_ESPACIO=abc#def\n",
        encoding="utf-8",
    )
    cargar_entorno()

    assert os.environ["CON_ALMOHADILLA"] == "clave # con almohadilla"
    assert os.environ["VACIA"] == ""
    assert os.environ["SIN_ESPACIO"] == "abc#def"
