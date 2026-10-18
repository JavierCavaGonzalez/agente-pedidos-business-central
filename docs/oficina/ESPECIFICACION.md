# Oficina de agentes — especificación de la interfaz gráfica (v0.2)

## 1. Qué es y para qué

Una interfaz web que representa el sistema de agentes como una **oficina isométrica en píxel art**: cada agente es un empleado sentado en su mesa, con su nombre, su rol y su estado visible; la persona que gobierna el sistema es el **director** (tiene su despacho en la escena) y un **tablero de control** resume en todo momento qué está pasando y cuánto cuesta. Es la primera pieza visible de una "torre de control" de agentes sobre Business Central.

Principios (capítulo 3 de *Designing Multi-Agent Systems*, Victor Dibia — UX para sistemas multiagente):

1. **Estado siempre visible**: en cualquier momento se ve qué hace cada agente, en qué paso está y desde cuándo.
2. **La persona manda**: el director asigna tareas, aprueba o deniega escrituras en el ERP y puede detener a un agente. Nada entra en Business Central sin que el flujo definido en código lo permita.
3. **Coste a la vista**: llamadas al modelo, tokens y euros, por agente y total del día.
4. **Nada sin rastro**: todo lo que se dibuja sale de eventos registrados; si no hay evento, no hay dibujo.
5. **Honestidad visual**: los estados "esperando aprobación" y "error" se ven desde lejos; no se maquilla nada.

No es un juego: es un panel operativo con estética de oficina. La estética ayuda a entender (un agente es como un empleado con permisos limitados); el contenido es el de una consola de operaciones.

## 2. Alcance de la v0.2 (MVP) y lo que queda fuera

Dentro:
- Un único agente real en su mesa: **Agente de Pedidos** (rol: Ventas). El resto de mesas aparecen libres con el rótulo "Vacante" (futuros agentes: Compras, Finanzas, Almacén) para que se entienda que la oficina crece.
- Despacho del director (la persona) y tablero de control.
- Flujo completo desde la interfaz: asignar una tarea (un correo de pedido) → ver al agente trabajar paso a paso → tarjeta de aprobación cuando el importe supera el umbral → aprobar o denegar desde la pantalla → ver el pedido creado (número de Business Central) y el coste.
- Ficha de cada agente: cronología de eventos, herramientas usadas, pedidos creados, coste acumulado.
- Funciona con el ERP simulado y con el sandbox real, igual que la CLI (`BC_MODO`).

Fuera (v0.3 o posterior): varios agentes reales a la vez, chat con el agente desde la oficina ("¿cómo va el módulo?"), autenticación de usuarios, despliegue en Azure, varios directores. Se deja la arquitectura preparada, pero no se construye.

## 3. Arquitectura

```
[agente_pedidos (ya existe)] --escribe--> eventos.jsonl --lee--> [backend FastAPI] --SSE--> [frontend web]
        ^                                                              |
        |---------------- subprocesos: procesar / reanudar -----------|
```

### 3.1 Capa de eventos (en el paquete `agente_pedidos`)

Nuevo módulo `src/agente_pedidos/eventos.py` con una función `emitir(tipo, agente, **datos)` que añade una línea JSON a `eventos.jsonl` (ruta configurable con `AGENTE_EVENTOS`, por defecto `eventos.jsonl`; añadir a `.gitignore`). Cada evento: `{"ts": ISO-8601 con zona, "agente": "pedidos", "tarea": id de tarea o null, "tipo": ..., "datos": {...}}`.

Tipos de evento (mínimo):
- `tarea_iniciada` — datos: `origen` (nombre del correo), `resumen` (primeras líneas sin datos sensibles).
- `paso` — datos: `nombre` del paso del workflow (interpretar, validar, politica, crear_pedido, redactar) y `descripcion` legible ("Buscando cliente Adatum Corporation").
- `modelo_llamada` — datos: `modelo`, `tokens_entrada`, `tokens_salida`, `coste_eur`.
- `herramienta` — datos: `nombre`, `argumentos` (resumidos, sin secretos), `resultado` ("ok" o el error), `duracion_ms`.
- `aprobacion_solicitada` — datos: `checkpoint_id`, `cliente`, `importe`, `lineas` (resumen), `motivo` ("supera el umbral de 3.000 €").
- `aprobacion_resuelta` — datos: `checkpoint_id`, `decision` (si/no), `aprobador`, `comentario`.
- `erp_escritura` — datos: `operacion` ("crear_pedido"), `pedido` (número de BC), `importe`, `modo` (demo/api).
- `erp_bloqueada` — escritura bloqueada por política (solo lectura, cliente bloqueado, duplicado…), con el motivo.
- `tarea_terminada` — datos: `resultado` (creado / rechazado / denegado / error), `pedido`, `coste_total_eur`, `duracion_s`.
- `error` — datos: `mensaje` (sin secretos ni trazas completas).

