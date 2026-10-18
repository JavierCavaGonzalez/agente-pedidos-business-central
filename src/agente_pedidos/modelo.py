"""Cliente de modelo: la pieza que conecta el agente con un modelo de lenguaje.

Agent Framework separa el agente del proveedor del modelo mediante un «chat client»
(cap. 4.4 del libro de Dibia: «convertir entrada → llamar a la API → convertir salida»).
Aquí se elige el cliente con la variable de entorno ``MODELO_PROVEEDOR``:

- ``simulado`` (por defecto): un cliente sin red que imita a un modelo con reglas sencillas.
  Permite ejecutar todo el ejemplo y las pruebas sin ninguna clave.
- ``openai``: OpenAI (variables ``OPENAI_API_KEY`` y ``OPENAI_CHAT_MODEL``).
- ``azure_openai``: Azure OpenAI (``AZURE_OPENAI_ENDPOINT``, ``AZURE_OPENAI_API_KEY`` o
  credencial de Azure, ``AZURE_OPENAI_CHAT_MODEL``).
- ``foundry``: un modelo desplegado en Microsoft Foundry (``FOUNDRY_PROJECT_ENDPOINT``,
  ``FOUNDRY_MODEL``, con ``azure-identity``).

Cambiar de proveedor no toca el resto del código: esa es la razón de ser de esta pieza.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterable, Awaitable, MutableSequence, Sequence
from datetime import date
from typing import Any

from agent_framework import (
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
    UsageDetails,
)
from agent_framework.observability import ChatTelemetryLayer
from typing_extensions import override

from .formato import euros

PROVEEDORES = ("simulado", "openai", "azure_openai", "foundry")


def crear_cliente_modelo(papel: str = "interprete") -> BaseChatClient:
    """Devuelve el cliente de modelo configurado en ``MODELO_PROVEEDOR``.

    ``papel`` solo lo usa el cliente simulado para saber qué tipo de respuesta imitar
    (``interprete``, ``redactor`` o ``asistente``). Los proveedores reales lo ignoran.
    """
    proveedor = os.environ.get("MODELO_PROVEEDOR", "simulado").strip().lower()
    if proveedor == "simulado":
        return ClienteSimulado(papel=papel)
    if proveedor == "openai":
        from agent_framework.openai import OpenAIChatClient

        return OpenAIChatClient(model=os.environ.get("OPENAI_CHAT_MODEL"))
    if proveedor == "azure_openai":
        from agent_framework.openai import OpenAIChatClient

        clave = os.environ.get("AZURE_OPENAI_API_KEY")
        if clave:
            return OpenAIChatClient(
                model=os.environ.get("AZURE_OPENAI_CHAT_MODEL"),
                azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                api_key=clave,
            )
        from azure.identity import DefaultAzureCredential  # autenticación sin clave

        return OpenAIChatClient(
            model=os.environ.get("AZURE_OPENAI_CHAT_MODEL"),
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            credential=DefaultAzureCredential(),
        )
    if proveedor == "foundry":
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import DefaultAzureCredential

        return FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=DefaultAzureCredential(),
        )
    raise ValueError(f"MODELO_PROVEEDOR='{proveedor}' no es válido. Opciones: {', '.join(PROVEEDORES)}")


# ----------------------------------------------------------------------------------
# Cliente simulado
# ----------------------------------------------------------------------------------

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
# Un modelo real sabe que «silla» es «chair»; el simulado lo imita con un diccionario mínimo.
PISTAS = {
    "mesa": "desk", "escritorio": "desk", "silla": "chair", "lámpara": "lamp", "lampara": "lamp",
    "pedestal": "pedestal", "cajonera": "pedestal", "pizarra": "whiteboard", "giratori": "swivel",
    "conferencia": "conference", "negr": "black", "azul": "blue", "verde": "green", "amarill": "yellow",
}
PALABRAS_VACIAS = {
    "de", "del", "la", "las", "el", "los", "y", "para", "con", "en", "un", "una", "unos", "unas",
    "x", "uds", "ud", "unidades", "unidad", "por", "favor", "nos", "me", "que", "al",
}
# Frase de prompts/interprete.md que pide responder solo con el objeto estructurado.
SOLO_OBJETO_ESTRUCTURADO = "Devuelve exclusivamente el objeto estructurado"


class ClienteSimulado(FunctionInvocationLayer, ChatMiddlewareLayer, ChatTelemetryLayer, BaseChatClient):
    """Imita a un modelo de lenguaje con reglas sencillas y sin red.

    Hereda las mismas capas que un cliente real (invocación de funciones, middleware y
    telemetría), de modo que el bucle del agente, las llamadas a herramientas, las
    aprobaciones y las trazas funcionan exactamente igual que con OpenAI o Foundry.
    Solo hay que implementar ``_inner_get_response``.

    Comportamiento por papel:
    - ``interprete``: lee la petición, llama a ``buscar_clientes`` y a ``buscar_articulos`` y
      devuelve el JSON de ``PedidoInterpretado``.
    - ``asistente``: igual, pero termina llamando a ``crear_pedido_venta`` (que requiere aprobación)
      y, tras crearlo, confirma en texto; si sus instrucciones piden solo el objeto estructurado,
      devuelve el JSON como haría un modelo real que las obedece.
    - ``redactor``: redacta una respuesta breve a partir del resumen que recibe.
    """

    def __init__(self, papel: str = "interprete", **kwargs: Any) -> None:
        super().__init__(middleware=[], **kwargs)
        self.papel = papel
        self.llamadas: int = 0

    # Esta es la única función que exige el framework a un cliente de modelo.
    @override
    def _inner_get_response(  # type: ignore[override]
        self,
        *,
        messages: MutableSequence[Message],
        stream: bool,
        options: dict[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        self.llamadas += 1
        respuesta = self._responder(list(messages), str(options.get("instructions") or ""))

        if stream:

            async def _flujo() -> AsyncIterable[ChatResponseUpdate]:
                for mensaje in respuesta.messages:
                    yield ChatResponseUpdate(contents=list(mensaje.contents), role="assistant", finish_reason="stop")

            def _finalizar(actualizaciones: Sequence[ChatResponseUpdate]) -> ChatResponse:
                return ChatResponse.from_updates(actualizaciones, output_format_type=options.get("response_format"))

            return ResponseStream(_flujo(), finalizer=_finalizar)

        async def _obtener() -> ChatResponse:
            return respuesta

        return _obtener()

    # --- "razonamiento" simulado --------------------------------------------------
    def _responder(self, mensajes: list[Message], instrucciones: str = "") -> ChatResponse:
        texto_usuario = _ultimo_texto_usuario(mensajes)
        llamadas, resultados = _llamadas_y_resultados(mensajes)
        if self.papel == "redactor":
            return _respuesta_texto(_redactar(texto_usuario), texto_usuario)

        peticion = _analizar_peticion(texto_usuario)
        buscadas_clientes = [c for c in llamadas if c["name"] == "buscar_clientes"]
        buscadas_articulos = [c for c in llamadas if c["name"] == "buscar_articulos"]
        creaciones = [c for c in llamadas if c["name"] == "crear_pedido_venta"]

        # 1. Primero identificar al cliente
        if not buscadas_clientes:
            return _respuesta_llamada("buscar_clientes", {"texto": peticion["cliente_texto"]}, texto_usuario)
        # 2. Después, cada artículo
        if len(buscadas_articulos) < len(peticion["lineas"]):
            linea = peticion["lineas"][len(buscadas_articulos)]
            return _respuesta_llamada("buscar_articulos", {"texto": linea["terminos"]}, texto_usuario)

        pedido = _componer_pedido(peticion, buscadas_clientes, buscadas_articulos, resultados)

        if self.papel == "asistente":
            if not creaciones:
                lineas = [
                    {"numero_articulo": l["numero_articulo"], "cantidad": l["cantidad"]}
                    for l in pedido["lineas"]
                    if l["numero_articulo"]
                ]
                if pedido["numero_cliente"] and lineas:
                    return _respuesta_llamada(
                        "crear_pedido_venta",
                        {"numero_cliente": pedido["numero_cliente"], "lineas": lineas},
                        texto_usuario,
                    )
                return _respuesta_texto(
                    "No he podido identificar con seguridad el cliente o los artículos: "
                    + "; ".join(pedido["dudas"] or ["faltan datos"]),
                    texto_usuario,
                )
            # Como un modelo real: si las instrucciones piden solo el objeto estructurado, obedece
            # y devuelve el JSON en lugar de confirmar el pedido en texto.
            if SOLO_OBJETO_ESTRUCTURADO in instrucciones:
                return _respuesta_texto(json.dumps(pedido, ensure_ascii=False), texto_usuario)
            resultado = resultados.get(creaciones[-1]["call_id"])
            return _respuesta_texto(_resumir_creacion(resultado), texto_usuario)

        # papel "interprete": salida estructurada (PedidoInterpretado) en JSON
        return _respuesta_texto(json.dumps(pedido, ensure_ascii=False), texto_usuario)


# --- utilidades del cliente simulado ------------------------------------------------


def _ultimo_texto_usuario(mensajes: list[Message]) -> str:
    for mensaje in reversed(mensajes):
        if mensaje.role == "user" and mensaje.text:
            return mensaje.text
    return ""


def _llamadas_y_resultados(mensajes: list[Message]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reconstruye qué herramientas se han llamado ya y qué devolvieron."""
    llamadas: list[dict[str, Any]] = []
    resultados: dict[str, Any] = {}
    for mensaje in mensajes:
        for contenido in mensaje.contents:
            if contenido.type == "function_call":
                argumentos = contenido.arguments
                if isinstance(argumentos, str):
                    try:
                        argumentos = json.loads(argumentos)
                    except json.JSONDecodeError:
                        argumentos = {}
                llamadas.append({"call_id": contenido.call_id, "name": contenido.name, "arguments": argumentos or {}})
            elif contenido.type == "function_result":
                resultados[contenido.call_id] = _a_datos(contenido.result)
    return llamadas, resultados


