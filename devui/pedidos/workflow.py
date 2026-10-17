"""DevUI descubre carpetas con ``workflow.py`` que definan una variable ``workflow``.

Los checkpoints se guardan en ./checkpoints-devui.
"""

from agente_pedidos.bc import ClienteDemo
from agente_pedidos.politicas import Politica
from agente_pedidos.workflow import construir_workflow, crear_storage

workflow = construir_workflow(ClienteDemo(), Politica(), crear_storage("checkpoints-devui")).workflow
