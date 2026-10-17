import pytest

from agente_pedidos.bc import ClienteDemo, ErrorBC


@pytest.mark.asyncio
async def test_busquedas_basicas():
    bc = ClienteDemo()
    assert (await bc.buscar_clientes("alpine"))[0]["number"] == "40000"
    assert (await bc.buscar_clientes("40000"))[0]["displayName"] == "Alpine Ski House"
    assert any(a["number"] == "1896-S" for a in await bc.buscar_articulos("athens desk"))
    assert await bc.buscar_articulos("") == []


@pytest.mark.asyncio
async def test_crear_pedido_y_errores():
    bc = ClienteDemo()
    pedido = await bc.crear_pedido_venta("40000", [{"numero_articulo": "1896-S", "cantidad": 2}], referencia_externa="MAIL-1")
    assert pedido["number"].startswith("S-ORD")
    assert pedido["totalAmountExcludingTax"] == pytest.approx(2 * 1000.80)
    assert len(bc.pedidos) == 1
    with pytest.raises(ErrorBC):
        await bc.crear_pedido_venta("50000", [{"numero_articulo": "1896-S", "cantidad": 1}])
    with pytest.raises(ErrorBC):
        await bc.crear_pedido_venta("40000", [])
