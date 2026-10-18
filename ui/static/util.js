// Utilidades sin dependencias. Todo el texto que viene de los datos se inserta con textContent:
// los correos son entrada no fiable y nunca se interpretan como HTML.

/** Crea un elemento: el("div", {class: "x", onclick: fn}, "texto", otroNodo). */
export function el(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2), valor);
    else if (clave === "dataset") Object.assign(nodo.dataset, valor);
    else nodo.setAttribute(clave, valor === true ? "" : valor);
  }
  for (const hijo of hijos.flat()) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return nodo;
}

const NS = "http://www.w3.org/2000/svg";

// useGrouping "always": 5.875,60 € (por defecto, es-ES no agrupa las cifras de cuatro dígitos).
const FORMATO_EUROS = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", useGrouping: "always" });
const FORMATO_COSTE = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: 4, maximumFractionDigits: 4, useGrouping: "always" });
const FORMATO_NUMERO = new Intl.NumberFormat("es-ES", { useGrouping: "always" });

// Redondeo «medio hacia arriba» sobre el valor decimal, igual que la CLI y el backend
// (redondear_eur): 0,00375 -> 0,0038 en los tres sitios.
const redondear = (n, decimales) => Math.round(n * 10 ** decimales + 1e-9) / 10 ** decimales;

export const euros = (n) => (n === null || n === undefined ? "—" : FORMATO_EUROS.format(redondear(n, 2)));
/** Costes del modelo: 4 decimales (0,0042 € no es «0,00 €»). */
export const coste = (n) => (n === null || n === undefined ? "—" : FORMATO_COSTE.format(redondear(n, 4)));
export const numero = (n) => (n === null || n === undefined ? "—" : FORMATO_NUMERO.format(n));

export function hora(ts) {
  if (!ts) return "—";
  return new Date(ts).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** «hace 35 s», «hace 4 min», «hace 2 h». */
export function hace(ts, ahora = Date.now()) {
  if (!ts) return "";
  const s = Math.max(0, Math.round((ahora - new Date(ts).getTime()) / 1000));
  if (s < 60) return `hace ${s} s`;
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  return `hace ${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}

export function duracion(segundos) {
  if (segundos === null || segundos === undefined) return "—";
  if (segundos < 60) return `${Math.round(segundos)} s`;
  const m = Math.floor(segundos / 60);
  return m < 60 ? `${m} min ${Math.round(segundos % 60)} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export const ESTADOS = {
  libre: "Libre",
  trabajando: "Trabajando",
  esperando_aprobacion: "Esperando aprobación",
  error: "Error",
  detenido: "Detenido",
};

/** fetch con JSON y errores legibles (el «detail» de FastAPI). */
export async function api(ruta, opciones = {}) {
  const respuesta = await fetch(ruta, {
    ...opciones,
    headers: { "Content-Type": "application/json", ...(opciones.headers || {}) },
    body: opciones.cuerpo ? JSON.stringify(opciones.cuerpo) : undefined,
  });
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const detalle = Array.isArray(datos.detail) ? datos.detail.map((d) => d.msg).join("; ") : datos.detail;
    const error = new Error(detalle || `Error ${respuesta.status}`);
    error.status = respuesta.status;
    throw error;
  }
  return datos;
}

// Iconos de trazo (24 × 24), dibujados para la oficina al estilo de Lucide
const ICONOS = {
  bc: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  tareas: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v3H9z"/><path d="M9 12h6M9 16h4"/>',
  aprobaciones: '<path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6z"/><path d="m9 12 2 2 4-4"/>',
  modelo: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
  error: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.5"/>',
  hecho: '<path d="m5 12 5 5 9-10"/>',
  fallido: '<path d="M7 7l10 10M17 7 7 17"/>',
  mano: '<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V11M11 10V4.5a1.5 1.5 0 0 1 3 0V11M14 10.5V6a1.5 1.5 0 0 1 3 0v8a7 7 0 0 1-7 7h-.5a6 6 0 0 1-4.6-2.2L3 15.5a1.6 1.6 0 0 1 2.4-2.1L8 16"/>',
};

/** Un icono de trazo como nodo SVG (los trazos son constantes del código, nunca datos). */
export function icono(nombre) {
  const nodo = document.createElementNS(NS, "svg");
  nodo.setAttribute("viewBox", "0 0 24 24");
  nodo.setAttribute("class", "icono");
  nodo.setAttribute("aria-hidden", "true");
  nodo.innerHTML = ICONOS[nombre] || ICONOS.tareas;
  return nodo;
}

export function avisar(texto, tipo = "info", ms = 6000) {
  const caja = el("div", { class: "aviso-flotante", dataset: { tipo }, role: "status" }, texto);
  document.getElementById("avisos").append(caja);
  setTimeout(() => caja.remove(), ms);
}
