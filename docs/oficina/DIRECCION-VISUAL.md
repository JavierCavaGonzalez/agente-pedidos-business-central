# Oficina de agentes — dirección visual definitiva (sustituye ARTE.md y la sección 4 de ESPECIFICACION.md)

## Referencia

Una torre de control de almacén tipo "Atico" (Circe Innovation): ilustración isométrica 3D limpia en el centro, con etiquetas flotantes sobre cada zona (punto de color + nombre + porcentaje), y alrededor paneles de datos de producto: tira de KPI arriba, feed de actividad a la izquierda, panel de detalle a la derecha, línea de seguimiento de un pedido abajo a la izquierda y lista de pedidos abajo. Indicador «Business Central · en vivo», botones «Inmersivo», «Ecosistema» y «Business Central ↗». Estilo: interfaz clara, tipografía de producto, tarjetas con bordes suaves, nada de píxel art.

Aquí se hace **lo mismo para una oficina de agentes**: en vez de muelles y estanterías, mesas de agentes; en vez de carretillas, tareas; en vez de ocupación por zona, estado y coste por agente. Construir con la skill instalada `isometric-3d-dashboard`, siguiendo sus recomendaciones técnicas (motor 3D o isométrico en código, no imágenes generadas).

## Colores y tipografía

Los de la web javiercava.com: leer los tokens de diseño del proyecto `C:\dev\javiercava.com` (variables CSS, configuración de Impeccable o tailwind) y usar su paleta, su tipografía y sus radios y sombras. Si la web es clara, la oficina es clara; los colores de estado (verde trabajando, ámbar esperando aprobación, rojo error, gris libre, azul detenido) se toman de la paleta de la web si tiene equivalentes y, si no, se añaden como acentos coherentes. Documentar los tokens usados en `docs/oficina/NOTAS.md`.

## Composición de la pantalla (mapa 1:1 con la referencia)

**Barra superior**: nombre «Oficina de agentes» con el logo de la web; buscador («Buscar tarea, pedido, cliente o agente»); indicador de conexión: «Business Central · en vivo» (verde, `BC_MODO=api`, con el nombre del entorno) o «Simulación» (gris, modo demo); modelo en uso; botones «Inmersivo» (oculta los paneles y deja la escena a pantalla completa), «Ecosistema» (de momento abre un panel vacío con el texto «próximamente»; en la v0.3 será el mapa de agentes y sistemas) y «Business Central ↗» (abre el sandbox en el navegador).

**Tira de KPI** (bajo la barra): Agentes activos · Tareas hoy · Aprobaciones pendientes · Escrituras en el ERP hoy · Coste hoy (€) · Llamadas al modelo hoy. Cada tarjeta con punto de color y valor grande; actualización en vivo por SSE.

**Escena isométrica (centro)**: una planta de oficina con el despacho del director (la persona), cuatro mesas de agentes (una ocupada por el Agente de Pedidos, tres libres y atenuadas con el rótulo «Vacante · Compras / Finanzas / Almacén»), sala de reuniones y un bloque «Business Central» (un pequeño edificio o servidor con el logo) al que llegan las escrituras. Sobre cada mesa, una **etiqueta flotante** como las de zona de la referencia: punto de color de estado + nombre del agente + dato clave (p. ej. «● Agente de Pedidos · Trabajando · 2 min» o «● Esperando aprobación · 3.781 €»). Al crear un pedido, una animación corta (un punto que recorre el camino de la mesa al bloque de Business Central). Al pulsar una mesa, se selecciona el agente y el panel derecho muestra su detalle. La escena se puede rotar o hacer zoom si la skill lo ofrece; con teclado también.

**Feed de actividad (izquierda)**: lista en vivo de eventos con hora, icono, agente y texto («Buscando cliente Adatum Corporation», «Pedido 101023 creado · 3.781,40 €», «Aprobación solicitada · supera 3.000 €»), filtros por tipo (BC · tareas · aprobaciones · modelo), interruptor «Auto» para seguir el flujo, y dos botones: **«Asignar tarea»** (cuadro para pegar un correo o elegir uno de `ejemplos/correos/` y el agente destino) y **«Preguntar al agente»** (ejecuta el comando `chat`; la respuesta aparece en el feed con su coste).

**Panel de detalle (derecha)**: lo seleccionado. Para un agente: nombre, rol, estado, barra de «carga» (tareas en curso / capacidad) y barra de coste del día frente a un presupuesto configurable (`OFICINA_PRESUPUESTO_DIA_EUR`), sección «Herramientas» (nombre · llamadas · errores), sección «Pedidos creados hoy» (número, cliente, importe, enlace «Abrir en Business Central ↗») y botones «Detener» / «Activar». Para el bloque Business Central: entorno, empresa, escrituras hoy, última escritura.

**Seguimiento de tarea (abajo a la izquierda)**: línea de pasos como la de seguimiento de pedido de la referencia: **Recibido → Interpretado → Validado → Aprobación → Creado en BC → Respondido**, con el paso actual resaltado, el tiempo de cada paso y, debajo, las líneas del pedido (artículo · cantidad · importe) y el coste de la tarea. La tarjeta de **aprobación** aparece aquí mismo cuando la tarea está en el paso «Aprobación»: cliente, importe, líneas, motivo, aprobador y botones Aprobar / Denegar.

**Pedidos creados hoy (abajo, centro)**: lista con número, cliente, importe, estado en BC y enlace para abrir el pedido en Business Central.

## Enlaces a Business Central

El backend construye el enlace profundo de cada pedido a partir del `.env` (`BC_TENANT_ID`, `BC_ENVIRONMENT`, `BC_COMPANY_NAME`): `https://businesscentral.dynamics.com/<tenant>/<entorno>?company=<empresa codificada>&page=42&filter='No.' IS '<número>'` (página 42 = ficha de pedido de venta; codificar la URL). En modo simulación no hay enlace y se indica «simulación».

## Lo que no cambia

El backend (`ui/backend/`), la capa de eventos, los endpoints, las pruebas y el flujo asignar → trabajar → aprobar → pedido creado. Solo se sustituye el frontend. Debe seguir funcionando con `BC_MODO=demo` y `api`, arrancar con un solo comando y verse bien desde 1280 px.

## Criterio de aceptación

Una captura con el Agente de Pedidos en «Esperando aprobación», la tarjeta de aprobación en el seguimiento de tarea, el feed con los últimos eventos y los KPI con cifras reales debe poder ponerse junto a la referencia y leerse como el mismo tipo de producto: torre de control isométrica, clara, con los colores de javiercava.com.
