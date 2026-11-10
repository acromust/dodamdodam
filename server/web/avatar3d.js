// 캐릭터 3D(폰 웹 캐릭터 만들기·홈 작은 캐릭터·가입 완료 광장 그림). 차 앱 광장과 같은 모델·얼굴 그림을 쓴다(11/09).
// - 모델: /avatar/char.glb = 차 앱 assets/plaza_char2.glb 의 웹용 가벼운 사본(car-app/tools/char/web_char.py). 몸·가발 20·수염·안경·목도리·모프 같음(이어폰은 뺐다)
// - 얼굴: /avatar/face_atlas.png + .json(차 앱 assets 그대로)을 FaceSheet.kt 와 같은 규칙으로 합쳐 얼굴 조각(face) 텍스처로 끼운다
// - 부품 번호·색은 서버 /api/presets(server/avatar.py), 부품 → 노드·모프·키는 PlazaView.dress 와 같다
// three.js·모델은 이 파일이 처음 쓰일 때만 받는다(고정 버전). WebGL이 없거나 못 받으면 2D 얼굴 그림으로 대신한다.
// 렌더러는 하나만 만든다: 큰 미리보기·정지 그림·광장 그림이 같은 WebGL 화면에 그린 뒤 각자 2D 캔버스로 옮긴다.
const THREE_V = "0.160.0";
const ASSET_V = "1110w7c1";   // server/web/avatar/* 를 다시 만들면 올린다(서버가 30일 담아 두게 함)
const CDN = [
  { three: `https://cdn.jsdelivr.net/npm/three@${THREE_V}/+esm`, gltf: `https://cdn.jsdelivr.net/npm/three@${THREE_V}/examples/jsm/loaders/GLTFLoader.js/+esm` },
  { three: `https://esm.sh/three@${THREE_V}`, gltf: `https://esm.sh/three@${THREE_V}/examples/jsm/loaders/GLTFLoader.js` },
];
let T = null, G = null, loading = null, glb = null, viewRig = null, snapRig = null;

export function load() {
  if (!loading) loading = (async () => {
    const atlasP = loadAtlas();
    if (!hasGL()) { await atlasP; return false; }
    for (const c of CDN) {
      try { const [t, g] = await Promise.all([import(c.three), import(c.gltf)]); T = t; G = g; break; } catch (e) { T = G = null; }
    }
    if (!T) { await atlasP; return false; }
    try {
      const r = await fetch(`/avatar/char.glb?v=${ASSET_V}`);
      if (!r.ok) throw new Error(r.status);
      glb = await r.arrayBuffer();
      [snapRig, viewRig] = await Promise.all([parseRig(), parseRig()]);
    } catch (e) { snapRig = viewRig = null; }
    await atlasP;
    return !!snapRig;
  })();
  return loading;
}
export const ready = () => !!(T && snapRig);
function hasGL() { try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return false; } }

