# 도담도담 캐릭터 자산 만들기(문서 68 계획 1번): Meshy 몸 B3 + 동작 + 가발·수염·안경·이어폰·목도리·손 소품 → 앱용 GLB 한 개.
#  - 동작: 못 쓰는 것 지우기, 전환 구간 자르기, 앉은 상체 합성(Sit_Wave·Sit_Yawn·Sit_Stretch), 크기 채널·(Hips 빼고)이동 채널 없음,
#          Hips 수평 위치는 0초에 원점으로 맞추고 차이·걷기 속도는 JSON(root_motion.json)으로
#  - 몸: 목 위는 Head 뼈 100%, 재질 4개(skin·top·pants·shoes, 앱이 baseColorFactor로 칠함), Meshy 텍스처 명암은 꼭짓점 색(shade)으로
#        모프: build_chubby·build_slim(목 아래, 팔다리는 뼈 둘레로 부풀림) / face_slim·face_square·face_full(얼굴 아래쪽)
#  - 얼굴: Head 뼈 자식 'face' 조각, 재질 'face'의 텍스처는 바깥 파일 face.png(앱이 addResourceData로 넣음, 지금 방식 그대로)
#  - 부품: 뼈 자식(가발·수염·안경·이어폰 → Head, 목도리 → Spine2, 컵·책·폰 → RightHand). 텍스처는 기본 색 한 장만 작게(가발 448·나머지 256), 머리색은 회색 명암 × baseColorFactor
# 실행: Blender -b --factory-startup -P build_char.py -- [--meshy DIR] [--out DIR] [--app ASSET.glb] [--wig-tex 448] [--part-tex 256] [--wig-tris 4500]
# 검사: Blender -b --factory-startup -P build_char.py -- --verify GLB [--out DIR]   (새 블렌더에서 다시 읽어 동작·뼈·모프 확인 + 렌더 + 시트)
import bpy, bmesh, json, math, os, re, struct, sys, time
import numpy as np
from mathutils import Vector, Matrix, Quaternion
from mathutils.kdtree import KDTree
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
# 원본 폴더: --meshy 로 주거나 DODAM_REFS(style_refs 폴더)/meshy_1109. 저장소에는 Meshy 원본을 넣지 않는다
REFS = os.environ.get("DODAM_REFS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "style_refs"))
MESHY = arg("--meshy", os.path.join(REFS, "meshy_1109"))
OUT = arg("--out", os.path.join(MESHY, "char_build"))
APP = arg("--app")
WIG_TEX, PART_TEX = int(arg("--wig-tex", "448")), int(arg("--part-tex", "256"))
WIG_TRIS = int(arg("--wig-tris", "4500"))
os.makedirs(OUT, exist_ok=True)
FPS = 30
T0 = time.time()
def log(*a): print("[build_char %5.1fs]" % (time.time() - T0), *a, flush=True)

def lin(c): c = np.asarray(c, float); return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
def enc(c): c = np.clip(np.asarray(c, float), 0, 1); return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)
def hexlin(h): return [float(x) for x in lin([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])]
def smooth(t): t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)
def b2g(v): return [round(float(v[0]), 4), round(float(v[2]), 4), round(float(-v[1]), 4)]   # 블렌더(앞 -Y, 위 Z) → glTF(앞 +Z, 위 Y)

def import_glb(path):
    before_o, before_a = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before_o], [a for a in bpy.data.actions if a not in before_a]

def iter_fcurves(act):
    for l in act.layers:
        for s in l.strips:
            for cb in s.channelbags:
                yield from cb.fcurves

def activate(o):
    for x in bpy.context.selected_objects: x.select_set(False)
    o.select_set(True); bpy.context.view_layer.objects.active = o

def tri_count(o): return sum(len(p.vertices) - 2 for p in o.data.polygons)

# ── 기본값(앱이 덮어씀) ──
DEF_COL = {"skin": "#F2C9AC", "top": "#5AA9F0", "pants": "#5B6270", "shoes": "#454A52", "hair": "#4A3226",
           "earbud": "#F4F4F2", "scarf": "#E58A9A", "glasses": "#2B2522"}
HAIR_GAIN = 0.9          # 회색 명암 텍스처의 중간 밝기(머리색 × 0.9가 가장 흔한 색)
WIGS = ["m_allback", "m_bowl", "m_dandy", "m_ez", "m_gareu", "m_man50", "m_spiky",
        "w_bob", "w_bun", "w_grancut", "w_long", "w_perm", "w_pigtail", "w_pony", "w_wave",
        "m_twoblock", "w_ccurl", "w_wavecut",
        "m_buzz"]   # 11/10 짧은 스포츠머리(뾰족, 강호동·중년 아빠) 추가 — wig_v3 --flush 0.004 --liner 0.006(안감)   # 11/10 83번 (c): 투블럭·C컬 중단발·웨이브 커트 추가, 바가지(m_bowl)는 앞머리 둥글게 다시 만든 것으로 교체
# 옛 머리 번호(server/avatar.py PARTS hair, Plaza.kt) → 새 노드. None = 아무것도 안 보임(민머리)
OLD_HAIR = [("스포츠머리", "hair_m_dandy"), ("옆가르마", "hair_m_gareu"), ("세운 머리", "hair_m_spiky"), ("옆머리", "hair_m_bald"),
            ("민머리", None), ("긴 생머리", "hair_w_long"), ("포니테일", "hair_w_pony"), ("양갈래", "hair_w_pigtail"),
            ("웨이브", "hair_w_wave"), ("올림머리", "hair_w_bun"), ("일자 앞머리", "hair_m_bowl"), ("단발", "hair_w_bob"),
            ("숏컷", "hair_w_grancut"), ("파마", "hair_w_perm")]
NEW_HAIR_APPEND = [("애즈펌", "hair_m_ez"), ("2:8 가르마", "hair_m_man50"), ("올백", "hair_m_allback"),
                   ("투블럭", "hair_m_twoblock"), ("C컬 중단발", "hair_w_ccurl"), ("웨이브 커트", "hair_w_wavecut"),
                   ("짧은 스포츠머리", "hair_m_buzz")]   # 11/10 17·18·19
# 11/10 83번: 얼굴형(갸름·각진) 모프를 늘 넣는 가발. 얼굴 아래쪽에서 먼 머리는 옮길 양이 문턱(1.5 mm)보다 작아 모프가 빠지고,
#  그러면 앱 풀이 '각진형 형태 없는 가발'로 보고 각진 얼굴을 안 줌(일자 앞머리 등 6개). 새로 만든 가발은 실제로 옮긴 양 그대로(작아도) 넣음
FORCE_FACE_MORPHS = {"hair_m_bowl", "hair_m_twoblock", "hair_w_ccurl", "hair_w_wavecut", "hair_m_buzz"}

# ════════════════════════════════════════════════════════════════════ glb 손질(채널 거르기·재질·버퍼 압축)
def glb_read(p):
    d = open(p, "rb").read()
    jl = struct.unpack("<I", d[12:16])[0]; J = json.loads(d[20:20 + jl])
    o = 20 + jl; bl = struct.unpack("<I", d[o:o + 4])[0]; B = d[o + 8:o + 8 + bl]
    return J, B
def glb_write(p, J, B):
    js = json.dumps(J, separators=(",", ":")).encode(); js += b" " * ((4 - len(js) % 4) % 4)
    B = bytes(B) + b"\0" * ((4 - len(B) % 4) % 4)
    tot = 12 + 8 + len(js) + 8 + len(B)
    with open(p, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, tot)); f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
        f.write(struct.pack("<II", len(B), 0x004E4942)); f.write(B)
def glb_compact(J, B):
    used = set()
    for m in J.get("meshes", []):
        for pr in m["primitives"]:
            used.update(pr["attributes"].values())
            if "indices" in pr: used.add(pr["indices"])
            for t in pr.get("targets", []): used.update(t.values())
    for s in J.get("skins", []):
        if "inverseBindMatrices" in s: used.add(s["inverseBindMatrices"])
    for a in J.get("animations", []):
        for s in a["samplers"]: used.update((s["input"], s["output"]))
    acc_map = {old: new for new, old in enumerate(sorted(used))}
    accs = [J["accessors"][i] for i in sorted(used)]
    sp = [a["sparse"][k] for a in accs if "sparse" in a for k in ("indices", "values")]   # 모프는 듬성(sparse) 접근자로 나옴
    bvs = sorted({a["bufferView"] for a in accs if "bufferView" in a} | {x["bufferView"] for x in sp} | {im["bufferView"] for im in J.get("images", []) if "bufferView" in im})
    bv_map, nb, newbv = {}, bytearray(), []
    for new, old in enumerate(bvs):
        bv = dict(J["bufferViews"][old]); s = bv.get("byteOffset", 0)
        while len(nb) % 4: nb += b"\0"
        bv["byteOffset"] = len(nb); nb += B[s:s + bv["byteLength"]]; bv["buffer"] = 0
        newbv.append(bv); bv_map[old] = new
    for a in accs:
        if "bufferView" in a: a["bufferView"] = bv_map[a["bufferView"]]
    for x in sp: x["bufferView"] = bv_map[x["bufferView"]]
    for im in J.get("images", []):
        if "bufferView" in im: im["bufferView"] = bv_map[im["bufferView"]]
    for m in J.get("meshes", []):
        for pr in m["primitives"]:
            pr["attributes"] = {k: acc_map[v] for k, v in pr["attributes"].items()}
            if "indices" in pr: pr["indices"] = acc_map[pr["indices"]]
            if "targets" in pr: pr["targets"] = [{k: acc_map[v] for k, v in t.items()} for t in pr["targets"]]
    for s in J.get("skins", []):
        if "inverseBindMatrices" in s: s["inverseBindMatrices"] = acc_map[s["inverseBindMatrices"]]
    for a in J.get("animations", []):
        for s in a["samplers"]: s["input"] = acc_map[s["input"]]; s["output"] = acc_map[s["output"]]
    J["accessors"] = accs; J["bufferViews"] = newbv; J["buffers"] = [{"byteLength": len(nb)}]
    return J, bytes(nb)

def mat_role(name):
    if name in ("skin", "top", "pants", "shoes"): return "body"
    if name == "face": return "face"
    if name.startswith(("hair_", "beard_")) or name in ("earbud", "scarf"): return "tint"
    if name.startswith("prop_"): return "prop"
    if name == "glasses": return "glasses"
    return "other"

