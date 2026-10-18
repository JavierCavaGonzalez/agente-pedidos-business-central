// Oficina de agentes: torre de control. Conecta con el backend por SSE y dibuja el estado que llega.
// Principio: nada sin rastro. Todo lo que se pinta sale de /api/estado (derivado de eventos.jsonl y de los
// checkpoints); el navegador no inventa estados ni cifras. Todo texto de los datos entra con textContent.

import { el, api, avisar, euros, coste, numero, hora, hace, duracion, icono, ESTADOS } from "./util.js";

const $ = (id) => document.getElementById(id);
const RESULTADOS = { creado: "Creado", rechazado: "Rechazado", denegado: "Denegado", error: "Error", respondido: "Respondida" };
const ESTADO_TAREA = { en_curso: "En curso", esperando_aprobacion: "Esperando aprobación", error: "Error", terminada: "Terminada" };

let config;
let escena = null;
let estado = null;
let seleccion = { tipo: "agente", id: "pedidos" };
let tareaFijada = ""; // "" = la más urgente, automáticamente
let filtroFeed = "todo";
let busqueda = "";
let pedidosVistos = null; // pedidos ya vistos (para animar solo los nuevos)
let feedVisto = null;
let firmaDetalle = "";
let ultimoEstado = 0;
const tarjetas = new Map(); // checkpoint_id -> tarjeta de aprobación (se conserva para no perder lo escrito)

// --- arranque ---------------------------------------------------------------------------------------

async function arrancar() {
  config = await fetch("oficina.json").then((r) => r.json());
  try {
    const { montarEscena } = await import("./escena3d.js");
    escena = montarEscena($("escena-lienzo"), config, { alElegir: elegir });
    $("escena-aviso").textContent = "";

  } catch (error) {
    // Sin WebGL los paneles siguen funcionando: la escena es la vista, no el control
    $("escena-aviso").textContent = `No se puede dibujar la planta en 3D en este navegador (${error.message}). Los paneles funcionan igual.`;
  }
  prepararControles();
  await pedirEstado();
  conectar();
  setInterval(() => estado && (pintarEscena(estado), pintarDetalle(estado)), 5000);
  setInterval(() => document.querySelectorAll(".reloj-paso").forEach((n) => (n.textContent = duracion((Date.now() - new Date(n.dataset.inicio)) / 1000))), 1000);
  setInterval(() => Date.now() - ultimoEstado > 8000 && pedirEstado(), 4000);
  const pedida = new URLSearchParams(location.hash.slice(1));
  if (pedida.get("ficha")) elegir({ tipo: "agente", id: pedida.get("ficha") });
  if (pedida.has("inmersivo")) alternarInmersivo(true);
}

async function pedirEstado() {
  try {
    pintar(await api("/api/estado"));
  } catch (error) {
    console.error("No se pudo pintar el estado:", error); // el SSE o el siguiente intento lo resolverán
  }
}

function conectar() {
  const fuente = new EventSource("/api/eventos");
  fuente.addEventListener("open", () => {
    marcarDirecto("conectado", "En directo");
    pedirEstado();
  });
  fuente.addEventListener("estado", (e) => pintar(JSON.parse(e.data)));
  fuente.addEventListener("error", () => {
    marcarDirecto(fuente.readyState === EventSource.CLOSED ? "caido" : "conectando", "Sin conexión con la oficina, reintentando");
    if (fuente.readyState === EventSource.CLOSED) setTimeout(conectar, 3000);
  });
}

function marcarDirecto(situacion, texto) {
  $("directo").dataset.estado = situacion;
  $("directo").textContent = texto;
}

// --- pintar ----------------------------------------------------------------------------------------

function pintar(foto) {
  if (estado && foto.ahora < estado.ahora) return; // una foto más antigua que la que ya se ve
  estado = foto;
  ultimoEstado = Date.now();
  pintarBarra(foto);
  pintarKpis(foto);
  pintarEscena(foto);
  avisarPedidosNuevos(foto);
  pintarFeed(foto);
  pintarSeguimiento(foto);
  pintarPedidos(foto);
  pintarDetalle(foto);
}

const nombreAgente = (id) => estado?.agentes.find((a) => a.id === id)?.nombre || id;
const aprobador = () => leerPreferencia("aprobador", "Director");
const coincide = (...textos) => !busqueda || textos.some((t) => String(t ?? "").toLowerCase().includes(busqueda));
const horaCorta = (ts) => (ts ? new Date(ts).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) : "—");
const sinExtension = (nombre) => String(nombre || "").replace(/\.txt$/, "");
const ESTADO_CORTO = { en_curso: "en curso", esperando_aprobacion: "esperando", error: "error", creado: "creado", rechazado: "rechazado", denegado: "denegado", respondido: "respondida" };
const estadoCorto = (t) => ESTADO_CORTO[t.estado === "terminada" ? t.resultado : t.estado] || t.resultado || t.estado;

