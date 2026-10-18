"""Backend de la oficina de agentes (FastAPI).

No ejecuta agentes dentro del servidor: lanza la misma CLI que se usa desde la terminal
(``procesar --aprobar pendiente`` y ``reanudar``) como subprocesos y lee lo que dejan en
``eventos.jsonl`` y en los checkpoints. Así la interfaz no puede saltarse el flujo definido en
código: aprobar desde la pantalla es exactamente ``reanudar --decision si``.

Arranque: ``python -m agente_pedidos.oficina`` (o ``uvicorn ui.backend.app:app`` desde la raíz).
Sin autenticación en esta versión: escucha solo en 127.0.0.1.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from watchfiles import awatch

from agente_pedidos import eventos
from agente_pedidos.workflow import aprobaciones_pendientes, crear_storage, motivo_para_no_reanudar

from . import estado

RAIZ = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    raiz: Path = RAIZ
    eventos: Path = RAIZ / "eventos.jsonl"
    checkpoints: Path = RAIZ / "checkpoints"
    bandeja: Path = RAIZ / "ui" / "bandeja"
    estaticos: Path = RAIZ / "ui" / "static"
    correos_ejemplo: Path = RAIZ / "ejemplos" / "correos"
    # ERP simulado compartido por los subprocesos (procesar y reanudar ven los mismos pedidos).
    erp_demo: Path = RAIZ / "ui" / "bandeja" / "erp_demo_pedidos.json"
    python: str = sys.executable
    entorno_extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def desde_entorno(cls) -> "Config":
        """Mismas variables que la CLI; las rutas relativas, respecto a la raíz del repositorio."""

        def ruta(variable: str, defecto: str) -> Path:
            valor = Path(os.environ.get(variable, defecto))
            return valor if valor.is_absolute() else RAIZ / valor

        return cls(
            eventos=ruta("AGENTE_EVENTOS", "eventos.jsonl"),
            checkpoints=ruta("AGENTE_CHECKPOINTS", "checkpoints"),
            bandeja=ruta("OFICINA_BANDEJA", "ui/bandeja"),
            erp_demo=ruta("BC_DEMO_PEDIDOS", "ui/bandeja/erp_demo_pedidos.json"),
        )


class NuevaTarea(BaseModel):
    agente: str = "pedidos"
    correo: str = Field(min_length=1, max_length=20_000)
    origen: str | None = None  # nombre del correo de ejemplo, si se eligió uno


class Decision(BaseModel):
    decision: str = Field(pattern="^(si|no)$")
    aprobador: str = Field(default="Director", min_length=1, max_length=80)
    comentario: str = Field(default="", max_length=500)


def crear_app(config: Config | None = None) -> FastAPI:
    config = config or Config.desde_entorno()
    config.bandeja.mkdir(parents=True, exist_ok=True)
    config.eventos.parent.mkdir(parents=True, exist_ok=True)
    config.eventos.touch(exist_ok=True)
    storage = crear_storage(config.checkpoints)
    # Aprobaciones con un «reanudar» ya lanzado: no se muestran ni se aceptan dos veces.
    en_curso: dict[str, subprocess.Popen] = {}
    agentes_validos = {a["id"] for a in estado.AGENTES}

    app = FastAPI(title="Oficina de agentes", version="0.2.0")

    def entorno_hijo(tarea: str | None = None, origen: str | None = None) -> dict[str, str]:
        entorno = {**os.environ, **config.entorno_extra}
        entorno["PYTHONPATH"] = os.pathsep.join(filter(None, [str(config.raiz / "src"), os.environ.get("PYTHONPATH")]))
        entorno["PYTHONIOENCODING"] = "utf-8"
        # Rutas absolutas: el hijo escribe exactamente donde lee el backend.
        entorno["AGENTE_EVENTOS"] = str(config.eventos)
        entorno["AGENTE_CHECKPOINTS"] = str(config.checkpoints)
        entorno["BC_DEMO_PEDIDOS"] = str(config.erp_demo)  # solo lo usa BC_MODO=demo
        entorno.pop("AGENTE_TAREA", None)
        entorno.pop("AGENTE_ORIGEN", None)
        if tarea:
            entorno["AGENTE_TAREA"] = tarea
        if origen:
            entorno["AGENTE_ORIGEN"] = origen
        return entorno

    def lanzar(argumentos: list[str], log: Path, tarea: str | None = None, origen: str | None = None) -> subprocess.Popen:
        with log.open("ab") as salida:
            return subprocess.Popen(
                [config.python, "-m", "agente_pedidos", *argumentos],
                cwd=config.raiz,
                env=entorno_hijo(tarea, origen),
                stdin=subprocess.DEVNULL,
                stdout=salida,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

    async def aprobaciones() -> list[dict[str, Any]]:
        lista = []
        for checkpoint in await aprobaciones_pendientes(storage):
            proceso = en_curso.get(checkpoint.checkpoint_id)
            if proceso is not None and proceso.poll() is None:
                continue  # ya se respondió desde la oficina y se está reanudando
            for evento in checkpoint.pending_request_info_events.values():
                datos = evento.get("data") if isinstance(evento, dict) else getattr(evento, "data", None)
                lista.append(_aprobacion(checkpoint.checkpoint_id, checkpoint.timestamp, datos))
        return lista

    async def foto() -> dict[str, Any]:
        return estado.foto(
            eventos.leer_eventos(config.eventos, dia=date.today()),
            estado.ahora_local(),
            await aprobaciones(),
            detenidos=detenidos(),
            modo_erp=os.environ.get("BC_MODO", "demo"),
            modelo=os.environ.get("MODELO_PROVEEDOR", "simulado"),
        )

    def emitir(tipo: str, agente: str, **datos: Any) -> None:
        eventos.emitir(tipo, agente=agente, tarea=None, fichero=config.eventos, **datos)

    def detenidos() -> dict[str, str]:
        """Agentes detenidos y desde cuándo (de todos los días: una detención no caduca a medianoche)."""
        todos = eventos.leer_eventos(config.eventos)
        return {a: d for a in agentes_validos if (d := estado.detenido_desde(todos, a))}

    # --- endpoints --------------------------------------------------------------------------------

    @app.get("/api/estado")
    async def get_estado() -> dict[str, Any]:
        return await foto()

    @app.get("/api/eventos")
    async def get_eventos(request: Request) -> EventSourceResponse:
        async def flujo():
            posicion = config.eventos.stat().st_size
            yield {"event": "estado", "data": json.dumps(await foto(), ensure_ascii=False)}
            # yield_on_timeout: cada pocos segundos se reenvía el estado aunque no haya eventos,
            # para que los cambios por tiempo (volver a «libre» a los 10 s) lleguen solos.
            async for _cambios in awatch(config.eventos, yield_on_timeout=True, rust_timeout=3000):
                if await request.is_disconnected():
                    break
                nuevas, posicion = _lineas_nuevas(config.eventos, posicion)
                for linea in nuevas:
                    yield {"event": "evento", "data": linea}
                yield {"event": "estado", "data": json.dumps(await foto(), ensure_ascii=False)}

        return EventSourceResponse(flujo(), ping=15)

    @app.post("/api/tareas", status_code=202)
    async def post_tarea(cuerpo: NuevaTarea) -> dict[str, str]:
        if cuerpo.agente not in agentes_validos:
            raise HTTPException(404, f"No hay ningún agente «{cuerpo.agente}» en la oficina (las otras mesas están vacantes).")
        if cuerpo.agente in detenidos():
            raise HTTPException(409, "El agente está detenido por el director: actívalo antes de asignarle tareas.")
        tarea = eventos.nueva_tarea_id()
        fichero = config.bandeja / f"{tarea}.txt"
        fichero.write_text(cuerpo.correo, encoding="utf-8")
        origen = f"{_nombre_seguro(cuerpo.origen)}.txt" if cuerpo.origen else "correo pegado en la oficina"
        lanzar(["procesar", str(fichero), "--aprobar", "pendiente", "--aprobador", "Director"], config.bandeja / f"{tarea}.log", tarea, origen)
        return {"tarea": tarea}

    @app.get("/api/aprobaciones")
    async def get_aprobaciones() -> list[dict[str, Any]]:
        return await aprobaciones()

    @app.post("/api/aprobaciones/{checkpoint_id}", status_code=202)
    async def post_aprobacion(checkpoint_id: str, cuerpo: Decision) -> dict[str, str]:
        proceso = en_curso.get(checkpoint_id)
        if proceso is not None and proceso.poll() is None:
            raise HTTPException(409, "Esta aprobación ya se está procesando.")
        try:
            motivo = await motivo_para_no_reanudar(storage, checkpoint_id)
            if motivo is None and not any(a["checkpoint_id"] == checkpoint_id for a in await aprobaciones()):
                motivo = "No hay ninguna aprobación pendiente con ese checkpoint."
        except Exception:
            raise HTTPException(404, "No existe ese checkpoint.") from None
        if motivo:
            raise HTTPException(409, motivo)
        log = config.bandeja / f"reanudar_{checkpoint_id}.log"
        en_curso[checkpoint_id] = lanzar(
            ["reanudar", "--checkpoint", checkpoint_id, "--decision", cuerpo.decision, "--aprobador", cuerpo.aprobador, "--comentario", cuerpo.comentario],
            log,
        )
        return {"checkpoint_id": checkpoint_id, "decision": cuerpo.decision}

    @app.post("/api/agentes/{agente}/detener")
    async def detener(agente: str) -> dict[str, str]:
        if agente not in agentes_validos:
            raise HTTPException(404, "Agente desconocido")
        # Queda en el registro (nada sin rastro). El MVP no mata procesos ya lanzados.
        emitir("agente_detenido", agente, por="director")
        return {"agente": agente, "estado": "detenido"}

    @app.post("/api/agentes/{agente}/activar")
    async def activar(agente: str) -> dict[str, str]:
        if agente not in agentes_validos:
            raise HTTPException(404, "Agente desconocido")
        emitir("agente_activado", agente, por="director")
        return {"agente": agente, "estado": "libre"}

    @app.get("/api/agentes/{agente}/cronologia")
    async def cronologia(agente: str) -> dict[str, Any]:
        if agente not in agentes_validos:
            raise HTTPException(404, "Agente desconocido")
        suyos = [e for e in eventos.leer_eventos(config.eventos, dia=date.today()) if e["agente"] == agente]
        herramientas: dict[str, int] = {}
        for e in suyos:
            if e["tipo"] == "herramienta":
                herramientas[e["datos"]["nombre"]] = herramientas.get(e["datos"]["nombre"], 0) + 1
        return {
            "agente": agente,
            "eventos": [{**e, "descripcion": estado.describir(e)} for e in suyos],
            "herramientas": herramientas,
            "pedidos": [e["datos"] | {"ts": e["ts"], "tarea": e["tarea"]} for e in suyos if e["tipo"] == "erp_escritura"],
            "coste_eur": round(sum(e["datos"].get("coste_eur", 0) for e in suyos if e["tipo"] == "modelo_llamada"), 6),
            "llamadas_modelo": sum(1 for e in suyos if e["tipo"] == "modelo_llamada"),
        }

    @app.get("/api/correos")
    async def correos() -> list[dict[str, str]]:
        """Correos de ejemplo para el cuadro «Asignar tarea»."""
        return [
            {"nombre": f.name, "texto": f.read_text(encoding="utf-8")}
            for f in sorted(config.correos_ejemplo.glob("*.txt"))
        ]

    app.mount("/", StaticFiles(directory=config.estaticos, html=True), name="estaticos")
    return app


def _aprobacion(checkpoint_id: str, ts: str, datos: Any) -> dict[str, Any]:
    leer = (lambda k, d=None: datos.get(k, d)) if isinstance(datos, dict) else (lambda k, d=None: getattr(datos, k, d))
    validado = leer("pedido_validado", {}) or {}
    lineas = [
        {"articulo": l.get("numero_articulo"), "descripcion": l.get("descripcion"), "cantidad": l.get("cantidad"), "importe": l.get("importe")}
        for l in validado.get("lineas", [])
    ]
    return {
        "checkpoint_id": checkpoint_id,
        "ts": ts,
        "agente": "pedidos",
        "tarea": leer("tarea"),
        "cliente": f"{leer('numero_cliente') or '?'} {leer('nombre_cliente') or ''}".strip(),
        "importe": leer("total"),
        "lineas": lineas,
        "motivo": "; ".join(leer("motivos", []) or []),
        "resumen": leer("resumen"),
        "referencia": validado.get("referencia_cliente"),
    }


def _lineas_nuevas(ruta: Path, posicion: int) -> tuple[list[str], int]:
    """Líneas completas añadidas desde ``posicion`` (una línea a medio escribir espera a la siguiente vuelta)."""
    with ruta.open("rb") as fichero:
        fichero.seek(posicion)
        bloque = fichero.read()
    completo = bloque[: bloque.rfind(b"\n") + 1]
    lineas = [l for l in completo.decode("utf-8").splitlines() if l.strip()]
    return lineas, posicion + len(completo)


def _nombre_seguro(nombre: str) -> str:
    base = Path(nombre).stem
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in base)[:60] or "correo"


def __getattr__(nombre: str) -> Any:
    """``ui.backend.app:app`` se crea al pedirlo (uvicorn), no al importar el módulo (pruebas)."""
    if nombre == "app":
        globals()["app"] = crear_app()
        return globals()["app"]
    raise AttributeError(nombre)