Dónde se emiten: en el middleware existente (herramientas y modelo), en los ejecutores del workflow (pasos, aprobación, escritura) y en la CLI (inicio y fin de tarea). `auditoria.jsonl` no cambia: sigue siendo el registro de auditoría; `eventos.jsonl` es el registro operativo para la interfaz. Las pruebas existentes deben seguir pasando; añadir pruebas de que un `procesar` con el ERP simulado produce la secuencia de eventos esperada.

Identificador de tarea: la CLI genera uno (`tarea_<fecha>_<4 hex>`) al empezar `procesar` y lo propaga; `reanudar` recupera el de la tarea original desde el checkpoint.

### 3.2 Backend (`ui/backend/`)

FastAPI + uvicorn. Sin autenticación en el MVP (solo escucha en `127.0.0.1`). Endpoints:

- `GET /api/estado` — foto completa: agentes (con estado derivado de los eventos), tareas del día, aprobaciones pendientes, totales del tablero.
- `GET /api/eventos` — flujo SSE: reenvía cada línea nueva de `eventos.jsonl` (vigilar el fichero con `watchfiles`); al conectar, envía primero el estado completo.
- `POST /api/tareas` — cuerpo: `{"agente": "pedidos", "correo": "texto del correo"}`. Guarda el correo en `ui/bandeja/<id>.txt` y lanza `python -m agente_pedidos procesar <fichero> --aprobar pendiente` como subproceso (sin bloquear). Devuelve el id de tarea.
- `GET /api/aprobaciones` — pendientes (lee los checkpoints igual que el comando `pendientes`).
- `POST /api/aprobaciones/{checkpoint_id}` — cuerpo: `{"decision": "si"|"no", "aprobador": "...", "comentario": "..."}`. Lanza `reanudar` como subproceso. Un checkpoint ya resuelto devuelve 409.
- `POST /api/agentes/{id}/detener` — marca al agente como detenido: el backend no lanza nuevas tareas para él y lo muestra en estado "detenido" (el MVP no mata procesos en curso; se documenta).
- `GET /api/agentes/{id}/cronologia` — eventos de ese agente del día.

Estado del agente, derivado del último evento de su tarea en curso: `libre` (sin tarea), `trabajando` (tarea iniciada o paso), `esperando_aprobacion` (aprobación solicitada sin resolver), `error` (último evento error), `detenido` (por el director). Un agente con tarea terminada vuelve a `libre` tras 10 segundos (para que se vea el resultado).

Tablero: agentes activos (no libres), tareas en curso, aprobaciones pendientes, escrituras en el ERP hoy, coste hoy (suma de `coste_eur`), llamadas al modelo hoy.

Pruebas con pytest: derivación de estados a partir de secuencias de eventos, cálculo del tablero, rechazo de aprobación ya resuelta, y una prueba de extremo a extremo con el ERP simulado (crear tarea → esperar aprobación → aprobar → pedido creado).

### 3.3 Frontend (`ui/static/`)

HTML, CSS y JavaScript sin paso de compilación (módulos ES nativos). Sin framework. Opcional: PixiJS solo si hace falta para las animaciones; preferible no.

Técnica: **fondo + capas**. La oficina es una imagen de fondo isométrica (`art/oficina.png`) con las mesas en posiciones conocidas, definidas en `ui/static/oficina.json`:

```json
{
  "escena": {"ancho": 1600, "alto": 900},
  "director": {"x": 180, "y": 260, "nombre": "Director"},
  "tablero": {"x": 1250, "y": 640},
  "mesas": [
    {"id": "m1", "x": 520, "y": 300, "agente": "pedidos"},
    {"id": "m2", "x": 820, "y": 300, "agente": null},
    {"id": "m3", "x": 520, "y": 560, "agente": null},
    {"id": "m4", "x": 820, "y": 560, "agente": null}
  ]
}
```

Sobre cada mesa se superponen, posicionados en absoluto y escalados con la escena:
- el **sprite del personaje** (`art/personaje_<estado>.png`, hoja de sprites de 4 fotogramas, animación CSS con `steps(4)`: libre = respira, trabajando = teclea, esperando = mano levantada, error = señal roja);
- el **rótulo** con nombre y rol (estilo etiqueta de píxel, como en la referencia);
- la **chapa de estado** (verde trabajando, ámbar esperando aprobación, gris libre, rojo error, azul detenido);
- el **bocadillo** con el paso actual ("Buscando artículo Lámpara ÁMSTERDAM…"), que se actualiza con cada evento `paso` o `herramienta`.

