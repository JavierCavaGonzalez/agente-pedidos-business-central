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
from collections.abc import Callable
from typing import Any

from agente_pedidos import formato

SEGUNDOS_RESULTADO = 10
# Tareas a la vez que cuentan como carga completa de un agente (la barra «Carga» del panel de detalle).
CAPACIDAD_POR_AGENTE = 3
# Presupuesto de coste del modelo por día si no se indica OFICINA_PRESUPUESTO_DIA_EUR.
PRESUPUESTO_DIA_EUR = 1.0
LIMITE_FEED = 80

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
    clase: str = "pedido"  # "pedido" o "pregunta"

    @property
    def es_pregunta(self) -> bool:
        """Una pregunta al agente (comando ``chat``): no cuenta como tarea ni como carga."""
        return self.clase == "pregunta"

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
            "clase": self.clase,
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
            tarea.clase = evento["datos"].get("clase") or "pedido"
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
    "estado_oficina": "Consultando el estado de la oficina",
}


def euros(importe: float | None, decimales: int = 2) -> str:
    """Formato español; los costes del modelo, con 4 decimales (0,0042 € no es «0,00 €»)."""
    return formato.euros(importe, decimales)


def describir(evento: dict[str, Any]) -> str | None:
    """Frase legible para un evento, o ``None`` si no merece bocadillo (p. ej. una llamada al modelo)."""
    tipo, datos = evento["tipo"], evento["datos"]
    if tipo == "tarea_iniciada":
        if datos.get("clase") == "pregunta":
            return f"Pregunta: {datos.get('resumen') or '…'}"
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
        return {"respondido": "Terminado: respuesta dada", "rechazado": "Terminado: pedido rechazado", "denegado": "Terminado: pedido denegado", "error": "Terminado con error"}.get(resultado, f"Terminado: {resultado}")
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
                "tareas_hoy": sum(1 for t in suyas if not t.es_pregunta),
                "preguntas_hoy": sum(1 for t in suyas if t.es_pregunta),
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
        "tareas_en_curso": sum(1 for t in tareas.values() if t.abierta and not t.es_pregunta),
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
    erp: dict[str, Any] | None = None,
    enlace_pedido: Callable[[str | None], str | None] | None = None,
    presupuesto_dia_eur: float = PRESUPUESTO_DIA_EUR,
) -> dict[str, Any]:
    """Todo lo que la interfaz necesita para dibujar la oficina en un instante.

    ``erp`` describe Business Central (modo, entorno, empresa, enlace) y ``enlace_pedido`` da el
    enlace profundo de un pedido (``None`` en simulación); los dos los pone el backend.
    """
    pendientes_por_agente: dict[str, int] = {}
    for aprobacion in aprobaciones:
        pendientes_por_agente[aprobacion["agente"]] = pendientes_por_agente.get(aprobacion["agente"], 0) + 1
    agentes = estado_agentes(eventos_hoy, ahora, pendientes_por_agente, detenidos)
    grupos = agrupar_tareas(eventos_hoy)
    tareas = sorted(
        ({**t.resumen_publico(), "seguimiento": seguimiento(t, ahora)} for t in grupos.values()),
        key=lambda t: t["inicio"] or "",
        reverse=True,
    )
    pedidos = pedidos_de_hoy(eventos_hoy, grupos, enlace_pedido or (lambda _numero: None))
    for agente in agentes:
        suyos = [e for e in eventos_hoy if e["agente"] == agente["id"]]
        agente["herramientas"] = herramientas(suyos)
        agente["tareas_en_curso"] = sum(1 for t in grupos.values() if t.agente == agente["id"] and t.abierta and not t.es_pregunta)
        agente["capacidad"] = CAPACIDAD_POR_AGENTE
        agente["llamadas_modelo_hoy"] = sum(1 for e in suyos if e["tipo"] == "modelo_llamada")
        agente["pedidos_hoy"] = [p for p in pedidos if p["agente"] == agente["id"]]
    escrituras = [e for e in eventos_hoy if e["tipo"] == "erp_escritura"]
    return {
        "ahora": ahora.isoformat(timespec="seconds"),
        "modo_erp": modo_erp,
        "modelo": modelo,
        "agentes": agentes,
        "tareas": tareas,
        "aprobaciones": aprobaciones,
        "tablero": tablero(eventos_hoy, agentes, len(aprobaciones)),
        "pedidos": pedidos,
        "feed": feed(eventos_hoy),
        "erp": {
            **(erp or {"modo": modo_erp}),
            "escrituras_hoy": len(escrituras),
            "bloqueadas_hoy": sum(1 for e in eventos_hoy if e["tipo"] == "erp_bloqueada"),
            "ultima_escritura": {"ts": escrituras[-1]["ts"], "pedido": escrituras[-1]["datos"].get("pedido")} if escrituras else None,
        },
        "presupuesto_dia_eur": presupuesto_dia_eur,
        # Las preguntas al agente van aparte: no son tareas ni cuentan en la carga
        "preguntas": {
            "hoy": sum(1 for t in grupos.values() if t.es_pregunta),
            "coste_eur": round(sum(t.coste() for t in grupos.values() if t.es_pregunta), 6),
        },
    }


