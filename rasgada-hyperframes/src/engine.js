// Rasgada PS2 — tutorial de surf em 3D low-poly estilo PlayStation 2.
// Tudo é determinístico: renderFrame(n) sempre gera o mesmo quadro.
import * as THREE from 'three';

const W = 540, H = 960;                       // canvas interno; a composição dobra para 1080x1920
const W3 = W, H3 = H;

// ---------------------------------------------------------------- utils
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const easeOut = t => 1 - Math.pow(1 - clamp(t, 0, 1), 3);
const easeInOut = t => { t = clamp(t, 0, 1); return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
const easeOutBack = t => { t = clamp(t, 0, 1); const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };
const hash = n => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
const frac = x => x - Math.floor(x);
const DEG = Math.PI / 180;
function rng(seed) { let a = seed >>> 0; return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const X_AXIS = V3(1, 0, 0), Y_AXIS = V3(0, 1, 0);
const srgb = (r, g, b) => new THREE.Color().setRGB(r, g, b, THREE.SRGBColorSpace);

// Hermite (Catmull-Rom não uniforme) sobre keyframes [t, v1, v2...]
function herm(K, tau, idx) {
  if (tau <= K[0][0]) return K[0][idx];
  if (tau >= K[K.length - 1][0]) return K[K.length - 1][idx];
  let i = 0; while (K[i + 1][0] < tau) i++;
  const t0 = K[i][0], t1 = K[i + 1][0], dt = t1 - t0, t = (tau - t0) / dt;
  const m = j => { const a = K[Math.max(j - 1, 0)], b = K[Math.min(j + 1, K.length - 1)]; return (b[idx] - a[idx]) / (b[0] - a[0]); };
  const p1 = K[i][idx], p2 = K[i + 1][idx], m1 = m(i), m2 = m(i + 1);
  const t2 = t * t, t3 = t2 * t;
  return (2 * t3 - 3 * t2 + 1) * p1 + (t3 - 2 * t2 + t) * dt * m1 + (-2 * t3 + 3 * t2) * p2 + (t3 - t2) * dt * m2;
}

// ---------------------------------------------------------------- perfil da onda
// Perfis (z, y) do mar aberto (z<0) até a areia (z>0). Extrudados ao longo de X.
const P0c = [[-30,0],[-14,0.25],[-7,1.0],[-3.5,2.0],[-1.3,2.7],[0.4,3.0],[1.6,2.9],[2.4,2.6],[2.8,2.35],[3.1,2.1],[3.6,1.7],[4.3,1.1],[5.5,0.45],[7.5,0.0],[14,-0.05],[40,0]];   // ombro
const P1c = [[-30,0],[-14,0.3],[-7,1.5],[-3.5,3.1],[-1.3,4.1],[0.4,4.6],[2.0,4.5],[3.1,3.8],[2.5,3.25],[1.6,3.0],[1.5,2.2],[2.2,1.2],[3.8,0.45],[6.5,0.0],[14,-0.05],[40,0]];   // lip quebrando
const P2c = [[-30,0],[-14,0.2],[-7,0.6],[-3.5,1.2],[-1.3,1.6],[0.4,1.9],[2.0,2.0],[3.1,1.9],[3.6,1.8],[4.0,1.7],[4.5,1.4],[5.2,1.0],[6.2,0.5],[8,0.1],[14,0],[40,0]];        // espuma
function refine(pts) {
  const out = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(i + 2, pts.length - 1)];
    out.push(p1);
    const t = 0.5;
    out.push([0, 1].map(k => 0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t * t * t)));
  }
  out.push(pts[pts.length - 1]);
  return out;
}
const R0 = refine(P0c), R1 = refine(P1c), R2 = refine(P2c);
const NS = R0.length; // 31
const FACE_TOP = 18, TROUGH = 26, LIP_TIP = 14;

function waveParams(d) {
  const b = 1 - smooth(-9, -1.5, d);            // já quebrou (espuma)
  const c = d < 0 ? 1 : 1 - smooth(0, 24, d);   // quanto o lip está pitando
  const amp = smooth(-80, -52, d) * (1 - smooth(48, 100, d));
  return { b, c, amp };
}
function profileAt(d, out) {
  const { b, c, amp } = waveParams(d);
  for (let j = 0; j < NS; j++) {
    let z = lerp(R0[j][0], R1[j][0], c), y = lerp(R0[j][1], R1[j][1], c);
    z = lerp(z, R2[j][0], b); y = lerp(y, R2[j][1], b);
    out[j * 2] = z; out[j * 2 + 1] = y * amp * 1.2;
  }
  return out;
}
const tmpProf = new Float32Array(NS * 2);
function faceAt(d, u) {
  profileAt(d, tmpProf);
  const n = TROUGH - FACE_TOP, pts = [], cum = [0];
  for (let k = 0; k <= n; k++) { const j = TROUGH - k; pts.push([tmpProf[j * 2], tmpProf[j * 2 + 1]]); }
  for (let k = 1; k <= n; k++) cum.push(cum[k - 1] + Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]));
  const L = cum[n], s = clamp(u, 0, 1) * L;
  let k = 0; while (k < n - 1 && cum[k + 1] < s) k++;
  const t = (s - cum[k]) / ((cum[k + 1] - cum[k]) || 1);
  const z = lerp(pts[k][0], pts[k + 1][0], t), y = lerp(pts[k][1], pts[k + 1][1], t);
  const tan = i => { const a = pts[Math.max(i - 1, 0)], b = pts[Math.min(i + 1, n)]; const dz = b[0] - a[0], dy = b[1] - a[1]; const l = Math.hypot(dz, dy) || 1; return [dz / l, dy / l]; };
  const t0 = tan(k), t1 = tan(k + 1);
  let tz = lerp(t0[0], t1[0], t), ty = lerp(t0[1], t1[1], t); const l = Math.hypot(tz, ty); tz /= l; ty /= l;
  return { z, y, tz, ty, L };
}
function lipTipAt(d) { profileAt(d, tmpProf); return [tmpProf[LIP_TIP * 2], tmpProf[LIP_TIP * 2 + 1]]; }
function profilePoint(d, jf) { // jf: índice contínuo no perfil refinado
  profileAt(d, tmpProf); const j = clamp(Math.floor(jf), 0, NS - 2), t = jf - j;
  return [lerp(tmpProf[j * 2], tmpProf[j * 2 + 2], t), lerp(tmpProf[j * 2 + 1], tmpProf[j * 2 + 3], t)];
}

