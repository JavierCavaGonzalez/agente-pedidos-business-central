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
| | **Total del día** | | **20** | **19.048 / 1.327** | **≈ 0,0487 €** |

Observaciones:

- La línea «Coste» de la CLI dice «2 respuesta(s) de agente»: cuenta respuestas de agente, no llamadas al modelo. Un agente con herramientas hace varias llamadas por respuesta (el intérprete hace 2: una para pedir las búsquedas, otra para devolver el pedido).
- El intérprete pidió las tres búsquedas (`buscar_clientes` y dos `buscar_articulos`) en una sola llamada, en paralelo; el modelo simulado las pide de una en una.