/** Lo que dice la segunda línea de la etiqueta del agente, sin repetir el dato de la primera (y sin recortar). */
function subDeAgente(agente, foto) {
  if (agente.resultado_reciente || !["trabajando", "esperando_aprobacion", "error"].includes(agente.estado)) return null;
  if (agente.estado === "esperando_aprobacion") {
    const suya = foto.aprobaciones.find((a) => a.agente === agente.id);
    return suya ? `Pedido de ${suya.cliente.replace(/^\S+\s/, "")}` : null;
  }
  return agente.bocadillo;
}

function pintarBarra(foto) {
  const erp = foto.erp || {};
  const indicador = $("conexion-erp");
  indicador.dataset.modo = foto.modo_erp;
  indicador.textContent = foto.modo_erp === "api" ? `Business Central · en vivo · ${erp.entorno || "sandbox"}` : "Simulación";
  indicador.title = foto.modo_erp === "api" ? `Empresa: ${erp.empresa || "—"}` : "ERP simulado: ningún pedido llega a Business Central";
  $("modelo").textContent = `Modelo: ${foto.modelo}`;
  const boton = $("boton-bc");
  if (erp.enlace) {
    boton.href = erp.enlace;
    boton.removeAttribute("aria-disabled");
    boton.title = `Abrir Business Central (${erp.entorno}${erp.empresa ? ` · ${erp.empresa}` : ""})`;
  } else {
    boton.removeAttribute("href");
    boton.setAttribute("aria-disabled", "true");
    boton.title = "Simulación: no hay un Business Central real que abrir";
  }
}

function pintarKpis(foto) {
  const t = foto.tablero;
  const pendiente = foto.aprobaciones.reduce((s, a) => s + (a.importe || 0), 0);
  const presupuesto = foto.presupuesto_dia_eur || 0;
  const vacantes = config.mesas.filter((m) => !m.agente).length;
  const erp = foto.erp || {};
  const kpis = [
    ["Agentes activos", numero(t.agentes_activos), `de ${foto.agentes.length} · ${vacantes} mesas vacantes`, "var(--e-trabajando)"],
    ["Tareas hoy", numero(foto.tareas.filter((x) => x.clase !== "pregunta").length), `${t.tareas_en_curso} en curso`, "var(--azul-500)"],
    ["Preguntas hoy", numero(foto.preguntas?.hoy || 0), foto.preguntas?.hoy ? `${coste(foto.preguntas.coste_eur)} en respuestas` : "ninguna", "var(--azul-300)"],
    ["Aprobaciones pendientes", numero(t.aprobaciones_pendientes), t.aprobaciones_pendientes ? `${euros(pendiente)} por aprobar` : "ninguna", "var(--e-esperando)", t.aprobaciones_pendientes > 0],
    ["Escrituras en el ERP hoy", numero(t.escrituras_erp_hoy), `${foto.modo_erp === "api" ? erp.entorno || "sandbox" : "simulación"} · ${erp.bloqueadas_hoy || 0} bloqueadas`, "var(--azul-700)"],
    ["Coste hoy (€)", coste(t.coste_hoy_eur), presupuesto ? `${numero(Math.round((t.coste_hoy_eur / presupuesto) * 1000) / 10)} % de ${euros(presupuesto)}` : "", "var(--oro-marca)"],
    ["Llamadas al modelo hoy", numero(t.llamadas_modelo_hoy), foto.modelo, "var(--marino-300)"],
  ];
  const caja = $("kpis");
  if (caja.children.length !== kpis.length) {
    caja.replaceChildren(...kpis.map(() => el("div", { class: "kpi" }, el("div", { class: "kpi-etiqueta" }), el("div", { class: "kpi-valor" }), el("div", { class: "kpi-nota" }))));
  }
  kpis.forEach(([etiqueta, valor, nota, color, alerta], i) => {
    const [cEtiqueta, cValor, cNota] = caja.children[i].children;
    if (!cEtiqueta.childElementCount) cEtiqueta.replaceChildren(el("span", { class: "punto", style: `background:${color}` }), etiqueta);
    if (cValor.textContent !== valor) {
      cValor.textContent = valor;
      cValor.classList.remove("cambio");
      void cValor.offsetWidth; // reinicia la animación
      cValor.classList.add("cambio");
    }
    cNota.textContent = nota;
    caja.children[i].dataset.alerta = String(Boolean(alerta));
  });
}

// --- escena -----------------------------------------------------------------------------------------

function minutos(ts) {
  if (!ts) return "";
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
  return s < 60 ? "menos de 1 min" : `${Math.floor(s / 60)} min`;
}

function datoDeAgente(agente, foto) {
  const reciente = agente.resultado_reciente;
  if (reciente) return `Terminado · ${RESULTADOS[reciente.resultado] || reciente.resultado}${reciente.pedido ? ` ${reciente.pedido}` : ""}`;
  if (agente.estado === "trabajando") return `Trabajando · ${minutos(agente.desde)}`;
  if (agente.estado === "esperando_aprobacion") {
    const suya = foto.aprobaciones.find((a) => a.agente === agente.id);
    return `Esperando aprobación${suya ? ` · ${euros(suya.importe)}` : ""}`;
  }
  if (agente.estado === "error") return `Error · ${hace(agente.desde)}`;
  if (agente.estado === "detenido") return "Detenido por el director";
  return `Libre · ${agente.tareas_hoy} ${agente.tareas_hoy === 1 ? "tarea" : "tareas"} hoy`;
}

