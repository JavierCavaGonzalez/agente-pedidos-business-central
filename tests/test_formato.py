"""Formato español de las cifras: el mismo en la CLI, las políticas, las respuestas y la oficina."""

from __future__ import annotations

import pytest

from agente_pedidos.bc import ClienteDemo
from agente_pedidos.esquemas import LineaInterpretada, PedidoInterpretado
from agente_pedidos.formato import euros, numero_es
from agente_pedidos.politicas import Politica, validar_pedido


def test_euros_con_punto_de_miles_coma_decimal_y_simbolo_detras():
    assert euros(5875.6) == "5.875,60 €"
    assert euros(3000) == "3.000,00 €"
    assert euros(1234567.891) == "1.234.567,89 €"
    assert euros(0.00375, 4) == "0,0038 €"  # medio hacia arriba, como la oficina
    assert euros(None) == "—" and numero_es(559) == "559,00"


@pytest.mark.asyncio
async def test_el_motivo_de_la_politica_lleva_los_importes_en_formato_espanol():
    pedido = PedidoInterpretado(
        cliente_texto="Adatum",
        numero_cliente="10000",
        resumen="Sillas y mesas",
        lineas=[
            LineaInterpretada(texto_original="20 sillas PARIS", numero_articulo="1900-S", cantidad=20),
            LineaInterpretada(texto_original="2 mesas ATHENS", numero_articulo="1896-S", cantidad=2),
        ],
    )
    resultado = await validar_pedido(pedido, ClienteDemo(), Politica(aprobar_siempre=False, umbral_aprobacion=3000))
    assert "El importe 5.875,60 € supera el umbral de 3.000,00 €" in resultado.motivos_aprobacion
    assert "Total sin impuestos: 5.875,60 €" in resultado.resumen_para_humano()
