# Notas de construcción

Cambios hechos después de la primera versión, con el motivo de cada uno. Lo que funciona a la primera no se apunta aquí; lo que falló, sí.

## 2026-10-18 · Los comentarios al final de línea en `.env` se colaban en los valores

**Síntoma.** Con un `.env` copiado de `.env.example`, `python -m agente_pedidos procesar …` se caía al arrancar, antes de llamar al modelo:

```
File "src/agente_pedidos/middleware.py", line 84, in __init__
  self.maximo = ... int(os.environ.get("AGENTE_MAX_LLAMADAS_MODELO", "12"))
ValueError: invalid literal for int() with base 10: '12    # tope de llamadas al modelo por ejecución'
```

**Causa.** Dos piezas que por separado parecían correctas:

- `.env.example` documentaba cuatro variables con un comentario detrás del valor (`AGENTE_MAX_LLAMADAS_MODELO=12    # tope de…`).
- `cargar_entorno()` en `cli.py` es un lector de `.env` hecho a mano que solo ignoraba las líneas que *empiezan* por `#`. Con un comentario al final de la línea, el comentario entraba en el valor.

**Lo más grave no era el error, sino lo que fallaba sin avisar.** `AGENTE_MAX_LLAMADAS_MODELO` se rompía de forma visible porque se convierte a entero. Las otras tres variables seguían funcionando con un valor incorrecto:

- `AGENTE_SOLO_LECTURA=1   # comentario` daba `"1   # comentario"`, que no es `"1"`: **el modo solo lectura quedaba desactivado** aunque la persona lo hubiera activado. Es justo el control que debe bloquear las escrituras en el ERP.
- `AGENTE_AUDITORIA` y `AGENTE_CHECKPOINTS` se convertían en rutas con el comentario dentro.

**Por qué no lo detectó la revisión.** El modo demo y las 22 pruebas funcionan **sin `.env`**: toman los valores por defecto del código y nunca pasan por `cargar_entorno()`. El fallo solo aparece cuando alguien copia `.env.example` a `.env` para conectar un modelo real, que es el primer paso fuera de la demo. Ninguna prueba cargaba un `.env`.

**Corrección.**

1. `cargar_entorno()` interpreta los valores como `python-dotenv` (función nueva `_valor_env`):
   - sin comillas, un `#` precedido de espacio empieza un comentario y se descarta (`CLAVE=1   # …` → `1`; `CLAVE=   # …` → vacío);
   - un `#` sin espacio delante se conserva (`CLAVE=abc#def` → `abc#def`);
   - entre comillas simples o dobles se conserva todo, `#` incluido, y se ignora lo que vaya después de la comilla de cierre.
2. `.env.example`: los comentarios pasan a su propia línea, y se añade una línea que lo pide. Se hace lo mismo con las asignaciones comentadas de observabilidad (`# ENABLE_CONSOLE_EXPORTERS=1   # …`), para que al descomentarlas no reaparezca el problema. Esto también protege a quien cargue el fichero con otras herramientas que no quitan comentarios, como `docker --env-file`.
3. Se aplicó el mismo cambio al `.env` local (que no está en el repositorio).
4. Prueba nueva `tests/test_entorno.py` (2 casos): carga un `.env` temporal con `AGENTE_SOLO_LECTURA=1   # comentario` y comprueba que `SoloLectura().activo` es `True` y que `PresupuestoLlamadas().maximo` es `12`; además comprueba que se conserva el `#` entre comillas y sin espacio delante. Ambos casos **fallan con el `cli.py` anterior** y pasan con el nuevo. Total: 24 pruebas.

**Lección.** Un control de seguridad configurable (aquí, el solo lectura) necesita una prueba que lo active **por el mismo camino que usará la persona**, no solo construyendo el objeto con `activo=True`.

## 2026-10-18 · `chat` respondía con un JSON en lugar de confirmar el pedido

**Síntoma.** Con `gpt-4.1-mini`, tras aprobar `crear_pedido_venta`, el pedido se creaba (S-ORD101001), pero la respuesta final del asistente era un `PedidoInterpretado` en JSON (`numero_cliente`, `lineas`, `referencia_externa`, `dudas`, `resumen`) en lugar de una frase con el número de pedido.

**Primer diagnóstico, equivocado.** Al principio se anotó que `respuesta.text` llegaba vacío. No era así: la CLI sí imprimía el texto, pero el filtro que se usó para ocultar las trazas de OpenTelemetry en la salida (que se saltaba los bloques entre una línea que empieza por `{` y otra que empieza por `}`) ocultaba también ese JSON. Ni el framework ni la CLI tenían ningún fallo. Se descubrió al volver a ejecutar con `ENABLE_SENSITIVE_DATA=1` y leer `gen_ai.output.messages` de la última llamada `chat`, y al mirar la salida en bruto. Lección: para diagnosticar, mirar la salida sin filtrar antes de concluir que algo falta.