// ---------------------------------------------------------------- a surfada (trajetória)
// d = posição relativa ao ponto de quebra (m), u = altura na parede (0 base, 1 topo)
const VP = 4.0, FACE_L = 4.3;
const KEYS = (() => {
  const k = [];
  for (let i = 0; i <= 10; i++) k.push([i * 0.8, 9.0 + (i % 2 ? 0.35 : -0.15), i % 2 ? 0.32 : 0.68]);
  k.push([8.7, 9.4, 0.30], [9.3, 9.9, 0.07], [9.8, 10.4, 0.035], [10.3, 10.3, 0.22], [10.8, 9.0, 0.62],
         [11.2, 7.9, 0.86], [11.45, 7.6, 0.91], [11.8, 6.7, 0.66], [12.3, 6.1, 0.22], [12.8, 6.6, 0.06],
         [13.4, 7.8, 0.2], [14.0, 8.5, 0.5]);
  for (let i = 0; i <= 16; i++) k.push([14.8 + i * 0.8, 9.0 + (i % 2 ? -0.15 : 0.35), i % 2 ? 0.66 : 0.33]);
  return k;
})();
const dAt = t => herm(KEYS, t, 1);
const uAt = t => clamp(herm(KEYS, t, 2), 0.02, 0.95);
function pathHeading(t) { const e = 0.005; const dd = (dAt(t + e) - dAt(t - e)) / (2 * e), du = (uAt(t + e) - uAt(t - e)) / (2 * e); return Math.atan2(FACE_L * du, VP + dd) / DEG; }
// Na rasgada a prancha pivota mais do que a trajetória: rabeta solta.
const SNAP = [[11.25, 75], [11.4, 48], [11.5, 0], [11.6, -70], [11.72, -112]];
const T_SNAP0 = 11.27, T_SNAP1 = 11.8;
function heading(t) {
  const w = smooth(11.1, 11.25, t) * (1 - smooth(11.72, 11.95, t));
  const hp = pathHeading(t);
  return w > 0 ? lerp(hp, herm(SNAP, t, 1), w) : hp;
}
function hdot(t) { const e = 0.02; return (heading(t + e) - heading(t - e)) / (2 * e); }
function hdotS(t) { let s = 0; for (let k = -2; k <= 2; k++) s += hdot(t + k * 0.03); return s / 5; }

function rideState(t) {
  const d = dAt(t), u = uAt(t), xc = VP * t;
  const f = faceAt(d, u);
  const Nf = V3(0, -f.tz, f.ty);
  const N = Nf.clone().addScaledVector(Y_AXIS, 0.55).normalize();
  const T = V3(0, N.z, -N.y);
  const h = heading(t) * DEG;
  const F = V3(Math.cos(h), 0, 0).addScaledVector(T, Math.sin(h)).normalize();
  const Zl = V3().crossVectors(F, N).normalize();
  const pos = V3(xc + d, f.y, f.z).addScaledVector(Nf, 0.1);
  const Nb = N.clone().addScaledVector(Y_AXIS, 0.6).normalize();
  const Fb = F.clone().addScaledVector(Nb, -F.dot(Nb)).normalize();
  const Zb = V3().crossVectors(Fb, Nb).normalize();
  const hd = hdotS(t), hdA = hdotS(t + 0.12);
  const roll = clamp(0.26 * hd, -55, 42);
  const crouch = clamp(0.38 + 0.42 * Math.min(Math.abs(hd) / 220, 1) + 0.15 * (1 - smooth(0.05, 0.25, u)), 0.3, 0.92);
  const twist = clamp(15 - 0.22 * hdA, -25, 100);
  return { t, d, u, xc, pos, T, N, F, Zl, Nb, Fb, Zb, h, hd, hdA, roll, crouch, twist };
}
function riderPosSmooth(t, span = 0.12) {
  const p = V3(); for (let k = -3; k <= 3; k++) p.add(rideState(t + k * span).pos); return p.multiplyScalar(1 / 7);
}

export function create(outCanvas) {
// ---------------------------------------------------------------- three.js setup
const out = outCanvas;
const ctx = out.getContext('2d');
const glCanvas = document.createElement('canvas'); glCanvas.width = W3; glCanvas.height = H3;
const renderer = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: false, preserveDrawingBuffer: true });
renderer.setPixelRatio(1); renderer.setSize(W3, H3, false);
const scene = new THREE.Scene();
const HORIZON = srgb(0.72, 0.86, 0.96);
scene.background = HORIZON.clone();
scene.fog = new THREE.Fog(HORIZON.clone(), 70, 420);
const camera = new THREE.PerspectiveCamera(65, W3 / H3, 0.1, 1500);

scene.add(new THREE.HemisphereLight(0xcfeaff, 0x1d4a6a, 1.5));
const sun = new THREE.DirectionalLight(0xfff0d0, 2.6); sun.position.set(0.5, 1.0, 0.75); scene.add(sun);

function canvasTex(w, h, draw, repeat = false) {
  const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d'); draw(g, w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.magFilter = THREE.NearestFilter; t.minFilter = THREE.NearestFilter; t.generateMipmaps = false;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; }
  return t;
}
function waterDraw(g, w, h) {
  g.fillStyle = '#cfe0e8'; g.fillRect(0, 0, w, h);
  const r = rng(7);
  for (let i = 0; i < 170; i++) {
    const x = r() * w | 0, y = r() * h | 0, l = 2 + r() * 11 | 0;
    g.fillStyle = r() < 0.55 ? 'rgba(255,255,255,0.6)' : 'rgba(90,140,175,0.35)';
    g.fillRect(x, y, l, 1); if (x + l > w) g.fillRect(x - w, y, l, 1);
  }
  for (let i = 0; i < 40; i++) { g.fillStyle = '#fff'; g.fillRect(r() * w | 0, r() * h | 0, 1, 1); }
}
const waveTex = canvasTex(64, 64, waterDraw, true);
const seaTex = canvasTex(64, 64, waterDraw, true);

