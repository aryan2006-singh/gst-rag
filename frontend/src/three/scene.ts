/**
 * The 3D backdrop: iridescent glass rings orbiting a stack of frosted legal
 * sheets, with GST reference tags and a dust field around it. It sits in a
 * fixed canvas behind the page, so it shows through the hero and the
 * "How it works" section, and it drifts across the screen as you scroll and
 * leans toward the pointer.
 *
 * Loaded lazily (see Backdrop.tsx) so three.js never blocks the first paint.
 */
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

export interface SceneHandle {
  dispose: () => void;
}

interface Options {
  canvas: HTMLCanvasElement;
  reducedMotion: boolean;
  /** Elements whose visibility keeps the render loop running. */
  windows: () => HTMLElement[];
  /** Where the object should sit: 0 = hero (right), 1 = pipeline (left). */
  anchor: () => number;
}

const TAGS = ["§ 16(4)", "RULE 36", "NOTIF. 11/2017", "CIRC. 183", "SEC. 9", "GSTR-3B"];

function sheetTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 680;
  const g = c.getContext("2d")!;
  const grad = g.createLinearGradient(0, 0, 512, 680);
  grad.addColorStop(0, "#ffffff");
  grad.addColorStop(1, "#e9edf0");
  g.fillStyle = grad;
  g.fillRect(0, 0, 512, 680);
  g.fillStyle = "rgba(0,0,0,0.55)";
  g.font = "500 30px 'JetBrains Mono', monospace";
  g.fillText("CGST · 2017", 52, 92);
  g.fillStyle = "rgba(0,0,0,0.82)";
  g.font = "500 300px 'DM Sans', sans-serif";
  g.fillText("§", 44, 430);
  g.fillStyle = "rgba(0,0,0,0.14)";
  [0.86, 0.72, 0.56].forEach((w, i) => g.fillRect(52, 520 + i * 34, 408 * w, 12));
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

function tagSprite(label: string): THREE.Sprite {
  const c = document.createElement("canvas");
  const g = c.getContext("2d")!;
  const font = "500 44px 'JetBrains Mono', monospace";
  g.font = font;
  const w = Math.ceil(g.measureText(label).width) + 44;
  c.width = w;
  c.height = 84;
  g.font = font;
  g.strokeStyle = "rgba(255,255,255,0.9)";
  g.lineWidth = 3;
  g.strokeRect(2, 2, w - 4, 80);
  g.fillStyle = "rgba(255,255,255,0.95)";
  g.textBaseline = "middle";
  g.fillText(label, 22, 44);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  sprite.scale.set((w / 84) * 0.15, 0.15, 1);
  return sprite;
}