**Causa (código del ejemplo, no del framework).** `crear_agente_asistente()` construía las instrucciones a partir de `prompts/interprete.md`, que dice «no respondes al cliente» y «Devuelve exclusivamente el objeto estructurado que se te pide». Un modelo real las obedece: tras la herramienta, devuelve el objeto. El párrafo añadido («Modo asistente: …») no decía cómo contestar al final.

**Por qué no lo detectaron las pruebas.** El modelo simulado no leía las instrucciones: en el papel `asistente` siempre confirmaba en texto, así que `"S-ORD" in final.text` pasaba con cualquier prompt.

**Corrección.**

1. `prompts/asistente.md`: instrucciones propias del asistente. Usa las mismas herramientas y reglas de identificación, llama a `crear_pedido_venta` y, cuando la herramienta responde, contesta en texto con el número, el cliente, las líneas y el total; nunca en JSON. `agentes.py` lo carga con `leer_prompt("asistente")`.
2. `modelo.py`: el `ClienteSimulado` lee `options["instructions"]` y, en el papel `asistente`, si contienen «Devuelve exclusivamente el objeto estructurado» (`SOLO_OBJETO_ESTRUCTURADO`), devuelve el JSON del pedido, como hizo `gpt-4.1-mini`.
3. Prueba nueva `test_tras_aprobar_el_asistente_confirma_en_texto_y_no_en_json` en `tests/test_chat_aprobacion.py`: comprueba que las instrucciones del asistente no piden el objeto estructurado y que, tras aprobar, el texto no empieza por `{` y contiene el número de pedido. Con el `agentes.py` anterior falla (y con él otras tres pruebas del mismo fichero, por la misma causa).

**Verificación con el modelo real (2026-10-18): no superada.** `CHAT_APROBAR=si python -m agente_pedidos chat "Empresa: Adatum Corporation. Necesito 5 lámparas AMSTERDAM"` con `gpt-4.1-mini`:

- La respuesta final ya es texto, no JSON: «He encontrado el cliente Adatum Corporation y el artículo AMSTERDAM Lamp con número 1928-S. ¿Confirmas que quieres pedir 5 unidades de esta lámpara?».
- Pero el modelo **no llamó a `crear_pedido_venta`**: hizo `buscar_clientes` y `buscar_articulos` (auditoría) y después pidió confirmación en el chat. No hubo petición de aprobación, `CHAT_APROBAR` no llegó a usarse y no se creó ningún pedido, así que no hay número de pedido, líneas ni total que comprobar.
- 3 llamadas al modelo (740/18, 802/20 y 870/37 tokens de entrada/salida; esta vez pidió las dos búsquedas en llamadas separadas), 2.412 / 75 tokens en total, coste estimado 0,0054 €. La CLI dice «1 respuesta(s) de agente».

**Causa probable: el prompt nuevo.** `prompts/asistente.md` dice «Es mejor preguntar que suponer» y «si no está claro, pregunta», pero no aclara que la aprobación de `crear_pedido_venta` ya es la confirmación de la persona. El modelo añadió su propia confirmación conversacional antes de la herramienta. Con el prompt anterior (el del intérprete) sí llamaba a la herramienta, pero luego contestaba en JSON.

**Ajuste del prompt.** En `prompts/asistente.md`, el paso 4 dice ahora que, con cliente, artículos y cantidades claros, llame directamente a `crear_pedido_venta` **sin pedir confirmación en el chat**, porque la herramienta se detiene a pedir la aprobación de una persona y esa aprobación ya es la confirmación. La regla «es mejor preguntar que suponer» queda limitada a cuando falta un dato o hay ambigüedad. La prueba con el modelo simulado no puede cubrir esto (el simulado no decide si pregunta o no); se verifica con el modelo real.

**Segunda verificación con el modelo real (2026-10-18): superada.** Mismo comando, `gpt-4.1-mini`:

- Se para a pedir aprobación: «EL AGENTE QUIERE EJECUTAR UNA HERRAMIENTA PROTEGIDA», `crear_pedido_venta` con cliente 10000 y 5 × 1928-S; `CHAT_APROBAR=si` la aprueba.
- Crea el pedido: S-ORD101001 (en la auditoría: `buscar_clientes`, `buscar_articulos`, `crear_pedido_venta`).
- Responde en texto, no en JSON: «He creado el pedido S-ORD101001 para Adatum Corporation con 5 lámparas AMSTERDAM, por un total sin impuestos de 279.5. Está en estado borrador pendiente de aprobación. ¿Quieres que te ayude con algo más?». Incluye número, cliente, líneas y total.
- 3 llamadas al modelo (817/53, 941/38 y 1.043/54), 2.801 / 145 tokens, coste estimado 0,0068 €.

**Observación menor (sin corregir).** «Pendiente de aprobación» no es exacto: el pedido ya se ha aprobado; `status: Draft` significa en Business Central que el pedido está abierto y sin lanzar. El modelo interpreta el estado por su cuenta. Si molesta, se puede añadir al prompt que no comente el estado o que explique «borrador = abierto, sin lanzar».

## 2026-10-18 · Aprobación por consola sin terminal

