// Oficina de agentes: conecta con el backend por SSE y dibuja el estado que llega.
// Principio: nada sin rastro. Todo lo que se pinta sale de /api/estado (derivado de eventos.jsonl
// y de los checkpoints); el navegador no inventa estados ni cifras.

import { el, api, avisar, euros, coste, numero, hora, hace, duracion, ESTADOS } from "./util.js";
import { detectarArte, montarEscena, pintarPersonaje } from "./escena.js";

const marco = document.getElementById("marco");
const escena = document.getElementById("escena");
const capaFija = document.getElementById("capa-fija");
const ficha = document.getElementById("ficha");
const conexion = document.getElementById("conexion");
const campoAprobador = document.getElementById("aprobador");

let config;
let arte;
let refs;
let estado = null;
let fichaAbierta = null; // id del agente cuya ficha está abierta
const tarjetas = new Map(); // checkpoint_id -> nodo (se conservan para no borrar lo que se está escribiendo)
const RESULTADOS = { creado: "Creado", rechazado: "Rechazado", denegado: "Denegado", error: "Error" };

// --- arranque ---------------------------------------------------------------------------------

async function arrancar() {
  campoAprobador.value = leerPreferencia("aprobador", "Director");
  campoAprobador.addEventListener("change", () => guardarPreferencia("aprobador", campoAprobador.value.trim() || "Director"));

  [config, arte] = await Promise.all([fetch("oficina.json").then((r) => r.json()), detectarArte()]);
  refs = montarEscena(escena, config, arte, { abrirFicha, asignarTarea: abrirDialogoTarea });
  ajustarEscala();
  window.addEventListener("resize", ajustarEscala);
  prepararDialogoTarea();
  await pedirEstado();
  conectar();
  setInterval(refrescarTiempos, 1000);
  // El backend reenvía el estado cada ~3 s; si en 8 s no ha llegado nada, se pide por HTTP.
  setInterval(() => Date.now() - ultimoEstado > 8000 && pedirEstado(), 4000);
  // Enlace directo a la ficha de un agente: …/#ficha=pedidos
  const pedida = new URLSearchParams(location.hash.slice(1)).get("ficha");
  if (pedida && refs.mesas.has(pedida)) abrirFicha(pedida);
}

function ajustarEscala() {
  const escala = Math.min(marco.clientWidth, 1920) / config.escena.ancho;
  document.documentElement.style.setProperty("--escala", escala);
  if (estado) pintarTarjetas(estado);
}

const escalaActual = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--escala")) || 1;

// --- conexión SSE (EventSource reconecta solo) --------------------------------------------------

let ultimoEstado = 0;

/** Foto completa por HTTP: al arrancar, al (re)conectar y si el SSE lleva un rato callado. */
async function pedirEstado() {
  try {
    pintar(await api("/api/estado"));
  } catch {
    /* el SSE o el siguiente intento lo resolverán */
  }
}

function conectar() {
  const fuente = new EventSource("/api/eventos");
  fuente.addEventListener("open", () => {
    marcarConexion("conectado", "En directo");
    pedirEstado();
  });
  fuente.addEventListener("estado", (e) => pintar(JSON.parse(e.data)));
  fuente.addEventListener("evento", (e) => {
    const evento = JSON.parse(e.data);
    if (fichaAbierta && evento.agente === fichaAbierta) refrescarFichaPronto();
  });
  fuente.addEventListener("error", () => {
    marcarConexion(fuente.readyState === EventSource.CLOSED ? "caido" : "conectando", "Reconectando…");
    if (fuente.readyState === EventSource.CLOSED) setTimeout(conectar, 3000);
  });
}

function marcarConexion(situacion, texto) {
  conexion.dataset.estado = situacion;
  conexion.textContent = texto;
}

// --- pintar el estado ---------------------------------------------------------------------------

