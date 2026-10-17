"""DevUI descubre carpetas con ``agent.py`` que definan una variable ``agent``.

Arranque (DevUI está en beta y no es para producción):
    PYTHONPATH=src devui ./devui --no-auth
"""

from agente_pedidos.agentes import crear_agente_interprete
from agente_pedidos.bc import ClienteDemo
from agente_pedidos.middleware import AuditoriaHerramientas

agent = crear_agente_interprete(ClienteDemo(), middleware=[AuditoriaHerramientas("auditoria-devui.jsonl")])