// ---------- céu
{
  const g = new THREE.SphereGeometry(900, 16, 10);
  const cols = [], p = g.attributes.position;
  const top = srgb(0.16, 0.42, 0.86), mid = srgb(0.45, 0.70, 0.95);
  for (let i = 0; i < p.count; i++) {
    const y = p.getY(i) / 900; const c = new THREE.Color();
    if (y > 0.25) c.lerpColors(mid, top, clamp((y - 0.25) / 0.6, 0, 1)); else c.lerpColors(HORIZON, mid, clamp(y / 0.25, 0, 1));
    cols.push(c.r, c.g, c.b);
  }
  g.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
  scene.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide, fog: false, depthWrite: false })));
  const sunTex = canvasTex(32, 32, (gg) => {
    for (let y = 0; y < 32; y++) for (let x = 0; x < 32; x++) { const r = Math.hypot(x - 15.5, y - 15.5); if (r < 9) { gg.fillStyle = '#fffbe6'; gg.fillRect(x, y, 1, 1); } else if (r < 15) { gg.fillStyle = `rgba(255,240,180,${(1 - (r - 9) / 6) * 0.6})`; gg.fillRect(x, y, 1, 1); } }
  });
  const sunSpr = new THREE.Sprite(new THREE.SpriteMaterial({ map: sunTex, fog: false, depthWrite: false, transparent: true }));
  sunSpr.position.set(420, 330, 600); sunSpr.scale.set(110, 110, 1); scene.add(sunSpr);
  const cloudTex = canvasTex(48, 20, (gg, w, h) => {
    const r = rng(3); gg.fillStyle = '#ffffff';
    for (let i = 0; i < 16; i++) { const cx = 8 + r() * 32, cy = 9 + r() * 5, rr = 3 + r() * 6; for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (Math.hypot(x - cx, (y - cy) * 1.4) < rr) gg.fillRect(x, y, 1, 1); }
    gg.fillStyle = 'rgba(190,210,235,0.9)'; gg.fillRect(0, 15, w, 5); gg.clearRect(0, 18, w, 2);
  });
  const r = rng(11);
  for (let i = 0; i < 22; i++) {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: cloudTex, fog: false, transparent: true, depthWrite: false, opacity: 0.95 }));
    const a = r() * Math.PI * 2, dist = 650 + r() * 150;
    s.position.set(Math.cos(a) * dist, 80 + r() * 140, Math.sin(a) * dist); const sc = 90 + r() * 120; s.scale.set(sc, sc * 0.42, 1); scene.add(s);
  }
}

// ---------- litoral (morros low-poly, areia, coqueiros)
const flat = (color, extra = {}) => new THREE.MeshLambertMaterial({ color, flatShading: true, ...extra });
{
  const sand = new THREE.Mesh(new THREE.BoxGeometry(1600, 1, 50), flat(0xe8d39a)); sand.position.set(100, -0.3, 175); scene.add(sand);
  const r = rng(21);
  for (let i = 0; i < 26; i++) {
    const g = new THREE.IcosahedronGeometry(1, 0); const m = new THREE.Mesh(g, flat(r() < 0.5 ? 0x2f7d3a : 0x3c9446));
    const s = 40 + r() * 70; m.scale.set(s * (1.3 + r()), s * (0.5 + r() * 0.6), s); m.position.set(-500 + i * 50 + r() * 30, 0, 235 + r() * 60); scene.add(m);
  }
  for (let i = 0; i < 6; i++) { // ilha distante
    const m = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 0), flat(0x4f8a72));
    m.scale.set(60 + i * 14, 28 + i * 6, 50); m.position.set(-260 + i * 38, -4, -380 - i * 8); scene.add(m);
  }
  for (let i = 0; i < 30; i++) { // coqueiros
    const tr = new THREE.Group();
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.6, 9, 5), flat(0x8a6a3c)); trunk.position.y = 4.5; trunk.rotation.z = (r() - 0.5) * 0.3; tr.add(trunk);
    for (let k = 0; k < 5; k++) { const leaf = new THREE.Mesh(new THREE.ConeGeometry(0.9, 6, 3), flat(0x2e8b3a)); leaf.position.y = 9; leaf.rotation.set(1.2, k * 1.26, 0); leaf.translateY(2.5); tr.add(leaf); }
    tr.position.set(-300 + i * 28 + r() * 10, 0, 166 + r() * 14); scene.add(tr);
  }
}

// ---------- mar aberto
const sea = new THREE.Mesh(new THREE.PlaneGeometry(2400, 2400), new THREE.MeshLambertMaterial({ color: srgb(0.12, 0.42, 0.58), map: seaTex }));
sea.rotation.x = -Math.PI / 2; sea.position.y = -0.04; seaTex.repeat.set(2400 / 7, 2400 / 7); scene.add(sea);