# --- seguimiento de una tarea, pedidos del día y feed ---------------------------------------------

# La línea de pasos del panel «Seguimiento de tarea». Cada evento abre un paso.
PASOS_SEGUIMIENTO: list[tuple[str, str]] = [
    ("recibido", "Recibido"),
    ("interpretado", "Interpretado"),
    ("validado", "Validado"),
    ("aprobacion", "Aprobación"),
    ("creado", "Creado en BC"),
    ("respondido", "Respondido"),
]
_PASO_DE_EVENTO = {
    ("tarea_iniciada", None): "recibido",
    ("paso", "interpretar"): "interpretado",
    ("paso", "validar"): "validado",
    ("paso", "politica"): "validado",
    ("paso", "aprobacion_humana"): "aprobacion",
    ("aprobacion_solicitada", None): "aprobacion",
    ("paso", "crear_pedido"): "creado",
    ("erp_escritura", None): "creado",
    ("paso", "redactar"): "respondido",
}


def seguimiento(tarea: Tarea, ahora: datetime) -> dict[str, Any] | None:
    """Pasos de una tarea de pedido (Recibido → … → Respondido) con su estado y su tiempo.

    Estados de un paso: ``hecho``, ``actual``, ``pendiente``, ``omitido`` (no hacía falta, p. ej.
    la aprobación de un pedido pequeño) y ``fallido`` (rechazado, denegado o error). El tiempo de
    un paso va de su primer evento al del paso siguiente. Una pregunta al agente no es un pedido:
    no tiene seguimiento (``None``).
    """
    if any(e["tipo"] == "tarea_iniciada" and e["datos"].get("clase") == "pregunta" for e in tarea.eventos):
        return None
    claves = [c for c, _ in PASOS_SEGUIMIENTO]
    inicio: dict[str, str] = {}
    notas: dict[str, str] = {}
    fallidos: set[str] = set()
    actual = "recibido"
    cliente, total, lineas = None, None, []
    for evento in tarea.eventos:
        tipo, datos = evento["tipo"], evento["datos"]
        clave = _PASO_DE_EVENTO.get((tipo, datos.get("nombre") if tipo == "paso" else None))
        if clave:
            inicio.setdefault(clave, evento["ts"])
            if claves.index(clave) >= claves.index(actual):
                actual = clave
        if tipo == "paso" and datos.get("nombre") == "politica":
            cliente, total, lineas = datos.get("cliente") or cliente, datos.get("total", total), datos.get("lineas") or lineas
            if datos.get("descripcion", "").startswith("Dentro de la política"):
                notas["aprobacion"] = "No hacía falta"
        elif tipo == "aprobacion_solicitada":
            cliente = cliente or datos.get("cliente")
            total = total if total is not None else datos.get("importe")
            lineas = lineas or [{"descripcion": linea} for linea in datos.get("lineas", [])]
        elif tipo == "aprobacion_resuelta":
            aprobado = datos.get("decision") == "si"
            notas["aprobacion"] = f"{'Aprobado' if aprobado else 'Denegado'} por {datos.get('aprobador') or 'el director'}"
            if not aprobado:
                fallidos.add("aprobacion")
        elif tipo == "erp_escritura":
            notas["creado"] = f"Pedido {datos.get('pedido')}"
        elif tipo == "paso" and datos.get("nombre") == "rechazar" and "aprobacion" not in fallidos:
            fallidos.add("validado")
            notas["validado"] = datos.get("descripcion") or "Rechazado"
        elif tipo == "error":
            fallidos.add(actual)
            notas[actual] = datos.get("mensaje") or "Error"
    terminada = tarea.fin is not None
    empezados = [c for c in claves if c in inicio]
    pasos = []
    for i, (clave, etiqueta) in enumerate(PASOS_SEGUIMIENTO):
        if clave in fallidos:
            situacion = "fallido"
        elif clave == actual and not terminada:
            situacion = "actual"
        elif clave in inicio:
            situacion = "hecho"
        elif terminada or i < claves.index(actual):
            situacion = "omitido"
        else:
            situacion = "pendiente"
        duracion = None
        if clave in inicio:
            siguientes = [inicio[c] for c in empezados if claves.index(c) > i]
            fin = siguientes[0] if siguientes else (tarea.fin["ts"] if terminada else None)
            hasta = datetime.fromisoformat(fin) if fin else ahora
            duracion = max(0.0, round((hasta - datetime.fromisoformat(inicio[clave])).total_seconds(), 1))
        pasos.append({"clave": clave, "etiqueta": etiqueta, "estado": situacion, "inicio": inicio.get(clave), "duracion_s": duracion, "nota": notas.get(clave)})
    return {"pasos": pasos, "actual": None if terminada else actual, "cliente": cliente, "total": total, "lineas": lineas}


