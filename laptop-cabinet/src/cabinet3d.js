/* LC-60 cabinet 3D model. Needs THREE (r128) and, for interaction, THREE.OrbitControls.
 * Model coordinates: x width, y depth (0 = front), z height (0 = floor), inches.
 * Three coordinates: (x, z, -y)  so the front faces the default camera. */
(function () {
  function P(x, y, z) { return new THREE.Vector3(x, z, -y); }

  function create(container, data, opts) {
    opts = opts || {};
    const pal = Object.assign({
      bg: 0xfaf8f4, board: 0xe4ded2, boardEdge: 0x2d2a25, back: 0xd6cfbe, kick: 0x3a362f,
      laptop: 0x2f3338, laptopEdge: 0x15181c, door: 0xdde5ee, ghost: 0x8fa9c7, line: 0x1a1814,
    }, opts.palette || {});

    const W = data.W, D = data.D, H = data.H;
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: !!opts.preserve, alpha: false });
    renderer.setPixelRatio(opts.pixelRatio || Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(pal.bg, 1);
    container.appendChild(renderer.domElement);
    renderer.domElement.style.display = 'block';

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8170, 0.85));
    const key = new THREE.DirectionalLight(0xffffff, 0.55); key.position.set(-40, 90, 70); scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.25); fill.position.set(80, 30, 40); scene.add(fill);

    const center = P(W / 2, D / 2, H / 2);
    const ortho = !!opts.ortho;
    let camera;
    function makeCamera(w, h) {
      if (ortho) {
        const span = 46, a = w / h;
        camera = new THREE.OrthographicCamera(-span * a, span * a, span, -span, -500, 1000);
      } else {
        camera = new THREE.PerspectiveCamera(30, w / h, 1, 2000);
      }
    }
    const size = () => [container.clientWidth || 800, container.clientHeight || 500];
    makeCamera(...size());

    let controls = null;
    if (THREE.OrbitControls && opts.interactive !== false) {
      controls = new THREE.OrbitControls(camera, renderer.domElement);
      controls.target.copy(center);
      controls.enableDamping = true;
      controls.dampingFactor = 0.12;
      controls.minDistance = 40; controls.maxDistance = 400;
      controls.addEventListener('change', () => needs = true);
    }

    const root = new THREE.Group(); scene.add(root);
    const parts = [];   // {mesh, base:Vector3 offset 0, explode:Vector3}
    const stacks = new THREE.Group(); root.add(stacks);
    const doors = new THREE.Group(); root.add(doors);
    const lineMat = new THREE.LineBasicMaterial({ color: pal.line, transparent: true, opacity: 0.85 });

    function boxGeom(b) {
      const [x0, y0, z0, x1, y1, z1] = b;
      const g = new THREE.BoxGeometry(x1 - x0, z1 - z0, y1 - y0);
      g.translate((x0 + x1) / 2, (z0 + z1) / 2, -(y0 + y1) / 2);
      return g;
    }
    function profileGeom(inst) {
      const [x0, , , x1] = inst.box;
      const shape = new THREE.Shape();
      inst.profile.forEach(([y, z], i) => i ? shape.lineTo(-y, z) : shape.moveTo(-y, z));
      shape.closePath();
      const g = new THREE.ExtrudeGeometry(shape, { depth: x1 - x0, bevelEnabled: false });
      // local (s=-y, z, e) -> three (x0 + e, z, s)
      g.applyMatrix4(new THREE.Matrix4().set(0, 0, 1, x0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1));
      return g;
    }
    function addMesh(group, geom, color, edgeColor, extra) {
      const mat = new THREE.MeshLambertMaterial(Object.assign({ color, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }, extra || {}));
      const mesh = new THREE.Mesh(geom, mat);
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geom, 20),
        edgeColor === undefined ? lineMat : new THREE.LineBasicMaterial({ color: edgeColor }));
      const g = new THREE.Group(); g.add(mesh); g.add(edges); group.add(g);
      return g;
    }

    // explode offsets (model units)
    function explodeFor(inst) {
      const b = inst.box, zc = (b[2] + b[5]) / 2;
      const v = { x: 0, y: 0, z: zc * 0.6 };
      switch (inst.label) {
        case 'Top': v.z += 6; break;
        case 'Side L': v.x = -16; v.z = 0; break;
        case 'Side R': v.x = 16; v.z = 0; break;
        case 'Back': v.y = 18; v.z = 10; break;
        case 'Toe kick': v.y = -10; v.z = -1; break;
        case 'Rear rail': v.y = 9; v.z = -9; break;
      }
      return v;
    }

    data.instances.forEach(inst => {
      const geom = inst.profile ? profileGeom(inst) : boxGeom(inst.box);
      let color = pal.board;
      if (inst.mark === 'P08') color = pal.back;
      if (inst.mark === 'P06') color = pal.kick;
      const g = addMesh(root, geom, color);
      const e = explodeFor(inst);
      parts.push({ group: g, inst, explode: new THREE.Vector3(e.x, e.z, -e.y) });
    });

    // laptop stacks
    const lt = data.LAPTOP.t, gap = 0.08;
    data.stacks.forEach(s => {
      const [x0, y0, z0, x1, y1] = s.box;
      for (let i = 0; i < data.LAPTOP.stack; i++) {
        const zb = z0 + i * lt;
        addMesh(stacks, boxGeom([x0, y0, zb, x1, y1, zb + lt - gap]), pal.laptop, pal.laptopEdge);
      }
    });
    stacks.visible = false;

    // ALT-1 doors (phantom)
    (function () {
      const d = data.door, n = data.COLS;
      for (let i = 0; i < n; i++) {
        const x0 = i * (W / n) + d.gap / 2;
        addMesh(doors, boxGeom([x0, -d.t, data.BASE_H + d.gap / 2, x0 + d.w, 0, data.BASE_H + d.gap / 2 + d.h]),
          pal.door, pal.ghost, { transparent: true, opacity: 0.45 });
      }
    })();
    doors.visible = false;

    let explodeT = 0, explodeTarget = 0, needs = true;

    function setMode(m) {
      stacks.visible = (m === 'loaded');
      explodeTarget = (m === 'exploded') ? 1 : 0;
      if (opts.instant) { explodeT = explodeTarget; applyExplode(); }
      needs = true;
    }
    function setDoors(on) { doors.visible = !!on; needs = true; }
    function applyExplode() {
      parts.forEach(p => p.group.position.copy(p.explode).multiplyScalar(explodeT));
    }

    const VIEWS = {
      iso: [-1.05, 0.62, 1.15], front: [0, 0.02, 1], side: [-1, 0.02, 0.0001], rear: [0.9, 0.55, -1.1], top: [0, 1, 0.001],
      iso_r: [1.05, 0.62, 1.15],
    };
    function setView(name, dist) {
      const v = new THREE.Vector3(...(VIEWS[name] || VIEWS.iso)).normalize();
      const r = dist || opts.distance || 165;
      camera.position.copy(center).add(v.multiplyScalar(r));
      camera.up.set(0, 1, 0);
      camera.lookAt(center);
      if (ortho) { camera.zoom = opts.zoom || 1; camera.updateProjectionMatrix(); }
      if (controls) { controls.target.copy(center); controls.update(); }
      needs = true;
    }

    function resize() {
      const [w, h] = size();
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = w + 'px'; renderer.domElement.style.height = h + 'px';
      if (ortho) {
        const span = 46 , a = w / h;
        Object.assign(camera, { left: -span * a, right: span * a, top: span, bottom: -span });
      } else camera.aspect = w / h;
      camera.updateProjectionMatrix();
      needs = true;
    }

    // screen position of a model point (for callout labels)
    function project(x, y, z) {
      const v = P(x, y, z).project(camera);
      const [w, h] = size();
      return [(v.x + 1) / 2 * w, (1 - v.y) / 2 * h];
    }
    function partAnchor(label, f) {
      const p = parts.find(q => q.inst.label === label); if (!p) return null;
      const b = p.inst.box, e = p.explode.clone().multiplyScalar(explodeT);
      f = f || [0.5, 0.5, 0.5];
      const at = (i) => b[i] + (b[i + 3] - b[i]) * f[i];
      return project(at(0) + e.x, at(1) - e.z, at(2) + e.y);
    }

    function frame() {
      if (Math.abs(explodeT - explodeTarget) > 1e-3) {
        explodeT += (explodeTarget - explodeT) * 0.14; applyExplode(); needs = true;
        if (Math.abs(explodeT - explodeTarget) <= 1e-3) { explodeT = explodeTarget; applyExplode(); }
      }
      if (controls) controls.update();
      if (needs) { renderer.render(scene, camera); needs = false; }
      if (!opts.instant) requestAnimationFrame(frame);
    }
    function renderNow() { applyExplode(); renderer.render(scene, camera); }

    resize(); setView(opts.view || 'iso');
    if (window.ResizeObserver) new ResizeObserver(resize).observe(container);
    if (!opts.instant) requestAnimationFrame(frame);

    return { setMode, setView, setDoors, resize, project, partAnchor, renderNow, renderer, camera,
      setPalette(p) { Object.assign(pal, p); renderer.setClearColor(pal.bg, 1); needs = true; } };
  }

  window.Cabinet3D = { create };
})();
