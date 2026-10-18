"""Reglas deterministas del negocio: aquí decide el código, no la IA.

Siguiendo la «delegación basada en reglas» del libro (cap. 2.5.2), las condiciones que
obligan a que una persona apruebe el pedido son explícitas, auditables y se prueban con
tests sin necesidad de ningún modelo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .bc.base import ClienteBC
from .esquemas import LineaValidada, PedidoInterpretado, PedidoValidado
from .formato import euros


@dataclass
class Politica:
    """Los umbrales son datos de configuración, no texto en un prompt: el modelo no puede cambiarlos."""

    umbral_aprobacion: float = 3000.0  # a partir de este importe aprueba siempre una persona
    aprobar_siempre: bool = False  # si es True, toda escritura en el ERP pasa por una persona
    permitir_sin_existencias: bool = False  # si es False, una línea sin stock suficiente bloquea el pedido
    max_lineas: int = 20
    clientes_vetados: set[str] = field(default_factory=set)  # números de cliente que nunca se procesan automáticamente

    @classmethod
    def desde_entorno(cls) -> "Politica":
        """Lee la política de variables de entorno (ver .env.example)."""
        vetados = {c.strip() for c in os.environ.get("POLITICA_CLIENTES_VETADOS", "").split(",") if c.strip()}
        return cls(
            umbral_aprobacion=float(os.environ.get("POLITICA_UMBRAL_APROBACION", "3000")),
            aprobar_siempre=os.environ.get("POLITICA_APROBAR_SIEMPRE", "0") == "1",
            permitir_sin_existencias=os.environ.get("POLITICA_PERMITIR_SIN_EXISTENCIAS", "0") == "1",
            max_lineas=int(os.environ.get("POLITICA_MAX_LINEAS", "20")),
            clientes_vetados=vetados,
        )


async def validar_pedido(pedido: PedidoInterpretado, bc: ClienteBC, politica: Politica) -> PedidoValidado:
    """Comprueba el pedido interpretado contra el ERP y la política y decide la ruta."""
    resultado = PedidoValidado(
        numero_cliente=pedido.numero_cliente,
        nombre_cliente=pedido.nombre_cliente,
        fecha_entrega=pedido.fecha_entrega,
        referencia_cliente=pedido.referencia_cliente,
    )

    # 1. Cliente
    cliente = await bc.obtener_cliente(pedido.numero_cliente) if pedido.numero_cliente else None
    if cliente is None:
        resultado.errores.append(f"No se ha identificado el cliente ('{pedido.cliente_texto}')")
    else:
        resultado.nombre_cliente = cliente.get("displayName", resultado.nombre_cliente)
        bloqueado = str(cliente.get("blocked", " ")).strip()
        if bloqueado:
            resultado.errores.append(f"El cliente {cliente['number']} está bloqueado ({bloqueado})")
        if cliente["number"] in politica.clientes_vetados:
            resultado.motivos_aprobacion.append("Cliente marcado para revisión manual")

    # 2. Líneas
    if not pedido.lineas:
        resultado.errores.append("La petición no contiene líneas de pedido")
    if len(pedido.lineas) > politica.max_lineas:
        resultado.errores.append(f"Demasiadas líneas ({len(pedido.lineas)} > {politica.max_lineas})")

    for linea in pedido.lineas:
        if linea.duda:
            resultado.avisos.append(f"Línea '{linea.texto_original}': {linea.duda}")
        if not linea.numero_articulo:
            resultado.errores.append(f"Línea '{linea.texto_original}': artículo no identificado")
            continue
        articulo = await bc.obtener_articulo(linea.numero_articulo)
        if articulo is None:
            resultado.errores.append(f"El artículo {linea.numero_articulo} no existe en Business Central")
            continue
        if articulo.get("blocked"):
            resultado.errores.append(f"El artículo {articulo['number']} está bloqueado")
            continue
        if linea.cantidad <= 0:
            resultado.errores.append(f"Cantidad no válida en '{linea.texto_original}'")
            continue
        existencias = float(articulo.get("inventory", 0) or 0)
        precio = float(articulo.get("unitPrice", 0) or 0)
        avisos_linea: list[str] = []
        if linea.cantidad > existencias:
            texto = f"Existencias insuficientes de {articulo['number']} (pedidas {linea.cantidad:g}, hay {existencias:g})"
            if politica.permitir_sin_existencias:
                avisos_linea.append(texto)
                resultado.motivos_aprobacion.append(texto)
            else:
                resultado.errores.append(texto)
                continue
        resultado.lineas.append(
            LineaValidada(
                numero_articulo=articulo["number"],
                descripcion=articulo.get("displayName", ""),
                cantidad=linea.cantidad,
                precio_unitario=precio,
                importe=round(linea.cantidad * precio, 2),
                existencias=existencias,
                avisos=avisos_linea,
            )
        )

    resultado.total = round(sum(l.importe for l in resultado.lineas), 2)

    # 3. Crédito (solo si el ERP informa de un límite)
    if cliente is not None:
        limite = float(cliente.get("creditLimit", 0) or 0)
        saldo = float(cliente.get("balanceDue", 0) or 0)
        if limite > 0 and saldo + resultado.total > limite:
            motivo = f"Supera el límite de crédito ({euros(saldo)} pendiente + {euros(resultado.total)} > {euros(limite)})"
            resultado.avisos.append(motivo)
            resultado.motivos_aprobacion.append(motivo)

    # 4. Dudas del intérprete: nunca se crea un pedido con dudas sin que alguien las vea
    for duda in pedido.dudas:
        resultado.avisos.append(duda)
        resultado.motivos_aprobacion.append("Duda del intérprete: " + duda)

    # 5. Ruta: ¿aprueba una persona?
    if politica.aprobar_siempre:
        resultado.motivos_aprobacion.append("La política exige aprobación humana para toda escritura en el ERP")
    if resultado.total >= politica.umbral_aprobacion:
        resultado.motivos_aprobacion.append(
            f"El importe {euros(resultado.total)} supera el umbral de {euros(politica.umbral_aprobacion)}"
        )
    resultado.requiere_aprobacion = bool(resultado.motivos_aprobacion) or bool(resultado.errores)
    resultado.apto_para_crear = not resultado.errores and bool(resultado.lineas)
    return resultado
