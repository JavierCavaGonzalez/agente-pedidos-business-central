// La escena: arte provisional en SVG (o los PNG de art/ si existen) y, sobre cada mesa,
// personaje, rótulo, chapa de estado y bocadillo. Las posiciones salen de oficina.json.

import { el, svg, existeImagen } from "./util.js";

// Estado del agente -> nombre de la hoja de sprites en art/ (personaje_<nombre>.png).
const SPRITE_DE = { libre: "libre", trabajando: "trabajando", esperando_aprobacion: "esperando", error: "error", detenido: "libre" };

/** Qué arte definitivo hay en art/. El que falte se dibuja en SVG. */
export async function detectarArte() {
  const nombres = ["libre", "trabajando", "esperando", "error"];
  const [fondo, director, ...sprites] = await Promise.all([
    existeImagen("art/oficina.png"),
    existeImagen("art/director.png"),
    ...nombres.map((n) => existeImagen(`art/personaje_${n}.png`)),
  ]);
  return { fondo, director, sprites: Object.fromEntries(nombres.map((n, i) => [n, sprites[i]])) };
}

/** Coloca un elemento en coordenadas de la escena (1600×900 lógicos). */
function colocar(nodo, x, y) {
  nodo.style.left = `${x}px`;
  nodo.style.top = `${y}px`;
  return nodo;
}

// --- arte provisional ---------------------------------------------------------------------------

function rombo(x, y, ancho, alto) {
  return `${x - ancho / 2},${y} ${x},${y - alto / 2} ${x + ancho / 2},${y} ${x},${y + alto / 2}`;
}

/** Bloque isométrico: cara superior y dos laterales. */
function bloque(x, y, ancho, alto, grosor, colores) {
  const [arriba, izquierda, derecha] = colores;
  const a = ancho / 2, h = alto / 2;
  return svg("g", {},
    svg("polygon", { points: `${x - a},${y} ${x},${y + h} ${x},${y + h + grosor} ${x - a},${y + grosor}`, fill: izquierda }),
    svg("polygon", { points: `${x},${y + h} ${x + a},${y} ${x + a},${y + grosor} ${x},${y + h + grosor}`, fill: derecha }),
    svg("polygon", { points: rombo(x, y, ancho, alto), fill: arriba, stroke: "#0006", "stroke-width": 1 }),
  );
}

function mesa(x, y) {
  return svg("g", { class: "mesa" },
    bloque(x, y, 190, 96, 22, ["#7b8db3", "#4a5878", "#3a4662"]),
    // monitor y teclado
    svg("polygon", { points: `${x + 22},${y - 30} ${x + 70},${y - 54} ${x + 70},${y - 92} ${x + 22},${y - 68}`, fill: "#0b1630", stroke: "#cfe0ff", "stroke-width": 2 }),
    svg("polygon", { class: "pantalla", points: `${x + 26},${y - 36} ${x + 66},${y - 56} ${x + 66},${y - 86} ${x + 26},${y - 66}`, fill: "#2fb7ff", opacity: ".55" }),
    svg("polygon", { points: rombo(x + 4, y + 6, 54, 18), fill: "#25304a" }),
  );
}

function sala(x1, y1, x2, y2, etiqueta) {
  return svg("g", {},
    svg("rect", { x: x1, y: y1, width: x2 - x1, height: y2 - y1, fill: "#5fa8ff12", stroke: "#8fc2ff", "stroke-width": 3, "stroke-dasharray": "10 6" }),
    svg("text", { x: x1 + 12, y: y1 + 28, fill: "#8fc2ff", "font-family": "VT323, monospace", "font-size": 24 }, document.createTextNode(etiqueta)),
  );
}

function planta(x, y) {
  return svg("g", {},
    bloque(x, y, 34, 18, 22, ["#8a5a3c", "#6b4430", "#5a3826"]),
    svg("circle", { cx: x, cy: y - 22, r: 20, fill: "#2f9e5a" }),
    svg("circle", { cx: x - 12, cy: y - 34, r: 12, fill: "#3dbb6c" }),
    svg("circle", { cx: x + 12, cy: y - 36, r: 11, fill: "#3dbb6c" }),
  );
}

