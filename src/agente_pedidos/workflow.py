"""El workflow: el grafo que decide quién hace qué.

Es un ``WorkflowBuilder`` de Agent Framework (cap. 6 del libro: pasos tipados, aristas
condicionales, ejecución determinista, checkpoints). Reparto de papeles:

- Decide el agente (IA): qué cliente y qué artículos nombra el correo (nodo ``interpretar``) y
  cómo redactar la respuesta (nodo ``redactar``).
- Decide el código: si el pedido es válido, su importe, si hace falta aprobación y qué ruta
  sigue (nodo ``validar`` + aristas condicionales). La escritura en el ERP la hace código, no el
  modelo (nodo ``crear_pedido``).
- Decide la persona: si se crea o no un pedido que exige aprobación (nodo ``aprobacion_humana``,
  que detiene el workflow con ``request_info`` y lo reanuda con la decisión, incluso en otro
  proceso gracias al checkpoint).

Grafo::

    interpretar -> validar -+-> rechazar ----------------+-> redactar -> salida
                            +-> aprobacion_humana -+-> crear_pedido -+
                            |                      +-> rechazar      |
                            +-> crear_pedido ------------------------+
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_framework import (
    Agent,
    Case,
    Default,
    Executor,
    FileCheckpointStorage,
    Workflow,
    WorkflowBuilder,
    WorkflowCheckpoint,
    WorkflowContext,
    WorkflowViz,
    handler,
    register_checkpoint_type,
    response_handler,
)
from typing_extensions import Never

from . import eventos
from .agentes import crear_agente_interprete, crear_agente_redactor
from .bc.base import ClienteBC, ErrorBC, PedidoDuplicado
from .esquemas import DecisionHumana, LineaInterpretada, LineaValidada, PedidoInterpretado, PedidoValidado, ResultadoPedido
from .observabilidad import ContadorCoste
from .politicas import Politica, validar_pedido

NOMBRE_WORKFLOW = "pedidos_por_correo"


# --- mensajes propios que viajan por el grafo ---------------------------------------------


@dataclass
class SolicitudAprobacion:
    """Lo que ve la persona que aprueba: calculado por código, no redactado por el modelo."""

    resumen: str
    total: float
    numero_cliente: str | None
    nombre_cliente: str | None
    motivos: list[str] = field(default_factory=list)
    pedido_validado: dict[str, Any] = field(default_factory=dict)  # PedidoValidado serializado
    tarea: str | None = None  # para que «reanudar», en otro proceso, siga contando en la misma tarea
    modo_erp: str | None = None  # demo | api: una aprobación de la simulación no se resuelve contra el ERP real


@dataclass
class DecisionTomada:
    pedido_validado: dict[str, Any]
    aprobado: bool
    comentario: str = ""
    aprobador: str = ""


# Los checkpoints se guardan en JSON y los objetos propios van serializados; el framework
# solo los restaura si su tipo está registrado (deserialización restringida, desde la 1.0.1).
for _tipo in (
    PedidoInterpretado,
    LineaInterpretada,
    PedidoValidado,
    LineaValidada,
    DecisionHumana,
    ResultadoPedido,
    SolicitudAprobacion,
    DecisionTomada,
):
    register_checkpoint_type(_tipo)


# --- nodos (executors) -----------------------------------------------------------------------


class Interpretar(Executor):
    """Nodo con IA: el agente intérprete convierte el correo en un PedidoInterpretado."""

    def __init__(self, agente: Agent, contador: ContadorCoste) -> None:
        super().__init__(id="interpretar")
        self.agente = agente
        self.contador = contador

    @handler
    async def interpretar(self, correo: str, ctx: WorkflowContext[PedidoInterpretado]) -> None:
        eventos.emitir("paso", nombre="interpretar", descripcion="Leyendo el correo e identificando cliente y artículos")
        respuesta = await self.agente.run(correo, options={"response_format": PedidoInterpretado})
        self.contador.registrar(respuesta)
        pedido = respuesta.value
        if pedido is None:  # el modelo no devolvió el formato pedido: nunca se adivina, se marca la duda
            pedido = _pedido_desde_texto(respuesta.text or "")
        ctx.set_state("correo", correo)
        await ctx.send_message(pedido)


class Validar(Executor):
    """Nodo de código: reglas deterministas contra el ERP y la política."""

    def __init__(self, bc: ClienteBC, politica: Politica) -> None:
        super().__init__(id="validar")
        self.bc = bc
        self.politica = politica

    @handler
    async def validar(self, pedido: PedidoInterpretado, ctx: WorkflowContext[PedidoValidado]) -> None:
        eventos.emitir("paso", nombre="validar", descripcion="Comprobando cliente, artículos, existencias, crédito e importe")
        validado = await validar_pedido(pedido, self.bc, self.politica)
        eventos.emitir(
            "paso",
            nombre="politica",
            descripcion=_decision_de_politica(validado),
            # Para el seguimiento de la oficina (también en el camino sin aprobación): cliente, total y líneas.
            cliente=f"{validado.numero_cliente or '?'} {validado.nombre_cliente or ''}".strip(),
            total=validado.total,
            lineas=[{"articulo": l.numero_articulo, "descripcion": l.descripcion, "cantidad": l.cantidad, "importe": l.importe} for l in validado.lineas],
        )
        await ctx.send_message(validado)


class AprobacionHumana(Executor):
    """Nodo humano: detiene el workflow y espera una DecisionHumana."""

    def __init__(self) -> None:
        super().__init__(id="aprobacion_humana")

    @handler
    async def pedir(self, validado: PedidoValidado, ctx: WorkflowContext) -> None:
        solicitud = SolicitudAprobacion(
            resumen=validado.resumen_para_humano(),
            total=validado.total,
            numero_cliente=validado.numero_cliente,
            nombre_cliente=validado.nombre_cliente,
            motivos=list(validado.motivos_aprobacion),
            pedido_validado=validado.model_dump(),
            tarea=eventos.tarea_actual(),
            modo_erp=os.environ.get("BC_MODO", "demo"),
        )
        eventos.emitir("paso", nombre="aprobacion_humana", descripcion="Esperando la decisión del director")
        await ctx.request_info(solicitud, DecisionHumana)

    @response_handler
    async def recibir(self, solicitud: SolicitudAprobacion, decision: DecisionHumana, ctx: WorkflowContext[DecisionTomada]) -> None:
        await ctx.send_message(
            DecisionTomada(
                pedido_validado=solicitud.pedido_validado,
                aprobado=decision.aprobado,
                comentario=decision.comentario,
                aprobador=decision.aprobador,
            )
        )


class CrearPedido(Executor):
    """Nodo de código: la única escritura en el ERP, con la identidad y permisos de la aplicación."""

    def __init__(self, bc: ClienteBC) -> None:
        super().__init__(id="crear_pedido")
        self.bc = bc

    @handler
    async def crear_sin_aprobacion(self, validado: PedidoValidado, ctx: WorkflowContext[ResultadoPedido]) -> None:
        await ctx.send_message(await self._crear(validado, comentario="Creado automáticamente (dentro de la política)"))

    @handler
    async def crear_aprobado(self, decision: DecisionTomada, ctx: WorkflowContext[ResultadoPedido]) -> None:
        validado = PedidoValidado.model_validate(decision.pedido_validado)
        comentario = f"Aprobado por {decision.aprobador or 'una persona'}" + (f": {decision.comentario}" if decision.comentario else "")
        await ctx.send_message(await self._crear(validado, comentario=comentario))

    async def _crear(self, validado: PedidoValidado, comentario: str) -> ResultadoPedido:
        eventos.emitir("paso", nombre="crear_pedido", descripcion=f"Creando el pedido en Business Central ({euros(validado.total)})")
        lineas = [{"numero_articulo": l.numero_articulo, "cantidad": l.cantidad} for l in validado.lineas]
        try:
            pedido = await self.bc.crear_pedido_venta(
                validado.numero_cliente or "",
                lineas,
                referencia_externa=validado.referencia_cliente or "",
                fecha_entrega=validado.fecha_entrega,
            )
        except PedidoDuplicado as duplicado:
            # Idempotencia: el mismo correo procesado dos veces no crea dos pedidos.
            return ResultadoPedido(
                creado=False,
                estado="rechazado",
                numero_pedido=duplicado.pedido.get("number"),
                total=float(duplicado.pedido.get("totalAmountExcludingTax") or validado.total),
                numero_cliente=validado.numero_cliente,
                nombre_cliente=validado.nombre_cliente,
                mensaje=f"No se ha creado un pedido nuevo: {duplicado}",
            )
        except ErrorBC as error:
            return ResultadoPedido(
                creado=False,
                estado="rechazado",
                total=validado.total,
                numero_cliente=validado.numero_cliente,
                nombre_cliente=validado.nombre_cliente,
                mensaje=f"Business Central rechazó el pedido: {error}",
            )
        return ResultadoPedido(
            creado=True,
            estado="creado",
            numero_pedido=pedido["number"],
            total=float(pedido.get("totalAmountExcludingTax", validado.total)),
            numero_cliente=pedido.get("customerNumber", validado.numero_cliente),
            nombre_cliente=pedido.get("customerName", validado.nombre_cliente),
            mensaje=f"Pedido {pedido['number']} creado. {comentario}. Líneas: " + "; ".join(f"{l.cantidad:g} x {l.numero_articulo} {l.descripcion}" for l in validado.lineas),
        )


class Rechazar(Executor):
    """Nodo de código: no se crea nada; se explica por qué."""

    def __init__(self) -> None:
        super().__init__(id="rechazar")

    @handler
    async def por_validacion(self, validado: PedidoValidado, ctx: WorkflowContext[ResultadoPedido]) -> None:
        motivos = validado.errores or ["El pedido no cumple la política"]
        eventos.emitir("paso", nombre="rechazar", descripcion="No se crea: " + "; ".join(motivos))
        eventos.emitir("erp_bloqueada", operacion="crear_pedido", motivo="Validación: " + "; ".join(motivos))
        await ctx.send_message(
            ResultadoPedido(
                creado=False,
                estado="rechazado",
                total=validado.total,
                numero_cliente=validado.numero_cliente,
                nombre_cliente=validado.nombre_cliente,
                mensaje="Pedido rechazado por validación: " + "; ".join(motivos),
            )
        )

    @handler
    async def por_persona(self, decision: DecisionTomada, ctx: WorkflowContext[ResultadoPedido]) -> None:
        validado = PedidoValidado.model_validate(decision.pedido_validado)
        eventos.emitir("paso", nombre="rechazar", descripcion=f"Denegado por {decision.aprobador or 'el director'}")
        await ctx.send_message(
            ResultadoPedido(
                creado=False,
                estado="denegado",
                total=validado.total,
                numero_cliente=validado.numero_cliente,
                nombre_cliente=validado.nombre_cliente,
                mensaje=f"Pedido rechazado por {decision.aprobador or 'una persona'}" + (f": {decision.comentario}" if decision.comentario else ""),
            )
        )


class Redactar(Executor):
    """Nodo con IA: el redactor escribe la respuesta al cliente y el workflow emite la salida."""

    def __init__(self, agente: Agent, contador: ContadorCoste) -> None:
        super().__init__(id="redactar")
        self.agente = agente
        self.contador = contador

    @handler
    async def redactar(self, resultado: ResultadoPedido, ctx: WorkflowContext[Never, ResultadoPedido]) -> None:
        eventos.emitir("paso", nombre="redactar", descripcion="Redactando la respuesta al cliente")
        resumen = (
            f"Resultado: {'pedido creado' if resultado.creado else 'no se ha creado el pedido'}\n"
            f"Número de pedido: {resultado.numero_pedido or '-'}\n"
            f"Cliente: {resultado.numero_cliente or '-'} {resultado.nombre_cliente or ''}\n"
            f"Total sin impuestos: {resultado.total:.2f}\n"
            f"Detalle: {resultado.mensaje}"
        )
        respuesta = await self.agente.run(resumen)
        self.contador.registrar(respuesta)
        resultado.respuesta_cliente = respuesta.text or ""
        await ctx.yield_output(resultado)


def euros(importe: float) -> str:
    """5875.6 -> «5.875,60 €»."""
    return f"{importe:,.2f} €".replace(",", "_").replace(".", ",").replace("_", ".")


def _decision_de_politica(validado: PedidoValidado) -> str:
    if not validado.apto_para_crear:
        return "No se puede crear: " + "; ".join(validado.errores or ["no cumple la política"])
    if validado.requiere_aprobacion:
        return f"Necesita aprobación ({euros(validado.total)}): " + "; ".join(validado.motivos_aprobacion)
    return f"Dentro de la política: se crea sin aprobación ({euros(validado.total)})"


# --- construcción ----------------------------------------------------------------------------


@dataclass
class PiezasWorkflow:
    workflow: Workflow
    contador: ContadorCoste
    storage: FileCheckpointStorage | None


def construir_workflow(
    bc: ClienteBC,
    politica: Politica | None = None,
    storage: FileCheckpointStorage | None = None,
    middleware: list[Any] | None = None,
    cliente_modelo_interprete: Any | None = None,
    cliente_modelo_redactor: Any | None = None,
) -> PiezasWorkflow:
    """Monta el grafo. Devuelve el workflow, el contador de coste y el almacén de checkpoints."""
    politica = politica or Politica()
    contador = ContadorCoste()
    middleware = middleware or []

    interpretar = Interpretar(crear_agente_interprete(bc, middleware, cliente_modelo_interprete), contador)
    validar = Validar(bc, politica)
    aprobacion = AprobacionHumana()
    crear = CrearPedido(bc)
    rechazar = Rechazar()
    redactar = Redactar(crear_agente_redactor(middleware, cliente_modelo_redactor), contador)

    constructor = WorkflowBuilder(
        name=NOMBRE_WORKFLOW,
        description="Pedidos de venta por correo con validación por código y aprobación humana",
        start_executor=interpretar,
        checkpoint_storage=storage,
    )
    constructor.add_edge(interpretar, validar)
    constructor.add_switch_case_edge_group(
        validar,
        [
            Case(condition=lambda v: not v.apto_para_crear, target=rechazar),
            Case(condition=lambda v: v.requiere_aprobacion, target=aprobacion),
            Default(target=crear),
        ],
    )
    constructor.add_edge(aprobacion, crear, condition=lambda d: d.aprobado)
    constructor.add_edge(aprobacion, rechazar, condition=lambda d: not d.aprobado)
    constructor.add_edge(crear, redactar)
    constructor.add_edge(rechazar, redactar)
    return PiezasWorkflow(workflow=constructor.build(), contador=contador, storage=storage)


def crear_storage(ruta: str | Path | None = None) -> FileCheckpointStorage:
    """Checkpoints en disco: permiten reanudar una aprobación horas después y en otro proceso."""
    carpeta = Path(ruta or "checkpoints")
    carpeta.mkdir(parents=True, exist_ok=True)
    return FileCheckpointStorage(storage_path=carpeta)


# --- ciclo de vida de las aprobaciones guardadas -----------------------------------------------
#
# Un checkpoint de pausa (con una petición de aprobación abierta) deja de estar pendiente cuando
# la aprobación se resuelve, en el mismo proceso o con ``reanudar``. Se reconoce de dos formas:
# 1. está anotado en ``aprobaciones_resueltas.jsonl`` (lo escribe ``marcar_resuelto``: quién,
#    cuándo y qué decidió); la extensión .jsonl evita que el almacén lo lea como checkpoint;
# 2. la ejecución ya continuó: hay un checkpoint posterior cuyo ``previous_checkpoint_id`` es
#    el suyo (cubre también los checkpoints anteriores a este registro).

REGISTRO_RESUELTAS = "aprobaciones_resueltas.jsonl"


def _ruta_registro(storage: FileCheckpointStorage) -> Path:
    return Path(storage.storage_path) / REGISTRO_RESUELTAS


def leer_resueltas(storage: FileCheckpointStorage) -> dict[str, dict[str, Any]]:
    try:
        lineas = _ruta_registro(storage).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    registros = (json.loads(linea) for linea in lineas if linea.strip())
    return {r["checkpoint_id"]: r for r in registros}


def marcar_resuelto(storage: FileCheckpointStorage, checkpoint_id: str, decision: DecisionHumana) -> None:
    """Anota que la aprobación de ``checkpoint_id`` ya se resolvió (no vuelve a salir en ``pendientes``)."""
    registro = {
        "checkpoint_id": checkpoint_id,
        "resuelta": datetime.now(timezone.utc).isoformat(),
        "aprobado": decision.aprobado,
        "aprobador": decision.aprobador,
        "comentario": decision.comentario,
    }
    with _ruta_registro(storage).open("a", encoding="utf-8") as fichero:
        fichero.write(json.dumps(registro, ensure_ascii=False) + "\n")


async def aprobaciones_pendientes(storage: FileCheckpointStorage) -> list[WorkflowCheckpoint]:
    """Checkpoints con una aprobación abierta que nadie ha resuelto todavía."""
    checkpoints = await storage.list_checkpoints(workflow_name=NOMBRE_WORKFLOW)
    resueltas = leer_resueltas(storage)
    continuados = {c.previous_checkpoint_id for c in checkpoints if c.previous_checkpoint_id}
    pendientes = [
        c for c in checkpoints
        if c.pending_request_info_events and c.checkpoint_id not in resueltas and c.checkpoint_id not in continuados
    ]
    return sorted(pendientes, key=lambda c: c.timestamp)


def modo_de_la_solicitud(evento: Any) -> str | None:
    datos = evento.get("data") if isinstance(evento, dict) else getattr(evento, "data", None)
    return datos.get("modo_erp") if isinstance(datos, dict) else getattr(datos, "modo_erp", None)


def motivo_por_modo(modo_solicitud: str | None, modo_actual: str) -> str | None:
    """Una aprobación pedida con un ERP no se resuelve con otro: con el simulado se podría crear un
    pedido real a partir de datos que solo existían en la simulación."""
    if modo_solicitud and modo_solicitud != modo_actual:
        return (
            f"La aprobación se pidió con BC_MODO={modo_solicitud} y ahora está BC_MODO={modo_actual}: "
            f"resuélvela con BC_MODO={modo_solicitud}."
        )
    return None


async def motivo_para_no_reanudar(storage: FileCheckpointStorage, checkpoint_id: str) -> str | None:
    """Por qué no se puede reanudar ``checkpoint_id`` (ya resuelto), o ``None`` si se puede."""
    resuelta = leer_resueltas(storage).get(checkpoint_id)
    if resuelta:
        decision = "aprobada" if resuelta["aprobado"] else "rechazada"
        quien = resuelta.get("aprobador") or "una persona"
        return f"La aprobación de este checkpoint ya se resolvió el {resuelta['resuelta']}: {decision} por {quien}."
    checkpoints = await storage.list_checkpoints(workflow_name=NOMBRE_WORKFLOW)
    if any(c.previous_checkpoint_id == checkpoint_id for c in checkpoints):
        return "La ejecución de este checkpoint ya continuó (hay checkpoints posteriores): su aprobación ya se resolvió."
    return None


def dibujar_mermaid(workflow: Workflow) -> str:
    return WorkflowViz(workflow).to_mermaid()


def _pedido_desde_texto(texto: str) -> PedidoInterpretado:
    try:
        return PedidoInterpretado.model_validate(json.loads(texto))
    except Exception:  # noqa: BLE001 - cualquier fallo de formato se convierte en una duda explícita
        return PedidoInterpretado(
            cliente_texto="",
            dudas=["El intérprete no devolvió un pedido con el formato esperado; revisar a mano."],
            resumen="Petición no interpretada",
        )
