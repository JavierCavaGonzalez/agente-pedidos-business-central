# Para construirlo con un asistente de programación: prompt listo para pegar

Este proyecto se puede regenerar (o adaptar a otro proceso del ERP) pidiéndoselo a un asistente de programación. El prompt siguiente vale para cualquier asistente que pueda ejecutar comandos. Cópialo entero en una carpeta vacía.

Consejos antes de pegar:

- El asistente debe **instalar la versión fijada y verificar la API real** antes de escribir código: la API de Agent Framework cambió por completo entre la beta de 2025 y la 1.x (y sigue cambiando cada semana). El prompt incluye los comandos de verificación.
- Pídele **modo demo obligatorio** (sin credenciales) y **pruebas**: es lo que permite comprobar que el esqueleto funciona antes de tocar un sandbox real.
- Si cambias el escenario (compras, cobros…), cambia solo los apartados 2 y 3 del prompt.

---

```text
Quiero que construyas un ejemplo pequeño pero completo de un agente de IA sobre Dynamics 365 Business Central con Microsoft Agent Framework (Python). Debe funcionar sin ninguna credencial en modo demo y conectarse a un sandbox real por variables de entorno. Trabaja en esta carpeta vacía. Lee todo el prompt antes de empezar y no me pidas confirmación salvo bloqueo real.

1. VERSIÓN Y API REAL (hazlo primero)
- Crea un entorno virtual e instala exactamente: agent-framework==1.22.0, httpx, pydantic>=2, pytest, pytest-asyncio, mcp. Si 1.22.0 no existe ya, instala la última estable e indícame qué versión has usado.
- Antes de escribir código, verifica los nombres reales de la API instalada con introspección, por ejemplo:
  python -c "import agent_framework as af; print(af.__version__); print([n for n in dir(af) if not n.startswith('_')])"
  python -c "import inspect, agent_framework as af; print(inspect.signature(af.Agent.__init__)); print(inspect.signature(af.WorkflowBuilder.__init__)); print(inspect.signature(af.tool))"
  python -c "import inspect, agent_framework as af; print(inspect.signature(af.WorkflowContext.request_info)); print(inspect.signature(af.Workflow.run))"
  y lee los docstrings de Agent, tool, WorkflowBuilder, Executor, handler, response_handler, FileCheckpointStorage, register_checkpoint_type, FunctionMiddleware, ChatMiddleware, MCPStdioTool y agent_framework.observability.configure_otel_providers.
- Usa SOLO nombres que existan en la versión instalada. En 1.22.0 son: Agent, AgentSession (agent.create_session()), agent.run(mensajes, session=, options=, stream=), AgentResponse (.text, .value, .usage_details, .user_input_requests), @tool(name=, description=, approval_mode="always_require"|"never_require"), Message, Content, WorkflowBuilder(name=, description=, start_executor=, checkpoint_storage=).add_edge(a, b, condition=).add_switch_case_edge_group(origen, [Case(condition=, target=), Default(target=)]).build(), Executor(id=...) con métodos @handler(self, mensaje: Tipo, ctx: WorkflowContext[TipoSalida]) y @response_handler(self, peticion, respuesta, ctx), ctx.send_message(), ctx.yield_output(), ctx.request_info(datos, TipoRespuesta), workflow.run(entrada, stream=True) / workflow.run(responses={id: respuesta}) / workflow.run(checkpoint_id=..., responses=...), eventos WorkflowEvent con .type en {"executor_invoked", "request_info", "output", "status"}, workflow.resolve_pause_checkpoint_id([request_id]), FileCheckpointStorage(storage_path=), register_checkpoint_type(Clase), WorkflowViz(wf).to_mermaid(), FunctionMiddleware/ChatMiddleware con process(context, call_next) (bloquear = no llamar a call_next y asignar context.result), FunctionInvocationContext (.function.name, .arguments, .result), ChatContext (.result), MCPStdioTool(name=, command=, args=, env=, allowed_tools=), agent_framework.openai.OpenAIChatClient (OpenAI y Azure OpenAI), agent_framework.foundry.FoundryChatClient, agent_framework.observability.configure_otel_providers.
- NO uses nombres de la beta de 2025: ChatAgent, AgentThread, run_stream, @ai_function, ChatMessage, TextContent, AzureOpenAIChatClient, AzureAIAgentClient, RequestInfoExecutor, WorkflowOutputEvent, set_start_executor, with_checkpointing, setup_observability. Si alguna guía o ejemplo los usa, está desactualizada.

2. ESCENARIO
Agente de pedidos de venta por correo: lee el texto de un correo de un cliente, identifica cliente y artículos en Business Central, valida el pedido con reglas de código (cliente no bloqueado, artículos existentes y no bloqueados, existencias suficientes, límite de crédito, importe) y, si el importe supera un umbral o hay dudas, pide aprobación a una persona antes de crear el pedido. Reparto de decisiones que debe quedar explícito en el código y en el README:
- Decide la IA: interpretar el correo (cliente, artículos, cantidades, fecha, referencia) y redactar la respuesta al cliente.
- Decide el código: validez, importe, si hace falta aprobación, la ruta del workflow y la escritura en el ERP.
- Decide la persona: aprobar o rechazar los pedidos que exigen aprobación.

3. PIEZAS QUE DEBEN APARECER (todas, cada una en su archivo)
- src/agente_pedidos/modelo.py: crear_cliente_modelo() que elige por MODELO_PROVEEDOR entre "simulado" (por defecto), "openai", "azure_openai" y "foundry". El cliente simulado hereda de BaseChatClient con las capas FunctionInvocationLayer, ChatMiddlewareLayer y ChatTelemetryLayer (mira cómo lo hacen los tests del propio paquete) e implementa _inner_get_response imitando a un modelo que llama a buscar_clientes, luego a buscar_articulos por cada línea y al final devuelve el JSON del pedido estructurado. Debe funcionar sin red.
- src/agente_pedidos/bc/: interfaz ClienteBC (buscar_clientes, obtener_cliente, buscar_articulos, obtener_articulo, crear_pedido_venta, cerrar), ClienteDemo (JSON en memoria con 5 clientes y 12 artículos, uno bloqueado, uno sin stock) y ClienteApiV2 (API v2.0 real: token OAuth client credentials en login.microsoftonline.com/<tenant>/oauth2/v2.0/token con scope https://api.businesscentral.dynamics.com/.default; GET companies, GET customers e items con $filter OData, POST salesOrders y POST salesOrderLines; variables BC_TENANT_ID, BC_ENVIRONMENT, BC_CLIENT_ID, BC_CLIENT_SECRET, BC_COMPANY_NAME o BC_COMPANY_ID).
- src/agente_pedidos/esquemas.py: modelos Pydantic PedidoInterpretado (con líneas, dudas y resumen), PedidoValidado (errores, avisos, requiere_aprobacion, motivos, apto_para_crear, resumen_para_humano()), DecisionHumana, ResultadoPedido.
- src/agente_pedidos/politicas.py: Politica (umbral, aprobar_siempre, permitir_sin_existencias, max_lineas, clientes_vetados; desde_entorno()) y validar_pedido(pedido, bc, politica) async y determinista.
- src/agente_pedidos/herramientas.py: cuatro @tool de lectura y una de escritura crear_pedido_venta con approval_mode="always_require"; parámetros con Annotated[..., Field(description=...)]; errores del ERP devueltos como {"error": ...}.
- src/agente_pedidos/middleware.py: AuditoriaHerramientas (FunctionMiddleware que escribe JSONL con instante, herramienta, argumentos, resumen del resultado, duración), SoloLectura (FunctionMiddleware que bloquea herramientas cuyo nombre empieza por crear_/modificar_/borrar_ si AGENTE_SOLO_LECTURA=1) y PresupuestoLlamadas (ChatMiddleware que corta tras N llamadas al modelo).
- prompts/interprete.md y prompts/redactor.md: instrucciones en español.
- src/agente_pedidos/agentes.py: crear_agente_interprete (lectura + salida estructurada), crear_agente_redactor, crear_agente_asistente (lectura + escritura con aprobación).
- src/agente_pedidos/workflow.py: nodos Executor interpretar (IA, options={"response_format": PedidoInterpretado}), validar (código), aprobacion_humana (ctx.request_info(SolicitudAprobacion, DecisionHumana) + @response_handler), crear_pedido (código, escribe en el ERP), rechazar, redactar (IA, yield_output); aristas: interpretar→validar; switch-case desde validar (no apto→rechazar; requiere aprobación→aprobacion_humana; por defecto→crear_pedido); aprobacion_humana→crear_pedido si aprobado, →rechazar si no; crear_pedido y rechazar→redactar. FileCheckpointStorage y register_checkpoint_type para todos los tipos propios. Función construir_workflow(bc, politica, storage, middleware) y dibujar_mermaid().
- src/agente_pedidos/observabilidad.py: configurar_observabilidad() (configure_otel_providers si hay OTEL_EXPORTER_OTLP_ENDPOINT o ENABLE_CONSOLE_EXPORTERS=1; Azure Monitor si hay APPLICATIONINSIGHTS_CONNECTION_STRING) y ContadorCoste (suma usage_details y convierte a euros con precios por millón de tokens desde variables de entorno).
- src/agente_pedidos/mcp_server.py: servidor MCP opcional (FastMCP, stdio) con las cuatro lecturas y crear_herramienta_mcp() que devuelve un MCPStdioTool (pásale env={"PYTHONPATH": "src"} porque el SDK de MCP arranca el subproceso con un entorno mínimo).
- src/agente_pedidos/cli.py y __main__.py: comandos demo, procesar <correo> [--aprobar preguntar|si|no|pendiente], pendientes, reanudar --checkpoint ID --decision si|no, chat "<mensaje>", grafo. Que lea .env sin dependencias externas.
- devui/: dos carpetas con agent.py (variable agent) y workflow.py (variable workflow) para DevUI.
- ejemplos/correos/: cuatro correos (pequeño que se crea solo; grande que exige aprobación; cliente bloqueado; artículo ambiguo).
- tests/: pytest sin red: reglas, cliente demo, los cuatro recorridos del workflow incluida la reanudación desde checkpoint en una instancia nueva, aprobación y rechazo a nivel de agente, middleware de solo lectura y presupuesto, e integración MCP (importorskip("mcp")).
- .env.example (todas las variables, sin valores secretos), .gitignore (.env, checkpoints/, auditoria*.jsonl), LICENSE MIT, requirements.txt y pyproject.toml con agent-framework==1.22.0 fijado.
- README.md en español, paso a paso: qué muestra (tabla pieza → archivo), escenarios y por qué este, diagrama Mermaid del workflow, requisitos, instalación y primera ejecución en modo demo, cada comando, cómo conectar un modelo real, cómo conectar un sandbox de Business Central (registro de aplicación en Entra con permiso de aplicación API.ReadWrite.All, página "Microsoft Entra applications" en BC con conjuntos de permisos mínimos y nunca SUPER), observabilidad (consola, Aspire Dashboard, Application Insights), DevUI y MCP, pruebas, estructura con explicación de cada archivo, limitaciones y licencia.

4. REGLAS
- Sin credenciales en el código ni en el repositorio: todo por variables de entorno y .env.example.
- Modo demo por defecto: `python -m agente_pedidos demo` debe funcionar recién clonado sin configurar nada.
- Código en español (nombres, comentarios, mensajes), salvo los nombres de la API del framework y de la API de Business Central.
- Comenta en cada archivo qué pieza del esqueleto es y qué decide (IA, código o persona).
- Ejecuta las pruebas y la demo antes de terminar, y pega la salida real de `python -m agente_pedidos demo` en el README o en docs/.
- Si algo del framework no existe con el nombre que esperabas, no lo inventes: busca el nombre real con introspección y dímelo.
```