// ---------- a onda (malha extrudada, fixa no referencial da onda)
const XOFF = (() => { const a = []; let x = -82; while (x < -14) { a.push(x); x += 4; } while (x < 34) { a.push(x); x += 1.25; } while (x <= 104) { a.push(x); x += 4; } return a; })();
const wave = (() => {
  const nx = XOFF.length, pos = [], col = [], uv = [], idx = [];
  const prof = new Float32Array(NS * 2);
  const cDeep = srgb(0.05, 0.30, 0.50), cBack = srgb(0.08, 0.36, 0.55), cCrest = srgb(0.20, 0.66, 0.70), cLip = srgb(0.55, 0.88, 0.85),
        cFace = srgb(0.10, 0.50, 0.62), cTrough = srgb(0.07, 0.36, 0.53), cFlat = srgb(0.12, 0.42, 0.58), cFoam = srgb(0.93, 0.97, 1.0), cUpper = srgb(0.24, 0.72, 0.72);
  const tmp = new THREE.Color();
  for (let i = 0; i < nx; i++) {
    const d = XOFF[i]; profileAt(d, prof); const { b, c, amp } = waveParams(d);
    let arc = 0;
    for (let j = 0; j < NS; j++) {
      const z = prof[j * 2], y = prof[j * 2 + 1];
      if (j > 0) arc += Math.hypot(z - prof[j * 2 - 2], y - prof[j * 2 - 1]);
      pos.push(d, y, z); uv.push(d * 0.11, arc * 0.11);
      const jc = j / 2; // índice no perfil grosso
      if (jc <= 3) tmp.lerpColors(cFlat, cBack, jc / 3);
      else if (jc <= 5) tmp.lerpColors(cBack, cCrest, (jc - 3) / 2);
      else if (jc < 9) { tmp.lerpColors(cCrest, cLip, Math.sin((jc - 5) / 4 * Math.PI) * 0.8); if (jc >= 6 && jc <= 8) tmp.lerp(cFoam, 0.55 * c * c); }
      else if (jc <= 13) tmp.lerpColors(cTrough, cUpper, Math.pow(clamp(y / (3.0 * Math.max(amp, 0.05)), 0, 1), 1.3));
      else tmp.lerpColors(cTrough, cFlat, clamp(jc - 13, 0, 1));
      if (jc > 2 && jc < 14) tmp.lerp(cFoam, b * 0.92);
      tmp.lerp(cFlat, 1 - amp);
      col.push(tmp.r, tmp.g, tmp.b);
    }
  }
  for (let i = 0; i < nx - 1; i++) for (let j = 0; j < NS - 1; j++) {
    const a = i * NS + j, b2 = (i + 1) * NS + j, c2 = a + 1, d2 = b2 + 1;
    idx.push(a, c2, b2, b2, c2, d2);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  const m = new THREE.Mesh(g, new THREE.MeshLambertMaterial({ vertexColors: true, map: waveTex, flatShading: true, side: THREE.DoubleSide }));
  scene.add(m); return m;
})();

// ---------------------------------------------------------------- surfista
const boardPivot = new THREE.Object3D(), bodyPivot = new THREE.Object3D();
scene.add(boardPivot, bodyPivot);
const SKIN = 0xb9773f, LYCRA = 0xe8231e, SHORTS = 0x1b1b2a, HAIR = 0x24160c;
{
  const s = new THREE.Shape();
  const top = [[-0.92, 0.12], [-0.7, 0.19], [-0.4, 0.235], [0, 0.24], [0.35, 0.215], [0.6, 0.16], [0.8, 0.08], [0.93, 0.0]];
  s.moveTo(top[0][0], -top[0][1]); top.forEach(p => s.lineTo(p[0], p[1])); for (let i = top.length - 2; i >= 0; i--) s.lineTo(top[i][0], -top[i][1]); s.closePath();
  const g = new THREE.ExtrudeGeometry(s, { depth: 0.05, bevelEnabled: true, bevelThickness: 0.015, bevelSize: 0.02, bevelSegments: 1 });
  g.rotateX(-Math.PI / 2); g.translate(0, -0.065, 0);
  const board = new THREE.Mesh(g, flat(0xf6f2e6)); boardPivot.add(board);
  const stripe = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.004, 0.46), flat(0xe8231e)); stripe.position.set(0.28, 0.001, 0); boardPivot.add(stripe);
  const stripe2 = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.004, 0.47), flat(0x1e6fe8)); stripe2.position.set(0.18, 0.001, 0); boardPivot.add(stripe2);
  const pad = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.008, 0.24), flat(0x151515)); pad.position.set(-0.72, 0.0, 0); boardPivot.add(pad);
  const finShape = new THREE.Shape(); finShape.moveTo(0, 0); finShape.lineTo(0.11, 0); finShape.lineTo(-0.02, -0.12); finShape.closePath();
  const finG = new THREE.ShapeGeometry(finShape);
  [[-0.78, 0.15], [-0.78, -0.15], [-0.86, 0]].forEach(([x, z]) => { const f = new THREE.Mesh(finG, flat(0x333a44, { side: THREE.DoubleSide })); f.position.set(x, -0.07, z); boardPivot.add(f); });
}
const torso = new THREE.Group(); torso.rotation.order = 'YXZ'; bodyPivot.add(torso);
const headGroup = new THREE.Group(); headGroup.rotation.order = 'YXZ'; headGroup.position.y = 0.56; torso.add(headGroup);
const shoulderR = new THREE.Object3D(), shoulderL = new THREE.Object3D(); shoulderR.position.set(0.2, 0.46, 0); shoulderL.position.set(-0.2, 0.46, 0); torso.add(shoulderR, shoulderL);
const hipR = new THREE.Object3D(), hipL = new THREE.Object3D(); bodyPivot.add(hipR, hipL);
const footR = new THREE.Object3D(), footL = new THREE.Object3D(); footR.position.set(0.34, 0.02, 0.02); footL.position.set(-0.37, 0.02, 0.0); boardPivot.add(footR, footL);
{
  const pelvis = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.2, 0.23), flat(SHORTS)); pelvis.position.y = 0.03; torso.add(pelvis);
  const chest = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.42, 0.22), flat(LYCRA)); chest.position.y = 0.32; torso.add(chest);
  const num = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.16, 0.01), flat(0xffffff)); num.position.set(0, 0.34, -0.115); torso.add(num);
  const neck = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.1), flat(SKIN)); neck.position.y = 0.54; torso.add(neck);
  const faceTex = canvasTex(16, 16, g => {
    g.fillStyle = '#b9773f'; g.fillRect(0, 0, 16, 16);
    g.fillStyle = '#24160c'; g.fillRect(0, 0, 16, 3); g.fillRect(3, 5, 3, 1); g.fillRect(10, 5, 3, 1);
    g.fillStyle = '#fff'; g.fillRect(4, 7, 2, 2); g.fillRect(10, 7, 2, 2);
    g.fillStyle = '#111'; g.fillRect(5, 7, 1, 2); g.fillRect(10, 7, 1, 2);
    g.fillStyle = '#93562a'; g.fillRect(7, 9, 2, 2);
    g.fillStyle = '#5e2a14'; g.fillRect(6, 12, 4, 1);
  });
  const sk = flat(SKIN);
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.21, 0.25, 0.23), [sk, sk, sk, sk, sk, new THREE.MeshLambertMaterial({ map: faceTex })]);
  head.position.y = 0.13; headGroup.add(head);
  const hair = new THREE.Mesh(new THREE.BoxGeometry(0.23, 0.08, 0.25), flat(HAIR)); hair.position.set(0, 0.27, 0.01); headGroup.add(hair);
  const hairB = new THREE.Mesh(new THREE.BoxGeometry(0.23, 0.16, 0.06), flat(HAIR)); hairB.position.set(0, 0.2, 0.11); headGroup.add(hairB);
  const footG = new THREE.BoxGeometry(0.11, 0.06, 0.27);
  const fr = new THREE.Mesh(footG, flat(SKIN)); fr.position.set(0.34, 0.03, -0.03); fr.rotation.y = 0.25; boardPivot.add(fr);
  const fl = new THREE.Mesh(footG, flat(SKIN)); fl.position.set(-0.37, 0.03, -0.02); fl.rotation.y = -0.15; boardPivot.add(fl);
}
function seg(w, color) { const g = new THREE.BoxGeometry(w, 1, w); g.translate(0, 0.5, 0); const m = new THREE.Mesh(g, flat(color)); scene.add(m); return m; }
const limbs = {
  thighR: seg(0.16, SHORTS), thighL: seg(0.16, SHORTS), shinR: seg(0.11, SKIN), shinL: seg(0.11, SKIN),
  uarmR: seg(0.1, LYCRA), uarmL: seg(0.1, LYCRA), farmR: seg(0.085, SKIN), farmL: seg(0.085, SKIN),
};
const handR = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.1, 0.05), flat(SKIN)), handL = handR.clone(); scene.add(handR, handL);
function place(mesh, a, b) {
  const dir = V3().subVectors(b, a); const len = dir.length();
  mesh.position.copy(a); mesh.quaternion.setFromUnitVectors(Y_AXIS, dir.multiplyScalar(1 / (len || 1))); mesh.scale.set(1, len, 1);
}
function ik(A, C, l1, l2, hint) {
  const AC = V3().subVectors(C, A); let d = AC.length(); const dir = AC.clone().normalize();
  d = clamp(d, Math.abs(l1 - l2) + 1e-3, (l1 + l2) * 0.999);
  const a = (l1 * l1 - l2 * l2 + d * d) / (2 * d), h = Math.sqrt(Math.max(l1 * l1 - a * a, 0));
  const perp = hint.clone().addScaledVector(dir, -hint.dot(dir)).normalize();
  const B = A.clone().addScaledVector(dir, a).addScaledVector(perp, h);
  const Cc = A.clone().addScaledVector(dir, d);
  return [B, Cc];
}
const m4 = new THREE.Matrix4(), qB = new THREE.Quaternion(), qR = new THREE.Quaternion();
function placeRider(S) {
  m4.makeBasis(S.F, S.N, S.Zl); qB.setFromRotationMatrix(m4);
  boardPivot.position.copy(S.pos); boardPivot.quaternion.copy(qB).multiply(qR.setFromAxisAngle(X_AXIS, -S.roll * DEG));
  m4.makeBasis(S.Fb, S.Nb, S.Zb); qB.setFromRotationMatrix(m4);
  bodyPivot.position.copy(S.pos); bodyPivot.quaternion.copy(qB).multiply(qR.setFromAxisAngle(X_AXIS, -S.roll * 0.45 * DEG));
  const hy = 0.98 - 0.42 * S.crouch;
  hipR.position.set(0.11, hy - 0.02, 0.04); hipL.position.set(-0.11, hy - 0.02, 0.04);
  torso.position.set(0.02, hy, 0.04);
  torso.rotation.y = -S.twist * DEG * 0.85;
  torso.rotation.x = -(0.18 + 0.5 * S.crouch);
  torso.rotation.z = clamp(S.hd, -300, 300) * -0.0006;
  headGroup.rotation.y = -S.twist * DEG * 0.45;
  headGroup.rotation.x = 0.25 + 0.3 * S.crouch;
  scene.updateMatrixWorld(true);
  const wp = o => o.getWorldPosition(V3());
  const bq = bodyPivot.quaternion;
  // pernas
  [[hipR, footR, V3(-0.25, 0.15, -1), 'thighR', 'shinR'], [hipL, footL, V3(0.25, 0.15, -1), 'thighL', 'shinL']].forEach(([hp, ft, hint, a, b]) => {
    const A = wp(hp), C = wp(ft); const [K, Cc] = ik(A, C, 0.47, 0.47, hint.applyQuaternion(bq));
    place(limbs[a], A, K); place(limbs[b], K, Cc);
  });
  // braços
  const wB = clamp(S.hd / 140, 0, 1), wS = clamp(-S.hdA / 260, 0, 1);
  const neutralR = V3(0.56, 0.06, -0.18), toeR = V3(0.42, -0.22, -0.46), snapR = V3(0.12, 0.08, 0.52);
  const neutralL = V3(-0.5, 0.02, -0.1), toeL = V3(-0.46, 0.26, 0.16), snapL = V3(0.12, 0.42, -0.45);
  const tR = neutralR.clone().lerp(toeR, wB).lerp(snapR, wS), tL = neutralL.clone().lerp(toeL, wB).lerp(snapL, wS);
  const tq = torso.getWorldQuaternion(new THREE.Quaternion());
  [[shoulderR, tR, 'uarmR', 'farmR', handR], [shoulderL, tL, 'uarmL', 'farmL', handL]].forEach(([sh, tgt, a, b, hand]) => {
    const A = wp(sh), C = torso.localToWorld(tgt.clone()); const hint = V3(0, -1, 0.5).applyQuaternion(tq);
    const [E, Cc] = ik(A, C, 0.29, 0.28, hint); place(limbs[a], A, E); place(limbs[b], E, Cc);
    hand.position.copy(Cc); hand.quaternion.copy(limbs[b].quaternion);
  });
}