Elementos fijos: despacho del director con un botón "Asignar tarea" (abre un cuadro para pegar o elegir un correo y el agente destino); **tablero de control** (panel de píxel con las seis cifras, actualización en vivo); **tarjeta de aprobación** anclada a la mesa del agente que espera, con cliente, importe, líneas y los botones Aprobar / Denegar / Ver detalle; **ficha del agente** (panel lateral al pulsar el personaje) con cronología, herramientas, pedidos y coste.

Tipografía de píxel (Google Fonts "Press Start 2P" o "VT323") solo en rótulos y tablero; el texto largo de fichas y tarjetas en una fuente legible normal. Paleta: la de la referencia (azules oscuros de fondo, acentos verde/ámbar/rojo para estados). Reconexión automática del SSE. Debe verse bien a 1280 px de ancho y escalar hasta 1920.

### 3.4 Arranque

`python -m agente_pedidos.oficina` (o `uvicorn ui.backend.app:app`) levanta el backend y sirve el frontend en `http://127.0.0.1:8765`. Documentar en el README (sección nueva "Oficina de agentes") con una captura.

## 4. Arte: cómo conseguir el aspecto de la referencia sin copiarla

La imagen de referencia no es nuestra y no se copia. Se generan assets propios en el mismo estilo (píxel art isométrico, oficina moderna, paleta azul oscuro con acentos) y se guardan los originales en `ui/static/art/` con un `LICENCIA.md` que diga cómo se crearon.

Orden de trabajo: **primero el sistema con arte provisional, después el arte definitivo.**
1. Primero construyo todo con placeholders dibujados en CSS/SVG (mesas como bloques isométricos, personajes como siluetas de color). El sistema funciona de extremo a extremo sin ninguna imagen.
2. Después genero el arte con un modelo de imágenes usando estos prompts, y guardo los PNG con los nombres indicados; el frontend los usa automáticamente si existen.

Prompts de generación (ajustar a gusto, mantener consistencia entre ellos):
- `oficina.png` (1600×900, sin personajes): "Pixel art isometric modern office floor seen from above, dark navy background, four empty desks with monitors arranged in a 2×2 grid in the centre, a glass-walled manager office in the top-left corner with a desk and a plant, a meeting room with a whiteboard in the top-right corner, a server rack and filing cabinets along the right wall, a large empty wall-mounted status board in the bottom-right corner, clean 16-bit style, crisp pixels, no text, no characters."
- `personaje_libre.png`, `personaje_trabajando.png`, `personaje_esperando.png`, `personaje_error.png` (hojas de 4 fotogramas, 64×64 por fotograma, fondo transparente): "Pixel art sprite sheet, 4 frames side by side, isometric office worker seated at a desk typing on a keyboard, 16-bit style, transparent background, consistent character design" (variar: idle breathing; typing; raising one hand with a small clock icon above; holding head with a red exclamation mark above).
- `director.png` (un personaje de pie o sentado en el despacho, 2 fotogramas).

Si la consistencia entre imágenes generadas no sale bien a la primera, generar una sola escena completa con personajes y recortar los sprites, repitiendo la escena con cada estado.

## 5. Entregables

Trabajar en la rama `oficina` (no en `main`): el artículo enlaza la etiqueta `v0.1.0` y no debe cambiar.

1. `src/agente_pedidos/eventos.py` y la emisión de eventos en middleware, workflow y CLI; pruebas; `.gitignore` con `eventos.jsonl` y `ui/bandeja/`.
2. `ui/backend/` (FastAPI) con los endpoints de 3.2 y sus pruebas; dependencias en `requirements-ui.txt` y extra `[ui]` en `pyproject.toml`.
3. `ui/static/` con el frontend de 3.3, arte provisional en CSS/SVG y carga automática de los PNG definitivos si existen.
4. Comando de arranque, sección del README con instrucciones y captura, y `docs/oficina/NOTAS.md` con decisiones y limitaciones.
5. Verificación con el ERP simulado: asignar el correo `02_pedido_grande.txt` desde la interfaz, ver al agente trabajar, aprobar desde la tarjeta y ver el pedido creado y el coste en el tablero. Después, una verificación con el sandbox real con el correo 06 (cambiando la referencia externa para que no sea duplicado).
6. Commits pequeños con mensajes claros; al final, fusionar en `main`, etiqueta `v0.2.0` y push.

Lista de comprobación final: ¿se ve el estado de cada agente sin pulsar nada? ¿la aprobación se hace desde la pantalla y queda en auditoría y en eventos? ¿el coste del tablero coincide con el de la CLI? ¿funciona con `BC_MODO=demo` y con `api`? ¿nada en pantalla sale de datos inventados? ¿el sistema arranca con un solo comando? ¿el arte provisional se sustituye sin tocar código?