**Síntoma.** `chat` con stdin redirigido desde `NUL` (`< /dev/null` en Git Bash) se caía con `EOFError` en `input()`. `procesar` en modo `preguntar` llamaba siempre a `input()`, sin comprobar si había alguien delante.

**Causa.** `cmd_chat` usaba `sys.stdin.isatty()` para elegir entre preguntar y leer `CHAT_APROBAR`, pero en Windows el dispositivo `NUL` dice ser una terminal (`isatty()` devuelve `True`), y `input()` recibe EOF. `cmd_procesar` no comprobaba nada: con una tubería, cualquier «s» que llegara por stdin aprobaba el pedido.

**Corrección.** Función nueva `preguntar_aprobacion()` en `cli.py`, usada por `procesar` y `chat`:

- si stdin no es una terminal, o `input()` lanza `EOFError`, la aprobación **se deniega** (una escritura en el ERP nunca se aprueba por defecto);
- la denegación se escribe en la auditoría como `{"evento": "aprobacion_denegada", "motivo": …, "solicitud": …}`, con el nuevo `AuditoriaHerramientas.registrar()`, que también usan ahora los eventos de herramientas;
- en `chat`, `CHAT_APROBAR=si|no` sigue siendo la decisión explícita para ejecuciones sin terminal; si no está definida, se deniega.

**Cambio de comportamiento.** Pasar la respuesta por tubería (`echo s | python -m agente_pedidos procesar …`) ya no aprueba: una tubería no es una persona. Para ejecuciones desatendidas se usa `--aprobar si|no|pendiente`.

**Pruebas nuevas** (`tests/test_aprobacion_consola.py`, 2 casos): `procesar` con stdin por tubería que contiene «s» deniega, no crea el pedido y deja la denegación en la auditoría; `chat` con una consola que devuelve EOF deniega y `crear_pedido_venta` no llega a ejecutarse. Ambas fallan con el código anterior. Total: 27 pruebas.

## 2026-10-18 · Primera conexión a un sandbox real: 501 por `or` entre campos

**Contexto.** Primera ejecución contra un Business Central real (sandbox TEST29, empresa CRONUS ES, `BC_MODO=api`, `AGENTE_SOLO_LECTURA=1`) con `chat "Empresa: Adatum Corporation. Necesito 2 lámparas AMSTERDAM"`.

**Síntoma.** El token de Entra ID y la empresa se obtenían bien, pero `buscar_clientes` y `buscar_articulos` fallaban, y el agente le pedía a la persona que «confirmara el nombre del cliente». Llamando al cliente directamente, sin el modelo, salió el error:

```
Business Central respondió 501: The 'OR' operator is not supported on distinct fields on an OData filter.
```

**Causa.** `cliente_api.py` buscaba con un solo filtro que combinaba nombre y número: `contains(displayName,'…') or number eq '…'`. La API v2.0 de Business Central no admite `or` entre campos distintos y responde `501 Not Implemented`. El ERP simulado (`ClienteDemo`) filtra en memoria y no tiene esa limitación, así que ni la demo ni las pruebas podían verlo. **Solo aparece contra un Business Central real.**

**Dos fallos más que destapó.**

1. **Las lecturas no devolvían los errores del ERP como datos.** Solo `crear_pedido_venta` capturaba `ErrorBC`; las cuatro lecturas dejaban pasar la excepción. El framework se la pasaba al modelo como un error genérico («raised an exception», el detalle solo se ve con `include_detailed_errors=True`). Por eso el modelo culpó al nombre del cliente en lugar de explicar que había fallado el sistema. El README ya decía que los errores volvían como datos, pero no era cierto para las lecturas.
2. **La auditoría no registraba las herramientas que fallan.** `AuditoriaHerramientas` escribía después de `call_next()`; si la herramienta lanzaba una excepción, no quedaba ni rastro. En esa ejecución, `auditoria.jsonl` no tuvo ni una línea, aunque hubo dos llamadas al ERP real.

**Corrección.**

1. `cliente_api.py`: las búsquedas filtran por nombre (`contains(displayName,…)`; en artículos, una condición por palabra unida con `and`, que sí se admite al ser el mismo campo). Si el texto parece un código (`PARECE_CODIGO`: dígitos, o dígitos con sufijo como `1928-S`), se hace una segunda petición con `number eq '…'`, y se unen los resultados sin duplicados, con la coincidencia exacta primero.
2. `herramientas.py`: las cuatro lecturas capturan `ErrorBC` y devuelven `{"error": …}`, igual que la escritura.
3. `middleware.py`: la auditoría envuelve `call_next()` en `try/finally` y registra también las herramientas que fallan, con `error` (tipo y mensaje de la excepción) y `resultado: null`; la excepción se vuelve a lanzar sin cambios.

**Pruebas nuevas (11; total 38).**