// ---------------------------------------------------------------- partículas
const SPRAY = (() => { // pré-calculado: rasgada + spray de borda
  const list = []; const r = rng(99);
  const tailAt = (t) => { const S = rideState(t); return { S, tail: S.pos.clone().addScaledVector(S.F, -0.8) }; };
  // leque da rasgada
  for (let i = 0; i < 2200; i++) {
    const te = T_SNAP0 + Math.pow(r(), 0.8) * (T_SNAP1 - T_SNAP0);
    const a = tailAt(te), b = tailAt(te + 0.01);
    const rel = V3().subVectors(V3().subVectors(b.tail, b.S.pos), V3().subVectors(a.tail, a.S.pos)).normalize();
    const dir = rel.multiplyScalar(1.0).addScaledVector(a.S.N, 0.75).addScaledVector(Y_AXIS, 0.8).add(V3(-0.15, 0, -0.35)).normalize();
    const sp = 5 + r() * 6.5;
    const v = dir.multiplyScalar(sp).add(V3(r() - 0.5, r() - 0.5, r() - 0.5).multiplyScalar(3.4));
    v.x += VP * 0.6;
    list.push({ te, life: 0.9 + r() * 0.9, p: a.tail.clone().addScaledVector(V3(r() - .5, r() - .5, r() - .5), 0.25), v, w: r() < 0.25 });
  }
  // spray de borda nas curvas
  let acc = 0;
  for (let t = 0; t < 23; t += 1 / 120) {
    const hd = hdotS(t); const inten = clamp((Math.abs(hd) - 45) / 160, 0, 1.4);
    acc += inten * 260 / 120;
    while (acc >= 1) {
      acc -= 1; const S = rideState(t + r() / 120);
      const outside = S.Zl.clone().multiplyScalar(hd > 0 ? 1 : -1);
      const p = S.pos.clone().addScaledVector(S.F, -0.25 - r() * 0.35).addScaledVector(outside, 0.22);
      const v = outside.clone().multiplyScalar(2 + r() * 2.5).addScaledVector(S.N, 1.5 + r() * 2).addScaledVector(Y_AXIS, 1 + r()).addScaledVector(S.F, -1 + r() * 0.8);
      v.x += VP * 0.8;
      list.push({ te: t, life: 0.45 + r() * 0.5, p, v, w: r() < 0.3 });
    }
  }
  return list;
})();
function makePoints(n, size, color, maxPx = 8) {
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(n * 3), 3));
  const mat = new THREE.PointsMaterial({ size, color, sizeAttenuation: true });
  mat.onBeforeCompile = sh => { sh.vertexShader = sh.vertexShader.replace('#include <fog_vertex>', `gl_PointSize = clamp(gl_PointSize, 2.0, ${maxPx.toFixed(1)});\n#include <fog_vertex>`); };
  const p = new THREE.Points(g, mat); p.frustumCulled = false; scene.add(p); return p;
}
const sprayPts = makePoints(SPRAY.length, 0.16, 0xf2fbff, 10);
const sprayPts2 = makePoints(SPRAY.length, 0.24, 0xbfe9f2, 11);
const FOAM_N = 900, CURT_N = 420;
const foamPts = makePoints(FOAM_N, 0.55, 0xf4fbff, 14);
const curtPts = makePoints(CURT_N, 0.3, 0xeaf8ff, 10);
function updateParticles(tau, xc) {
  const a1 = sprayPts.geometry.attributes.position.array, a2 = sprayPts2.geometry.attributes.position.array;
  for (let i = 0; i < SPRAY.length; i++) {
    const s = SPRAY[i], age = tau - s.te, arr = s.w ? a2 : a1;
    if (age >= 0 && age < s.life) {
      arr[i * 3] = s.p.x + s.v.x * age; arr[i * 3 + 1] = s.p.y + s.v.y * age - 4.9 * age * age; arr[i * 3 + 2] = s.p.z + s.v.z * age;
    } else { arr[i * 3 + 1] = -999; }
    (s.w ? a1 : a2)[i * 3 + 1] = -999;
  }
  sprayPts.geometry.attributes.position.needsUpdate = true; sprayPts2.geometry.attributes.position.needsUpdate = true;
  const fa = foamPts.geometry.attributes.position.array;
  for (let k = 0; k < FOAM_N; k++) {
    const off = -1.5 - hash(k * 1.31) * 60; const jf = 3 + hash(k * 2.7) * 22;
    const [z, y] = profilePoint(off, jf);
    fa[k * 3] = xc + off + 0.4 * Math.sin(tau * 2.1 + k);
    fa[k * 3 + 1] = y + 0.15 + 0.22 * Math.abs(Math.sin(tau * 3.3 + k * 1.7)) * (1 - waveParams(off).amp * 0 ) ;
    fa[k * 3 + 2] = z + (hash(k * 5.1) - 0.5) * 0.8;
  }
  foamPts.geometry.attributes.position.needsUpdate = true;
  const ca = curtPts.geometry.attributes.position.array;
  for (let k = 0; k < CURT_N; k++) {
    const ph = frac(hash(k * 7.7) + tau * (0.8 + 0.6 * hash(k * 1.9)));
    const off = -4.5 + hash(k * 2.3) * 5.5; const tt = ph * 0.85;
    const [z, y] = lipTipAt(off);
    ca[k * 3] = xc + off + (hash(k * 4.4) - 0.5) * 0.6;
    ca[k * 3 + 1] = y - 4.9 * tt * tt + (hash(k * 3.3) - 0.5) * 0.3;
    ca[k * 3 + 2] = z + 3.0 * tt + (hash(k * 8.1) - 0.5) * 0.5;
    if (ca[k * 3 + 1] < 0.1) ca[k * 3 + 1] = -999;
  }
  curtPts.geometry.attributes.position.needsUpdate = true;
}