function pintarEscena(foto) {
  if (!escena) return;
  const erp = foto.erp || {};
  const n = foto.aprobaciones.length;
  escena.actualizar({
    agentes: foto.agentes.map((a) => ({
      id: a.id,
      estado: a.estado,
      nombre: a.nombre,
      dato: datoDeAgente(a, foto),
      sub: subDeAgente(a, foto),
    })),
    vacantes: config.mesas.filter((m) => !m.agente).map((m) => ({ id: m.id, area: m.vacante })),
    director: { nombre: aprobador(), dato: n ? `${n} ${n === 1 ? "aprobación pendiente" : "aprobaciones pendientes"}` : "Despacho del director", pendientes: n },
    bc: {
      modo: foto.modo_erp,
      dato: `${foto.modo_erp === "api" ? `${erp.entorno || "sandbox"} · ${erp.empresa || ""}` : "Simulación"} · ${numero(erp.escrituras_hoy || 0)} ${erp.escrituras_hoy === 1 ? "escritura" : "escrituras"} hoy`,
    },
  });
  escena.elegir(seleccion);
}

function avisarPedidosNuevos(foto) {
  const claves = new Set(foto.pedidos.map((p) => `${p.modo}:${p.pedido}`));
  if (pedidosVistos) {
    for (const p of foto.pedidos) {
      if (pedidosVistos.has(`${p.modo}:${p.pedido}`)) continue;
      escena?.enviarPedido(p.agente);
      avisar(`Pedido ${p.pedido} creado en ${p.modo === "api" ? "Business Central" : "la simulación"} · ${euros(p.importe)}`, "ok");
    }
  }
  pedidosVistos = claves;
}

function elegir(nueva) {
  seleccion = nueva;
  escena?.elegir(seleccion);
  firmaDetalle = "";
  if (estado) pintarDetalle(estado);
}

// --- feed de actividad ------------------------------------------------------------------------------

const claveFeed = (f) => `${f.ts}|${f.tipo}|${f.tarea}`;

function pintarFeed(foto, forzar = false) {
  const lista = $("feed-lista");
  const auto = $("feed-auto").checked;
  const textoAuto = $("feed-auto").nextElementSibling;
  if (!auto && !forzar && lista.childElementCount) {
    // Sin «Auto», la lista no se mueve mientras se lee: solo se cuenta lo nuevo
    const nuevos = feedVisto ? foto.feed.filter((f) => !feedVisto.has(claveFeed(f))).length : 0;
    textoAuto.textContent = nuevos ? `Auto (${nuevos} nuevos)` : "Auto";
    return;
  }
  textoAuto.textContent = "Auto";
  const seguidaId = seguida(foto)?.id;
  const filas = foto.feed.filter((f) => (filtroFeed === "todo" || f.categoria === filtroFeed) && coincide(f.texto, nombreAgente(f.agente), f.tarea));
  const firma = `${filtroFeed}|${busqueda}|${filas.length}|${filas[0] ? claveFeed(filas[0]) : ""}|${seguidaId}`;
  if (lista.dataset.firma === firma && !forzar) return;
  lista.dataset.firma = firma;
  lista.replaceChildren(
    ...(filas.length
      ? filas.map((f) => {
          const nuevo = feedVisto && !feedVisto.has(claveFeed(f));
          return el("li", {
            class: `feed-item${nuevo ? " nuevo" : ""}`,
            dataset: { categoria: f.categoria, error: String(f.error), ...(f.tarea ? { tarea: f.tarea } : {}), elegido: String(Boolean(f.tarea) && f.tarea === seguidaId) },
            onclick: f.tarea ? () => seguirTarea(f.tarea) : null,
            title: f.tarea ? "Ver esta tarea en el seguimiento" : null,
          },
            el("span", { class: "feed-icono" }, icono(f.error ? "error" : f.categoria)),
            el("span", { class: "feed-meta" }, el("span", {}, hora(f.ts)), el("b", {}, nombreAgente(f.agente)), f.coste_eur != null ? el("span", { class: "pastilla feed-coste" }, coste(f.coste_eur)) : null),
            el("span", { class: "feed-texto" }, f.texto),
          );
        })
      : [el("li", { class: "vacio" }, busqueda || filtroFeed !== "todo" ? "Nada con este filtro." : "Sin actividad hoy. Asigna una tarea para empezar.")]),
  );
  if (auto) lista.scrollTop = 0;
  feedVisto = new Set(foto.feed.map(claveFeed));
}

// --- seguimiento de tarea ---------------------------------------------------------------------------

