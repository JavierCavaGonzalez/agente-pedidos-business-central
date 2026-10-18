# Oficina de agentes — notas de construcción (v0.2)

Decisiones tomadas al construir la oficina según [`ESPECIFICACION.md`](ESPECIFICACION.md), con el principio de la sección 1 en que se apoya cada una, y las limitaciones conocidas. Rama `oficina`.

Principios: (1) estado siempre visible, (2) la persona manda, (3) coste a la vista, (4) nada sin rastro, (5) honestidad visual.

## Capa de eventos

- **Una sola fuente para la pantalla (4).** Todo lo que se dibuja sale de `eventos.jsonl` o de los checkpoints (aprobaciones pendientes, como en el comando `pendientes`). El backend no guarda estado propio que pueda contradecir al registro. Hasta la detención de un agente es un evento (`agente_detenido` / `agente_activado`).
- **La tarea viaja sola.** La CLI fija el id de la tarea en una `ContextVar` y el workflow y el middleware lo leen sin pasarlo de mano en mano. La oficina crea el id y se lo pasa al subproceso en `AGENTE_TAREA`. `reanudar` lo recupera del propio checkpoint: va dentro de la `SolicitudAprobacion` (campo `tarea`). En un checkpoint anterior a los eventos, `reanudar` abre una tarea nueva para no perder el rastro.
- **Pasos emitidos.** Los de la especificación (`interpretar`, `validar`, `politica`, `crear_pedido`, `redactar`) y dos más para que el bocadillo no mienta: `aprobacion_humana` («Esperando la decisión del director») y `rechazar`. El paso `politica` lo emite el nodo `validar` con la decisión tomada por código («Necesita aprobación (5.875,60 €): …»).
- **`erp_bloqueada`** se emite cuando una escritura no llega al ERP por política: modo solo lectura (middleware), rechazo por validación (por ejemplo, cliente bloqueado), duplicado por referencia externa o error devuelto por Business Central.
- **Sin datos sensibles.** El resumen del correo quita las líneas `De:`/`Para:` y las direcciones de correo. Los argumentos de las herramientas se recortan y se ocultan las claves que parecen secretos. Los errores van sin traza, sin URLs y sin GUIDs (pueden llevar el tenant).
- **Coste de una tarea (3).** `coste_total_eur` de `tarea_terminada` es la suma de sus eventos `modelo_llamada`, no el contador del proceso. Así una tarea parada en un proceso y reanudada en otro cuenta su coste completo. Coincide con la línea «Coste» de la CLI (prueba `test_procesar_sin_aprobacion_produce_la_secuencia_esperada`).
- **Redondeo único.** 0,00375 € salía «0,0037» en la CLI (`f"{x:.4f}"` depende de la representación binaria) y «0,0038» en el navegador. La CLI, el backend y el navegador redondean ahora «medio hacia arriba» sobre el valor decimal (`redondear_eur`). Lo detectó la primera captura de la interfaz: el bocadillo y la tabla no coincidían.
- `eventos.jsonl` se escribe con `\n` también en Windows y una línea por escritura, para que varios procesos puedan añadir a la vez.

## Backend

- **La interfaz no ejecuta agentes (2).** Asignar una tarea lanza `python -m agente_pedidos procesar <fichero> --aprobar pendiente` y aprobar lanza `reanudar --decision si|no`, como subprocesos. La pantalla no puede saltarse el flujo definido en código: aprobar desde la tarjeta *es* `reanudar`. Por eso la aprobación queda en la auditoría y en los eventos exactamente igual que desde la terminal.
- **Estados del agente (1, 5).** Se derivan de la tarea más urgente de ver: error, después trabajando, después esperando aprobación. Con varias tareas a la vez, las tarjetas de aprobación se muestran igualmente y la mesa lleva un contador ámbar. Una aprobación pendiente sin eventos de hoy (de otro día) también pone al agente en «esperando aprobación».
- **Los 10 segundos del resultado (5).** La especificación dice que el agente vuelve a «libre» 10 s después de terminar. Durante esos 10 s el estado conserva el color (verde, o rojo si terminó con error), pero la chapa dice **«Terminado · Creado»** y no «Trabajando», que ya no sería verdad. El backend publica `resultado_reciente`.
- **409** si la aprobación ya se resolvió (en el mismo proceso o con `reanudar`), si ya hay un `reanudar` lanzado para ella (doble clic) o si se pidió con otro ERP (ver abajo).
- **Una aprobación del ERP simulado no se resuelve contra el real (2).** Los checkpoints de los dos modos comparten carpeta. Sin protección, una aprobación pedida con `BC_MODO=demo` y reanudada con `BC_MODO=api` habría creado un pedido real con datos de la simulación. La solicitud guarda `modo_erp`; `reanudar` y la oficina se niegan a resolverla con otro modo, antes de conectar con ningún ERP. La tarjeta lo explica y desactiva los botones.
- **ERP simulado compartido entre procesos.** `procesar` y `reanudar` son procesos distintos: con el ERP simulado en memoria, cada uno empezaba a numerar desde S-ORD101001 (dos pedidos distintos con el mismo número en pantalla) y la comprobación de duplicados no funcionaba entre ellos. Con `BC_DEMO_PEDIDOS=<fichero>` el `ClienteDemo` guarda sus pedidos en ese fichero. La oficina lo activa (`ui/bandeja/erp_demo_pedidos.json`); la CLI sola sigue en memoria, como antes.
- **Bandeja.** El correo se guarda como `ui/bandeja/<id>.txt` (como dice la especificación) y la salida del subproceso en `ui/bandeja/<id>.log`. El nombre legible («02_pedido_grande.txt» o «correo pegado en la oficina») se pasa a la CLI en `AGENTE_ORIGEN`.
- **Añadidos a la especificación.** `POST /api/agentes/{id}/activar` (sin él, detener no tendría vuelta atrás desde la pantalla) y `GET /api/correos` (los correos de ejemplo para el cuadro «Asignar tarea»).
- **SSE.** Al conectar se envía la foto completa. Después se vigila `eventos.jsonl` con `watchfiles` y se reenvía cada línea nueva seguida de la foto actualizada. Cada 3 s sin cambios se reenvía también la foto, para que lleguen solos los cambios que dependen del tiempo (volver a «libre»). Una línea a medio escribir espera a la siguiente vuelta.
- `app` se crea al pedirla (`ui.backend.app:app`), no al importar el módulo: las pruebas no tocan los ficheros reales.