// ---------------------------------------------------------------- linha do tempo
// tau = tempo da surfada; v = tempo do vídeo
const SCENES = [
  { id: 'intro',  v0: 0,    v1: 3.5,  tau: v => v },
  { id: 'p1',     v0: 3.5,  v1: 8.5,  tau: v => v },
  { id: 'p2',     v0: 8.5,  v1: 14.5, tau: v => 8.5 + (v - 8.5) * (2 / 6) },
  { id: 'p3',     v0: 14.5, v1: 18.5, tau: v => 10.5 + (v - 14.5) * 0.2 },
  { id: 'p4',     v0: 18.5, v1: 25.5, tau: v => v < 20.5 ? 11.3 + (v - 18.5) * 0.1 : v < 23.5 ? 11.5 : 11.5 + (v - 23.5) * 0.2 },
  { id: 'p5',     v0: 25.5, v1: 29.5, tau: v => 11.9 + (v - 25.5) * 0.5 },
  { id: 'replay', v0: 29.5, v1: 35.5, tau: v => 9.0 + (v - 29.5) },
  { id: 'outro',  v0: 35.5, v1: 42,   tau: v => 15 + (v - 35.5) },
];
const sceneAt = v => SCENES.find(s => v >= s.v0 && v < s.v1) || SCENES[SCENES.length - 1];

