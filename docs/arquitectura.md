# Arquitectura: los tres diagramas

Los mismos diagramas del artículo, en Mermaid, para copiarlos donde haga falta. Nombres de la API de Agent Framework 1.22.0 (Python).

## 1. El esqueleto de un agente en Agent Framework

```mermaid
flowchart TB
  subgraph AG["Agente (Agent)"]
    direction TB
    INS["Instrucciones (system prompt)\n+ opciones por defecto"]
    MOD["Cliente de modelo\nOpenAIChatClient / FoundryChatClient /\nAnthropicClient / OllamaChatClient / simulado"]
    TOOLS["Herramientas (@tool)\nfunciones propias, MCP,\notros agentes (as_tool)"]
    SES["Sesión y memoria (AgentSession)\nhistorial + context providers"]
    MW["Middleware\nagente / función / chat"]
    LOOP(("bucle de\nejecución"))
    INS --> LOOP
    MOD <--> LOOP
    LOOP --> MW --> TOOLS
    SES <--> LOOP
  end
  HITL["Aprobaciones humanas\napproval_mode / request_info"] --- AG
  OUT["Salida estructurada\nresponse_format → .value"] --- AG
  WF["Workflows (WorkflowBuilder)\nnodos, aristas condicionales,\ncheckpoints, parada y reanudación"] --- AG
  ORQ["Orquestaciones\nsequential, concurrent, handoff,\ngroup chat, magentic"] --- WF
  OBS["Observabilidad (OpenTelemetry)\ntrazas, tokens → Aspire, App Insights, Foundry"] --- AG
  PROTO["Protocolos\nMCP cliente y servidor, A2A, AG-UI"] --- AG
  DECL["Declarativo (YAML)\nAgentFactory / WorkflowFactory"] --- AG
  HOST["Hosting\ncontenedor propio, Azure Functions (Durable),\nFoundry hosted agents"] --- AG
  DEV["DevUI (beta)\ninterfaz de pruebas"] --- AG
```

En este repositorio: el agente y sus instrucciones en `agentes.py` y `prompts/`; el cliente de modelo en `modelo.py`; las herramientas en `herramientas.py`; la sesión en `cli.py` (comando `chat`); el middleware en `middleware.py`; la salida estructurada en `esquemas.py`; el workflow con aprobación y checkpoints en `workflow.py`; la observabilidad en `observabilidad.py`; MCP en `mcp_server.py`; DevUI en `devui/`.

## 2. El recorrido de una petición

```mermaid
sequenceDiagram
    autonumber
    participant U as Buzón / persona
    participant A as Agent.run()
    participant MW as Middleware
    participant M as Modelo (chat client)
    participant T as Herramientas (@tool)
    participant BC as Business Central
    participant H as Aprobador humano
    U->>A: correo del pedido (+ sesión)
    A->>A: prepara contexto: instrucciones + historial + proveedores de contexto
    A->>MW: middleware de chat
    MW->>M: mensajes + esquemas de herramientas
    M-->>A: "necesito buscar_clientes('Adatum')"
    A->>MW: middleware de función (audita, puede bloquear)
    MW->>T: buscar_clientes
    T->>BC: GET /customers?$filter=... (identidad de aplicación)
    BC-->>T: cliente 10000, no bloqueado
    T-->>A: resultado → se añade a la sesión
    A->>M: segunda vuelta del bucle (y las que hagan falta)
    M-->>A: salida estructurada: PedidoInterpretado
    Note over A: código: valida existencias, crédito, umbral de importe
    A->>H: approval_mode / request_info: "¿crear pedido de 5.875,60 €?" (estado guardado)
    H-->>A: aprobado (misma sesión o checkpoint)
    A->>T: crear_pedido_venta
    T->>BC: POST /salesOrders + líneas
    BC-->>T: S-ORD101002 (registrado con la identidad de la aplicación)
    A-->>U: respuesta + trazas OpenTelemetry de cada paso
```

## 3. El workflow del ejemplo (generado por `WorkflowViz(workflow).to_mermaid()`)

```mermaid
flowchart TD
  interpretar["interpretar (Start)"];
  validar["validar"];
  rechazar["rechazar"];
  aprobacion_humana["aprobacion_humana"];
  crear_pedido["crear_pedido"];
  redactar["redactar"];
  interpretar --> validar;
  validar --> rechazar;
  validar --> aprobacion_humana;
  validar --> crear_pedido;
  aprobacion_humana -. conditional .-> crear_pedido;
  aprobacion_humana -. conditional .-> rechazar;
  crear_pedido --> redactar;
  rechazar --> redactar;
```

Las tres aristas que salen de `validar` forman un grupo switch-case evaluado en código: `not apto_para_crear` → `rechazar`; `requiere_aprobacion` → `aprobacion_humana`; por defecto → `crear_pedido`. Las dos aristas de `aprobacion_humana` dependen de `DecisionTomada.aprobado`.

## 4. Quién decide qué

| Paso | Quién decide | Pieza |
|---|---|---|
| Qué cliente y qué artículos nombra el correo | IA | `Agent` intérprete + `@tool` de lectura + salida estructurada |
| Si el pedido es válido y cuánto importa | Código | `politicas.validar_pedido` |
| Qué ruta sigue el pedido | Código | aristas condicionales del `WorkflowBuilder` |
| Si se crea un pedido que exige aprobación | Persona | `request_info` + checkpoint (o `approval_mode` en el agente de chat) |
| Escribir en Business Central | Código | nodo `crear_pedido` → `ClienteBC.crear_pedido_venta` (API v2.0 con identidad de aplicación) |
| Qué se le dice al cliente | IA (sobre datos calculados por código) | `Agent` redactor |
| Qué queda registrado | Código | middleware de auditoría + OpenTelemetry + registro de cambios de BC |

La salida real de `python -m agente_pedidos demo` está en [`salida-demo.txt`](salida-demo.txt).