def _a_datos(valor: Any) -> Any:
    """Normaliza el resultado de una herramienta: puede llegar como objeto, como JSON en texto
    o, en el caso de MCP, como una lista de contenidos de texto."""
    if isinstance(valor, list) and valor and all(hasattr(v, "text") for v in valor):
        valor = "".join(str(v.text or "") for v in valor)
    if isinstance(valor, list) and len(valor) == 1 and isinstance(valor[0], str):
        valor = valor[0]
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError:
            return valor
    # FastMCP envuelve las listas devueltas por una herramienta en {"result": [...]}
    if isinstance(valor, dict) and set(valor.keys()) == {"result"}:
        return valor["result"]
    return valor


def _analizar_peticion(texto: str) -> dict[str, Any]:
    """Extrae cliente, líneas, fecha y referencia de un correo con expresiones regulares."""
    cliente_texto = ""
    m = re.search(r"(?:^|\b)(?:empresa|cliente)\s*:\s*([^.\n]+)", texto, re.IGNORECASE | re.MULTILINE)
    if m:
        cliente_texto = m.group(1).strip()
    else:
        m = re.search(r"@([a-z0-9-]+)\.", texto, re.IGNORECASE)
        if m:
            cliente_texto = m.group(1)
    if not cliente_texto:
        m = re.search(r"\b(?:para|de)\s+([A-Z][\w&]+(?:\s+[A-Z][\w&]+)*)", texto)
        cliente_texto = m.group(1) if m else "desconocido"

    lineas: list[dict[str, Any]] = []
    cuerpo = re.sub(r"^(de|asunto|empresa|cliente|para)\s*:[^\n.]*\.?", "", texto, flags=re.IGNORECASE | re.MULTILINE)
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(?:x|uds?\.?|unidades(?: de)?)?\s+([^,;.\n]+?)(?=\s+(?:y|para|antes|con)\b|[,;.\n]|$)", cuerpo):
        cantidad = float(m.group(1).replace(",", "."))
        fragmento = m.group(2).strip()
        if re.fullmatch(r"(de\s+)?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b.*", fragmento, re.IGNORECASE):
            continue  # era una fecha, no una línea
        mayusculas = re.findall(r"\b[A-ZÁÉÍÓÚ]{3,}\b", fragmento)
        pistas = [ingles for raiz, ingles in PISTAS.items() if raiz in fragmento.lower()]
        if mayusculas or pistas:
            terminos = " ".join(dict.fromkeys(mayusculas + pistas))
        else:
            terminos = " ".join(p for p in re.findall(r"[\wáéíóú-]+", fragmento.lower()) if p not in PALABRAS_VACIAS)
        if terminos:
            lineas.append({"texto_original": f"{m.group(1)} {fragmento}", "cantidad": cantidad, "terminos": terminos})

    fecha = None
    m = re.search(r"(\d{4}-\d{2}-\d{2})", texto)
    if m:
        fecha = m.group(1)
    else:
        m = re.search(r"\b(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")(?:\s+de\s+(\d{4}))?", texto, re.IGNORECASE)
        if m:
            hoy = date.today()
            anio = int(m.group(3)) if m.group(3) else hoy.year
            candidata = date(anio, MESES[m.group(2).lower()], int(m.group(1)))
            if not m.group(3) and candidata < hoy:
                candidata = date(anio + 1, candidata.month, candidata.day)
            fecha = candidata.isoformat()

    referencia = None
    m = re.search(r"referencia[^:\n]*:\s*([A-Za-z0-9/-]+)", texto, re.IGNORECASE)
    if m:
        referencia = m.group(1)

    dudas: list[str] = []
    if re.search(r"lo de siempre|como siempre|unas cuantas|varias", texto, re.IGNORECASE):
        dudas.append("La petición contiene cantidades o artículos indeterminados («lo de siempre», «unas cuantas»)")
    return {"cliente_texto": cliente_texto, "lineas": lineas, "fecha_entrega": fecha, "referencia_cliente": referencia, "dudas": dudas}


