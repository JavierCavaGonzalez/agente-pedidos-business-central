"""Formato español de las cifras que leen las personas (CLI, políticas, respuestas y oficina).

5875.6 -> «5.875,60 €»: punto de miles, coma decimal y símbolo de euro detrás, redondeando
«medio hacia arriba» igual que la CLI, el backend y el navegador (``redondear_eur``).
"""

from __future__ import annotations

from .observabilidad import redondear_eur


def numero_es(valor: float, decimales: int = 2) -> str:
    """5875.6 -> «5.875,60»."""
    return f"{redondear_eur(valor, decimales):,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def euros(importe: float | None, decimales: int = 2) -> str:
    """5875.6 -> «5.875,60 €»; ``None`` -> «—»."""
    return "—" if importe is None else f"{numero_es(importe, decimales)} €"