- `tests/test_cliente_api.py` (6): el `ClienteApiV2` real contra una API simulada con `httpx.MockTransport` que, como la real, responde 501 si un filtro usa `or` entre campos distintos. Comprueba los filtros que se envían, la segunda petición solo para textos con forma de código, la unión sin duplicados y que un 501 llega como `ErrorBC` con su código. Con el `cliente_api.py` anterior fallan las 4 que dependen de la corrección.
- `tests/test_errores_erp.py` (5): las cuatro lecturas devuelven `{"error": …}` ante un `ErrorBC`, y la auditoría registra con su error una herramienta que lanza una excepción inesperada. Las 5 fallan con el código anterior.

**Lección.** Un ERP simulado sirve para el esqueleto, pero no reproduce las limitaciones del protocolo real (OData de Business Central). Contra el ERP real hay que probar antes las lecturas, sin el modelo, una a una.

## 2026-10-18 · Segunda prueba en el sandbox: el artículo no aparece y `blocked` llega como `_x0020_`

**Ejecución tras corregir los filtros.** `chat "Empresa: Adatum Corporation. Necesito 2 lámparas AMSTERDAM"` contra TEST29 con `AGENTE_SOLO_LECTURA=1` y `CHAT_APROBAR=si`: token ✅, empresa ✅, cliente ✅ (10000 Adatum Corporation, ya sin 501), artículo ❌ (`buscar_articulos("AMSTERDAM lámpara")` sin resultados) y, por tanto, bloqueo de la escritura sin probar: el agente no llegó a pedir `crear_pedido_venta`. 2 llamadas al modelo, 1.825 / 101 tokens, 0,0045 €. Esta vez la auditoría sí registró las dos lecturas.

**Hallazgo 1: el `contains` de Business Central distingue mayúsculas y tildes, y CRONUS ES tiene los nombres en español.** El artículo 1928-S se llama «Lámpara ÁMSTERDAM». Medido en TEST29 con `contains(displayName,'…')`: «Lámpara» → 1 resultado; «lámpara», «LÁMPARA», «lampara», «Lámparas», «ámsterdam» y «AMSTERDAM» → 0. Los datos de demostración (`datos_demo.json`) usan los nombres del CRONUS en inglés («AMSTERDAM Lamp») y `ClienteDemo` compara sin distinguir mayúsculas, así que la demo no podía mostrarlo.

**Corrección.** `buscar_articulos` en `cliente_api.py`:

1. Primero busca con todas las palabras (`contains(…) and contains(…)`), como antes. Si encuentra algo, no hace nada más.
2. Si no, busca **cada palabra útil por separado**: ignora las de menos de tres letras y las palabras vacías (`PALABRAS_VACIAS`: del, las, los, con, para, una…), pasa a singular las de cuatro letras o más acabadas en «s» (`contains` con «Lámpara» también encuentra «Lámparas») y prueba sus variantes de mayúsculas (tal cual, minúsculas, Capitalizada, MAYÚSCULAS). Cada petición filtra un solo campo, sin `or`.
3. Une los candidatos sin duplicados y los ordena en el código por cuántas palabras coinciden **sin tildes ni mayúsculas** (`_plegar`). «2 lámparas AMSTERDAM» → busca «lámpara» (encuentra «Lámpara ÁMSTERDAM» con la variante «Lámpara») y la pone primero porque «amsterdam» coincide con «ÁMSTERDAM» una vez plegado.

Las tildes no se pueden adivinar desde el código (una búsqueda de solo «AMSTERDAM» sigue sin encontrar «ÁMSTERDAM»). Por eso `prompts/interprete.md` y `prompts/asistente.md` piden además al modelo que, si una búsqueda no da resultados, la repita con el nombre en español y con tildes antes de concluir que el artículo no existe.

**Hallazgo 2: `blocked` de un cliente no bloqueado llega como `"_x0020_"`.** Es el valor en blanco del enum, con el espacio codificado al estilo XML. `politicas.py` considera bloqueado cualquier valor no vacío, así que **`procesar` contra un Business Central real habría rechazado todos los pedidos** con «el cliente está bloqueado (_x0020_)», y la herramienta se lo pasaba tal cual al modelo. Corrección: `cliente_api.py` decodifica el enum (`_decodificar_enum`) en `buscar_clientes` y `obtener_cliente`: `"_x0020_"` → `""`; un bloqueo real (`Ship`, `Invoice`, `All`) se conserva. Así las políticas y las herramientas reciben lo mismo que con `ClienteDemo`.

**Pruebas.** La API falsa de `tests/test_cliente_api.py` se comporta ahora como la real en lo medido: `contains` distingue mayúsculas y tildes, y `blocked` llega como `_x0020_`. 6 pruebas nuevas (total 44): normalización de `blocked` (y que «All» se conserva), desglose de palabras clave, búsqueda tolerante con tres redacciones («2 lámparas AMSTERDAM», «AMSTERDAM lámpara», «lampara de Ámsterdam») contra un catálogo como el de CRONUS ES, y que no se desglosa si la búsqueda completa encuentra algo. Con el `cliente_api.py` anterior el fichero de pruebas ni siquiera se importa (no existe `_palabras_clave`), así que esa comprobación aquí no aporta información.