def _componer_pedido(
    peticion: dict[str, Any],
    buscadas_clientes: list[dict[str, Any]],
    buscadas_articulos: list[dict[str, Any]],
    resultados: dict[str, Any],
) -> dict[str, Any]:
    dudas = list(peticion["dudas"])
    clientes = resultados.get(buscadas_clientes[0]["call_id"]) or []
    numero_cliente = nombre_cliente = None
    if isinstance(clientes, list) and len(clientes) == 1:
        numero_cliente, nombre_cliente = clientes[0]["number"], clientes[0]["displayName"]
    elif isinstance(clientes, list) and len(clientes) > 1:
        exactos = [c for c in clientes if c["displayName"].lower() == peticion["cliente_texto"].lower()]
        if len(exactos) == 1:
            numero_cliente, nombre_cliente = exactos[0]["number"], exactos[0]["displayName"]
        else:
            dudas.append(f"Varios clientes coinciden con '{peticion['cliente_texto']}': " + ", ".join(c["displayName"] for c in clientes))
    else:
        dudas.append(f"No se encontró ningún cliente para '{peticion['cliente_texto']}'")

    lineas_salida = []
    for linea, llamada in zip(peticion["lineas"], buscadas_articulos, strict=False):
        articulos = resultados.get(llamada["call_id"]) or []
        numero = descripcion = duda = None
        if isinstance(articulos, list) and articulos:
            terminos = linea["terminos"].lower().split()
            exactos = [a for a in articulos if all(t in f"{a['number']} {a['displayName']}".lower() for t in terminos)]
            candidatos = exactos or articulos
            if len(candidatos) == 1:
                numero, descripcion = candidatos[0]["number"], candidatos[0]["displayName"]
            else:
                duda = "Varios artículos posibles: " + ", ".join(f"{a['number']} {a['displayName']}" for a in candidatos[:5])
        else:
            duda = "No se encontró ningún artículo con esa descripción"
        lineas_salida.append(
            {
                "texto_original": linea["texto_original"],
                "numero_articulo": numero,
                "descripcion_articulo": descripcion,
                "cantidad": linea["cantidad"],
                "duda": duda,
            }
        )
    resumen = f"{nombre_cliente or peticion['cliente_texto']} pide {len(lineas_salida)} línea(s)"
    if peticion["fecha_entrega"]:
        resumen += f" para el {peticion['fecha_entrega']}"
    return {
        "cliente_texto": peticion["cliente_texto"],
        "numero_cliente": numero_cliente,
        "nombre_cliente": nombre_cliente,
        "lineas": lineas_salida,
        "fecha_entrega": peticion["fecha_entrega"],
        "referencia_cliente": peticion["referencia_cliente"],
        "dudas": dudas,
        "resumen": resumen,
    }