/** La tarea que se sigue: la elegida por la persona o, si no, la más urgente (esperando, en curso, la última). */
function seguida(foto) {
  const tareas = foto.tareas;
  if (tareaFijada) {
    const fijada = tareas.find((t) => t.id === tareaFijada);
    if (fijada) return fijada;
  }
  return tareas.find((t) => t.estado === "esperando_aprobacion") || tareas.find((t) => t.estado === "en_curso") || tareas[0] || null;
}

function seguirTarea(id) {
  tareaFijada = id;
  if (!estado) return;
  pintarSeguimiento(estado);
  pintarFeed(estado, true);
  pintarPedidos(estado);
}

function pintarSeguimiento(foto) {
  const selector = $("seguimiento-tarea");
  const opciones = [
    ["", "La más urgente"],
    ...foto.tareas
      .filter((t) => coincide(t.origen, t.resumen, t.pedido, t.id, t.seguimiento?.cliente))
      .map((t) => [t.id, `${horaCorta(t.inicio)} · ${sinExtension(t.origen) || t.id} · ${estadoCorto(t)}`]),
  ];
  const firmaOpciones = JSON.stringify(opciones);
  if (selector.dataset.firma !== firmaOpciones) {
    selector.dataset.firma = firmaOpciones;
    selector.replaceChildren(...opciones.map(([valor, texto]) => el("option", { value: valor }, texto)));
  }
  selector.value = foto.tareas.some((t) => t.id === tareaFijada) ? tareaFijada : "";

  const cuerpo = $("seguimiento-cuerpo");
  const tarea = seguida(foto);
  if (!tarea) {
    cuerpo.replaceChildren(el("p", { class: "vacio" }, "Sin tareas hoy. Pulsa «Asignar tarea» y elige un correo: aquí verás cada paso hasta el pedido en Business Central."));
    return;
  }
  if (!tarea.seguimiento) {
    // Una pregunta al agente: no es un pedido, no tiene pasos
    const respuesta = foto.feed.find((f) => f.tarea === tarea.id && f.tipo === "respuesta_agente");
    cuerpo.replaceChildren(el("div", { class: "seguimiento-detalle sin-tarjeta" }, el("div", { class: "seguimiento-resumen" },
      el("div", { class: "cabeza" }, el("strong", {}, "Pregunta al agente"), el("span", {}, tarea.estado === "terminada" ? `Respondida en ${duracion(tarea.duracion_s)}` : "Pensando la respuesta")),
      el("p", {}, tarea.resumen || ""),
      respuesta ? el("p", { class: "detalle-bocadillo" }, respuesta.texto) : null,
      el("div", { class: "pie" }, el("span", {}, `Coste ${coste(tarea.coste_eur)}`), el("span", {}, tarea.id)),
    )));
    return;
  }
  const s = tarea.seguimiento;
  const pasos = el("ol", { class: "pasos", "aria-label": "Pasos de la tarea" }, s.pasos.map((p) =>
    el("li", { class: "paso", dataset: { estado: p.estado, clave: p.clave }, title: p.nota || "" },
      el("span", { class: "marca-paso" }, p.estado === "hecho" ? icono("hecho") : p.estado === "fallido" ? icono("fallido") : null),
      el("b", {}, p.etiqueta),
      el("span", p.estado === "actual" ? { class: "reloj-paso", dataset: { inicio: p.inicio } } : {}, p.estado === "omitido" ? "—" : p.estado === "actual" ? duracion((Date.now() - new Date(p.inicio)) / 1000) : p.duracion_s != null ? duracion(p.duracion_s) : "pendiente"),
      p.nota ? el("span", { class: "nota-paso" }, p.nota) : null,
    )));
  const aprobacion = foto.aprobaciones.find((a) => a.tarea === tarea.id);
  const lineas = s.lineas || [];
  const resumen = el("div", { class: "seguimiento-resumen" },
    el("div", { class: "cabeza" }, el("strong", {}, s.cliente || tarea.origen || "Pedido"), el("span", {}, s.total != null ? euros(s.total) : "")),
    lineas.length
      ? el("table", { class: "tabla tabla-lineas" },
          el("thead", {}, el("tr", {}, el("th", {}, "Cantidad y artículo"), el("th", { class: "num" }, "Importe"))),
          el("tbody", {}, lineas.map((l) => el("tr", {},
            el("td", { class: "cliente" }, [l.cantidad != null ? `${numero(l.cantidad)} ×` : null, l.articulo, l.descripcion].filter(Boolean).join(" ")),
            el("td", { class: "num" }, l.importe != null ? euros(l.importe) : ""),
          ))))
      : el("p", { class: "vacio" }, tarea.estado === "terminada" ? "Sin líneas validadas." : "Las líneas aparecen cuando el agente valida el pedido."),
    el("div", { class: "pie" },
      el("span", {}, `Coste ${coste(tarea.coste_eur)}`),
      el("span", {}, tarea.estado === "terminada"
        ? `${RESULTADOS[tarea.resultado] || tarea.resultado}${tarea.pedido ? ` · ${tarea.pedido}` : ""} en ${duracion(tarea.duracion_s)}`
        : tarea.origen || ""),
    ),
  );
  const detalle = el("div", { class: `seguimiento-detalle${aprobacion ? "" : " sin-tarjeta"}` }, resumen, aprobacion ? tarjetaAprobacion(aprobacion, foto) : null);
  cuerpo.replaceChildren(pasos, detalle);
  const vigentes = new Set(foto.aprobaciones.map((a) => a.checkpoint_id));
  for (const id of tarjetas.keys()) if (!vigentes.has(id)) tarjetas.delete(id);
}

