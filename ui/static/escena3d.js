// La planta de la oficina en 3D real (three.js), como las maquetas de javiercava.com: isometría a 30°, volúmenes
// mates en arcilla fría con cantos redondeados, luz alta desde arriba a la izquierda, sombras suaves y el oro solo en
// lo elegido y en el flujo de un pedido hacia Business Central.
// La escena no decide nada: dibuja lo que le pasa app.js (que sale de /api/estado) y avisa de lo que se pulsa.

import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/CSS2DRenderer.js";
import { RoundedBoxGeometry } from "three/addons/RoundedBoxGeometry.js";

// Colores de las figuras de javiercava.com (src/figuras/dibujo.css, tema claro)
const C = {
  muro: "#ffffff", blanco: "#f6f8fb", vidrio: "#9ccbee", acero: "#aebccd", oscuro: "#1f3f6b", azul: "#2b8fd0",
  azulMarca: "#0a4d7a", tejado: "#1b7cc3", oro: "#fdc308", verde: "#5cbd8b", madera: "#d9ab72", hormigon: "#dfe5ee",
  parcela: "#f1f4f9", suelo: "#e8edf4", tablero: "#dde4ef", ventana: "#3f6c9e", pantalla: "#0a4d7a", goma: "#22344d",
  asfalto: "#cbd5e3", raya: "#ffffff", zonaA: "#c9def0", piel: "#efd3bd", tinta: "#081a30", cielo: "#dfe7ff", rebote: "#f6efe4",
  apagado: "#c3cedb",
};
export const COLOR_ESTADO = {
  libre: "#9fb3cf", trabajando: "#1f8a5b", esperando_aprobacion: "#e8a825", error: "#c8402f", detenido: "#1270ae",
};
const ELEVACION = Math.atan(0.8165 / Math.SQRT2); // 30°: la isometría de las maquetas de la web
const AZIMUT = Math.PI / 4;
const quieto = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const materiales = new Map();
function mate(color, opciones = {}) {
  const clave = `${color}|${JSON.stringify(opciones)}`;
  if (!materiales.has(clave)) materiales.set(clave, new THREE.MeshLambertMaterial({ color, ...opciones }));
  return materiales.get(clave);
}
const matAristas = new THREE.LineBasicMaterial({ color: C.tinta, transparent: true, opacity: 0.16 });

/** Una caja de cantos redondeados (con aristas finas si es grande), apoyada en y. */
function caja(w, h, d, material, x = 0, y = 0, z = 0, { aristas = false, radio = 0.05, sombra = true } = {}) {
  const r = Math.min(radio, w / 4, h / 4, d / 4);
  const malla = new THREE.Mesh(r > 0.01 ? new RoundedBoxGeometry(w, h, d, 2, r) : new THREE.BoxGeometry(w, h, d), material);
  malla.position.set(x, y + h / 2, z);
  malla.castShadow = sombra;
  malla.receiveShadow = true;
  if (aristas) {
    const lineas = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w, h, d)), matAristas);
    malla.add(lineas);
  }
  return malla;
}

function cilindro(radio, alto, material, x = 0, y = 0, z = 0, lados = 18) {
  const malla = new THREE.Mesh(new THREE.CylinderGeometry(radio, radio, alto, lados), material);
  malla.position.set(x, y + alto / 2, z);
  malla.castShadow = true;
  malla.receiveShadow = true;
  return malla;
}

function anillo(interior, exterior, color, opacidad) {
  const malla = new THREE.Mesh(
    new THREE.RingGeometry(interior, exterior, 64),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: opacidad, depthWrite: false }),
  );
  malla.rotation.x = -Math.PI / 2;
  return malla;
}

function etiqueta(elemento, x, y, z) {
  const objeto = new CSS2DObject(elemento);
  objeto.position.set(x, y, z);
  objeto.center.set(0.5, 1); // la etiqueta queda encima del punto, con su pie en él
  return objeto;
}

// --- piezas de la oficina -------------------------------------------------------------------------

