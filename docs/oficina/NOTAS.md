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

## Frontend (torre de control, según `DIRECCION-VISUAL.md`)

`DIRECCION-VISUAL.md` sustituye a la sección 4 de la especificación y a `ARTE.md`. `ARTE.md` se ha borrado sin llegar a entrar en el repositorio. El backend, los eventos y las pruebas anteriores no cambian; lo nuevo del backend son añadidos (ver más abajo).

- **3D real con three.js 0.186 y sin compilación.** La skill `isometric-3d-dashboard` recomienda React, Vite y @react-three/fiber. El repositorio no tiene Node y la oficina arranca con un solo comando de Python, así que se respeta ese stack: three.js va como módulo ES local (`ui/static/vendor/`, importmap) en la misma versión que usa javiercava.com. Lo que la skill pide se cumple igual: cámara ortográfica isométrica (30°, como las maquetas de la web), giro y zoom acotados con el ratón y el teclado (flechas, + y −, 0 para volver), clic y paso del ratón sobre los objetos, etiquetas flotantes ancladas (CSS2DRenderer), geometrías simples, `pixelRatio` de 2 como máximo y una sola luz con sombra. Sin WebGL, los paneles funcionan igual y la escena lo dice (5).
- **Escena.** Planta en corte de diorama, con muros al fondo y ventanales. Contiene el despacho del director (mamparas de vidrio), cuatro mesas (la del Agente de Pedidos y tres vacantes atenuadas), la sala de reuniones y el edificio de **Business Central** fuera de la planta, con un camino de puntos desde la mesa del agente. El agente es un robot cuyos ojos, baliza y aro en el suelo llevan el color de su estado. Teclea cuando trabaja, levanta la mano cuando espera una aprobación y ladea la cabeza cuando hay un error. Al crear un pedido, un punto de oro recorre el camino hasta Business Central y la azotea se enciende. Con «reducir movimiento», las posturas son fijas y solo se enciende la azotea.
- **Tokens de javiercava.com** (de `src/styles/tokens.css` y `src/figuras/dibujo.css` de ese proyecto), en `ui/static/oficina.css`:
  - **Paleta**: marino `#081a30` (texto), azul `#1270ae` (lo que se pulsa), azul logotipo `#0a4d7a` (Business Central), oro del logotipo `#fdc308` (lo elegido y el flujo de un pedido), niebla `#f4f6f9` (fondo de la escena), bordes `#dbe3ec` y `#a9b8cb`.
  - **Arcilla fría de las maquetas** (muro, blanco, vidrio, acero…) para los volúmenes 3D, con luz desde arriba a la izquierda.
  - **Letras**: DM Sans para la interfaz y Archivo Estrecha para las cifras grandes y los títulos, las dos copiadas de la web con su licencia OFL.
  - **Radios**: recto en paneles y tarjetas, 4 px en botones y campos, pastilla en chips. La referencia hablaba de «bordes suaves», pero manda la web.
  - **Sombra** solo en lo que flota: etiquetas, ventanas y avisos.
  - **Lo elegido** lleva la línea de oro de 3 px debajo y el anillo de oro en el suelo.
- **Colores de estado.** Ámbar (esperando aprobación) es el oro 500 de la paleta, gris (libre) es el marino 300 y azul (detenido) es el azul 500. La web no tiene verde ni rojo, así que se añaden como acentos con la luminosidad de su azul: verde `#1f8a5b` (trabajando) y rojo `#c8402f` (error).
- **Composición** (mapa 1:1 con la referencia):
  - **Barra superior**: logo, buscador, «Simulación» o «Business Central · en vivo · <entorno>», modelo, Inmersivo, Ecosistema y Business Central ↗.
  - **Seis KPI.**
  - **Feed** a la izquierda, **escena** en el centro y **detalle** a la derecha.
  - **Seguimiento de tarea** abajo a la izquierda y **pedidos creados hoy** abajo en el centro.
  - Por debajo de 920 px de alto, la página se desplaza en lugar de comprimir los paneles. Por debajo de 1280 px de ancho, los paneles se apilan.
- **Seguimiento de tarea.** Sigue la tarea más urgente (esperando aprobación, después en curso, después la última) o la que elija la persona en el selector, en el feed o en la tabla de pedidos. La **tarjeta de aprobación** vive aquí, junto a las líneas del pedido. El nombre del aprobador va en la propia tarjeta y en el despacho del director, y se recuerda en el navegador. El tiempo del paso actual corre en vivo.
- **Feed.** Cada 3 s llega la foto con los últimos 80 eventos del día ya descritos por el backend. «Auto» desactivado congela la lista para leerla y cuenta los eventos nuevos.
- **Buscador.** Filtra el feed, los pedidos y el selector de tareas por texto. Si coincide con un agente, lo selecciona.
- **Ecosistema** abre un panel «próximamente» (v0.3). **Inmersivo** deja solo la escena; se sale con Esc.
- **Seguridad.** Todo texto de los datos entra con `textContent`. Los únicos `innerHTML` son los trazos de los iconos, que son constantes del código.
- `…/#ficha=pedidos` selecciona el agente al cargar y `…/#inmersivo` abre el modo inmersivo.

