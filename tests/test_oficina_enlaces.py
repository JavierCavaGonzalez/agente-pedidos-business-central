"""Oficina: enlaces profundos a Business Central (sin red)."""

from __future__ import annotations

from ui.backend import business_central as bc

API = {"BC_MODO": "api", "BC_TENANT_ID": "00000000-1111-2222-3333-444444444444", "BC_ENVIRONMENT": "TEST29", "BC_COMPANY_NAME": "CRONUS ES"}


def test_enlace_de_un_pedido_abre_la_ficha_42_filtrada_por_numero_y_codificada():
    assert bc.enlace_pedido("101023", API) == (
        "https://businesscentral.dynamics.com/00000000-1111-2222-3333-444444444444/TEST29"
        "?company=CRONUS%20ES&page=42&filter=%27No.%27%20IS%20%27101023%27"
    )


def test_en_simulacion_no_hay_enlace():
    assert bc.enlace_pedido("S-ORD101001", {**API, "BC_MODO": "demo"}) is None
    assert bc.enlace_inicio({"BC_MODO": "demo"}) is None
    assert bc.descripcion({"BC_MODO": "demo"})["entorno"] == "Simulación"


def test_sin_tenant_o_sin_numero_no_hay_enlace_y_sin_empresa_se_omite_el_parametro():
    assert bc.enlace_pedido("101023", {**API, "BC_TENANT_ID": ""}) is None
    assert bc.enlace_pedido(None, API) is None
    sin_empresa = {k: v for k, v in API.items() if k != "BC_COMPANY_NAME"}
    assert bc.enlace_pedido("1", sin_empresa).endswith("/TEST29?page=42&filter=%27No.%27%20IS%20%271%27")


def test_la_descripcion_del_erp_no_lleva_credenciales():
    datos = bc.descripcion({**API, "BC_CLIENT_SECRET": "no-debe-salir", "BC_CLIENT_ID": "tampoco"})
    assert (datos["modo"], datos["entorno"], datos["empresa"]) == ("api", "TEST29", "CRONUS ES")
    assert "no-debe-salir" not in str(datos) and "tampoco" not in str(datos)