function planta(config) {
  const grupo = new THREE.Group();
  const { ancho, fondo } = config.planta;
  // Parcela (el papel de la maqueta), suelo de la oficina con su rejilla y muros del fondo (corte de diorama)
  grupo.add(caja(ancho + 11.5, 0.3, fondo + 2, mate(C.parcela), 5.25, -0.3, 0, { radio: 0.12, sombra: false }));
  grupo.add(caja(ancho, 0.25, fondo, mate(C.suelo), 0, 0, 0, { aristas: true, radio: 0.06, sombra: false }));
  const rejilla = [];
  for (let x = -ancho / 2 + 2; x < ancho / 2; x += 2) rejilla.push(x, 0.252, -fondo / 2, x, 0.252, fondo / 2);
  for (let z = -fondo / 2 + 2; z < fondo / 2; z += 2) rejilla.push(-ancho / 2, 0.252, z, ancho / 2, 0.252, z);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(rejilla, 3));
  grupo.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: C.tinta, transparent: true, opacity: 0.06 })));

  const alto = 2.3, grueso = 0.25;
  grupo.add(caja(ancho, alto, grueso, mate(C.muro), 0, 0.25, -fondo / 2 + grueso / 2, { aristas: true }));
  grupo.add(caja(grueso, alto, fondo, mate(C.muro), -ancho / 2 + grueso / 2, 0.25, 0, { aristas: true }));
  // Ventanales en los muros
  for (let x = -2.5; x < ancho / 2 - 1; x += 3.2) grupo.add(caja(2.4, 1.1, 0.04, mate(C.ventana), x, 1.05, -fondo / 2 + grueso + 0.02, { radio: 0, sombra: false }));
  for (let z = -0.2; z < fondo / 2 - 1; z += 3.2) grupo.add(caja(0.04, 1.1, 2.4, mate(C.ventana), -ancho / 2 + grueso + 0.02, 1.05, z + 0.6, { radio: 0, sombra: false }));
  return grupo;
}

function mamparas(x0, x1, z0, z1, hueco) {
  // Mamparas de vidrio de una sala (lados x = x1 y z = z1 o z = z0), con un hueco de puerta
  const grupo = new THREE.Group();
  const vidrio = mate(C.vidrio, { transparent: true, opacity: 0.32, depthWrite: false });
  const perfil = mate(C.acero);
  const alto = 2.1;
  const lado = (x, za, zb) => {
    grupo.add(caja(0.08, alto, Math.abs(zb - za), vidrio, x, 0.25, (za + zb) / 2, { radio: 0, sombra: false }));
    grupo.add(caja(0.1, 0.08, Math.abs(zb - za), perfil, x, 0.25 + alto, (za + zb) / 2, { radio: 0 }));
  };
  const frente = (z, xa, xb) => {
    grupo.add(caja(Math.abs(xb - xa), alto, 0.08, vidrio, (xa + xb) / 2, 0.25, z, { radio: 0, sombra: false }));
    grupo.add(caja(Math.abs(xb - xa), 0.08, 0.1, perfil, (xa + xb) / 2, 0.25 + alto, z, { radio: 0 }));
  };
  lado(x1, z0, z1);
  frente(hueco.z, x0, hueco.desde);
  frente(hueco.z, hueco.hasta, x1);
  return grupo;
}

function silla(x, z, giro = 0, color = C.oscuro) {
  const grupo = new THREE.Group();
  grupo.add(cilindro(0.05, 0.42, mate(C.acero), 0, 0.25, 0, 8));
  grupo.add(caja(0.62, 0.1, 0.58, mate(color), 0, 0.67, 0));
  grupo.add(caja(0.62, 0.62, 0.1, mate(color), 0, 0.77, -0.3));
  grupo.position.set(x, 0, z);
  grupo.rotation.y = giro;
  return grupo;
}

function planta_maceta(x, z, alto = 1.2) {
  const grupo = new THREE.Group();
  grupo.add(cilindro(0.3, 0.45, mate(C.hormigon), 0, 0.25, 0, 16));
  const hojas = new THREE.Mesh(new THREE.IcosahedronGeometry(0.55, 1), mate(C.verde, { flatShading: true }));
  hojas.position.set(0, 0.7 + alto * 0.45, 0);
  hojas.scale.set(1, alto, 1);
  hojas.castShadow = true;
  grupo.add(hojas);
  grupo.position.set(x, 0, z);
  return grupo;
}

/** Mesa de trabajo: tablero, faldón, monitor y teclado. El agente se sienta detrás, mirando a la cámara. */
function mesa(atenuada) {
  const grupo = new THREE.Group();
  const op = atenuada ? { transparent: true, opacity: 0.55 } : {};
  grupo.add(caja(2.6, 0.08, 1.3, mate(atenuada ? C.hormigon : C.blanco, op), 0, 0.98, 0, { aristas: !atenuada }));
  grupo.add(caja(2.5, 0.62, 0.06, mate(C.acero, op), 0, 0.36, 0.55));
  grupo.add(caja(0.06, 0.73, 1.2, mate(C.acero, op), -1.2, 0.25, 0));
  grupo.add(caja(0.06, 0.73, 1.2, mate(C.acero, op), 1.2, 0.25, 0));
  const monitor = new THREE.Group();
  monitor.add(caja(1.05, 0.62, 0.06, mate(C.oscuro, op), 0, 0.2, 0));
  monitor.add(caja(0.08, 0.2, 0.08, mate(C.acero, op), 0, 0, 0.03));
  // A un lado y girado hacia el agente, para que se le vea la cara desde la cámara
  monitor.position.set(-0.72, 1.06, 0.05);
  monitor.rotation.y = 0.5;
  grupo.add(monitor);
  if (!atenuada) grupo.add(caja(0.7, 0.03, 0.22, mate(C.hormigon), 0.2, 1.06, -0.28, { radio: 0.01 }));
  return grupo;
}

