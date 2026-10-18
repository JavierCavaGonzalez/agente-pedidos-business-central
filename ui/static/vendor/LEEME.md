# Dependencias del frontend, copiadas tal cual (sin compilación ni Node)

| Fichero | Origen | Licencia |
|---|---|---|
| `three/three.module.js`, `three/three.core.js` | three.js 0.186.1 (`build/`), la misma versión que usa javiercava.com | MIT (`three/LICENSE`) |
| `three/addons/OrbitControls.js`, `CSS2DRenderer.js`, `RoundedBoxGeometry.js` | three.js 0.186.1 (`examples/jsm/`) | MIT |

Fuentes (`../fuentes/`), las de javiercava.com: DM Sans variable (Fontsource), Archivo al 75 % de ancho
(«Archivo Estrecha», instancia de javiercava.com) e IBM Plex Mono 400. Todas con licencia SIL OFL 1.1
(ficheros `OFL-*.txt`).

Imágenes (`../img/`): el icono de javiercava.com (`logo-icono-60.webp`, de Javier Cava) y el logotipo de
Business Central (`business-central.svg`, marca de Microsoft, usado solo para identificar el sistema con el que
se conecta la oficina).

Para actualizar three.js: copiar los mismos ficheros de una versión nueva (`npm pack three@<versión>`) y
comprobar la oficina en el navegador.