function suelo(config) {
  const { ancho, alto } = config.escena;
  const patron = svg("pattern", { id: "baldosa", width: 80, height: 40, patternUnits: "userSpaceOnUse" },
    svg("polygon", { points: "0,20 40,0 80,20 40,40", fill: "#152654", stroke: "#1f3470", "stroke-width": 1 }),
  );
  const d = config.director;
  return svg("svg", { class: "arte-provisional", viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, "aria-hidden": "true" },
    svg("defs", {}, patron),
    svg("rect", { width: ancho, height: alto, fill: "url(#baldosa)" }),
    // pared del fondo
    svg("rect", { width: ancho, height: 70, fill: "#0c1638" }),
    svg("rect", { y: 66, width: ancho, height: 6, fill: "#2f4a8f" }),
    // despacho del director (cristal), con mesa y planta
    sala(d.x - 150, 100, d.x + 170, 430, "Despacho"),
    bloque(d.x + 10, d.y + 30, 150, 74, 20, ["#9b7a5a", "#6e543c", "#5c4630"]),
    planta(d.x + 120, 170),
    // sala de reuniones con pizarra (arriba a la derecha)
    sala(1100, 100, 1560, 400, "Sala de reuniones"),
    svg("rect", { x: 1180, y: 130, width: 260, height: 110, fill: "#e9eef9", stroke: "#7f8db0", "stroke-width": 4 }),
    svg("line", { x1: 1200, y1: 160, x2: 1350, y2: 160, stroke: "#4d8dff", "stroke-width": 4 }),
    svg("line", { x1: 1200, y1: 185, x2: 1310, y2: 185, stroke: "#ff4d4d", "stroke-width": 4 }),
    bloque(1310, 320, 260, 110, 20, ["#7b8db3", "#4a5878", "#3a4662"]),
    // armario de servidores y archivadores (pared derecha)
    svg("rect", { x: 1500, y: 430, width: 70, height: 170, fill: "#1a2140", stroke: "#4d8dff", "stroke-width": 2 }),
    ...[0, 1, 2, 3, 4].map((i) => svg("rect", { x: 1510, y: 445 + i * 30, width: 50, height: 6, fill: i % 2 ? "#3ddc84" : "#2fb7ff" })),
    svg("rect", { x: 1420, y: 470, width: 60, height: 120, fill: "#56607a", stroke: "#2a3048", "stroke-width": 3 }),
    svg("line", { x1: 1420, y1: 510, x2: 1480, y2: 510, stroke: "#2a3048", "stroke-width": 3 }),
    svg("line", { x1: 1420, y1: 550, x2: 1480, y2: 550, stroke: "#2a3048", "stroke-width": 3 }),
    planta(980, 760),
    planta(80, 800),
    // mesas
    ...config.mesas.map((m) => mesa(m.x, m.y)),
  );
}

// --- personajes ----------------------------------------------------------------------------------

function figura({ camisa = "#2bb3a3", corbata = null } = {}) {
  return svg("svg", { viewBox: "0 0 96 120", "aria-hidden": "true" },
    svg("g", { class: "cuerpo" },
      svg("rect", { x: 22, y: 58, width: 52, height: 56, rx: 6, fill: "#26324f" }), // respaldo de la silla
      svg("rect", { x: 28, y: 56, width: 40, height: 46, rx: 10, fill: camisa }),
      corbata ? svg("polygon", { points: "48,58 44,64 48,86 52,64", fill: corbata }) : null,
      svg("circle", { cx: 48, cy: 40, r: 17, fill: "#f2c9a0" }),
      svg("path", { d: "M31 36 Q48 14 65 36 L65 30 Q48 10 31 30 Z", fill: "#3b2a1e" }),
      svg("rect", { x: 40, y: 38, width: 4, height: 4, fill: "#1b1b1b" }),
      svg("rect", { x: 52, y: 38, width: 4, height: 4, fill: "#1b1b1b" }),
      svg("g", { class: "brazos" },
        svg("rect", { x: 20, y: 74, width: 16, height: 12, rx: 4, fill: camisa }),
        svg("rect", { x: 60, y: 74, width: 16, height: 12, rx: 4, fill: camisa }),
      ),
      // mano levantada y reloj (esperando aprobación)
      svg("g", { class: "mano" },
        svg("rect", { x: 62, y: 30, width: 12, height: 32, rx: 5, fill: camisa }),
        svg("circle", { cx: 68, cy: 26, r: 7, fill: "#f2c9a0" }),
      ),
      svg("g", { class: "reloj" },
        svg("circle", { cx: 84, cy: 8, r: 11, fill: "#ffb020", stroke: "#06102a", "stroke-width": 3 }),
        svg("path", { d: "M84 2 V8 H89", stroke: "#06102a", "stroke-width": 3, fill: "none" }),
      ),
      // señal de error
      svg("g", { class: "alerta" },
        svg("rect", { x: 40, y: -18, width: 16, height: 16, fill: "#ff4d4d", stroke: "#06102a", "stroke-width": 3 }),
        svg("rect", { x: 46, y: -15, width: 4, height: 7, fill: "#fff" }),
        svg("rect", { x: 46, y: -6, width: 4, height: 3, fill: "#fff" }),
      ),
    ),
  );
}