**Lección.** Antes de diseñar una búsqueda contra el ERP real, medir cómo filtra (mayúsculas, tildes, plurales, idioma de los datos) con unas pocas lecturas directas; la API simulada de las pruebas debe imitar lo medido, no lo supuesto.

## 2026-10-18 · Tercera prueba en el sandbox: las cinco comprobaciones superadas

`chat "Empresa: Adatum Corporation. Necesito 2 lámparas AMSTERDAM"` contra TEST29 (CRONUS ES) con `AGENTE_SOLO_LECTURA=1` y `CHAT_APROBAR=si`, después de los commits de los filtros, `blocked` y la búsqueda tolerante:

| # | Comprobación | Resultado |
|---|---|---|
| 1 | Token de Entra ID | ✅ Obtenido |
| 2 | Empresa CRONUS ES | ✅ Encontrada |
| 3 | Cliente | ✅ `buscar_clientes("Adatum Corporation")` → 10000 Adatum Corporation, con `blocked: ""` (ya normalizado) |
| 4 | Artículo | ✅ `buscar_articulos("AMSTERDAM lamp")` → nada; el modelo repitió con `"Lámpara ÁMSTERDAM"` → 1928-S (504 en existencias, 55,20) |
| 5 | Bloqueo de la escritura | ✅ El agente pidió `crear_pedido_venta` (10000, 2 × 1928-S), `CHAT_APROBAR=si` lo aprobó y `SoloLectura` lo bloqueó: la auditoría registra la llamada con `{"error": "La herramienta 'crear_pedido_venta' está bloqueada por política: el agente está en modo solo lectura."}` |

Respuesta final: «He identificado el cliente Adatum Corporation y el artículo Lámpara ÁMSTERDAM con número 1928-S para 2 unidades, pero no puedo crear el pedido porque estoy en modo solo lectura.» Una lectura posterior de `salesOrders` (cliente 10000, fecha 2026-10-18) confirma que en TEST29 no se creó ningún pedido.

**Qué encontró el artículo.** Esta vez el modelo buscó en inglés («AMSTERDAM lamp»), y ni la búsqueda completa ni el desglose podían encontrar «Lámpara ÁMSTERDAM» («lamp» no está en «Lámpara»). Lo resolvió la línea nueva de los prompts: el modelo repitió la búsqueda en español y con tildes. El desglose del código cubre el caso en que el modelo usa palabras españolas sin tilde o en otra forma («2 lámparas AMSTERDAM», «lampara de Ámsterdam»); las dos medidas se complementan.

5 llamadas al modelo (918/18, 983/19, 1.012/22, 1.093/38, 1.183/53), 5.189 / 150 tokens, coste estimado 0,0116 €.

## 2026-10-18 · Búsqueda de clientes tolerante a mayúsculas y tildes

`buscar_clientes` tenía el mismo problema que los artículos: «adatum» no encontraba «Adatum Corporation» porque `contains` distingue mayúsculas. El desglose palabra por palabra pasa a un método común, `_buscar_por_palabras(entidad, texto, campos)`, que usan `buscar_articulos` y `buscar_clientes` cuando la búsqueda con el texto completo no da resultados. Los clientes encontrados por ese camino también pasan por la normalización de `blocked`. 4 pruebas nuevas en `tests/test_cliente_api.py` («adatum», «ADATUM CORPORATION», «corporation adatum» y «muebles ibanez» → «Muebles Ibáñez»); fallan con el código anterior. Total: 48.

## 2026-10-18 · Pedidos reales creados en el sandbox: flujo directo y flujo con aprobación

Sandbox TEST29 (CRONUS ES), `BC_MODO=api`, `AGENTE_SOLO_LECTURA=0`, umbral de aprobación 3.000 €, modelo `gpt-4.1-mini`.

**Correos nuevos**, con artículos y clientes reales de TEST29 consultados por API y los nombres tal como están en CRONUS ES (sin códigos de artículo, para que el modelo tenga que buscarlos):

- `ejemplos/correos/05_cronus_es_pequeno.txt`: Adatum Corporation, 10 × «Lámpara ÁMSTERDAM» (1928-S, 55,20) + 2 × «Silla inv. PARÍS, negra» (1900-S, 193,70) = 939,40 €.
- `ejemplos/correos/06_cronus_es_grande.txt`: Trey Research (20000), 3 × «Escritorio ATENAS» (1896-S, 1.005,80) + 4 × «Silla giratoria LONDRES, azul» (1908-S, 191,00) = 3.781,40 €.

**Flujo directo** (`procesar 05_cronus_es_pequeno.txt`): interpretar → validar → crear_pedido → redactar, sin aprobación (939,40 < 3.000). **Pedido 101021** creado en Business Central: Adatum Corporation, 939,40 € sin impuestos (el total que devuelve Business Central coincide con el que calcula el código), referencia ADT-8102, estado Draft. El intérprete encontró los dos artículos a la primera, buscando «Lámpara ÁMSTERDAM» y «Silla inv. PARÍS negra». 3 llamadas al modelo (1.363/76, 1.577/185, 287/98), 3.227 / 359 tokens, 0,0093 €.