export function createScene({ canvas, reducedMotion, windows, anchor }: Options): SceneHandle {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environment = envTex;

  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  camera.position.set(0, 0, 11);

  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(4, 6, 5);
  scene.add(key, new THREE.AmbientLight(0xffffff, 0.35));

  // Outer group moves with scroll; inner group leans toward the pointer.
  const rig = new THREE.Group();
  const lean = new THREE.Group();
  rig.add(lean);
  scene.add(rig);

  // --- glass rings
  // Polished iridescent glass. Real transmission has nothing to refract
  // against a transparent canvas, so this fakes it with a mirror-like
  // finish plus thin-film colour, which reads as glass at this size.
  const glass = new THREE.MeshPhysicalMaterial({
    color: 0xdfe6ee,
    metalness: 0.92,
    roughness: 0.12,
    iridescence: 1,
    iridescenceIOR: 1.6,
    iridescenceThicknessRange: [220, 820],
    clearcoat: 1,
    clearcoatRoughness: 0.04,
    envMapIntensity: 1.6,
    transparent: true,
    opacity: 0.9,
  });
  const ringSpecs = [
    { r: 2.25, t: 0.1, tilt: new THREE.Euler(1.25, 0.2, 0), speed: [0.0, 0.0, 0.22] },
    { r: 1.9, t: 0.075, tilt: new THREE.Euler(0.3, 1.1, 0), speed: [0.0, 0.0, -0.17] },
    { r: 1.58, t: 0.06, tilt: new THREE.Euler(-0.6, -0.7, 0.4), speed: [0.0, 0.0, 0.13] },
  ];
  const rings = ringSpecs.map((spec) => {
    const holder = new THREE.Group();
    holder.rotation.copy(spec.tilt);
    const mesh = new THREE.Mesh(new THREE.TorusGeometry(spec.r, spec.t, 48, 220), glass);
    holder.add(mesh);
    lean.add(holder);
    return { mesh, speed: spec.speed };
  });

  // --- the stack of sheets
  const sheets = new THREE.Group();
  const sheetGeo = new RoundedBoxGeometry(1.35, 1.8, 0.05, 4, 0.04);
  const frosted = new THREE.MeshPhysicalMaterial({
    color: 0xffffff,
    roughness: 0.35,
    clearcoat: 0.6,
    transparent: true,
    opacity: 0.55,
    envMapIntensity: 1.1,
    depthWrite: false,
  });
  const back1 = new THREE.Mesh(sheetGeo, frosted);
  back1.position.set(-0.16, 0.06, -0.28);
  back1.rotation.z = 0.16;
  const back2 = new THREE.Mesh(sheetGeo, frosted);
  back2.position.set(0.1, -0.04, -0.14);
  back2.rotation.z = -0.07;
  const faceMat = new THREE.MeshPhysicalMaterial({
    map: sheetTexture(),
    roughness: 0.42,
    clearcoat: 0.8,
    clearcoatRoughness: 0.2,
  });
  const plain = new THREE.MeshPhysicalMaterial({ color: 0xf2f4f6, roughness: 0.4 });
  // RoundedBox groups: +x, -x, +y, -y, +z (front), -z
  const front = new THREE.Mesh(sheetGeo, [plain, plain, plain, plain, faceMat, plain]);
  sheets.add(back1, back2, front);
  sheets.rotation.set(0.05, -0.35, 0.02);
  lean.add(sheets);

  // --- tags orbiting on a tilted ring
  const tagOrbit = new THREE.Group();
  tagOrbit.rotation.x = 0.35;
  const tags = TAGS.map((label, i) => {
    const s = tagSprite(label);
    const a = (i / TAGS.length) * Math.PI * 2;
    s.position.set(Math.cos(a) * 2.9, Math.sin(a * 2) * 0.5, Math.sin(a) * 2.9);
    tagOrbit.add(s);
    return s;
  });
  lean.add(tagOrbit);

  // --- dust
  const dustCount = 420;
  const pos = new Float32Array(dustCount * 3);
  for (let i = 0; i < dustCount; i++) {
    const r = 2.6 + Math.random() * 2.8;
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
    pos[i * 3 + 1] = r * Math.cos(ph) * 0.7;
    pos[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th);
  }
  const dustGeo = new THREE.BufferGeometry();
  dustGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const dust = new THREE.Points(
    dustGeo,
    new THREE.PointsMaterial({ color: 0xffffff, size: 0.022, transparent: true, opacity: 0.75, depthWrite: false }),
  );
  lean.add(dust);

  // --- sizing and layout
  let mobile = false;
  function resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    mobile = w < 768;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener("resize", resize);

  // --- input
  const pointer = { x: 0, y: 0 };
  const onPointer = (e: PointerEvent) => {
    pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
    pointer.y = (e.clientY / window.innerHeight) * 2 - 1;
  };
  window.addEventListener("pointermove", onPointer, { passive: true });

  // --- run only while a window onto the scene is visible
  let visible = true;
  const visibleSet = new Set<Element>();
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => (e.isIntersecting ? visibleSet.add(e.target) : visibleSet.delete(e.target)));
    visible = visibleSet.size > 0;
    if (visible) kick();
  });
  windows().forEach((el) => io.observe(el));
  const onVis = () => kick();
  document.addEventListener("visibilitychange", onVis);

  const clock = new THREE.Clock();
  let raf = 0;
  let t = 0;
  const cur = { x: 0, y: 0, ry: 0, s: 1 };

  function frame() {
    raf = 0;
    const dt = Math.min(clock.getDelta(), 0.05);
    if (!reducedMotion) t += dt;

    const a = anchor(); // 0 hero .. 1 pipeline
    const span = mobile ? 0.7 : 2.35;
    const target = {
      x: THREE.MathUtils.lerp(span, -span, a),
      y: mobile ? THREE.MathUtils.lerp(-1.6, -1.0, a) : THREE.MathUtils.lerp(-0.15, -0.3, a),
      ry: a * Math.PI * 1.15,
      s: mobile ? 0.78 : 1,
    };
    const k = reducedMotion ? 1 : 1 - Math.pow(0.0015, dt);
    cur.x += (target.x - cur.x) * k;
    cur.y += (target.y - cur.y) * k;
    cur.ry += (target.ry - cur.ry) * k;
    cur.s += (target.s - cur.s) * k;
    rig.position.set(cur.x, cur.y, 0);
    rig.rotation.y = cur.ry;
    rig.scale.setScalar(cur.s);

    // Scrolling through the hero dollies the camera in, so the scene zooms toward you.
    const zoom = Math.min(window.scrollY / Math.max(window.innerHeight, 1), 1) || 0;
    const camZ = 11 - zoom * 4.5;
    camera.position.z += (camZ - camera.position.z) * k;

    const lk = reducedMotion ? 0 : 1 - Math.pow(0.02, dt);
    lean.rotation.y += (pointer.x * 0.35 - lean.rotation.y) * lk;
    lean.rotation.x += (pointer.y * 0.25 - lean.rotation.x) * lk;

    rings.forEach(({ mesh, speed }, i) => {
      mesh.rotation.z = t * speed[2] * 2;
      mesh.rotation.x = Math.sin(t * 0.3 + i) * 0.08;
    });
    sheets.position.y = Math.sin(t * 0.9) * 0.12;
    sheets.rotation.y = -0.35 + Math.sin(t * 0.45) * 0.22;
    tagOrbit.rotation.y = t * 0.12;
    tags.forEach((s, i) => (s.material.opacity = 0.75 + 0.25 * Math.sin(t * 0.8 + i)));
    dust.rotation.y = -t * 0.04;

    renderer.render(scene, camera);
    if (!reducedMotion && visible && !document.hidden) raf = requestAnimationFrame(frame);
  }

  function kick() {
    if (!raf && !document.hidden) {
      clock.getDelta();
      raf = requestAnimationFrame(frame);
    }
  }

  // Reduced motion: still follow scroll position, but render on demand.
  const onScroll = () => reducedMotion && kick();
  window.addEventListener("scroll", onScroll, { passive: true });
  kick();

  return {
    dispose() {
      cancelAnimationFrame(raf);
      io.disconnect();
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("scroll", onScroll);
      document.removeEventListener("visibilitychange", onVis);
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose?.();
        const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
        mats.forEach((mat) => {
          (mat as THREE.MeshPhysicalMaterial).map?.dispose();
          mat.dispose();
        });
      });
      envTex.dispose();
      pmrem.dispose();
      renderer.dispose();
    },
  };
}