/** El agente: un robot amable. Ojos y baliza del color de su estado; brazo derecho que se levanta para pedir aprobación. */
function robot() {
  const grupo = new THREE.Group();
  const cuerpo = caja(0.7, 0.72, 0.48, mate(C.azul), 0, 0.72, 0, { radio: 0.12 });
  const cabeza = new THREE.Group();
  cabeza.add(caja(0.58, 0.46, 0.48, mate(C.muro), 0, 0, 0, { radio: 0.12 }));
  const visor = caja(0.46, 0.22, 0.02, mate(C.pantalla), 0, 0.14, 0.245, { radio: 0, sombra: false });
  cabeza.add(visor);
  const ojoMat = new THREE.MeshBasicMaterial({ color: COLOR_ESTADO.libre });
  for (const x of [-0.1, 0.1]) {
    const ojo = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.06, 0.02), ojoMat);
    ojo.position.set(x, 0.25, 0.26);
    cabeza.add(ojo);
  }
  cabeza.add(cilindro(0.02, 0.22, mate(C.acero), 0, 0.46, 0, 6));
  const baliza = new THREE.Mesh(new THREE.SphereGeometry(0.075, 16, 12), new THREE.MeshBasicMaterial({ color: COLOR_ESTADO.libre }));
  baliza.position.set(0, 0.72, 0);
  cabeza.add(baliza);
  cabeza.position.set(0, 1.5, 0);
  const brazo = (lado) => {
    const pivote = new THREE.Group();
    pivote.position.set(lado * 0.42, 1.34, 0);
    const pieza = caja(0.15, 0.55, 0.15, mate(C.azul), 0, -0.55, 0, { radio: 0.06 });
    pivote.add(pieza);
    return pivote;
  };
  const izquierdo = brazo(-1), derecho = brazo(1);
  grupo.add(cuerpo, cabeza, izquierdo, derecho);
  return { grupo, cuerpo, cabeza, izquierdo, derecho, ojoMat, baliza };
}

function persona() {
  const grupo = new THREE.Group();
  grupo.add(caja(0.66, 0.74, 0.44, mate("#14325b"), 0, 0.72, 0, { radio: 0.14 }));
  const cabeza = new THREE.Mesh(new THREE.SphereGeometry(0.24, 20, 16), mate(C.piel));
  cabeza.position.set(0, 1.68, 0);
  cabeza.castShadow = true;
  const pelo = new THREE.Mesh(new THREE.SphereGeometry(0.25, 20, 16, 0, Math.PI * 2, 0, Math.PI / 2.2), mate("#2b2f36"));
  pelo.position.set(0, 1.7, -0.02);
  grupo.add(cabeza, pelo);
  for (const lado of [-1, 1]) {
    const brazo = caja(0.14, 0.5, 0.14, mate("#14325b"), lado * 0.38, 0.92, 0.12, { radio: 0.06 });
    brazo.rotation.x = -0.9;
    grupo.add(brazo);
  }
  return grupo;
}

function edificioBC() {
  const grupo = new THREE.Group();
  grupo.add(caja(4.4, 0.18, 4.4, mate(C.hormigon), 0, 0, 0, { radio: 0.06 }));
  grupo.add(caja(3.6, 2.8, 3.6, mate(C.azulMarca), 0, 0.18, 0, { aristas: true, radio: 0.08 }));
  grupo.add(caja(3.8, 0.22, 3.8, mate(C.tejado), 0, 2.98, 0, { radio: 0.06 }));
  // Ventanas en dos fachadas y puerta hacia la oficina
  for (let fila = 0; fila < 3; fila++) {
    for (let col = -1; col <= 1; col++) {
      grupo.add(caja(0.7, 0.42, 0.03, mate(C.vidrio), col * 1.05, 0.55 + fila * 0.78, 1.81, { radio: 0, sombra: false }));
      grupo.add(caja(0.03, 0.42, 0.7, mate(C.vidrio), 1.81, 0.55 + fila * 0.78, col * 1.05, { radio: 0, sombra: false }));
    }
  }
  grupo.add(caja(0.03, 0.95, 0.8, mate(C.oscuro), -1.81, 0.18, 0, { radio: 0 }));
  // Servidores en la azotea, con su luz (se enciende al llegar una escritura)
  const luz = new THREE.MeshBasicMaterial({ color: "#74b4e6" });
  for (const x of [-0.8, 0.4]) {
    grupo.add(caja(0.9, 0.7, 1.4, mate(C.acero), x, 3.2, -0.4, { radio: 0.04 }));
    const led = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.06, 0.02), luz);
    led.position.set(x, 3.7, 0.31);
    grupo.add(led);
  }
  return { grupo, luz };
}