**Flujo con aprobación** (`procesar 06_cronus_es_grande.txt --aprobar pendiente`, `pendientes`, `reanudar … --decision si --aprobador "Javier" --comentario "OK"`):

1. `procesar` se para en `aprobacion_humana` (3.781,40 > 3.000) y guarda el checkpoint `66f533d0-11ce-4e95-b80f-0c7d338dbb65`. 2 llamadas al modelo (1.364/76, 1.566/181), 2.930 / 257 tokens, 0,0079 € (calculado con las trazas: en modo `pendiente` la CLI termina sin imprimir el coste).
2. Pedidos en TEST29 leídos por API antes de procesar, durante la parada y justo antes de reanudar: el último seguía siendo el 101021. **Entre la parada y la reanudación no se creó ningún pedido.**
3. `reanudar`, en otro proceso: aprobacion_humana → crear_pedido → redactar. **Pedido 101022** creado: Trey Research, 3.781,40 € sin impuestos (Business Central coincide), referencia TRY-5531, estado Draft, «Aprobado por Javier: OK». 1 llamada al modelo (redactor), 283 / 100 tokens, 0,0014 €.

Total del flujo con aprobación: 3 llamadas, 3.213 / 357 tokens, 0,0093 €.

**Hallazgos (sin corregir).**

- **La escritura del workflow no queda en la auditoría.** El nodo `crear_pedido` (`workflow.py`) llama directamente a `bc.crear_pedido_venta`, sin pasar por las herramientas ni por el middleware. En `auditoria.jsonl` constan las lecturas del intérprete, pero **no la creación de los pedidos 101021 y 101022**, que son justo las operaciones que más interesa auditar. (En `chat` sí consta, porque la escritura es una herramienta.) Propuesta: que `CrearPedido` registre el intento y el resultado con `AuditoriaHerramientas.registrar()`, incluida la decisión humana (aprobador y comentario).
- **`pendientes` muestra aprobaciones ya resueltas.** Aparecieron cuatro checkpoints antiguos de hoy (Adatum, 5.875,60, de la demo y de `procesar` con aprobación en el mismo proceso) como si siguieran pendientes: cuando la aprobación se responde en el mismo proceso (`--aprobar si` o por consola), el checkpoint de la pausa no se marca como resuelto. Es peligroso con un ERP real: los artículos 1900-S y 1896-S existen también en CRONUS ES, así que `reanudar` sobre uno de esos checkpoints **crearía un pedido real de 5.875,60 € duplicado**. Propuesta: que `pendientes` ignore los checkpoints de ejecuciones que ya continuaron (o que se borren al terminar), y que `reanudar` se niegue a reanudar un checkpoint ya superado.
- **En modo `--aprobar pendiente`, `procesar` no imprime el coste** de la parte ya ejecutada (interpretar y validar).

## 2026-10-18 · Auditoría de escrituras, ciclo de vida de los checkpoints e idempotencia

Corrección de los tres hallazgos de la sección anterior.

**1. Las escrituras quedan en la auditoría, las pida el modelo o el workflow.** La escritura pasa a registrarse en la capa del cliente del ERP. `ClienteBC.crear_pedido_venta` (`bc/base.py`) es ahora un método común que llama a `_crear_pedido_venta` de cada implementación (`cliente_api.py`, `cliente_demo.py`) y registra el resultado con `AuditoriaHerramientas.registrar_escritura`: una línea `evento: escritura_erp` con los argumentos y la cabecera y las líneas del pedido creado, o con el error si falla. La CLI conecta la auditoría al cliente (`crear_cliente_bc(auditoria=…)`) en `procesar`, `reanudar` y `chat`.

Para no duplicar líneas en `chat`, donde la escritura llega a través de la herramienta `crear_pedido_venta` y el middleware también escribiría la suya, el middleware publica una marca en una `ContextVar` mientras ejecuta la herramienta. Si el cliente del ERP audita la escritura dentro de esa llamada, la anota (`origen: herramienta`) y el middleware no escribe otra línea. Desde el workflow no hay marca y la línea sale con `origen: codigo`. Una escritura bloqueada por `SoloLectura` no llega al ERP, así que la sigue registrando el middleware, con el error de política.

**2. Ciclo de vida de las aprobaciones guardadas.** Al resolverse una aprobación (en el mismo proceso con `--aprobar si|no` o por consola, o con `reanudar`), la CLI la anota en `checkpoints/aprobaciones_resueltas.jsonl` (checkpoint, fecha, decisión, aprobador y comentario). La extensión `.jsonl` evita que `FileCheckpointStorage`, que lee todos los `*.json` de la carpeta, lo tome por un checkpoint. Además, una aprobación también se considera resuelta si la ejecución ya continuó: hay un checkpoint posterior con su `previous_checkpoint_id`. Se comprobó en los cinco checkpoints de pausa resueltos hoy (todos tienen uno posterior), así que los cuatro antiguos de Adatum también dejan de salir sin necesidad de migrarlos.

