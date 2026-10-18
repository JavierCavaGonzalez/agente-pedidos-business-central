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
from pathlib import Path
from typing import Any

from agent_framework import Message

from .agentes import crear_agente_asistente
from .bc import ClienteApiV2, ClienteBC, ClienteDemo
from .esquemas import DecisionHumana, ResultadoPedido
from .middleware import AuditoriaHerramientas, PresupuestoLlamadas, SoloLectura
from .observabilidad import ContadorCoste, configurar_observabilidad
from .politicas import Politica
from .workflow import NOMBRE_WORKFLOW, construir_workflow, crear_storage, dibujar_mermaid

CORREOS_DEMO = ["01_pedido_pequeno.txt", "02_pedido_grande.txt", "03_cliente_bloqueado.txt", "04_con_dudas.txt"]


# --- infraestructura común ----------------------------------------------------------------


def crear_cliente_bc() -> ClienteBC:
    """``BC_MODO=demo`` (por defecto) usa datos simulados; ``BC_MODO=api`` usa la API v2.0 de un sandbox."""
    modo = os.environ.get("BC_MODO", "demo").strip().lower()
    if modo == "demo":
        return ClienteDemo()
    if modo == "api":
        return ClienteApiV2.desde_entorno()
    raise SystemExit(f"BC_MODO='{modo}' no es válido (demo | api)")


def crear_middleware() -> list[Any]:
    return [AuditoriaHerramientas(), SoloLectura(), PresupuestoLlamadas()]


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
    bc = crear_cliente_bc()
    middleware = crear_middleware()
    storage = crear_storage(os.environ.get("AGENTE_CHECKPOINTS", "checkpoints"))
    piezas = construir_workflow(bc, Politica.desde_entorno(), storage, middleware)
    correo = Path(ruta_correo).read_text(encoding="utf-8")

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
        if modo_aprobacion == "pendiente":
            print(f"\nLa ejecución queda guardada. Para decidir más tarde:\n  python -m agente_pedidos reanudar --checkpoint {checkpoint} --decision si|no --aprobador \"{aprobador}\"")
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
        async for evento in piezas.workflow.run(stream=True, responses={pendiente.request_id: decision}):
            if evento.type == "executor_invoked":
                print(f"  paso: {evento.executor_id}")
            elif evento.type == "output":
                salidas.append(evento.data)

    for salida in salidas:
        imprimir_resultado(salida)
    print("\nCoste:", piezas.contador.resumen())
    print("Auditoría de herramientas:", middleware[0].ruta)
    await bc.cerrar()
    return 0


async def cmd_reanudar(checkpoint_id: str, decision_texto: str, comentario: str, aprobador: str) -> int:
    bc = crear_cliente_bc()
    storage = crear_storage(os.environ.get("AGENTE_CHECKPOINTS", "checkpoints"))
    piezas = construir_workflow(bc, Politica.desde_entorno(), storage, crear_middleware())
    checkpoint = await storage.load(checkpoint_id)
    pendientes = list(checkpoint.pending_request_info_events.keys())
    if not pendientes:
        print("Ese checkpoint no tiene ninguna aprobación pendiente.")
        return 1
    decision = DecisionHumana(aprobado=decision_texto == "si", comentario=comentario, aprobador=aprobador)
    salidas: list[ResultadoPedido] = []
    async for evento in piezas.workflow.run(stream=True, checkpoint_id=checkpoint_id, responses={pendientes[0]: decision}):
        if evento.type == "executor_invoked":
            print(f"  paso: {evento.executor_id}")
        elif evento.type == "output":
            salidas.append(evento.data)
    for salida in salidas:
        imprimir_resultado(salida)
    print("\nCoste de esta reanudación:", piezas.contador.resumen())
    await bc.cerrar()
    return 0


async def cmd_pendientes() -> int:
    storage = crear_storage(os.environ.get("AGENTE_CHECKPOINTS", "checkpoints"))
    checkpoints = await storage.list_checkpoints(workflow_name=NOMBRE_WORKFLOW)
    encontrados = 0
    for cp in sorted(checkpoints, key=lambda c: c.timestamp):
        if cp.pending_request_info_events:
            encontrados += 1
            print(f"checkpoint {cp.checkpoint_id}  ({cp.timestamp})")
            for request_id, evento in cp.pending_request_info_events.items():
                datos = evento.get("data") if isinstance(evento, dict) else getattr(evento, "data", None)
                resumen = getattr(datos, "resumen", None) or (datos.get("resumen") if isinstance(datos, dict) else "")
                print(f"  solicitud {request_id}\n    " + str(resumen).replace("\n", "\n    "))
    if not encontrados:
        print("No hay aprobaciones pendientes.")
    return 0


async def cmd_chat(mensaje: str, aprobador: str) -> int:
    """Variante conversacional: aprobación a nivel de agente (approval_mode) en lugar de workflow."""
    bc = crear_cliente_bc()
    middleware = crear_middleware()
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