function pintar(nuevo) {
  if (estado && nuevo.ahora < estado.ahora) return; // una foto más antigua que la que ya se ve
  estado = nuevo;
  ultimoEstado = Date.now();
  const modo = document.getElementById("modo-erp");
  modo.textContent = `ERP: ${nuevo.modo_erp === "api" ? "sandbox real (api)" : "simulado (demo)"}`;
  modo.dataset.modo = nuevo.modo_erp;
  document.getElementById("modelo").textContent = `Modelo: ${nuevo.modelo}`;

  for (const agente of nuevo.agentes) {
    const r = refs.mesas.get(agente.id);
    if (!r) continue;
    pintarPersonaje(r.personaje, agente.estado, arte);
    r.personaje.title = `${agente.nombre}: ${ESTADOS[agente.estado]}`;
    r.rotulo.replaceChildren(agente.nombre, el("small", {}, agente.rol));
    r.chapa.dataset.estado = agente.estado;
    r.chapa.dataset.desde = agente.desde || "";
    r.chapa.replaceChildren(textoChapa(agente), el("span", { class: "desde" }, textoDesde(agente.desde)));
    r.bocadillo.dataset.estado = agente.estado;
    r.bocadillo.textContent = agente.bocadillo || "";
    r.contador.hidden = !agente.aprobaciones_pendientes;
    r.contador.textContent = agente.aprobaciones_pendientes || "";
  }

  for (const [clave, nodo] of Object.entries(refs.cifras)) {
    const valor = nuevo.tablero[clave];
    const texto = clave === "coste_hoy_eur" ? coste(valor) : numero(valor);
    if (nodo.textContent !== texto) {
      nodo.textContent = texto;
      nodo.classList.remove("cambio");
      void nodo.offsetWidth; // reinicia la animación
      nodo.classList.add("cambio");
    }
    nodo.classList.toggle("ambar", clave === "aprobaciones_pendientes" && valor > 0);
  }

  pintarTarjetas(nuevo);
  pintarTareas(nuevo.tareas);
  if (fichaAbierta) pintarCabeceraFicha();
}

/** Recién terminada: «Terminado · Creado» (no «Trabajando») durante los 10 s en que se ve el resultado. */
function textoChapa(agente) {
  const reciente = agente.resultado_reciente;
  if (reciente) return `Terminado · ${RESULTADOS[reciente.resultado] || reciente.resultado}`;
  return ESTADOS[agente.estado] || agente.estado;
}

function textoDesde(ts) {
  return ts ? `desde ${hora(ts)} · ${hace(ts)}` : "";
}

function refrescarTiempos() {
  for (const r of refs?.mesas.values() || []) {
    const desde = r.chapa.querySelector(".desde");
    if (desde) desde.textContent = textoDesde(r.chapa.dataset.desde);
  }
}

// --- tarjetas de aprobación (ancladas a la mesa del agente que espera) -----------------------------

function pintarTarjetas(foto) {
  const vigentes = new Set(foto.aprobaciones.map((a) => a.checkpoint_id));
  for (const [id, nodo] of tarjetas) {
    if (!vigentes.has(id)) {
      nodo.remove();
      tarjetas.delete(id);
    }
  }
  const escala = escalaActual();
  const porAgente = new Map();
  for (const aprobacion of foto.aprobaciones) {
    const r = refs.mesas.get(aprobacion.agente);
    if (!r) continue;
    const indice = porAgente.get(aprobacion.agente) || 0;
    porAgente.set(aprobacion.agente, indice + 1);
    let tarjeta = tarjetas.get(aprobacion.checkpoint_id);
    if (!tarjeta) {
      tarjeta = crearTarjeta(aprobacion);
      tarjetas.set(aprobacion.checkpoint_id, tarjeta);
      capaFija.append(tarjeta);
    }
    // A la derecha de la mesa si está en la mitad izquierda de la escena; si no, a la izquierda.
    // Separada lo bastante para no tapar nunca la chapa de estado ni el rótulo del agente.
    const derecha = r.mesa.x < config.escena.ancho / 2;
    tarjeta.classList.toggle("a-la-derecha", derecha);
    tarjeta.classList.toggle("a-la-izquierda", !derecha);
    const x = (r.mesa.x + (derecha ? 240 : -240)) * escala;
    tarjeta.style.left = `${derecha ? x : x - 330}px`;
    tarjeta.style.top = `${Math.max(4, (r.mesa.y - 190) * escala + indice * 36)}px`;
  }
}