function tarjetaAprobacion(a, foto) {
  const existente = tarjetas.get(a.checkpoint_id);
  if (existente) return existente;
  const campoAprobador = el("input", { type: "text", maxlength: "80", value: aprobador(), "aria-label": "Aprobador", autocomplete: "off", title: "Aprobador: queda en la auditoría tal como se escribe" });
  campoAprobador.addEventListener("change", () => guardarPreferencia("aprobador", campoAprobador.value.trim() || "Director"));
  const comentario = el("input", { type: "text", maxlength: "500", placeholder: "Comentario", "aria-label": "Comentario (opcional)", title: "Comentario opcional: queda en la auditoría" });
  const situacion = el("p", { class: "situacion", role: "status" });
  const responder = async (decision) => {
    botones.forEach((b) => (b.disabled = true));
    botones[decision === "si" ? 0 : 1].setAttribute("aria-busy", "true");
    situacion.textContent = decision === "si" ? "Aprobando: el agente reanuda la tarea." : "Denegando.";
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
    } finally {
      botones.forEach((b) => b.removeAttribute("aria-busy"));
    }
  };
  const botones = [
    el("button", { class: "boton boton--azul boton--pequeno", type: "button", onclick: () => responder("si") }, "Aprobar"),
    el("button", { class: "boton boton--peligro boton--pequeno", type: "button", onclick: () => responder("no") }, "Denegar"),
  ];
  // Una aprobación pedida con otro ERP (p. ej. con el simulado) no se resuelve contra este
  if (a.modo_erp && a.modo_erp !== foto.modo_erp) {
    botones.forEach((b) => (b.disabled = true));
    situacion.textContent = `Se pidió con el ERP ${a.modo_erp === "api" ? "real (api)" : "simulado (demo)"}: arranca la oficina en ese modo para resolverla.`;
  }
  const tarjeta = el("article", { class: "tarjeta-aprobacion", "aria-label": `Aprobación pendiente: ${a.cliente}` },
    el("div", { class: "fila" }, el("h3", {}, icono("mano"), "Aprobación necesaria"), el("div", { class: "importe" }, euros(a.importe))),
    el("div", { class: "cliente" }, a.cliente, a.referencia ? el("span", { class: "pastilla", style: "margin-left:8px" }, `ref. ${a.referencia}`) : null),
    el("p", { class: "motivo" }, a.motivo || ""),
    el("div", { class: "campos" }, campoAprobador, comentario, ...botones),
    situacion,
  );
  tarjetas.set(a.checkpoint_id, tarjeta);
  return tarjeta;
}

// --- pedidos creados hoy ----------------------------------------------------------------------------

function pintarPedidos(foto) {
  const filas = foto.pedidos.filter((p) => coincide(p.pedido, p.cliente, p.tarea));
  const total = foto.pedidos.reduce((s, p) => s + (p.importe || 0), 0);
  $("pedidos-total").textContent = foto.pedidos.length ? `${foto.pedidos.length} · ${euros(total)}` : "ninguno";
  const seguidaId = seguida(foto)?.id;
  $("pedidos-lista").replaceChildren(
    ...(filas.length
      ? filas.map((p) => el("tr", { dataset: { elegido: String(p.tarea === seguidaId) }, onclick: () => p.tarea && seguirTarea(p.tarea), style: "cursor:pointer", title: "Ver la tarea en el seguimiento" },
          el("td", {}, el("strong", {}, p.pedido)),
          el("td", { class: "cliente", title: p.cliente || "" }, p.cliente || "—"),
          el("td", { class: "num" }, euros(p.importe)),
          el("td", {}, el("span", { class: "pastilla" }, p.estado_bc)),
          el("td", { class: "col-hora" }, horaCorta(p.ts)),
          el("td", {}, p.enlace
            ? el("a", { href: p.enlace, target: "_blank", rel: "noopener", onclick: (e) => e.stopPropagation() }, "Abrir en Business Central ↗")
            : el("span", { class: "simulacion", title: "Pedido de la simulación: no existe en Business Central" }, "simulación")),
        ))
      : [el("tr", {}, el("td", { colspan: "6", class: "vacio" }, busqueda ? "Ningún pedido coincide con la búsqueda." : "Todavía no hay pedidos hoy."))]),
  );
}

// --- panel de detalle -------------------------------------------------------------------------------