// --- montaje ---------------------------------------------------------------------------------------

/**
 * Monta la escena en ``contenedor``. ``alElegir({tipo, id})`` se llama al pulsar una mesa, el despacho o Business
 * Central. Devuelve ``{actualizar, elegir, enviarPedido, recolocar}`` o lanza un error si no hay WebGL.
 */
export function montarEscena(contenedor, config, { alElegir }) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor("#f4f6f9");
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  contenedor.append(renderer.domElement);
  renderer.domElement.setAttribute("aria-hidden", "true");

  const etiquetas = new CSS2DRenderer();
  Object.assign(etiquetas.domElement.style, { position: "absolute", inset: "0", pointerEvents: "none" });
  contenedor.append(etiquetas.domElement);

  const escena = new THREE.Scene();
  escena.add(new THREE.HemisphereLight(C.cielo, C.rebote, 1.25));
  const sol = new THREE.DirectionalLight("#ffffff", 1.7);
  sol.position.set(-14, 22, 6);
  sol.target.position.set(4, 0, 0);
  sol.castShadow = true;
  sol.shadow.mapSize.set(2048, 2048);
  Object.assign(sol.shadow.camera, { left: -26, right: 26, top: 22, bottom: -22, near: 1, far: 70 });
  sol.shadow.radius = 4;
  sol.shadow.bias = -0.0008;
  sol.shadow.normalBias = 0.02;
  escena.add(sol, sol.target);

  escena.add(planta(config));
  const seleccionables = [];
  const marcar = (objeto, seleccion) => {
    objeto.traverse((o) => o.isMesh && ((o.userData.seleccion = seleccion), seleccionables.push(o)));
  };

  // Despacho del director (esquina del fondo) y sala de reuniones (izquierda)
  const d = config.director, r = config.reuniones;
  escena.add(mamparas(-12, -5, -8, -1.4, { z: -1.4, desde: -9.8, hasta: -8.4 }));
  escena.add(mamparas(-12, -5, 1.4, 8, { z: 1.4, desde: -9.8, hasta: -8.4 }));
  const alfombra = caja(4.6, 0.02, 3.6, mate(C.zonaA), d.x, 0.25, d.z + 0.3, { radio: 0, sombra: false });
  escena.add(alfombra);
  const despacho = new THREE.Group();
  despacho.add(caja(2.4, 0.08, 1.1, mate(C.madera), 0, 0.98, 0.6, { aristas: true }));
  despacho.add(caja(2.3, 0.73, 0.06, mate(C.oscuro), 0, 0.25, 1.1));
  despacho.add(caja(0.8, 0.5, 0.05, mate(C.oscuro), 0.3, 1.06, 0.75));
  despacho.add(silla(0, -0.35, 0, C.goma));
  const director = persona();
  director.position.set(0, 0, -0.35);
  despacho.add(director);
  despacho.position.set(d.x, 0, d.z);
  escena.add(despacho);
  escena.add(planta_maceta(-11.2, -7.2, 1.5), planta_maceta(-5.8, -7.1, 1));
  marcar(despacho, { tipo: "director", id: "director" });

  const reuniones = new THREE.Group();
  reuniones.add(caja(3.4, 0.08, 1.7, mate(C.blanco), 0, 0.98, 0, { aristas: true, radio: 0.3 }));
  reuniones.add(cilindro(0.18, 0.73, mate(C.acero), -0.9, 0.25, 0, 10), cilindro(0.18, 0.73, mate(C.acero), 0.9, 0.25, 0, 10));
  for (const x of [-1.1, 0, 1.1]) reuniones.add(silla(x, -1.25, 0, C.acero), silla(x, 1.25, Math.PI, C.acero));
  reuniones.add(caja(0.08, 1.3, 2.2, mate(C.muro), -3.35, 0.7, 0, { radio: 0.02 }));
  reuniones.position.set(r.x, 0, r.z);
  escena.add(reuniones, planta_maceta(-5.8, 7.2, 1.2));

  // Armarios, impresora y plantas de la zona abierta
  for (const x of [9.2, 10.6]) escena.add(caja(1.3, 1.9, 0.6, mate(C.acero), x, 0.25, -7.45, { aristas: true }));
  escena.add(caja(1.1, 0.95, 0.75, mate(C.blanco), 11.2, 0.25, 6.9, { aristas: true }));
  escena.add(planta_maceta(11.1, -5.6, 1.3), planta_maceta(2.9, 7.1, 1), planta_maceta(2.9, -7.1, 1.1));

  // Business Central, fuera de la oficina, con el camino por el que llegan las escrituras
  const bc = config.business_central;
  const edificio = edificioBC();
  edificio.grupo.position.set(bc.x, 0, bc.z);
  escena.add(edificio.grupo);
  marcar(edificio.grupo, { tipo: "bc", id: "bc" });
  escena.add(caja(bc.x - 2.2 - 12, 0.02, 1.4, mate(C.asfalto), (12 + bc.x - 2.2) / 2, 0, bc.z, { radio: 0, sombra: false }));
  for (let x = 12.6; x < bc.x - 2.4; x += 1.1) escena.add(caja(0.5, 0.01, 0.08, mate(C.raya), x, 0.025, bc.z, { radio: 0, sombra: false }));

  // Mesas de los agentes
  const mesas = new Map();
  const etiquetasPorClave = new Map();
  const capaEtiqueta = (clave, tipo, alPulsar) => {
    const nodo = document.createElement("div");
    nodo.className = "etiqueta";
    nodo.dataset.tipo = tipo;
    if (alPulsar) {
      nodo.setAttribute("role", "button");
      nodo.tabIndex = 0;
      nodo.addEventListener("click", alPulsar);
      nodo.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), alPulsar()));
    }
    etiquetasPorClave.set(clave, nodo);
    return nodo;
  };

  for (const m of config.mesas) {
    const ocupada = Boolean(m.agente);
    const grupo = new THREE.Group();
    grupo.add(mesa(!ocupada));
    grupo.add(silla(0, -0.95, 0, ocupada ? C.oscuro : C.apagado));
    const aro = anillo(1.85, 2.0, COLOR_ESTADO.libre, ocupada ? 0.55 : 0.18);
    aro.position.y = 0.26;
    const elegido = anillo(2.08, 2.3, C.oro, 0.95);
    elegido.position.y = 0.262;
    elegido.visible = false;
    grupo.add(aro, elegido);
    const seleccion = ocupada ? { tipo: "agente", id: m.agente } : { tipo: "vacante", id: m.id };
    let figura = null;
    if (ocupada) {
      figura = robot();
      figura.grupo.position.set(0.2, 0, -0.95);
      figura.grupo.scale.setScalar(1.12);
      grupo.add(figura.grupo);
    }
    grupo.position.set(m.x, 0, m.z);
    escena.add(grupo);
    marcar(grupo, seleccion);
    const nodo = capaEtiqueta(`${seleccion.tipo}:${seleccion.id}`, ocupada ? "agente" : "vacante", () => alElegir(seleccion));
    grupo.add(etiqueta(nodo, 0, ocupada ? 2.7 : 1.25, ocupada ? -0.9 : 0));
    mesas.set(seleccion.id, { m, grupo, aro, elegido, figura, seleccion, estado: "libre", camino: ocupada ? caminoHaciaBC(m, bc) : null });
  }

  // Camino de cada mesa ocupada hasta Business Central: línea de puntos azul y, al crear un pedido, un punto de oro
  function caminoHaciaBC(m, destino) {
    const y = 0.3;
    const puntos = [
      new THREE.Vector3(m.x, y, m.z + 0.9), new THREE.Vector3(m.x, y, 0), new THREE.Vector3(12.6, y, 0),
      new THREE.Vector3(12.6, y, destino.z), new THREE.Vector3(destino.x - 2.25, y, destino.z),
    ];
    const curva = new THREE.CurvePath();
    for (let i = 0; i < puntos.length - 1; i++) curva.add(new THREE.LineCurve3(puntos[i], puntos[i + 1]));
    const linea = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(puntos),
      new THREE.LineDashedMaterial({ color: "#74b4e6", dashSize: 0.35, gapSize: 0.25, transparent: true, opacity: 0.8 }),
    );
    linea.computeLineDistances();
    escena.add(linea);
    return { curva, linea };
  }

  const etiquetaDirector = capaEtiqueta("director", "director", () => alElegir({ tipo: "director", id: "director" }));
  escena.add(etiqueta(etiquetaDirector, d.x - 1.2, 2.6, d.z - 1.6));
  const etiquetaBC = capaEtiqueta("bc", "bc", () => alElegir({ tipo: "bc", id: "bc" }));
  escena.add(etiqueta(etiquetaBC, bc.x, 4.3, bc.z));
  const zona = (texto, x, z) => {
    const nodo = document.createElement("div");
    nodo.className = "etiqueta";
    nodo.dataset.tipo = "zona";
    const linea = document.createElement("span");
    linea.className = "etiqueta-linea";
    linea.textContent = texto;
    nodo.append(linea);
    escena.add(etiqueta(nodo, x, 0.3, z));
  };
  zona("Sala de reuniones", r.x + 1.2, r.z + 3.1);

  // --- cámara: ortográfica, isometría a 30°, que solo se mueve si la mueve la persona ---
  const camara = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 400);
  const objetivo = new THREE.Vector3(3.2, 0, 0);
  const controles = new OrbitControls(camara, renderer.domElement);
  controles.target.copy(objetivo);
  controles.enableDamping = true;
  controles.dampingFactor = 0.12;
  controles.enablePan = false;
  controles.minZoom = 0.75;
  controles.maxZoom = 2.6;
  controles.minPolarAngle = Math.PI / 2 - ELEVACION - 0.25;
  controles.maxPolarAngle = Math.PI / 2 - ELEVACION + 0.12;
  controles.minAzimuthAngle = AZIMUT - 0.7;
  controles.maxAzimuthAngle = AZIMUT + 0.7;

  const caja3 = new THREE.Box3(new THREE.Vector3(-12.2, 0, -8.2), new THREE.Vector3(bc.x + 2.2, 3.4, 8.2));
  function vistaInicial() {
    const distancia = 60;
    camara.position.set(
      objetivo.x + distancia * Math.cos(ELEVACION) * Math.sin(AZIMUT),
      objetivo.y + distancia * Math.sin(ELEVACION),
      objetivo.z + distancia * Math.cos(ELEVACION) * Math.cos(AZIMUT),
    );
    camara.zoom = 1;
    camara.lookAt(objetivo);
    controles.target.copy(objetivo);
    recolocar();
  }

  /** Ajusta el encuadre al tamaño del contenedor para que la planta entera quepa con margen. */
  function recolocar() {
    const ancho = Math.max(contenedor.clientWidth, 1), alto = Math.max(contenedor.clientHeight, 1);
    renderer.setSize(ancho, alto);
    etiquetas.setSize(ancho, alto);
    camara.updateMatrixWorld();
    const inversa = camara.matrixWorldInverse;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const x of [caja3.min.x, caja3.max.x]) for (const y of [caja3.min.y, caja3.max.y]) for (const z of [caja3.min.z, caja3.max.z]) {
      const p = new THREE.Vector3(x, y, z).applyMatrix4(inversa);
      minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
    }
    const margen = 1.02, cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    let medioAncho = ((maxX - minX) / 2) * margen, medioAlto = ((maxY - minY) / 2) * margen + 0.4; // sitio para las etiquetas
    if (medioAncho / medioAlto > ancho / alto) medioAlto = medioAncho * (alto / ancho);
    else medioAncho = medioAlto * (ancho / alto);
    Object.assign(camara, { left: cx - medioAncho, right: cx + medioAncho, top: cy + medioAlto + 0.3, bottom: cy - medioAlto + 0.3 });
    camara.updateProjectionMatrix();
  }

  // Teclado: flechas giran e inclinan, + y − acercan, 0 vuelve a la vista inicial
  contenedor.tabIndex = 0;
  contenedor.addEventListener("keydown", (e) => {
    const desplazado = new THREE.Vector3().subVectors(camara.position, controles.target);
    const esfera = new THREE.Spherical().setFromVector3(desplazado);
    const paso = 0.09;
    if (e.key === "ArrowLeft") esfera.theta -= paso;
    else if (e.key === "ArrowRight") esfera.theta += paso;
    else if (e.key === "ArrowUp") esfera.phi -= paso / 2;
    else if (e.key === "ArrowDown") esfera.phi += paso / 2;
    else if (e.key === "+" || e.key === "=") camara.zoom = Math.min(controles.maxZoom, camara.zoom * 1.15);
    else if (e.key === "-") camara.zoom = Math.max(controles.minZoom, camara.zoom / 1.15);
    else if (e.key === "0") return vistaInicial();
    else return;
    e.preventDefault();
    esfera.theta = THREE.MathUtils.clamp(esfera.theta, controles.minAzimuthAngle, controles.maxAzimuthAngle);
    esfera.phi = THREE.MathUtils.clamp(esfera.phi, controles.minPolarAngle, controles.maxPolarAngle);
    camara.position.copy(controles.target).add(new THREE.Vector3().setFromSpherical(esfera));
    camara.updateProjectionMatrix();
    controles.update();
  });

  // Ratón: resaltar al pasar y elegir al pulsar (sin confundir un arrastre para girar con un clic)
  const rayo = new THREE.Raycaster();
  const puntero = new THREE.Vector2();
  let pasando = null, abajo = null;
  const buscar = (evento) => {
    const rect = renderer.domElement.getBoundingClientRect();
    puntero.set(((evento.clientX - rect.left) / rect.width) * 2 - 1, -((evento.clientY - rect.top) / rect.height) * 2 + 1);
    rayo.setFromCamera(puntero, camara);
    return rayo.intersectObjects(seleccionables, false)[0]?.object.userData.seleccion || null;
  };
  renderer.domElement.addEventListener("pointermove", (e) => {
    const s = buscar(e);
    const clave = s ? `${s.tipo}:${s.id}` : null;
    if (clave === pasando) return;
    pasando = clave;
    renderer.domElement.style.cursor = s ? "pointer" : "grab";
    for (const [id, mesaRef] of mesas) mesaRef.aro.material.opacity = mesaRef.seleccion.id === s?.id ? 0.95 : mesaRef.figura ? 0.55 : 0.18;
  });
  renderer.domElement.addEventListener("pointerdown", (e) => (abajo = [e.clientX, e.clientY]));
  renderer.domElement.addEventListener("pointerup", (e) => {
    if (!abajo || Math.hypot(e.clientX - abajo[0], e.clientY - abajo[1]) > 5) return;
    const s = buscar(e);
    if (s) alElegir(s);
  });

  // --- vida: posturas según el estado y el punto de oro de un pedido ---
  const envios = [];
  let destello = 0;
  const inicioReloj = performance.now();
  const reloj = { getElapsedTime: () => (performance.now() - inicioReloj) / 1000 };
  let medidas = "";
  function animar() {
    // El encuadre sigue al tamaño del contenedor (paneles que aparecen, modo inmersivo, ventana)
    const ahora = `${contenedor.clientWidth}x${contenedor.clientHeight}`;
    if (ahora !== medidas) {
      medidas = ahora;
      recolocar();
    }
    const t = reloj.getElapsedTime();
    const sinMovimiento = quieto();
    for (const ref of mesas.values()) {
      const f = ref.figura;
      if (!f) continue;
      const onda = sinMovimiento ? 0 : 1;
      f.izquierdo.rotation.set(0, 0, 0);
      f.derecho.rotation.set(0, 0, 0);
      f.cabeza.rotation.set(0, 0, 0);
      f.baliza.scale.setScalar(1);
      if (ref.estado === "trabajando") {
        f.izquierdo.rotation.x = -1.15 + Math.sin(t * 11) * 0.12 * onda;
        f.derecho.rotation.x = -1.15 + Math.sin(t * 11 + 1.7) * 0.12 * onda;
        f.cabeza.rotation.x = 0.12 + Math.sin(t * 2.2) * 0.04 * onda;
      } else if (ref.estado === "esperando_aprobacion") {
        f.izquierdo.rotation.x = -0.9;
        f.derecho.rotation.z = 2.75 + Math.sin(t * 3.2) * 0.14 * onda; // la mano levantada
        f.cabeza.rotation.y = -0.25;
        f.baliza.scale.setScalar(1 + (Math.sin(t * 4) * 0.25 + 0.25) * onda);
      } else if (ref.estado === "error") {
        f.izquierdo.rotation.x = f.derecho.rotation.x = -0.3;
        f.cabeza.rotation.z = 0.22;
        f.baliza.visible = sinMovimiento || Math.sin(t * 6) > -0.3;
      } else {
        f.izquierdo.rotation.x = f.derecho.rotation.x = -0.75;
        f.cabeza.position.y = 1.5 + Math.sin(t * 1.4) * 0.012 * onda;
      }
      if (ref.estado !== "error") f.baliza.visible = true;
    }
    for (let i = envios.length - 1; i >= 0; i--) {
      const envio = envios[i];
      const avance = (t - envio.inicio) / 1.8;
      if (avance >= 1) {
        escena.remove(envio.punto);
        envios.splice(i, 1);
        destello = t;
        continue;
      }
      envio.punto.position.copy(envio.curva.getPointAt(avance));
    }
    const brillo = Math.max(0, 1 - (t - destello) / 1.2);
    edificio.luz.color.set(brillo > 0 ? C.oro : "#74b4e6");
    controles.update();
    renderer.render(escena, camara);
    etiquetas.render(escena, camara);
  }
  renderer.setAnimationLoop(animar);
  vistaInicial();

  // --- lo que app.js le pide a la escena ---
  return {
    /** ``agentes``: [{id, estado, nombre, dato, sub}], ``director``: {nombre, dato, pendientes}, ``bc``: {dato, sub}. */
    actualizar({ agentes, director: dir, bc: datosBC, vacantes }) {
      for (const a of agentes) {
        const ref = mesas.get(a.id);
        if (!ref) continue;
        ref.estado = a.estado;
        const color = COLOR_ESTADO[a.estado] || COLOR_ESTADO.libre;
        ref.aro.material.color.set(color);
        ref.figura.ojoMat.color.set(a.estado === "detenido" ? "#34547c" : color);
        ref.figura.baliza.material.color.set(color);
        ref.figura.cuerpo.material = mate(a.estado === "detenido" ? C.apagado : C.azul);
        ref.camino.linea.material.color.set(a.estado === "trabajando" ? "#1270ae" : "#74b4e6");
        ref.camino.linea.material.opacity = a.estado === "trabajando" ? 1 : 0.7;
        pintarEtiqueta(etiquetasPorClave.get(`agente:${a.id}`), a.estado, a.nombre, a.dato, a.sub);
      }
      for (const v of vacantes) pintarEtiqueta(etiquetasPorClave.get(`vacante:${v.id}`), "vacante", `Vacante · ${v.area}`, null, null, true);
      pintarEtiqueta(etiquetaDirector, dir.pendientes ? "esperando_aprobacion" : "libre", dir.nombre, dir.dato, null, false, dir.pendientes);
      pintarEtiqueta(etiquetaBC, datosBC.modo === "api" ? "trabajando" : "libre", "Business Central", null, datosBC.dato, false, 0, "img/business-central.svg");
    },
    elegir(seleccion) {
      for (const ref of mesas.values()) ref.elegido.visible = Boolean(seleccion) && ref.seleccion.tipo === seleccion.tipo && ref.seleccion.id === seleccion.id;
      for (const [clave, nodo] of etiquetasPorClave) nodo.dataset.elegido = String(Boolean(seleccion) && clave === (seleccion.tipo === "director" || seleccion.tipo === "bc" ? seleccion.tipo : `${seleccion.tipo}:${seleccion.id}`));
    },
    /** Animación corta: un punto de oro de la mesa del agente al bloque de Business Central. */
    enviarPedido(agente) {
      const ref = mesas.get(agente);
      if (!ref?.camino) return;
      if (quieto()) {
        destello = reloj.getElapsedTime();
        return;
      }
      const punto = new THREE.Mesh(new THREE.SphereGeometry(0.22, 16, 12), new THREE.MeshBasicMaterial({ color: C.oro }));
      escena.add(punto);
      envios.push({ punto, curva: ref.camino.curva, inicio: reloj.getElapsedTime() });
    },
    recolocar,
    vistaInicial,
  };
}

