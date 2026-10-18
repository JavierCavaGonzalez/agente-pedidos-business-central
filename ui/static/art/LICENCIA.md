# Arte de la oficina

Esta carpeta guarda el arte definitivo de la oficina. Mientras no haya ningún PNG, el frontend dibuja un **arte provisional en SVG/CSS** (mesas como bloques isométricos, personajes como siluetas), generado por código en `ui/static/escena.js` y publicado con la misma licencia MIT que el resto del repositorio.

## Ficheros que usa el frontend si existen

No hay que tocar código: si un fichero existe, se usa; si no, se dibuja el provisional.

| Fichero | Tamaño | Contenido |
|---|---|---|
| `oficina.png` | 1600×900 | Fondo isométrico sin personajes (mesas en las posiciones de `ui/static/oficina.json`) |
| `personaje_libre.png` | 256×64 | Hoja de 4 fotogramas de 64×64: respira |
| `personaje_trabajando.png` | 256×64 | Teclea |
| `personaje_esperando.png` | 256×64 | Mano levantada con un reloj encima (esperando aprobación) |
| `personaje_error.png` | 256×64 | Se lleva las manos a la cabeza, exclamación roja |
| `director.png` | 128×64 | El director, 2 fotogramas de 64×64 |

El estado «detenido» usa `personaje_libre.png` en gris (filtro CSS).

## Origen y licencia

La imagen de referencia de la especificación **no se copia**. Cada PNG que se añada aquí debe ser propio. Al añadirlo, anota debajo cómo se creó (herramienta o modelo de imágenes, fecha y prompt) y con qué licencia se publica.

| Fichero | Cómo se creó | Fecha | Licencia |
|---|---|---|---|
| — | — | — | — |

Los prompts sugeridos están en `docs/oficina/ESPECIFICACION.md`, sección 4.
