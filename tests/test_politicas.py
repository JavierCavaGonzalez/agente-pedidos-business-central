"""Las reglas deterministas se prueban sin ningún modelo de IA."""

import pytest

from agente_pedidos.bc import ClienteDemo
from agente_pedidos.esquemas import LineaInterpretada, PedidoInterpretado
from agente_pedidos.politicas import Politica, validar_pedido


def pedido_base(**cambios):
    datos = dict(
        cliente_texto="Alpine Ski House",
        numero_cliente="40000",
        nombre_cliente="Alpine Ski House",
        lineas=[
            LineaInterpretada(texto_original="2 mesas ATHENS", numero_articulo="1896-S", cantidad=2),
            LineaInterpretada(texto_original="4 lámparas AMSTERDAM", numero_articulo="1928-S", cantidad=4),
        ],
        resumen="Alpine pide 2 mesas y 4 lámparas",
    )
    datos.update(cambios)
    return PedidoInterpretado(**datos)


@pytest.mark.asyncio
async def test_pedido_correcto_calcula_total_y_pide_aprobacion_por_politica():
    bc = ClienteDemo()
    resultado = await validar_pedido(pedido_base(), bc, Politica(aprobar_siempre=True))
    assert resultado.apto_para_crear
    assert resultado.total == pytest.approx(2 * 1000.80 + 4 * 55.90)
    assert resultado.requiere_aprobacion
    assert any("aprobación humana" in m for m in resultado.motivos_aprobacion)


@pytest.mark.asyncio
async def test_pedido_pequeno_sin_aprobar_siempre_no_requiere_aprobacion():
    bc = ClienteDemo()
    politica = Politica(aprobar_siempre=False, umbral_aprobacion=5000)
    resultado = await validar_pedido(pedido_base(), bc, politica)
    assert resultado.apto_para_crear
    assert not resultado.requiere_aprobacion


@pytest.mark.asyncio
async def test_importe_sobre_umbral_requiere_aprobacion():
    bc = ClienteDemo()
    pedido = pedido_base(lineas=[LineaInterpretada(texto_original="5 mesas", numero_articulo="1896-S", cantidad=5)])
    resultado = await validar_pedido(pedido, bc, Politica(aprobar_siempre=False, umbral_aprobacion=3000))
    assert resultado.total == pytest.approx(5 * 1000.80)
    assert resultado.requiere_aprobacion
    assert any("umbral" in m for m in resultado.motivos_aprobacion)


@pytest.mark.asyncio
async def test_cliente_bloqueado_es_error():
    bc = ClienteDemo()
    pedido = pedido_base(numero_cliente="50000", nombre_cliente="Relecloud")
    resultado = await validar_pedido(pedido, bc, Politica())
    assert not resultado.apto_para_crear
    assert any("bloqueado" in e for e in resultado.errores)


@pytest.mark.asyncio
async def test_sin_existencias_bloquea_salvo_que_la_politica_lo_permita():
    bc = ClienteDemo()
    pedido = pedido_base(lineas=[LineaInterpretada(texto_original="2 sillas ROME", numero_articulo="1960-S", cantidad=2)])
    estricta = await validar_pedido(pedido, bc, Politica(permitir_sin_existencias=False))
    assert not estricta.apto_para_crear
    laxa = await validar_pedido(pedido, bc, Politica(permitir_sin_existencias=True))
    assert laxa.apto_para_crear
    assert laxa.requiere_aprobacion


@pytest.mark.asyncio
async def test_duda_del_interprete_obliga_a_revision():
    bc = ClienteDemo()
    pedido = pedido_base(dudas=["No está claro si quiere entrega el viernes 24 o el 31"])
    resultado = await validar_pedido(pedido, bc, Politica(aprobar_siempre=False, umbral_aprobacion=100000))
    assert resultado.requiere_aprobacion
    assert resultado.apto_para_crear


@pytest.mark.asyncio
async def test_articulo_no_identificado_es_error():
    bc = ClienteDemo()
    pedido = pedido_base(lineas=[LineaInterpretada(texto_original="una cosa", numero_articulo=None, cantidad=1, duda="No sé qué es")])
    resultado = await validar_pedido(pedido, bc, Politica())
    assert not resultado.apto_para_crear