- `pendientes` solo muestra las aprobaciones abiertas (`aprobaciones_pendientes`).
- `reanudar` comprueba antes de nada `motivo_para_no_reanudar` y, si el checkpoint ya está resuelto, termina con código 1 y un mensaje claro («No se reanuda el checkpoint … La aprobación de este checkpoint ya se resolvió el …: aprobada por Javier.»).

**Idempotencia.** Antes de crear un pedido con referencia externa, `ClienteBC.crear_pedido_venta` busca uno del mismo cliente con la misma referencia (`_buscar_pedido_por_referencia`; en la API, `GET salesOrders` con `customerNumber eq … and externalDocumentNumber eq …`, dos campos unidos con `and`, que sí se admite). Si existe, lanza `PedidoDuplicado` (subclase de `ErrorBC`, con el pedido existente) y no crea nada. La herramienta lo devuelve como `{"error": "Ya existe el pedido … del cliente … con la referencia …; no se crea otro"}` y el workflow como un resultado no creado con el número del pedido existente. El intento queda también en la auditoría, con el error. Sin referencia externa no hay comprobación: no hay nada fiable con que comparar.

**3. `procesar --aprobar pendiente` imprime el coste** de lo ejecutado hasta la parada («Coste hasta la parada: …»).

**Pruebas nuevas** (`tests/test_auditoria_checkpoints.py`, 8; total 56): un pedido creado desde el workflow aparece en `auditoria.jsonl` con sus líneas; en `chat` la escritura deja una sola línea; una escritura bloqueada por `SoloLectura` deja la suya; `pendientes` → `reanudar` → `pendientes` vacío → segundo `reanudar` rechazado (y el coste hasta la parada); una aprobación resuelta en el mismo proceso no queda pendiente, aunque se borre el registro; el mismo correo dos veces crea un solo pedido; la herramienta devuelve el duplicado como error de datos; contra la API simulada, un pedido existente no provoca ningún `POST`. Con el `cli.py` anterior fallan las tres pruebas que dependen de la CLI.

## 2026-10-18 · Verificación en el sandbox de auditoría, checkpoints e idempotencia

TEST29 (CRONUS ES), `BC_MODO=api`, `AGENTE_SOLO_LECTURA=0`, `gpt-4.1-mini`. La misma secuencia dos veces: `procesar 06_cronus_es_grande.txt --aprobar pendiente` → `pendientes` → `reanudar --decision si --aprobador "Javier" --comentario "OK"` → `pendientes` → segundo `reanudar` del mismo checkpoint. Los pedidos de TEST29 se leyeron por API antes, durante la parada y después.

**A · Referencia TRY-5531, la del pedido 101022 que ya existía (idempotencia contra el ERP real).**

- `procesar` se para en la aprobación (3.781,40 €) e imprime «Coste hasta la parada: … 0.0080 €» (2 llamadas, 2.930 / 263 tokens).
- `pendientes` muestra solo el checkpoint nuevo (`f6aaec24-…`); ya no aparecen los cinco anteriores.
- `reanudar` → «Pedido creado: no · Número de pedido: 101022 · No se ha creado un pedido nuevo: Ya existe el pedido 101022 del cliente 20000 con la referencia TRY-5531; no se crea otro». 1 llamada (redactor), 273 / 98 tokens, 0,0013 €.
- `pendientes` → «No hay aprobaciones pendientes.»; el segundo `reanudar` termina con código 1: «No se reanuda el checkpoint f6aaec24-… La aprobación de este checkpoint ya se resolvió el 2026-10-18T12:25:34…: aprobada por Javier.»
- En TEST29, el último pedido sigue siendo el 101022: **no se duplicó**. La auditoría registra el intento rechazado: `crear_pedido_venta · escritura_erp · origen: codigo · error: PedidoDuplicado: Ya existe el pedido 101022…`.

**B · Referencia nueva TRY-5532 (`06_cronus_es_grande.txt` cambia a esta referencia).**

- `procesar` se para e imprime «Coste hasta la parada: … 0.0079 €» (2 llamadas, 2.930 / 257 tokens). Durante la parada, el último pedido de TEST29 sigue siendo el 101022.
- `pendientes` muestra solo el checkpoint nuevo (`8a693c10-…`).
- `reanudar` crea el **pedido 101023**: Trey Research, 3.781,40 €, referencia TRY-5532, «Aprobado por Javier: OK». 1 llamada, 283 / 97 tokens, 0,0013 €.
- `pendientes` vacío y segundo `reanudar` rechazado con el mismo mensaje.
- **La auditoría registra la creación con sus líneas**: `crear_pedido_venta · escritura_erp · origen: codigo · {"number": "101023", "customerNumber": "20000", "externalDocumentNumber": "TRY-5532", "status": "Draft", "totalAmountExcludingTax": 3781.4, "lineas": [{"articulo": "1896-S", "descripcion": "Escritorio ATENAS", "cantidad": 3, "importe": 3017.4}, {"articulo": "1908-S", "descripcion": "Silla giratoria LONDRES, azul", "cantidad": 4, "importe": 764}]}`.