function camFor(sc, lv, tau, S) {
  const Ps = riderPosSmooth(tau, sc.id === 'p4' ? 0.02 : 0.12);
  const P = (x, y, z) => Ps.clone().add(V3(x, y, z));
  switch (sc.id) {
    case 'intro': {
      const k = easeInOut(lv / 3.5); const a = lerp(0.9, -0.78, k), r = lerp(26, 12.7, easeOut(lv / 3.5)), h = lerp(9, 1.8, k);
      return { pos: P(Math.sin(a) * r, h, Math.cos(a) * r), look: P(lerp(-4, 3, k), lerp(0.5, 1.4, k), -2), fov: 60 };
    }
    case 'p1': return lv < 2.5 ? { pos: P(-9 + lv * 0.35, 1.8, 9), look: P(3, 1.4, -2), fov: 60 }
                               : { pos: P(3.8 - (lv - 2.5) * 0.3, 1.0, 6.8), look: P(0.2, 1.4, -1), fov: 60 };
    case 'p2': return lv < 3 ? { pos: P(9 - lv * 0.3, 1.6, 9), look: P(-2, 1.2, -1.5), fov: 60 }
                             : { pos: P(5.2 - (lv - 3) * 0.2, 1.2, 7.4), look: P(-1.6, 1.4, -1.2), fov: 60 };
    case 'p3': return { pos: P(8, 1.3, 8 - lv * 0.25), look: P(-1, 1.6, -1), fov: 58 };
    case 'p4': {
      const C = torso.getWorldPosition(V3()).lerp(S.pos, 0.25);
      let a, r;
      if (lv < 2) { a = 0.78; r = lerp(8.5, 6.0, easeOut(lv / 2)); }
      else if (lv < 5) { a = lerp(0.78, -0.9, easeInOut((lv - 2) / 3)); r = 6.0; }
      else { a = lerp(-0.9, -0.65, easeOut((lv - 5) / 2)); r = lerp(6.0, 8.5, easeOut((lv - 5) / 2)); }
      return { pos: C.clone().add(V3(Math.sin(a) * r, 0.9, Math.cos(a) * r)), look: C.clone().add(V3(0, 1.1, 0)), fov: 58 };
    }
    case 'p5': return { pos: P(-8, 2.0, 8.5), look: P(3, 1.2, -2), fov: 60 };
    case 'replay': return lv < 1.5 ? { pos: P(12 - lv * 0.3, 1.6, 9), look: P(-1, 1.3, -1.5), fov: 50 }
                       : lv < 3.5 ? { pos: P(4.6, 1.3, 7.2), look: P(-0.6, 1.6, -1), fov: 56 }
                                  : { pos: P(2 - (lv - 3.5) * 0.6, 4.2, 16), look: P(-2, 1.0, -2), fov: 58 };
    case 'outro': return { pos: P(-3 - lv * 0.6, 9.5, 16), look: P(3, -1.5, -2), fov: 62 };
  }
}

