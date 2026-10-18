"""Esquemas de datos (Pydantic) que viajan entre los pasos del workflow.

La salida estructurada es, según Dibia (cap. 4.5), «la clave de los agentes fiables»:
el modelo no devuelve texto libre que haya que interpretar, sino un objeto con campos
tipados que el código puede validar.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LineaInterpretada(BaseModel):
    texto_original: str = Field(description="Fragmento literal de la petición que describe esta línea")
    numero_articulo: str | None = Field(
        default=None,
        description="Número de artículo de Business Central resuelto con la herramienta buscar_articulos; null si no se encontró o hay varios candidatos",
    )
    descripcion_articulo: str | None = Field(default=None, description="Descripción del artículo según Business Central")
    cantidad: float = Field(description="Cantidad pedida, siempre un número mayor que cero")
    duda: str | None = Field(default=None, description="Explicación si la línea es ambigua o no se pudo resolver")


class PedidoInterpretado(BaseModel):
    """Lo que el agente intérprete entiende de la petición. Solo interpreta: no decide nada."""

    cliente_texto: str = Field(description="Cómo se identifica el cliente en la petición (nombre, firma, dominio del correo)")
    numero_cliente: str | None = Field(default=None, description="Número de cliente en Business Central resuelto con buscar_clientes; null si no hay un único candidato")
    nombre_cliente: str | None = Field(default=None, description="Nombre del cliente según Business Central")
    lineas: list[LineaInterpretada] = Field(default_factory=list)
    fecha_entrega: str | None = Field(default=None, description="Fecha de entrega solicitada en formato AAAA-MM-DD, solo si se indica explícitamente")
    referencia_cliente: str | None = Field(default=None, description="Referencia o número de pedido del cliente si aparece en el texto")
    dudas: list[str] = Field(default_factory=list, description="Dudas que una persona debería resolver antes de crear el pedido")
    resumen: str = Field(description="Una frase que resume la petición")


class LineaValidada(BaseModel):
    numero_articulo: str
    descripcion: str
    cantidad: float
    precio_unitario: float
    importe: float
    existencias: float
    avisos: list[str] = Field(default_factory=list)


class PedidoValidado(BaseModel):
    """Resultado de las reglas deterministas. Aquí decide el código, no el modelo."""

    numero_cliente: str | None = None
    nombre_cliente: str | None = None
    lineas: list[LineaValidada] = Field(default_factory=list)
    total: float = 0.0
    fecha_entrega: str | None = None
    referencia_cliente: str | None = None
    errores: list[str] = Field(default_factory=list, description="Impiden crear el pedido")
    avisos: list[str] = Field(default_factory=list, description="No impiden crearlo, pero una persona debe verlos")
    requiere_aprobacion: bool = True
    motivos_aprobacion: list[str] = Field(default_factory=list)
    apto_para_crear: bool = False

    def resumen_para_humano(self) -> str:
        """Texto que ve la persona que aprueba."""
        partes = [f"Cliente: {self.numero_cliente or '?'} {self.nombre_cliente or ''}".strip()]
        for linea in self.lineas:
            partes.append(
                f"  - {linea.cantidad:g} x {linea.numero_articulo} {linea.descripcion} "
                f"a {linea.precio_unitario:.2f} = {linea.importe:.2f} (existencias: {linea.existencias:g})"
            )
        partes.append(f"Total sin impuestos: {self.total:.2f}")
        if self.fecha_entrega:
            partes.append(f"Entrega solicitada: {self.fecha_entrega}")
        for aviso in self.avisos:
            partes.append(f"  AVISO: {aviso}")
        for error in self.errores:
            partes.append(f"  ERROR: {error}")
        if self.motivos_aprobacion:
            partes.append("Motivos por los que se pide aprobación: " + "; ".join(self.motivos_aprobacion))
        return "\n".join(partes)


class DecisionHumana(BaseModel):
    aprobado: bool
    comentario: str = ""
    aprobador: str = ""


class ResultadoPedido(BaseModel):
    creado: bool
    estado: str = ""  # creado | rechazado | denegado: lo que pasó, sin tener que leer el mensaje
    numero_pedido: str | None = None
    total: float = 0.0
    numero_cliente: str | None = None
    nombre_cliente: str | None = None
    mensaje: str = ""
    respuesta_cliente: str = ""