Las comprobaciones de las dos secuencias se cumplieron: coste impreso en la parada, `pendientes` solo con el checkpoint nuevo y luego vacío, segundo `reanudar` rechazado, escritura auditada (creada o rechazada) e idempotencia contra el ERP real.

## 2026-10-18 · Ejecuciones con el modelo real: llamadas y coste

Azure OpenAI, despliegue `gpt-4.1-mini`, `BC_MODO=demo` (ERP simulado: no se escribió nada real). Las llamadas al modelo salen de las trazas (`ENABLE_CONSOLE_EXPORTERS=1`, spans `chat`); sus tokens cuadran con la línea «Coste» de la CLI. El coste está calculado con las tarifas por defecto del ejemplo (2 € por millón de tokens de entrada y 8 € por millón de salida), no con la tarifa real de Azure.

| # | Ejecución | Resultado | Llamadas al modelo | Tokens entrada / salida | Coste estimado |
|---|---|---|---|---|---|
| 1 | `procesar 02_pedido_grande.txt` | Fallo al leer `.env` antes de llamar al modelo | 0 | 0 / 0 | 0 € |
| 2 | `procesar 02_pedido_grande.txt` («s» por tubería) | Se para a pedir aprobación; aprobado; S-ORD101001 creado | 3 (2 intérprete + 1 redactor) | 3.137 / 324 | 0,0089 € |
| 3 | `chat …` (stdin desde `NUL`) | Pide aprobación; `EOFError` al preguntar | 2 | 1.807 / 92 | 0,0044 € |
| 4 | `chat …` (`CHAT_APROBAR=si`) | Pedido creado; respuesta final en JSON | 3 | 2.875 / 177 | 0,0072 € |
| 5 | `chat …` (`CHAT_APROBAR=si`, `ENABLE_SENSITIVE_DATA=1`, diagnóstico) | Igual que la 4 | 3 | 2.875 / 177 | 0,0072 € |
| 6 | `procesar 02_pedido_grande.txt --aprobar si` (tras las correcciones) | Igual que la 2 | 3 (2 + 1) | 3.141 / 337 | 0,0090 € |
| 7 | `chat …` (`CHAT_APROBAR=si`, con `prompts/asistente.md`) | Responde en texto, pero pide confirmación en el chat y no llama a `crear_pedido_venta`; sin pedido | 3 | 2.412 / 75 | 0,0054 € |
| 8 | `chat …` (`CHAT_APROBAR=si`, prompt del asistente ajustado) | Pide aprobación, crea S-ORD101001 y responde en texto con número, cliente, líneas y total | 3 | 2.801 / 145 | 0,0068 € |
| 9 | `chat …` contra TEST29 (solo lectura) | Lecturas con 501 por `or` entre campos | sin trazas | 1.792 / 111 | 0,0045 € |
| 10 | `chat …` contra TEST29 (solo lectura) | Cliente encontrado; artículo no | 2 | 1.825 / 101 | 0,0045 € |
| 11 | `chat …` contra TEST29 (solo lectura) | Cinco comprobaciones superadas; escritura bloqueada por `SoloLectura` | 5 | 5.189 / 150 | 0,0116 € |
| 12 | `procesar 05_cronus_es_pequeno.txt` contra TEST29 | Pedido real 101021 (939,40 €), sin aprobación | 3 | 3.227 / 359 | 0,0093 € |
| 13 | `procesar 06_cronus_es_grande.txt --aprobar pendiente` contra TEST29 | Se para a pedir aprobación; checkpoint guardado | 2 | 2.930 / 257 | 0,0079 € |
| 14 | `reanudar --checkpoint 66f533d0-… --decision si` contra TEST29 | Pedido real 101022 (3.781,40 €) | 1 | 283 / 100 | 0,0014 € |
| 15 | Verificación A: `procesar 06 --aprobar pendiente` + `reanudar` (TRY-5531) | Duplicado detectado: no se crea otro pedido; 101022 devuelto como error de datos | 3 (2 + 1) | 3.203 / 361 | 0,0093 € |
| 16 | Verificación B: `procesar 06 --aprobar pendiente` + `reanudar` (TRY-5532) | Pedido real 101023 (3.781,40 €) con sus líneas en la auditoría | 3 (2 + 1) | 3.213 / 354 | 0,0093 € |
| | **Total del día** | | **39 + las de la 9** | **40.710 / 3.120** | **≈ 0,1064 €** |

Observaciones:

- La línea «Coste» de la CLI dice «2 respuesta(s) de agente»: cuenta respuestas de agente, no llamadas al modelo. Un agente con herramientas hace varias llamadas por respuesta (el intérprete hace 2: una para pedir las búsquedas, otra para devolver el pedido).
- El intérprete pidió las tres búsquedas (`buscar_clientes` y dos `buscar_articulos`) en una sola llamada, en paralelo; el modelo simulado las pide de una en una.
