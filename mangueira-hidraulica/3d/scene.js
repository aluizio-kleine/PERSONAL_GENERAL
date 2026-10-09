import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const SEG = 128;
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf4f5f7);
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.9;

// ---------- materials
const steel = new THREE.MeshStandardMaterial({ color: 0xcfd3d8, metalness: 1, roughness: 0.27, side: THREE.DoubleSide });
const steelBlock = new THREE.MeshStandardMaterial({ color: 0xbfc4ca, metalness: 1, roughness: 0.38 });
const steelFerrule = new THREE.MeshStandardMaterial({ color: 0xd6d9dd, metalness: 1, roughness: 0.22, side: THREE.DoubleSide });
const oringMat = new THREE.MeshStandardMaterial({ color: 0x141414, metalness: 0, roughness: 0.45 });
const holeMat = new THREE.MeshStandardMaterial({ color: 0x2a2c30, metalness: 0.6, roughness: 0.6 });

function hoseTexture() {
  const c = document.createElement('canvas'); c.width = 4096; c.height = 512;
  const g = c.getContext('2d');
  g.fillStyle = '#121212'; g.fillRect(0, 0, c.width, c.height);
  // fine wrap texture of the cover
  for (let i = 0; i < 9000; i++) {
    const v = 14 + Math.random() * 14;
    g.fillStyle = `rgb(${v},${v},${v})`;
    g.fillRect(Math.random() * c.width, Math.random() * c.height, 3 + Math.random() * 10, 2);
  }
  for (const yc of [128, 384]) {
    g.fillStyle = 'rgba(205,205,205,0.85)';
    g.font = 'bold 34px Arial';
    g.textBaseline = 'middle';
    let x = 20;
    while (x < c.width) { g.fillText('MANGUEIRA HIDRÁULICA  ▪  ALTA PRESSÃO  ▪', x, yc); x += 820; }
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 8;
  return t;
}
const hoseTex = hoseTexture();

// ---------- geometry helpers
// profile: array of [r, s]; split at sharp corners so edges stay crisp
function lathe(pts, modify) {
  const pieces = []; let cur = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    cur.push(pts[i]);
    if (i < pts.length - 1) {
      const a = [pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]];
      const b = [pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]];
      const ang = Math.acos(Math.max(-1, Math.min(1, (a[0] * b[0] + a[1] * b[1]) / (Math.hypot(...a) * Math.hypot(...b)))));
      if (ang > 0.4) { pieces.push(cur); cur = [pts[i]]; }
    }
  }
  pieces.push(cur);
  const geos = pieces.filter(p => p.length > 1).map(p => {
    const g = new THREE.LatheGeometry(p.map(q => new THREE.Vector2(q[0], q[1])), SEG);
    if (modify && modify(g)) {
      g.computeVertexNormals();
      const n = g.attributes.normal, np = p.length;
      for (let j = 0; j < np; j++) {
        const a = j, b = SEG * np + j;
        const v = new THREE.Vector3().fromBufferAttribute(n, a).add(new THREE.Vector3().fromBufferAttribute(n, b)).normalize();
        n.setXYZ(a, v.x, v.y, v.z); n.setXYZ(b, v.x, v.y, v.z);
      }
    }
    return g;
  });
  return mergeGeometries(geos);
}
function threadPts(rMin, rMaj, s0, s1, p, down) {
  const out = [];
  for (let s = s0; s < s1 - 1e-6; s += p) {
    out.push([rMin, s], [rMaj, s + 0.42 * p], [rMaj, s + 0.58 * p]);
  }
  out.push([rMin, s1]);
  return down ? out.reverse() : out;
}
function hexGeo(af, h, hole, y0) {
  const b = 0.9;
  const R = (af - 2 * b) / Math.sqrt(3);
  const sh = new THREE.Shape();
  for (let i = 0; i < 6; i++) {
    const a = Math.PI / 6 + i * Math.PI / 3;
    i ? sh.lineTo(R * Math.cos(a), R * Math.sin(a)) : sh.moveTo(R * Math.cos(a), R * Math.sin(a));
  }
  const hp = new THREE.Path(); hp.absarc(0, 0, hole + b, 0, Math.PI * 2, true); sh.holes.push(hp);
  const g = new THREE.ExtrudeGeometry(sh, { depth: h - 2 * b, bevelEnabled: true, bevelThickness: b, bevelSize: b, bevelSegments: 3, curveSegments: 64 });
  g.translate(0, 0, b); g.rotateX(-Math.PI / 2); g.translate(0, y0, 0);
  return g;
}
const mesh = (g, m) => { const o = new THREE.Mesh(g, m); o.castShadow = o.receiveShadow = true; return o; };

