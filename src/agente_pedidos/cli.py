"""Línea de comandos del ejemplo.

    python -m agente_pedidos demo                         # los cuatro correos de ejemplo, aprobación automática
    python -m agente_pedidos procesar ejemplos/correos/02_pedido_grande.txt
    python -m agente_pedidos procesar correo.txt --aprobar pendiente   # deja la aprobación en un checkpoint
    python -m agente_pedidos pendientes                   # qué aprobaciones hay pendientes
    python -m agente_pedidos reanudar --checkpoint ID --decision si --aprobador "Ana"
    python -m agente_pedidos chat "Crea un pedido para Adatum de 5 lámparas AMSTERDAM"
    python -m agente_pedidos grafo                        # el workflow en Mermaid

Todo funciona sin credenciales (MODELO_PROVEEDOR=simulado y BC_MODO=demo, los valores por defecto).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_framework import Message

from . import eventos
from .agentes import crear_agente_asistente
from .bc import ClienteApiV2, ClienteBC, ClienteDemo
from .esquemas import DecisionHumana, ResultadoPedido
from .middleware import AuditoriaHerramientas, EventosModelo, PresupuestoLlamadas, SoloLectura
from .observabilidad import ContadorCoste, configurar_observabilidad
from .politicas import Politica
from .workflow import (
    aprobaciones_pendientes,
    construir_workflow,
    crear_storage,
    dibujar_mermaid,
    marcar_resuelto,
    motivo_para_no_reanudar,
)

CORREOS_DEMO = ["01_pedido_pequeno.txt", "02_pedido_grande.txt", "03_cliente_bloqueado.txt", "04_con_dudas.txt"]


# --- infraestructura común ----------------------------------------------------------------


def crear_cliente_bc(auditoria: AuditoriaHerramientas | None = None) -> ClienteBC:
    """``BC_MODO=demo`` (por defecto) usa datos simulados; ``BC_MODO=api`` usa la API v2.0 de un sandbox.

    Con ``auditoria``, cada escritura en el ERP queda registrada, la pida el modelo o el workflow.
    """
    modo = os.environ.get("BC_MODO", "demo").strip().lower()
    if modo == "demo":
        bc: ClienteBC = ClienteDemo()
    elif modo == "api":
        bc = ClienteApiV2.desde_entorno()
    else:
        raise SystemExit(f"BC_MODO='{modo}' no es válido (demo | api)")
    bc.auditoria = auditoria
    return bc


def crear_middleware() -> list[Any]:
    return [AuditoriaHerramientas(), SoloLectura(), PresupuestoLlamadas(), EventosModelo()]


# --- eventos de la tarea (registro operativo de la oficina) -------------------------------------


def _emitir_aprobacion_solicitada(checkpoint_id: str, solicitud: Any) -> None:
    lineas = [
        f"{linea['cantidad']:g} × {linea['numero_articulo']} {linea['descripcion']}"
        for linea in solicitud.pedido_validado.get("lineas", [])
    ]
    eventos.emitir(
        "aprobacion_solicitada",
        checkpoint_id=checkpoint_id,
        cliente=f"{solicitud.numero_cliente or '?'} {solicitud.nombre_cliente or ''}".strip(),
        importe=solicitud.total,
        lineas=lineas,
        motivo="; ".join(solicitud.motivos),
    )


def _emitir_aprobacion_resuelta(checkpoint_id: str, decision: DecisionHumana) -> None:
    eventos.emitir(
        "aprobacion_resuelta",
        checkpoint_id=checkpoint_id,
        decision="si" if decision.aprobado else "no",
        aprobador=decision.aprobador,
        comentario=decision.comentario,
    )


def _tarea_de_la_solicitud(evento: Any) -> str | None:
    datos = evento.get("data") if isinstance(evento, dict) else getattr(evento, "data", None)
    return datos.get("tarea") if isinstance(datos, dict) else getattr(datos, "tarea", None)


def _totales_de_la_tarea() -> tuple[float, float | None]:
    """Coste (suma de sus llamadas al modelo) y duración de la tarea, sacados de sus eventos.

    Así una tarea parada y reanudada en otro proceso cuenta su coste y su tiempo completos.
    """
    tarea = eventos.tarea_actual()
    suyos = [e for e in eventos.leer_eventos() if e["tarea"] == tarea]
    coste = round(sum(e["datos"].get("coste_eur", 0) for e in suyos if e["tipo"] == "modelo_llamada"), 6)
    inicio = next((e["ts"] for e in suyos if e["tipo"] == "tarea_iniciada"), None)
    duracion = round((datetime.now().astimezone() - datetime.fromisoformat(inicio)).total_seconds(), 1) if inicio else None
    return coste, duracion


def _terminar_tarea(salidas: list[ResultadoPedido]) -> None:
    ultima = salidas[-1] if salidas else None
    coste, duracion = _totales_de_la_tarea()
    eventos.emitir(
        "tarea_terminada",
        resultado=(ultima.estado or ("creado" if ultima.creado else "rechazado")) if ultima else "error",
        pedido=ultima.numero_pedido if ultima and ultima.creado else None,
        coste_total_eur=coste,
        duracion_s=duracion,
    )


def _terminar_con_error(error: BaseException) -> None:
    eventos.emitir("error", mensaje=eventos.resumir_error(error))
    coste, duracion = _totales_de_la_tarea()
    eventos.emitir("tarea_terminada", resultado="error", pedido=None, coste_total_eur=coste, duracion_s=duracion)


def cargar_entorno() -> None:
    """Carga .env si existe (sin dependencias: unas líneas CLAVE=valor)."""
    ruta = Path(".env")
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), _valor_env(valor))


def _valor_env(bruto: str) -> str:
    """Como python-dotenv: entre comillas se respeta todo (también '#'); sin comillas, ' #...' es un comentario."""
    valor = bruto.lstrip()
    if valor[:1] in ('"', "'"):
        cierre = valor.find(valor[0], 1)
        if cierre != -1:
            return valor[1:cierre]
    # Sobre el valor sin recortar, para que "CLAVE= # comentario" quede vacío y "CLAVE=a#b" conserve el '#'.
    return re.split(r"\s+#", bruto, maxsplit=1)[0].strip()


RESPUESTAS_SI = ("s", "si", "sí", "y", "yes")


def preguntar_aprobacion(pregunta: str, auditoria: AuditoriaHerramientas, que: str) -> bool:
    """Pide la aprobación por consola. Sin terminal o sin respuesta (EOF) se deniega y se audita.

    Una escritura en el ERP nunca se aprueba por defecto: si nadie puede contestar, la respuesta es no.
    """
    motivo = None
    if not sys.stdin.isatty():
        motivo = "no hay terminal para preguntar"
    else:
        try:
            # En Windows, NUL dice ser una terminal: ahí input() lanza EOFError.
            respuesta = input(pregunta)
        except EOFError:
            motivo = "la consola no devolvió respuesta (EOF)"
    if motivo:
        print(f"\nAprobación denegada: {motivo}.")
        auditoria.registrar({"evento": "aprobacion_denegada", "motivo": motivo, "solicitud": que})
        return False
    return respuesta.strip().lower() in RESPUESTAS_SI


def imprimir_resultado(resultado: ResultadoPedido) -> None:
    print("\n--- Resultado ---")
    print("Pedido creado:", "sí" if resultado.creado else "no")
    if resultado.numero_pedido:
        print("Número de pedido:", resultado.numero_pedido)
    print("Cliente:", resultado.numero_cliente or "-", resultado.nombre_cliente or "")
    print(f"Total sin impuestos: {resultado.total:.2f}")
    print("Detalle:", resultado.mensaje)
    print("\n--- Respuesta propuesta al cliente ---")
    print(resultado.respuesta_cliente)


# --- comandos ------------------------------------------------------------------------------


async def cmd_procesar(ruta_correo: str, modo_aprobacion: str, aprobador: str) -> int:
    correo = Path(ruta_correo).read_text(encoding="utf-8")
    # La oficina pasa el id de la tarea que ya ha creado; desde la terminal se genera uno.
    eventos.fijar_tarea(os.environ.get("AGENTE_TAREA") or eventos.nueva_tarea_id())
    eventos.emitir("tarea_iniciada", origen=Path(ruta_correo).name, resumen=eventos.resumir_correo(correo))
    try:
        return await _procesar(correo, ruta_correo, modo_aprobacion, aprobador)
    except Exception as error:
        _terminar_con_error(error)
        raise


async def _procesar(correo: str, ruta_correo: str, modo_aprobacion: str, aprobador: str) -> int:
    middleware = crear_middleware()
    bc = crear_cliente_bc(auditoria=middleware[0])
    storage = crear_storage(os.environ.get("AGENTE_CHECKPOINTS", "checkpoints"))
    piezas = construir_workflow(bc, Politica.desde_entorno(), storage, middleware)

    print(f"Procesando {ruta_correo} (modelo={os.environ.get('MODELO_PROVEEDOR', 'simulado')}, BC={os.environ.get('BC_MODO', 'demo')})")
    pendiente = None
    salidas: list[ResultadoPedido] = []
    async for evento in piezas.workflow.run(correo, stream=True):
        if evento.type == "executor_invoked":
            print(f"  paso: {evento.executor_id}")
        elif evento.type == "request_info":
            pendiente = evento
        elif evento.type == "output":
            salidas.append(evento.data)

    if pendiente is not None:
        solicitud = pendiente.data
        print("\n=== APROBACIÓN NECESARIA ===")
        print(solicitud.resumen)
        checkpoint = await piezas.workflow.resolve_pause_checkpoint_id([pendiente.request_id])
        _emitir_aprobacion_solicitada(checkpoint, solicitud)
        if modo_aprobacion == "pendiente":
            print(f"\nLa ejecución queda guardada. Para decidir más tarde:\n  python -m agente_pedidos reanudar --checkpoint {checkpoint} --decision si|no --aprobador \"{aprobador}\"")
            print("\nCoste hasta la parada:", piezas.contador.resumen())
            await bc.cerrar()
            return 0
        if modo_aprobacion == "preguntar":
            aprobado = preguntar_aprobacion("\n¿Crear el pedido? [s/n] ", middleware[0], f"crear pedido ({ruta_correo})")
            comentario = "" if sys.stdin.isatty() else "denegado: no hay terminal para preguntar"
            if sys.stdin.isatty():
                try:
                    comentario = input("Comentario (opcional): ").strip()
                except EOFError:
                    comentario = "denegado: la consola no devolvió respuesta (EOF)"
        else:
            aprobado = modo_aprobacion == "si"
            comentario = "aprobación automática desde la línea de comandos" if aprobado else "rechazo automático desde la línea de comandos"
        decision = DecisionHumana(aprobado=aprobado, comentario=comentario, aprobador=aprobador)
        _emitir_aprobacion_resuelta(checkpoint, decision)
        async for evento in piezas.workflow.run(stream=True, responses={pendiente.request_id: decision}):
            if evento.type == "executor_invoked":
                print(f"  paso: {evento.executor_id}")
            elif evento.type == "output":
                salidas.append(evento.data)
        marcar_resuelto(storage, checkpoint, decision)  # ya no es una aprobación pendiente

    _terminar_tarea(salidas)
    for salida in salidas:
        imprimir_resultado(salida)
    print("\nCoste:", piezas.contador.resumen())
    print("Auditoría de herramientas:", middleware[0].ruta)
    await bc.cerrar()
    return 0


async def cmd_reanudar(checkpoint_id: str, decision_texto: str, comentario: str, aprobador: str) -> int:
    storage = crear_storage(os.environ.get("AGENTE_CHECKPOINTS", "checkpoints"))
    motivo = await motivo_para_no_reanudar(storage, checkpoint_id)
    if motivo:
        # Reanudar dos veces la misma aprobación podría crear el pedido dos veces.
        print(f"No se reanuda el checkpoint {checkpoint_id}. {motivo}")
        return 1
    middleware = crear_middleware()
    bc = crear_cliente_bc(auditoria=middleware[0])
    piezas = construir_workflow(bc, Politica.desde_entorno(), storage, middleware)
    checkpoint = await storage.load(checkpoint_id)
    pendientes = list(checkpoint.pending_request_info_events.keys())
    if not pendientes:
        print("Ese checkpoint no tiene ninguna aprobación pendiente.")
        await bc.cerrar()
        return 1
    decision = DecisionHumana(aprobado=decision_texto == "si", comentario=comentario, aprobador=aprobador)
    # La tarea sigue siendo la del «procesar» original: su id viaja dentro del checkpoint.
    tarea = _tarea_de_la_solicitud(checkpoint.pending_request_info_events[pendientes[0]])
    eventos.fijar_tarea(tarea or eventos.nueva_tarea_id())
    if tarea is None:  # checkpoint anterior a los eventos: se abre una tarea para no perder el rastro
        eventos.emitir("tarea_iniciada", origen=f"checkpoint {checkpoint_id}", resumen="Reanudación de una aprobación guardada")
    _emitir_aprobacion_resuelta(checkpoint_id, decision)
    salidas: list[ResultadoPedido] = []
    try:
        async for evento in piezas.workflow.run(stream=True, checkpoint_id=checkpoint_id, responses={pendientes[0]: decision}):
            if evento.type == "executor_invoked":
                print(f"  paso: {evento.executor_id}")
            elif evento.type == "output":
                salidas.append(evento.data)
    except Exception as error:
        _terminar_con_error(error)
        raise
    marcar_resuelto(storage, checkpoint_id, decision)
    _terminar_tarea(salidas)
    for salida in salidas:
        imprimir_resultado(salida)
    print("\nCoste de esta reanudación:", piezas.contador.resumen())
    print("Auditoría:", middleware[0].ruta)
    await bc.cerrar()
    return 0


async def cmd_pendientes() -> int:
    storage = crear_storage(os.environ.get("AGENTE_CHECKPOINTS", "checkpoints"))
    pendientes = await aprobaciones_pendientes(storage)  # sin las ya resueltas
    for cp in pendientes:
        print(f"checkpoint {cp.checkpoint_id}  ({cp.timestamp})")
        for request_id, evento in cp.pending_request_info_events.items():
            datos = evento.get("data") if isinstance(evento, dict) else getattr(evento, "data", None)
            resumen = getattr(datos, "resumen", None) or (datos.get("resumen") if isinstance(datos, dict) else "")
            print(f"  solicitud {request_id}\n    " + str(resumen).replace("\n", "\n    "))
    if not pendientes:
        print("No hay aprobaciones pendientes.")
    return 0


async def cmd_chat(mensaje: str, aprobador: str) -> int:
    """Variante conversacional: aprobación a nivel de agente (approval_mode) en lugar de workflow."""
    middleware = crear_middleware()
    bc = crear_cliente_bc(auditoria=middleware[0])
    agente = crear_agente_asistente(bc, middleware)
    sesion = agente.create_session()
    contador = ContadorCoste()

    respuesta = await agente.run(mensaje, session=sesion)
    contador.registrar(respuesta)
    while respuesta.user_input_requests:
        peticion = respuesta.user_input_requests[0]
        print("\n=== EL AGENTE QUIERE EJECUTAR UNA HERRAMIENTA PROTEGIDA ===")
        print("Herramienta:", peticion.function_call.name)
        print("Argumentos:", json.dumps(peticion.function_call.parse_arguments(), ensure_ascii=False, indent=2))
        if not sys.stdin.isatty() and "CHAT_APROBAR" in os.environ:
            # Decisión explícita para ejecuciones sin terminal (scripts, pruebas).
            aprobado = os.environ["CHAT_APROBAR"] == "si"
            print("Decisión (CHAT_APROBAR):", "aprobar" if aprobado else "rechazar")
        else:
            aprobado = preguntar_aprobacion("¿Aprobar? [s/n] ", middleware[0], f"{peticion.function_call.name} (chat)")
        contenido = peticion.to_function_approval_response(approved=aprobado)
        respuesta = await agente.run(Message("user", [contenido]), session=sesion)
        contador.registrar(respuesta)
    print("\n" + (respuesta.text or ""))
    print("\nCoste:", contador.resumen())
    await bc.cerrar()
    return 0


async def cmd_demo(aprobador: str) -> int:
    for nombre in CORREOS_DEMO:
        print("\n" + "=" * 78)
        codigo = await cmd_procesar(str(Path("ejemplos/correos") / nombre), "si", aprobador)
        if codigo:
            return codigo
    return 0


def cmd_grafo() -> int:
    piezas = construir_workflow(ClienteDemo())
    print(dibujar_mermaid(piezas.workflow))
    return 0


# --- entrada -------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    cargar_entorno()
    if configurar_observabilidad():
        print("Observabilidad: trazas OpenTelemetry activadas")

    parser = argparse.ArgumentParser(prog="agente_pedidos", description="Agente de pedidos de venta sobre Business Central (Microsoft Agent Framework)")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("procesar", help="procesa un correo con el workflow")
    p.add_argument("correo", help="ruta del fichero de texto con el correo")
    p.add_argument("--aprobar", choices=["preguntar", "si", "no", "pendiente"], default="preguntar", help="qué hacer si hace falta aprobación")
    p.add_argument("--aprobador", default=os.environ.get("USER", "aprobador"))

    p = sub.add_parser("reanudar", help="responde a una aprobación guardada en un checkpoint")
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--decision", choices=["si", "no"], required=True)
    p.add_argument("--comentario", default="")
    p.add_argument("--aprobador", default=os.environ.get("USER", "aprobador"))

    sub.add_parser("pendientes", help="lista las aprobaciones pendientes")

    p = sub.add_parser("chat", help="asistente conversacional con herramienta de escritura protegida")
    p.add_argument("mensaje")
    p.add_argument("--aprobador", default=os.environ.get("USER", "aprobador"))

    p = sub.add_parser("demo", help="procesa los correos de ejemplo con aprobación automática")
    p.add_argument("--aprobador", default="demo")

    sub.add_parser("grafo", help="imprime el workflow en Mermaid")

    args = parser.parse_args(argv)
    if args.comando == "procesar":
        return asyncio.run(cmd_procesar(args.correo, args.aprobar, args.aprobador))
    if args.comando == "reanudar":
        return asyncio.run(cmd_reanudar(args.checkpoint, args.decision, args.comentario, args.aprobador))
    if args.comando == "pendientes":
        return asyncio.run(cmd_pendientes())
    if args.comando == "chat":
        return asyncio.run(cmd_chat(args.mensaje, args.aprobador))
    if args.comando == "demo":
        return asyncio.run(cmd_demo(args.aprobador))
    if args.comando == "grafo":
        return cmd_grafo()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