function pintarEtiqueta(nodo, estado, nombre, dato, sub, vacante = false, contador = 0, icono = null) {
  if (!nodo) return;
  const firma = JSON.stringify([estado, nombre, dato, sub, contador]);
  if (nodo.dataset.firma === firma) return;
  nodo.dataset.firma = firma;
  nodo.dataset.estado = estado;
  const linea = document.createElement("span");
  linea.className = "etiqueta-linea";
  if (icono) {
    const imagen = document.createElement("img");
    imagen.src = icono;
    imagen.alt = "";
    linea.append(imagen);
  } else {
    const punto = document.createElement("span");
    punto.className = "punto";
    punto.dataset.estado = vacante ? "libre" : estado;
    linea.append(punto);
  }
  linea.append(nombre);
  if (dato) {
    const d = document.createElement("span");
    d.className = "etiqueta-dato";
    d.textContent = `· ${dato}`;
    linea.append(d);
  }
  if (contador) {
    const c = document.createElement("span");
    c.className = "contador";
    c.textContent = String(contador);
    c.title = `${contador} aprobación(es) pendiente(s)`;
    linea.append(c);
  }
  const hijos = [linea];
  if (sub) {
    const s = document.createElement("span");
    s.className = "etiqueta-sub";
    s.textContent = sub;
    hijos.push(s);
  }
  nodo.replaceChildren(...hijos);
  nodo.setAttribute("aria-label", [nombre, dato, sub].filter(Boolean).join(". "));
}