// ---------- 얼굴(2D): GPT 부품 그림 모음(face_atlas)을 칸에 붙인다. FaceSheet.kt 와 같은 순서·색 규칙 ----------
// 순서(json draw_order): 짧은 수염 → 볼터치 → 점 → 주름 → 코 → 입 → 눈 → 눈썹. 눈썹은 머리색, 수염은 수염색을 곱한다(회색 명암 × 색 / mean)
// 피부 맞춤(11/10): 주름·코는 피부보다 한 단 어둡게(tint skin), 볼터치는 분홍~장밋빛(tint pair), 눈썹·짧은 수염은 피부와 밝기 차가 sep 보다 작으면 어둡게.
// 식은 FaceSheet.kt paintOf · face_atlas.py compose() 와 같다. 주름 3(눈가+이마)은 json 에 두 층이 담겨 있다
let atlas = null, atlasP = null;
function loadAtlas() {
  if (!atlasP) atlasP = (async () => {
    try {
      const [j, img] = await Promise.all([
        fetch(`/avatar/face_atlas.json?v=${ASSET_V}`).then(r => r.ok ? r.json() : Promise.reject()),
        new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = `/avatar/face_atlas.png?v=${ASSET_V}`; })]);
      atlas = { j, img, tint: new Map() };
    } catch (e) { atlas = null; }
  })();
  return atlasP;
}
// 11/10 고르는 칸용 큰 아틀라스(얼굴 1024 기준, 무손실 WebP 약 1.6MB, 같은 층·같은 칸). 캐릭터 만들기 화면에서만 받는다(tileReady).
// 3D 얼굴(512 캔버스)·광장 그림은 지금 아틀라스 그대로. 못 받으면 칸도 지금 아틀라스로
let hd = null, hdP = null;
export function tileReady() {
  if (!hdP) hdP = (async () => {
    try {
      const [j, img] = await Promise.all([
        fetch(`/avatar/face_atlas_hd.json?v=${ASSET_V}`).then(r => r.ok ? r.json() : Promise.reject()),
        new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = `/avatar/face_atlas_hd.webp?v=${ASSET_V}`; })]);
      hd = { j, img, tint: new Map() };
    } catch (e) { hd = null; }
    return !!hd;
  })();
  return hdP;
}
const hexRgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
// 색을 곱한 부품 조각(조각 크기 캔버스). ColorMatrix(r × 색/(255·mean))와 같은 식, 알파는 그대로
function tinted(A, si, hex, mean) {
  const key = `${si}|${hex}|${mean}`;
  let c = A.tint.get(key);
  if (c) return c;
  const [x, y, w, h] = A.j.sprites[si].src;
  c = document.createElement("canvas"); c.width = w; c.height = h;
  const g = c.getContext("2d", { willReadFrequently: true });
  g.drawImage(A.img, x, y, w, h, 0, 0, w, h);
  const d = g.getImageData(0, 0, w, h), p = d.data, [cr, cg, cb] = hexRgb(hex), m = 1 / (255 * Math.max(mean, .05));
  for (let i = 0; i < p.length; i += 4) { p[i] = Math.min(255, p[i] * cr * m); p[i + 1] = Math.min(255, p[i + 1] * cg * m); p[i + 2] = Math.min(255, p[i + 2] * cb * m); }
  g.putImageData(d, 0, 0);
  if (A.tint.size > 64) A.tint.clear();
  A.tint.set(key, c);
  return c;
}
const luma = c => (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255;
const rnd = v => Math.min(255, Math.max(0, Math.floor(v + 0.5)));
const toHex = c => "#" + c.map(v => v.toString(16).padStart(2, "0")).join("");
// 층 하나에 곱할 색(#hex, 없으면 null)과 alpha. skin = 피부 [r,g,b], t = 0(짙은 피부)~1(밝은 피부)
function paintOf(L, a, cat, skin, t) {
  const al0 = L.alpha ?? 1, al = L.alpha_dark != null ? L.alpha_dark + (al0 - L.alpha_dark) * t : al0;
  let col = null;
  if (L.tint === "hair" || L.tint === "beard") {
    const c = hexRgb(L.tint === "hair" ? cat.hairColors[a.hairColor].hex : beardHex(a, cat)), lc = luma(c), ls = luma(skin);
    col = L.sep > 0 && Math.abs(lc - ls) < L.sep ? c.map(v => rnd(v * Math.max(ls - L.sep, .04) / Math.max(lc, 1e-3))) : c;
    if (L.shade) { const w = L.shade[1] + (L.shade[0] - L.shade[1]) * t; col = col.map((v, i) => rnd(v * (1 - w) + skin[i] * L.shade[2] * w)); }   // 11/10 짧은 수염: 짙은 피부일수록 피부 그늘색 쪽으로
  } else if (L.tint === "skin") {
    const k = L.k[1] + (L.k[0] - L.k[1]) * t; col = skin.map(v => rnd(v * k));
  } else if (L.tint === "pair") {
    const c0 = hexRgb(L.c[0]), c1 = hexRgb(L.c[1]); col = c1.map((v, i) => rnd(v + (c0[i] - v) * t));
  }
  return [col && toHex(col), Math.max(0, Math.min(1, al))];
}
const valOf = (a, k) => (k === "beards" ? beardsOf(a) : k === "marks" ? marksOf(a) : a[k]) || 0;
// opt.stub: 짧은 수염을 그만큼 진하게(수염 고르기 칸만, 79번 — 밝은 피부 칸에서 연함). opt.all: 같이 안 그리는 규칙(unless_eyes)을 끈다(주름 고르기 칸)
function faceSheet(cv, a, cat, bg, only, opt, A) {
  const S = cv.width, g = cv.getContext("2d"), J = A.j;
  g.save();
  g.clearRect(0, 0, S, S);
  if (bg) { g.fillStyle = bg; g.fillRect(0, 0, S, S); }
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
  const skin = hexRgb(cat.skins[a.skin].hex), st = J.skin_t || [.40, .89];   // 바탕(bg)이 없어도 부품 색은 이 사람 피부에 맞춘다
  const t = Math.max(0, Math.min(1, (luma(skin) - st[0]) / (st[1] - st[0])));
  for (const key of J.draw_order) {
    if (only && !only.includes(key)) continue;   // 고르기 타일: 그 부분만
    const opts = J.groups[key], layers = opts && opts[valOf(a, key)];
    if (!layers) continue;
    for (const L of layers) {
      if (L.unless_eyes && !(opt && opt.all) && L.unless_eyes.includes(a.eyes)) continue;   // 애교살 눈 + 눈 밑 선: 같은 자리라 눈 밑 선은 안 그림(79번)
      if (L.need && !Object.entries(L.need).every(([k, bit]) => valOf(a, k) & bit)) continue;   // 11/10: 그 칸 비트가 켜졌을 때만(짧은 수염 위 주름·주근깨 자리 비우기)
      const si = L.by_eyes && L.by_eyes[a.eyes] >= 0 ? L.by_eyes[a.eyes] : L.sprite;   // 11/10: 눈가 주름은 눈마다 자리가 다르다(그 눈 바깥 끝 옆)
      const s = J.sprites[si], [sx, sy, sw, sh] = s.src, [l, t, r, b] = s.dst;
      let [col, al] = paintOf(L, a, cat, skin, t);
      if ((key === "beard" || key === "beards") && opt && opt.stub && !L.need) { al = Math.min(1, al * opt.stub); if (col) col = toHex(hexRgb(col).map(v => rnd(v * .8))); }
      const src = col ? tinted(A, si, col, L.mean ?? 1) : null;
      g.globalAlpha = al;
      const draw = () => src ? g.drawImage(src, 0, 0, sw, sh, l * S, t * S, (r - l) * S, (b - t) * S)
        : g.drawImage(A.img, sx, sy, sw, sh, l * S, t * S, (r - l) * S, (b - t) * S);
      draw();
      if (L.mirror) { g.save(); g.translate(S, 0); g.scale(-1, 1); draw(); g.restore(); }   // 왼쪽만 담긴 부품: u 0.5 기준으로 오른쪽에 한 번 더
    }
  }
  g.restore();
}

// 얼굴 텍스처 한 장(cv 정사각). 부품 그림을 못 받았으면 예전 도형 그리기(FACE_SPEC)로
export function drawFace(cv, a, cat, bg, only, opt, A) {
  if (A || atlas) return faceSheet(cv, a, cat, bg, only, opt, A || atlas);
  return drawFaceSpec(cv, a, cat, bg);
}

// ---------- 예전 도형 얼굴(FACE_SPEC 좌표 그대로, 한 변 = 1.0). 부품 그림을 못 받았을 때만 ----------
function rgba(hex) {   // #RRGGBB 또는 #RRGGBBAA
  const h = hex.replace("#", ""), n = i => parseInt(h.slice(i, i + 2), 16);
  return [n(0), n(2), n(4), h.length >= 8 ? n(6) / 255 : 1];
}
const css = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a == null ? c[3] : a})`;
const rot = (tilt, s) => (-(tilt || 0) * s) * Math.PI / 180;
function drawFaceSpec(cv, a, cat, bg) {
  const S = cv.width, F = cat.face_spec, g = cv.getContext("2d");
  const ink = F.ink, hair = cat.hairColors[a.hairColor].hex;
  g.save();
  g.clearRect(0, 0, S, S);
  if (bg) { g.fillStyle = bg; g.fillRect(0, 0, S, S); }
  g.lineCap = "round"; g.lineJoin = "round";
  const X = v => v * S, sides = [-1, 1];
  if ((beardsOf(a) & 1) && F.beard && F.beard.stubble) {
    const b = F.beard.stubble, bc = rgba(beardHex(a, cat)), c = [bc[0], bc[1], bc[2], rgba(F.stubble)[3]];
    g.save(); g.translate(X(.5), X(b.y)); g.scale(1, b.h / b.w);
    const r = X(b.w / 2), gr = g.createRadialGradient(0, 0, r * .55, 0, 0, r);
    gr.addColorStop(0, css(c)); gr.addColorStop(1, css(c, 0));
    g.fillStyle = gr; g.beginPath(); g.arc(0, 0, r, 0, Math.PI * 2); g.fill(); g.restore();
  }
  if (a.blush) {
    const b = F.blush, c = rgba(typeof F.blushColor === "string" ? F.blushColor : "#F2969A66");
    for (const s of sides) {
      const x = X(.5 + s * b.dx), y = X(b.y), r = X(b.r), gr = g.createRadialGradient(x, y, 0, x, y, r);
      gr.addColorStop(0, css(c)); gr.addColorStop(1, css(c, 0));
      g.fillStyle = gr; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
    }
  }
  const n = F.nose.options[a.nose], ny = X(F.nose.y);
  g.fillStyle = css(rgba(ink), n.shape === "dot" ? .85 : .3);
  g.beginPath(); g.ellipse(X(.5), ny, X(n.w / 2), X(n.h / 2), 0, 0, Math.PI * 2); g.fill();
  const m = F.mouth.options[a.mouth], my = X(F.mouth.y);
  g.strokeStyle = ink; g.fillStyle = ink;
  if (m.shape === "smile") { g.lineWidth = X(m.stroke); g.beginPath(); g.ellipse(X(.5), my - X(m.h / 2), X(m.w / 2), X(m.h), 0, Math.PI * .1, Math.PI * .9); g.stroke(); }
  else if (m.shape === "line") { g.lineWidth = X(m.stroke); g.beginPath(); g.moveTo(X(.5 - m.w / 2), my); g.lineTo(X(.5 + m.w / 2), my); g.stroke(); }
  else { g.beginPath(); g.ellipse(X(.5), my, X(m.w / 2), X(m.h / 2), 0, 0, Math.PI * 2); g.fill(); }
  const e = F.eyes.options[a.eyes], ey = X(F.eyes.y);
  for (const s of sides) {
    g.save(); g.translate(X(.5 + s * F.eyes.dx), ey); g.fillStyle = ink; g.strokeStyle = ink;
    if (e.shape === "line" || e.shape === "arc_up") { g.lineWidth = X(e.stroke); g.beginPath(); g.moveTo(-X(e.w / 2), 0); g.lineTo(X(e.w / 2), 0); g.stroke(); }
    else { g.rotate(rot(e.tilt, s)); g.beginPath(); g.ellipse(0, 0, X(e.w / 2), X(e.h / 2), 0, 0, Math.PI * 2); g.fill(); }
    g.restore();
  }
  const b = F.brows.options[a.brows], by = X(F.brows.y);
  g.strokeStyle = hair;
  for (const s of sides) {
    g.save(); g.translate(X(.5 + s * F.brows.dx), by); g.rotate(rot(b.tilt, s)); g.lineWidth = X(b.stroke);
    g.beginPath(); g.moveTo(-X(b.w / 2), 0); g.quadraticCurveTo(0, -X(.014), X(b.w / 2), 0); g.stroke(); g.restore();
  }
  g.restore();
}

// 수염색(11/08 추가). 예전에 저장된 캐릭터는 칸이 없다: 긴 수염은 흰색, 나머지는 머리색
const beardIdx = a => Number.isInteger(a.beardColor) ? a.beardColor : a.beard === 3 ? 4 : a.hairColor;
// 11/10 수염·점 비트 칸(1 짧은 수염·2 콧수염·4 턱수염 / 점 1~64). 없던 값은 예전 한 칸(beard·mark)에서 같은 모습으로(server/avatar.py BEARD_OLD·MARK_OLD)
// 콧수염(2)·턱수염(4)은 둘 중 하나(턱수염 3D 에 콧수염이 붙어 있다): 둘 다 켜진 값은 턱수염만(server/avatar.py beards_fix)
const beardsRaw = a => Number.isInteger(a.beards) ? a.beards : [0, 1, 2, 4, 3][a.beard] || 0;
export const beardsOf = a => { const b = beardsRaw(a); return (b & 6) === 6 ? b & ~2 : b; };
export const marksOf = a => Number.isInteger(a.marks) ? a.marks : [0, 1, 4, 16, 64][a.mark] || 0;
const beardHex = (a, cat) => cat.hairColors[beardIdx(a)].hex;

// ---------- 3D: 차 앱 PlazaView.dress 와 같은 부품 규칙 ----------
// 옛 머리 번호(server/avatar.py hair) → 가발 노드. null = 민머리
const HAIR_NODES = ["hair_m_dandy", "hair_m_gareu", "hair_m_spiky", "hair_m_bald", null, "hair_w_long", "hair_w_pony", "hair_w_pigtail",
  "hair_w_wave", "hair_w_bun", "hair_m_bowl", "hair_w_bob", "hair_w_grancut", "hair_w_perm", "hair_m_ez", "hair_m_man50", "hair_m_allback",
  "hair_m_twoblock", "hair_w_ccurl", "hair_w_wavecut", "hair_m_buzz"];   // 11/10 17 투블럭·18 C컬 중단발·19 웨이브 커트
const GLASSES = [null, "glasses_round", "glasses_square", "glasses_half"];
const HEIGHT = [.86, 1, 1.12];
// 체형 [build_slim, build_chubby]: 0 날씬·1 보통·2 듬직·3 조금 날씬·4 조금 듬직. 얼굴형 [face_slim, face_square, face_full]: 0 둥근·1 갸름·2 각진·3 조금 갸름·4 조금 각진
// · 5 넓은 얼굴·6 넓고 각진(85번: 볼·턱이 넓고 턱 밑이 어깨로 이어지는 얼굴, 뒤에만 붙임)
// 11/10 콧수염(beard_mus) 자리(사장: 넓고 각진 + 짧은 수염 + 콧수염이면 입이 거의 안 보임). 원인: 콧수염 3D 아래 끝(가운데 y 1.152, 옆 1.12)이
// 입 선(웃는 입 가운데 1.114~1.138, 입꼬리 1.16~1.17)과 겹치고 얼굴보다 3 cm 앞에 떠 있어, 어느 얼굴형이든 입꼬리·웃는 선 윗부분을 덮었다
// (넓은 얼굴은 입이 옆으로 넓어져 더 많이 덮임). → 콧수염 윗가운데(코 밑)를 기준으로 세로 MUS_S[1]·가로 MUS_S[0]·앞뒤 MUS_S[2]로 줄여
// 아래 끝을 입꼬리 높이까지 올린다. 넓은 얼굴(5·6)은 입이 넓어 가로를 조금 더(MUS_WIDE). 메시 좌표(머리 뼈 자식 노드 기준). 차 PlazaView MUS_* 와 같은 값
const MUS_PIVOT = [0, 1.21, 0.30], MUS_S = [0.92, 0.72, 0.8], MUS_WIDE = 0.96;
const BUILD_W = [[1, 0], [0, 0], [0, 1], [.5, 0], [0, .5]], FACE_W = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [.5, 0, 0], [0, .5, 0], [0, 0, 1], [0, .7, 1]];   // 키는 뿌리 균일 크기(불균일이면 가발이 찌그러짐). 체형·얼굴형은 모프
const C_IDLE = "Short_Breathe_and_Look_Around", C_SIT = "Chair_Sit_Idle_F";
const still = () => { try { return matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) { return false; } };

function parseRig() {
  return new Promise((ok, no) => new G.GLTFLoader().parse(glb, "", g => ok(new Rig(g)), no));
}

class Rig {
  constructor(gltf) {
    const root = gltf.scene;
    this.wrap = new T.Group();   // 키(균일 크기)·좌우 돌리기는 여기에
    this.wrap.add(root);
    this.n = {};
    this.morph = []; this.body = [];
    root.traverse(o => {
      if (o.name && !this.n[o.name]) this.n[o.name] = o;
      if (o.isMesh) {
        o.frustumCulled = false;   // 뼈로 움직이는 몸은 쉬는 자세 상자로 잘릴 수 있다
        if (o.morphTargetDictionary) this.morph.push(o);
        if (o.material && ["skin", "top", "pants"].includes(o.material.name)) this.body.push(o);
      }
    });
    this.head = root.getObjectByName("mixamorigHead");
    this.hips = root.getObjectByName("mixamorigHips");
    // 얼굴 조각: 사람마다 그림을 바꿔 끼운다(glTF UV라 flipY 끔)
    this.faceMesh = this.n.face;
    this.faceCv = document.createElement("canvas"); this.faceCv.width = this.faceCv.height = 512;
    this.faceTex = new T.CanvasTexture(this.faceCv);
    this.faceTex.flipY = false; this.faceTex.colorSpace = T.SRGBColorSpace; this.faceTex.anisotropy = 4;
    if (this.faceMesh) { const m = this.faceMesh.material.clone(); if (m.map) m.map.dispose(); m.map = this.faceTex; this.faceMesh.material = m; }
    const sh = new T.Mesh(new T.CircleGeometry(.34, 32), new T.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: .07, depthWrite: false }));
    sh.rotation.x = -Math.PI / 2; sh.position.y = .002; this.shadow = sh; this.wrap.add(sh);
    this.mixer = new T.AnimationMixer(root);
    this.clips = {}; for (const c of gltf.animations) this.clips[c.name] = c;
    this.act = null; this.clip = null;
    this.faceKey = "";
    for (const h of [...HAIR_NODES, "beard_mus", "beard_long"]) if (h && this.n[h] && this.n[h].material) saltable(this.n[h]);
    const mu = this.n.beard_mus; if (mu) { mu.updateMatrix(); this.mus0 = mu.matrix.clone(); this.musFace = -1; }
  }
  show(name, on) { const o = this.n[name]; if (o) o.visible = on; }
  dress(a, colorHex, cat, faceOpt) {
    const hair = HAIR_NODES[a.hair] || null;
    for (const h of HAIR_NODES) if (h) this.show(h, h === hair);
    const bd = beardsOf(a);
    this.show("beard_mus", !!(bd & 2));    // 콧수염(짧은 수염은 얼굴 그림에)
    this.show("beard_long", !!(bd & 4));   // 턱수염(예전 긴 수염)
    if (this.mus0 && this.musFace !== a.face) {   // 콧수염 줄여 올리기(MUS_S): 머리 뼈 기준 원래 자리 × (기준점 둘레 크기)
      this.musFace = a.face;
      const [px, py, pz] = MUS_PIVOT, w = a.face === 5 || a.face === 6 ? MUS_WIDE : 1;
      const adj = new T.Matrix4().makeTranslation(px, py, pz).multiply(new T.Matrix4().makeScale(MUS_S[0] * w, MUS_S[1], MUS_S[2])).multiply(new T.Matrix4().makeTranslation(-px, -py, -pz));
      const mu = this.n.beard_mus; this.mus0.clone().multiply(adj).decompose(mu.position, mu.quaternion, mu.scale);
    }
    for (const g of GLASSES) if (g) this.show(g, g === GLASSES[a.glasses]);
    this.show("scarf", a.acc === 1);          // 소품: 1 목도리(이어폰은 뺐다)
    // 색: 몸은 skin·top·pants 재질(신발은 파일 기본색), 가발은 머리색, 수염은 수염색
    // 83번: 바지 색(pantsColor)·안경테 색(glassesColor). 예전 기록·예전 서버 값에 없으면 0(예전 바지·테 색)
    const skin = cat.skins[a.skin].hex, pick = (list, i) => (list && (list[Number.isInteger(i) ? i : 0] || list[0]) || {}).hex;
    const pants = pick(cat.pantsColors, a.pantsColor);
    for (const o of this.body) {
      const n = o.material.name;
      if (n === "pants") { if (pants) o.material.color.set(pants); }
      else o.material.color.set(n === "skin" ? skin : colorHex);
    }
    const gl = this.n[GLASSES[a.glasses]], glc = pick(cat.glassesColors, a.glassesColor);
    if (gl && gl.material && glc) gl.material.color.set(glc);   // 안경 셋은 한 재질(glasses)을 같이 쓴다
    const hcol = cat.hairColors[a.hairColor], bcol = cat.hairColors[beardIdx(a)] || hcol;
    for (const h of HAIR_NODES) if (h && this.n[h]) paintHair(this.n[h].material, hcol);
    for (const b of ["beard_mus", "beard_long"]) if (this.n[b]) paintHair(this.n[b].material, bcol);
    // 목도리 색(대표색 8가지, 윗옷과 따로 고른다): 회색 무늬 × 색. 예전 기록에 없으면 1 분홍(server/avatar.py SCARF_DEFAULT)
    if (a.acc === 1 && this.n.scarf) this.n.scarf.material.color.set(cat.colors[Number.isInteger(a.scarfColor) ? a.scarfColor : 1].hex);
    // 모프: 체형·얼굴형 5단계(83번: 뒤에 붙인 3·4는 형태 중간값 0.5). BUILD_W·FACE_W 는 차 PlazaView 와 같은 값
    const [bs, bc] = BUILD_W[a.build] || BUILD_W[1], [fs, fq, ff] = FACE_W[a.face] || FACE_W[0];
    const w = { build_slim: bs, build_chubby: bc, face_slim: fs, face_square: fq, face_full: ff };
    for (const o of this.morph) for (const [k, i] of Object.entries(o.morphTargetDictionary)) o.morphTargetInfluences[i] = w[k] || 0;
    this.wrap.scale.setScalar(HEIGHT[a.height] || 1);
    // 얼굴 그림(512): 바뀐 것만 다시
    const fk = JSON.stringify([a.eyes, a.brows, a.nose, a.mouth, a.wrinkle, a.blush, marksOf(a), beardsOf(a), a.hairColor, beardIdx(a), a.skin, !!atlas, faceOpt || null]);
    if (fk !== this.faceKey) {
      this.faceKey = fk;
      drawFace(this.faceCv, a, cat, skin, null, faceOpt);
      this.faceTex.needsUpdate = true;
    }
  }
  // 동작 하나를 t초 자리로(멈춘 그림) 또는 돌리기 시작
  pose(name, t) {
    const c = this.clips[name] || this.clips[C_IDLE];
    if (this.clip !== c) {
      this.mixer.stopAllAction();
      this.act = this.mixer.clipAction(c); this.act.play(); this.clip = c;
    }
    if (t != null) this.mixer.setTime(t);
    this.wrap.updateMatrixWorld(true);
  }
  // 머리 가운데(월드, 지금 자세·키 기준). 얼굴 조각 상자 가운데 = 머리 가운데 앞
  headCenter() {
    this.wrap.updateMatrixWorld(true);
    const v = new T.Vector3();
    if (this.faceMesh) { new T.Box3().setFromObject(this.faceMesh).getCenter(v); v.z = this.wrap.position.z; v.x = this.wrap.position.x; }
    else if (this.head) this.head.getWorldPosition(v);
    return v;
  }
}

// 희끗한 머리(11/10, 77번 다시): 새치는 관자놀이·귀밑·뒷머리부터 나고 멀리서는 그 자리가 밝은 회색으로 읽힌다(흰 가닥 줄은 11/10 사용자 요청으로 뺌).
// 머리 기준 좌표로 옆머리(귀 위~귀밑)·이마 양옆 모서리(정면에서 보이는 관자놀이)·뒷머리 아래만 부드럽게 밝히고 정수리는 짙게 둔다.
// 빛 반사처럼 보이지 않게 밝은 쪽은 찬 회색(server/avatar.py HAIR_SALT), 자리는 조명이 아니라 머리 자리로 정한다.
// 가발 UV는 조각조각이라 무늬는 쉬는 자세 좌표(position, 가발 17개·수염이 같은 좌표계)로 그린다.
// 재질마다 uniform 을 따로 두어 색만 바꿀 때 셰이더를 다시 만들지 않는다. salt 가 없는 색은 예전처럼 한 색(uSalt 0)
function saltable(mesh) {
  const m = mesh.material;
  const u = m.userData.salt = { uSalt: { value: 0 }, uSaltDark: { value: new T.Color() }, uSaltLight: { value: new T.Color() }, uSaltAmt: { value: .3 } };
  m.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, u);
    sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vSaltP;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvSaltP = position;");
    sh.fragmentShader = sh.fragmentShader.replace("#include <common>", `#include <common>