// ---------------------------------------------------------------- overlays presos ao 3D
function project(p) { const v = p.clone().project(camera); return { x: (v.x * 0.5 + 0.5) * W, y: (-v.y * 0.5 + 0.5) * H, ok: v.z < 1 && v.z > -1 }; }
function reticle(p, lv) {
  const s = project(p); if (!s.ok) return;
  const r = 26 + 4 * Math.sin(lv * 8), a = lv * 2.2;
  ctx.save(); ctx.translate(s.x, s.y); ctx.rotate(a);
  for (let i = 0; i < 4; i++) {
    ctx.rotate(Math.PI / 2);
    ctx.fillStyle = '#000814'; ctx.fillRect(r - 3, -r - 3, 14, 6); ctx.fillRect(r + 5, -r - 3, 6, 14);
    ctx.fillStyle = '#ff3b2a'; ctx.fillRect(r - 1, -r - 1, 10, 3); ctx.fillRect(r + 6, -r - 1, 3, 10);
  }
  ctx.restore();
  ctx.fillStyle = '#ffd21f'; ctx.fillRect(s.x - 2, s.y - 2, 4, 4);
}
function pathPreview(tau0, tau1, lv) {
  const pts = [];
  for (let t = tau0; t <= tau1; t += 0.05) { const S = rideState(t); const s = project(S.pos.clone().addScaledVector(S.N, 0.05)); if (s.ok) pts.push(s); }
  ctx.save();
  for (let i = 0; i < pts.length; i++) {
    if ((i + Math.floor(lv * 10)) % 3 === 0) continue;
    const a = 1 - i / pts.length;
    ctx.fillStyle = `rgba(0,8,20,${0.7 * a})`; ctx.fillRect(pts[i].x - 4, pts[i].y - 4, 8, 8);
    ctx.fillStyle = `rgba(255,214,31,${a})`; ctx.fillRect(pts[i].x - 2.5, pts[i].y - 2.5, 5, 5);
  }
  ctx.restore();
}
// Só o que depende da projeção 3D fica no canvas; todo texto é HTML nas composições.
// Âncoras das legendas da pausa (espaço 540x960; o HTML usa o dobro).
const CALLOUTS = [
  { at: 2.1, x: 274, y: 380 },  // 1 OMBROS GIRAM  (borda direita da caixa)
  { at: 2.6, x: 290, y: 440 },  // 2 OLHAR NA BASE
  { at: 3.1, x: 242, y: 500 },  // 3 PÉ DE TRÁS
];
function leader(p, lx, ly, a) {
  const s = project(p); if (!s.ok || a <= 0) return;
  ctx.save(); ctx.globalAlpha = a;
  ctx.strokeStyle = '#000814'; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(lx, ly); ctx.stroke();
  ctx.strokeStyle = '#ffd21f'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(lx, ly); ctx.stroke();
  ctx.fillStyle = '#000814'; ctx.fillRect(s.x - 7, s.y - 7, 14, 14); ctx.fillStyle = '#ffd21f'; ctx.fillRect(s.x - 4, s.y - 4, 8, 8);
  ctx.restore();
}
function drawWorldOverlays(sc, lv, tau, S) {
  if ((sc.id === 'p2' && lv > 2.2) || sc.id === 'p3') {
    const ff = faceAt(7.75, 0.9); reticle(V3(S.xc + 7.75, ff.y, ff.z), sc.id === 'p3' ? lv + 3 : lv);
    pathPreview(tau + 0.04, 11.45, lv);
  }
  if (sc.id === 'p4' && lv > 2 && lv < 5.2) {
    const fade = 1 - smooth(4.9, 5.2, lv);
    const shoulders = shoulderR.getWorldPosition(V3()).add(shoulderL.getWorldPosition(V3())).multiplyScalar(0.5);
    const pts = [shoulders, S.pos.clone().addScaledVector(S.N, 1.25), footL.getWorldPosition(V3())];
    CALLOUTS.forEach((c, i) => leader(pts[i], c.x, c.y, clamp((lv - c.at) / 0.3, 0, 1) * fade));
  }
  if (sc.id === 'outro') { ctx.fillStyle = `rgba(0,6,24,${0.5 * clamp(lv / 0.5, 0, 1)})`; ctx.fillRect(0, 0, W, H); }
}

// ---------------------------------------------------------------- pós-processamento PS2
const scan = (() => { const c = document.createElement('canvas'); c.width = 4; c.height = 4; const g = c.getContext('2d'); g.fillStyle = 'rgba(0,0,0,0.10)'; g.fillRect(0, 1, 4, 1); g.fillRect(0, 3, 4, 1); return ctx.createPattern(c, 'repeat'); })();
const dither = (() => {
  const c = document.createElement('canvas'); c.width = 4; c.height = 4; const g = c.getContext('2d');
  const B = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
  for (let i = 0; i < 16; i++) { const v = B[i] / 15; g.fillStyle = `rgba(${v > 0.5 ? 255 : 0},${v > 0.5 ? 255 : 0},${v > 0.5 ? 255 : 0},${Math.abs(v - 0.5) * 0.14})`; g.fillRect(i % 4, i >> 2, 1, 1); }
  return ctx.createPattern(c, 'repeat');
})();
const vignette = (() => { const g = ctx.createRadialGradient(W / 2, H / 2, H * 0.3, W / 2, H / 2, H * 0.75); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,20,0.45)'); return g; })();

const CUTS = [3.5, 6.0, 8.5, 11.5, 14.5, 18.5, 25.5, 29.5, 31.0, 33.0, 35.5];
function drawFrame(v) {
  const sc = sceneAt(v), lv = v - sc.v0, tau = sc.tau(v);
  const S = rideState(tau);
  placeRider(S);
  updateParticles(tau, S.xc);
  wave.position.x = S.xc;
  waveTex.offset.set(S.xc * 0.11, -tau * 0.55);
  const cam = camFor(sc, lv, tau, S);
  camera.position.copy(cam.pos); camera.lookAt(cam.look); camera.fov = cam.fov; camera.updateProjectionMatrix();
  sea.position.x = camera.position.x; sea.position.z = camera.position.z;
  seaTex.offset.set(camera.position.x / 7 + tau * 0.02, -camera.position.z / 7 + tau * 0.05);
  renderer.render(scene, camera);

  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.filter = 'saturate(1.18) contrast(1.06)';
  ctx.drawImage(glCanvas, 0, 0, W, H);
  ctx.filter = 'blur(6px) brightness(1.05)';
  ctx.globalCompositeOperation = 'screen'; ctx.globalAlpha = 0.32;
  ctx.drawImage(glCanvas, 0, 0, W, H);
  ctx.restore();
  ctx.fillStyle = vignette; ctx.fillRect(0, 0, W, H);

  drawWorldOverlays(sc, lv, tau, S);

  ctx.fillStyle = dither; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = scan; ctx.fillRect(0, 0, W, H);
  // flash branco de 7 quadros em cada corte (nunca no quadro 0: ele é o gancho/thumbnail)
  let flash = 0;
  for (const c of CUTS) if (v >= c && v < c + 0.24) flash = Math.max(flash, 1 - (v - c) / 0.24);
  if (flash > 0) { ctx.fillStyle = `rgba(255,255,255,${flash * 0.9})`; ctx.fillRect(0, 0, W, H); }
  // flash extra no impacto da rasgada
  if (sc.id === 'p4') { const f = 1 - smooth(5.2, 5.45, lv); if (lv > 5.2 && f > 0) { ctx.fillStyle = `rgba(255,255,255,${f * 0.8})`; ctx.fillRect(0, 0, W, H); } }
}

return { renderAt: drawFrame, SCENES };
}
