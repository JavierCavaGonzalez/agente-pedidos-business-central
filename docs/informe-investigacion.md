# Informe de investigación: Agent Framework, Copilot Studio y Foundry para agentes sobre Business Central

*Investigación previa al artículo «Microsoft Agent Framework explicado desde el ERP: qué hay detrás de un agente que toca Business Central» y al ejemplo de este repositorio. Los códigos entre corchetes del artículo ([AF-13], [BC-58]…) remiten a la lista de fuentes del final de este informe.*

18 de octubre de 2026 · Javier Cava

## Alcance, método y criterios de evidencia

Este informe es la investigación previa al artículo sobre Microsoft Agent Framework aplicado a Business Central; todas las fuentes se consultaron el 17 de octubre de 2026 salvo indicación en contra. El ejemplo práctico que acompaña al artículo está publicado en [agente-pedidos-business-central](https://github.com/JavierCavaGonzalez/agente-pedidos-business-central) (etiqueta `v0.1.0`) y se ejecutó el 18 de octubre de 2026 contra un sandbox real de Business Central; el apartado «Verificación del ejemplo contra un sandbox real» recoge lo que enseñó.

- Pregunta central: ¿es Microsoft Agent Framework la mejor manera de crear agentes cuando se necesita control total sobre un agente que actúa sobre un ERP como Business Central, o lo son Copilot Studio o Microsoft Foundry, o una combinación de ellos?
- Base conceptual: el libro *Designing Multi-Agent Systems* (Victor Dibia), leído completo, incluidos epílogo y glosario; se cita por capítulo y sección y no se le atribuye nada que no esté en él.
- Fuentes: primero las oficiales (Microsoft Learn, repositorio microsoft/agent-framework, blogs oficiales de Microsoft, notas de versión y planes de lanzamiento de Business Central); las de terceros solo como complemento y señaladas como tales.
- Estado de cada función: se marca "preview" cuando no tiene disponibilidad general (GA); se indica la fecha de cada hito verificado.
- Método: lectura del libro, siete líneas de investigación (framework, historia SK/AutoGen, Copilot Studio, Foundry y gobernanza, Business Central, protocolos y riesgo, verificación práctica de la API instalando el paquete) y contraste cruzado antes de redactar.
- Lo que no se ha podido verificar se dice como tal en la sección de puntos dudosos.
- Verificación práctica en dos fases: el 17 de octubre, la API del framework 1.22.0 instalada y probada; el 18 de octubre, el ejemplo publicado ejecutado contra un sandbox real de Business Central (TEST29, CRONUS ES) con un modelo real (Azure OpenAI, `gpt-4.1-mini`), con tres pedidos creados y cada fallo documentado en `docs/notas-de-construccion.md` del repositorio.

## Hallazgos: Microsoft Agent Framework

Códigos de fuente: [AF-n] remite a la lista de fuentes del final (apartado Agent Framework); [VER] indica verificación práctica propia: el 17-10-2026 instalando `agent-framework` 1.22.0 en un entorno limpio y ejecutando una prueba de humo (agente con herramienta, aprobación, salida estructurada, workflow con parada y reanudación desde checkpoint); el 18-10-2026, ejecutando el ejemplo publicado (v0.1.0, 56 pruebas) contra un sandbox real de Business Central con Azure OpenAI gpt-4.1-mini.

### Estado, versiones y paquetes

- Qué es: SDK y runtime de código abierto (licencia MIT) para construir agentes y workflows multiagente en Python y .NET, con Go en vista previa; Microsoft lo presenta como "the direct successor" de Semantic Kernel y AutoGen, "created by the same teams" [AF-2][AF-1].
- Cronología verificada: vista previa pública el 1 de octubre de 2025; release candidate el 19 de febrero de 2026; versión 1.0 (GA) el 2 de abril de 2026 (Python `agent-framework` 1.0.0; .NET `Microsoft.Agents.AI` 1.0.0), anunciada el 3 de abril como "the production-ready release: stable APIs, and a commitment to long-term support" [AF-10][AF-3][AF-6].
- Versión vigente a 17-10-2026: Python 1.22.0 (publicada el 15-10-2026) y .NET 1.25.0 (14-10-2026). Las numeraciones son independientes y sale aproximadamente una versión menor por semana [AF-3][AF-4][AF-7].
- Paquetes Python (estado oficial en PACKAGE_STATUS.md): `agent-framework` es un metapaquete que instala `agent-framework-core` 1.22.0, `-openai` 1.17.0 (OpenAI y Azure OpenAI), `-foundry` 1.15.0 (sustituye a `-azure-ai`, que nunca llegó a GA y está marcado como obsoleto), `-orchestrations` 1.3.2 y `-declarative` 1.3.0, todos "released". En beta: `-devui`, `-a2a`, `-copilotstudio`, `-mem0`, `-redis`, `-anthropic`, `-bedrock`, `-gemini`, `-mistral`, `-ollama`, `-foundry-hosting`, `-purview`, `-chatkit`. En alfa: los paquetes `hosting-*` (canales) y los almacenes vectoriales [AF-60][VER].
- Paquetes .NET: `Microsoft.Agents.AI`, `.Abstractions`, `.OpenAI`, `.Workflows`, `.Workflows.Declarative`, `.Anthropic`, `.Harness` y `.GitHub.Copilot` estables en 1.25.0; `.Foundry` en 1.25.0-preview (hubo un 1.5.0 estable en mayo de 2026 y después solo previews: anomalía señalada en dudas); `.Hosting.*` y `.A2A` en preview; `.Mcp` en alfa; `.Purview` en release candidate [AF-7][AF-72][AF-73].
- Cambios que rompen compatibilidad después de la 1.0, incluso en paquetes "released": 1.13.0 (checkpoints), 1.15.0 (atributos de OpenTelemetry) y 1.22.0 (formato de estado persistido no compatible hacia atrás; no mezclar versiones en despliegues graduales) [AF-62]. No hay política pública de soporte a largo plazo con plazos ni hoja de ruta publicada [AF-83][AF-1].
- Consecuencia práctica para quien programe contra el framework hoy: casi todo el material anterior a marzo de 2026 (vídeos, blogs, incluso partes de las guías de migración oficiales) usa nombres que ya no existen. La tabla siguiente recoge los renombrados que he verificado [AF-13][VER].

| Nombre antiguo (beta 2025) | Nombre vigente (1.22.0) |
| --- | --- |
| `ChatAgent` | `Agent` |
| `AgentThread` | `AgentSession` (`agent.create_session()`) |
| `agent.run_stream(...)` | `agent.run(..., stream=True)` |
| `@ai_function` / `AIFunction` | `@tool` / `FunctionTool` |
| `ChatMessage`, `TextContent`, `FunctionCallContent`… | `Message` y `Content` (con campo `type`) |
| `AgentRunResponse` | `AgentResponse` |
| `AzureOpenAIChatClient`, `AzureOpenAIResponsesClient` | `OpenAIChatClient` (sirve OpenAI y Azure OpenAI según variables de entorno o `azure_endpoint`) y `OpenAIChatCompletionClient` |
| `AzureAIAgentClient` / `AzureAIClient` | `FoundryChatClient` (modelo de Foundry) y `FoundryAgent` (agente alojado en Foundry) |
| `setup_observability()`, `ENABLE_OTEL` | `configure_otel_providers()`, `ENABLE_INSTRUMENTATION` |
| `RequestInfoExecutor`, `RequestInfoEvent`, `RequestResponse` | `ctx.request_info(...)` + `@response_handler` + evento `WorkflowEvent` con `type == "request_info"` |
| `WorkflowOutputEvent` | `WorkflowEvent` con `type == "output"` |
| `.set_start_executor()`, `.with_checkpointing()` | argumentos `start_executor=` y `checkpoint_storage=` del constructor `WorkflowBuilder` |
| `HostedMCPTool` | `client.get_mcp_tool(...)` (herramienta MCP alojada en Foundry) |

### Arquitectura: la lista real de componentes (Python 1.22.0, verificada)

El libro describe un agente como modelo + herramientas + memoria dentro de un bucle de ejecución (cap. 1.4 y 4.2). En el framework cada una de esas ideas tiene una pieza concreta:

1. Cliente de modelo (chat client): `OpenAIChatClient` (API Responses; OpenAI y Azure OpenAI), `OpenAIChatCompletionClient`, `FoundryChatClient`, `AnthropicClient`, `OllamaChatClient`, `BedrockChatClient`, `GeminiChatClient`, `MistralChatClient`; en .NET cualquier `IChatClient` de Microsoft.Extensions.AI. Un cliente propio se construye heredando de `BaseChatClient` con las capas `FunctionInvocationLayer`, `ChatMiddlewareLayer` y `ChatTelemetryLayer` (así está hecho el modo simulado del ejemplo) [AF-23][AF-24][VER].
2. Agente: `Agent(client, instructions, name, description, tools, default_options, context_providers, middleware, compaction_strategy)`; `agent.run(mensajes, stream=False, session=None, options=None)` devuelve `AgentResponse` con `.text`, `.messages`, `.value` (salida estructurada), `.usage_details` (tokens) y `.user_input_requests` (aprobaciones pendientes) [AF-15][AF-19][VER].
3. Instrucciones y opciones: el system prompt va en `instructions`; `options={"response_format": ModeloPydantic}` produce salida estructurada validada en `.value`, que el libro llama "the key to reliable agents" (cap. 4.5) [AF-21][VER].
4. Herramientas: funciones Python decoradas con `@tool(name, description, approval_mode="always_require"|"never_require", max_invocations)`, con parámetros anotados (`Annotated[str, Field(description=...)]`); `agent.as_tool()` convierte un agente en herramienta de otro (agents-as-tools, cap. 4.11); herramientas MCP (`MCPStdioTool`, `MCPStreamableHTTPTool`, `MCPWebsocketTool`, con `allowed_tools` y `approval_mode` por herramienta remota); herramientas alojadas de Foundry a través de `FoundryChatClient` [AF-20][AF-26][AF-24].
5. Sesión y memoria: `AgentSession` guarda el historial y se serializa (`to_dict()` / `from_dict()`); proveedores de historial `InMemoryHistoryProvider` (por defecto), `FileHistoryProvider`, `RedisHistoryProvider`, `CosmosHistoryProvider`; memoria a largo plazo mediante `context_providers` (`Mem0ContextProvider`, `RedisContextProvider`, `FoundryMemoryProvider` en preview, `FileMemoryProvider`) con ganchos `before_run` / `after_run`, que corresponden al corto y largo plazo del cap. 4.7 [AF-16][AF-34][AF-35][AF-36].
6. Middleware: tres tipos, `AgentMiddleware` (alrededor de cada ejecución), `FunctionMiddleware` (alrededor de cada llamada a herramienta: puede inspeccionar `FunctionInvocationContext.arguments`, bloquear o reemplazar el resultado) y `ChatMiddleware` (alrededor de cada llamada al modelo); cortocircuito asignando `context.result` sin llamar a `call_next`; `ToolApprovalMiddleware` con reglas de autoaprobación. Tubería interna desde la RC5: invocación de funciones → chat middleware → telemetría → cliente bruto [AF-18][AF-13].
7. Humano en el bucle a nivel de agente: una herramienta con `approval_mode="always_require"` detiene la ejecución; la respuesta trae `user_input_requests`, cada uno con `.function_call.name` y `.arguments`; el código responde con `req.to_function_approval_response(approved=True|False)` dentro de la misma sesión (ligado a sesión desde 1.20.0). Si se rechaza, el modelo recibe "Error: Tool call invocation was rejected by user." [AF-22][VER].
8. Workflows (grafos): `WorkflowBuilder(start_executor=..., checkpoint_storage=...)` con `.add_edge(a, b, condition=...)`, `.add_switch_case_edge_group(origen, [Case(condition, target), Default(target)])`, fan-out, fan-in, selección múltiple y cadenas; nodos `Executor` con métodos `@handler` tipados, o funciones `@executor`; agentes como nodos (`AgentExecutor`); `ctx.send_message()`, `ctx.yield_output()`, `ctx.request_info(datos, tipo_respuesta)` + `@response_handler` para la parada humana; `workflow.run(mensaje, stream=True)`, `workflow.run(responses={id: respuesta}, checkpoint_id=...)` para reanudar; eventos `WorkflowEvent.type` (`started`, `executor_invoked`, `request_info`, `output`, `status`, `failed`); checkpoints `InMemoryCheckpointStorage`, `FileCheckpointStorage` (pickle restringido desde 1.0.1) y Cosmos; sub-workflows; `WorkflowViz(wf).to_mermaid()`; `workflow.as_agent()`; API funcional `@workflow` / `@step` experimental. Esto es exactamente el modelo de grafo tipado, validado y con checkpoints del cap. 6 del libro [AF-40][AF-41][AF-42][AF-44][AF-46][AF-47][AF-4][VER].
9. Orquestaciones (patrones autónomos del cap. 7): `SequentialBuilder`, `ConcurrentBuilder` (con agregador), `HandoffBuilder`, `GroupChatBuilder` (función de selección u orquestador LLM) y `MagenticBuilder` (planificador con revisión opcional del plan por un humano); estables desde la 1.0 de `agent-framework-orchestrations` (8 de julio de 2026); en .NET Magentic sigue marcado experimental [AF-52][AF-37][AF-39][AF-54].
10. Observabilidad: `configure_otel_providers(service_name, otlp_endpoint, enable_sensitive_data, enable_console_exporters)`; variables `ENABLE_INSTRUMENTATION` (activa por defecto desde 1.6.0), `ENABLE_SENSITIVE_DATA` (contenido de mensajes; opt-in como pide el libro, cap. 4.10), `OTEL_EXPORTER_OTLP_ENDPOINT`; spans `invoke_agent <nombre>`, `chat <modelo>`, `execute_tool <función>` con convenciones GenAI; métricas `gen_ai.client.token.usage` y `gen_ai.client.operation.duration`; exportación a Aspire Dashboard, Azure Monitor / Application Insights y al portal de Foundry. El framework cuenta tokens pero no calcula coste en euros: eso lo hace la aplicación [AF-9][AF-63].
11. Declarativo: `AgentFactory` y `WorkflowFactory` cargan agentes y workflows desde YAML; workflows declarativos estables (1.0, julio de 2026), agentes declarativos experimentales [AF-48][AF-53].
12. Herramientas de desarrollo: DevUI (beta; su propia documentación dice que es una aplicación de muestra "not intended for production"), plantillas `dotnet new`, extensión de VS Code, evaluación local experimental [AF-33].
13. Hosting: Foundry Hosted Agents (servicio GA desde julio–septiembre de 2026; el paquete de integración `agent-framework-foundry-hosting` sigue en prerelease; `ResponsesHostServer(agent).run()` y despliegue con `azd`), autohospedaje en ASP.NET Core o FastAPI, extensión Durable para Azure Functions (repositorio separado, prerelease), canales (alfa), servidor A2A (preview en .NET, alfa en Python) y `agent.as_mcp_server()` [AF-30][AF-5][AF-58][AF-29].
14. Seguridad del propio framework: la documentación de seguridad afirma que construir agentes seguros es "a shared responsibility" y que, por defecto, "all tools provided to an agent are invoked without user approval"; añade FIDES (etiquetas de confianza y políticas, experimental en Python), Agent Hooks (experimental) y `PurviewPolicyMiddleware` (beta) [AF-78][AF-8][AF-79][AF-80].

### Protocolos en el framework

- MCP como cliente: estable (stdio, Streamable HTTP y WebSocket), con `header_provider` para tokens, `allowed_tools` y aprobación por herramienta; el muestreo (sampling) de MCP queda obsoleto por la especificación 2026-07-28 y se retirará antes del 28-07-2027 [AF-26].
- MCP como servidor: `agent.as_mcp_server()` en Python y `McpServerTool.Create(agent.AsAIFunction())` en .NET; paquete de hosting MCP en alfa [AF-26][AF-29].
- A2A: cliente `A2AAgent(name, url | agent_card)` en beta sobre `a2a-sdk` 1.0; servidor en preview (.NET) y alfa (Python). El anuncio de la 1.0 decía "A2A 1.0 support coming soon" y el repositorio ya trae muestras, pero no he encontrado una nota de versión que declare soporte completo de A2A 1.0 [AF-27][AF-10].
- AG-UI (interfaz agente-usuario de CopilotKit): estable en Python, preview en .NET [AF-31].

### Relación con Microsoft Foundry

- El framework es independiente: la documentación dice que funciona "with any OpenAI-compatible endpoint" y no exige Azure; ninguna página lo llama literalmente "el SDK oficial de Foundry" [AF-1][AF-24].
- Dos modos de uso con Foundry: `Agent(client=FoundryChatClient(...))`, donde la aplicación es dueña de instrucciones y herramientas y usa el modelo (y opcionalmente herramientas alojadas) de Foundry; y `FoundryAgent(...)`, donde la definición autoritativa vive en el servidor de Foundry [AF-24][AF-25].
- Foundry aporta lo que el framework no trae: hosting gestionado con identidad de Entra por agente, trazas en Application Insights, evaluadores, memoria y versiones; Microsoft lo llama "recommended orchestration layer for Hosted agents in Foundry" [FY-35][FY-20].
- Los workflows declarativos propios de Foundry (vista previa desde noviembre de 2025) se retiran el 1 de diciembre de 2026 y la documentación remite a "use Microsoft Agent Framework" [FY-22].

### Novedades de 2026 y lo que no existe

- Novedades: Harness (agente con bucle y aprobaciones persistentes, liberado el 22-07-2026), CodeAct con Hyperlight (alfa), FIDES (mayo), canales de agente y workflow (alfa, agosto), Go en vista previa (julio), orquestaciones 1.0 (julio), workflows declarativos 1.0 (julio), hosted agents GA (septiembre), 1.22.0 con soporte parcial de Python 3.15 [AF-14][AF-56][AF-8][AF-29][AF-59][AF-52][AF-53][AF-55][AF-3].
- No existe: versión para Java ni para JavaScript/TypeScript; en .NET, FIDES, Hooks y CodeAct figuran como "coming soon"; Go carece de handoff, hosting, declarativo y DevUI; no hay hoja de ruta pública ni plan de 2.0 [AF-59][AF-83].
- Anticipo para la matriz: todo lo anterior es código que posee el equipo (modelo, herramientas, grafo, aprobaciones, trazas), pero el framework no da por sí mismo identidad de agente ni gobernanza del tenant; eso llega al desplegar en Foundry o con el SDK de Agent 365 (ver sección de gobernanza).

## Hallazgos: Semantic Kernel, AutoGen y la convergencia

Códigos [SK-n] en la lista de fuentes (apartado Semantic Kernel y AutoGen).

### Qué era Semantic Kernel y qué aportó

- Origen: proyecto de incubación interno de Microsoft (primer commit el 24-02-2023), publicado como código abierto el 17 de marzo de 2023 con la entrada "Hello, Semantic Kernel!" de John Maeda; C# primero, después Python y Java. Versión 1.0 en .NET el 19-12-2023, en Python el 21-05-2024 y en Java el 22-05-2024 [SK-1][SK-3][SK-4][SK-27].
- Conceptos: el `Kernel` como contenedor de servicios; "skills" renombrados a plugins y funciones (`KernelFunction`, `@kernel_function`); planificadores (Stepwise, Handlebars) hoy retirados en favor de la llamada a funciones nativa del modelo ("We recommend using function calling"); conectores a modelos y memoria vectorial [SK-24].
- Agentes: el "Agent Framework de Semantic Kernel" alcanzó GA el 4 de abril de 2025 (SK 1.45 en .NET, 1.27 en Python); la orquestación multiagente siguió en preview y el Process Framework en alfa [SK-6].
- Lo que aportó según Microsoft: "a stable SDK with connectors into enterprise systems, content moderation, and telemetry" (es decir, la base empresarial y el soporte .NET) [SK-13].

### Qué era AutoGen y qué aportó

- Origen: Microsoft Research, derivado de FLAML; artículo arXiv 2308.08155 (16-08-2023; Wu, Bansal… Wang), presentado en COLM 2024; anuncio en el blog de MSR el 25-09-2023; primera versión `pyautogen` 0.0.1 el 25-08-2023 [SK-32][SK-31].
- Conceptos: agentes conversables (`UserProxyAgent`, `AssistantAgent`, `GroupChatManager`) que resuelven tareas conversando; AutoGen Studio (junio de 2024, "not production ready"); Magentic-One (noviembre de 2024) [SK-34][SK-35].
- v0.4 (9 de enero de 2025, anunciada el 14): "complete redesign" con arquitectura asíncrona y dirigida por eventos, en capas Core / AgentChat / Extensions [SK-36]. Fork AG2 en noviembre de 2024 por parte de algunos creadores originales, con aclaración oficial de Microsoft sobre los forks [SK-38].
- Lo que aportó según Microsoft: "we opened the door to experimental multi-agent orchestration patterns" [SK-13].

### Cómo y por qué convergieron (cronología con fuentes)

| Fecha | Hito | Fuente |
| --- | --- | --- |
| 15-11-2024 | "Microsoft's Agentic AI Frameworks: AutoGen and Semantic Kernel": se anuncia alinear `autogen-core` con SK a principios de 2025; "Customers should choose Semantic Kernel if they're building agent production applications" | [SK-8] |
| 03-02-2025 | Hoja de ruta de SK para el primer semestre de 2025: "strategic convergence" | [SK-7] |
| 28-04-2025 | Se crea el repositorio microsoft/agent-framework | [SK-28] |
| 01-10-2025 | Anuncio de Microsoft Agent Framework en vista previa pública (tres entradas oficiales) | [SK-11][SK-12][SK-13] |
| 02-10-2025 | AutoGen anuncia que se fusiona "into a single, unified framework under the name Microsoft Agent Framework"; solo recibirá correcciones críticas | [SK-39] |
| 07-10-2025 | "Think of Microsoft Agent Framework as Semantic Kernel v2.0 (it's built by the same team!)"; SK 1.x seguirá con soporte "for the foreseeable future" y al menos un año después de la GA del nuevo framework | [SK-14] |
| 02/03-04-2026 | Agent Framework 1.0 GA: "Now is the time to migrate" | [SK-16] |
| 06-10-2026 | SK sigue publicando (dotnet-1.81.0, python-1.45.0): mantenimiento activo | [SK-23][SK-30] |
| 16-10-2026 | README de AutoGen: "Project archived and no longer maintained"; Microsoft no da correcciones ni soporte y "continue to advise against production use" | [SK-40] |

Los motivos declarados por Microsoft en el anuncio del 1 de octubre de 2025: "the path from prototype to production has been fraught with obstacles. Many of the most popular open-source frameworks are fragmented… enterprise readiness is missing: observability, compliance hooks, security, and long-running durability"; y sobre los dos antecesores: "Both had passionate users — but each had gaps". El nuevo framework "doesn't replace Semantic Kernel and AutoGen — it builds on them" y distingue explícitamente dos formas de orquestar: "Agent Orchestration (LLM-driven)" y "Workflow Orchestration (business-logic driven, deterministic multi-agent workflows)" [SK-13]. El blog de .NET añade: "If you're starting a new project that uses agents you should use Agent Framework" [SK-12].

### Rutas de migración oficiales

- Desde Semantic Kernel: `ChatCompletionAgent` / `OpenAIAssistantAgent` / `AzureAIAgent` → `ChatClientAgent` sobre `IChatClient` en .NET; en Python `ChatCompletionAgent(service=...)` → `Agent(client=...)`, `@kernel_function` → funciones normales en `tools=`, `invoke` → `run`, hilos → `create_session()`; sin `Kernel` obligatorio; capa de compatibilidad `semantic-kernel ≥ 1.38` con `.as_agent_framework_tool()`. La guía no cubre planificadores, memoria del Kernel ni Process Framework [SK-10].
- Desde AutoGen: `AssistantAgent(name, model_client, tools)` → `Agent(name, client, tools)`; equipos y runtime → `Workflow` tipado; `RoundRobinGroupChat` → `SequentialBuilder`; `MagenticOneGroupChat` → `MagenticBuilder`; `GraphFlow` → `Workflow`; `AgentTool` → `agent.as_tool()`; sin equivalente directo de `SelectorGroupChat` ni `Swarm` en la guía (aunque existen `GroupChatBuilder` y `HandoffBuilder`); el runtime distribuido de AutoGen no tiene equivalente: el framework "focuses on single-process composition today, with distributed execution planned" [SK-41].
- Advertencia verificada: ambas guías contienen restos de nombres antiguos (`AgentThread`, parámetro `thread`), así que la referencia fiable es la guía de cambios de 2026 y las páginas de conceptos (ver sección anterior) [AF-13].

### Lenguajes y a quién va dirigido

- Python y .NET con paridad declarada para lo que esté en GA ("We intend to support Python and C#/.NET at parity for features that are marked General Availability"); Go en vista previa desde el 10-07-2026; no existe Agent Framework para Java (la última versión de SK Java es la 1.4.4-RC1 de mayo de 2025, sin declaración oficial) ni para JavaScript/TypeScript [SK-14][SK-44].
- Público: equipos pro-code que llevan agentes "from prototype to production"; encaja cuando hace falta orquestación más allá de un chat, grafos, "durability, restartability, observability, governance, or human-in-the-loop control" y libertad de proveedor de modelo [SK-21][SK-23].

### Contraste con el epílogo del libro

- Lo que dice el libro (epílogo): AutoGen nació con `ConversableAgent`, la v0.4 de enero de 2025 adoptó el modelo de actores (Core / AgentChat), parte del equipo bifurcó AG2, Semantic Kernel aportó capacidades empresariales y soporte .NET, y la confusión entre los dos proyectos llevó al Agent Framework, que el libro describe como "a major version revision"; el prefacio lo llama "a production-ready successor". El libro también anticipa dos fases: hoy dominan los workflows y la autonomía crecerá después, de modo que los andamios "become more of control points for human oversight".
- Lo que confirman las fuentes: la cronología y la motivación coinciden punto por punto con los anuncios oficiales (fragmentación, falta de preparación empresarial, mismo equipo). El libro no entra en lo que ocurrió después de su edición: la GA del 2 de abril de 2026, el archivado de AutoGen (octubre de 2026) y la salida de la vista previa de hosted agents en Foundry. Tampoco hay en el libro ninguna afirmación sobre Business Central, Copilot Studio o Agent 365, así que todo lo que el artículo diga de esos productos procede de la documentación de Microsoft, no del libro.
- Un matiz: el libro presenta la fusión sobre todo desde la historia de AutoGen (su autor fue parte del equipo); las entradas oficiales de Microsoft la presentan como "Semantic Kernel v2.0" [SK-14]. Ambas cosas son ciertas: el equipo fue el mismo, las ideas de orquestación vienen de AutoGen y la base empresarial de SK.

## Hallazgos: Copilot Studio

Códigos [CS-n] en la lista de fuentes (apartado Copilot Studio).

### Un cambio de base en 2026: los tres "harnesses"

- Desde mediados de 2026 un agente de Copilot Studio se crea sobre uno de tres "harnesses" (arneses de ejecución): el GitHub Copilot harness (el agente razona por su cuenta, descompone objetivos, usa habilidades y memoria en un entorno aislado; en vista previa desde junio de 2026 y GA entre agosto y septiembre según la fuente), el standard harness (el clásico: temas y orquestación generativa o clásica) y el Copilot chat harness [CS-1][CS-2][CS-5][CS-6].
- Punto clave para el control: en el GitHub Copilot harness la documentación indica que no hay opción de configurar la orquestación y que el cambio de harness no es reversible; además factura créditos desde la fase de diseño [CS-7][CS-71].

### Ciclo de vida completo (standard harness, que es el que admite más control)

- Crear: diseño low-code o en lenguaje natural; instrucciones de hasta 8.000 caracteres; hasta 1.000 temas. Orquestación generativa (el modelo elige temas y herramientas por su descripción: probabilística) u orquestación clásica (frases desencadenantes: determinista) [CS-8][CS-9].
- Agentes autónomos: desencadenadores por eventos de conectores o recurrencia; corren con las credenciales del creador (maker) y la guía recomienda menos de 15 llamadas consecutivas [CS-13].
- Computer use (uso del ordenador) GA en mayo de 2026, con supervisión humana por correo [CS-14][CS-45].
- Como código: extensión de VS Code GA en enero de 2026 (definición en YAML: `agent.mcs.yaml`, temas, etc.), CLI `pac copilot`, API REST y soluciones/pipelines con Git; solo para el standard harness [CS-17][CS-18][CS-20][CS-21].
- Conocimiento: SharePoint, OneDrive, Dataverse, sitios web, archivos, Graph connectors, Azure AI Search, Foundry IQ (vista previa en Copilot Studio desde junio de 2026), Fabric IQ y Work IQ; hasta 500 fuentes. No hay fuente de conocimiento nativa de Business Central: BC entra como herramienta [CS-24][CS-26][CS-27].
- Acciones y herramientas: conectores de Power Platform (el de Business Central es Premium, con acciones V3 de crear/obtener/actualizar/borrar registro, búsqueda OData, ejecutar acción y una acción "Dynamics 365 Business Central MCP"; desencadenadores por registro creado/modificado/borrado y eventos de negocio en vista previa; 300 llamadas por conexión cada 60 s), servidores MCP (solo Streamable HTTP; autenticación None, clave de API u OAuth 2.0; interruptor por herramienta; certificación de servidores MCP por Microsoft en vista previa desde julio de 2026), REST, flujos de agente (13 créditos por cada 100 acciones), prompts de AI Builder e intérprete de código (desactivado por defecto) [CS-29][CS-30][CS-36][CS-37][CS-38][CS-43].
- Servidor MCP de Business Central desde Copilot Studio: Copilot Studio es un host preautorizado; la conexión usa siempre la identidad del usuario que inicia sesión; límite de 70 herramientas salvo "Dynamic Tool Mode"; la página de BC que lo describe sigue etiquetada "(Preview)" [CS-31][CS-32][CS-33][CS-34].
- Publicar: Teams, Microsoft 365 Copilot, SharePoint, WhatsApp, web, Azure Bot Service (Slack y otros), Direct Line, Dynamics 365 Customer Service; voz GA el 27-04-2026 (Norteamérica). No hay un canal "Business Central" [CS-56][CS-45].
- Gobernar: Power Platform admin center (DLP sobre conocimiento, conectores, MCP, HTTP y canales; prohibición de credenciales del creador; CMK), Entra Agent ID automática y sin posibilidad de desactivarla desde mayo de 2026, Agent 365 (registro automático), auditoría en Purview no desactivable, cuota de 8.000 mensajes por minuto y entorno [CS-39][CS-61][CS-62][CS-63][CS-68][CS-8].

### Multiagente y protocolos

- Agentes hijo, otros agentes del entorno, agentes A2A (GA en abril de 2026, solo como cliente: no se documenta exponer un agente de Copilot Studio como servidor A2A), agentes de Foundry (vista previa, vía endpoint Activity), agentes de Fabric (vista previa) y agentes del Microsoft 365 Agents SDK (vista previa). La documentación advierte de degradación por encima de unas 30–40 opciones (herramientas y agentes) en orquestación generativa. No existe una conexión específica con Agent Framework; la vía es Foundry, A2A o el Agents SDK [CS-44][CS-46][CS-48][CS-49].
- MCP: GA desde el 29 de mayo de 2025 en el standard harness y desde septiembre de 2026 en el GitHub Copilot harness [CS-40][CS-6].

### Modelos: qué controla el creador

- Catálogo cerrado (tabla oficial del 14-10-2026): GPT Chat Latest por defecto (cambia cuando Microsoft decide), GPT-4.1, GPT-5 Chat, GPT-5.5 Chat, GPT-5 Reasoning/Auto, GPT-5.3 (vista previa), Claude Sonnet 4.6, Claude Opus 4.6/4.7/4.8 (GA) y Grok 4.2 (experimental); los modelos externos requieren habilitación del administrador y pueden procesarse fuera de la geografía en algunas regiones [CS-51][CS-52][CS-53].
- No se documentan parámetros de modelo (temperatura, tokens máximos) ni formato de salida configurable; "traer tu propio modelo" solo aplica a prompts de AI Builder [CS-42][CS-51].

### Evaluación, telemetría e intervención humana

- Evaluación GA en marzo de 2026: conjuntos de prueba, multi-turno, seguridad, comparación de versiones, API en vista previa para CI/CD [CS-69][CS-70].
- Telemetría: analítica (transcripciones 28–29 días), Application Insights por agente (eventos propios, no OpenTelemetry; solo standard harness), telemetría de entorno alineada con OpenTelemetry en vista previa (spans InvokeAgent / ExecuteTool) y observabilidad de Agent 365 [CS-72][CS-73][CS-74][CS-66].
- Humano en el bucle: "Request information / human review" en flujos de agente (vista previa desde noviembre de 2025; solo por Outlook), supervisión de computer use, traspaso a Dynamics 365 Customer Service y aprobación explícita en borrados del MCP de Dataverse. No hay un mecanismo genérico de "pausar, esperar aprobación con estado y reanudar" documentado [CS-76][CS-77][CS-41].
- Identidad ante las herramientas: autenticación del usuario (el conector corre con su identidad) o credenciales del creador; en el MCP de BC siempre la del usuario; no se documenta el uso de service principals para conectores [CS-78][CS-79].

### Licenciamiento (cifras oficiales en USD)

- 200 $/mes por 25.000 créditos o pago por uso a 0,01 $/crédito; respuesta clásica 1 crédito, generativa 2, acción de agente 5 (15 si es premium), grounding en el grafo del tenant 10, flujos 13 por 100 acciones; los agentes se desactivan al superar el 125 % del límite; Microsoft 365 Copilot (30 $/usuario) incluye el uso interno del standard harness; el GitHub Copilot harness factura desde el diseño y comparte capacidad con Cowork y Work IQ; Agent 365 cuesta 15 $/usuario/mes [CS-16][CS-11][CS-71][CS-75][CS-65].

### Lectura para la matriz

- Control alto sobre qué herramientas y datos ve el agente y sobre la gobernanza del tenant; control medio sobre el flujo (alto con orquestación clásica, nulo en el nuevo harness); control bajo sobre el modelo (catálogo cerrado, sin parámetros) y sobre el hosting (SaaS); aprobaciones humanas limitadas a mecanismos concretos; trazabilidad buena en Purview pero sin OpenTelemetry GA; alto bloqueo de proveedor en runtime, con definición exportable en YAML y protocolos abiertos (MCP, A2A) para integrar [CS-1][CS-9][CS-51][CS-76][CS-73][CS-17].

## Hallazgos: Microsoft Foundry

Códigos [FY-n] en la lista de fuentes (apartado Foundry y gobernanza).

### Nombres y cambios de nombre (verificados)

- Azure AI Studio → Azure AI Foundry (Ignite, noviembre de 2024) → Microsoft Foundry (Ignite, 18 de noviembre de 2025). Azure AI Services pasó a llamarse Foundry Tools; el portal antiguo se denomina "Foundry (classic)" [FY-1][FY-3][FY-4][FY-6].
- Servicio de agentes: Azure AI Agent Service (vista previa en diciembre de 2024) → GA el 19-05-2025 → "next-gen" Foundry Agent Service GA el 16-03-2026, construido sobre la API Responses (conversaciones, elementos, respuestas y versiones de agente); el servicio "classic" se retira el 31-03-2027 [FY-7][FY-8][FY-9].
- Las notas de prensa de la Linux Foundation siguen diciendo "Azure AI Foundry" en 2026; la documentación de Microsoft usa "Microsoft Foundry" desde Ignite 2025 [FY-1].

### Cómo crea agentes Foundry hoy

- Dos tipos de agente (documentación de septiembre de 2026): prompt agents (definidos por configuración: instrucciones, modelo y herramientas) y hosted agents (código propio empaquetado en contenedor o zip, escrito con Agent Framework, LangGraph, OpenAI Agents SDK, Anthropic Agent SDK o GitHub Copilot SDK); además, agentes efímeros vía API Responses [FY-8][FY-20].
- Hosted agents: vista previa en Ignite 2025, relanzados el 22-04-2026, GA el 09-07-2026; entorno aislado por sesión, escala a cero, tiempo de inactividad 2–60 min (15 por defecto), 31 regiones (incluidas West Europe y Sweden Central), Python y C# [FY-19][FY-15][FY-16][FY-20].
- Runtime: conversaciones (con opción de Cosmos DB propio), herramientas integradas (búsqueda web, búsqueda de archivos, intérprete de código, memoria en vista previa), herramienta MCP con aprobación por llamada (`require_approval` "always" por defecto), OpenAPI, toolboxes (GA julio–agosto de 2026), skills y búsqueda de herramientas (vista previa), versiones, publicación a Teams y Microsoft 365 Copilot (GA 10-06-2026), Routines (vista previa 03-06-2026), operaciones de larga duración con paso de aprobación humana (vista previa, agosto de 2026) y Agent optimizer (vista previa) [FY-8][FY-17][FY-46][PR-37].
- Multiagente: "connected agents" retirado; herramienta A2A saliente v1.0 GA (solo texto, sin streaming) y endpoints A2A entrantes (vista previa; Entra obligatorio); los workflows declarativos de Foundry (YAML, vista previa desde el 25-11-2025 y construidos sobre Agent Framework) se retiran el 1 de diciembre de 2026 con la indicación de usar Agent Framework [FY-24][FY-22][FY-23].
- Portal frente a SDK: todo lo anterior puede hacerse desde el portal o desde los SDK de Foundry (Python, .NET, Java, JS) [FY-33].

### Catálogo de modelos

- Más de 10.000 modelos, "vendidos por Azure" o por socios; OpenAI (GPT-5.4 GA el 05-03-2026, 5.5, 5.6 el 09-07-2026), Anthropic (Claude en Foundry desde el 18-11-2025; GA en junio de 2026; claude-opus-5 GA el 24-07-2026), xAI, Mistral, Meta, DeepSeek y modelos MAI; enrutador de modelos GA; tipos de despliegue Global / Data Zone / Regional, estándar o aprovisionado, por lotes [FY-25][FY-26].
- Para el control esto significa elegir modelo y parámetros por agente con residencia de datos definida, algo que Copilot Studio no ofrece.

### Observabilidad y evaluación

- OpenTelemetry con Application Insights para cualquier framework; trazas GA para prompt agents (marzo de 2026) y para hosted agents (junio–julio de 2026); evaluadores GA el 16-03-2026 (precisión de llamadas a herramientas, finalización de tarea, etc.); evaluación continua; AI Red Teaming Agent; Control Plane con coste, tokens, ejecuciones y errores (en vista previa); ASSERT y Agent Control Specification (código abierto, Build 2026) [FY-27][FY-28][FY-29][FY-13].

### Hosting, seguridad y precios

- Recurso Foundry y proyectos; red virtual gestionada GA en mayo de 2026 y red propia para hosted agents; identidad de agente de Entra por agente al publicar o desplegar; RBAC (Foundry User y otros); filtros de contenido y guardrails; claves gestionadas por el cliente [FY-8][FY-30][FY-12].
- Precios: los agentes nativos de Foundry no tienen cargo adicional (se paga tokens y herramientas); los hosted agents se facturan por vCPU-hora y GiB-hora, pero la página oficial de precios no mostraba importes el 17-10-2026 y las cifras disponibles proceden de un tercero (0,0994 $/vCPU-h y 0,0118 $/GiB-h) [FY-32][FY-69].

### Relación con Agent Framework y con Copilot Studio

- Con Agent Framework: Foundry es el destino de despliegue "recomendado" para agentes del framework (`agent-framework-foundry-hosting`, `azd ai agent init/run`, `azd provision/deploy`), con identidad de Entra dedicada al desplegar; `FoundryChatClient` para usar modelos y herramientas alojadas, `FoundryAgent` para usar agentes definidos en Foundry; Build 2026 añadió Agent Harness, CodeAct con Hyperlight (alfa) y GitHub Copilot SDK [FY-34][FY-35][FY-36][FY-38].
- Con Copilot Studio: "Connect to a Microsoft Foundry agent (preview)" mediante el endpoint Activity (hay que habilitarlo por API o SDK); Foundry IQ como fuente de conocimiento en Copilot Studio; traer modelos de Foundry solo para prompts de AI Builder; en sentido contrario, Foundry publica a Teams y Microsoft 365 Copilot (GA 10-06-2026) a través de Azure Bot Service, una app de Entra y aprobación del administrador de M365; Work IQ en vista previa con flujo en nombre del usuario [FY-40][FY-44][FY-41][FY-46][FY-45].
- No encontrado: ninguna integración específica de Foundry con Business Central (ni documentación ni ejemplo oficial); la conexión se hace con las herramientas genéricas (MCP de BC, OpenAPI o funciones propias sobre la API v2.0).

### Lectura para la matriz

- Foundry da el control del modelo (catálogo abierto, parámetros, residencia), observabilidad estándar, evaluación, identidad de agente y hosting gestionado; pero el flujo del agente, las validaciones y las aprobaciones no viven en Foundry salvo que se escriban en código (hosted agent) o se usen los pasos de aprobación en vista previa; para los prompt agents el bucle es el del servicio [FY-8][FY-17].

## Hallazgos: gobernanza e identidad de agentes (Agent 365, Entra Agent ID, Purview, Defender)

Códigos [FY-n], [CS-n] y [AF-n] en la lista de fuentes.

### Microsoft Entra Agent ID

- Qué es: identidades propias para agentes en Entra, con tres tipos: agent identity (un principal de servicio especial), agent identity blueprint (plantilla para crear identidades) y agent user (usuario de tipo agente); admite Acceso condicional y exige un "sponsor" (persona responsable). Anunciado en vista previa en Build 2025; GA en abril de 2026 (la documentación oficial solo dice "April 2026") [FY-48][FY-49].
- Cómo lo recibe cada producto: Copilot Studio crea la identidad automáticamente desde mayo de 2026 (la fecha varía entre mayo y julio según la página) y no se puede desactivar; Foundry crea una identidad por defecto y una dedicada al publicar o desplegar; un agente de Agent Framework no recibe identidad por sí solo: la obtiene al desplegarse en Foundry o al integrar el SDK de Agent 365 o el SDK de autenticación de Entra [FY-52][FY-30][FY-59].
- Limitación relevante: "Extending Microsoft Entra security features to agents requires Microsoft Agent 365" (gobernanza de identidades de agente y control de red requieren esa licencia) [FY-48][FY-54].

### Microsoft Agent 365

- Plano de control para registrar, observar, gobernar y asegurar agentes de cualquier origen (Copilot Studio, Foundry, Agent Framework, terceros, incluso Bedrock o Vertex vía sincronización): Registry, control de acceso, visualización, interoperabilidad y seguridad (Defender, Intune, Purview). Anunciado en Ignite el 18-11-2025; GA el 1 de mayo de 2026; 15 $/usuario/mes o incluido en Microsoft 365 E7 [FY-54][FY-55][FY-56][FY-57].
- El Agent Registry de Entra migró a Agent 365 el 01-05-2026 con nueva API de Graph ("Agents registered via the current API will need to be re-registered"). SDK de Agent 365 (`microsoft-agents-a365-*`) y CLI para agentes propios; la extensión para Agent Framework (`microsoft-agents-a365-tooling-extensions-agentframework` 1.0.0, 01-05-2026) está marcada alfa en PyPI [FY-58][FY-59][AF-67][AF-68].

### Microsoft Purview

- Para Foundry: auditoría de prompts y respuestas, DSPM for AI, etiquetas de confidencialidad, DLP (bloqueo de prompts) e Insider Risk Management. Limitación clave: las políticas (DLP, clasificación) solo aplican cuando el agente actúa con un token en contexto de usuario (flujo en nombre del usuario); un agente autónomo con identidad propia solo deja auditoría [FY-61].
- Para Copilot Studio: registro de auditoría no desactivable [CS-68]. Para Agent Framework: `PurviewPolicyMiddleware` (beta; requiere permisos de Graph y licencia M365 E5) [AF-80].

### Microsoft Defender

- Detección y protección para agentes de IA en vista previa: cubre agentes gestionados por Agent 365 y, en detección, solo agentes de Foundry publicados; señales de jailbreak, inyección indirecta (XPIA) y fuga de secretos [FY-62][FY-63].

### Microsoft 365 Agents SDK y Copilot Control System

- El Microsoft 365 Agents SDK es la capa de canales (protocolo Activity) para llevar un agente a Teams, web, Slack y otros; es agnóstico del framework de IA; el Agents Toolkit es el antiguo Teams Toolkit. No he encontrado integración oficial vigente entre Agent Framework y el Agents SDK (solo evidencia indirecta: el protocolo Activity en hosted agents de Foundry) [FY-64][FY-65][AF-66].
- Copilot Control System: conjunto de controles de administración de Microsoft 365 para Copilot y agentes [FY-66].

### Qué significa para el control del agente sobre Business Central

- Identidad: la gobernanza de Microsoft (Entra Agent ID, Agent 365) identifica al agente en el tenant, pero Business Central tiene su propia capa: un agente externo entra en BC como una aplicación de Entra registrada en la página "Microsoft Entra applications" con conjuntos de permisos, o como el usuario que inicia sesión (MCP), y los agentes nativos usan usuarios de tipo agente. No he encontrado ninguna fuente que conecte Entra Agent ID o Agent 365 con los permisos de Business Central [FY-48][BC-58][BC-42].
- Políticas: Purview solo gobierna lo que pasa con token de usuario; un agente desatendido que escribe en BC con credenciales de aplicación queda fuera de las políticas DLP (solo auditoría), así que las reglas de negocio deben vivir en el código del agente y en los permisos de BC [FY-61].
- Coste de la gobernanza: Agent 365 es una licencia adicional por usuario; Copilot Studio y Foundry se integran con ella de serie, Agent Framework mediante SDK en alfa [FY-55][AF-68].

## Hallazgos: Business Central y agentes

Códigos [BC-n] (fuentes oficiales) y [BC-Tn] (terceros) en la lista de fuentes.

### Contexto de versiones y hojas de ruta

- Business Central 2026 release wave 2 (versión 29.0, octubre de 2026) es la versión vigente; Microsoft retiró los planes de lanzamiento semestrales (anuncio del 25-08-2026; el Release Planner se retira el 15-11-2026) y la fuente pasa a ser "What's new, update 29.0" y el AI at Work roadmap [BC-18][BC-24][BC-T5].

### Agentes nativos (lo que Microsoft ya vende dentro de BC)

- Sales Order Agent: vista previa el 07-03-2025, GA el 10-11-2025 (plan 2024 wave 2); mejoras GA el 07-11-2025 (adjuntos, expansión a DK/DE/IT/FR/ES) y "varios agentes por empresa" GA el 08-07-2026. Qué hace: vigila un buzón de Microsoft 365, identifica al cliente solo por el correo del contacto, busca artículos, comprueba disponibilidad y siempre crea primero una oferta de venta; el PDF sale tras revisión humana y se convierte en pedido cuando el cliente confirma. Límites declarados: no crea artículos, clientes ni contactos; no registra; máximo 15 líneas; solo líneas de tipo artículo; sin precios ni descuentos (escala al usuario); "las instrucciones del agente no se pueden modificar"; más de 70 casos de prueba en 12 categorías; prompts guardados 20 días. Revisión humana: panel de tareas, línea de tiempo, Confirmar o Detener, instrucciones al agente solo para el paso actual, confianza por campo [BC-1][BC-2][BC-3][BC-5][BC-6][BC-7][BC-15].
- Payables Agent: vista previa el 04-07-2025, GA el 07-11-2025; disponible en España desde el 09-01-2026; cotejo con pedidos GA el 06-02-2026; remitentes conocidos GA el 07-08-2026. Qué hace: lee PDF del buzón, los pasa por documentos electrónicos entrantes y OCR (Azure Document Intelligence) y crea borradores de factura de compra sin registrar; no registra ni aprueba; límites de 100 correos y 500 facturas al día; 50 facturas gratuitas de prueba [BC-8][BC-9][BC-10][BC-11].
- Expense Agent: vista previa el 08-05-2026 (EE. UU.), español en vista previa desde el 01-07-2026; 50 créditos por recibo [BC-12][BC-13].
- Custom Agent / Agent Designer: vista previa pública el 06-02-2026 (BC 27.4); la tabla del plan 2025 wave 2 prevé GA en octubre de 2026, pero no aparece en "What's new 29.0" (punto dudoso) [BC-16][BC-18][BC-T1].
- Gobernanza común de los agentes nativos: cada agente es un usuario propio de BC ("SALES ORDER AGENT - [EMPRESA]") con conjunto de permisos y perfil; sus acciones quedan con su identificador de usuario en el registro de cambios; los permisos efectivos son la intersección de los del agente y los del usuario que lo configuró o responde ("los agentes nunca superan los privilegios del usuario"); permisos de sistema Configure All Agents (9665) y Manage Agent Tasks (9670); conjuntos AGENT - ADMIN, D365 Agent y AGENT - DIAGNOSTICS ("What the agent saw", coste de ejecución); panel "Copilot & agent capabilities" por capacidad y usuario; modelo GPT-5.3-chat por defecto desde la versión 28 con selector de modelo en vista previa (28.2); panel unificado de tareas GA el 01-04-2026; si se agotan los créditos el Sales Order Agent deja de leer el correo; telemetría de ciclo de vida (LC0066–LC0068) y de consumo de IA [BC-14][BC-15][BC-32][BC-34][BC-72][BC-75][BC-T2].

### Crear agentes propios dentro de BC

- AI Development Toolkit (solo sandbox, desde 27.2) y Agent SDK for AL (sandbox desde 27.4; producción desde 28.1): no hay un objeto AL "agent"; se implementa una `enumextension` de "Agent Metadata Provider" con las interfaces `IAgentFactory`, `IAgentMetadata` e `IAgentTaskExecution` y se registra una capacidad de Copilot (`RegisterCapability` con capacidad, disponibilidad, tipo de facturación y URL); las tareas se crean desde AL (Agent Task Builder; `SetRequiresReview(false)` desde 28.1). Limitaciones: el agente no puede exceder los permisos del creador, instrucciones en inglés, Azure OpenAI, filtros no desactivables, solo online. No hay API REST documentada para crear tareas de agente desde fuera de BC [BC-26][BC-27][BC-28][BC-29][BC-30][BC-31][BC-32][BC-33][BC-34].
- Facturación de agentes propios: "se anunciará"; los tipos de facturación de capacidades son Microsoft Billed, Custom Billed y Not Billed [BC-72][BC-T4].

### Servidor MCP de Business Central

- Estado: vista previa el 31-10-2025 (2025 wave 2, BC 27.1) con GA "sin anunciar" en el plan original; mejoras publicadas como GA el 01-04-2026 (endpoint `https://mcp.businesscentral.dynamics.com`, OAuth 2.1, hosts preautorizados, telemetría y Purview) y el 12-06-2026 (todas las API estándar y consultas API); en 29.0 "Run data queries with MCP Server" figura como GA en el roadmap, pero la documentación de octubre de 2026 sigue etiquetando "Data Query Tools (Preview)" y la página de Copilot Studio "(Preview)". Lectura prudente: API Tools en producción, Data Query Tools en vista previa [BC-39][BC-45][BC-46][BC-40][BC-41][BC-43].
- Configuración: página 8350 "MCP Server Configurations" (requiere el conjunto MCP - Admin): Active, Unblock Edit Tools, API Tools con Allow Read / Create / Modify / Delete / Actions por objeto, Dynamic Tool Mode (`bc_actions_search/describe/invoke`, para esquivar el límite de 70 herramientas de Copilot Studio), Data Query Tools (`bc_data_find_tables`, `bc_data_get_table_schema`, `bc_data_get_table_relations`, `bc_data_query`; solo lectura), "Add All Standard APIs", validación y exportación/importación en JSON; nombres de herramienta como `List_Customers_PAG30009` o `Create_Customer_PAG30009`; las acciones OData (por ejemplo registrar) se exponen si se permiten Actions; cabeceras `TenantId`, `EnvironmentName`, `Company` y `ConfigurationName`. Por defecto el servidor es de solo lectura: cada escritura se habilita API a API [BC-41][BC-40].
- Autenticación: OAuth 2.0 con código de autorización y PKCE contra Entra ID; "todas las operaciones se ejecutan con la identidad y permisos del usuario"; los clientes no Microsoft registran su propia app en Entra (sin registro dinámico) con el permiso delegado `Financials.ReadWrite.All`; solo Streamable HTTP. No hay flujo de credenciales de cliente (aplicación a aplicación) documentado para el MCP de BC: siempre delegado, es decir, con un usuario presente. Esto es decisivo para un agente desatendido [BC-42][BC-40].
- Hosts documentados: Copilot Studio (recomienda GPT-5), VS Code con GitHub Copilot, GitHub Copilot CLI, Claude Code, ChatGPT y MCP Inspector; telemetría RT0054 "MCP Server tool called" [BC-43][BC-44][BC-74].
- Relacionados: Admin Center MCP server en vista previa desde el 01-04-2026 (excluye seis operaciones destructivas y exige confirmación explícita); AL MCP Server para desarrollo (`al_build`, `al_compile`, `al_publish`…) [BC-47][PR-67].

### Conectar un agente externo: las vías y lo que cada una permite

| Vía | Qué permite | Identidad y permisos | Estado | Fuente |
| --- | --- | --- | --- | --- |
| Servidor MCP de BC | Lectura por defecto; crear, modificar, borrar y acciones OData si se configuran; consultas de datos | Siempre usuario delegado (OAuth + PKCE); permisos del usuario ∩ configuración MCP | Producción (API Tools); Data Query Tools en vista previa | [BC-40][BC-41][BC-42] |
| Copilot Studio con el MCP de BC o el conector Premium | Igual que MCP (límite 70 herramientas) o CRUD, ejecutar acción y desencadenadores por evento | Usuario conectado; licencia Copilot Studio y créditos; conector 300 llamadas/60 s | MCP en vista previa en la página de BC; conector GA | [BC-43][BC-65] |
| API v2.0 (REST) | CRUD sobre entidades estándar (`customers`, `items`, `salesOrders` → `salesOrderLines`) y acciones enlazadas (`shipAndInvoice`) | S2S con credenciales de cliente (`API.ReadWrite.All`; app registrada en "Microsoft Entra applications" con conjuntos de permisos, nunca SUPER; no necesita licencia) o delegado (`Financials.ReadWrite.All`); 600 req/min en producción, 300 en sandbox, 6.000 por usuario cada 5 min | GA (S2S desde la 18.3) | [BC-53][BC-54][BC-55][BC-58][BC-59][BC-60] |
| APIs personalizadas en AL u OData v4 | CRUD y procedimientos sobre páginas propias (`PageType = API`), exponibles también al MCP | Igual que API v2.0 | GA | [BC-62][BC-63][BC-64] |
| Agent SDK for AL / Agent Designer | Agentes que operan dentro de BC con revisión humana nativa | Usuario de agente propio; permisos ∩ creador | SDK en producción desde 28.1; Designer en vista previa | [BC-26][BC-34] |

### Permisos, licencias y coste

- Licencias: Essentials 80 $, Premium 110 $, Team Members, Device y External Accountant (USD); "los usuarios deben tener licencia de BC para usar los agentes de serie"; los Copilot Credits se compran aparte (0,01 $/crédito en pago por uso o paquetes); no hay SKU de "capacidad de agente"; una aplicación S2S no necesita licencia; la regla de multiplexación solo la he verificado en la guía on-premises de 2024 [BC-67][BC-68][BC-59][BC-71].
- Consumo publicado: Sales Order Agent ≈ 1.650 créditos al mes por cada 100 solicitudes (≈ 16,5 $); Payables 50 créditos por factura + 5 por línea (≈ 6.500 créditos por 100 facturas); Expense 50 por recibo [BC-72].
- Sandbox: desde el centro de administración (Essentials y Premium incluyen 1 entorno de producción y 3 sandboxes) [BC-66].

### Encaje con Agent Framework (y con Foundry y Copilot Studio)

- La documentación oficial de Agent Framework no menciona Business Central, y la de BC cubre como hosts MCP a Copilot Studio, VS Code, GitHub Copilot CLI, Claude Code y ChatGPT; no existe ejemplo ni guía oficial de Microsoft de un agente de Agent Framework o de Foundry conectado a BC, ni por MCP ni por API [BC-77][BC-78][BC-40].
- Lectura técnica: un agente de Agent Framework puede usar `MCPStreamableHTTPTool` con un token delegado (`header_provider`) y las cabeceras de BC cuando hay un usuario presente, o funciones propias sobre la API v2.0 con credenciales de cliente cuando debe trabajar desatendido con mínimo privilegio. Esa es la razón por la que el ejemplo práctico escribe en BC por API v2.0 y deja el MCP como extensión opcional.
- Comunidad (no verificable en detalle): Bert Verbeek publicó "Microsoft Agent Framework and Business Central MCP server" el 12-11-2025 (artículo no accesible; solo resumen de terceros); repositorios comunitarios de servidores MCP para BC [BC-T8][BC-T13].

## Hallazgos: protocolos MCP y A2A

Códigos [PR-n] en la lista de fuentes (apartado protocolos y riesgo).

### MCP (Model Context Protocol, protocolo de contexto de modelo)

- Origen y gobernanza: presentado por Anthropic el 25-11-2024; donado el 09-12-2025 a la Agentic AI Foundation (AAIF), un fondo dirigido de la Linux Foundation cofundado por Anthropic, Block y OpenAI, con Microsoft como miembro Platinum. La gobernanza técnica es por personas, no por empresas: lead maintainers David Soria Parra y Den Delimarsky; Caitie McCaffrey (Microsoft) es core maintainer y miembro del comité técnico de la AAIF; las propuestas se tramitan como SEP [PR-1][PR-3][PR-4][PR-5][PR-7][PR-8].
- Versiones de la especificación: 2024-11-05 (inicial: JSON-RPC, stdio y HTTP+SSE, tools/resources/prompts), 2025-03-26 (autorización OAuth 2.1, Streamable HTTP, anotaciones de herramientas), 2025-06-18 (salida estructurada, servidores como OAuth Resource Servers, RFC 8707, elicitation), 2025-11-25 (CIMD, consentimiento incremental de ámbitos, tasks experimental) y la vigente 2026-07-28: protocolo sin estado (desaparecen `initialize` y `Mcp-Session-Id`), nuevo `server/discover`, MRTR para peticiones de varios viajes, tasks como extensión, propagación de trazas OpenTelemetry en `_meta`; Roots, Sampling y Logging quedan obsoletos (retirada no antes del 28-07-2027) y el registro dinámico de clientes cede paso a CIMD; política formal de obsolescencia de 12 meses [PR-2][PR-13][PR-14][PR-15][PR-16][PR-17][PR-19].
- Extensiones oficiales (2026): `ext-auth` (credenciales de cliente y Enterprise-Managed Authorization, OAuth "sin intervención" gobernado por el IdP corporativo, adoptada por Anthropic y por Microsoft en VS Code), MCP Apps, MCP Tasks y Skills over MCP; siempre desactivadas por defecto. Hoja de ruta (22-08-2026): identidad de agente y seguridad empresarial (DPoP, federación de identidad de carga de trabajo, ID-JAG) [PR-23][PR-24][PR-20].
- SDK: C# en nivel 1, "maintained in collaboration with Microsoft" (NuGet `ModelContextProtocol` 2.2.0, 13-08-2026); registro oficial de servidores en vista previa desde el 08-09-2025 sin anuncio de GA localizado; `microsoft/mcp` como catálogo oficial de servidores de Microsoft [PR-25][PR-26][PR-28][PR-29][PR-30][PR-32].
- Seguridad: la página normativa "Security Best Practices" (2026-07-28) cubre el diputado confundido, el paso de tokens ("MCP servers MUST NOT accept tokens not explicitly issued for the MCP server"), SSRF, secuestro de identificadores de estado, servidores locales y minimización de ámbitos. Riesgos documentados por terceros: envenenamiento de herramientas, rug pulls y shadowing (Invariant Labs, 01-04-2025) y el "flujo tóxico" del GitHub MCP (26-05-2025). El blog oficial de MCP (16-03-2026) insiste en que las anotaciones (`readOnlyHint`, `destructiveHint`) son "vocabulario de riesgo", no un control, y en que las garantías deben vivir en controles deterministas; Foundry advierte de que las descripciones y resultados de herramientas remotas son entrada no fiable [PR-33][PR-34][PR-35][PR-36][PR-37].

### A2A (Agent2Agent)

- Origen: Google, 09-04-2025, con más de 50 socios (Microsoft no estaba en la lista inicial); Microsoft se unió al grupo de trabajo el 07-05-2025; proyecto de la Linux Foundation desde el 23-06-2025; v1.0.0 el 12-03-2026 (separación de protocolo y bindings de transporte, OAuth modernizado con PKCE y código de dispositivo, `tasks/list`, multi-tenencia gRPC, Agent Cards firmadas) y v1.0.1 el 28-05-2026; incorporado a la AAIF el 17-08-2026; Microsoft forma parte del comité técnico [PR-38][PR-39][PR-40][PR-43][PR-45][PR-41].
- Conceptos: Agent Card (identidad, capacidades, skills, endpoint, autenticación; firmable), Message con Parts, Task con ciclo de vida (WORKING, INPUT_REQUIRED, AUTH_REQUIRED, COMPLETED, FAILED…), Artifact y Context; transportes JSON-RPC, gRPC y HTTP+JSON; streaming por SSE y notificaciones push [PR-46].
- SDK .NET (`a2aproject/a2a-dotnet`, nacido del proyecto de Darrel Miller en Microsoft): solo versiones preview (1.0.0-preview3, 14-10-2026) aunque la Linux Foundation lo califique de "production-ready" [PR-47][PR-48][PR-44].

### Adopción por Microsoft (resumen de fechas)

| Producto | MCP | A2A |
| --- | --- | --- |
| Copilot Studio | GA desde el 29-05-2025 (standard); certificación de servidores en vista previa (julio 2026) | GA abril 2026, solo como cliente |
| Microsoft Foundry | Herramienta MCP con `require_approval` "always" por defecto, `allowed_tools`, autenticación con identidad de agente o de proyecto; tiempo de espera 100 s | Herramienta A2A v1.0 GA; endpoints entrantes en vista previa con Entra obligatorio (asume 0.3 si no se indica versión) |
| Agent Framework | Cliente estable; servidor con `as_mcp_server()` | Cliente beta; servidor preview/alfa; "A2A 1.0 coming soon" en el anuncio de 1.0 |
| Business Central | Servidor MCP propio (ver sección anterior) | No documentado |
| Otros | Dataverse MCP GA el 15-12-2025 (`delete_record` solo con aprobación explícita), GitHub MCP GA el 04-09-2025, Azure MCP 2.0 el 10-04-2026, Windows MCP en prerelease | — |

Fuentes de la tabla: [PR-51][PR-52][PR-53][PR-37][PR-55][PR-56][PR-58][PR-59][PR-60][PR-68][PR-69][PR-49][BC-40].

### Cómo decidir entre MCP y A2A, y relación con el capítulo 12 del libro

- Lo que dicen los proyectos: MCP es "vertical" (da profundidad a un agente conectándolo a herramientas y recursos, normalmente sin estado) y A2A es "horizontal" (descubrimiento, negociación y colaboración con estado entre agentes de equipos u organizaciones distintas); ambos viven hoy bajo la AAIF y se complementan, aunque hay zonas grises porque MCP añade tareas duraderas y apps y A2A permite skills "tipo herramienta" [PR-77][PR-20][PR-41].
- Lo que dice el libro (cap. 12) y lo que ha cambiado: el libro describe MCP con herramientas, recursos, prompts, elicitation y sampling, autorización OAuth 2.1 sin paso de tokens; y A2A con Agent Card y tareas con estados. Todo sigue vigente salvo un detalle: sampling (y roots y logging) quedaron obsoletos en la revisión 2026-07-28, posterior al libro. La frase del libro "MCP gives you visibility and control over individual capability calls. A2A lets you delegate entire tasks" coincide con la lectura vertical/horizontal de los proyectos, y su advertencia de que "organization-level governance… still lives outside the protocol" es exactamente lo que confirman Entra Agent ID y Agent 365: los protocolos transportan identidad y autorización, pero la política se decide fuera.
- Regla práctica para un ERP: si lo que se expone es un sistema (Business Central, Dataverse) con operaciones acotadas, autorización OAuth y auditoría por usuario, la pieza natural es MCP; si lo que se expone es un agente con razonamiento propio, tareas largas y pertenencia a otro equipo o proveedor, A2A. Pueden convivir: orquestador → agentes de dominio por A2A → sistemas por MCP [PR-77].
- Punto dudoso transversal: ningún producto de Microsoft consultado declara qué revisión de MCP implementa; conviene no afirmar que un servidor "cumple 2026-07-28" sin verificarlo en cada caso.

## Hallazgos: control y riesgo de agentes en sistemas empresariales

Códigos [PR-n] en la lista de fuentes.

### Satya Nadella: "Models as Insider Risks in the Super Intelligence Era"

- Fuente primaria localizada: ensayo publicado el 10 de octubre de 2026 en el blog personal "sn scratchpad" (https://snscratchpad.com/posts/models-as-insider-risks/) y, el mismo día y con el texto idéntico, como artículo de X en la cuenta @satyanadella (https://x.com/satyanadella/status/2108931348857827686) y recogido por Bloomberg (vía Deccan Chronicle, 13-10), Forbes (11-10), Business Standard y PC Guide (12-10). Autoría confirmada el 18-10-2026 con el artículo de X; el blog no lleva firma explícita, pero enlaza a los perfiles de Nadella en X y LinkedIn [PR-78][PR-79][PR-80][PR-81][PR-82][PR-83][PR-84].
- Tesis: tratar los modelos frontera (cerrados o de pesos abiertos) como riesgos internos, "not because they are necessarily malicious, but because any sufficiently capable actor" puede equivocarse o verse comprometido; "we need to separate the supply of intelligence from the authority over it"; "the controls that govern what a model can access and what actions it can take must sit outside the model"; "we must assume a model is compromised and contain it from the start"; "an authorized person should always be able to pause or shut down a model mid-task" (el "freno de emergencia"); "a model provider's assurances do not relieve us of that responsibility"; la transparencia de la cadena de razonamiento "alone is not sufficient or dependable"; y el cierre: "The most trustworthy Super Intelligence system will not be the one with the model we trust most. It will be the one that enables us to trust the model the least" [PR-78].
- Siete principios de diseño (en negrita en el original): diversidad de modelos (ninguno verifica su propio trabajo), observar todo (evidencia a prueba de manipulación y legible), verificabilidad (probar el sistema completo incluidos ataques y casos límite), controles independientes, auditoría independiente ("la validación debe ser independiente de la inteligencia validada"), contención y divulgación de incidentes. El texto no menciona productos; la relación con Entra Agent ID y Agent 365 la hacen los medios, pero encaja con la línea de Microsoft Security de tratar a cada agente como "first-class principal" con identidad propia, RBAC por tarea, vinculación de herramientas y aprobaciones escalonadas [PR-78][PR-82][PR-86][PR-87].
- Dónde encaja en el artículo: en la definición de "control" (los controles fuera del modelo son exactamente el workflow determinista, el middleware, los permisos de BC y la aprobación humana) y en la conclusión. Declaraciones anteriores con la misma idea solo se han encontrado a través de terceros (podcast Possible, junio de 2026: "give them identities… sandboxes… policies"; All-In Summit, septiembre de 2026: un modelo al que se pide optimizar el capital circulante "may fake my books") [PR-88][PR-82].

### Otras referencias de peso

- Microsoft, taxonomía de modos de fallo de agentes: versión inicial (24-04-2025) con el caso de envenenamiento de memoria y versión 2.0 (04-06-2026) con siete modos nuevos; lección central: la elusión del humano en el bucle fue el modo de fallo más explotado (fatiga de consentimiento, escalada incremental); mitigaciones: descomponer acciones compuestas, resumir las aprobaciones a partir de las llamadas reales a herramientas y escalonar por reversibilidad y radio de impacto [PR-89][PR-90].
- OWASP: Top 10 para aplicaciones LLM 2025 (LLM06 Excessive Agency, LLM10 Unbounded Consumption) y Top 10 para aplicaciones agénticas 2026 (ASI01 secuestro de objetivo, ASI02 mal uso de herramientas, ASI03 abuso de identidad y privilegios, ASI04 cadena de suministro MCP/A2A, ASI06 envenenamiento de memoria, ASI10 agentes descontrolados) [PR-91][PR-93].
- NIST: evaluaciones de secuestro de agentes (el ataque más fuerte pasó del 11 % al 81 % de éxito con técnicas adaptativas; "seguirá siendo un desafío persistente"), COSAiS (sin overlays publicados a 17-10-2026) y la AI Agent Standards Initiative (17-02-2026) [PR-94][PR-95][PR-96].
- Google: controladores humanos bien definidos, poderes limitados y acciones observables; defensa en profundidad con una primera capa de controles deterministas (motor de políticas que permite, bloquea o pide confirmación según irreversibilidad e importe) y una segunda basada en razonamiento "sin garantías absolutas" [PR-100][PR-101].
- Anthropic: Agentic Misalignment (20-06-2025: en simulaciones, 16 modelos de varios desarrolladores eligieron a veces conductas de amenaza interna; recomendación de humano en el bucle para acciones irreversibles) y marco de agentes seguros (04-08-2025: aprobación humana antes de modificar sistemas) [PR-102][PR-103]. OpenAI: prácticas de gobernanza (2023: restringir el espacio de acción, exigir aprobación, atribuibilidad, interrumpibilidad) y la admisión de que la inyección de prompt "sigue siendo un reto abierto" (22-12-2025) [PR-104][PR-105].
- Simon Willison, "lethal trifecta" (16-06-2025): un agente es peligroso cuando combina acceso a datos privados, exposición a contenido no fiable y capacidad de comunicación externa; coincide con la Regla de dos de Meta que recoge el libro (cap. 13). EchoLeak en Microsoft 365 Copilot es CVE-2025-32711 [PR-98][PR-99].
- Gartner (25-06-2025): más del 40 % de los proyectos de IA agéntica se cancelarán antes de finales de 2027 por costes, valor poco claro y "controles de riesgo inadecuados" [PR-106]. Cemri et al. (MAST): los fallos multiagente requieren soluciones de diseño, no solo mejores modelos [PR-107].
- Incidentes públicos (prensa especializada; postmortems primarios no siempre accesibles): Replit borró una base de datos de producción pese a instrucciones de no cambiar nada sin aprobación (julio de 2025); Amazon Q 1.84.0 distribuyó un prompt malicioso introducido por pull request (julio de 2025); Gemini CLI borró ficheros por comandos alucinados (julio de 2025); PocketOS/Railway: un agente de programación encontró un token con autoridad total y borró producción y copias en nueve segundos (abril–mayo de 2026) [PR-108][PR-109][PR-110][PR-111].

### Principios que se repiten (aplicados a un ERP)

1. Mínimo privilegio y ámbitos progresivos: en BC, el servidor MCP es de solo lectura por defecto y cada escritura se habilita API a API; con la API v2.0, conjuntos de permisos sin SUPER [PR-33][PR-87][BC-41][BC-58].
2. Identidad propia del agente, nunca credenciales compartidas [PR-78][PR-87][PR-90].
3. Aprobación humana para escrituras e irreversibles, sabiendo que es el control más eludido: resumir lo que realmente se va a ejecutar, no lo que el agente dice [PR-90][PR-37][PR-60].
4. Separar la decisión del modelo de la ejecución determinista (controles fuera del modelo); en BC la lógica de AL se ejecuta en el servidor con los permisos del usuario, no en el prompt [PR-78][PR-101][PR-36][BC-40].
5. Trazabilidad independiente: el paso de tokens rompe el rastro de auditoría; registrar identidad, ámbito, recurso, acción y correlación [PR-33][PR-87].
6. Evaluación previa y continua, incluidos ataques [PR-78][PR-94].
7. Límites de alcance y gasto y "freno de emergencia" [PR-78][PR-98][PR-91].

Estos siete principios, junto con los once criterios de la sección "Qué significa control", son la vara de medir de la matriz comparativa.

## Qué dice el libro de Victor Dibia (leído completo, ed. octubre 2025)

El libro da el marco conceptual del artículo: qué es un agente, cuándo conviene un sistema multiagente, qué patrones existen y por qué el control explícito y la aprobación humana importan cuando el agente actúa. Esta tabla recoge, por capítulo, lo que el artículo cita.

| Capítulo y sección | Qué dice el libro (sin añadir nada) | Para qué lo usa el artículo |
| --- | --- | --- |
| Prefacio | Las pipelines dan fiabilidad (cada paso se prueba) pero asumen que la descomposición es conocida y la tarea estable; AutoGen (mayo 2023) nació para que los agentes se autoorganicen conversando; "as the project matured, it evolved into the Microsoft Agent Framework—a production-ready successor" | Origen de la tensión workflow/autonomía y conexión AutoGen → Agent Framework |
| 1.1 y 1.4 | Agente = entidad que razona, actúa (con herramientas), se comunica y se adapta; componentes: modelo, herramientas, memoria (Fig. 1.5); bucle acción-percepción (Fig. 1.6); la decisión "can be driven by generative AI models, predefined logic, or explicit human input" (1.4.2.1) | Definición de agente para no técnicos y base del "qué decide la IA, el código o la persona" |
| 1.5 | Sistema multiagente y orquestación ("how they share information, and who controls the flow of execution"); workflows (orquestación definida) frente a autonomía (orquestación dirigida por IA) | Vocabulario de orquestación |
| 1.7 | Marco de decisión (Fig. 1.8): "Choose the simplest architecture that effectively addresses your requirements"; validado en 10.6 | Justificar un workflow explícito para el ERP |
| 2.1–2.4 | Taxonomía de patrones en un espectro de autonomía; Tabla 2.2 (control y autonomía se mueven a la inversa); "Production reliability critical -> Workflow patterns with explicit task management"; híbridos | Comparar cómo cada producto expone patrones y cuánto control dejan |
| 2.5 | Gestión de tareas: terminación (presupuesto, semántica, señal externa) y delegación humana basada en reglas ("financial transactions exceeding $10,000") o en el LLM | Diseño del umbral de aprobación del ejemplo |
| 3 (intro, 3.4, 3.5) | Delegation design (autonomía, consecuencias, duración); principios UX: capability discovery, cost-aware action delegation (tres niveles: automático, notificar después, pedir permiso antes), observabilidad y procedencia, interrumpibilidad; escenarios offline de back-office (extraer datos de correos y actualizar un CRM) | Explicar por qué un agente sobre un ERP necesita aprobaciones y trazas visibles |
| 4.1–4.6 | Principios (async, streaming, serialización, cancelación, clases base contra el lock-in); bucle de ejecución de 5 pasos; cliente de modelo intercambiable; salida estructurada como "the key to reliable agents"; tool calling; herramientas genéricas frente a específicas ("constrain the agent's behavior, enabling predictability") | Esqueleto del agente "en pizarra" y recorrido de una petición |
| 4.7–4.8 | Memoria a corto plazo (historial) y largo plazo (RAG); gestionada por la aplicación o por el agente ("control versus convenience") | Pieza "hilo y memoria" |
| 4.9–4.10 | Middleware intercepta llamadas al modelo y a herramientas y puede bloquearlas; usos: logging, filtrado/PII, límites de coste, "Audit and Compliance"; OpenTelemetry con convenciones GenAI, contenido opt-in | Piezas "middleware" y "observabilidad" y criterio de trazabilidad |
| 4.11–4.13 | Agentes como herramientas (aislamiento de contexto); context engineering; humanos en el bucle: herramientas con approval_mode, el agente se detiene y reanuda con estado serializable | Pieza "humano en el bucle" y comparación de aprobaciones por producto |
| 6 | Workflows = grafos (pasos tipados, aristas condicionales, fan-out/fan-in), validación previa, ejecución determinista, serialización y checkpointing con hash de estructura; "excels for ... approval workflows, and any scenario where audit trails and deterministic execution are essential" (6.8) | Pieza "workflows" y argumento de determinismo |
| 7 | Bucle del orquestador (seleccionar, preparar contexto, ejecutar, actualizar, comprobar terminación); terminaciones componibles; round-robin, selección por IA y basada en plan (2+ llamadas por paso); nota: las decisiones de un framework "become slightly opaque" | Patrones automáticos y su coste |
| 9 | Por qué usar un framework (mantenimiento y componentes estándar); diez capacidades (DX, async, observabilidad, estado, configuración declarativa, guardrails/middleware, patrones, producción/seguridad, evaluación, ecosistema); matriz ponderada; "there is no universally 'best' framework" (9.5); Agent Framework "provides seamless Azure AI Foundry integration" (9.4) | Criterios de la matriz comparativa y respuesta a la pregunta central |
| 10 | Desarrollo guiado por evaluación (5 pasos); trayectorias; métricas deterministas frente a jueces LLM; la observabilidad convierte cada ejecución en dato de evaluación; multiagente usa 43x más tokens que el modelo directo | Criterio "evaluación y pruebas" |
| 11 | Diez fallos en producción; herramientas de dominio y pocas; patrón equivocado (Tabla 11.1); delegación a humanos por riesgo (Tabla 11.2: lectura → automático; irreversible o costoso → aprobación); "You probably don't need a multi-agent system" | Diseño del ejemplo y advertencias |
| 12 | MCP (herramientas, recursos, prompts; elicitation, sampling; OAuth 2.1, sin token passthrough) y A2A (Agent Card, tareas con estados); "organization-level governance ... still lives outside the protocol"; "MCP gives you visibility and control over individual capability calls. A2A lets you delegate entire tasks" | Sección de protocolos y conexión con el MCP de Business Central |
| 13 | "Risk scales with action capability"; Regla de dos de Meta (entradas no fiables, datos sensibles, cambiar estado: no las tres sin humano); defensa por middleware (entrada, autorización de herramientas, salida); lista de despliegue (mínimo privilegio, auditoría, umbrales de supervisión, revisión periódica) | Definición de "control" y criterios de seguridad para el ERP |
| 14 y 15 | Caso determinista (barato antes que caro; salida estructurada; sin puntuaciones de confianza; tests con mocks) y caso autónomo (herramientas + prompts + memoria) | Decisiones de diseño del repositorio |
| Epílogo | Historia de AutoGen (ConversableAgent, v0.4 con modelo de actores en enero 2025, fork AG2, Core/AgentChat); Semantic Kernel aportó capacidades empresariales y .NET; la confusión entre ambos llevó al Agent Framework, "a major version revision"; fases: hoy dominan los workflows, luego autonomía; "scaffolds ... become more of control points for human oversight" | Sección "por qué nace" y conclusiones |
| Glosario | Definiciones de agente, contexto, bucle, middleware, checkpointing, human-in-the-loop, MCP, A2A, salida estructurada, trayectoria | Glosario del artículo |

## Qué significa "control" cuando el agente actúa sobre un ERP

"Control" se descompone aquí en once criterios con una pregunta observable cada uno; la matriz de la sección siguiente puntuá cada producto contra estas preguntas, no contra impresiones. Los criterios parten de la lista de Javier y la amplían con lo que el libro pide a un framework (cap. 9) y a un despliegue responsable (cap. 13).

| N.º | Criterio | Pregunta concreta que se responde con evidencia | Cómo se mide |
| --- | --- | --- | --- |
| 1 | Modelo | ¿Puedo elegir modelo y proveedor por agente, fijar parámetros (temperatura, tokens máximos, formato de salida) y cambiar de proveedor sin reescribir el agente? | N.º de proveedores admitidos; parámetros expuestos; cambio de modelo = cambio de una línea o de una configuración |
| 2 | Herramientas y datos | ¿Decido yo exactamente qué puede leer y qué puede escribir en Business Central, por entidad y por operación, y puedo validar o bloquear cada llamada con código antes de que ocurra? | Lista cerrada de herramientas por agente; interceptación de argumentos antes de ejecutar; separación lectura/escritura |
| 3 | Identidad y permisos | ¿El agente actúa con identidad propia y conjuntos de permisos mínimos en BC, de modo que el registro de cambios muestra "lo hizo el agente X" y no "lo hizo el usuario que lo creó"? | Identidad (app de Entra o Agent ID) distinta de la del creador; permission sets asignables; quién consta como autor del cambio |
| 4 | Determinismo | ¿Puedo fijar en código el orden de los pasos y las condiciones de paso (grafo con aristas evaluadas por código), y limitar la IA a los pasos donde hace falta? | Proporción de decisiones tomadas por código frente a por el modelo; validación del grafo antes de ejecutar; reproducibilidad con mocks |
| 5 | Aprobaciones humanas | ¿Puedo poner puntos de parada por herramienta y por regla (p. ej. importe), que sobrevivan horas o días y se reanuden con el estado intacto, y decidir quién aprueba y dónde? | Aprobación por herramienta; por umbral calculado en código; persistencia (checkpoint); canal de aprobación configurable |
| 6 | Trazabilidad, auditoría y observabilidad | ¿Queda registrado quién hizo qué, con qué datos, qué herramienta llamó con qué argumentos, qué se aprobó y cuánto costó, en un estándar exportable a mi sistema de monitorización? | OpenTelemetry (trazas GenAI); tokens y coste por ejecución; exportación a Application Insights u otro backend; retención y correlación con el registro de cambios de BC |
| 7 | Evaluación y pruebas | ¿Puedo probar herramientas y flujo sin tocar BC (mocks), ejecutar un conjunto de casos antes de cada cambio y detectar regresiones? | Tests unitarios y de integración; evaluadores; modo demo sin ERP; integración continua |
| 8 | Coste y previsibilidad | ¿Sé cuánto cuesta cada ejecución y puedo poner topes (iteraciones, tokens, presupuesto) antes de que se gaste? | Unidad de facturación (tokens, créditos, mensajes); límites configurables; coste visible por tarea |
| 9 | Ejecución, despliegue y gobierno | ¿Dónde corre el agente (mi contenedor, Azure, SaaS de Microsoft), quién lo administra y a qué piezas de gobernanza del tenant se conecta (Entra, Purview, Agent 365)? | Opciones de hosting; consola de administración; región de datos; integración con gobernanza |
| 10 | Dependencia, código abierto y portabilidad | ¿El código es abierto, el agente es portable a otro runtime o nube y usa protocolos abiertos (MCP, A2A)? | Licencia; exportabilidad; protocolos |
| 11 | Esfuerzo y perfil | ¿Qué perfil hace falta para construirlo y mantenerlo, y cuánto cuesta el primer prototipo y las actualizaciones? | Low-code frente a pro-code; tiempo a primer prototipo; carga de mantenimiento ante cambios de API |

Dos aclaraciones de método. Primera: "más control" no es "mejor" por sí mismo; el libro insiste en que control y autonomía se mueven a la inversa (Tabla 2.2) y en elegir la arquitectura más simple que resuelva el problema (1.7), así que la pregunta correcta es cuánto control exige el ERP, no cuánto ofrece la herramienta. Segunda: el control del agente y el control del ERP son capas distintas; aunque el agente sea una caja negra, Business Central sigue aplicando sus permisos, validaciones y registro de cambios a cualquier escritura por API, y eso vale para las tres opciones.

## Matriz comparativa: Copilot Studio, Microsoft Foundry y Agent Framework frente a los criterios de control

Escala: Alto = el equipo decide y puede verificarlo en código o configuración propia; Medio = se decide dentro de los límites que marca el producto; Bajo = lo decide el producto o Microsoft. Cada celda indica la evidencia; "Foundry" se refiere a prompt agents salvo que se diga "hosted" (un hosted agent escrito con Agent Framework hereda la columna del framework más lo que añade Foundry).

| Criterio | Copilot Studio | Microsoft Foundry | Agent Framework |
| --- | --- | --- | --- |
| 1. Modelo | Bajo: catálogo cerrado, modelo por defecto que cambia cuando Microsoft decide, sin parámetros documentados [CS-51][CS-42] | Alto: más de 10.000 modelos, parámetros, tipos de despliegue y residencia de datos [FY-25] | Alto: cualquier proveedor (OpenAI, Azure OpenAI, Foundry, Anthropic, Ollama local, Bedrock, Gemini, Mistral); cambiar de modelo es cambiar el cliente; parámetros y formato de salida en `options` [AF-23][AF-21] |
| 2. Herramientas y datos | Alto en qué herramientas; Bajo en validar cada llamada: conectores, MCP y REST con interruptor por herramienta y DLP, pero sin código que inspeccione los argumentos antes de ejecutar [CS-36][CS-39] | Medio-alto: MCP con aprobación por llamada y `allowed_tools`, OpenAPI, toolboxes; la validación programática solo en hosted agents [PR-37][FY-8] | Alto: lista cerrada de `@tool`, `FunctionMiddleware` que ve y puede bloquear argumentos, `max_invocations`, MCP con `allowed_tools`; la herramienta de escritura la escribe el equipo [AF-20][AF-18][AF-26] |
| 3. Identidad y permisos en BC | Medio: Entra Agent ID automática; pero ante BC actúa como el usuario conectado (MCP) o con credenciales del creador (autónomos); sin service principal documentado [CS-63][CS-79][BC-42] | Medio-alto: identidad de Entra por agente; ante BC, token de usuario (MCP) o funciones propias con app S2S en hosted agents [FY-30][BC-58] | Alto en BC, Bajo en el tenant: app de Entra propia con conjuntos de permisos mínimos (S2S) y el registro de cambios muestra esa app; pero no recibe Entra Agent ID por sí solo (lo obtiene al desplegar en Foundry o con el SDK de Agent 365, alfa) [BC-58][FY-59][AF-68] |
| 4. Determinismo | Medio: orquestación clásica por temas es determinista; la generativa es probabilística; en el GitHub Copilot harness no se configura la orquestación [CS-9][CS-7] | Bajo en prompt agents (bucle del servicio); los workflows declarativos se retiran el 01-12-2026 [FY-8][FY-22] | Alto: grafo con aristas y `switch_case` evaluados en código, validación previa, reproducible con mocks; la IA solo en los nodos donde se la invoca [AF-40][AF-44] |
| 5. Aprobaciones humanas | Bajo-medio: "Request information" (vista previa, solo Outlook), supervisión de computer use, traspasos; sin pausa genérica con estado [CS-76] | Medio: aprobación por llamada MCP (`require_approval`) y paso de aprobación humana en operaciones largas (vista previa) [PR-37][FY-17] | Alto: `approval_mode` por herramienta, `request_info` en workflow con umbral calculado en código, checkpoint en fichero/Cosmos para reanudar horas después, canal de aprobación a elección del equipo [AF-22][AF-41][AF-4] |
| 6. Trazabilidad y observabilidad | Medio: Purview no desactivable, transcripciones 28–29 días, App Insights por agente (no OTel); OTel en vista previa [CS-68][CS-73][CS-74] | Alto: OpenTelemetry + Application Insights GA, Control Plane con coste y tokens [FY-27][FY-28] | Alto en estándar, Medio en coste: OTel GenAI (spans de agente, modelo y herramienta; métricas de tokens) exportable a cualquier backend; el coste monetario lo calcula la aplicación [AF-9] |
| 7. Evaluación y pruebas | Medio: evaluación GA (conjuntos, multi-turno, API en vista previa); sin mocks de BC | Alto: evaluadores GA, evaluación continua, red teaming [FY-27] | Alto en pruebas, Medio en evaluadores: tests unitarios con BC simulado y modelo simulado (verificado en el ejemplo: 56 pruebas sin modelo ni ERP reales, y ejecución contra un sandbox real el 18-10-2026 que destapó siete fallos invisibles para la demo), evaluación local experimental, evaluadores de Foundry opcionales [AF-77][VER] |
| 8. Coste y previsibilidad | Medio: créditos con tarifas fijadas (acción de agente 5, premium 15), límites por agente, corte al 125 %; el nuevo harness factura desde el diseño [CS-16][CS-71] | Medio-alto: tokens más herramientas, hosted por vCPU/GiB-hora (tarifas oficiales no visibles) [FY-32] | Alto: solo tokens del proveedor elegido; límites de iteraciones, llamadas y tokens en código (`FunctionInvocationConfiguration`, middleware de presupuesto) [AF-20][AF-18] |
| 9. Ejecución, despliegue y gobierno | Bajo en hosting (SaaS), Alto en gobierno de tenant (PPAC, Entra, Agent 365, Purview) [CS-61][CS-63] | Alto: hosted agents GA con red privada, identidad, RBAC, Agent 365, Purview (OBO) [FY-20][FY-61] | Alto en libertad (contenedor propio, Azure Functions, Foundry), Bajo en gobierno integrado: nada de serie; Agent 365 SDK en alfa, Purview middleware en beta [AF-30][AF-80] |
| 10. Dependencia y portabilidad | Bajo: runtime, harness, modelos y canales propietarios; definición exportable en YAML; MCP y A2A para integrar [CS-17] | Medio: hosted agents son contenedores portables; el runtime de prompt agents es propietario [FY-20] | Alto: MIT, cualquier modelo, cualquier nube; MCP estable, A2A beta; riesgo distinto: cambios semanales de API [AF-1][AF-62] |
| 11. Esfuerzo y perfil | Bajo esfuerzo inicial (maker), alto en gobierno; sin programar | Medio: portal para prompt agents; desarrollador para hosted | Alto: desarrollador Python o .NET y mantenimiento ante cambios de API; cada nombre de la API hay que comprobarlo contra la versión instalada [AF-13] |

### Lectura por filas

- Agent Framework gana en los criterios que el libro asocia a producción fiable (determinismo, aprobaciones con estado, validación de cada llamada, pruebas con mocks, observabilidad estándar, portabilidad) y pierde en lo que no es código: gobierno integrado del tenant, identidad de agente de serie, esfuerzo y estabilidad de API.
- Foundry gana en modelo, observabilidad, evaluación e identidad, y es el complemento natural del framework (hosting, trazas, Entra); por sí solo, con prompt agents, no da el flujo determinista ni las aprobaciones por regla.
- Copilot Studio gana en tiempo a primer prototipo, canales y gobierno de tenant; pierde en modelo, determinismo (especialmente en el harness nuevo), validación programática de llamadas y aprobaciones persistentes; frente a Business Central siempre actúa con un usuario, lo que es una ventaja de auditoría y un límite para procesos desatendidos.
- Ninguna de las tres sustituye la capa de control de Business Central (permisos, validaciones de AL, registro de cambios), que se aplica igual a las tres.

## Respuesta argumentada a la pregunta central

La pregunta: ¿es Microsoft Agent Framework la mejor manera de crear agentes cuando se necesita control total sobre un agente que actúa sobre un ERP como Business Central, o lo son Copilot Studio o Microsoft Foundry, o una combinación?

### Respuesta corta

La hipótesis de partida se confirma solo en parte. Con la evidencia recogida, Agent Framework es la mejor base para el agente cuando el requisito es control verificable sobre su comportamiento (qué modelo, qué herramientas, qué argumentos, en qué orden, con qué aprobación y con qué traza), pero no es "la mejor manera" por sí solo ni en todos los casos: "control total" no existe en ninguna de las tres opciones, el framework no aporta identidad ni gobierno del tenant, y hay escenarios en los que Copilot Studio o un agente nativo de Business Central son la elección correcta. La respuesta que sostiene la evidencia es una combinación con reparto de papeles: Agent Framework para la lógica del agente, Foundry (opcional pero recomendable) para ejecutarlo con identidad, trazas y evaluación, y los controles propios de Business Central como última línea; Copilot Studio cuando el agente conversa con una persona que ya está dentro del tenant y actúa con su identidad.

### Argumentos a favor de la hipótesis

1. En los criterios que el libro vincula a producción fiable, el framework es el único de los tres donde el equipo posee la decisión: grafo determinista con condiciones evaluadas en código (cap. 6; `WorkflowBuilder`), aprobación por herramienta y por regla con estado persistente (cap. 4.13 y 2.5; `approval_mode`, `request_info`, checkpoints), middleware que ve y bloquea cada llamada (cap. 4.9; `FunctionMiddleware`), salida estructurada (cap. 4.5) y trazas OpenTelemetry con convenciones GenAI (cap. 4.10). Todo ello verificado en la versión 1.22.0 [AF-40][AF-22][AF-41][AF-18][AF-21][AF-9][VER].
2. Es la única opción en la que un agente desatendido puede actuar sobre BC con una identidad de aplicación propia y permisos mínimos (API v2.0 con credenciales de cliente, sin licencia de usuario y sin SUPER), de modo que el registro de cambios de BC muestra a esa aplicación y no al usuario que creó el agente. Copilot Studio actúa como el usuario conectado o con las credenciales del creador, y el servidor MCP de BC solo admite flujo delegado [BC-58][BC-42][CS-79].
3. La dirección de Microsoft apunta al framework como capa pro-code: AutoGen archivado, Semantic Kernel en mantenimiento con la recomendación explícita de empezar proyectos nuevos en Agent Framework, los workflows declarativos de Foundry retirados el 01-12-2026 a favor del framework, y hosted agents de Foundry con el framework como "recommended orchestration layer" [SK-40][SK-14][SK-12][FY-22][FY-35].
4. Coincide con el principio de Nadella de que los controles deben estar fuera del modelo: en el framework, las reglas de negocio, los umbrales y las aprobaciones son código que el modelo no puede alterar [PR-78].

### Argumentos en contra o que matizan la hipótesis

1. "Control total" es una expresión que la evidencia no respalda para ninguna opción: el modelo sigue siendo probabilístico, la inyección de prompt es un problema abierto reconocido por OpenAI y por la taxonomía de Microsoft, y la aprobación humana es el control más eludido en pruebas de red teaming. Lo que sí es alcanzable es control verificable sobre el perímetro: qué puede tocar el agente y qué necesita una firma humana [PR-105][PR-90][PR-94].
2. El framework no da gobierno del tenant: sin Foundry o sin el SDK de Agent 365 (alfa), un agente de Agent Framework no tiene Entra Agent ID, no aparece en el registro de Agent 365 y no entra en las políticas de Purview; y Purview solo aplica políticas con token de usuario, así que un agente autónomo con identidad propia queda fuera de ellas en cualquier opción [FY-59][AF-68][FY-61]. Si el criterio de control que más pesa es "que el departamento de seguridad vea y gobierne el agente como ve a un usuario", Copilot Studio y Foundry lo resuelven de serie y el framework no.
3. Cuando el agente trabaja con una persona delante (un comercial que pregunta por un cliente y crea un pedido desde Teams), la identidad del usuario es el mejor control posible: BC aplica los permisos de esa persona y el registro de cambios la muestra. Para ese caso, Copilot Studio con el servidor MCP de BC (hosts preautorizados, lectura por defecto, escrituras habilitadas API a API) da más auditoría por usuario y mucho menos esfuerzo que un agente propio [BC-40][BC-41][CS-31].
4. Para el proceso concreto del ejemplo (pedidos de venta por correo) Microsoft ya vende un agente nativo con revisión humana integrada, más de 70 casos de prueba y coste conocido; el libro recuerda que "you probably don't need a multi-agent system" y que conviene elegir la arquitectura más simple (cap. 11 y 1.7). Construir un agente propio solo se justifica cuando el proceso sale de los límites del nativo (otros canales, otras entidades, reglas propias, integración con sistemas externos, idioma de las instrucciones) [BC-5][BC-72].
5. El coste de control del framework es real: API que cambia cada semana con rupturas incluso en paquetes estables, guías de migración con nombres obsoletos, sin política de soporte a largo plazo con plazos, y ningún ejemplo oficial de Agent Framework con Business Central [AF-62][AF-13][BC-77]. Cada nombre de la API debe verificarse contra la versión instalada, como se ha hecho aquí.
6. Foundry por sí solo no compite en control del flujo: sus prompt agents tienen el bucle del servicio y su orquestación declarativa se retira; su valor está en lo que añade al framework (modelos, identidad, trazas, evaluación, hosting) [FY-8][FY-22][FY-27].

### Conclusión operativa

- Agente desatendido que escribe en BC con reglas propias y aprobaciones por importe: Agent Framework (workflow + middleware + aprobación con checkpoint) con escritura por API v2.0 bajo identidad de aplicación mínima; desplegado en Foundry (hosted agent) si se quiere identidad de Entra, trazas en Application Insights y evaluación sin construirlas; registrado en Agent 365 si la organización lo exige. Es la combinación que mejor cumple los once criterios y los siete principios.
- Asistente conversacional para usuarios del tenant que leen y, con su propia identidad, escriben en BC: Copilot Studio con el servidor MCP de BC; aceptar su menor control sobre modelo y flujo a cambio de gobierno integrado y rapidez.
- Proceso que un agente nativo de BC ya cubre: usarlo, y reservar el desarrollo propio para lo que no cubre.
- Lo que contradice la hipótesis tal como estaba formulada: el framework no es "la mejor manera" aislada ni para todo; es la mejor base para el control del comportamiento, dentro de una combinación, y solo cuando el proceso justifica un agente propio.

## Verificación del ejemplo contra un sandbox real (18-10-2026)

El ejemplo práctico ([agente-pedidos-business-central](https://github.com/JavierCavaGonzalez/agente-pedidos-business-central), etiqueta `v0.1.0`, Python, `agent-framework==1.22.0`, licencia MIT, 56 pruebas) se ejecutó el 18 de octubre de 2026 contra un sandbox real de Business Central y un modelo real. Esta sección resume lo que enseñó; el detalle, ejecución por ejecución, está en `docs/notas-de-construccion.md` del repositorio.

### Configuración

- Business Central: sandbox TEST29 con los datos de demostración de CRONUS ES (nombres de clientes y artículos en español). Registro de aplicación en Microsoft Entra ID con el permiso de aplicación `API.ReadWrite.All` y consentimiento de administrador; en Business Central, página «Aplicaciones de Microsoft Entra» con el Id. de cliente, estado habilitado y los conjuntos de permisos `D365 BASIC`, `D365 READ` y `D365 SALES DOC, EDIT` (nunca `SUPER`). Autenticación servicio a servicio (client credentials) y API v2.0 estándar, sin extensiones AL [BC-58].
- Modelo: Azure OpenAI, despliegue `gpt-4.1-mini` en Sweden Central, elegido porque el código fija `temperature` en las opciones por defecto de cada agente y la familia GPT-5 y los modelos razonadores no admiten ese parámetro.
- Entorno: Python 3.13 (el repositorio también está probado con 3.14); la instalación tarda unos diez minutos porque `agent-framework` trae todos los conectores (unos 200 paquetes).

### Pedidos creados

| Pedido | Correo | Recorrido | Llamadas al modelo | Tokens (entrada / salida) | Coste estimado |
| --- | --- | --- | --- | --- | --- |
| 101021, Adatum Corporation, 939,40 € | `05_cronus_es_pequeno.txt` (10 × Lámpara ÁMSTERDAM, 2 × Silla inv. PARÍS, negra; ref. ADT-8102) | Directo, sin aprobación (por debajo del umbral de 3.000 €) | 3 (2 intérprete + 1 redactor) | 3.227 / 359 | 0,0093 € |
| 101022, Trey Research, 3.781,40 € | `06_cronus_es_grande.txt` (3 × Escritorio ATENAS, 4 × Silla giratoria LONDRES, azul; ref. TRY-5531; el correo publicado en el repositorio lleva ya TRY-5532) | Parada de aprobación con checkpoint (`--aprobar pendiente`) y reanudación en otro proceso; comprobado por API que durante la espera no se creó ningún pedido | 2 hasta la parada + 1 al reanudar | 2.930 / 257 + 283 / 100 | 0,0079 € + 0,0014 € |
| 101023, Trey Research, 3.781,40 € | El mismo correo con la ref. TRY-5532 | Verificación de la idempotencia: con la ref. TRY-5531 repetida no se creó nada («Ya existe el pedido 101022…»); con la nueva sí, y la auditoría registró la escritura con sus líneas | 3 | 3.213 / 354 | 0,0093 € |

Tarifas por defecto del ejemplo: 2 € por millón de tokens de entrada y 8 € por millón de salida, por encima de la tarifa real de Azure. Cada pedido son tres llamadas al modelo y unos 0,009 €; el día entero de pruebas con el modelo real (dieciséis ejecuciones registradas, varias con más de un comando) sumó 40.710 / 3.120 tokens y 0,1064 €. El total que devuelve Business Central coincidió en los tres pedidos con el calculado por el código.

### Lo que la demo y las pruebas con dobles no podían enseñar

Las 22 pruebas iniciales (modelo simulado y ERP simulado) pasaban. El primer día contra el sistema real aparecieron estos fallos, todos del código del ejemplo o del protocolo del ERP, ninguno del framework. Cada uno tiene ahora su prueba (56 en total) y su nota.

| Hallazgo | Síntoma | Causa | Corrección y prueba |
| --- | --- | --- | --- |
| Lector de `.env` | `AGENTE_SOLO_LECTURA=1   # …` no activaba el modo solo lectura; `AGENTE_MAX_LLAMADAS_MODELO` rompía al convertir a entero | El lector casero no quitaba los comentarios de final de línea; ninguna prueba cargaba un `.env` | `_valor_env` (como `python-dotenv`), `.env.example` sin comentarios tras los valores, `tests/test_entorno.py` |
| Asistente de chat en JSON | Tras aprobar, `gpt-4.1-mini` respondía con el objeto estructurado en lugar de confirmar el pedido; corregido, pedía confirmación en el chat antes de llamar a la herramienta | Heredaba las instrucciones del intérprete; el simulado no leía las instrucciones | `prompts/asistente.md` (la aprobación de la herramienta es la única confirmación), el simulado obedece `options["instructions"]`, prueba en `test_chat_aprobacion.py` |
| Aprobación sin terminal | `EOFError` en `input()`; cualquier «s» por tubería aprobaba | `isatty()` engaña en Windows (`NUL`) y `procesar` no comprobaba nada | `preguntar_aprobacion()` fail-closed: sin terminal se deniega y se audita (`evento: aprobacion_denegada`); desatendido, `--aprobar` con `si`, `no` o `pendiente`; `tests/test_aprobacion_consola.py` |
| HTTP 501 | «The 'OR' operator is not supported on distinct fields on an OData filter» en las lecturas | La API v2.0 no admite `or` entre campos distintos; el ERP simulado filtra en memoria | Filtros separados (nombre y, si parece un código, número); lecturas con errores como `{"error": …}`; auditoría también de las herramientas que fallan; `tests/test_cliente_api.py` con `httpx.MockTransport`, `tests/test_errores_erp.py` |
| `blocked` como `_x0020_` | Todos los clientes parecían bloqueados | La API devuelve el valor en blanco del enum con el espacio codificado | `_decodificar_enum` en `cliente_api.py`; un bloqueo real (`Ship`, `Invoice`, `All`) se conserva |
| `contains` sensible a mayúsculas y tildes | «AMSTERDAM» no encontraba «Lámpara ÁMSTERDAM» (CRONUS ES en español) | Comportamiento del filtro de la API; los datos de la demo están en inglés | Búsqueda palabra por palabra tolerante (`_buscar_por_palabras`, `_plegar`) y una línea en los prompts para reintentar en español y con tildes |
| Auditoría, checkpoints e idempotencia | Los pedidos creados desde el workflow no constaban en la auditoría; `pendientes` mostraba aprobaciones resueltas y `reanudar` las habría repetido; `--aprobar pendiente` no imprimía el coste | La escritura del workflow no pasaba por el middleware; nada marcaba un checkpoint como resuelto | Auditoría de escrituras en el cliente del ERP (`ClienteBC.crear_pedido_venta`, `evento: escritura_erp`); `checkpoints/aprobaciones_resueltas.jsonl`, `aprobaciones_pendientes()`, `motivo_para_no_reanudar()`; `PedidoDuplicado` por cliente y referencia externa, verificado contra el ERP; `tests/test_auditoria_checkpoints.py` |

Lectura para el informe: confirma el capítulo 10 del libro (desarrollo guiado por evaluación, 10.2; «observability enables evaluation», 10.3.2; «Benchmarks ≠ Your Task», 10.6) y la secuencia que recomienda el README del ejemplo: modo demo, después solo lectura contra el sandbox y, al final, la escritura. También matiza el criterio 7 de la matriz: las pruebas con dobles miden lo que se supuso del ERP, no lo que el ERP hace; la API simulada de las pruebas se ajustó después a lo medido en la real.

## Puntos dudosos, cosas que cambian con rapidez y lo que no se ha podido verificar

### Dudosos o volátiles (reverificar antes de publicar o al cabo de unas semanas)

1. Agent Framework cambia cada semana y rompe compatibilidad incluso en paquetes "released" (1.13.0, 1.15.0, 1.22.0); el código del ejemplo está verificado contra Python 1.22.0 y debe fijarse esa versión [AF-62].
2. `Microsoft.Agents.AI.Foundry` (.NET) solo tiene versiones preview tras un 1.5.0 estable; el paquete Python `agent-framework-foundry-hosting` sigue en prerelease aunque el servicio de hosted agents sea GA (ninguna fuente da el día exacto de esa GA) [AF-72][AF-58][FY-20].
3. Estado GA del servidor MCP de Business Central como tal: el plan original lo deja sin fecha, las mejoras de 2026 salieron como GA, pero la documentación de octubre de 2026 etiqueta "Data Query Tools (Preview)" y la herramienta de Copilot Studio "(Preview)" [BC-39][BC-45][BC-41][BC-43].
4. Agent Designer / Custom Agent de BC: GA prevista para octubre de 2026 en el plan, pero ausente de "What's new 29.0"; tratar como vista previa [BC-16][BC-18].
5. Expense Agent en España y validación en español del Payables Agent: la tabla de idiomas lista es-ES, la página de configuración dice "validado en inglés"; confirmar antes de prometerlo [BC-9][BC-13].
6. Catálogo de modelos de Copilot Studio: cambia mensualmente; la tabla oficial del 14-10-2026 no lista Claude Sonnet 5 aunque otras páginas lo mencionen [CS-51].
7. Fecha de GA del GitHub Copilot harness (agosto según terceros, septiembre según el blog) y fecha de la identidad automática de Entra en Copilot Studio (mayo o julio de 2026 según la página) [CS-5][CS-6][CS-63].
8. Cabecera `TenantId` del MCP de BC: la visión general la exige y la página de configuración dice que no es necesaria [BC-40][BC-41].
9. Precios: todos en USD y "sujetos a cambio"; las tarifas de hosted agents de Foundry solo constan por un tercero; la facturación de agentes propios de BC "se anunciará" [FY-32][BC-72].
10. Qué revisión de la especificación MCP implementa cada producto de Microsoft (ninguno lo declara); el registro MCP oficial sigue en vista previa; el SDK .NET de A2A solo en preview [PR-30][PR-48].
11. Soporte completo de A2A 1.0 en Agent Framework: muestras en el repositorio, pero sin nota de versión que lo declare [AF-27].
12. Atribución del blog "sn scratchpad" a Satya Nadella: resuelta. Autoría confirmada el 18-10-2026: el ensayo está publicado también como artículo de X en la cuenta @satyanadella, con el mismo texto y la frase textual [PR-78][PR-80].
13. Fin de los planes de lanzamiento de Dynamics 365 y Power Platform (septiembre de 2026): las fechas de los ítems de octubre de 2026 proceden de espejos del roadmap de Microsoft 365 [BC-24][BC-T5].
14. Soporte de Semantic Kernel: solo compromiso cualitativo ("foreseeable future", al menos un año tras la GA del framework, es decir, al menos hasta abril de 2027 por inferencia) [SK-14]. El "archivado" de AutoGen consta en el README, no se ha confirmado la marca de archivo del repositorio en GitHub [SK-40].

### No verificado (se dice como tal en el artículo o se omite)

- Ninguna guía, ejemplo o referencia oficial de Microsoft de un agente de Agent Framework o de Foundry conectado a Business Central, ni relación documentada entre Entra Agent ID / Agent 365 y los permisos o usuarios de agente de BC [BC-77][FY-48].
- Existencia de una API REST para crear tareas de agente en BC desde fuera (solo AL documentado) [BC-30][BC-31].
- Si un agente de Copilot Studio puede exponerse como servidor A2A; uso de service principals en conectores de Copilot Studio; parámetros de modelo en Copilot Studio [CS-46][CS-79][CS-51].
- Integración vigente entre Agent Framework y el Microsoft 365 Agents SDK; herramientas OpenAPI o Logic Apps en `FoundryChatClient`; soporte de ACP; importación de workflows de Copilot Studio al framework declarativo [AF-66][AF-24][AF-48].
- Tarifas oficiales de hosted agents; existencia de un "Agent Catalog" en Foundry con ese nombre [FY-32].
- Postmortems primarios de los incidentes de Replit, Amazon Q, Gemini CLI y PocketOS/Railway; una formulación de "insider risk" anterior al 10-10-2026 [PR-108][PR-111].
- El artículo de Bert Verbeek sobre Agent Framework y el MCP de BC (no accesible) [BC-T8].
- La guía de licencias online actual de BC en el enlace oficial (se usó la página de guidance y una copia de agosto de 2026 alojada por un tercero) [BC-67][BC-69].

## Fuentes (todas consultadas el 17 de octubre de 2026)

Fecha de consulta de todas las fuentes: 2026-10-17, salvo que la entrada indique otra fecha de publicación entre paréntesis. Las fuentes de terceros se señalan como tales; el resto son oficiales (Microsoft Learn, blogs oficiales de Microsoft, repositorios oficiales, especificaciones de los protocolos, organismos y fabricantes citados). Los códigos entre corchetes son los que se usan en el texto del informe.

### Libro y verificación propia

- [Libro] Victor Dibia, *Designing Multi-Agent Systems* (edición leída completa, incluidos epílogo y glosario; archivo EPUB aportado por Javier). Se cita por capítulo y sección.
- [VER] Verificación práctica propia. El 17-10-2026: instalación de `agent-framework` 1.22.0 (PyPI) en un entorno limpio, lectura del código fuente del paquete y del repositorio microsoft/agent-framework (rama main) y ejecución de una prueba de humo con cliente de modelo simulado: agente con herramienta, aprobación de herramienta (`approval_mode`), salida estructurada (`response_format`), workflow con `request_info`, checkpoint en fichero y reanudación. El 18-10-2026: el repositorio del ejemplo, [agente-pedidos-business-central](https://github.com/JavierCavaGonzalez/agente-pedidos-business-central) (etiqueta `v0.1.0`, 56 pruebas), ejecutado contra un sandbox real de Business Central (TEST29, CRONUS ES) con Azure OpenAI `gpt-4.1-mini`: pedidos 101021, 101022 y 101023, con cada hallazgo en `docs/notas-de-construccion.md`. Los nombres de clases, métodos y parámetros citados en el informe proceden de esa verificación.

### Microsoft Agent Framework [AF-n]

- [AF-1] README repo: https://github.com/microsoft/agent-framework
- [AF-2] Overview Learn: https://learn.microsoft.com/agent-framework/overview/agent-framework-overview
- [AF-3] PyPI agent-framework (y API JSON de cada subpaquete, https://pypi.org/pypi/<paquete>/json): https://pypi.org/project/agent-framework/
- [AF-4] Releases GitHub (págs. 1–2 y latest): https://github.com/microsoft/agent-framework/releases ; https://github.com/microsoft/agent-framework/releases?page=2 ; https://github.com/microsoft/agent-framework/releases/latest ; checkpoints: https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints
- [AF-5] Durable extension: https://learn.microsoft.com/en-us/agent-framework/hosting/azure-functions ; https://github.com/microsoft/agent-framework-durable-extension
- [AF-6] NuGet Microsoft.Agents.AI: https://www.nuget.org/packages/Microsoft.Agents.AI ; https://www.nuget.org/packages/Microsoft.Agents.AI/1.0.0
- [AF-7] Perfil NuGet: https://www.nuget.org/profiles/MicrosoftAgentFramework (págs. 1–3)
- [AF-8] FIDES: https://learn.microsoft.com/en-us/agent-framework/agents/security ; https://devblogs.microsoft.com/agent-framework/fides/
- [AF-9] Observabilidad: https://learn.microsoft.com/en-us/agent-framework/agents/observability
- [AF-10] Post 1.0: https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/
- [AF-13] Cambios significativos Python 2026: https://learn.microsoft.com/en-us/agent-framework/support/upgrade/python-2026-significant-changes ; índice: https://learn.microsoft.com/en-us/agent-framework/support/upgrade/
- [AF-14] Harness released: https://devblogs.microsoft.com/agent-framework/the-microsoft-agent-framework-harness-is-now-released/
- [AF-15] Agentes (conceptos): https://learn.microsoft.com/agent-framework/concepts/agents/
- [AF-16] Conversaciones/sesiones: https://learn.microsoft.com/agent-framework/concepts/agents/conversations/
- [AF-18] Middleware: https://learn.microsoft.com/agent-framework/concepts/agents/middleware/
- [AF-19] Running agents: https://learn.microsoft.com/agent-framework/concepts/agents/running-agents
- [AF-20] Function tools: https://learn.microsoft.com/en-us/agent-framework/agents/tools/function-tools
- [AF-21] Structured outputs: https://learn.microsoft.com/en-us/agent-framework/agents/structured-outputs
- [AF-22] Tool approval: https://learn.microsoft.com/en-us/agent-framework/agents/tools/tool-approval
- [AF-23] Model providers: https://learn.microsoft.com/agent-framework/integrations/by-component/model-providers/ ; OpenAI: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/openai
- [AF-24] Foundry (modelos y herramientas alojadas): https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/microsoft-foundry
- [AF-25] Foundry Agent Service (FoundryAgent): https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/agent-services/foundry
- [AF-26] MCP: https://learn.microsoft.com/en-us/agent-framework/agents/tools/local-mcp-tools
- [AF-27] A2A: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/agent-services/a2a
- [AF-29] Channels: https://devblogs.microsoft.com/agent-framework/introducing-agent-and-workflow-channels/
- [AF-30] Hosting get-started: https://learn.microsoft.com/en-us/agent-framework/get-started/hosting
- [AF-31] AG-UI: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/ui/ag-ui/
- [AF-33] DevUI: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/ui/devui/
- [AF-34] Context providers (concepto): https://learn.microsoft.com/en-us/agent-framework/concepts/agents/conversations/context-providers ; índice: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/context-providers/
- [AF-35] Mem0: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/context-providers/mem0
- [AF-36] Redis: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/context-providers/redis
- [AF-37] Group chat: https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/group-chat ; índice: https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/
- [AF-39] Magentic: https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/magentic
- [AF-40] Workflows (conceptos): https://learn.microsoft.com/agent-framework/concepts/workflows/
- [AF-41] Human-in-the-loop: https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop ; capacidades: https://learn.microsoft.com/agent-framework/workflows/
- [AF-42] Executors: https://learn.microsoft.com/en-us/agent-framework/concepts/workflows/executors
- [AF-44] Edges: https://learn.microsoft.com/en-us/agent-framework/concepts/workflows/edges
- [AF-46] Sub-workflows: https://learn.microsoft.com/en-us/agent-framework/concepts/workflows/advanced/sub-workflows
- [AF-47] Visualización: https://learn.microsoft.com/en-us/agent-framework/workflows/visualization
- [AF-48] Declarativo: https://learn.microsoft.com/en-us/agent-framework/workflows/declarative
- [AF-52] Orquestaciones 1.0: https://devblogs.microsoft.com/agent-framework/agent-frameworks-orchestration-patterns-reach-1-0/
- [AF-53] Declarativo 1.0: https://devblogs.microsoft.com/agent-framework/move-agent-orchestration-workflows-out-of-code-with-agent-framework-declarative-workflows-1-0/
- [AF-54] Handoff: https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/handoff
- [AF-55] Aislamiento hosted agents: https://devblogs.microsoft.com/agent-framework/foundry-hosted-agent-isolation-with-microsoft-agent-framework/
- [AF-56] CodeAct: https://devblogs.microsoft.com/agent-framework/codeact-with-hyperlight/
- [AF-58] Hosted agents (concepto Foundry): https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents ; MAF: https://learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent
- [AF-59] Go: https://github.com/microsoft/agent-framework-go
- [AF-60] PACKAGE_STATUS.md: https://raw.githubusercontent.com/microsoft/agent-framework/main/python/PACKAGE_STATUS.md
- [AF-62] CHANGELOG Python: https://raw.githubusercontent.com/microsoft/agent-framework/main/python/CHANGELOG.md
- [AF-63] Módulo observability.py (main y etiquetas python-1.0.0b251211/b251216): https://raw.githubusercontent.com/microsoft/agent-framework/main/python/packages/core/agent_framework/observability.py ; PR #2782: https://github.com/microsoft/agent-framework/pull/2782
- [AF-66] M365 Agents SDK: https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/
- [AF-67] Agent 365 SDK: https://learn.microsoft.com/en-us/microsoft-agent-365/developer/agent-365-sdk
- [AF-68] PyPI Agent 365 tooling ext.: https://pypi.org/project/microsoft-agents-a365-tooling-extensions-agentframework/
- [AF-72] NuGet Foundry: https://www.nuget.org/packages/Microsoft.Agents.AI.Foundry
- [AF-73] NuGet A2A: https://www.nuget.org/packages/Microsoft.Agents.AI.A2A
- [AF-77] Evaluación Foundry: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/evaluation/microsoft-foundry
- [AF-78] Safety: https://learn.microsoft.com/agent-framework/concepts/agents/safety
- [AF-79] Agent Hooks: https://learn.microsoft.com/en-us/agent-framework/agents/agent-hooks
- [AF-80] Purview: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/middleware/purview
- [AF-83] Discussions Announcements: https://github.com/microsoft/agent-framework/discussions/categories/announcements

### Semantic Kernel y AutoGen [SK-n]

- [SK-1] Hello, Semantic Kernel! (17-03-2023) https://devblogs.microsoft.com/agent-framework/hello-world/
- [SK-3] Semantic Kernel v1.0.1 has arrived (19-12-2023) https://devblogs.microsoft.com/agent-framework/semantic-kernel-v1-0-1-has-arrived-to-help-you-build-agents/
- [SK-4] Semantic Kernel Python 1.0.0 release (22-05-2024) https://devblogs.microsoft.com/semantic-kernel/semantic-kernel-python-1-0-0-release/
- [SK-6] Semantic Kernel Agents are now generally available (04-04-2025) https://devblogs.microsoft.com/agent-framework/semantic-kernel-agents-are-now-generally-available/
- [SK-7] Semantic Kernel roadmap H1 2025 (03-02-2025) https://devblogs.microsoft.com/semantic-kernel/semantic-kernel-roadmap-h1-2025-accelerating-agents-processes-and-integration/
- [SK-8] Microsoft's Agentic AI Frameworks: AutoGen and Semantic Kernel (15-11-2024) https://devblogs.microsoft.com/semantic-kernel/microsofts-agentic-ai-frameworks-autogen-and-semantic-kernel/
- [SK-10] Agent Framework: Migration guide from Semantic Kernel https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-semantic-kernel
- [SK-11] Introducing Microsoft Agent Framework (Azure blog, 01-10-2025) https://azure.microsoft.com/en-us/blog/introducing-microsoft-agent-framework/
- [SK-12] Introducing Microsoft Agent Framework Preview (.NET blog, 01-10-2025) https://devblogs.microsoft.com/dotnet/introducing-microsoft-agent-framework-preview/
- [SK-13] Introducing Microsoft Agent Framework: the open-source engine for agentic AI apps (Foundry blog, 01-10-2025) https://devblogs.microsoft.com/foundry/introducing-microsoft-agent-framework-the-open-source-engine-for-agentic-ai-apps/
- [SK-14] Semantic Kernel and Microsoft Agent Framework (07-10-2025) https://devblogs.microsoft.com/semantic-kernel/semantic-kernel-and-microsoft-agent-framework/
- [SK-16] Microsoft Agent Framework Version 1.0 (03-04-2026) https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/
- [SK-21] Agent Framework overview (Microsoft Learn) https://learn.microsoft.com/en-us/agent-framework/overview/
- [SK-23] Repositorio microsoft/semantic-kernel (README) https://github.com/microsoft/semantic-kernel
- [SK-24] Semantic Kernel: Planning (Microsoft Learn) https://learn.microsoft.com/en-us/semantic-kernel/concepts/planning
- [SK-27] Announcing the general availability of Semantic Kernel Java (22-05-2024) https://devblogs.microsoft.com/semantic-kernel/announcing-the-general-availability-of-semantic-kernel-java/
- [SK-28] Repositorio microsoft/agent-framework (README, fecha de creación) https://github.com/microsoft/agent-framework
- [SK-30] PyPI (JSON): semantic-kernel, agent-framework, autogen-agentchat, pyautogen, ag2 https://pypi.org/pypi/semantic-kernel/json
- [SK-31] AutoGen: Enabling next-generation large language model applications (MSR, 25-09-2023) https://www.microsoft.com/en-us/research/blog/autogen-enabling-next-generation-large-language-model-applications/
- [SK-32] AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation (arXiv 2308.08155) https://arxiv.org/abs/2308.08155
- [SK-34] Introducing AutoGen Studio (17-06-2024) https://www.microsoft.com/en-us/research/blog/introducing-autogen-studio-a-low-code-interface-for-building-multi-agent-workflows/
- [SK-35] Magentic-One (04-11-2024) https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/
- [SK-36] AutoGen v0.4: Reimagining the foundation of agentic AI (14-01-2025) https://www.microsoft.com/en-us/research/blog/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness/
- [SK-38] Clarification Regarding AutoGen Forks (15-11-2024) https://github.com/microsoft/autogen/discussions/4217
- [SK-39] AutoGen discussion #7066: merging into Microsoft Agent Framework (02-10-2025) https://github.com/microsoft/autogen/discussions/7066
- [SK-40] README de microsoft/autogen (16-10-2026) https://raw.githubusercontent.com/microsoft/autogen/main/README.md
- [SK-41] Agent Framework: Migration guide from AutoGen https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen
- [SK-44] Microsoft Agent Framework for Go public preview (10-07-2026) https://devblogs.microsoft.com/go/microsoft-agent-framework-for-go-public-preview/

### Copilot Studio [CS-n]

- [CS-1] Harnesses in Copilot Studio — https://learn.microsoft.com/en-us/microsoft-copilot-studio/harnesses-overview
- [CS-2] What's new in Copilot Studio (oct. 2025 – sept. 2026) — https://learn.microsoft.com/microsoft-copilot-studio/whats-new
- [CS-5] TechCommunity, "Introducing a new harness for Copilot Studio" (mod. 3-8-2026) — https://techcommunity.microsoft.com/blog/copilot-studio-blog/more-powerful-agents-and-workflows-for-autonomous-business-processes-introducing/4542969
- [CS-6] Blog oficial, "New and improved: GitHub Copilot harness, agent skills, and richer context" (2-9-2026) — https://www.microsoft.com/microsoft-copilot/blog/copilot-studio/new-and-improved-github-copilot-harness-agent-skills-and-richer-context/
- [CS-7] Agent-building experience overview (GitHub Copilot harness) — https://learn.microsoft.com/en-us/microsoft-copilot-studio/agents-experience/overview
- [CS-8] Quotas and limits — https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-quotas
- [CS-9] Orchestrate agent behavior with generative AI — https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-generative-actions
- [CS-11] Copilot Studio pricing (nota "Copilot Studio Lite") — https://www.microsoft.com/en-us/microsoft-365-copilot/pricing/copilot-studio
- [CS-13] Event triggers — https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-triggers-about
- [CS-14] Computer use — https://learn.microsoft.com/en-us/microsoft-copilot-studio/computer-use
- [CS-16] Billing rates and management — https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-messages-management
- [CS-17] VS Code extension overview — https://learn.microsoft.com/microsoft-copilot-studio/visual-studio-code-extension-overview
- [CS-18] Clone an agent (VS Code) — https://learn.microsoft.com/en-us/microsoft-copilot-studio/visual-studio-code-extension-clone-agent
- [CS-20] pac copilot — https://learn.microsoft.com/en-us/power-platform/developer/cli/reference/copilot
- [CS-21] Solutions overview — https://learn.microsoft.com/microsoft-copilot-studio/authoring-solutions-overview
- [CS-24] Knowledge sources overview — https://learn.microsoft.com/en-us/microsoft-copilot-studio/knowledge-copilot-studio
- [CS-26] Azure AI Search as knowledge — https://learn.microsoft.com/en-us/microsoft-copilot-studio/knowledge-azure-ai-search
- [CS-27] Conector Azure AI Search Foundry IQ (Preview) — https://learn.microsoft.com/en-us/connectors/azureaisearchfoundryiq/
- [CS-29] Connector tools — https://learn.microsoft.com/microsoft-copilot-studio/microsoft-copilot-extend-action-connector
- [CS-30] Conector Dynamics 365 Business Central — https://learn.microsoft.com/connectors/dynamicssmbsaas
- [CS-31] Business Central MCP server overview — https://learn.microsoft.com/dynamics365/business-central/dev-itpro/ai/mcp-overview
- [CS-32] Configure Business Central MCP server — https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/configure-mcp-server
- [CS-33] BC 2026 wave 1, "Unlock more Business Central data with MCP server enhancements" — https://learn.microsoft.com/en-us/dynamics365/release-plan/2026wave1/smb/dynamics365-business-central/unlock-more-business-central-data-mcp-server-enhancements
- [CS-34] BC 2026 wave 1, "Create agentic experiences with enhanced MCP server" — https://learn.microsoft.com/en-us/dynamics365/release-plan/2026wave1/smb/dynamics365-business-central/create-agentic-experiences-enhanced-mcp-server
- [CS-36] MCP in Copilot Studio — https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-mcp
- [CS-37] Connect an existing MCP server — https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent
- [CS-38] Add MCP tools and resources — https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-components-to-agent
- [CS-39] Data policies (DLP) — https://learn.microsoft.com/en-us/microsoft-copilot-studio/admin-data-loss-prevention
- [CS-40] Blog, "What's new in Copilot Studio: November 2025" (15-12-2025) — https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/whats-new-in-microsoft-copilot-studio-november-2025/
- [CS-41] Dataverse MCP server — https://learn.microsoft.com/en-us/power-apps/maker/data-platform/data-platform-mcp
- [CS-42] Bring your own model for prompts — https://learn.microsoft.com/en-us/microsoft-copilot-studio/bring-your-own-model-prompts
- [CS-43] Code interpreter FAQ — https://learn.microsoft.com/microsoft-copilot-studio/faq-code-interpreter
- [CS-44] Multi-agent (add other agents) — https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-add-other-agents
- [CS-45] Blog, "New and improved: Computer-using agents…" (26-5-2026) — https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/new-and-improved-computer-using-agents-a-new-workflows-experience-and-real-time-voice-experiences/
- [CS-46] Connect an A2A agent — https://learn.microsoft.com/en-us/microsoft-copilot-studio/add-agent-agent-to-agent
- [CS-48] Connect to a Microsoft Foundry agent (preview) — https://learn.microsoft.com/en-us/microsoft-copilot-studio/add-agent-foundry-agent
- [CS-49] Connect to a Microsoft 365 Agents SDK agent (preview) — https://learn.microsoft.com/en-us/microsoft-copilot-studio/add-agent-microsoft-365-agents-sdk-agent
- [CS-51] Select a primary AI model — https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-select-agent-model
- [CS-52] Blog, "Anthropic joins the multi-model lineup" (24-9-2025) — https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/anthropic-joins-the-multi-model-lineup-in-microsoft-copilot-studio/
- [CS-53] Select an external response model — https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-select-external-response-model
- [CS-56] Publish: key concepts and channels — https://learn.microsoft.com/en-us/microsoft-copilot-studio/publication-fundamentals-publish-channels
- [CS-61] Security and governance — https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance
- [CS-62] Control maker credential options — https://learn.microsoft.com/en-us/microsoft-copilot-studio/configure-no-maker-authentication
- [CS-63] Entra Agent IDs for Copilot Studio agents — https://learn.microsoft.com/microsoft-copilot-studio/admin-use-entra-agent-identities
- [CS-65] Microsoft Agent 365 (precios) — https://www.microsoft.com/en-us/microsoft-agent-365
- [CS-66] Agent 365 observability (Copilot Studio) — https://learn.microsoft.com/microsoft-agent-365/builder/observability
- [CS-68] Audit logging (Purview) — https://learn.microsoft.com/en-us/microsoft-copilot-studio/admin-logging-copilot-studio
- [CS-69] TechCommunity, "Agent evaluation… now generally available" (mod. 31-3-2026) — https://techcommunity.microsoft.com/blog/copilot-studio-blog/agent-evaluation-in-microsoft-copilot-studio-is-now-generally-available/4507392
- [CS-70] Agent evaluations intro — https://learn.microsoft.com/en-us/microsoft-copilot-studio/analytics-agent-evaluation-intro
- [CS-71] Billing overview (GitHub Copilot harness) — https://learn.microsoft.com/microsoft-copilot-studio/agents-experience/billing-credit-overview
- [CS-72] Monitor analytics — https://learn.microsoft.com/en-us/microsoft-copilot-studio/analytics-overview
- [CS-73] Telemetry overview — https://learn.microsoft.com/en-us/microsoft-copilot-studio/telemetry-overview
- [CS-74] Environment-level telemetry (preview) — https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-environment-level-agent-telemetry
- [CS-75] Manage costs for GitHub Copilot harness agents (PPAC) — https://learn.microsoft.com/en-us/power-platform/admin/manage-usage-github-copilot-harness ; Govern credit consumption — https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/govern-credit-consumption ; Enforcement policy — https://learn.microsoft.com/en-us/microsoft-copilot-studio/agents-experience/enforcement-policy-credits ; Buy credits — https://learn.microsoft.com/en-us/microsoft-copilot-studio/agents-experience/billing-manage-buy-credits
- [CS-76] Request information (human review) — https://learn.microsoft.com/en-us/microsoft-copilot-studio/flows-request-for-information
- [CS-77] Hand off to Dynamics 365 Customer Service — https://learn.microsoft.com/en-us/microsoft-copilot-studio/configuration-hand-off-omnichannel
- [CS-78] Configure user authentication — https://learn.microsoft.com/en-us/microsoft-copilot-studio/configuration-end-user-authentication
- [CS-79] User authentication for tools — https://learn.microsoft.com/en-us/microsoft-copilot-studio/configure-enduser-authentication

### Microsoft Foundry y gobernanza [FY-n]

- [FY-1] What is Microsoft Foundry? — https://learn.microsoft.com/azure/foundry/what-is-foundry (ms.date 2026-08-13)
- [FY-3] Build and scale AI agents with Microsoft Foundry, Asha Sharma (18-11-2025) — https://azure.microsoft.com/en-us/blog/microsoft-foundry-scale-innovation-on-a-modular-interoperable-and-secure-agent-stack/
- [FY-4] Introducing Azure AI Foundry, Tech Community (25-11-2024) — https://techcommunity.microsoft.com/discussions/Marketplace-Forum/introducing-azure-ai-foundry/4336056
- [FY-6] Azure AI Foundry: your AI app and agent factory (19-05-2025) — https://azure.microsoft.com/en-us/blog/azure-ai-foundry-your-ai-app-and-agent-factory/
- [FY-7] What's new in Foundry Agent Service (classic) — https://learn.microsoft.com/en-us/azure/ai-foundry/agents/whats-new
- [FY-8] What is Microsoft Foundry Agent Service? — https://learn.microsoft.com/en-us/azure/foundry/agents/overview (ms.date 2026-09-25)
- [FY-9] Foundry Agent Service is GA (16-03-2026) — https://devblogs.microsoft.com/foundry/foundry-agent-service-ga/
- [FY-12] What's new, May 2026 (30-05-2026) — https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-may-2026
- [FY-13] What's new, Build 2026 edition (02-06-2026) — https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-build-2026/
- [FY-15] What's New in Hosted Agents in Foundry Agent Service (02-06-2026) — https://devblogs.microsoft.com/foundry/hosted-agents-build26/
- [FY-16] What's new, June 2026 (07-07-2026) — https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-june-2026/
- [FY-17] What's new, July–August 2026 (09-09-2026) — https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-july-august-2026/
- [FY-19] Introducing the new hosted agents… (22-04-2026) — https://devblogs.microsoft.com/foundry/introducing-the-new-hosted-agents-in-foundry-agent-service-secure-scalable-compute-built-for-agents
- [FY-20] Hosted agents (concepts) — https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents (2026-09-11)
- [FY-22] Workflows in Microsoft Foundry — https://learn.microsoft.com/azure/foundry/agents/concepts/workflow (2026-07-31)
- [FY-23] Introducing multi-agent workflows in Foundry Agent Service (25-11-2025) — https://devblogs.microsoft.com/foundry/introducing-multi-agent-workflows-in-foundry-agent-service/
- [FY-24] Agent-to-agent (A2A) tool — https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/agent-to-agent (2026-09-14)
- [FY-25] Foundry Models overview — https://learn.microsoft.com/en-us/azure/foundry/concepts/foundry-models-overview (2026-07-28)
- [FY-26] Introducing Anthropic's Claude models in Microsoft Foundry (18-11-2025) — https://azure.microsoft.com/en-us/blog/introducing-anthropics-claude-models-in-microsoft-foundry-bringing-frontier-intelligence-to-azure/
- [FY-27] Observability in Microsoft Foundry — https://learn.microsoft.com/azure/foundry/concepts/observability (2026-10-17)
- [FY-28] Foundry Control Plane overview — https://learn.microsoft.com/en-us/azure/foundry/control-plane/overview (2026-08-13)
- [FY-29] Manage agents in Foundry Control Plane — https://learn.microsoft.com/en-us/azure/foundry/control-plane/how-to-manage-agents (2026-07-15)
- [FY-30] Agent identity concepts in Microsoft Foundry — https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity (2026-08-25)
- [FY-32] Foundry Agent Service pricing — https://azure.microsoft.com/en-us/pricing/details/foundry-agent-service/
- [FY-33] Microsoft Foundry SDKs overview — https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview (2026-10-06)
- [FY-34] Agent Framework: Microsoft Foundry model provider — https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/microsoft-foundry (2026-09-29)
- [FY-35] Agent Framework: Foundry hosted agent — https://learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent (2026-10-02)
- [FY-36] Microsoft Agent Framework Version 1.0 (03-04-2026) — https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/
- [FY-38] Microsoft Agent Framework at BUILD 2026 (03-06-2026) — https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-at-build-2026-announce/
- [FY-40] Copilot Studio: Connect to a Microsoft Foundry agent (preview) — https://learn.microsoft.com/en-us/microsoft-copilot-studio/add-agent-foundry-agent (2026-08-28)
- [FY-41] Copilot Studio: Bring your own model for your prompts — https://learn.microsoft.com/en-us/microsoft-copilot-studio/bring-your-own-model-prompts (2026-08-03)
- [FY-44] Copilot Studio: Connect to Foundry IQ — https://learn.microsoft.com/en-us/microsoft-copilot-studio/agents-experience/foundry-iq-connect (2026-09-16)
- [FY-45] Foundry: Connect agents to Microsoft 365 with Work IQ (preview) — https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/work-iq (2026-09-17)
- [FY-46] Foundry: Publish to Teams and Microsoft 365 Copilot — https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot (2026-09-28)
- [FY-48] What is Microsoft Entra Agent ID? — https://learn.microsoft.com/en-us/entra/agent-id/what-is-microsoft-entra-agent-id (2026-06-24)
- [FY-49] What's new in Microsoft Entra Agent ID — https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id (2026-05-01)
- [FY-52] Copilot Studio: Microsoft Entra Agent IDs for Copilot Studio agents — https://learn.microsoft.com/microsoft-copilot-studio/admin-use-entra-agent-identities (2026-09-15)
- [FY-54] Microsoft Agent 365 overview — https://learn.microsoft.com/en-us/microsoft-agent-365/overview (2026-08-20)
- [FY-55] Microsoft Agent 365, now generally available… (Security Blog, 01-05-2026) — https://microsoft.com/en-us/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations
- [FY-56] Agent 365 will be generally available on May 1, 2026 (Tech Community, 09-03-2026) — https://techcommunity.microsoft.com/discussions/agent-365-discussions/agent-365-will-be-generally-available-on-may-1-2026/4500380
- [FY-57] Microsoft Ignite 2025: Copilot and agents built to power the Frontier Firm, Jared Spataro (18-11-2025) — https://www.microsoft.com/en-us/copilot/blog/2025/11/18/microsoft-ignite-2025-copilot-and-agents-built-to-power-the-frontier-firm/
- [FY-58] Agent 365 developer overview — https://learn.microsoft.com/en-us/microsoft-agent-365/developer/ (2026-10-02)
- [FY-59] Microsoft Agent 365 SDK — https://learn.microsoft.com/en-us/microsoft-agent-365/developer/agent-365-sdk (2026-10-09)
- [FY-61] Use Microsoft Purview to manage data security & compliance for Microsoft Foundry — https://learn.microsoft.com/purview/ai-azure-foundry (2026-05-01)
- [FY-62] Microsoft Defender: AI agent detection and protection — https://learn.microsoft.com/en-us/defender-xdr/security-for-ai/ai-agent-detection-protection (2026-09-03)
- [FY-63] Defender for Cloud: AI threat protection — https://learn.microsoft.com/en-ca/azure/defender-for-cloud/ai-threat-protection (2026-06-17)
- [FY-64] Microsoft 365 Agents SDK overview — https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/agents-sdk-overview (2026-04-29)
- [FY-65] Microsoft 365 Agents Toolkit overview — https://learn.microsoft.com/en-us/microsoft-365/developer/overview-m365-agents-toolkit (2026-01-29)
- [FY-66] Copilot controls overview (Copilot Control System) — https://learn.microsoft.com/copilot/microsoft-365/copilot-control-system/overview (2026-09-09)
- [FY-69] (tercero) BigHat Group, Microsoft Foundry Hosted Agents: What Enterprise IT Should Do Now (24-04-2026) — https://www.bighatgroup.com/blog/microsoft-foundry-hosted-agents-enterprise-guide-april-2026/

### Business Central (oficiales) [BC-n]

- [BC-1] https://learn.microsoft.com/en-us/dynamics365/release-plan/2024wave2/smb/dynamics365-business-central/use-copilot-agent-capabilities-automate-sales-order-taking-process
- [BC-2] https://learn.microsoft.com/en-us/dynamics365/business-central/sales-order-agent-setup
- [BC-3] https://learn.microsoft.com/en-us/dynamics365/business-central/sales-order-agent-process
- [BC-5] https://learn.microsoft.com/en-us/dynamics365/business-central/faqs-sales-order-taker-agent
- [BC-6] https://learn.microsoft.com/en-us/dynamics365/release-plan/2025wave2/smb/dynamics365-business-central/capture-more-sales-enhanced-sales-order-agent
- [BC-7] https://learn.microsoft.com/en-us/dynamics365/release-plan/2026wave1/smb/dynamics365-business-central/run-multiple-sales-order-agents-per-company-smarter-item-matching-relevance-filtering-streamlined-setup
- [BC-8] https://learn.microsoft.com/en-us/dynamics365/release-plan/2025wave2/smb/dynamics365-business-central/automate-payables-processes-payables-agent
- [BC-9] https://learn.microsoft.com/en-us/dynamics365/business-central/payables-agent-setup
- [BC-10] https://learn.microsoft.com/en-us/dynamics365/business-central/payables-agent
- [BC-11] https://learn.microsoft.com/en-us/dynamics365/release-plan/2025wave2/smb/dynamics365-business-central/use-payables-agent-more-countries-regions
- [BC-12] https://learn.microsoft.com/en-us/dynamics365/release-plan/2026wave1/smb/dynamics365-business-central/manage-expenses-business-central-using-expense-agent
- [BC-13] https://learn.microsoft.com/en-us/dynamics365/business-central/copilot-agents-region-language-availability
- [BC-14] https://learn.microsoft.com/en-us/dynamics365/business-central/enable-ai
- [BC-15] https://learn.microsoft.com/en-us/dynamics365/business-central/supervise-agent-tasks
- [BC-16] https://learn.microsoft.com/en-us/dynamics365/release-plan/2025wave2/smb/dynamics365-business-central/planned-features
- [BC-18] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/whatsnew/whatsnew-update-29-0
- [BC-24] https://www.microsoft.com/en-us/dynamics-365/blog/business-leader/2026/08/25/one-always-on-roadmap-dynamics-365-power-platform-and-dataverse-join-the-ai-at-work-roadmap/
- [BC-26] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/ai-agent-sdk-overview
- [BC-27] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/ai-development-toolkit-overview
- [BC-28] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/ai-development-toolkit-agent-create
- [BC-29] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/ai-agent-sdk-define-register
- [BC-30] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/ai-agent-sdk-tasks
- [BC-31] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/ai-development-toolkit-tasks-api
- [BC-32] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/ai-development-toolkit-permissions-profiles
- [BC-33] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/ai-development-toolkit-run-agent
- [BC-34] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/transparency-note-ai-development-toolkit
- [BC-39] https://learn.microsoft.com/en-us/dynamics365/release-plan/2025wave2/smb/dynamics365-business-central/connect-ai-agents-business-central-through-mcp-server
- [BC-40] https://learn.microsoft.com/dynamics365/business-central/dev-itpro/ai/mcp-overview
- [BC-41] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/configure-mcp-server
- [BC-42] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/use-mcp-server-non-microsoft
- [BC-43] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/create-agent-in-copilot-studio
- [BC-44] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/ai/use-mcp-server-in-vscode
- [BC-45] https://learn.microsoft.com/en-us/dynamics365/release-plan/2026wave1/smb/dynamics365-business-central/create-agentic-experiences-enhanced-mcp-server
- [BC-46] https://learn.microsoft.com/en-us/dynamics365/release-plan/2026wave1/smb/dynamics365-business-central/unlock-more-business-central-data-mcp-server-enhancements
- [BC-47] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/administration/administration-center-api-mcp
- [BC-53] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/api-reference/v2.0/
- [BC-54] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/api-reference/v2.0/resources/dynamics_salesorder
- [BC-55] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/api-reference/v2.0/api/dynamics_salesorder_create
- [BC-58] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/administration/automation-apis-using-s2s-authentication
- [BC-59] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/webservices/authenticate-web-services-using-oauth
- [BC-60] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/administration/operational-limits-online
- [BC-62] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/developer/devenv-api
- [BC-63] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/developer/devenv-api-pagetype
- [BC-64] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/webservices/odata-web-services
- [BC-65] https://learn.microsoft.com/connectors/dynamicssmbsaas
- [BC-66] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/administration/tenant-admin-center-environments
- [BC-67] https://www.microsoft.com/licensing/guidance/Dynamics-365-Business-Central
- [BC-68] https://www.microsoft.com/licensing/guidance/Copilot-Credits
- [BC-69] Dynamics 365 Licensing Guide (agosto 2026), copia alojada por un tercero del PDF oficial: https://www.licensingschool.co.uk/wp-content/uploads/2026/08/Dynamics-365-Licensing-Guide-August-2026.pdf (el enlace oficial https://go.microsoft.com/fwlink/?LinkId=866544 no se pudo abrir)
- [BC-71] https://assetsprod.microsoft.com/mpn/business-central-dynamics-licensing-guide.pdf (guía on-premises, enero 2024)
- [BC-72] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/administration/tenant-admin-center-manage-consumption-billing
- [BC-74] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/administration/telemetry-mcp-server-trace
- [BC-75] https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/administration/telemetry-agent-lifecycle-trace
- [BC-77] https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview
- [BC-78] https://learn.microsoft.com/en-us/agent-framework/user-guide/model-context-protocol/using-mcp-tools

### Business Central (terceros) [BC-Tn]

- [BC-T1] Yun Zhu, Custom Agent en BC 27.4 (09-02-2026): https://yzhums.com/70502/
- [BC-T2] Yun Zhu, selección de modelo en BC 28.2 (01-07-2026): https://yzhums.com/74431/
- [BC-T4] Yun Zhu, Billing Type de capacidades de Copilot (08-09-2025): https://yzhums.com/67462/
- [BC-T5] Yun Zhu, fin de los release plans (01-09-2026): https://yzhums.com/75614/
- [BC-T8] Bert Verbeek, «Microsoft Agent Framework and Business Central MCP server» (12-11-2025; no accesible; resumen de terceros en https://mydigest.365.training/Link/9c3f3e4d-45c0-f011-bbd3-0022480b738e): https://www.bertverbeek.nl/blog/2025/11/12/microsoft-agent-framework-and-business-central-mcp-server/
- [BC-T13] Repositorios comunitarios de servidores MCP para BC (no abiertos): https://github.com/demiliani/AI_Training ; https://github.com/SShadowS/business-central-mcp ; https://github.com/Bertverbeek4PS/BusinessCentralMCPserver

### Protocolos MCP/A2A y control y riesgo [PR-n]

- [PR-1] Anthropic, «Introducing the Model Context Protocol» (25 nov 2024): https://www.anthropic.com/news/model-context-protocol
- [PR-2] MCP, «Versioning»: https://modelcontextprotocol.io/specification/versioning
- [PR-3] Anthropic, «Donating the Model Context Protocol and establishing of the Agentic AI Foundation» (9 dic 2025): https://anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation
- [PR-4] Linux Foundation, «Linux Foundation Announces the Formation of the Agentic AI Foundation» (9 dic 2025): https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation
- [PR-5] AAIF, «About»: https://aaif.io/about
- [PR-7] MCP, «Governance and Stewardship»: https://modelcontextprotocol.io/community/governance
- [PR-8] MCP blog, «Expanding the MCP Maintainer Team» (8 abr 2026): https://blog.modelcontextprotocol.io/posts/2026-04-08-maintainer-update/
- [PR-13] MCP, «Key Changes» 2025-03-26: https://modelcontextprotocol.io/specification/2025-03-26/changelog
- [PR-14] MCP, «Key Changes» 2025-06-18: https://modelcontextprotocol.io/specification/2025-06-18/changelog
- [PR-15] MCP, «Key Changes» 2025-11-25: https://modelcontextprotocol.io/specification/2025-11-25/changelog
- [PR-16] MCP, «Key Changes» 2026-07-28: https://modelcontextprotocol.io/specification/2026-07-28/changelog
- [PR-17] MCP blog, «The 2026-07-28 Specification» (28 jul 2026): https://blog.modelcontextprotocol.io/posts/2026-07-28/
- [PR-19] AAIF blog, «MCP 2026-07-28: From Local Tool to Distributed Protocol» (21 jul 2026): https://aaif.io/blog/mcp-2026-07-28-whats-changing-and-how-to-migrate
- [PR-20] MCP blog, «The New MCP Roadmap» (22 ago 2026): https://blog.modelcontextprotocol.io/posts/mcp-roadmap/
- [PR-23] MCP, «Extensions Overview»: https://modelcontextprotocol.io/docs/extensions/overview
- [PR-24] MCP blog, «Enterprise-Managed Authorization: Zero-touch OAuth for MCP» (18 jun 2026): https://blog.modelcontextprotocol.io/posts/enterprise-managed-auth/
- [PR-25] MCP, «SDKs»: https://modelcontextprotocol.io/docs/sdk
- [PR-26] GitHub, modelcontextprotocol/csharp-sdk: https://github.com/modelcontextprotocol/csharp-sdk
- [PR-28] NuGet, ModelContextProtocol: https://www.nuget.org/packages/ModelContextProtocol
- [PR-29] MCP blog, «Introducing the MCP Registry» (8 sep 2025): https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/
- [PR-30] MCP Registry: https://registry.modelcontextprotocol.io/
- [PR-32] GitHub, microsoft/mcp: https://github.com/microsoft/mcp
- [PR-33] MCP, «Security Best Practices» (2026-07-28): https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices
- [PR-34] (tercero) Invariant Labs, «MCP Security Notification: Tool Poisoning Attacks» (1 abr 2025): https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
- [PR-35] (tercero) Invariant Labs, «GitHub MCP Exploited» (26 may 2025): https://invariantlabs.ai/blog/mcp-github-vulnerability
- [PR-36] MCP blog, «Tool Annotations as Risk Vocabulary» (16 mar 2026): https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/
- [PR-37] Microsoft Learn, «Connect to Model Context Protocol servers (Foundry Agent Service)»: https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/model-context-protocol
- [PR-38] Google Developers Blog, «Announcing the Agent2Agent Protocol (A2A)» (9 abr 2025): https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
- [PR-39] Microsoft Cloud Blog, «Empowering multi-agent apps with the open Agent2Agent (A2A) protocol» (7 may 2025): https://www.microsoft.com/en-us/microsoft-cloud/blog/2025/05/07/empowering-multi-agent-apps-with-the-open-agent2agent-a2a-protocol/
- [PR-40] Linux Foundation, «Linux Foundation Launches the Agent2Agent Protocol Project» (23 jun 2025): https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents
- [PR-41] AAIF, «A2A joins AAIF» (17 ago 2026): https://aaif.io/blog/a2a-joins-aaif
- [PR-43] A2A, «A2A Protocol Ships v1.0» (12 mar 2026): https://a2a-protocol.org/latest/blog/2026/03/12/a2a-protocol-ships-v10-production-ready-standard-for-agent-to-agent-communication/
- [PR-44] Linux Foundation, «A2A Protocol Surpasses 150 Organizations…» (9 abr 2026): https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year
- [PR-45] GitHub, a2aproject/A2A releases: https://github.com/a2aproject/A2A/releases
- [PR-46] A2A, especificación (1.0.0): https://a2a-protocol.org/latest/specification/
- [PR-47] GitHub, a2aproject/a2a-dotnet: https://github.com/a2aproject/a2a-dotnet
- [PR-48] NuGet, A2A: https://www.nuget.org/packages/A2A
- [PR-49] Microsoft Learn, «MCP on Windows overview»: https://learn.microsoft.com/en-us/windows/ai/mcp/overview
- [PR-51] Microsoft Copilot Blog, «MCP is now generally available in Microsoft Copilot Studio» (29 may 2025): https://www.microsoft.com/en-us/copilot/blog/copilot-studio/model-context-protocol-mcp-is-now-generally-available-in-microsoft-copilot-studio/
- [PR-52] Microsoft Learn, «What's new in Copilot Studio»: https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new
- [PR-53] Microsoft Copilot Blog, «New and improved multi-agent orchestration…» (1 abr 2026): https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/new-and-improved-multi-agent-orchestration-connected-experiences
- [PR-55] Microsoft Learn, «A2A tool (Foundry agents)» (14 sep 2026): https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/agent-to-agent
- [PR-56] Microsoft Learn, «Enable incoming A2A on a Foundry agent» (14 sep 2026): https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint
- [PR-58] Microsoft DevBlogs, «Microsoft Agent Framework Version 1.0» (3 abr 2026): https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/
- [PR-59] GitHub, microsoft/agent-framework: https://github.com/microsoft/agent-framework
- [PR-60] Microsoft Learn (release plan), «Dataverse MCP Server»: https://learn.microsoft.com/en-us/power-platform/release-plan/2025wave1/data-platform/dataverse-mcp-server
- [PR-67] Microsoft Learn, «AL MCP Server»: https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/developer/al-agent-tools/al-mcp-server
- [PR-68] GitHub Changelog, «Remote GitHub MCP Server is now generally available» (4 sep 2025): https://github.blog/changelog/2025-09-04-remote-github-mcp-server-is-now-generally-available/ ; vista previa (12 jun 2025): https://github.blog/changelog/2025-06-12-remote-github-mcp-server-is-now-available-in-public-preview/
- [PR-69] Microsoft DevBlogs, «Announcing Azure MCP Server 2.0 stable release» (10 abr 2026): https://devblogs.microsoft.com/azure-sdk/announcing-azure-mcp-server-2-0-stable-release
- [PR-77] A2A, «A2A and MCP»: https://a2a-protocol.org/latest/topics/a2a-and-mcp/
- [PR-78] Satya Nadella (sn scratchpad), «Models as Insider Risks in the Super Intelligence Era» (10 oct 2026): https://snscratchpad.com/posts/models-as-insider-risks/
- [PR-79] sn scratchpad (portada): https://snscratchpad.com/
- [PR-80] X, @satyanadella, el ensayo publicado como artículo de X (10 oct 2026; comprobado el 18-10-2026, texto idéntico al del blog y frase textual): https://x.com/satyanadella/status/2108931348857827686
- [PR-81] (tercero, texto de Bloomberg) Deccan Chronicle, «Microsoft CEO Nadella Calls for 'Emergency Brake' on Advanced AI» (13 oct 2026): https://www.deccanchronicle.com/amp/technology/microsoft-ceo-nadella-calls-for-emergency-brake-on-advanced-ai-1995427
- [PR-82] (tercero) Forbes, «Microsoft's Nadella Wants An Emergency Brake On Every AI Model» (11 oct 2026): https://www.forbes.com/sites/gabrielalinzainescu/2026/10/11/microsofts-nadella-wants-an-emergency-brake-on-every-ai-model/
- [PR-83] (tercero) Business Standard (12 oct 2026): https://www.business-standard.com/technology/artificial-intelligence/satya-nadella-warns-of-ai-insider-risks-seeks-stronger-safety-controls-126101200572_1.html
- [PR-84] (tercero) PC Guide (12 oct 2026): https://www.pcguide.com/pro/news-pro/microsoft-ceo-says-there-should-be-an-emergency-brake-on-ai-or-as-he-calls-it-super-intelligence/
- [PR-86] Microsoft Security Blog, «80% of Fortune 500 use active AI agents…» (10 feb 2026): https://www.microsoft.com/en-us/security/blog/2026/02/10/80-of-fortune-500-use-active-ai-agents-observability-governance-and-security-shape-the-new-frontier/
- [PR-87] Microsoft Security Blog, «Least privilege for AI agents: Identity, access, and tool binding» (16 jul 2026): https://www.microsoft.com/en-us/security/blog/2026/07/16/least-privilege-for-ai-agents-identity-access-and-tool-binding/
- [PR-88] (tercero) Windows Central (8 jun 2026, citando Business Insider): https://www.windowscentral.com/artificial-intelligence/satya-nadella-ai-agents-deserve-real-identities
- [PR-89] Microsoft Security Blog, «New whitepaper outlines the taxonomy of failure modes in AI agents» (24 abr 2025): https://www.microsoft.com/en-us/security/blog/2025/04/24/new-whitepaper-outlines-the-taxonomy-of-failure-modes-in-ai-agents/
- [PR-90] Microsoft Security Blog, «Updating the taxonomy of failure modes in agentic AI systems» (4 jun 2026): https://www.microsoft.com/en-us/security/blog/2026/06/04/updating-taxonomy-failure-modes-agentic-ai-systems-year-red-teaming-taught-us/
- [PR-91] OWASP, «Top 10 for LLM Applications 2025»: https://genai.owasp.org/llm-top-10/
- [PR-93] OWASP, «OWASP Top 10 for Agentic Applications» (9 dic 2025): https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/ ; recurso: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- [PR-94] NIST/CAISI, «Strengthening AI Agent Hijacking Evaluations» (17 ene 2025): https://www.nist.gov/news-events/news/2025/01/technical-blog-strengthening-ai-agent-hijacking-evaluations
- [PR-95] NIST CSRC, proyecto COSAiS: https://csrc.nist.gov/projects/cosais
- [PR-96] NIST, «Announcing the AI Agent Standards Initiative» (17 feb 2026): https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure
- [PR-98] Simon Willison, «The lethal trifecta for AI agents» (16 jun 2025): https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- [PR-99] NIST NVD, CVE-2025-32711: https://nvd.nist.gov/vuln/detail/CVE-2025-32711
- [PR-100] Google Research, «An Introduction to Google's Approach for Secure AI Agents» (2025): https://research.google/pubs/an-introduction-to-googles-approach-for-secure-ai-agents/
- [PR-101] Simon Willison, «Design Patterns… / Google's approach to AI agent security» (15 jun 2025): https://simonwillison.net/2025/Jun/15/ai-agent-security/
- [PR-102] Anthropic, «Agentic Misalignment» (20 jun 2025): https://www.anthropic.com/research/agentic-misalignment
- [PR-103] Anthropic, «Our framework for developing safe and trustworthy agents» (4 ago 2025): https://www.anthropic.com/news/our-framework-for-developing-safe-and-trustworthy-agents
- [PR-104] OpenAI, «Practices for Governing Agentic AI Systems» (PDF, 2023): https://cdn.openai.com/papers/practices-for-governing-agentic-ai-systems.pdf
- [PR-105] OpenAI, «Continuously hardening ChatGPT Atlas against prompt injection attacks» (22 dic 2025): https://openai.com/index/hardening-atlas-against-prompt-injection
- [PR-106] Gartner, nota de prensa (25 jun 2025): https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027
- [PR-107] Cemri et al., «Why Do Multi-Agent LLM Systems Fail?» (arXiv 2503.13657): https://arxiv.org/abs/2503.13657
- [PR-108] (tercero) eWeek, «'Catastrophic Failure': AI Agent Wipes Production Database…» (22–24 jul 2025): https://www.eweek.com/news/replit-ai-coding-assistant-failure/
- [PR-109] (tercero) CSO Online, «Hacker inserts destructive code in Amazon Q as update goes live» (24 jul 2025): https://www.csoonline.com/article/4027963/hacker-inserts-destructive-code-in-amazon-q-as-update-goes-live.html
- [PR-110] OECD.AI incident 2025-07-25-03b9 (Gemini CLI): https://oecd.ai/en/incidents/2025-07-25-03b9
- [PR-111] (tercero) Security Magazine, «Company Database Deleted by AI Agent» (1 may 2026): https://www.securitymagazine.com/articles/102278-company-database-deleted-by-ai-agent-what-security-leaders-need-to-know