function medida(etiqueta, valor, maximo, texto) {
  const proporcion = maximo > 0 ? valor / maximo : 0;
  return el("div", { class: "barra-medida", dataset: { nivel: proporcion > 1 ? "excedido" : proporcion >= 0.8 ? "alto" : "normal" } },
    el("span", {}, etiqueta), el("b", {}, texto),
    el("div", { class: "pista", role: "meter", "aria-valuemin": "0", "aria-valuemax": String(maximo), "aria-valuenow": String(valor), "aria-label": etiqueta },
      el("div", { class: "relleno", style: `width:${Math.min(100, proporcion * 100)}%` })),
  );
}

function pintarDetalle(foto) {
  const contenido = detalleDe(foto);
  const firma = JSON.stringify(contenido.firma);
  if (firma === firmaDetalle) return;
  if (firmaDetalle && document.activeElement?.matches("#detalle input")) return; // no se repinta mientras se escribe
  firmaDetalle = firma;
  $("detalle").replaceChildren(el("div", { class: "detalle-cuerpo" }, contenido.nodos()));
}

const vacio = (texto) => el("p", { class: "vacio", style: "padding:0" }, texto);

function detalleDe(foto) {
  if (seleccion.tipo === "bc") {
    const erp = foto.erp || {};
    const real = foto.modo_erp === "api";
    return {
      firma: ["bc", erp],
      nodos: () => [
        el("div", { class: "detalle-titulo" },
          el("div", {}, el("h2", {}, "Business Central"), el("p", {}, real ? "Sandbox real, siempre a través del backend" : "ERP simulado con los datos de ejemplo de CRONUS")),
          el("span", { class: "chip-estado", dataset: { estado: real ? "trabajando" : "libre" } }, el("span", { class: "punto" }), real ? "En vivo" : "Simulación")),
        el("dl", { class: "ficha-datos" },
          el("dt", {}, "Entorno"), el("dd", {}, erp.entorno || "—"),
          el("dt", {}, "Empresa"), el("dd", {}, erp.empresa || "—"),
          el("dt", {}, "Escrituras hoy"), el("dd", {}, numero(erp.escrituras_hoy || 0)),
          el("dt", {}, "Escrituras bloqueadas hoy"), el("dd", {}, numero(erp.bloqueadas_hoy || 0)),
          el("dt", {}, "Última escritura"), el("dd", {}, erp.ultima_escritura ? `${erp.ultima_escritura.pedido} · ${hora(erp.ultima_escritura.ts)}` : "—"),
        ),
        el("p", { class: "detalle-bocadillo" }, "El navegador nunca habla con Business Central: el backend usa sus credenciales, y cada escritura pasa por la política y, si hace falta, por tu aprobación."),
        erp.enlace ? el("div", { class: "detalle-acciones" }, el("a", { class: "boton boton--azul boton--pequeno", href: erp.enlace, target: "_blank", rel: "noopener" }, "Abrir Business Central ↗")) : null,
      ],
    };
  }
  if (seleccion.tipo === "director") {
    return {
      firma: ["director", foto.aprobaciones.map((a) => [a.checkpoint_id, a.importe]), aprobador()],
      nodos: () => {
        const campo = el("input", { type: "text", maxlength: "80", value: aprobador(), "aria-label": "Nombre del aprobador", class: "campo" });
        campo.addEventListener("change", () => {
          guardarPreferencia("aprobador", campo.value.trim() || "Director");
          pintarEscena(estado);
        });
        return [
          el("div", { class: "detalle-titulo" }, el("div", {}, el("h2", {}, "Despacho del director"), el("p", {}, "La persona que decide lo que supera la política"))),
          el("label", { class: "campo-etiquetado" }, el("h3", {}, "Aprobador (queda en la auditoría tal como se escribe)"), campo),
          el("div", {}, el("h3", {}, "Aprobaciones pendientes"),
            foto.aprobaciones.length
              ? el("table", { class: "tabla-mini" }, el("tbody", {}, foto.aprobaciones.map((a) => el("tr", {},
                  el("td", {}, a.cliente), el("td", { class: "num" }, euros(a.importe)),
                  el("td", { class: "num" }, el("button", { class: "boton boton--secundario boton--pequeno", type: "button", onclick: () => a.tarea && seguirTarea(a.tarea) }, "Revisar")),
                ))))
              : vacio("Ninguna. Cuando un pedido supere la política, su tarjeta aparecerá en el seguimiento de tarea.")),
        ];
      },
    };
  }
  if (seleccion.tipo === "vacante") {
    const mesa = config.mesas.find((m) => m.id === seleccion.id);
    return {
      firma: ["vacante", seleccion.id],
      nodos: () => [
        el("div", { class: "detalle-titulo" }, el("div", {}, el("h2", {}, `Vacante · ${mesa?.vacante || ""}`), el("p", {}, "Mesa preparada para un próximo agente")), el("span", { class: "chip-estado" }, el("span", { class: "punto" }), "Sin agente")),
        el("p", { class: "detalle-bocadillo" }, `Próximamente, un agente de ${String(mesa?.vacante || "").toLowerCase()}. Mientras tanto, esta mesa no recibe tareas.`),
      ],
    };
  }
  const agente = foto.agentes.find((a) => a.id === seleccion.id) || foto.agentes[0];
  const ultima = foto.tareas.find((t) => t.agente === agente.id);
  const presupuesto = foto.presupuesto_dia_eur || 0;
  return {
    firma: ["agente", agente, ultima?.id, ultima?.estado, presupuesto],
    nodos: () => {
      const detenido = agente.estado === "detenido";
      return [
        el("div", { class: "detalle-titulo" },
          el("div", {}, el("h2", {}, agente.nombre), el("p", {}, `Rol: ${agente.rol}`)),
          el("span", { class: "chip-estado", dataset: { estado: agente.estado } }, el("span", { class: "punto" }),
            agente.resultado_reciente ? `Terminado · ${RESULTADOS[agente.resultado_reciente.resultado] || ""}` : ESTADOS[agente.estado]),
        ),
        agente.bocadillo ? el("p", { class: "detalle-bocadillo" }, agente.bocadillo) : null,
        medida("Carga", agente.tareas_en_curso, agente.capacidad, `${agente.tareas_en_curso} de ${agente.capacidad} tareas`),
        medida("Coste del día", agente.coste_hoy_eur, presupuesto, `${coste(agente.coste_hoy_eur)} de ${euros(presupuesto)}`),
        el("dl", { class: "ficha-datos" },
          el("dt", {}, "Tareas hoy"), el("dd", {}, numero(agente.tareas_hoy)),
          el("dt", {}, "Preguntas hoy"), el("dd", {}, numero(agente.preguntas_hoy || 0)),
          el("dt", {}, "Llamadas al modelo"), el("dd", {}, numero(agente.llamadas_modelo_hoy)),
          el("dt", {}, "Aprobaciones pendientes"), el("dd", {}, numero(agente.aprobaciones_pendientes)),
          el("dt", {}, "Última tarea"), el("dd", {}, ultima ? `${horaCorta(ultima.inicio)}, ${estadoCorto(ultima)}` : "—"),
        ),
        el("div", {}, el("h3", {}, "Herramientas"),
          agente.herramientas.length
            ? el("table", { class: "tabla-mini" },
                el("thead", {}, el("tr", {}, el("th", {}, "Nombre"), el("th", { class: "num" }, "Llamadas"), el("th", { class: "num" }, "Errores"))),
                el("tbody", {}, agente.herramientas.map((h) => el("tr", {}, el("td", {}, h.nombre), el("td", { class: "num" }, numero(h.llamadas)), el("td", { class: `num${h.errores ? " error" : ""}` }, numero(h.errores))))))
            : vacio("Ninguna usada hoy.")),
        el("div", {}, el("h3", {}, "Pedidos creados hoy"),
          agente.pedidos_hoy.length
            ? el("table", { class: "tabla-mini" }, el("tbody", {}, agente.pedidos_hoy.map((p) => el("tr", {},
                el("td", {}, el("strong", {}, p.pedido), el("br"), el("span", { class: "apagado" }, p.cliente || "")),
                el("td", { class: "num" }, euros(p.importe), el("br"), p.enlace ? el("a", { href: p.enlace, target: "_blank", rel: "noopener" }, "Abrir en Business Central ↗") : el("span", { class: "apagado" }, "simulación")),
              ))))
            : vacio("Ninguno hoy.")),
        el("div", { class: "detalle-acciones" },
          el("button", {
            class: `boton ${detenido ? "boton--azul" : "boton--peligro"} boton--pequeno`, type: "button",
            title: detenido ? "Vuelve a aceptar tareas" : "No acepta tareas nuevas (las que están en marcha terminan)",
            onclick: () => cambiarDetencion(agente.id, !detenido),
          }, detenido ? "Activar" : "Detener"),
          el("button", { class: "boton boton--secundario boton--pequeno", type: "button", onclick: () => abrirDialogoTarea(agente.id), disabled: detenido }, "Asignar tarea"),
        ),
      ];
    },
  };
}