def _redactar(resumen: str) -> str:
    if "creado" in resumen.lower() and "no se ha creado" not in resumen.lower():
        cuerpo = "Hemos registrado su pedido con los datos indicados a continuación. Les avisaremos en cuanto salga del almacén."
    elif "rechaz" in resumen.lower():
        cuerpo = "Lamentablemente no hemos podido tramitar su pedido por los motivos que se indican a continuación. Quedamos a su disposición para resolverlo."
    else:
        cuerpo = "Hemos recibido su petición y necesitamos aclarar algunos datos antes de tramitarla. Les agradeceríamos que nos confirmaran lo siguiente."
    return f"Estimado cliente:\n\n{cuerpo}\n\n{resumen.strip()}\n\nUn saludo,\nDepartamento comercial"


def _resumir_creacion(resultado: Any) -> str:
    if isinstance(resultado, dict) and resultado.get("number"):
        return f"Pedido {resultado['number']} creado para {resultado.get('customerName', '')} por {euros(resultado.get('totalAmountExcludingTax', 0))} sin impuestos."
    return f"No se ha creado el pedido: {resultado}"


def _respuesta_llamada(nombre: str, argumentos: dict[str, Any], texto_entrada: str) -> ChatResponse:
    _contador["llamadas"] += 1
    return ChatResponse(
        messages=[Message("assistant", [Content.from_function_call(call_id=f"sim-{_contador['llamadas']}", name=nombre, arguments=json.dumps(argumentos, ensure_ascii=False))])],
        usage_details=_uso(texto_entrada, 24),
    )


def _respuesta_texto(texto: str, texto_entrada: str) -> ChatResponse:
    return ChatResponse(messages=[Message("assistant", [texto])], usage_details=_uso(texto_entrada, len(texto) // 4 + 1))


def _uso(texto_entrada: str, salida: int) -> UsageDetails:
    """Tokens aproximados (4 caracteres por token) para que el contador de coste tenga datos."""
    entrada = len(texto_entrada) // 4 + 50
    return UsageDetails(input_token_count=entrada, output_token_count=salida, total_token_count=entrada + salida)


_contador = {"llamadas": 0}