def glb_fix(path, hips_name="mixamorig:Hips"):
    J, B = glb_read(path)
    nodes = J["nodes"]; hips = [i for i, n in enumerate(nodes) if n.get("name") == hips_name][0]
    dropped = {"scale": 0, "translation": 0, "weights": 0}
    for a in J.get("animations", []):
        keep = []
        for c in a["channels"]:
            pth = c["target"]["path"]
            if pth == "rotation" or (pth == "translation" and c["target"].get("node") == hips): keep.append(c)
            else: dropped[pth] = dropped.get(pth, 0) + 1
        used = sorted({c["sampler"] for c in keep}); smap = {o: n for n, o in enumerate(used)}
        a["samplers"] = [a["samplers"][i] for i in used]
        for c in keep: c["sampler"] = smap[c["sampler"]]
        a["channels"] = keep
    # 재질: 이름별로 정해진 값
    tex_role = {}
    for m in J.get("materials", []):
        r = mat_role(m["name"]); pbr = m.setdefault("pbrMetallicRoughness", {})
        pbr.pop("metallicRoughnessTexture", None); m.pop("normalTexture", None); m.pop("occlusionTexture", None); m.pop("emissiveTexture", None)
        m.pop("extensions", None); m.pop("emissiveFactor", None)
        pbr["metallicFactor"] = 0.0
        if r == "body":
            pbr["baseColorFactor"] = hexlin(DEF_COL[m["name"]]) + [1.0]; pbr["roughnessFactor"] = 0.6 if m["name"] == "skin" else 0.85
            m.pop("alphaMode", None); m.pop("doubleSided", None)
        elif r == "tint":
            key = "hair" if m["name"].startswith(("hair_", "beard_")) else m["name"]
            pbr["baseColorFactor"] = hexlin(DEF_COL[key]) + [1.0]; pbr["roughnessFactor"] = 0.7
            m["alphaMode"] = "MASK"; m["alphaCutoff"] = 0.5; m["doubleSided"] = True
        elif r == "prop":
            pbr["baseColorFactor"] = [1, 1, 1, 1]; pbr["roughnessFactor"] = 0.7; m.pop("alphaMode", None); m.pop("alphaCutoff", None)
        elif r == "glasses":
            pbr["baseColorFactor"] = hexlin(DEF_COL["glasses"]) + [1.0]; pbr["roughnessFactor"] = 0.4; pbr["metallicFactor"] = 0.3
            m.pop("alphaMode", None)
        elif r == "face":
            pbr["baseColorFactor"] = [1, 1, 1, 1]; pbr["roughnessFactor"] = 0.6; m.pop("alphaMode", None); m.pop("doubleSided", None)
        if "baseColorTexture" in pbr: tex_role[pbr["baseColorTexture"]["index"]] = r
    # 텍스처 거르개: 얼굴은 늘이기·밉맵 없음(옛 파일과 같음), 나머지는 밉맵(멀리서 머리카락 반짝임 방지)
    J["samplers"] = [{"magFilter": 9729, "minFilter": 9729, "wrapS": 33071, "wrapT": 33071},
                     {"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}]
    for i, t in enumerate(J.get("textures", [])):
        t["sampler"] = 0 if tex_role.get(i) == "face" else 1
        if tex_role.get(i) == "face":   # 얼굴 그림은 파일 안에 넣지 않고 바깥 이름 face.png로(앱이 사람마다 넣음)
            im = J["images"][t["source"]]; im.pop("bufferView", None); im.pop("mimeType", None); im["uri"] = "face.png"; im["name"] = "face"
    J, B = glb_compact(J, B)
    glb_write(path, J, B)
    return dropped

# ════════════════════════════════════════════════════════════════════ 텍스처 옮기기(UV 다시 펴고 작게 굽기)
def sample_bilinear(px, u, v):
    H, W = px.shape[:2]
    x = np.clip(u * W - 0.5, 0, W - 1.001); y = np.clip(v * H - 0.5, 0, H - 1.001)
    x0 = x.astype(int); y0 = y.astype(int); fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    return (px[y0, x0] * (1 - fx) * (1 - fy) + px[y0, x0 + 1] * fx * (1 - fy) + px[y0 + 1, x0] * (1 - fx) * fy + px[y0 + 1, x0 + 1] * fx * fy)

def bake_transfer(me, old_uv, new_uv, src, N, gate=None, ss=2):
    """새 UV 삼각형마다 픽셀을 채우고, 같은 자리의 옛 UV로 원본 텍스처를 읽는다. 결과: (N,N,4) [색 sRGB 그대로, 알파=원본알파×gate]."""
    N2 = N * ss; col = np.zeros((N2, N2, 4), np.float32); cov = np.zeros((N2, N2), np.float32)
    me.calc_loop_triangles()
    UO = np.empty(len(me.loops) * 2); me.uv_layers[old_uv].data.foreach_get("uv", UO); UO = UO.reshape(-1, 2)
    UN = np.empty(len(me.loops) * 2); me.uv_layers[new_uv].data.foreach_get("uv", UN); UN = UN.reshape(-1, 2) * N2
    LV = np.empty(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", LV)
    for t in me.loop_triangles:
        L = list(t.loops); a, b, c = UN[L]
        x0 = max(int(np.floor(min(a[0], b[0], c[0]))), 0); x1 = min(int(np.ceil(max(a[0], b[0], c[0]))) + 1, N2)
        y0 = max(int(np.floor(min(a[1], b[1], c[1]))), 0); y1 = min(int(np.ceil(max(a[1], b[1], c[1]))) + 1, N2)
        if x1 <= x0 or y1 <= y0: continue
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12: continue
        xs, ys = np.meshgrid(np.arange(x0, x1) + .5, np.arange(y0, y1) + .5)
        l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d; l3 = 1 - l1 - l2
        m = (l1 >= -1e-4) & (l2 >= -1e-4) & (l3 >= -1e-4)
        if not m.any(): continue
        w = np.stack([l1[m], l2[m], l3[m]], 1); uo = w @ UO[L]
        s = sample_bilinear(src, uo[:, 0], uo[:, 1])
        if gate is not None: s[:, 3] *= w @ gate[LV[L]]
        yy, xx = np.nonzero(m); col[yy + y0, xx + x0] = s; cov[yy + y0, xx + x0] = 1
    # 줄이기(ss×ss 평균, 덮인 칸만)
    col = (col * cov[..., None]).reshape(N, ss, N, ss, 4).sum((1, 3)); cnt = cov.reshape(N, ss, N, ss).sum((1, 3))
    out = np.where(cnt[..., None] > 0, col / np.maximum(cnt, 1)[..., None], 0)
    # 섬 바깥으로 번지기(밉맵·필터 때 이음매 틈 방지)
    filled = cnt > 0
    for _ in range(8):
        acc = np.zeros_like(out); n = np.zeros(filled.shape)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0: continue
                acc += np.roll(np.roll(out * filled[..., None], dy, 0), dx, 1); n += np.roll(np.roll(filled, dy, 0), dx, 1)
        grow = (~filled) & (n > 0)
        out[grow] = acc[grow] / n[grow][:, None]; filled = filled | grow
    return out.astype(np.float32), float((cnt > 0).mean())

def image_from(name, arr, save_dir):
    N = arr.shape[0]
    img = bpy.data.images.new(name, N, N, alpha=True); img.pixels.foreach_set(arr.ravel().astype(np.float32))
    p = os.path.join(save_dir, name + ".png"); img.filepath_raw = p; img.file_format = 'PNG'; img.save()
    bpy.data.images.remove(img); img = bpy.data.images.load(p); img.alpha_mode = 'STRAIGHT'
    return img

def base_image(o):
    for m in o.data.materials:
        if not (m and m.node_tree): continue
        for n in m.node_tree.nodes:
            if n.type == 'BSDF_PRINCIPLED':
                def up(sock, depth=0):
                    for l in sock.links:
                        fn = l.from_node
                        if fn.type == 'TEX_IMAGE' and fn.image: return fn.image
                        if depth < 4:
                            for inp in fn.inputs:
                                r_ = up(inp, depth + 1)
                                if r_: return r_
                    return None
                r_ = up(n.inputs["Base Color"])
                if r_: return r_
    for m in o.data.materials:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image: return n.image
    return None

def img_array(img):
    W, H = img.size; a = np.empty(W * H * 4, np.float32); img.pixels.foreach_get(a); return a.reshape(H, W, 4)

def simple_mat(name, img=None, alpha=False):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; bs = nt.nodes["Principled BSDF"]
    if img is not None:
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = img
        nt.links.new(tx.outputs["Color"], bs.inputs["Base Color"])
        if alpha: nt.links.new(tx.outputs["Alpha"], bs.inputs["Alpha"])
    m.use_backface_culling = False
    return m

def decimate_to(o, tris):
    cur = tri_count(o)
    if cur <= tris: return cur
    activate(o); md = o.modifiers.new("dec", 'DECIMATE'); md.ratio = tris / cur; md.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=md.name)
    return tri_count(o)

def keep_uv(o):
    """Meshy UV 배치는 그대로 쓴다: 머리카락은 얇게 접힌 면이라 섬이 1천 개 안팎(새로 펴도 700개) → 다시 채우면 여백 때문에 오히려 손해(실측 0.18 vs 원래 0.4)."""
    me = o.data; old = me.uv_layers[0].name
    me.uv_layers.new(name="pack", do_init=True)
    return old, "pack"

def prep_part(o, name, tris, N, mode, gate_src=None):
    """mode: tint(머리색처럼 회색 명암+알파) / color(소품 색 그대로) / plain(텍스처 없음)."""
    me = o.data; src_img = base_image(o) if mode != "plain" else None
    P0 = np.array([v.co[:] for v in me.vertices])
    gate0 = None
    if mode == "tint":   # wig_v3가 넣은 '가장자리 문'(꼭짓점 알파) → 텍스처 알파에 곱해 넣는다
        for ca in me.color_attributes:
            a = np.empty(len(ca.data) * 4, np.float32); ca.data.foreach_get("color", a); al = a.reshape(-1, 4)[:, 3]
            if ca.domain == 'POINT' and al.std() > 1e-4: gate0 = al; break
            if ca.domain == 'CORNER' and al.std() > 1e-4:
                lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", lv)
                g = np.ones(len(me.vertices)); np.minimum.at(g, lv, al); gate0 = g; break
    t0 = tri_count(o)
    if mode != "plain":   # glTF에서 온 메시는 UV 이음매마다 점이 갈라져 있음 → 붙이고(UV는 모서리별이라 그대로) 이음매 표시 → 줄이기
        activate(o); bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=1e-5); bpy.ops.uv.seams_from_islands(mark_seams=True)
        bpy.ops.object.mode_set(mode='OBJECT')
    t1 = decimate_to(o, tris); me = o.data
    for ca in list(me.color_attributes): me.color_attributes.remove(ca)
    info = {"tris_src": t0, "tris": t1}
    if mode == "plain":
        while len(me.uv_layers): me.uv_layers.remove(me.uv_layers[0])
        return info
    gate = None
    if gate0 is not None:
        kd = KDTree(len(P0))
        for i, p in enumerate(P0): kd.insert(p, i)
        kd.balance(); gate = np.array([gate0[kd.find(v.co)[1]] for v in me.vertices])
    src = img_array(src_img)
    old, new = keep_uv(o)
    out, used = bake_transfer(me, old, new, src, N, gate=gate)
    if mode == "tint":
        L = lin(src[..., :3]) @ np.array([0.2126, 0.7152, 0.0722]); ref = float(np.median(L[src[..., 3] > 0.5])) if (src[..., 3] > 0.5).any() else 0.1
        Lo = lin(out[..., :3]) @ np.array([0.2126, 0.7152, 0.0722])
        g = enc(np.clip(HAIR_GAIN * Lo / max(ref, 1e-4), 0, 1))
        out[..., 0] = out[..., 1] = out[..., 2] = g
        out[..., 3] = np.clip(out[..., 3], 0, 1)
    else:
        out[..., 3] = 1
    me.uv_layers.remove(me.uv_layers[old]); me.uv_layers[0].name = "UVMap"
    img = image_from("tex_" + name, out, os.path.join(OUT, "textures"))
    me.materials.clear(); me.materials.append(simple_mat(name, img, alpha=(mode == "tint")))
    info.update(tex=N, uv_used=round(used, 2))
    return info

# ════════════════════════════════════════════════════════════════════ 검사 모드
def run_verify(GLB):
    """새 장면에 GLB만 다시 읽어 동작·뼈 무게·모프가 살아 있는지 보고, 꾸민 사람 5명 × 동작 5개를 렌더해 한 장으로 붙인다."""
    VD = os.path.join(OUT, "verify"); os.makedirs(VD, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene; sc.render.fps = FPS; sc.render.fps_base = 1
    objs, acts = import_glb(GLB)
    arm = [o for o in objs if o.type == 'ARMATURE'][0]; body = bpy.data.objects["body"]
    rep = {"animations": [], "objects": {}}
    for a in sorted(bpy.data.actions, key=lambda a: a.name):
        rep["animations"].append([a.name, round((a.frame_range[1] - a.frame_range[0]) / FPS, 3)])
    for o in bpy.data.objects:
        if o.type != 'MESH': continue
        rep["objects"][o.name] = {"parent": o.parent.name if o.parent else None, "bone": o.parent_bone, "tris": tri_count(o),
                                  "mats": [m.name for m in o.data.materials], "morphs": [k.name for k in o.data.shape_keys.key_blocks[1:]] if o.data.shape_keys else [],
                                  "skin": any(m.type == 'ARMATURE' for m in o.modifiers), "vgroups": len(o.vertex_groups),
                                  "colors": [c.name for c in o.data.color_attributes]}
    log("VERIFY anims", len(rep["animations"]), rep["animations"])
    log("VERIFY body", rep["objects"]["body"])
    ad = arm.animation_data
    def use(name):
        a = bpy.data.actions[name]; ad.action = a
        try: ad.action_slot = a.slots[0]
        except Exception: pass
    for t in ad.nla_tracks: t.mute = True
    parts = [o for o in bpy.data.objects if o.type == 'MESH' and o is not body and o.name != "face"]
    # ── 수치 검사: 큰 머리 ↔ 다리, 긴 머리·목도리 ↔ 몸 뚫림(깊이 m)
    vgn = {g.index: g.name for g in body.vertex_groups}
    hw = np.zeros(len(body.data.vertices)); lw = np.zeros(len(body.data.vertices))
    for v in body.data.vertices:
        for g in v.groups:
            n = vgn[g.group]
            if n == "mixamorig:Head": hw[v.index] = g.weight
            if any(k in n for k in ("UpLeg", "mixamorig:LeftLeg", "mixamorig:RightLeg")): lw[v.index] += g.weight
    legs = np.nonzero(lw > 0.5)[0]; hv = np.nonzero(hw > 0.99)[0]
    handw = np.zeros(len(body.data.vertices))
    for v in body.data.vertices:
        for g in v.groups:
            if vgn[g.group] in ("mixamorig:RightHand", "mixamorig:LeftHand", "Bone_035", "Bone_036"): handw[v.index] += g.weight
    hands = np.nonzero(handw > 0.6)[0]
    allp = [list(p.vertices) for p in body.data.polygons]
    R0 = np.array([v.co[:] for v in body.data.vertices]) @ np.array(body.matrix_world)[:3, :3].T + np.array(body.matrix_world)[:3, 3]
    hc0 = (R0[hv].min(0) + R0[hv].max(0)) / 2; hr = float(np.median(np.linalg.norm(R0[hv] - hc0, axis=1))) * 0.95   # 머리 = 공(조금 작게)
    pbh = arm.pose.bones["mixamorig:Head"]; loc_c = (arm.matrix_world @ pbh.bone.matrix_local).inverted() @ Vector(hc0)
    def inside_depth(bvh, pts, reach=0.12):   # 닫힌 몸에서 가까운 면의 안쪽이면 그 거리 = 파고든 깊이
        dmax = 0.0
        for p in pts:
            loc, n, i, d = bvh.find_nearest(Vector(p))
            if loc is not None and d < reach and (Vector(p) - loc).dot(n) < 0: dmax = max(dmax, d)
        return dmax
    checks = {}
    probe = {k: bpy.data.objects[k] for k in ("hair_w_long", "hair_w_pony", "hair_w_pigtail", "hair_w_wave", "scarf", "beard_long") if k in bpy.data.objects}
    dg = bpy.context.evaluated_depsgraph_get(); Mb = np.array(body.matrix_world)
    def part_pts(o):   # 뼈 자식이든 뼈 무게(스킨)든 지금 자세의 세계 좌표
        eo = o.evaluated_get(dg); em = eo.to_mesh(); V = np.empty(len(em.vertices) * 3); em.vertices.foreach_get("co", V); eo.to_mesh_clear()
        Mw = np.array(eo.matrix_world); return V.reshape(-1, 3)[::3] @ Mw[:3, :3].T + Mw[:3, 3]
    for a in sorted(bpy.data.actions, key=lambda a: a.name):
        use(a.name); dur = (a.frame_range[1] - a.frame_range[0]) / FPS
        worst = {"head_knee_gap": (9.0, 0)}   # 머리 공 겉면 ~ 다리 점 최소 거리(m, 음수면 파고듦)
        for t in np.arange(0, dur + 1e-6, 0.2):
            sc.frame_set(int(round(t * FPS))); dg.update()
            be = body.evaluated_get(dg); em = be.to_mesh(); X = np.empty(len(em.vertices) * 3); em.vertices.foreach_get("co", X); be.to_mesh_clear()
            X = X.reshape(-1, 3) @ Mb[:3, :3].T + Mb[:3, 3]
            c = np.array(arm.matrix_world @ pbh.matrix @ loc_c)
            d = float((np.linalg.norm(X[legs] - c, axis=1) - hr).min())
            if d < worst["head_knee_gap"][0]: worst["head_knee_gap"] = (round(d, 3), round(float(t), 2))
            dh = float((np.linalg.norm(X[hands] - c, axis=1) - hr).min())   # 손이 큰 머리 속으로(원래 머리 크기에 맞춘 동작)
            if dh < -0.03: worst.setdefault("hand_in_head_sec", []).append(round(float(t), 1))
            worst["hand_head_gap_min"] = min(worst.get("hand_head_gap_min", 9.0), round(dh, 3))
            bb = BVHTree.FromPolygons([Vector(x) for x in X], allp)
            for k, o in probe.items():
                dd = inside_depth(bb, part_pts(o))
                if dd > worst.get(k, (0, 0))[0]: worst[k] = (round(dd, 3), round(float(t), 2))
        checks[a.name] = worst
    # 쉬는 자세에서 이미 파고든 깊이(가발 모양 자체: 긴 머리가 어깨·팔을 지나감) → 동작 때 더해진 것만 따로
    arm.data.pose_position = 'REST'; bpy.context.view_layer.update(); dg.update()
    be = body.evaluated_get(dg); em = be.to_mesh(); X = np.empty(len(em.vertices) * 3); em.vertices.foreach_get("co", X); be.to_mesh_clear()
    X = X.reshape(-1, 3) @ Mb[:3, :3].T + Mb[:3, 3]; bb = BVHTree.FromPolygons([Vector(x) for x in X], allp); base = {}
    for k, o in probe.items(): base[k] = round(inside_depth(bb, part_pts(o)), 3)
    arm.data.pose_position = 'POSE'; bpy.context.view_layer.update()
    rep["rest_penetration_m"] = base; log("VERIFY rest penetration", base)
    rj = os.path.join(os.path.dirname(GLB), "root_motion.json")   # 손이 큰 머리 속으로 들어가는 구간을 동작 정보에 적어 둠(앱이 그 구간을 건너뛰거나 팔을 덜 올림)
    if os.path.exists(rj):
        RM = json.load(open(rj))
        for nm, w_ in checks.items():
            if nm in RM["clips"]:
                RM["clips"][nm].pop("hand_in_head_sec", None)
                if w_.get("hand_in_head_sec"): RM["clips"][nm]["hand_in_head_sec"] = [w_["hand_in_head_sec"][0], w_["hand_in_head_sec"][-1]]
        json.dump(RM, open(rj, "w"), ensure_ascii=False, indent=1)
    rep["penetration_m_max_at_sec"] = checks
    log("VERIFY penetration", checks)
    # ── 렌더
    def tint(m, h):
        nt = m.node_tree; bs = [n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'][0]; inp = bs.inputs["Base Color"]; c = hexlin(h) + [1]
        if not inp.links: inp.default_value = c; return
        fn = inp.links[0].from_node
        if fn.type == 'MIX' and fn.blend_type == 'MULTIPLY': fn.inputs[7].default_value = c; return
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.inputs[0].default_value = 1
        nt.links.new(inp.links[0].from_socket, mx.inputs[6]); mx.inputs[7].default_value = c; nt.links.new(mx.outputs[2], inp)
    def shade_body():   # 꼭짓점 색(shade)을 몸 재질에 곱함(앱 gltfio와 같게)
        for m in body.data.materials:
            nt = m.node_tree; bs = [n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'][0]; inp = bs.inputs["Base Color"]
            if inp.links: continue
            ca = nt.nodes.new("ShaderNodeVertexColor"); ca.layer_name = body.data.color_attributes[0].name if body.data.color_attributes else ""
            mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.inputs[0].default_value = 1
            mx.inputs[6].default_value = inp.default_value[:]; nt.links.new(ca.outputs["Color"], mx.inputs[7]); nt.links.new(mx.outputs[2], inp)
    shade_body()
    # 얼굴: 앱 drawFace 대신 같은 배치(눈 y .50 dx .15, 입 y .66, v=0 위)로 간단히 그린 시험 그림
    fp = arg("--face-png")
    if fp: fimg = bpy.data.images.load(fp)
    else:
        NF = 256; yy, xx = np.mgrid[0:NF, 0:NF] + 0.5; u = xx / NF; v = 1 - yy / NF
        a = np.zeros((NF, NF, 4), np.float32); a[..., :3] = enc(hexlin(DEF_COL["skin"])); a[..., 3] = 1
        ink = ((u - .35) / .035) ** 2 + ((v - .5) / .05) ** 2 < 1
        ink |= ((u - .65) / .035) ** 2 + ((v - .5) / .05) ** 2 < 1
        r = np.hypot(u - .5, (v - .62) * 1.0); ink |= (np.abs(r - .06) < .008) & (v > .63)
        a[ink, :3] = 0.12
        fimg = bpy.data.images.new("face_test", NF, NF, alpha=True); fimg.pixels.foreach_set(a.ravel())
        face_ink = ink
    fi = bpy.data.objects["face"].data.materials[0]; tn = [n for n in fi.node_tree.nodes if n.type == 'TEX_IMAGE']
    if not tn:
        t_ = fi.node_tree.nodes.new("ShaderNodeTexImage"); bs_ = [n for n in fi.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'][0]
        fi.node_tree.links.new(t_.outputs["Color"], bs_.inputs["Base Color"]); tn = [t_]
    for n in tn: n.image = fimg; n.extension = 'EXTEND'
    rep["face_texture_slot"] = "face.png" if any(i.filepath.endswith("face.png") for i in bpy.data.images) else "?"
    sc.render.engine = 'CYCLES'; sc.cycles.samples = 12; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 240, 300; sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    for loc, e in (((-2, -4, 3), 250), ((3, -3, 1), 90), ((0, 4, 2), 80)):
        l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = loc; sc.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0, 0, 0.8)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = 2.0
    def camyaw(deg, c=(0, 0, 0.88), scale=2.0):
        a = math.radians(deg); cam.location = (c[0] + 6 * math.sin(a), c[1] - 6 * math.cos(a), c[2]); cam.rotation_euler = (math.pi / 2, 0, a)
        cam.data.ortho_scale = scale; txo.location = (-0.475 * scale, -0.46 * scale, -1); txt.size = 0.045 * scale
    txt = bpy.data.curves.new("lab", 'FONT'); txt.size = 0.09; txo = bpy.data.objects.new("lab", txt); sc.collection.objects.link(txo)
    tm = bpy.data.materials.new("lab"); tm.use_nodes = True; tm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0, 0, 0, 1); txt.materials.append(tm)
    txo.parent = cam; txo.location = (-0.95, -0.92, -1); txo.rotation_euler = (0, 0, 0)
    try: txt.body_format  # noqa
    except Exception: pass
    ROWS = [("default", [], {}, {}),
            ("pony+round+cup", ["hair_w_pony", "glasses_round", "prop_cup"], {"skin": "#F8DCC8", "top": "#F08AAE", "hair": "#2B2522"}, {}),
            ("man50+beard_long+scarf", ["hair_m_man50", "beard_long", "scarf"], {"skin": "#C98E64", "top": "#3F5BA9", "hair": "#A9A6A2", "beard": "#A9A6A2"}, {}),
            ("bald", ["hair_m_bald"], {"skin": "#EBC394", "top": "#7CC36B", "hair": "#2B2522"}, {}),
            ("bun", ["hair_w_bun", "glasses_square", "prop_book"], {"skin": "#8E5B3E", "top": "#F5C842", "hair": "#E2B85A"}, {}),
            ("morph:chubby+square (man50)", ["hair_m_man50", "beard_long", "scarf"], {"top": "#F49A4A", "hair": "#4A3226", "beard": "#4A3226"}, {"build_chubby": 1, "face_square": 1}),
            ("morph:slim+faceslim (long)", ["hair_w_long", "glasses_half", "prop_phone"], {"top": "#A98BE8", "hair": "#8A5A3C"}, {"build_slim": 1, "face_slim": 1}),
            ("morph:chubby+full+square (ccurl)", ["hair_w_ccurl", "glasses_round", "scarf"], {"top": "#7CC36B", "hair": "#4A3226"}, {"build_chubby": 1, "face_full": 1, "face_square": 0.6})]
    COLS = [("Short_Breathe_and_Look_Around", 1.5, 25), ("Chair_Sit_Idle_F", 3.0, 25), ("Sit_Wave", 1.0, 20), ("Walking", 0.25, 40),
            ("Sit_and_Drink", 4.0, 30), ("Sit_Yawn", 1.4, 20), ("Sit_Stretch", 1.6, 20), ("Stand_to_Sit_Transition_M", 0.55, 70), ("Short_Breathe_and_Look_Around", 1.5, 180)]
    base_cols = {m.name: None for m in bpy.data.materials}
    files = []
    for ri, (rn, show, cols, morphs) in enumerate(ROWS):
        for o in parts: o.hide_render = o.name not in show
        for m in body.data.materials: tint(m, cols.get(m.name, DEF_COL.get(m.name, "#FFFFFF")))
        for o in parts:
            for m in o.data.materials:
                if m.name.startswith("hair_"): tint(m, cols.get("hair", DEF_COL["hair"]))
                elif m.name.startswith("beard_"): tint(m, cols.get("beard", cols.get("hair", DEF_COL["hair"])))
        if not fp:   # 앱처럼 얼굴 바탕 = 그 사람 피부색
            a = np.zeros((256, 256, 4), np.float32); a[..., :3] = enc(hexlin(cols.get("skin", DEF_COL["skin"]))); a[..., 3] = 1; a[face_ink, :3] = 0.12
            fimg.pixels.foreach_set(a.ravel())
        for o in [body, bpy.data.objects["face"]] + parts:
            if o.data.shape_keys:
                for kb in o.data.shape_keys.key_blocks[1:]: kb.value = morphs.get(kb.name, 0.0)
        for ci, (clip, t, yaw) in enumerate(COLS):
            use(clip); sc.frame_set(int(round(t * FPS))); camyaw(yaw)
            txt.body = f"{rn} | {clip} {t}s"
            p = os.path.join(VD, f"r{ri}_c{ci}.png"); sc.render.filepath = p; bpy.ops.render.render(write_still=True); files.append((ri, ci, p))
    # 가까이 보기 줄: 손 소품·얼굴·큰 머리-무릎
    def show_only(names, cols):
        for o in parts: o.hide_render = o.name not in names
        for m in body.data.materials: tint(m, cols.get(m.name, DEF_COL.get(m.name, "#FFFFFF")))
        for o in [body, bpy.data.objects["face"]] + parts:
            if o.data.shape_keys:
                for kb in o.data.shape_keys.key_blocks[1:]: kb.value = 0.0
        a = np.zeros((256, 256, 4), np.float32); a[..., :3] = enc(hexlin(cols.get("skin", DEF_COL["skin"]))); a[..., 3] = 1
        if not fp: a[face_ink, :3] = 0.12; fimg.pixels.foreach_set(a.ravel())
    def at_bone(bn): return tuple(arm.matrix_world @ arm.pose.bones[bn].head)
    CLOSE = [(["prop_cup"], "Sit_and_Drink", 2.0, "mixamorig:RightHand", 30, 0.7), (["prop_cup"], "Sit_and_Drink", 5.0, "mixamorig:RightHand", 30, 0.7),
             (["prop_cup"], "Walking", 0.25, "mixamorig:RightHand", -30, 0.7), (["prop_book"], "Chair_Sit_Idle_F", 3.0, "mixamorig:RightHand", 20, 0.7),
             (["prop_phone"], "Short_Breathe_and_Look_Around", 1.5, "mixamorig:RightHand", -30, 0.7), (["hair_w_pony", "glasses_round"], "Short_Breathe_and_Look_Around", 1.5, "mixamorig:Head", 0, 1.0),
             (["hair_m_man50", "beard_mus", "glasses_half"], "Short_Breathe_and_Look_Around", 1.5, "mixamorig:Head", 35, 1.0),
             (["hair_w_wave"], "Stand_to_Sit_Transition_M", 0.55, "mixamorig:Hips", 90, 1.6), (["hair_w_bob", "scarf"], "Sit_and_Doze_Off", 4.0, "mixamorig:Hips", 90, 1.6)]
    ri = len(ROWS)
    for ci, (names, clip, t, bn, yaw, scl) in enumerate(CLOSE):
        show_only(names, {"top": "#5FD0B5"}); use(clip); sc.frame_set(int(round(t * FPS))); bpy.context.view_layer.update()
        c = at_bone(bn)
        if bn == "mixamorig:Head": c = tuple(np.array(arm.matrix_world @ pbh.matrix @ loc_c))
        camyaw(yaw, c, scl); txt.body = f"{'+'.join(names)} | {clip} {t}s"
        p = os.path.join(VD, f"r{ri}_c{ci}.png"); sc.render.filepath = p; bpy.ops.render.render(write_still=True); files.append((ri, ci, p))
    # 한 장으로
    RW, RH = sc.render.resolution_x, sc.render.resolution_y; nr, nc = len(ROWS) + 1, len(COLS)
    sheet = np.ones((nr * RH, nc * RW, 4), np.float32)
    for ri, ci, p in files:
        im = bpy.data.images.load(p); a = np.empty(RW * RH * 4, np.float32); im.pixels.foreach_get(a)
        sheet[(nr - 1 - ri) * RH:(nr - ri) * RH, ci * RW:(ci + 1) * RW] = a.reshape(RH, RW, 4); bpy.data.images.remove(im)
    si = bpy.data.images.new("sheet", nc * RW, nr * RH); si.pixels.foreach_set(sheet.ravel())
    sp = os.path.join(OUT, "contact_sheet.jpg"); si.filepath_raw = sp; si.file_format = 'JPEG'; si.save()
    rep["contact_sheet"] = sp
    json.dump(rep, open(os.path.join(OUT, "verify_report.json"), "w"), ensure_ascii=False, indent=1)
    log("VERIFY done", sp)

if arg("--verify"):
    run_verify(arg("--verify")); sys.exit(0)

# ════════════════════════════════════════════════════════════════════ 1. 몸·뼈·동작 불러오기
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
objs, acts = import_glb(os.path.join(MESHY, "anim/body_B3_anims.glb"))
SRC_FPS = sc.render.fps / sc.render.fps_base
arm = [o for o in objs if o.type == 'ARMATURE'][0]; body = [o for o in objs if o.type == 'MESH' and o.vertex_groups][0]
for o in objs:
    if o.type == 'MESH' and o is not body: bpy.data.objects.remove(o)   # Icosphere(무게 없음) 버림
arm.name = "char"; body.name = "body"; body.data.name = "body"
assert arm.matrix_world == Matrix() and body.matrix_world == Matrix(), "몸·뼈대 원점이 기준과 다름"
src = {a.name: a for a in acts}
for nm, fn in (("Stretch", "clip_stretch.glb"), ("Yawn", "clip_yawn.glb")):   # AI 동작 2개: 뼈대 같음 → 동작만 가져옴
    o2, a2 = import_glb(os.path.join(MESHY, "anim", fn))
    a2[0].name = nm; src[nm] = a2[0]
    for o in o2: bpy.data.objects.remove(o)
for k, a in src.items(): a.name = "SRC_" + k   # 새 동작 이름과 안 겹치게
log("source clips", len(src), "fps", SRC_FPS)

# ════════════════════════════════════════════════════════════════════ 2. 동작 정리
bones = [b.name for b in arm.data.bones]
UPPER = set()
def _sub(b):
    UPPER.add(b.name)
    for c in b.children: _sub(c)
_sub(arm.data.bones["mixamorig:Spine"])
HIPS = "mixamorig:Hips"
ML = arm.data.bones[HIPS].matrix_local.copy(); ML3i = ML.to_3x3().inverted()

def fc_table(act):
    d = {}
    for fc in iter_fcurves(act):
        m = re.match(r'pose\.bones\["(.+)"\]\.(\w+)', fc.data_path)
        if m: d.setdefault((m.group(1), m.group(2)), {})[fc.array_index] = fc
    return d
TAB = {k: fc_table(a) for k, a in src.items()}
# 원래 동작의 이동(Hips 말고)·크기 채널이 정말 비어 있는지(1·0 고정인지) 확인
dev = {"loc": 0.0, "scale": 0.0}
for k, tab in TAB.items():
    for (bn, prop), fcs in tab.items():
        for i, fc in fcs.items():
            vals = np.array([kp.co[1] for kp in fc.keyframe_points])
            if prop == "location" and bn != HIPS:
                if float(np.abs(vals).max()) > dev["loc"]: dev["loc_where"] = f"{k}:{bn}[{i}]"
                dev["loc"] = max(dev["loc"], float(np.abs(vals).max()))
            if prop == "scale": dev["scale"] = max(dev["scale"], float(np.abs(vals - 1).max()))
log("non-Hips location max", round(dev["loc"], 5), dev.get("loc_where"), "scale dev max", round(dev["scale"], 5))

def sample(name, t_sec, bone, prop, n):
    fcs = TAB[name].get((bone, prop))
    if not fcs: return None
    fr = np.asarray(t_sec) * SRC_FPS
    out = np.zeros((len(fr), n))
    for i in range(n):
        if i in fcs: out[:, i] = [fcs[i].evaluate(float(f)) for f in fr]
        elif prop == "rotation_quaternion" and i == 0: out[:, i] = 1
    return out
def src_dur(name):
    a = src[name]; return (a.frame_range[1] - a.frame_range[0]) / SRC_FPS

CUT = {"Sit_to_Stand_Transition_M": (1.40, 2.57), "Stand_to_Sit_Transition_M": (2.50, 3.53), "Big_Wave_Hello": (0.47, 2.57)}
DROP = {"Running", "Idle_15", "Right_Uppercut_from_Guard", "Wake_Up_and_Look_Up", "Yawn"}   # Yawn은 바닥 앉기 → 상체만 Sit_Yawn으로
LOOP = {"Walking", "Chair_Sit_Idle_F", "Long_Breathe_and_Look_Around", "Short_Breathe_and_Look_Around", "Sit_and_Doze_Off",
        "Sit_and_Drink", "Sit_Cross_Legged", "Sit_Cross_Legged_on_Floor", "Stand_and_Chat", "Wave_One_Hand"}
SIT_BASE = "Chair_Sit_Idle_F"
COMPOSITE = {"Sit_Wave": ("Big_Wave_Hello", CUT["Big_Wave_Hello"]), "Sit_Yawn": ("Yawn", None), "Sit_Stretch": ("Stretch", None)}
ROOT_EXTRACT = {"Step_to_Sit_Transition"}     # 몸 전체가 걸어 나가는 동작: 수평 이동을 통째로 JSON 경로로

def clip_plan():
    plan = []
    for nm in sorted(src):
        if nm in DROP: continue
        t0, t1 = CUT.get(nm, (0.0, src_dur(nm)))
        plan.append((nm, {b: (nm, t0) for b in bones}, t1 - t0))
    for nm, (up, rng) in COMPOSITE.items():
        t0, t1 = rng if rng else (0.0, src_dur(up))
        plan.append((nm, {b: ((up, t0) if b in UPPER else (SIT_BASE, 0.0)) for b in bones}, t1 - t0))
    return plan

def new_action(name):
    act = bpy.data.actions.new(name); act.use_fake_user = True
    slot = act.slots.new(id_type='OBJECT', name=arm.name)
    st = act.layers.new("L").strips.new(type='KEYFRAME'); cb = st.channelbags.new(slot)
    return act, cb
def put_curve(cb, path, idx, frames, vals, group):
    fc = cb.fcurves.new(path, index=idx); n = len(frames)
    fc.keyframe_points.add(n); fc.keyframe_points.foreach_set("co", np.column_stack([frames, vals]).ravel().astype(np.float32))
    try: fc.keyframe_points.foreach_set("interpolation", [1] * n)   # LINEAR
    except Exception:
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
    fc.update()

ROOT = {"fps": FPS, "coords": "glTF(+Y 위, +Z 앞, 미터). 모든 동작은 0초에 Hips 수평 위치가 원점",
        "note": "end_hips = 끝날 때 Hips 수평 위치(다음 동작으로 넘길 때 사람 원점을 이만큼 옮김). path = 원점 이동 경로 [t, x, z](ROOT_EXTRACT 동작만, 클립에서 그만큼 뺌). walk_speed = 걷기 발 디딤 속도(m/s, +Z 방향)",
        "clips": {}}
out_acts = []
for nm, srcmap, dur in clip_plan():
    n = int(round(dur * FPS)) + 1; tl = np.linspace(0, dur, n); frames = tl * FPS
    act, cb = new_action(nm)
    hl = None
    for b in bones:
        sname, st0 = srcmap[b]
        q = sample(sname, st0 + tl, b, "rotation_quaternion", 4)
        if q is not None:
            q /= np.linalg.norm(q, axis=1, keepdims=True)
            for i in range(1, n):
                if np.dot(q[i], q[i - 1]) < 0: q[i] = -q[i]
            for i in range(4): put_curve(cb, f'pose.bones["{b}"].rotation_quaternion', i, frames, q[:, i], b)
        if b == HIPS:
            hl = sample(sname, st0 + tl, b, "location", 3)
    # Hips: 수평 위치(아마추어 공간 XY)를 0초에 원점으로, ROOT_EXTRACT면 수평 이동 전부를 경로로 뺌
    head = np.array([ML.translation + ML.to_3x3() @ Vector(l) for l in hl])
    shift = np.zeros_like(head)
    if nm in ROOT_EXTRACT: shift[:, :2] = head[:, :2]
    else: shift[:, :2] = head[0, :2]
    newhead = head - shift
    loc = np.array([ML3i @ (Vector(h) - ML.translation) for h in newhead])
    for i in range(3): put_curve(cb, f'pose.bones["{HIPS}"].location', i, frames, loc[:, i], HIPS)
    info = {"duration": round(float(dur), 4), "loop": nm in LOOP, "removed_offset": b2g([head[0, 0], head[0, 1], 0])[0::2],
            "end_hips": b2g(newhead[-1])[0::2], "hips_height": [round(float(newhead[:, 2].min()), 3), round(float(newhead[:, 2].max()), 3)]}
    if nm in CUT: info["cut_from_source_sec"] = list(CUT[nm])
    if nm in COMPOSITE: info["composite"] = {"upper": COMPOSITE[nm][0], "lower": SIT_BASE}
    if nm in ROOT_EXTRACT:
        k = max(1, FPS // 10)
        info["path"] = [[round(float(tl[i]), 3)] + b2g(shift[i])[0::2] for i in range(0, n, k)]
        info["end_hips"] = b2g(shift[-1] + newhead[-1] - newhead[0])[0::2]
    ROOT["clips"][nm] = info
    out_acts.append(act)
log("clips built", len(out_acts))
for k, a in src.items(): bpy.data.actions.remove(a)

# 걷기 속도·처음 방향: 실제 자세로 계산
ad = arm.animation_data or arm.animation_data_create()
def use_action(a):
    ad.action = a
    try: ad.action_slot = a.slots[0]
    except Exception: pass
body.modifiers[0].show_viewport = False   # 자세만 계산(빠르게)
for a in out_acts:
    use_action(a); sc.frame_set(0)
    lr = arm.pose.bones["mixamorig:LeftUpLeg"].head - arm.pose.bones["mixamorig:RightUpLeg"].head   # 몸의 오른쪽→왼쪽(쉬는 자세 +X)
    fwd = -Vector((0, 0, 1)).cross(lr)                                                                # 쉬는 자세에서 -Y(앞)
    ROOT["clips"][a.name]["yaw0_deg"] = round(math.degrees(math.atan2(fwd.x, -fwd.y)), 1)   # 0 = 정면, + = 왼쪽(위에서 반시계)
use_action(bpy.data.actions["Walking"])
nfr = int(ROOT["clips"]["Walking"]["duration"] * FPS); T, Lz, Ly, Rz, Ry = [], [], [], [], []
for f in range(nfr + 1):
    sc.frame_set(f); pb = arm.pose.bones
    l = pb["mixamorig:LeftToeBase"].head; r = pb["mixamorig:RightToeBase"].head
    Lz.append(l.z); Ly.append(l.y); Rz.append(r.z); Ry.append(r.y)
Lz, Ly, Rz, Ry = map(np.array, (Lz, Ly, Rz, Ry))
vL, vR = np.gradient(Ly) * FPS, np.gradient(Ry) * FPS
slow = np.where(np.abs(vL) < np.abs(vR), vL, vR)                      # 두 발 중 느린 발 = 디딤발(휘두르는 발은 두 배쯤 빠름)
ROOT["walk_speed"] = round(float(np.median(slow)), 3)                  # 디딤발이 뒤(+Y)로 미끄러지는 속도 = 앞으로 가는 속도(m/s, 실측 약 0.75)
ROOT["clips"]["Walking"]["walk_speed"] = ROOT["walk_speed"]
ad.action = None
body.modifiers[0].show_viewport = True
for a in out_acts:   # 내보내기(ACTIONS 모드)는 NLA 트랙의 동작을 하나씩 내보냄
    tr = ad.nla_tracks.new(); tr.name = a.name; s = tr.strips.new(a.name, 0, a); tr.mute = True
    try: s.action_slot = a.slots[0]
    except Exception: pass
json.dump(ROOT, open(os.path.join(OUT, "root_motion.json"), "w"), ensure_ascii=False, indent=1)
log("walk speed", ROOT["walk_speed"])

# ════════════════════════════════════════════════════════════════════ 3. 좌표: 기준 머리(master) ↔ 리깅 몸
objs_t, _ = import_glb(os.path.join(MESHY, "body_B3_textured.glb"))
ref = [o for o in objs_t if o.type == 'MESH'][0]
R0 = np.array([ref.matrix_world @ v.co for v in ref.data.vertices])
for o in objs_t: bpy.data.objects.remove(o)
me = body.data
P = np.array([v.co[:] for v in me.vertices])
s_rig = (P[:, 2].max() - P[:, 2].min()) / (R0[:, 2].max() - R0[:, 2].min())
off = (P.min(0) + P.max(0)) / 2 - s_rig * (R0.min(0) + R0.max(0)) / 2
map_err = float(np.abs(P - (s_rig * R0 + off)).max()) if len(P) == len(R0) else -1
mj = json.load(open(os.path.join(MESHY, "master/master_head.json"))); C = np.array(mj["center_body"]); Rr = mj["radius_body"]
K = s_rig * Rr / 0.5                                  # 기준 머리 1 = 리깅 K 미터
def rig2m(X): return ((np.asarray(X) - off) / s_rig - C) * (0.5 / Rr)
def m2rig(Q): return (np.asarray(Q) * (Rr / 0.5) + C) * s_rig + off
M2R = Matrix.Translation(Vector(off)) @ Matrix.Scale(s_rig, 4) @ Matrix.Translation(Vector(C)) @ Matrix.Scale(Rr / 0.5, 4)
def zb(z): return s_rig * z + off[2]                  # 몸(텍스처본) 높이 → 리깅 높이
NECK, HEM, ANK = zb(mj["neck_z_body"]), zb(-0.167), zb(-0.386)   # 문서 56(body_parts.py) 확정 경계
log("rig scale", round(s_rig, 4), "map_err", round(map_err, 5), "K", round(K, 4), "cuts", round(NECK, 3), round(HEM, 3), round(ANK, 3))

# ════════════════════════════════════════════════════════════════════ 4. 몸: 경계 자르기·재질 4개·명암 꼭짓점 색
img = base_image(body); TX = img_array(img); TW, TH_ = img.size
bm = bmesh.new(); bm.from_mesh(me)
for zc in (NECK, HEM, ANK):
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, zc), plane_no=(0, 0, 1))
bm.to_mesh(me); bm.free(); me.update()
uvd = me.uv_layers[0].data
def texel(uv): x = min(TW - 1, max(0, int(uv[0] * TW))); y = min(TH_ - 1, max(0, int(uv[1] * TH_))); return TX[y, x, :3]
def classify(rgb):
    r, g, b = rgb; mx, mn = max(rgb), min(rgb); sat = (mx - mn) / (mx + 1e-6)
    if b > r + 0.15 and sat > 0.35: return 1
    if r > b + 0.15 and sat > 0.2: return 0
    return 1
labels = []
for p in me.polygons:
    zc = p.center.z
    if zc >= NECK: labels.append(0); continue
    if zc < ANK: labels.append(3); continue
    if zc < HEM: labels.append(2); continue
    us = np.mean([uvd[li].uv[:] for li in p.loop_indices], axis=0)
    labels.append(0 if classify(texel(us)) == 0 else 1)          # 몸통·팔: 손만 피부
labels = np.array(labels)
bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
for _ in range(2):
    new = labels.copy()
    for f in bm.faces:
        if f.calc_center_median().z >= NECK or f.calc_center_median().z < HEM: continue
        nb = [labels[g.index] for e in f.edges for g in e.link_faces if g.index != f.index]
        if nb:
            vals, cnt = np.unique(nb, return_counts=True)
            if cnt.max() >= 2 and vals[cnt.argmax()] != labels[f.index]: new[f.index] = vals[cnt.argmax()]
    labels = new
bm.free()
BODY_MATS = ["skin", "top", "pants", "shoes"]
me.materials.clear()
for nm in BODY_MATS:
    m = bpy.data.materials.new(nm); m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = hexlin(DEF_COL[nm]) + [1]
    me.materials.append(m)
me.polygons.foreach_set("material_index", labels.astype(np.int32))
# 명암: 부위별 중간 밝기로 나눈 값(어둡게만, 0.8~1). 목 위(얼굴)는 1(Meshy가 칠한 눈 자국 버림)
lum_l = np.zeros(len(me.loops)); lab_l = np.zeros(len(me.loops), int); zl = np.zeros(len(me.loops))
for p in me.polygons:
    for li in p.loop_indices:
        lum_l[li] = float(lin(texel(uvd[li].uv)) @ np.array([0.2126, 0.7152, 0.0722])); lab_l[li] = labels[p.index]; zl[li] = p.center.z
shade = np.ones(len(me.loops))
for k in range(4):
    sel = (lab_l == k) & (zl < NECK)
    if sel.sum() > 10:
        r = np.clip((lum_l[sel] + 1e-3) / (np.median(lum_l[sel]) + 1e-3), 0.7, 1.15)
        shade[sel] = np.clip(1 - 0.7 * (1 - r), 0, 1)
ca = me.color_attributes.new("shade", 'FLOAT_COLOR', 'CORNER')
ca.data.foreach_set("color", np.column_stack([shade, shade, shade, np.ones_like(shade)]).ravel().astype(np.float32))
counts = {BODY_MATS[k]: int((labels == k).sum()) for k in range(4)}
log("body parts", counts, "shade range", round(float(shade.min()), 3), round(float(shade.max()), 3))

# ════════════════════════════════════════════════════════════════════ 5. 목 위는 Head 뼈 100%
vg = body.vertex_groups; head_g = vg["mixamorig:Head"]; BAND = 0.035
nv0 = sum(1 for v in me.vertices if not v.groups)
for v in me.vertices:
    z = v.co.z
    if z < NECK - BAND: continue
    t = float(smooth((z - (NECK - BAND)) / BAND))
    ws = {vg[g.group].name: g.weight for g in v.groups}
    tot = sum(ws.values()) or 1
    ws = {k: w / tot * (1 - t) for k, w in ws.items()}; ws["mixamorig:Head"] = ws.get("mixamorig:Head", 0) + t
    for g in list(v.groups): vg[g.group].remove([v.index])
    for k, w in ws.items():
        if w > 1e-4: vg[k].add([v.index], w, 'REPLACE')
headw = np.zeros(len(me.vertices))
for v in me.vertices:
    for g in v.groups:
        if g.group == head_g.index: headw[v.index] = g.weight
log("head-rigid verts", int((headw > 0.999).sum()), "unweighted before", nv0, "after", sum(1 for v in me.vertices if not v.groups))

# ════════════════════════════════════════════════════════════════════ 6. 모프: 체형·얼굴형
P = np.array([v.co[:] for v in me.vertices]); Hb = P[:, 2].max() - P[:, 2].min(); zmin = P[:, 2].min()
W = {}   # 뼈별 무게
for v in me.vertices:
    for g in v.groups: W.setdefault(vg[g.group].name, np.zeros(len(P)))[v.index] = g.weight
TORSO = {"mixamorig:Hips", "mixamorig:Spine", "mixamorig:Spine1", "mixamorig:Spine2", "mixamorig:Neck", "mixamorig:LeftShoulder", "mixamorig:RightShoulder"}
LIMB = {"mixamorig:LeftArm", "mixamorig:LeftForeArm", "mixamorig:RightArm", "mixamorig:RightForeArm", "Bone_024", "Bone_023", "Bone_019", "Bone_018",
        "mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:RightUpLeg", "mixamorig:RightLeg"}
below = np.clip((NECK - P[:, 2]) / (0.04 * Hb), 0, 1)
belly = np.exp(-((P[:, 2] - (zmin + 0.42 * Hb)) / (0.12 * Hb)) ** 2)
YC = float(arm.data.bones["mixamorig:Spine1"].head_local.y)
def build_disp(k):
    D = np.zeros_like(P); tot = np.zeros(len(P))
    for bn, w in W.items():
        if bn in TORSO:   # body_shapes.py 식(몸통 가운데 기준 가로·앞으로)
            d = np.zeros_like(P); f = k * (0.55 + 0.45 * belly)
            d[:, 0] = P[:, 0] * f
            d[:, 1] = (P[:, 1] - YC) * np.where(P[:, 1] < YC, k * (0.4 + 0.8 * belly), k * 0.4)
        elif bn in LIMB:  # 팔다리: 뼈 줄기 둘레로(뼈 위치는 그대로 → 손·소품이 안 어긋남)
            b = arm.data.bones[bn]; a_ = np.array(b.head_local[:]); c_ = np.array(b.tail_local[:]); ab = c_ - a_
            t = np.clip(((P - a_) @ ab) / (ab @ ab), 0, 1); cl = a_ + t[:, None] * ab
            d = (P - cl) * (0.6 * k)
        else:
            d = np.zeros_like(P)
        D += d * w[:, None]; tot += w
    D = D / np.maximum(tot, 1e-6)[:, None] * below[:, None]
    return D
Z_KEEP, Z_FULL = 0.02, -0.30                          # face_shapes.py 그대로(기준 머리 좌표)
def ramp(z): t = np.clip((Z_KEEP - z) / (Z_KEEP - Z_FULL), 0, 1); return t * t * (3 - 2 * t)
def f_slim(Q0):
    Q = Q0.copy(); w = ramp(Q0[:, 2]); Q[:, 0] *= 1 - 0.16 * w
    Q[:, 1] = np.where(Q0[:, 1] < 0, Q0[:, 1] * (1 - 0.06 * w), Q0[:, 1])
    cx = smooth(1 - np.abs(Q0[:, 0]) / 0.3); Q[:, 2] -= 0.04 * w * cx; return Q
def f_square(Q0):
    Q = Q0.copy(); w = ramp(Q0[:, 2]); front = np.clip((0.15 - Q0[:, 1]) / 0.35, 0, 1)
    ang = np.arctan2(Q0[:, 1], Q0[:, 0]); boxy = 1 / np.maximum(np.abs(np.cos(ang)), np.abs(np.sin(ang))) ** 0.3
    f = 1 + (boxy - 1) * w * front * 0.9; Q[:, 0] = Q0[:, 0] * f; Q[:, 1] = Q0[:, 1] * f
    under = np.clip((-0.25 - Q0[:, 2]) / 0.2, 0, 1); Q[:, 2] = Q0[:, 2] + 0.035 * under * front; return Q
def f_full(Q0):   # 11/10 85번 넓은 얼굴: 볼·턱을 옆으로, 턱 밑(목으로 좁아지는 자리)을 메워 턱선이 어깨로 이어지게, 턱 밑을 살짝 아래로(두 턱)
    Q = Q0.copy(); x, y, z = Q0[:, 0], Q0[:, 1], Q0[:, 2]; w = ramp(z)
    deep = smooth((FULL_DEEP[0] - z) / (FULL_DEEP[0] - FULL_DEEP[1])); front = np.clip((0.2 - y) / 0.5, 0, 1)
    Q[:, 0] = x * (1 + FULL_W[0] * w + FULL_W[1] * deep)
    Q[:, 1] = y * (1 + (FULL_Y[0] * w + FULL_Y[1] * deep) * front)
    Q[:, 2] = z - FULL_CHIN * deep * front * smooth(1 - np.abs(x) / 0.35); return Q
FULL_W, FULL_Y, FULL_DEEP, FULL_CHIN = (0.20, 0.20), (0.06, 0.12), (-0.28, -0.50), 0.045   # 기준 머리 좌표(반지름 0.5): 입 높이 -0.27, 턱끝 -0.41, 목 -0.52
def face_disp(X, fn, wgt):
    Qm = rig2m(X); return (m2rig(fn(Qm)) - X) * wgt[:, None]
DISP = {"build_chubby": build_disp(0.22), "build_slim": build_disp(-0.14),
        "face_slim": face_disp(P, f_slim, headw), "face_square": face_disp(P, f_square, headw), "face_full": face_disp(P, f_full, headw)}
body.shape_key_add(name="Basis")
for nm, d in DISP.items():
    sk = body.shape_key_add(name=nm); sk.data.foreach_set("co", (P + d).ravel())
log("morphs", {k: round(float(np.linalg.norm(d, axis=1).max()), 4) for k, d in DISP.items()})
KD_BODY = KDTree(len(P))
for i, p in enumerate(P): KD_BODY.insert(p, i)
KD_BODY.balance()
def transfer_morphs(o, names, reach=0.06, force=False):
    """부품 점마다 가까운 몸 점들의 모프 이동을 거리로 줄여 따라가게(턱 바뀌면 수염·긴 머리도 따라감)."""
    X = np.array([v.co[:] for v in o.data.vertices]); res = {}
    near = [KD_BODY.find_n(Vector(x), 6) for x in X]
    for nm in names:
        D = DISP[nm]; out = np.zeros_like(X)
        # 85번: 체형(듬직)은 어깨에 얹힌 머리 끝이 몸에서 조금 떨어져 있어도 몸만큼 같이 움직여야 안 뚫음(4 cm 까지 그대로, 12 cm 에서 0)
        r0, rr = (0.04, 0.08) if nm.startswith("build_") else (0.01, reach)
        for i, nn in enumerate(near):
            ds = np.array([n[2] for n in nn]); ix = [n[1] for n in nn]; w = 1 / (ds + 1e-3) ** 2
            fall = float(smooth(1 - (ds.min() - r0) / rr))
            out[i] = (D[ix] * w[:, None]).sum(0) / w.sum() * fall
        if (force and nm.startswith("face_")) or np.linalg.norm(out, axis=1).max() > 0.0015: res[nm] = out
    if res:
        if not o.data.shape_keys: o.shape_key_add(name="Basis")
        for nm, d in res.items():
            sk = o.shape_key_add(name=nm); sk.data.foreach_set("co", (X + d).ravel())
    return list(res)

# ════════════════════════════════════════════════════════════════════ 7. 얼굴 조각(앱이 그린 face.png를 받는 자리)
FACE_PHI, FACE_THETA = 1.8, 1.9; TH0 = math.pi / 2 - FACE_THETA / 2      # make_plaza_glb.py 와 같은 펼침(u: 좌→우, v: 위→아래)
Qm = rig2m(P); dn = Qm / np.linalg.norm(Qm, axis=1, keepdims=True)
th = np.arccos(np.clip(dn[:, 2], -1, 1)); ph = np.arctan2(-dn[:, 1], -dn[:, 0])
FU = (ph - math.pi / 2) / FACE_PHI + 0.5; FV = (th - TH0) / FACE_THETA
inrect = (FU > 0) & (FU < 1) & (FV > 0) & (FV < 1) & (headw > 0.999)
fsel = [p for p in me.polygons if all(headw[i] > 0.999 for i in p.vertices) and any(inrect[i] for i in p.vertices)]
vids = sorted({i for p in fsel for i in p.vertices}); vmap = {v: k for k, v in enumerate(vids)}
nrm = np.array([me.vertices[i].normal[:] for i in vids])
FP = P[vids] + nrm * 0.0025 * K
fme = bpy.data.meshes.new("face"); fme.from_pydata(FP.tolist(), [], [[vmap[i] for i in p.vertices] for p in fsel]); fme.update()
fuv = fme.uv_layers.new(name="UVMap")
for p in fme.polygons:
    for li in p.loop_indices:
        vi = vids[fme.loops[li].vertex_index]; fuv.data[li].uv = (FU[vi], 1 - FV[vi])
face = bpy.data.objects.new("face", fme); sc.collection.objects.link(face)
arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
for pb in arm.pose.bones: pb.matrix_basis = Matrix()
for p in fme.polygons: p.use_smooth = True
FACE_N = 256; ph_img = np.zeros((FACE_N, FACE_N, 4), np.float32); ph_img[..., :3] = enc(hexlin(DEF_COL["skin"])); ph_img[..., 3] = 1
fme.materials.append(simple_mat("face", image_from("face_placeholder", ph_img, os.path.join(OUT, "textures"))))
face.shape_key_add(name="Basis")
for nm, fn in (("face_slim", f_slim), ("face_square", f_square), ("face_full", f_full)):
    sk = face.shape_key_add(name=nm); sk.data.foreach_set("co", (FP + face_disp(FP, fn, np.ones(len(FP)))).ravel())
face.parent = arm; face.parent_type = 'BONE'; face.parent_bone = "mixamorig:Head"; bpy.context.view_layer.update(); face.matrix_world = Matrix()
log("face patch faces", len(fsel))

# ════════════════════════════════════════════════════════════════════ 8. 부품
arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
def attach(o, bone):
    Wm = o.matrix_world.copy(); o.parent = arm; o.parent_type = 'BONE'; o.parent_bone = bone
    bpy.context.view_layer.update(); o.matrix_world = Wm
def load_part(path):
    ob, _ = import_glb(path); ms = [o for o in ob if o.type == 'MESH']
    for o in ms:   # 원본 재질 이름이 새 재질 이름(glasses 등)을 차지해 '.001'이 붙지 않게
        for m in o.data.materials:
            if m and not m.name.startswith("src_"): m.name = "src_" + m.name
    for o in ob:
        if o.type != 'MESH': bpy.data.objects.remove(o)
    return ms
PARTS = {}
os.makedirs(os.path.join(OUT, "textures"), exist_ok=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import char_fix_hair
def finish(o, nm, bone, info, morphs):
    o.name = nm; o.data.name = nm
    for p in o.data.polygons: p.use_smooth = True
    o.matrix_world = Matrix(); attach(o, bone)
    info["bone"] = bone; info["morphs"] = transfer_morphs(o, morphs, force=nm in FORCE_FACE_MORPHS) if morphs else []
    PARTS[nm] = info; log("part", nm, info)
HEAD_MORPHS = ["face_slim", "face_square", "face_full"]
def head_part(path, nm, tris, N, more=()):
    o = load_part(path); assert len(o) == 1; o = o[0]
    info = prep_part(o, nm, tris, N, "tint")
    o.data.transform(M2R)
    if nm in char_fix_hair.SHORTEN: info["shorten"] = char_fix_hair.shorten(o.data, **char_fix_hair.SHORTEN[nm])   # 발목까지 긴 머리 → 허리
    finish(o, nm, "mixamorig:Head", info, HEAD_MORPHS + list(more))
for w in WIGS: head_part(os.path.join(MESHY, "wigs_pro/final_mv", w + ".glb"), "hair_" + w, WIG_TRIS, WIG_TEX, ["build_chubby"])   # 85번: 어깨에 닿는 머리 끝은 듬직 어깨를 따라감(안 뚫게)
head_part(os.path.join(MESHY, "parts_mv/out/m_bald.glb"), "hair_m_bald", WIG_TRIS, WIG_TEX)
head_part(os.path.join(MESHY, "parts_mv/out/b_long.glb"), "beard_long", 2000, PART_TEX, ["build_chubby"])
head_part(os.path.join(MESHY, "parts_mv/out/b_mus.glb"), "beard_mus", 1000, PART_TEX)
o = load_part(os.path.join(MESHY, "parts_mv/out/p_scarf.glb"))[0]
info = prep_part(o, "scarf", 1500, PART_TEX, "tint"); o.data.transform(M2R)
finish(o, "scarf", "mixamorig:Spine2", info, ["build_chubby", "build_slim"] + HEAD_MORPHS)
gm = None
for o in load_part(os.path.join(MESHY, "glasses/glasses.glb")):
    nm = o.name.split(".")[0]
    info = prep_part(o, nm, 1200, 0, "plain"); o.data.transform(M2R)
    if gm is None: gm = simple_mat("glasses")
    o.data.materials.clear(); o.data.materials.append(gm)
    finish(o, nm, "mixamorig:Head", info, HEAD_MORPHS)

# 손 소품: Sit_and_Drink에서 오른손이 컵을 드는 자세 기준으로 손바닥 안쪽에 세워 둠 → RightHand 뼈 자식(앱이 필요할 때만 보이기)
arm.data.pose_position = 'POSE'
use_action(bpy.data.actions["Sit_and_Drink"])
HOLD_T = float(arg("--hold-t", "2.0")); sc.frame_set(int(HOLD_T * FPS)); bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get(); be = body.evaluated_get(dg); em = be.to_mesh()
PP = np.array([v.co[:] for v in em.vertices]); be.to_mesh_clear()
hw = W.get("mixamorig:RightHand", 0) + W.get("Bone_036", 0)
hand = PP[np.asarray(hw) > 0.6]; hc = hand.mean(0); hr = float(np.linalg.norm(hand - hc, axis=1).mean())
chest = np.array(arm.pose.bones["mixamorig:Spine2"].head[:])
inward = chest - hc; inward[2] = 0; inward /= np.linalg.norm(inward)
B_pose = arm.matrix_world @ arm.pose.bones["mixamorig:RightHand"].matrix
arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
B_rest = arm.matrix_world @ arm.pose.bones["mixamorig:RightHand"].matrix
yaw = math.atan2(inward[0], -inward[1])
# 컵: lift·tip = 손 위쪽·손끝 쪽으로 조금(손이 컵 아래쪽을 쥠 → 마실 때 테두리가 입까지 닿게)
PROPS = {"cup": dict(n=1200, push=0.55, rot=(0, 0, 0), lift=0.035, tip=0.015), "book": dict(n=1200, push=0.35, rot=(0, 0, math.pi / 2)), "phone": dict(n=1200, push=0.3, rot=(0, 0, math.pi / 2))}
for nm, cfg in PROPS.items():
    o = load_part(os.path.join(MESHY, f"parts_mv/out/p_{nm}.glb"))[0]
    info = prep_part(o, "prop_" + nm, cfg["n"], PART_TEX, "color")
    X = np.array([v.co[:] for v in o.data.vertices]); cen = (X.min(0) + X.max(0)) / 2
    o.data.transform(Matrix.Translation(Vector(-cen))); half = (X.max(0) - X.min(0)) / 2 * K
    # 소품 크기는 기준 머리 좌표(prop_prep.py) → K배. 손 공 안쪽(몸 쪽)에 반쯤 묻히게
    pos = hc + inward * (hr + float(min(half[0], half[1])) * cfg["push"])
    pos = pos + np.array([0, 0, cfg.get("lift", 0.0)]) + np.array(B_pose.to_3x3().col[1].normalized()) * cfg.get("tip", 0.0)
    Wp = Matrix.Translation(Vector(pos)) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(cfg["rot"][2], 4, 'Z') @ Matrix.Scale(K, 4)
    o.data.transform(Wp)                                  # 붙잡는 자세의 세계 위치
    o.data.transform(B_rest @ B_pose.inverted())          # 같은 손 기준으로 쉬는 자세로 되돌림
    info["hold_pose"] = f"Sit_and_Drink@{HOLD_T}s"
    finish(o, "prop_" + nm, "mixamorig:RightHand", info, None)
ad.action = None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import char_fix_clips; char_fix_clips.fix_clips(arm, body, out_acts, FPS, log, m2rig(np.zeros(3)), OUT)   # 큰 머리: 손·팔·컵이 머리(+머리카락) 속으로 안 들어가게 동작 고치기
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import char_fix_hair; char_fix_hair.apply(arm, body, PARTS, OUT, log, out_acts)   # 긴 머리·수염·목도리: 몸 뚫림 고치기(밀어내기 + 뼈 무게)

# ════════════════════════════════════════════════════════════════════ 9. 내보내기 + 손질
while me.uv_layers: me.uv_layers.remove(me.uv_layers[0])   # 몸은 텍스처 없음(색은 재질, 명암은 꼭짓점 색)
for o in list(bpy.data.objects):
    if o.type == 'MESH' and o.parent is None and o is not body: bpy.data.objects.remove(o)
for p in me.polygons: p.use_smooth = True
for pb in arm.pose.bones: pb.matrix_basis = Matrix()
arm.data.pose_position = 'POSE'
sc.render.fps = FPS; sc.render.fps_base = 1
for x in bpy.context.selected_objects: x.select_set(False)
sel = [arm, body, face] + [bpy.data.objects[n] for n in PARTS]
for o in sel: o.select_set(True)
bpy.context.view_layer.objects.active = arm
GLB = os.path.join(OUT, "plaza_char2.glb")
bpy.ops.export_scene.gltf(filepath=GLB, export_format='GLB', use_selection=True, export_animations=True, export_animation_mode='ACTIONS',
                          export_force_sampling=True, export_frame_step=1, export_optimize_animation_size=True, export_morph=True, export_morph_normal=True,
                          export_skins=True, export_def_bones=False, export_vertex_color='NAME', export_vertex_color_name='shade',
                          export_all_vertex_colors=False, export_tangents=False, export_image_format='AUTO', export_yup=True, export_apply=False,
                          export_texcoords=True, export_normals=True, export_extras=False, export_cameras=False, export_lights=False)
size0 = os.path.getsize(GLB)
dropped = glb_fix(GLB)
log("exported", size0, "→", os.path.getsize(GLB), "dropped channels", dropped)

# 요약
J, Bn = glb_read(GLB)
def tex_bytes(n): return int(n * n * 4 * 4 / 3)
tex = [];
for im in J.get("images", []):
    if im.get("uri") == "face.png": tex.append(("face.png(app)", FACE_N)); continue
    tex.append((im.get("name"), None))
anim = []
for a in J["animations"]:
    t = max(J["accessors"][s["input"]]["max"][0] for s in a["samplers"])
    paths = sorted({c["target"]["path"] for c in a["channels"]})
    anim.append({"name": a["name"], "sec": round(t, 3), "channels": len(a["channels"]), "paths": paths})
tri_body = tri_count(body)
worst = {"body": tri_body, "face": tri_count(face)}
hair_max = max((v["tris"], k) for k, v in PARTS.items() if k.startswith("hair_"))
worst.update({hair_max[1]: hair_max[0], "beard_long": PARTS["beard_long"]["tris"], "glasses(max)": max(PARTS[g]["tris"] for g in ("glasses_round", "glasses_square", "glasses_half")),
              "scarf": PARTS["scarf"]["tris"], "prop(max)": max(PARTS[p]["tris"] for p in ("prop_cup", "prop_book", "prop_phone"))})
texsz = {k: v.get("tex") for k, v in PARTS.items() if v.get("tex")}
REPORT = {"glb": GLB, "bytes": os.path.getsize(GLB), "rig_scale": s_rig, "K_master_to_rig": K, "map_err": map_err,
          "cuts_rig_z": {"neck": NECK, "hem": HEM, "ankle": ANK}, "body_faces_per_material": counts,
          "body_morphs": list(DISP), "face_morphs": HEAD_MORPHS, "parts": PARTS, "animations": anim,
          "worst_case_tris": worst, "worst_case_total": sum(worst.values()),
          "textures": texsz, "texture_decoded_MB_incl_mips": round(sum(tex_bytes(n) for n in texsz.values()) / 2 ** 20, 2),
          "face_texture_per_person_MB": round(tex_bytes(FACE_N) / 2 ** 20, 2),
          "dropped_channels": dropped, "source_nonhips_loc_max": dev["loc"], "source_scale_dev_max": dev["scale"],
          "old_hair_index_to_node": [{"old": i, "name": n, "node": nd} for i, (n, nd) in enumerate(OLD_HAIR)],
          "new_hair_append": [{"new": len(OLD_HAIR) + i, "name": n, "node": nd} for i, (n, nd) in enumerate(NEW_HAIR_APPEND)]}
json.dump(REPORT, open(os.path.join(OUT, "build_report.json"), "w"), ensure_ascii=False, indent=1)
log("worst tris", REPORT["worst_case_total"], worst, "tex MB", REPORT["texture_decoded_MB_incl_mips"])
if APP:
    import shutil; shutil.copyfile(GLB, APP); log("app asset →", APP)
log("DONE")