## Frontend

- **Escena lógica de 1600×900 escalada** al ancho disponible, hasta 1920 px. Los rótulos, chapas, bocadillos y el tablero escalan con ella. La **tarjeta de aprobación**, la **ficha** y el cuadro de **asignar tarea** van en capas sin escalar, para que su texto se lea a 1280 px. La tarjeta se ancla a la mesa del agente que espera, al lado que tenga sitio, sin tapar nunca su chapa de estado.
- **Seguridad.** Todo texto que viene de los datos (correos, nombres, mensajes) se inserta con `textContent`, nunca como HTML: el correo es entrada no fiable.
- **Arte provisional** en SVG: suelo de baldosas isométricas, mesas como bloques, despacho de cristal, sala de reuniones, armarios y plantas. Los personajes son siluetas animadas con CSS: respira, teclea, mano levantada con reloj, exclamación roja; el estado detenido se ve en gris. Si existen `art/oficina.png`, `art/personaje_<estado>.png` o `art/director.png`, se usan sin tocar código (ver `ui/static/art/LICENCIA.md`).
- **Robustez.** Además del SSE (que reconecta solo), el navegador pide `/api/estado` al arrancar y al reconectar, y si pasan 8 s sin recibir estado. Lo motivó una captura en la que la página quedó vacía mientras arrancaba.
- **Tipografía.** VT323 de Google Fonts solo en rótulos y tablero; el texto largo, en la fuente del sistema. Sin conexión a internet se usa una monoespaciada del sistema.
- `…/#ficha=pedidos` abre la ficha del agente al cargar (útil para enlazarla y para capturas).
- El nombre del director (campo de la cabecera) se recuerda en el navegador (`localStorage`). Es solo una comodidad.

## Arranque

- `python -m agente_pedidos.oficina` (con `PYTHONPATH=src` o el paquete instalado con `pip install -e ".[ui]"`), desde una copia del repositorio. Escucha **solo en 127.0.0.1** y no tiene opción para cambiarlo: esta versión no tiene autenticación.
- `--bc demo|api` y `--modelo …` mandan sobre `.env` en esa sesión, también para los subprocesos. Con `--bc api` el arranque avisa en la consola de si las tareas escriben en Business Central real o están en solo lectura.

## Limitaciones conocidas

- **El nombre del aprobador no se verifica.** Es un campo de texto: queda en la auditoría tal como se escribe. La autenticación queda para la v0.3.
- **Detener no mata procesos.** Un agente detenido no recibe tareas nuevas, pero lo que ya está en marcha termina. Sus aprobaciones pendientes se pueden seguir resolviendo: decide el director.
- **`eventos.jsonl` crece sin límite** y se relee entero en cada foto (cada ~3 s por cliente conectado). Sirve para el uso de un día; habrá que rotarlo por día o pasar a SQLite si crece.
- **Un solo agente real.** Las otras mesas son vacantes. La estructura (`AGENTES` en `ui/backend/estado.py`, `mesas` en `oficina.json`) está preparada para más.
- El bocadillo de una herramienta se arma con plantillas por nombre (`buscar_clientes` → «Buscando cliente «…»»). Una herramienta nueva sin plantilla sale como «Usando <nombre>».

## Verificación

- 88 pruebas, todas sin red. Entre ellas: secuencias de eventos de `procesar` y `reanudar`, derivación de estados y tablero, 409 por aprobación resuelta, por doble clic y por cambio de modo, y una **prueba de extremo a extremo** que lanza subprocesos reales con el ERP simulado: asignar el correo 02 → esperar aprobación → aprobar → pedido creado, coste en el tablero, cronología y auditoría.
- Revisión visual con Edge headless a 1280 y 1600 px. Arreglado tras las capturas: el director levantaba la mano, la tarjeta tapaba la chapa, la chapa tapaba el rótulo, el coste no cuadraba por el redondeo, el origen salía con el nombre del fichero de la bandeja, los números de pedido de la simulación se repetían, la chapa de la ficha se descolocaba y la página podía quedarse vacía al arrancar.
- **Pendiente:** la verificación con el sandbox real (correo 06 con una referencia externa nueva), después de que Javier vea la oficina con el ERP simulado.