// crimped ferrule, s=0 at hose entry (back), s=L at front
function ferrule(rHose) {
  const L = 42, rO = rHose + 3.5;
  const pts = [[rO - 1.2, 0], [rO + 0.6, 1.2], [rO + 0.6, 4]];
  for (let s = 6; s <= 36; s += 1) pts.push([rO, s]);
  pts.push([rO + 0.6, 38], [rO + 0.6, L - 1], [rO - 0.4, L], [rHose - 1, L], [rHose + 0.3, 0.8], [rO - 1.2, 0]);
  const g = lathe(pts, geo => {
    const p = geo.attributes.position; let changed = false;
    for (let i = 0; i < p.count; i++) {
      const x = p.getX(i), y = p.getY(i), z = p.getZ(i), r = Math.hypot(x, z);
      if (y < 5.5 || y > 36.5 || r < rO - 0.2) continue;
      const th = Math.atan2(x, z), a = Math.PI / 4;
      const loc = ((th % a) + a) % a - a / 2;
      const w = Math.min(1, (y - 5.5) / 4, (36.5 - y) / 4);
      const rf = Math.min(r, (rO - 0.65) / Math.cos(loc));
      const rn = r + (rf - r) * w;
      p.setXYZ(i, x * rn / r, y, z * rn / r); changed = true;
    }
    return changed;
  });
  return mesh(g, steelFerrule);
}

// female DKO swivel (TB15 / 15L, M22x1,5). origin at hose entry, +Y towards the face
function femaleDKO(rHose) {
  const g = new THREE.Group();
  g.add(ferrule(rHose));
  // stem neck between ferrule and nut
  g.add(mesh(lathe([[9.6, 41.5], [9.6, 47], [8.8, 47]]), steel));
  // swivel nut SW27, y 46..66
  g.add(mesh(hexGeo(27, 20, 11, 46), steel));
  g.add(mesh(lathe([[11, 51], [9.6, 51], [9.6, 46.2]]), steel));
  g.add(mesh(lathe(threadPts(10.2, 11, 51, 66, 1.5, true)), steel));
  // sealing cone with O-ring
  const cone = [[9.5, 50.5], [9.5, 55], [10.0, 55], [10.0, 56.2], [8.6, 56.2], [8.6, 58], [10.0, 58], [9.3, 61.5], [8.1, 63.3], [5.0, 63.3], [5.0, 50.5]];
  g.add(mesh(lathe(cone), steel));
  const or = mesh(new THREE.TorusGeometry(9.15, 1.0, 24, 96), oringMat);
  or.rotation.x = Math.PI / 2; or.position.y = 57.1; g.add(or);
  // dark bore
  const bore = mesh(new THREE.CircleGeometry(5, 48), holeMat); bore.rotation.x = -Math.PI / 2; bore.position.y = 56; g.add(bore);
  return g;
}

// straight hose tail for block port: origin at hose entry, +Y towards block face (y=55)
function portTail(rHose) {
  const g = new THREE.Group();
  g.add(ferrule(rHose));
  g.add(mesh(lathe([[9.6, 41.5], [9.6, 45.5]]), steel));
  g.add(mesh(hexGeo(27, 9.5, 9.5, 45.5), steel));
  return g;
}

// male DKO TB22 (22L, M30x2) on block: origin at block face, +Y outward
function maleDKO() {
  const g = new THREE.Group();
  g.add(mesh(hexGeo(36, 18, 12, 0), steel));
  const pts = [[12.2, 18], [13.4, 18], [13.4, 21.5], [14.0, 21.5], ...threadPts(13.8, 15, 22, 42, 2, false).slice(1), [14.2, 43], [11.4, 43], [9.4, 43 - 2 / Math.tan(12 * Math.PI / 180)], [8.0, 33], [8.0, 18], [12.2, 18]];
  g.add(mesh(lathe(pts), steel));
  const bore = mesh(new THREE.CircleGeometry(8, 48), holeMat); bore.rotation.x = -Math.PI / 2; bore.position.y = 25; g.add(bore);
  return g;
}

// ---------- assembly (mm). X: flow direction, Y: up, Z: towards viewer
const RH = 9.75;              // hose OD/2 (DN10 typical)
const CY = 21;                // centre height of block / fittings
const BX = 22, BZ = 38;
const asm = new THREE.Group(); scene.add(asm);

const block = mesh(new RoundedBoxGeometry(BX * 2, CY * 2, BZ * 2, 4, 2.5), steelBlock);
block.position.set(0, CY, 0); asm.add(block);
for (const z of [-26, 26]) {
  const h = mesh(new THREE.CircleGeometry(4.2, 40), holeMat); h.rotation.x = -Math.PI / 2; h.position.set(0, CY * 2 + 0.05, z); asm.add(h);
}
const male = maleDKO(); male.rotation.z = Math.PI / 2; male.position.set(-BX, CY, 0); asm.add(male);