function crearTarjeta(a) {
  const comentario = el("input", { type: "text", maxlength: "500", placeholder: "Comentario (opcional)", "aria-label": "Comentario" });
  const situacion = el("p", { class: "situacion", role: "status" });
  const detalle = el("pre", { class: "detalle", hidden: true }, a.resumen || "");
  const responder = async (decision) => {
    botones.forEach((b) => (b.disabled = true));
    situacion.textContent = decision === "si" ? "Aprobando… el agente reanuda la tarea." : "Denegando…";
    try {
      await api(`/api/aprobaciones/${encodeURIComponent(a.checkpoint_id)}`, {
        method: "POST",
        cuerpo: { decision, aprobador: campoAprobador.value.trim() || "Director", comentario: comentario.value.trim() },
      });
      avisar(decision === "si" ? `Aprobado: ${a.cliente} · ${euros(a.importe)}` : `Denegado: ${a.cliente}`, "ok");
    } catch (error) {
      situacion.textContent = error.message;
      botones.forEach((b) => (b.disabled = error.status === 409));
      avisar(`No se pudo registrar la decisión: ${error.message}`, "error");
    }
  };
  const botones = [
    el("button", { class: "aprobar", type: "button", onclick: () => responder("si") }, "Aprobar"),
    el("button", { class: "denegar", type: "button", onclick: () => responder("no") }, "Denegar"),
    el("button", { class: "ver", type: "button", onclick: () => (detalle.hidden = !detalle.hidden) }, "Ver detalle"),
  ];
  // Una aprobación pedida con otro ERP (p. ej. con el simulado) no se resuelve contra este.
  if (a.modo_erp && estado && a.modo_erp !== estado.modo_erp) {
    botones[0].disabled = botones[1].disabled = true;
    situacion.textContent = `Se pidió con el ERP ${a.modo_erp === "api" ? "real (api)" : "simulado (demo)"}: arranca la oficina en ese modo para resolverla.`;
  }
  return el("article", { class: "tarjeta", "aria-label": `Aprobación pendiente: ${a.cliente}` },
    el("h3", {}, "APROBACIÓN NECESARIA"),
    el("div", {}, el("strong", {}, a.cliente), a.referencia ? ` · ref. ${a.referencia}` : ""),
    el("div", { class: "importe" }, euros(a.importe)),
    el("ul", {}, a.lineas.map((l) => el("li", {}, `${numero(l.cantidad)} × ${l.articulo} ${l.descripcion} — ${euros(l.importe)}`))),
    el("p", { class: "motivo" }, a.motivo),
    comentario,
    el("div", { class: "botones" }, botones),
    situacion,
    detalle,
  );
}

// --- tareas de hoy --------------------------------------------------------------------------------

function pintarTareas(tareas) {
  const cuerpo = document.getElementById("tareas");
  if (!tareas.length) {
    cuerpo.replaceChildren(el("tr", {}, el("td", { colspan: "7", class: "vacio" }, "Sin tareas hoy.")));
    return;
  }
  cuerpo.replaceChildren(...tareas.map((t) => {
    const situacion = t.estado === "terminada" ? t.resultado : t.estado;
    const textos = { ...RESULTADOS, esperando_aprobacion: "Esperando aprobación", en_curso: "En curso" };
    return el("tr", {},
      el("td", {}, hora(t.inicio)),
      el("td", {}, t.origen || t.id),
      el("td", {}, el("span", { class: "resultado", dataset: { r: situacion } }, textos[situacion] || situacion)),
      el("td", {}, t.pedido || "—"),
      el("td", { class: "num" }, coste(t.coste_eur)),
      el("td", { class: "num" }, duracion(t.duracion_s)),
      el("td", {}, t.bocadillo || ""),
    );
  }));
}

