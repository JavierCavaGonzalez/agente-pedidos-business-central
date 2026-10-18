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

/** Igual que el(), para SVG. */
export function svg(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElementNS(NS, etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) nodo.setAttribute(clave, valor);
  for (const hijo of hijos.flat()) if (hijo) nodo.append(hijo);
  return nodo;
}

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

/** ¿Existe la imagen? (para usar el arte definitivo si está y el provisional si no). */
export function existeImagen(url) {
  return new Promise((resolver) => {
    const imagen = new Image();
    imagen.onload = () => resolver(true);
    imagen.onerror = () => resolver(false);
    imagen.src = url;
  });
}

export function avisar(texto, tipo = "info", ms = 6000) {
  const caja = el("div", { class: "aviso-flotante", dataset: { tipo }, role: "status" }, texto);
  document.getElementById("avisos").append(caja);
  setTimeout(() => caja.remove(), ms);
}