varying vec3 vSaltP;
uniform float uSalt; uniform vec3 uSaltDark, uSaltLight;`)
      .replace("#include <map_fragment>", `#include <map_fragment>
if (uSalt > .5) {
  vec3 q = (vSaltP - vec3(0., 1.42, -.06)) / .47;   // 머리 가운데·반지름(char.glb 쉬는 자세)
  float ax = abs(q.x);
  float side = smoothstep(.55, .9, ax) * smoothstep(.7, .15, q.y);                                 // 옆머리(귀 위~귀밑)
  float corner = smoothstep(.38, .72, ax) * smoothstep(.05, .45, q.z) * smoothstep(.75, .25, q.y);  // 이마 양옆 모서리(관자놀이)
  float nape = smoothstep(-.35, -.85, q.z) * smoothstep(.15, -.5, q.y);                            // 뒷머리 아래
  float w = clamp(.12 + .55 * max(side, corner) + .32 * nape, 0., .8);
  diffuseColor.rgb *= mix(uSaltDark, uSaltLight, w);
}`);
  };
  m.customProgramCacheKey = () => "salt3";
  m.needsUpdate = true;
}
// 머리·수염 색 한 가지 칠하기. salt 가 있으면 재질 색은 흰색(무늬가 색을 정한다)
function paintHair(m, col) {
  const u = m.userData.salt, s = col.salt;
  if (u && s) {
    m.color.set(0xffffff);
    u.uSalt.value = 1; u.uSaltDark.value.set(s[0]); u.uSaltLight.value.set(s[1]); u.uSaltAmt.value = s[2];
  } else {
    m.color.set(col.hex);
    if (u) u.uSalt.value = 0;
  }
}

function lights(scene) {
  scene.add(new T.HemisphereLight(0xffffff, 0xd9dce2, 2.3));
  const d = new T.DirectionalLight(0xffffff, 1.15); d.position.set(1.5, 3, 5); scene.add(d);
  const f = new T.DirectionalLight(0xffffff, .45); f.position.set(-3, 2, -4); scene.add(f);
}

// ---------- 렌더러 하나: 그릴 칸(w×h)을 WebGL 화면 왼쪽 위에 그리고 2D 캔버스로 옮긴다 ----------
let R = null;
function renderer() {
  if (!R) {
    R = new T.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true, powerPreference: "low-power" });
    R.setPixelRatio(1); R.setScissorTest(true);
    R.W = 0; R.H = 0;
  }
  return R;
}
// 장면을 w×h(기기 픽셀)로 그린다. 끝나면 R.domElement 의 (0,0,w,h)에 그림이 있다
function render(scene, cam, w, h, bg) {
  const r = renderer();
  if (w > r.W || h > r.H) { r.W = Math.max(w, r.W); r.H = Math.max(h, r.H); r.setSize(r.W, r.H, false); }
  r.setViewport(0, r.H - h, w, h); r.setScissor(0, r.H - h, w, h);
  if (bg) r.setClearColor(bg, 1); else r.setClearColor(0x000000, 0);
  cam.aspect = w / h; cam.updateProjectionMatrix();
  r.render(scene, cam);
}
const copyTo = (g, w, h) => { g.clearRect(0, 0, w, h); g.drawImage(R.domElement, 0, 0, w, h, 0, 0, w, h); };

// ---------- 카메라 ----------
const FOV = 28, TAN = Math.tan(FOV / 2 * Math.PI / 180);
// cy: 화면 가운데 높이, vis: 세로로 보이는 높이(m) → 카메라를 그만큼 뒤로
function frameCam(cam, cy, vis, aspect) {
  const d = (aspect < 1 ? vis / aspect : vis) / 2 / TAN;
  cam.position.set(0, cy + .04, d); cam.lookAt(0, cy, 0);
}
// 큰 미리보기: body(몸 전체, 키 차이가 보이게 고정) · head(머리·안경·수염: 머리 쪽으로 당김) · face(눈·눈썹·입·코·주름·볼터치: 얼굴만 크게)
const BODY_CY = 1.04, BODY_VIS = 2.4;
const FRAME = { body: () => ({ cy: BODY_CY, vis: BODY_VIS }), head: hc => ({ cy: hc.y - .05, vis: 1.75 }), face: hc => ({ cy: hc.y - .07, vis: 1.2 }) };

// 손가락으로 좌우만 돌려 보는 큰 미리보기. 서 있는 동작(Short_Breathe_and_Look_Around)을 돈다(움직임 줄이기 설정이면 멈춘 자세).
// 화면에서 안 보이면(캔버스 폭 0·탭 숨김) 멈춘다. 초당 30장까지만
// 부품을 바꿔도(11/10) 동작은 이어서 돌고, 카메라는 움직이지 않는다: 머리·얼굴 자리는 지금 움직이는 머리가 아니라
// 서 있는 동작 0초 자세의 머리 가운데(키 1 기준 높이 × 지금 키)로 잡는다. 키·체형·얼굴형은 0.25초 동안 바뀐다(움직임 줄이기면 바로)
const MORPH_S = .25;
const ease = k => k * k * (3 - 2 * k);
// 모프 값 전부(메시 차례대로 한 줄로)
const morphs = r => r.morph.flatMap(o => Array.from(o.morphTargetInfluences));
function tween(r, tw) {
  const e = ease(tw.k);
  r.wrap.scale.setScalar(tw.s0 + (tw.s1 - tw.s0) * e);
  let j = 0;
  for (const o of r.morph) { const f = o.morphTargetInfluences; for (let i = 0; i < f.length; i++, j++) f[i] = tw.m0[j] + (tw.m1[j] - tw.m0[j]) * e; }
}
// 서 있는 동작 0초 자세의 머리 가운데 높이(키 1). 뼈대마다 한 번만 재고, 이미 도는 동작은 건드리지 않는다
function headY(r) {
  if (r.hy0 == null) {
    if (r.clip) r.hy0 = 1.3;   // (여기 오기 전에 이미 돌고 있으면 0초로 되감지 않는다)
    else {
      const s = r.wrap.scale.x, ry = r.wrap.rotation.y;
      r.wrap.scale.setScalar(1); r.wrap.rotation.y = 0;
      r.pose(C_IDLE, 0);
      r.hy0 = r.headCenter().y;
      r.wrap.scale.setScalar(s); r.wrap.rotation.y = ry; r.wrap.updateMatrixWorld(true);
    }
  }
  return r.hy0;
}
export class View {
  constructor(canvas, cat) {
    if (!viewRig) throw new Error("no model");
    this.cv = canvas; this.cat = cat; this.ry = 0; this.rig = viewRig; this.on = false;
    this.g = canvas.getContext("2d");
    this.mode = "body"; this.k = 1; this.from = null; this.cur = null; this.last = 0; this.dirty = true; this.t0 = 0;
    this.tw = null; this.shown = 0;   // tw: 키·모프가 옮겨 가는 중 { k, s0, s1, m0, m1 }, shown: 마지막으로 그린 때
    this.scene = new T.Scene(); lights(this.scene); this.scene.add(this.rig.wrap);
    this.cam = new T.PerspectiveCamera(FOV, 1, .1, 50);
    this.hy = headY(this.rig);
    this.hc = new T.Vector3(0, this.hy, 0);
    let x0 = null;
    canvas.addEventListener("pointerdown", e => { x0 = e.clientX; try { canvas.setPointerCapture(e.pointerId); } catch (er) {} });
    canvas.addEventListener("pointermove", e => { if (x0 == null) return; this.ry += (e.clientX - x0) * .012; x0 = e.clientX; this.draw(); });
    const up = () => { x0 = null; };
    canvas.addEventListener("pointerup", up); canvas.addEventListener("pointercancel", up);
    document.addEventListener("visibilitychange", () => this.draw());
  }
  set(a, colorHex) {
    const r = this.rig, s0 = r.wrap.scale.x, m0 = morphs(r);
    r.dress(a, colorHex, this.cat);   // 머리·안경·수염 보이기, 색, 얼굴 그림은 제자리에서 바로 바뀐다
    if (!r.clip) r.pose(C_IDLE, 0);   // 처음 한 번만. 도는 동작은 처음부터 다시 하지 않는다
    const s1 = r.wrap.scale.x, m1 = morphs(r);
    // 키·체형·얼굴형: 바뀐 것이 있을 때만 지금 모습에서 새 모습으로 옮겨 간다. 화면에 막 들어왔으면(다른 사람·처음 열기) 바로
    const fresh = !this.has || performance.now() - this.shown > 400 || still();
    const same = (s, m, t, n) => Math.abs(s - t) < 1e-4 && m.every((v, i) => Math.abs(v - n[i]) < 1e-4);
    if (fresh) this.tw = null;                                          // dress 가 둔 새 모습 그대로
    else if (this.tw && same(this.tw.s1, this.tw.m1, s1, m1)) tween(r, this.tw);   // 옮겨 가던 곳이 같으면(머리·색만 바꿈) 그대로 이어서
    else if (!same(s0, m0, s1, m1)) { this.tw = { k: 0, s0, s1, m0, m1 }; tween(r, this.tw); }   // 지금 보이는 모습에서 출발
    else this.tw = null;
    r.wrap.updateMatrixWorld(true);
    this.has = true;
    this.draw();
  }
  resize() {
    const w = this.cv.clientWidth, h = this.cv.clientHeight;
    if (!w || !h) return;
    const dpr = Math.min(devicePixelRatio || 1, 2), W = Math.round(w * dpr), H = Math.round(h * dpr);
    if (W !== this.cv.width || H !== this.cv.height) { this.cv.width = W; this.cv.height = H; }
    this.draw();
  }
  // "body" · "head" · "face". 지금 보이는 자리에서 새 자리로 0.3초 동안 옮겨 간다(움직임 줄이기 설정이면 바로)
  setMode(m) {
    if (!FRAME[m] || m === this.mode) return;
    this.mode = m; this.last = 0;
    this.from = this.cur ? { ...this.cur } : null;
    this.k = still() || !this.from ? 1 : 0;
    this.draw();
  }
  draw() { this.dirty = true; if (!this.on) { this.on = true; this.prev = 0; requestAnimationFrame(t => this.tick(t)); } }
  tick(now) {
    const vis = this.has && this.cv.isConnected && this.cv.clientWidth > 0 && !document.hidden;
    const moving = !still();
    if (!vis) { this.on = false; return; }
    if (this.prev && now - this.prev < 30 && this.k >= 1 && !this.dirty) { requestAnimationFrame(t => this.tick(t)); return; }
    const dt = this.prev ? Math.min(.1, (now - this.prev) / 1000) : 0;
    this.prev = now;
    if (this.k < 1) this.k = still() ? 1 : Math.min(1, this.k + dt / .3);
    if (this.tw) { this.tw.k = still() ? 1 : Math.min(1, this.tw.k + dt / MORPH_S); tween(this.rig, this.tw); if (this.tw.k >= 1) this.tw = null; }
    if (moving) this.rig.mixer.update(dt);
    this.hc.set(0, this.hy * this.rig.wrap.scale.x, 0);   // 머리 자리는 키만 따라간다(숨 쉬고 둘러보는 머리 움직임은 카메라에 넣지 않는다)
    const e = ease(this.k), B = FRAME[this.mode](this.hc), A = this.from || B;
    const cy = A.cy + (B.cy - A.cy) * e, vs = A.vis + (B.vis - A.vis) * e;
    this.cur = { cy, vis: vs };
    const W = this.cv.width, H = this.cv.height;
    frameCam(this.cam, cy, vs, W / H);
    this.rig.wrap.rotation.y = this.ry;
    this.rig.wrap.position.set(0, 0, 0);
    if (this.rig.wrap.parent !== this.scene) this.scene.add(this.rig.wrap);
    render(this.scene, this.cam, W, H);
    copyTo(this.g, W, H);
    this.dirty = false; this.shown = performance.now();
    if (moving || this.k < 1 || this.tw) requestAnimationFrame(t => this.tick(t)); else this.on = false;
  }
  turn(v) { this.ry = v; this.draw(); }
}

// ---------- 정지 그림(PNG data URL): 서 있는 자세 0초 ----------
let snapScene = null, snapCam = null;
function snapSetup() {
  if (!snapScene) { snapScene = new T.Scene(); lights(snapScene); snapCam = new T.PerspectiveCamera(FOV, 1, .1, 50); }
  if (snapRig.wrap.parent !== snapScene) snapScene.add(snapRig.wrap);
  snapRig.wrap.position.set(0, 0, 0); snapRig.wrap.rotation.set(0, 0, 0);
}
function toUrl(w, h) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  copyTo(c.getContext("2d"), w, h);
  return c.toDataURL("image/png");
}
// frame: true(어깨 위, 기본) · "head"(머리만 크게) · "body"(몸 전체, 같은 카메라라 키 차이가 보인다)
// · "bust"(닮은 모습 고르기 칸, 11/10: 얼굴과 어깨. 키와 상관없이 얼굴 크기가 같게 키만큼 당긴다)
const BUST = [.05, 1.42];   // [머리 가운데에서 내려 잡을 높이, 세로로 보이는 높이](키 1 기준)
// opt(고르기 칸만): yaw = 몸을 돌려 비스듬히(라디안), face = 얼굴 그림 옵션(drawFace opt)
// · ss = 몇 배로 크게 그려 줄일지(11/10 닮은 모습 칸: 눈·안경 선이 계단지지 않게 2배로 그려 반씩 줄임, 한 변 2048까지)
export function snap(a, colorHex, cat, size, frame, opt) {
  size = size || 256;
  if (!ready()) return snap2d(a, colorHex, cat, size);
  snapSetup();
  snapRig.shadow.visible = true;
  snapRig.dress(a, colorHex, cat, opt && opt.face);
  snapRig.pose(C_IDLE, 0);
  if (opt && opt.yaw) { snapRig.wrap.rotation.set(0, opt.yaw, 0); snapRig.wrap.updateMatrixWorld(true); }
  const f = frame == null ? true : frame;
  if (f === "body") frameCam(snapCam, BODY_CY, BODY_VIS, 1);
  else {
    const hc = snapRig.headCenter(), k = snapRig.wrap.scale.x || 1;
    if (f === "head") frameCam(snapCam, hc.y + .06, 1.2, 1);
    else if (f === "headwide") frameCam(snapCam, hc.y - .02, 1.5, 1);   // 얼굴형 칸(79번): 카메라를 조금 빼서 턱선까지
    else if (f === "bust") frameCam(snapCam, hc.y - BUST[0] * k, BUST[1] * k, 1);
    else frameCam(snapCam, hc.y - .08, 1.5, 1);
  }
  const ss = opt && opt.ss > 1 ? Math.max(1, Math.min(opt.ss, 2048 / size)) : 1, S = Math.round(size * ss);
  render(snapScene, snapCam, S, S);
  return S > size ? shrinkUrl(S, S, size, size) : toUrl(size, size);
}
// three.js를 못 쓸 때: 얼굴 그림을 동그랗게 잘라 머리색 테두리만
export function snap2d(a, colorHex, cat, size) {
  const cv = document.createElement("canvas"); cv.width = cv.height = size || 256;
  const S = cv.width, g = cv.getContext("2d"), f = document.createElement("canvas");
  f.width = f.height = 512; drawFace(f, a, cat, cat.skins[a.skin].hex);
  g.fillStyle = colorHex; g.beginPath(); g.ellipse(S / 2, S * 1.02, S * .36, S * .22, 0, 0, Math.PI * 2); g.fill();
  if (a.hair !== 4) { g.fillStyle = cat.hairColors[a.hairColor].hex; g.beginPath(); g.arc(S / 2, S * .44, S * .36, 0, Math.PI * 2); g.fill(); }
  g.save(); g.beginPath(); g.arc(S / 2, S * .48, S * .31, 0, Math.PI * 2); g.clip();
  g.drawImage(f, 512 * .14, 512 * .2, 512 * .72, 512 * .72, S * .19, S * .17, S * .62, S * .62); g.restore();
  return cv.toDataURL("image/png");
}

// ---------- 고르기 타일 그림: 지금 내 캐릭터에 그 부품만 바꿔 입힌 그림 ----------
// 얼굴 그림 부품(눈·눈썹·입·코·주름·볼터치)은 얼굴 그림에서 그 부분만 잘라 2D로. [x, y, 폭, 높이](얼굴 한 변 = 1, face_atlas 칸 범위 기준).
// 눈·눈썹·볼터치는 두 쪽이 다 들어가게 가로 2:1(그림도 2:1), 코·입은 정사각. only: 그 부분만 그린다(눈썹 칸에 눈이 겹쳐 보이지 않게). 주름·볼터치는 얼굴째
// 나머지는 3D(머리·안경·수염·얼굴형은 머리, 키·체형은 몸 전체, 소품은 어깨 위)
const CROP = { eyes: [.04, .328, .92, .46, ["eyes"]], brows: [.04, .125, .92, .46, ["brows"]], nose: [.33, .496, .34, .34, ["nose"]], mouth: [.332, .632, .34, .34, ["mouth"]],
  wrinkle: [.05, .1, .9, .9], blush: [.02, .4, .96, .48],
  // 점(11/10): 눈 아래 ~ 입 아래를 가로 2:1로, 얼굴째 그려서(눈·코·입이 보여야 점 자리를 안다) 칸마다 같은 자리
  marks: [.04, .44, .92, .46] };
// 11/10 눈가(1)는 눈가 주름이 눈마다 눈 바깥 끝 옆(얼굴 그림 가장자리 가까이)으로 옮겨져 가로를 거의 끝까지
// 주름은 켜고 끄는 칸마다 그 선이 있는 자리만 가로 2:1로 크게(1 눈가·2 이마·4 입가·8 눈 밑, face_atlas 칸 자리 기준). 합친 값은 얼굴째(CROP.wrinkle)
const WR_CROP = { 1: [.01, .34, .98, .49], 2: [.04, .06, .92, .46], 4: [.04, .53, .92, .46], 8: [.04, .45, .92, .46] };
// 79번: 얼굴형은 조금 빼서(턱선), 옆머리(머리 3)는 비스듬히(민머리와 칸에서 구별), 짧은 수염(1)은 칸에서만 한 단 진하게
const FRAME_OF = { height: "body", build: "body", acc: true, face: "headwide" };
const HAIR_YAW = { 3: .62 }, STUB_TILE = 1.45;
let tileFace = null;
// size = 칸 그림 한 변(기기 픽셀), h = 칸 높이(기기 픽셀, 없으면 size). 11/10 사장 '옵션 선택 이미지도 해상도 좀 올려 줘':
// 예전엔 160px 한 장을 칸(390 폭 DPR3 에서 330px)에 늘려 흐렸다 → 칸 × 화면 배율 그대로 그린다.
// · 얼굴 그림 칸(눈·눈썹·코·입·주름·볼터치·점): 얼굴 캔버스를 칸 크기에 맞춰 부품 그림(face_atlas, 얼굴 한 변 512)에서 한 번에 그린다.
//   부품 그림보다 크게는 안 늘린다(코·입 칸은 얼굴 1024 기준 348px 까지, 큰 아틀라스를 못 받았으면 512 기준 174px) — 늘린 그림은 더 선명해지지 않고 무겁기만 하다
// · 3D 칸: 2배로 그려 반씩 줄인다(snap ss, 닮은 모습 칸과 같은 방식)
export function tile(a, colorHex, cat, part, size, h) {
  size = size || 160; h = h || size;
  const c = part === "wrinkle" && WR_CROP[a.wrinkle] || CROP[part];
  if (c) {
    const A = hd || atlas, FS = A ? A.j.face_size || 512 : 2048;   // 큰 아틀라스(1024)가 있으면 그것으로. 부품 그림이 없으면(도형 얼굴) 선 그림이라 원하는 만큼
    const w = Math.max(1, Math.min(Math.round(Math.max(size, h * c[2] / c[3])), Math.round(FS * c[2])));
    const S = Math.round(w / c[2]);
    if (!tileFace) tileFace = document.createElement("canvas");
    if (tileFace.width !== S) tileFace.width = tileFace.height = S;
    drawFace(tileFace, a, cat, cat.skins[a.skin].hex, c[4], part === "wrinkle" ? { all: true } : null, A);
    const cv = document.createElement("canvas"); cv.width = w; cv.height = Math.max(1, Math.round(w * c[3] / c[2]));
    cv.getContext("2d").drawImage(tileFace, c[0] * S, c[1] * S, cv.width, cv.height, 0, 0, cv.width, cv.height);   // 1:1 로 잘라 내기만
    return cv.toDataURL("image/png");
  }
  const opt = Object.assign({ ss: 2 }, part === "hair" && HAIR_YAW[a.hair] ? { yaw: HAIR_YAW[a.hair] } : part === "beards" && (beardsOf(a) & 1) ? { face: { stub: STUB_TILE } } : null);
  return snap(a, colorHex, cat, Math.max(size, h), FRAME_OF[part] != null ? FRAME_OF[part] : "head", opt);
}

// ---------- 광장 그림(가입 완료 화면 W5): 차 앱 광장과 같은 장면·카메라·빛 ----------
// 장면: /avatar/plaza.glb = 차 앱 assets/plaza_scene.glb 의 맑은 낮 모습만 남긴 가벼운 사본(car-app/tools/web_plaza.py, 새는 가지 끝에 굳힘).
// 쿠션 자리 1~5(make_plaza_glb.py cushion_pos): 앉은 사람은 대표색 쿠션에, 다음 초대 자리 하나만 회색 + '+', 그 뒤 빈자리는 안 보인다(PlazaView.stageColors).
// 사람: 차와 같은 모델·앉은 동작(Chair_Sit_Idle_F 0초), 뿌리 자리·높이는 PlazaView 의 빈백 표(SEAT_D·Y_CHAIR), 다리는 앞으로 뻗어 쿠션 위에(aimBone 같은 식).
// 사람마다 같은 렌더러 화면에 겹쳐 그린다(깊이는 남겨 두어 쿠션·나무에 맞게 가려짐). 장면 파일은 이 그림이 필요한 화면에서만 받는다.
// 장면을 아직 못 받았으면 예전 도형 광장(plazaShotLite)으로 대신한다. three.js가 없으면 null
const PLAZA_V = "1109p";   // server/web/avatar/plaza.glb 를 다시 만들면 올린다
const P_EYE = [0, 5.4, 11.2], P_LOOK = [0, .9, .2], P_FOV = 34;   // PlazaView EYE·LOOK. 세로 시야는 차(가로 화면 36°)보다 조금 좁혀 4:3 칸에 받침판이 꽉 차게
const P_TARGET_Z = 6, SEAT_D = [.15, .09, .12], Y_CHAIR = [.225, .193, .171];   // PlazaView 와 같은 값(키 작음·보통·큼)
const LEG = [[.12, -.05, 1], [.10, -.30, 1], [.05, .75, .66]];   // 허벅지·정강이·발 방향(몸 기준 +X 왼쪽, 오른다리는 X 반대). PlazaView LEG_*
const LEG_BONES = [["LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase"], ["RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"]];
const HEAD_LIMIT = .12;   // 앉은 사람 고개 숙임 한도(라디안): 얼굴이 보이게
const INVITE_HEX = "#B9BCC2";
let plazaP = null, plaza = null;
// 장면 파일을 받아 둔다(여러 번 불러도 한 번). 받으면 true
export function plazaReady() {
  if (!plazaP) plazaP = (async () => {
    if (!(await load())) return false;
    try {
      const r = await fetch(`/avatar/plaza.glb?v=${PLAZA_V}`);
      if (!r.ok) throw new Error(r.status);
      const buf = await r.arrayBuffer();
      const g = await new Promise((ok, no) => new G.GLTFLoader().parse(buf, "", ok, no));
      plaza = buildPlaza(g.scene);
      return true;
    } catch (e) { plazaP = null; return false; }
  })();
  return plazaP;
}
// 초대장 첫 화면에서 이 파일을 불렀으면(가입하러 온 사람) 장면도 미리 받아 둔다
try { const h = document.getElementById("s-hello"); if (h && !h.hidden) setTimeout(plazaReady, 0); } catch (e) {}

function buildPlaza(root) {
  const scene = new T.Scene();
  // 빛: PlazaView 맑은 낮(해 2.3·보조 0.9·둘레 0.32, 그림자 없음, 색 보정 없음). three 는 둘레빛을 π로 나누므로 π를 곱한다
  scene.add(new T.AmbientLight(0xffffff, .32 * Math.PI));
  const sun = new T.DirectionalLight(0xffffff, 2.3); sun.position.set(.35, 1, .55); scene.add(sun);
  const fill = new T.DirectionalLight(0xffffff, .9); fill.position.set(-.6, .4, .7); scene.add(fill);
  scene.add(root);
  const slots = [];
  for (let s = 1; s <= 5; s++) {
    const c = root.getObjectByName(`cushion${s}`);
    if (!c) continue;
    let m = null; c.traverse(o => { if (o.isMesh) m = o.material; });
    const x = c.position.x, z = c.position.z;
    slots[s] = { x, z, yaw: Math.atan2(0 - x, P_TARGET_Z - z), cushion: c, mat: m,
      plus: root.getObjectByName(`plus${s}`), shadow: root.getObjectByName(`cshadow${s}`) };
  }
  // 받침판·잔디처럼 비스듬히 보이는 면의 그림이 뭉개지지 않게 이방성 거르기를 최대로(기기 한도, 보통 16)
  const aniso = renderer().capabilities.getMaxAnisotropy();
  root.traverse(o => {
    if (!o.isMesh) return;
    o.frustumCulled = false;
    for (const m of [].concat(o.material)) if (m && m.map) { m.map.anisotropy = aniso; m.map.needsUpdate = true; }
  });
  const pplScene = new T.Scene();
  pplScene.add(new T.AmbientLight(0xffffff, .32 * Math.PI));
  pplScene.add(sun.clone()); pplScene.add(fill.clone());
  return { scene, slots, pplScene, cam: new T.PerspectiveCamera(P_FOV, 4 / 3, .1, 60) };
}

// 뼈 bone 을 제자리에서 돌려 자식 관절 쪽이 몸 기준 방향 d 를 보게(PlazaView.aimBone, 무게 1)
const _v = () => new T.Vector3();
function setWorld(o, M) {
  const L = new T.Matrix4().copy(o.parent.matrixWorld).invert().multiply(M);
  L.decompose(o.position, o.quaternion, o.scale);
  o.updateMatrixWorld(true);
}
function aimBone(bone, child, d, yaw) {
  if (!bone || !child) return;
  const bp = _v().setFromMatrixPosition(bone.matrixWorld), cp = _v().setFromMatrixPosition(child.matrixWorld);
  const ax = cp.sub(bp); if (ax.lengthSq() < 1e-12) return; ax.normalize();
  const t = _v().set(d[0], d[1], d[2]).normalize().applyAxisAngle(_v().set(0, 1, 0), yaw);
  const R = new T.Matrix4().makeRotationFromQuaternion(new T.Quaternion().setFromUnitVectors(ax, t));
  const M = R.multiply(bone.matrixWorld); M.setPosition(bp);
  setWorld(bone, M);
}
// 얼굴 앞 방향(머리 뼈 기준): 쉬는 자세에서 몸 앞 +Z 로 가는 축 = 묶음 행렬 회전의 셋째 줄
const headFwd = new WeakMap();
function faceFwd(rig) {
  if (headFwd.has(rig)) return headFwd.get(rig);
  let f = new T.Vector3(0, 0, 1);
  rig.wrap.traverse(o => {
    if (!o.isSkinnedMesh || !rig.head) return;
    const i = o.skeleton.bones.indexOf(rig.head);
    if (i < 0) return;
    const e = new T.Matrix4().copy(o.skeleton.boneInverses[i]).invert().elements;
    f = new T.Vector3(e[2], e[6], e[10]).normalize();
  });
  headFwd.set(rig, f);
  return f;
}
function seatPerson(rig, a, hex, cat, seat) {
  rig.dress(a, hex, cat);
  rig.pose(C_SIT, 0);
  const hi = Math.max(0, Math.min(2, a.height | 0)), yaw = seat.yaw, d = SEAT_D[hi];
  const wrap = rig.wrap;
  wrap.position.set(seat.x + Math.sin(yaw) * d, Y_CHAIR[hi], seat.z + Math.cos(yaw) * d);
  wrap.rotation.set(0, yaw, 0); wrap.scale.setScalar(HEIGHT[hi]);
  wrap.updateMatrixWorld(true);
  LEG_BONES.forEach((b, k) => {
    const sx = k === 0 ? 1 : -1, n = b.map(x => rig.n[`mixamorig${x}`]);
    for (let i = 0; i < 3; i++) aimBone(n[i], n[i + 1], [LEG[i][0] * sx, LEG[i][1], LEG[i][2]], yaw);
  });
  // 고개 숙임 한도: 넘는 만큼 몸 오른쪽 축으로 들어 올림(PlazaView.worldRot)
  const hd = rig.head;
  if (hd) {
    const f = faceFwd(rig).clone().transformDirection(hd.matrixWorld);
    const down = Math.atan2(-f.y, Math.hypot(f.x, f.z));
    if (down > HEAD_LIMIT) {
      const p = _v().setFromMatrixPosition(hd.matrixWorld);
      const r = new T.Matrix4().makeRotationY(yaw).multiply(new T.Matrix4().makeRotationX(-(down - HEAD_LIMIT))).multiply(new T.Matrix4().makeRotationY(-yaw));
      const M = r.multiply(hd.matrixWorld); M.setPosition(p);
      setWorld(hd, M);
    }
  }
}

// 광장 그림 한 장. people: [{slot 1~5, hex, a(캐릭터, 없으면 쿠션 색만)}]. 비어 있는 첫 자리는 회색 + '+'. 흰 바탕 PNG data URL
// ss: 몇 배 크게 그린 뒤 줄일지(가장자리·얼굴 선이 매끈하게). 기본은 2배, 그리는 칸이 약 400만 화소·기기 한도를 넘지 않게 낮춘다
const SS_PIXELS = 4.2e6;
export function plazaPicture(people, cat, w, h, ss) {
  if (!ready() || !plaza) return null;
  w = w || 960; h = h || 720;
  const r0 = renderer(), gl = r0.getContext();
  const maxDim = Math.min(gl.getParameter(gl.MAX_RENDERBUFFER_SIZE), ...gl.getParameter(gl.MAX_VIEWPORT_DIMS));
  ss = Math.max(1, Math.min(ss || Math.min(2, Math.sqrt(SS_PIXELS / (w * h))), maxDim / w, maxDim / h));
  const W = Math.round(w * ss), H = Math.round(h * ss), keepW = r0.W, keepH = r0.H;
  const P = plaza, by = {};
  for (const p of people) if (P.slots[p.slot]) by[p.slot] = p;
  let invite = 0;
  for (let s = 1; s <= 5; s++) if (P.slots[s] && !by[s]) { invite = s; break; }
  for (let s = 1; s <= 5; s++) {
    const S = P.slots[s]; if (!S) continue;
    const on = !!by[s] || s === invite;
    S.cushion.visible = on; if (S.shadow) S.shadow.visible = on; if (S.plus) S.plus.visible = s === invite;
    if (S.mat) S.mat.color.set(by[s] ? by[s].hex : INVITE_HEX);
  }
  const cam = P.cam;
  cam.position.set(P_EYE[0], P_EYE[1], P_EYE[2]); cam.lookAt(P_LOOK[0], P_LOOK[1], P_LOOK[2]);
  render(P.scene, cam, W, H, 0xffffff);
  // 사람: 앉힌 뒤 같은 화면에 겹쳐 그린다(지우지 않음)
  const wrap = snapRig.wrap, old = wrap.parent;
  P.pplScene.add(wrap);
  snapRig.shadow.visible = false;
  const r = renderer();
  r.autoClear = false;
  try {
    for (const p of people) {
      if (!p.a || !P.slots[p.slot]) continue;
      seatPerson(snapRig, p.a, p.hex, cat, P.slots[p.slot]);
      r.render(P.pplScene, cam);
    }
  } finally { r.autoClear = true; }
  const url = W === w && H === h ? toUrl(w, h) : shrinkUrl(W, H, w, h);
  P.pplScene.remove(wrap); if (old) old.add(wrap);
  wrap.position.set(0, 0, 0); wrap.rotation.set(0, 0, 0); wrap.scale.setScalar(1); snapRig.shadow.visible = true;
  // 크게 그리느라 늘린 WebGL 화면은 원래 크기로 돌려 메모리를 돌려준다(다른 그림은 다시 필요한 만큼 늘린다)
  if (r.W > Math.max(keepW, w) || r.H > Math.max(keepH, h)) { r.W = Math.max(keepW, w); r.H = Math.max(keepH, h); r.setSize(r.W, r.H, false); }
  return url;
}
// R 의 (0,0,W,H) 그림을 w×h 로: 반씩 줄여 가다가(한 번에 많이 줄이면 거칠어진다) 마지막에 딱 맞춘다. 흰 바탕 PNG data URL
function shrinkUrl(W, H, w, h) {
  let src = R.domElement, cw = W, ch = H;
  const step = (nw, nh) => {
    const c = document.createElement("canvas"); c.width = nw; c.height = nh;
    const g = c.getContext("2d"); g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
    g.drawImage(src, 0, 0, cw, ch, 0, 0, nw, nh);
    src = c; cw = nw; ch = nh;
  };
  while (cw / 2 >= w && ch / 2 >= h) step(Math.round(cw / 2), Math.round(ch / 2));
  if (cw !== w || ch !== h || src === R.domElement) step(w, h);
  return src.toDataURL("image/png");
}

// 가입 완료 화면: 같은 차 다른 가족(others: 대표색만)은 앞자리부터 색 쿠션, 나는 그다음 자리에 앉는다(서버가 왼쪽 빈자리부터 주는 것과 같은 순서)
export function plazaShot(a, myHex, others, cat, w, h) {
  if (!ready()) return null;
  if (!plaza) { plazaReady(); return plazaShotLite(a, myHex, others, cat, w, h); }
  const ppl = others.slice(0, 4).map((hex, i) => ({ slot: i + 1, hex }));
  ppl.push({ slot: ppl.length + 1, hex: myHex, a });
  return plazaPicture(ppl, cat, w, h);
}

// ---------- 장면 파일이 없을 때의 예전 도형 광장: 흰 원형 받침판 + 둥근 나무 + 쿠션 ----------
function mat(color) { return new T.MeshStandardMaterial({ color, roughness: .82, metalness: 0 }); }
function mesh(geo, m, p, s) {
  const o = new T.Mesh(geo, m);
  if (p) o.position.set(p[0], p[1], p[2]);
  if (s) o.scale.set(s[0], s[1], s[2]);
  return o;
}
function plazaShotLite(a, myHex, others, cat, w, h) {
  if (!ready()) return null;
  w = w || 960; h = h || 720;
  const scene = new T.Scene(); lights(scene);
  const top = .34, ball = (r, m, p, s) => mesh(new T.SphereGeometry(r, 32, 20), m, p, s);
  scene.add(mesh(new T.CylinderGeometry(3.15, 3.15, .2, 72), mat("#E6E5E1"), [0, .1, 0]));
  scene.add(mesh(new T.CylinderGeometry(3.02, 3.1, .14, 72), mat("#F4F3F0"), [0, .27, 0]));
  scene.add(mesh(new T.CylinderGeometry(.72, .72, .02, 48), mat("#EBDDC4"), [0, top + .01, 1.35]));   // 가운데 모래 자리
  scene.add(mesh(new T.CylinderGeometry(.1, .14, .7, 16), mat("#8C6B4E"), [0, top + .35, -1.5]));
  scene.add(ball(.82, mat("#6CBF5A"), [0, top + 1.4, -1.5]));
  // 쿠션: 가로로 한 줄(가운데 나무를 둘러 살짝 휘게). 내 쿠션을 가운데 쪽에
  const cols = others.slice(0, 4), n = cols.length + 1, mine = Math.floor(n / 2);
  cols.splice(mine, 0, myHex);
  const shadowM = new T.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: .06, depthWrite: false });
  let me = null;
  cols.forEach((hex, i) => {
    const x = (i - (n - 1) / 2) * 1.1, z = -.25 + .14 * x * x;
    scene.add(ball(.47, mat(hex), [x, top + .2, z], [1, .46, 1]));
    const s = mesh(new T.CircleGeometry(.52, 32), shadowM, [x, top + .015, z + .05]); s.rotation.x = -Math.PI / 2; scene.add(s);
    if (i === mine) me = [x, z];
  });
  // 내 캐릭터: 쿠션에 앉은 동작 0초. 엉덩이가 쿠션 윗면에 닿게 뿌리 높이를 맞춘다
  snapRig.dress(a, myHex, cat);
  snapRig.pose(C_SIT, 0);
  const wrap = snapRig.wrap, old = wrap.parent;
  scene.add(wrap);
  snapRig.shadow.visible = false;
  const k = .95 * (HEIGHT[a.height] || 1);
  wrap.scale.setScalar(k); wrap.rotation.set(0, 0, 0); wrap.position.set(0, 0, 0); wrap.updateMatrixWorld(true);
  const hip = new T.Vector3(); snapRig.hips.getWorldPosition(hip);
  wrap.position.set(me[0], top + .2 + .47 * .46 + .02 - hip.y, me[1] - .06 - hip.z);
  const cam = new T.PerspectiveCamera(30, w / h, .1, 60);
  cam.position.set(0, 4.6, 9.6); cam.lookAt(0, .75, -.2);
  render(scene, cam, w, h, 0xffffff);
  const url = toUrl(w, h);
  scene.remove(wrap); if (old) old.add(wrap);
  wrap.position.set(0, 0, 0); wrap.scale.setScalar(HEIGHT[a.height] || 1); snapRig.shadow.visible = true;
  scene.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material && o.material !== shadowM) o.material.dispose(); });
  shadowM.dispose();
  return url;
}