async function cambiarDetencion(agente, detener) {
  try {
    await api(`/api/agentes/${encodeURIComponent(agente)}/${detener ? "detener" : "activar"}`, { method: "POST" });
    avisar(detener ? "Agente detenido: no recibirá tareas nuevas. Las que estén en marcha terminan." : "Agente activado.", "ok");
    pedirEstado();
  } catch (error) {
    avisar(error.message, "error");
  }
}

// --- controles: buscador, filtros, inmersivo, ecosistema y diálogos ---------------------------------

function prepararControles() {
  $("buscar").addEventListener("input", (e) => {
    busqueda = e.target.value.trim().toLowerCase();
    if (!estado) return;
    pintarFeed(estado, true);
    pintarPedidos(estado);
    pintarSeguimiento(estado);
    const agente = busqueda && estado.agentes.find((a) => `${a.nombre} ${a.rol}`.toLowerCase().includes(busqueda));
    if (agente) elegir({ tipo: "agente", id: agente.id });
  });
  for (const boton of $("feed-filtros").querySelectorAll("button")) {
    boton.addEventListener("click", () => {
      filtroFeed = boton.dataset.filtro;
      for (const b of $("feed-filtros").querySelectorAll("button")) b.setAttribute("aria-pressed", String(b === boton));
      if (estado) pintarFeed(estado, true);
    });
  }
  $("feed-auto").addEventListener("change", () => estado && pintarFeed(estado, true));
  $("seguimiento-tarea").addEventListener("change", (e) => seguirTarea(e.target.value));
  $("boton-inmersivo").addEventListener("click", () => alternarInmersivo());
  $("salir-inmersivo").addEventListener("click", () => alternarInmersivo(false));
  document.addEventListener("keydown", (e) => e.key === "Escape" && document.body.classList.contains("inmersivo") && alternarInmersivo(false));
  $("boton-ecosistema").addEventListener("click", () => $("dialogo-ecosistema").showModal());
  $("boton-asignar").addEventListener("click", () => abrirDialogoTarea());
  $("boton-preguntar").addEventListener("click", abrirDialogoPregunta);
  prepararDialogoTarea();
  prepararDialogoPregunta();
}

