"""Estado de la oficina derivado de los eventos (funciones puras, sin E/S).

Principio *nada sin rastro*: todo lo que devuelve este módulo sale de ``eventos.jsonl`` (y de
las aprobaciones pendientes que lee el backend de los checkpoints). No hay estado guardado
aparte que pueda contradecir al registro.

Estado de un agente:

- ``detenido``: el director lo detuvo (último ``agente_detenido`` sin ``agente_activado`` después).
- ``error``: una tarea abierta cuyo último evento es ``error``, o una terminada con error hace
  menos de ``SEGUNDOS_RESULTADO``.
- ``trabajando``: una tarea abierta que no espera aprobación, o una terminada hace menos de
  ``SEGUNDOS_RESULTADO`` (para que se vea el resultado en el bocadillo).
- ``esperando_aprobacion``: una tarea con ``aprobacion_solicitada`` sin ``aprobacion_resuelta``.
- ``libre``: nada de lo anterior.

Si un agente tiene varias tareas a la vez, gana la más urgente de ver: error, después
trabajando y después esperando (las tarjetas de aprobación se muestran igualmente).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agente_pedidos.observabilidad import redondear_eur

SEGUNDOS_RESULTADO = 10

AGENTES: list[dict[str, str]] = [
    {"id": "pedidos", "nombre": "Agente de Pedidos", "rol": "Ventas"},
]

_PRIORIDAD = {"error": 3, "trabajando": 2, "esperando_aprobacion": 1, "libre": 0}


@dataclass
class Tarea:
    id: str
    agente: str
    inicio: str | None = None
    origen: str | None = None
    resumen: str | None = None
    eventos: list[dict[str, Any]] = field(default_factory=list)
    fin: dict[str, Any] | None = None  # el evento tarea_terminada

    @property
    def abierta(self) -> bool:
        return self.fin is None

    @property
    def esperando(self) -> bool:
        """Hay una aprobación solicitada que todavía no se ha resuelto."""
        pendiente = False
        for evento in self.eventos:
            if evento["tipo"] == "aprobacion_solicitada":
                pendiente = True
            elif evento["tipo"] == "aprobacion_resuelta":
                pendiente = False
        return pendiente

    @property
    def ultimo(self) -> dict[str, Any]:
        return self.eventos[-1]

    def coste(self) -> float:
        return round(sum(e["datos"].get("coste_eur", 0) for e in self.eventos if e["tipo"] == "modelo_llamada"), 6)

    def resumen_publico(self) -> dict[str, Any]:
        fin = (self.fin or {}).get("datos", {})
        return {
            "id": self.id,
            "agente": self.agente,
            "origen": self.origen,
            "resumen": self.resumen,
            "inicio": self.inicio,
            "fin": self.fin["ts"] if self.fin else None,
            "estado": "terminada" if self.fin else ("esperando_aprobacion" if self.esperando else ("error" if self.ultimo["tipo"] == "error" else "en_curso")),
            "resultado": fin.get("resultado"),
            "pedido": fin.get("pedido"),
            "coste_eur": self.coste(),
            "duracion_s": fin.get("duracion_s"),
            "bocadillo": bocadillo(self),
        }


def agrupar_tareas(eventos: list[dict[str, Any]]) -> dict[str, Tarea]:
    tareas: dict[str, Tarea] = {}
    for evento in eventos:
        if not evento.get("tarea"):
            continue
        tarea = tareas.setdefault(evento["tarea"], Tarea(id=evento["tarea"], agente=evento["agente"]))
        tarea.eventos.append(evento)
        if evento["tipo"] == "tarea_iniciada":
            tarea.inicio = evento["ts"]
            tarea.origen = evento["datos"].get("origen")
            tarea.resumen = evento["datos"].get("resumen")
        elif evento["tipo"] == "tarea_terminada":
            tarea.fin = evento
    return tareas


# --- el bocadillo: lo que el agente está haciendo, en una frase -----------------------------------

_HERRAMIENTAS = {
    "buscar_clientes": "Buscando cliente «{texto}»",
    "obtener_cliente": "Consultando el cliente {numero}",
    "buscar_articulos": "Buscando artículo «{texto}»",
    "obtener_articulo": "Consultando el artículo {numero}",
    "crear_pedido_venta": "Creando el pedido para el cliente {numero_cliente}",
}


def euros(importe: float | None, decimales: int = 2) -> str:
    """Formato español; los costes del modelo, con 4 decimales (0,0042 € no es «0,00 €»)."""
    if importe is None:
        return "—"
    return f"{redondear_eur(importe, decimales):,} €".replace(",", "_").replace(".", ",").replace("_", ".")


def describir(evento: dict[str, Any]) -> str | None:
    """Frase legible para un evento, o ``None`` si no merece bocadillo (p. ej. una llamada al modelo)."""
    tipo, datos = evento["tipo"], evento["datos"]
    if tipo == "tarea_iniciada":
        return f"Nueva tarea: {datos.get('origen') or 'correo'}"
    if tipo == "paso":
        return datos.get("descripcion") or datos.get("nombre")
    if tipo == "herramienta":
        plantilla = _HERRAMIENTAS.get(datos.get("nombre"), "Usando {nombre}")
        try:
            frase = plantilla.format(nombre=datos.get("nombre"), **datos.get("argumentos", {}))
        except (KeyError, IndexError):
            frase = f"Usando {datos.get('nombre')}"
        return frase + ("…" if datos.get("resultado") == "ok" else f": {datos.get('resultado')}")
    if tipo == "aprobacion_solicitada":
        return f"Esperando aprobación: {euros(datos.get('importe'))} · {datos.get('cliente')}"
    if tipo == "aprobacion_resuelta":
        decision = "Aprobado" if datos.get("decision") == "si" else "Denegado"
        return f"{decision} por {datos.get('aprobador') or 'el director'}"
    if tipo == "erp_escritura":
        return f"Pedido {datos.get('pedido')} creado en Business Central ({euros(datos.get('importe'))})"
    if tipo == "erp_bloqueada":
        return f"Escritura bloqueada: {datos.get('motivo')}"
    if tipo == "error":
        return f"Error: {datos.get('mensaje')}"
    if tipo == "tarea_terminada":
        resultado = datos.get("resultado")
        if resultado == "creado":
            return f"Hecho: pedido {datos.get('pedido')} · coste {euros(datos.get('coste_total_eur'), 4)}"
        return {"rechazado": "Terminado: pedido rechazado", "denegado": "Terminado: pedido denegado", "error": "Terminado con error"}.get(resultado, f"Terminado: {resultado}")
    return None


def bocadillo(tarea: Tarea) -> str | None:
    for evento in reversed(tarea.eventos):
        frase = describir(evento)
        if frase:
            return frase
    return None


# --- agentes y tablero ----------------------------------------------------------------------------


def _segundos_desde(ts: str, ahora: datetime) -> float:
    return (ahora - datetime.fromisoformat(ts)).total_seconds()


def estado_de_tarea(tarea: Tarea, ahora: datetime) -> str:
    if tarea.fin is not None:
        if _segundos_desde(tarea.fin["ts"], ahora) >= SEGUNDOS_RESULTADO:
            return "libre"
        return "error" if tarea.fin["datos"].get("resultado") == "error" else "trabajando"
    if tarea.ultimo["tipo"] == "error":
        return "error"
    return "esperando_aprobacion" if tarea.esperando else "trabajando"


def estado_agentes(
    eventos: list[dict[str, Any]],
    ahora: datetime,
    pendientes_por_agente: dict[str, int] | None = None,
    detenidos: dict[str, str] | None = None,
    agentes: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """``detenidos`` (agente -> desde) se calcula con todos los días; si falta, con ``eventos``."""
    agentes = agentes or AGENTES
    pendientes_por_agente = pendientes_por_agente or {}
    if detenidos is None:
        detenidos = {a["id"]: d for a in agentes if (d := detenido_desde(eventos, a["id"]))}
    tareas = agrupar_tareas(eventos)
    resultado = []
    for agente in agentes:
        suyas = [t for t in tareas.values() if t.agente == agente["id"]]
        estado, desde, actual = "libre", None, None
        for tarea in suyas:
            candidato = estado_de_tarea(tarea, ahora)
            if _PRIORIDAD[candidato] > _PRIORIDAD[estado] or (candidato == estado and candidato != "libre"):
                estado, desde, actual = candidato, tarea.ultimo["ts"], tarea
        if estado == "libre" and pendientes_por_agente.get(agente["id"]):
            estado = "esperando_aprobacion"  # p. ej. una aprobación de otro día, sin eventos de hoy
        if estado == "libre" and suyas:
            ultima = max(suyas, key=lambda t: t.ultimo["ts"])
            desde = ultima.fin["ts"] if ultima.fin else None
        if agente["id"] in detenidos:
            estado, desde = "detenido", detenidos[agente["id"]]
        resultado.append(
            {
                **agente,
                "estado": estado,
                "desde": desde,
                "tarea": actual.id if actual else None,
                "bocadillo": bocadillo(actual) if actual else None,
                "resultado_reciente": _resultado_reciente(actual, ahora),
                "aprobaciones_pendientes": pendientes_por_agente.get(agente["id"], 0),
                "tareas_hoy": len(suyas),
                "coste_hoy_eur": round(sum(e["datos"].get("coste_eur", 0) for e in eventos if e["agente"] == agente["id"] and e["tipo"] == "modelo_llamada"), 6),
            }
        )
    return resultado


def _resultado_reciente(tarea: Tarea | None, ahora: datetime) -> dict[str, Any] | None:
    """La tarea mostrada terminó hace menos de SEGUNDOS_RESULTADO: su resultado, para que la chapa no diga «Trabajando»."""
    if tarea is None or tarea.fin is None or _segundos_desde(tarea.fin["ts"], ahora) >= SEGUNDOS_RESULTADO:
        return None
    return {"resultado": tarea.fin["datos"].get("resultado"), "pedido": tarea.fin["datos"].get("pedido")}


def detenido_desde(eventos: list[dict[str, Any]], agente: str) -> str | None:
    desde = None
    for evento in eventos:
        if evento["agente"] != agente:
            continue
        if evento["tipo"] == "agente_detenido":
            desde = evento["ts"]
        elif evento["tipo"] == "agente_activado":
            desde = None
    return desde


def tablero(eventos: list[dict[str, Any]], agentes: list[dict[str, Any]], aprobaciones_pendientes: int) -> dict[str, Any]:
    tareas = agrupar_tareas(eventos)
    return {
        "agentes_activos": sum(1 for a in agentes if a["estado"] in ("trabajando", "esperando_aprobacion", "error")),
        "tareas_en_curso": sum(1 for t in tareas.values() if t.abierta),
        "aprobaciones_pendientes": aprobaciones_pendientes,
        "escrituras_erp_hoy": sum(1 for e in eventos if e["tipo"] == "erp_escritura"),
        "coste_hoy_eur": round(sum(e["datos"].get("coste_eur", 0) for e in eventos if e["tipo"] == "modelo_llamada"), 6),
        "llamadas_modelo_hoy": sum(1 for e in eventos if e["tipo"] == "modelo_llamada"),
    }


def foto(
    eventos_hoy: list[dict[str, Any]],
    ahora: datetime,
    aprobaciones: list[dict[str, Any]],
    modo_erp: str,
    modelo: str,
    detenidos: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Todo lo que la interfaz necesita para dibujar la oficina en un instante."""
    pendientes_por_agente: dict[str, int] = {}
    for aprobacion in aprobaciones:
        pendientes_por_agente[aprobacion["agente"]] = pendientes_por_agente.get(aprobacion["agente"], 0) + 1
    agentes = estado_agentes(eventos_hoy, ahora, pendientes_por_agente, detenidos)
    tareas = sorted((t.resumen_publico() for t in agrupar_tareas(eventos_hoy).values()), key=lambda t: t["inicio"] or "", reverse=True)
    return {
        "ahora": ahora.isoformat(timespec="seconds"),
        "modo_erp": modo_erp,
        "modelo": modelo,
        "agentes": agentes,
        "tareas": tareas,
        "aprobaciones": aprobaciones,
        "tablero": tablero(eventos_hoy, agentes, len(aprobaciones)),
    }


def ahora_local() -> datetime:
    return datetime.now().astimezone()