// --- ficha del agente -------------------------------------------------------------------------------

let temporizadorFicha = null;

function refrescarFichaPronto() {
  clearTimeout(temporizadorFicha);
  temporizadorFicha = setTimeout(() => fichaAbierta && cargarFicha(fichaAbierta), 300);
}

async function abrirFicha(agente) {
  fichaAbierta = agente;
  ficha.hidden = false;
  ficha.replaceChildren(el("p", { class: "vacio" }, "Cargando…"));
  await cargarFicha(agente);
}

function cerrarFicha() {
  fichaAbierta = null;
  ficha.hidden = true;
}

document.addEventListener("keydown", (e) => e.key === "Escape" && fichaAbierta && cerrarFicha());

async function cargarFicha(agente) {
  let datos;
  try {
    datos = await api(`/api/agentes/${encodeURIComponent(agente)}/cronologia`);
  } catch (error) {
    ficha.replaceChildren(el("p", {}, `No se pudo cargar la ficha: ${error.message}`));
    return;
  }
  if (fichaAbierta !== agente) return;
  const herramientas = Object.entries(datos.herramientas);
  ficha.replaceChildren(
    el("button", { class: "cerrar", type: "button", onclick: cerrarFicha, "aria-label": "Cerrar la ficha" }, "×"),
    el("div", { id: "ficha-cabecera" }),
    el("h3", {}, "Hoy"),
    el("div", { class: "cifras" },
      el("div", { class: "cifra" }, "Coste", el("b", {}, coste(datos.coste_eur))),
      el("div", { class: "cifra" }, "Llamadas al modelo", el("b", {}, numero(datos.llamadas_modelo))),
    ),
    el("h3", {}, "Pedidos creados"),
    datos.pedidos.length
      ? el("ul", {}, datos.pedidos.map((p) => el("li", {}, el("span", { class: "hora" }, hora(p.ts)), `Pedido ${p.pedido} · ${euros(p.importe)} · cliente ${p.cliente} · ${p.modo === "api" ? "sandbox real" : "simulado"}`)))
      : el("p", { class: "vacio" }, "Ninguno hoy."),
    el("h3", {}, "Herramientas usadas"),
    herramientas.length
      ? el("ul", {}, herramientas.map(([nombre, veces]) => el("li", {}, `${nombre} · ${veces} ${veces === 1 ? "vez" : "veces"}`)))
      : el("p", { class: "vacio" }, "Ninguna hoy."),
    el("h3", {}, "Cronología"),
    datos.eventos.length
      ? el("ul", {}, [...datos.eventos].reverse().map((e) => el("li", { dataset: { tipo: e.tipo } }, el("span", { class: "hora" }, hora(e.ts)), describirEvento(e))))
      : el("p", { class: "vacio" }, "Sin eventos hoy."),
  );
  pintarCabeceraFicha();
}

function describirEvento(e) {
  if (e.tipo === "modelo_llamada") {
    const d = e.datos;
    return `Modelo ${d.modelo}: ${numero(d.tokens_entrada)} tokens de entrada, ${numero(d.tokens_salida)} de salida · ${coste(d.coste_eur)}`;
  }
  if (e.tipo === "agente_detenido") return "Detenido por el director";
  if (e.tipo === "agente_activado") return "Activado por el director";
  return e.descripcion || e.tipo;
}

