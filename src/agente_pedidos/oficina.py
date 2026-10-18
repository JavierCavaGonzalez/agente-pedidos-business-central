"""Arranca la oficina de agentes (interfaz web) con un solo comando.

    python -m agente_pedidos.oficina                 # usa BC_MODO y MODELO_PROVEEDOR de .env
    python -m agente_pedidos.oficina --bc demo       # fuerza el ERP simulado en esta sesión
    python -m agente_pedidos.oficina --bc demo --modelo simulado   # sin red y sin coste

Sirve el backend y el frontend en http://127.0.0.1:8765. Solo escucha en 127.0.0.1: esta
versión no tiene autenticación. Las opciones ``--bc`` y ``--modelo`` valen para el servidor y
para los subprocesos que lanza (``procesar`` y ``reanudar``), por encima de lo que diga .env.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .cli import cargar_entorno
from .modelo import PROVEEDORES

RAIZ = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agente_pedidos.oficina", description="Oficina de agentes: interfaz web del agente de pedidos")
    parser.add_argument("--puerto", type=int, default=int(os.environ.get("OFICINA_PUERTO", "8765")))
    parser.add_argument("--bc", choices=["demo", "api"], help="ERP para esta sesión (por defecto, BC_MODO de .env)")
    parser.add_argument("--modelo", choices=list(PROVEEDORES), help="proveedor del modelo para esta sesión (por defecto, MODELO_PROVEEDOR de .env)")
    args = parser.parse_args(argv)

    if not (RAIZ / "ui" / "backend" / "app.py").exists():
        print("No encuentro ui/backend: ejecuta la oficina desde una copia del repositorio (no desde un paquete instalado).")
        return 2
    os.chdir(RAIZ)  # .env, eventos.jsonl y checkpoints/ se resuelven respecto a la raíz, como en la CLI
    sys.path.insert(0, str(RAIZ))
    cargar_entorno()
    if args.bc:
        os.environ["BC_MODO"] = args.bc
    if args.modelo:
        os.environ["MODELO_PROVEEDOR"] = args.modelo

    try:
        import uvicorn
    except ImportError:
        print("Faltan las dependencias de la oficina: pip install -r requirements-ui.txt")
        return 2

    modo = os.environ.get("BC_MODO", "demo")
    url = f"http://127.0.0.1:{args.puerto}"
    print(f"Oficina de agentes en {url}")
    print(f"  ERP: {'sandbox real (api)' if modo == 'api' else 'simulado (demo)'} · modelo: {os.environ.get('MODELO_PROVEEDOR', 'simulado')}")
    if modo == "api":
        solo_lectura = os.environ.get("AGENTE_SOLO_LECTURA", "0") == "1"
        print(f"  ATENCIÓN: las tareas leen y {'NO escriben (solo lectura)' if solo_lectura else 'ESCRIBEN'} en Business Central real.")
    print("  Ctrl+C para parar.")
    uvicorn.run("ui.backend.app:app", host="127.0.0.1", port=args.puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