/** Ajusta el personaje al estado: sprite PNG si existe, SVG animado si no. */
export function pintarPersonaje(nodo, estado, arte) {
  nodo.dataset.estado = estado;
  const nombre = SPRITE_DE[estado] || "libre";
  if (arte.sprites[nombre]) {
    nodo.classList.add("sprite");
    nodo.style.backgroundImage = `url("art/personaje_${nombre}.png")`;
  } else {
    nodo.classList.remove("sprite");
    nodo.style.backgroundImage = "";
  }
}

/**
 * Monta la escena y devuelve las referencias a lo que cambia con el estado.
 * acciones: { abrirFicha(agenteId), asignarTarea() }
 */
export function montarEscena(contenedor, config, arte, acciones) {
  contenedor.replaceChildren();
  contenedor.classList.toggle("con-fondo", arte.fondo);
  contenedor.append(suelo(config));

  // Director
  const d = config.director;
  const director = colocar(el("div", { class: "en-escena director", title: d.nombre }), d.x, d.y + 10);
  if (arte.director) {
    director.classList.add("sprite");
    director.style.backgroundImage = 'url("art/director.png")';
  }
  director.append(figura({ camisa: "#3d4f8f", corbata: "#ff4d4d" }));
  const despacho = colocar(el("div", { class: "en-escena despacho-rotulo" },
    el("div", { class: "rotulo" }, d.nombre, el("small", {}, "La persona al mando")),
    el("button", { class: "boton-pixel", type: "button", onclick: acciones.asignarTarea }, "Asignar tarea"),
  ), d.x, d.y + 110);
  contenedor.append(director, despacho);

  // Mesas
  const mesas = new Map();
  for (const m of config.mesas) {
    if (!m.agente) {
      contenedor.append(colocar(el("div", { class: "en-escena rotulo vacante" }, "Vacante", el("small", {}, m.vacante || "Próximo agente")), m.x, m.y + 92));
      continue;
    }
    const personaje = colocar(el("button", { class: "en-escena personaje", type: "button", "aria-label": "Abrir la ficha del agente", onclick: () => acciones.abrirFicha(m.agente) }, figura()), m.x - 30, m.y - 6);
    const bocadillo = colocar(el("div", { class: "en-escena bocadillo", role: "status" }), m.x - 30, m.y - 140);
    const rotulo = colocar(el("div", { class: "en-escena rotulo" }), m.x - 85, m.y + 92);
    const chapa = colocar(el("div", { class: "en-escena chapa" }), m.x + 125, m.y + 92);
    const contador = colocar(el("div", { class: "en-escena contador-aprobaciones", title: "Aprobaciones pendientes" }), m.x + 30, m.y - 120);
    contador.hidden = true;
    contenedor.append(personaje, bocadillo, rotulo, chapa, contador);
    mesas.set(m.agente, { mesa: m, personaje, bocadillo, rotulo, chapa, contador });
  }

  // Tablero de control
  const t = config.tablero;
  const cifras = {};
  const filas = [
    ["agentes_activos", "Agentes activos"],
    ["tareas_en_curso", "Tareas en curso"],
    ["aprobaciones_pendientes", "Aprobaciones pend."],
    ["escrituras_erp_hoy", "Escrituras ERP hoy"],
    ["coste_hoy_eur", "Coste hoy"],
    ["llamadas_modelo_hoy", "Llamadas modelo hoy"],
  ];
  const lista = el("dl", {});
  for (const [clave, texto] of filas) {
    cifras[clave] = el("dd", {}, "—");
    lista.append(el("dt", {}, texto), cifras[clave]);
  }
  const tablero = el("section", { class: "tablero", "aria-label": "Tablero de control" }, el("h2", {}, "TABLERO DE CONTROL"), lista);
  tablero.style.left = `${t.x - 10}px`;
  tablero.style.top = `${t.y - 30}px`;
  contenedor.append(tablero);

  return { mesas, cifras };
}
