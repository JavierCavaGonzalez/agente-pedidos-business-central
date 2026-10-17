import sys
from pathlib import Path

# Permite ejecutar los tests sin instalar el paquete (python -m pytest).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