function pintarCabeceraFicha() {
  const cabecera = document.getElementById("ficha-cabecera");
  const agente = estado?.agentes.find((a) => a.id === fichaAbierta);
  if (!cabecera || !agente) return;
  const detenido = agente.estado === "detenido";
  cabecera.replaceChildren(
    el("h2", { class: "pixel" }, agente.nombre),
    el("p", { class: "rol" }, `Rol: ${agente.rol}`),
    el("span", { class: "chapa", dataset: { estado: agente.estado } }, textoChapa(agente), el("span", { class: "desde" }, textoDesde(agente.desde))),
    agente.bocadillo ? el("p", {}, agente.bocadillo) : null,
    el("div", { class: "acciones" },
      el("button", {
        class: "boton-pixel", type: "button",
        title: detenido ? "Vuelve a aceptar tareas" : "No acepta tareas nuevas (las que están en marcha terminan)",
        onclick: () => cambiarDetencion(agente.id, !detenido),
      }, detenido ? "Activar" : "Detener"),
    ),
  );
}

async function cambiarDetencion(agente, detener) {
  try {
    await api(`/api/agentes/${encodeURIComponent(agente)}/${detener ? "detener" : "activar"}`, { method: "POST" });
    avisar(detener ? "Agente detenido: no recibirá tareas nuevas. Las que estén en marcha terminan." : "Agente activado.", "ok");
  } catch (error) {
    avisar(error.message, "error");
  }
}

// --- asignar tarea --------------------------------------------------------------------------------

const dialogo = document.getElementById("dialogo-tarea");
let correos = [];

function prepararDialogoTarea() {
  const ejemplo = document.getElementById("tarea-ejemplo");
  const texto = document.getElementById("tarea-correo");
  ejemplo.addEventListener("change", () => {
    const elegido = correos.find((c) => c.nombre === ejemplo.value);
    texto.value = elegido ? elegido.texto : "";
  });
  document.getElementById("tarea-cancelar").addEventListener("click", () => dialogo.close());
  document.getElementById("form-tarea").addEventListener("submit", async (e) => {
    e.preventDefault();
    const aviso = document.getElementById("tarea-aviso");
    const boton = document.getElementById("tarea-asignar");
    boton.disabled = true;
    aviso.textContent = "";
    try {
      const { tarea } = await api("/api/tareas", {
        method: "POST",
        cuerpo: { agente: document.getElementById("tarea-agente").value, correo: texto.value, origen: ejemplo.value || null },
      });
      dialogo.close();
      avisar(`Tarea asignada (${tarea}). El agente empieza en unos segundos.`, "ok");
    } catch (error) {
      aviso.textContent = error.message;
    } finally {
      boton.disabled = false;
    }
  });
}

async function abrirDialogoTarea() {
  const selector = document.getElementById("tarea-agente");
  const reales = (estado?.agentes || []).map((a) => el("option", { value: a.id, disabled: a.estado === "detenido" }, `${a.nombre} (${a.rol})${a.estado === "detenido" ? " — detenido" : ""}`));
  const vacantes = config.mesas.filter((m) => !m.agente).map((m) => el("option", { disabled: true }, `Vacante: ${m.vacante || "próximo agente"}`));
  selector.replaceChildren(...reales, ...vacantes);
  try {
    correos = await api("/api/correos");
  } catch {
    correos = [];
  }
  const ejemplo = document.getElementById("tarea-ejemplo");
  ejemplo.replaceChildren(el("option", { value: "" }, "— pegar uno propio —"), ...correos.map((c) => el("option", { value: c.nombre }, c.nombre)));
  document.getElementById("tarea-correo").value = "";
  document.getElementById("tarea-aviso").textContent = "";
  dialogo.showModal();
}

// --- preferencias del navegador (solo comodidad: el nombre del director) ----------------------------

function leerPreferencia(clave, defecto) {
  try {
    return localStorage.getItem(`oficina.${clave}`) || defecto;
  } catch {
    return defecto;
  }
}

function guardarPreferencia(clave, valor) {
  try {
    localStorage.setItem(`oficina.${clave}`, valor);
  } catch {
    /* sin almacenamiento: se usa el valor por defecto */
  }
}

arrancar().catch((error) => {
  marcarConexion("caido", "Error al arrancar");
  avisar(`No se pudo arrancar la oficina: ${error.message}`, "error", 20000);
});
