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


async def test_con_bc_demo_pedidos_varios_procesos_comparten_el_erp_simulado(tmp_path, monkeypatch):
    from agente_pedidos.bc import PedidoDuplicado

    monkeypatch.setenv("BC_DEMO_PEDIDOS", str(tmp_path / "pedidos.json"))
    primero = await ClienteDemo().crear_pedido_venta("10000", [{"numero_articulo": "1928-S", "cantidad": 1}], referencia_externa="A-1")
    # Otro «proceso» (otra instancia que lee el fichero): el número sigue y el duplicado se detecta.
    otro = ClienteDemo()
    segundo = await otro.crear_pedido_venta("10000", [{"numero_articulo": "1928-S", "cantidad": 1}], referencia_externa="A-2")
    assert int(segundo["number"].removeprefix("S-ORD")) == int(primero["number"].removeprefix("S-ORD")) + 1
    with pytest.raises(PedidoDuplicado):
        await ClienteDemo().crear_pedido_venta("10000", [{"numero_articulo": "1928-S", "cantidad": 1}], referencia_externa="A-1")
