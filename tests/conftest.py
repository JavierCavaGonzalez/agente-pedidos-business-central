import sys
from pathlib import Path

import pytest

# Permite ejecutar los tests sin instalar el paquete (python -m pytest).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# Y el paquete de la oficina (ui/), que vive en la raíz del repositorio.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def eventos_temporales(tmp_path, monkeypatch):
    """Cada prueba escribe sus eventos en su propio fichero, nunca en el eventos.jsonl real."""
    ruta = tmp_path / "eventos.jsonl"
    monkeypatch.setenv("AGENTE_EVENTOS", str(ruta))
    return ruta