const PORT = 55, FEM = 66, HIDE = 8;
const named = {};
function branch(zSide, total, bendZ, bendX) {
  const tail = portTail(RH); tail.rotation.z = Math.PI / 2;
  const sx = BX + PORT; tail.position.set(sx, CY, zSide); asm.add(tail);
  const target = total - BX - PORT - FEM + 2 * HIDE;
  let d = 200, curve;
  for (let it = 0; it < 6; it++) {
    const endX = bendX + d;
    curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(sx - HIDE, CY, zSide),
      new THREE.Vector3(sx + 40, CY - 4, zSide + Math.sign(zSide) * 6),
      new THREE.Vector3(sx + 95, RH + 1, zSide + Math.sign(zSide) * 55),
      new THREE.Vector3(bendX, RH, bendZ),
      new THREE.Vector3(bendX + 0.5 * (endX - bendX), RH, bendZ),
      new THREE.Vector3(endX - 70, RH + 1, bendZ),
      new THREE.Vector3(endX, CY - 5, bendZ),
    ], false, 'centripetal');
    d += target - curve.getLength();
  }
  const tex = hoseTex.clone(); tex.needsUpdate = true; tex.repeat.set(curve.getLength() / 480, 1);
  const hm = new THREE.MeshPhysicalMaterial({ map: tex, roughness: 0.62, metalness: 0, clearcoat: 0.15, clearcoatRoughness: 0.5 });
  asm.add(mesh(new THREE.TubeGeometry(curve, 900, RH, 40, false), hm));
  const end = curve.getPoint(1), tan = curve.getTangent(1);
  const f = femaleDKO(RH);
  f.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tan);
  f.position.copy(end).addScaledVector(tan, -HIDE); asm.add(f);
  return { curve, tan, face: f.position.clone().addScaledVector(tan, FEM), femPos: f.position.clone().addScaledVector(tan, 40), mid: curve.getPoint(0.55) };
}
const A = branch(-18, 600, -150, 250);
const B = branch(18, 1500, 190, 330);
named.inlet = new THREE.Vector3(-BX - 43, CY, 0);
named.block = new THREE.Vector3(0, CY * 2, 0);
named.hoseA = A.mid; named.hoseB = B.mid; named.femA = A.femPos; named.femB = B.femPos;
named.faceA = A.face; named.faceB = B.face; named.center = new THREE.Vector3(0, CY, 0);

const ground = new THREE.Mesh(new THREE.PlaneGeometry(8000, 8000), new THREE.MeshStandardMaterial({ color: 0xf4f5f7, roughness: 1 }));
ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; scene.add(ground);

const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.castShadow = true; sun.shadow.mapSize.set(8192, 8192);
sun.shadow.bias = -0.0002; sun.shadow.normalBias = 0.4; sun.shadow.radius = 6;
scene.add(sun); scene.add(sun.target);
function setSun(tx, tz, span) {
  sun.position.set(tx - 250, 1400, tz + 500); sun.target.position.set(tx, 0, tz);
  const c = sun.shadow.camera; c.left = -span; c.right = span; c.top = span; c.bottom = -span; c.near = 100; c.far = 4000; c.updateProjectionMatrix();
}
scene.add(new THREE.HemisphereLight(0xffffff, 0xdddddd, 0.4));

function project(cam, w, h) {
  const out = {};
  for (const [k, v] of Object.entries(named)) {
    const p = v.clone().project(cam);
    out[k] = [(p.x + 1) / 2 * w, (1 - p.y) / 2 * h];
  }
  return out;
}

window.info = { lenA: A.curve.getLength(), lenB: B.curve.getLength(), faceA: A.face.toArray(), faceB: B.face.toArray() };
window.renderView = (v) => {
  renderer.setSize(v.w, v.h);
  let cam;
  if (v.ortho) {
    const [cx, cz, halfW] = v.ortho, halfH = halfW * v.h / v.w;
    cam = new THREE.OrthographicCamera(-halfW, halfW, halfH, -halfH, 1, 5000);
    cam.position.set(cx, 2000, cz); cam.up.set(0, 0, -1); cam.lookAt(cx, 0, cz);
  } else {
    cam = new THREE.PerspectiveCamera(v.fov, v.w / v.h, 5, 20000);
    if (v.face) {
      const br = v.face[0] === 'A' ? A : B;
      const t = br.face.clone().addScaledVector(br.tan, -v.face[4]);
      cam.position.copy(br.face).addScaledVector(br.tan, v.face[1]).add(new THREE.Vector3(0, v.face[2], v.face[3]));
      cam.lookAt(t);
    } else {
      cam.position.fromArray(v.pos); cam.lookAt(new THREE.Vector3().fromArray(v.target));
    }
  }
  setSun(...v.sun);
  renderer.render(scene, cam);
  return { png: renderer.domElement.toDataURL('image/png'), pts: project(cam, v.w, v.h) };
};
window.ready = true;