function alternarInmersivo(activar = !document.body.classList.contains("inmersivo")) {
  document.body.classList.toggle("inmersivo", activar);
  $("boton-inmersivo").setAttribute("aria-pressed", String(activar));
  requestAnimationFrame(() => escena?.recolocar());
}

const opcionesAgentes = (elegido) => [
  ...(estado?.agentes || []).map((a) => el("option", { value: a.id, disabled: a.estado === "detenido", selected: a.id === elegido }, `${a.nombre} (${a.rol})${a.estado === "detenido" ? ", detenido" : ""}`)),
  ...config.mesas.filter((m) => !m.agente).map((m) => el("option", { disabled: true }, `Vacante: ${m.vacante}`)),
];

let correos = [];

function prepararDialogoTarea() {
  const ejemplo = $("tarea-ejemplo"), texto = $("tarea-correo");
  ejemplo.addEventListener("change", () => (texto.value = correos.find((c) => c.nombre === ejemplo.value)?.texto || ""));
  $("tarea-cancelar").addEventListener("click", () => $("dialogo-tarea").close());
  $("form-tarea").addEventListener("submit", async (e) => {
    e.preventDefault();
    const boton = $("tarea-asignar");
    boton.disabled = true;
    $("tarea-aviso").textContent = "";
    try {
      const { tarea } = await api("/api/tareas", { method: "POST", cuerpo: { agente: $("tarea-agente").value, correo: texto.value, origen: ejemplo.value || null } });
      $("dialogo-tarea").close();
      tareaFijada = tarea;
      avisar(`Tarea asignada (${tarea}). El agente empieza en unos segundos.`, "ok");
    } catch (error) {
      $("tarea-aviso").textContent = error.message;
    } finally {
      boton.disabled = false;
    }
  });
}

async function abrirDialogoTarea(agente = "pedidos") {
  $("tarea-agente").replaceChildren(...opcionesAgentes(agente));
  try {
    correos = await api("/api/correos");
  } catch {
    correos = [];
  }
  $("tarea-ejemplo").replaceChildren(el("option", { value: "" }, "Pegar uno propio"), ...correos.map((c) => el("option", { value: c.nombre }, c.nombre)));
  $("tarea-correo").value = "";
  $("tarea-aviso").textContent = "";
  $("dialogo-tarea").showModal();
}

function prepararDialogoPregunta() {
  $("pregunta-cancelar").addEventListener("click", () => $("dialogo-pregunta").close());
  $("form-pregunta").addEventListener("submit", async (e) => {
    e.preventDefault();
    const boton = $("pregunta-enviar");
    boton.disabled = true;
    $("pregunta-aviso").textContent = "";
    try {
      const { tarea } = await api("/api/preguntas", { method: "POST", cuerpo: { agente: $("pregunta-agente").value, mensaje: $("pregunta-texto").value } });
      $("dialogo-pregunta").close();
      tareaFijada = tarea;
      avisar("Pregunta enviada: la respuesta aparecerá en la actividad con su coste.", "ok");
    } catch (error) {
      $("pregunta-aviso").textContent = error.message;
    } finally {
      boton.disabled = false;
    }
  });
}

function abrirDialogoPregunta() {
  $("pregunta-agente").replaceChildren(...opcionesAgentes(seleccion.tipo === "agente" ? seleccion.id : "pedidos"));
  $("pregunta-texto").value = "";
  $("pregunta-aviso").textContent = "";
  $("dialogo-pregunta").showModal();
}

// --- preferencias del navegador (solo comodidad: el nombre del aprobador) ---------------------------

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
  marcarDirecto("caido", "Error al arrancar");
  avisar(`No se pudo arrancar la oficina: ${error.message}`, "error", 20000);
});