### Añadidos al backend para estos paneles (sin cambiar lo que ya había)

- **Enlace profundo a Business Central** (`ui/backend/business_central.py`): `https://businesscentral.dynamics.com/<tenant>/<entorno>?company=<empresa>&page=42&filter='No.' IS '<número>'`, con la URL codificada. Solo existe con `BC_MODO=api`; en simulación se indica «simulación». Lleva el tenant, porque es la URL del cliente web de Business Central, pero nunca credenciales. El inicio de sesión lo pide Business Central con los permisos de quien lo abre (2).
- **La foto (`/api/estado`)** añade claves sin tocar las anteriores: `seguimiento` de cada tarea, `pedidos` del día, `feed`, `erp` (modo, entorno, empresa, enlace, escrituras y bloqueos de hoy, última escritura), `presupuesto_dia_eur` (`OFICINA_PRESUPUESTO_DIA_EUR`, 1 € por defecto) y, por agente, herramientas con llamadas y errores, carga (tareas en curso frente a una capacidad de 3) y pedidos.
- **Evento `politica`.** Ahora lleva también el cliente, el total y las líneas validadas. Así el seguimiento muestra las líneas también cuando el pedido no necesita aprobación (4).
- **«Preguntar al agente»** (`POST /api/preguntas`) lanza `chat` como subproceso, igual que las tareas. El comando `chat` deja ahora rastro como tarea de clase «pregunta» y emite un evento nuevo, `respuesta_agente`, con la respuesta resumida y su coste (3, 4). Sin terminal y con `CHAT_APROBAR=no`, si el asistente intenta escribir se le deniega y queda en la auditoría: desde la pantalla, los pedidos solo se crean con la tarjeta de aprobación del workflow (2).
- **Estado del pedido en BC.** Se muestra como «Abierto», que es como lo deja el agente: no lo lanza ni lo registra. No se consulta a Business Central en cada foto.

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

- 99 pruebas, todas sin red. Entre ellas: enlaces profundos, seguimiento por pasos (pedido grande parado y aprobado, pequeño sin aprobación, denegado y rechazado), pedidos del día con su enlace solo en modo api, feed y herramientas, «Preguntar al agente» con su respuesta y su coste en eventos, secuencias de eventos de `procesar` y `reanudar`, derivación de estados y tablero, 409 por aprobación resuelta, por doble clic y por cambio de modo, y una **prueba de extremo a extremo** que lanza subprocesos reales con el ERP simulado: asignar el correo 02 → esperar aprobación → aprobar → pedido creado, coste en el tablero, cronología y auditoría.
- **Torre de control, probada desde la interfaz** con Playwright y Edge, con el ERP simulado y el modelo real de `.env`. Se pulsa «Asignar tarea» y se elige `02_pedido_grande.txt`. A los 22 s aparece la tarjeta de aprobación y el agente queda en «Esperando aprobación · 5.875,60 €», con 2 llamadas al modelo y 0,0078 € (captura `captura.png`). Al aprobar como «Javier» se crea S-ORD101001: el punto de oro llega a Business Central, la tabla de pedidos lo muestra como «simulación» y los KPI suben a 1 escritura, 3 llamadas y 0,0091 €. Los seis pasos quedan hechos, con «Aprobado por Javier».
- Al revisar las capturas se corrigieron:
  - El lienzo 3D se quedaba en blanco si el contenedor cambiaba de tamaño al llegar los datos. Ahora la fila de KPI tiene su alto reservado y el encuadre se recalcula en cada fotograma si cambia el tamaño.
  - La tarjeta de aprobación quedaba cortada.
  - El monitor tapaba la cara del agente.
  - Las etiquetas se pisaban en escenas estrechas.
- Revisión visual de la versión anterior (arte provisional) con Edge headless a 1280 y 1600 px. Arreglado tras las capturas: el director levantaba la mano, la tarjeta tapaba la chapa, la chapa tapaba el rótulo, el coste no cuadraba por el redondeo, el origen salía con el nombre del fichero de la bandeja, los números de pedido de la simulación se repetían, la chapa de la ficha se descolocaba y la página podía quedarse vacía al arrancar.
- **Pendiente:** la verificación con el sandbox real (correo 06 con una referencia externa nueva), después de que Javier vea la oficina con el ERP simulado.