def pedidos_de_hoy(eventos: list[dict[str, Any]], tareas: dict[str, Tarea], enlace: Callable[[str | None], str | None]) -> list[dict[str, Any]]:
    """Pedidos creados hoy (eventos ``erp_escritura``), el más reciente primero, con su enlace a BC."""
    pedidos = []
    for evento in eventos:
        if evento["tipo"] != "erp_escritura":
            continue
        datos = evento["datos"]
        tarea = tareas.get(evento.get("tarea") or "")
        nombre = (seguimiento(tarea, datetime.fromisoformat(evento["ts"])) or {}).get("cliente") if tarea else None
        pedidos.append(
            {
                "pedido": datos.get("pedido"),
                "cliente": nombre or datos.get("cliente"),
                "importe": datos.get("importe"),
                # El agente crea pedidos abiertos: ni los lanza ni los registra.
                "estado_bc": "Abierto",
                "modo": datos.get("modo"),
                "ts": evento["ts"],
                "tarea": evento.get("tarea"),
                "agente": evento["agente"],
                "enlace": enlace(datos.get("pedido")) if datos.get("modo") == "api" else None,
            }
        )
    return list(reversed(pedidos))


def herramientas(eventos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Herramientas usadas: llamadas y errores (un resultado distinto de «ok» es un error)."""
    cuenta: dict[str, dict[str, Any]] = {}
    for evento in eventos:
        if evento["tipo"] != "herramienta":
            continue
        nombre = evento["datos"].get("nombre") or "?"
        fila = cuenta.setdefault(nombre, {"nombre": nombre, "llamadas": 0, "errores": 0})
        fila["llamadas"] += 1
        fila["errores"] += int(evento["datos"].get("resultado") != "ok")
    return sorted(cuenta.values(), key=lambda f: -f["llamadas"])


_CATEGORIA = {
    "erp_escritura": "bc",
    "erp_bloqueada": "bc",
    "herramienta": "bc",
    "aprobacion_solicitada": "aprobaciones",
    "aprobacion_resuelta": "aprobaciones",
    "modelo_llamada": "modelo",
}


def describir_feed(evento: dict[str, Any]) -> str | None:
    """Frase del feed de actividad: la del bocadillo y, además, llamadas al modelo y respuestas."""
    tipo, datos = evento["tipo"], evento["datos"]
    if tipo == "modelo_llamada":
        tokens = (datos.get("tokens_entrada") or 0) + (datos.get("tokens_salida") or 0)
        miles = f"{tokens:,}".replace(",", ".")
        return f"Llamada al modelo · {miles} tokens · {euros(datos.get('coste_eur'), 4)}"
    if tipo == "erp_escritura":
        return f"Pedido {datos.get('pedido')} creado · {euros(datos.get('importe'))}"
    if tipo == "aprobacion_solicitada":
        return f"Aprobación solicitada · {euros(datos.get('importe'))} · {datos.get('motivo') or datos.get('cliente')}"
    if tipo == "agente_detenido":
        return "Detenido por el director"
    if tipo == "agente_activado":
        return "Activado por el director"
    if tipo == "respuesta_agente":
        return f"Respuesta: {datos.get('texto') or '(vacía)'}"
    return describir(evento)


def feed(eventos: list[dict[str, Any]], limite: int = LIMITE_FEED) -> list[dict[str, Any]]:
    """Los últimos eventos del día como frases, el más reciente primero, con su categoría para filtrar."""
    filas = []
    for evento in reversed(eventos):
        texto = describir_feed(evento)
        if not texto:
            continue
        datos = evento["datos"]
        filas.append(
            {
                "ts": evento["ts"],
                "tipo": evento["tipo"],
                "categoria": _CATEGORIA.get(evento["tipo"], "tareas"),
                "agente": evento["agente"],
                "tarea": evento.get("tarea"),
                "texto": texto,
                "coste_eur": datos.get("coste_eur") if evento["tipo"] == "respuesta_agente" else None,
                "error": evento["tipo"] in ("error", "erp_bloqueada") or (evento["tipo"] == "herramienta" and datos.get("resultado") != "ok"),
            }
        )
        if len(filas) >= limite:
            break
    return filas


def ahora_local() -> datetime:
    return datetime.now().astimezone()
