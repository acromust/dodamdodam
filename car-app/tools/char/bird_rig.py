# 도담도담 광장 새: Meshy 텍스처 새(pr_bird)를 다듬고 뼈를 넣어 움직이게 한다(나무에 앉아 고개 돌리기·쪼기·뛰기, 가로등까지 날기).
#  - 소품 정리: 색 맞추기(prop_prep --recolor 방식) → 점 붙이기 → 면 수 줄이기 → 부리가 앞(-Y, 렌더 front 쪽) → 길이(부리~꼬리) --size
#    → 새 UV(여백 있게)에 원본 고면에서 색만 구움(Meshy 아틀라스 이음매 번짐 없앰) → 날개는 단단한 조각으로 떼고 몸 옆구리는 매끈하게
#  - Meshy 다리가 2×2 넷이라 뒤쪽 둘을 지움(--keep4legs 로 끔)
#  - 원점 = 두 발 사이 바닥. 앱은 이 점을 가지 위(BIRD_PERCH)에 놓는다
#  - 뼈: bird_root(다리) → bird_body → bird_head / bird_wingL / bird_wingR / bird_tail. 무게는 점 위치로 계산(같은 자리 점은 같은 무게라 UV 이음매가 벌어지지 않음)
#  - 동작(30fps, 앱이 이름으로 틂): idle_breathe · head_turn · peck · hop · flap · takeoff · land. 뿌리 뼈는 위아래로만 움직임(앞뒤·옆 이동은 앱이 길 따라)
#  - 확인: 내보낸 GLB를 다시 불러 동작마다 4장씩 3/4 시점 렌더(줄 = 동작) + 정면·옆·뒤·위45
# 실행: Blender -b --factory-startup -P bird_rig.py -- --in TEX.glb --out OUT --name pr_bird [--faces 3000] [--size 0.3] [--tex 512] [--norender] [--samples 24] [--cell 256] [--keep4legs]
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector, Quaternion, Matrix
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
IN, OUT, NAME = arg("--in"), arg("--out"), arg("--name", "pr_bird")
NF, SIZE, TEX = int(arg("--faces", "3000")), float(arg("--size", "0.3")), int(arg("--tex", "512"))
FPS = 30
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=IN)
ms = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
for o in bpy.context.selected_objects: o.select_set(False)
for o in ms: o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
if len(ms) > 1: bpy.ops.object.join()
o = bpy.context.view_layer.objects.active; bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for x in [x for x in bpy.data.objects if x not in before and x.type != 'MESH']: bpy.data.objects.remove(x)
me = o.data

# ── 텍스처: 새는 화면에서 아주 작아서 512면 충분(Pleos RAM 400MB 예산). 색은 앱 팔레트로(prop_prep --recolor 와 같은 방식) ──
import tempfile
TMP = tempfile.mkdtemp()
def _swap(img, ext):   # 고친 그림을 파일로 저장→다시 불러 노드에 끼움(내보내기가 그 파일을 그대로 씀)
    fn = os.path.join(TMP, img.name.replace("/", "_") + ext); img.file_format = 'PNG' if ext == '.png' else 'JPEG'
    try: img.save(filepath=fn, quality=90)
    except TypeError: img.filepath_raw = fn; img.save()
    ni = bpy.data.images.load(fn); ni.colorspace_settings.name = img.colorspace_settings.name
    for m in me.materials:
        for nd in (m.node_tree.nodes if m and m.use_nodes else []):
            if nd.type == 'TEX_IMAGE' and nd.image == img: nd.image = ni
    return ni
def _lab(c):   # sRGB(0~1) → CIE Lab(D65)
    l = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    x = l @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(x > 0.008856, np.cbrt(x), 7.787 * x + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)
def _srgb(L):   # Lab → sRGB(0~1)
    fy = (L[:, 0] + 16) / 116; f = np.stack([fy + L[:, 1] / 500, fy, fy - L[:, 2] / 200], 1)
    x = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    l = x @ np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]]).T
    l = np.clip(l, 0, 1); return np.where(l <= 0.0031308, 12.92 * l, 1.055 * l ** (1 / 2.4) - 0.055)
def _w(L, sel):   # 조건 범위 안 1, 밖으로 서서히 0 (h 색상각 ±8, C 채도 ±5, L 밝기 ±5)
    w = np.ones(len(L)); C = np.hypot(L[:, 1], L[:, 2]); H = np.degrees(np.arctan2(L[:, 2], L[:, 1])) % 360
    for cnd in sel.split("+"):
        k, (a, b) = cnd[0], map(float, cnd[1:].split("-")); v, fe = {"h": (H, 8.0), "C": (C, 5.0), "L": (L[:, 0], 5.0)}[k]
        d = np.maximum(a - v, v - b) if k != "h" else np.minimum.reduce([np.maximum(a - x, x - b) for x in (v, v - 360, v + 360)])
        w *= np.clip(1 - d / fe, 0, 1) ** 2 * (3 - 2 * np.clip(1 - d / fe, 0, 1))
    return w
# 등·머리·날개 차콜(Meshy #282828) → #4A4E55, 배 흰색 → #F4F4F2, 부리·다리 갈색 → #B58A64. 눈(#080808, L≈2)은 L 범위 밖이라 그대로 검정
RECOLOR = arg("--recolor", "C0-12+L10-45>#4A4E55;C0-12+L80-100>#F4F4F2;h40-95+C18-999>#B58A64")
recolor_rep = []
uv = me.uv_layers.active.data; U = np.empty(len(uv) * 2); uv.foreach_get("uv", U); U = U.reshape(-1, 2)
ar = np.empty(len(me.polygons)); me.polygons.foreach_get("area", ar)
lt = np.empty(len(me.polygons), np.int64); me.polygons.foreach_get("loop_total", lt); la = np.repeat(ar / lt, lt)
bc = []
for m in me.materials:
    for nd in (m.node_tree.nodes if m and m.use_nodes else []):
        if nd.type == 'BSDF_PRINCIPLED':
            for ln in nd.inputs['Base Color'].links:
                if ln.from_node.type == 'TEX_IMAGE' and ln.from_node.image not in bc: bc.append(ln.from_node.image)
for img in bc:
    W, H = img.size; px = np.empty(W * H * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(-1, 4)
    Lx = _lab(px[:, :3].astype(np.float64)); out = Lx.copy()
    si = (np.floor(U[:, 1] % 1 * H).astype(int).clip(0, H - 1)) * W + np.floor(U[:, 0] % 1 * W).astype(int).clip(0, W - 1)
    for rule in RECOLOR.split(";"):
        sel, hx = rule.split(">"); T = _lab(np.array([[int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]]))[0]
        ws = _w(Lx[si], sel) * la; mean = (Lx[si] * ws[:, None]).sum(0) / max(ws.sum(), 1e-12)
        out += _w(Lx, sel)[:, None] * (T - mean)
        hexo = lambda L: '#%02X%02X%02X' % tuple((_srgb(L[None])[0] * 255).round().astype(int))
        recolor_rep.append({"sel": sel, "to": hx, "share": round(float(ws.sum() / la.sum()), 3), "before": hexo(mean)})
    px[:, :3] = _srgb(out); img.pixels.foreach_set(px.ravel()); img.update(); _swap(img, '.png')

# ── 다리 넷 → 둘: Meshy 가 다리를 2×2(앞뒤 두 쌍)로 만듦(앞에서 둘, 옆에서 둘로 보여 겉보기엔 둘 같지만 3/4 시점에서 다리 넷). 뒤쪽 쌍을 지움 ──
#  배 바로 아래(발바닥 위 키의 11.2%)까지 지우고 남은 짧은 그루터기 구멍은 배 흰색으로 막음(9.5%에서 자르면 갈색 그루터기가 옆·아래에서 보였음)
if '--keep4legs' not in argv:
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5); bm.faces.ensure_lookup_table()   # 점 붙이기(UV는 모서리마다 그대로)
    uvh = bm.loops.layers.uv.active
    Ph = np.array([v.co[:] for v in bm.verts]); lo_h, hi_h = Ph.min(0), Ph.max(0); Hh = hi_h[2] - lo_h[2]
    fz = Ph[Ph[:, 1] < lo_h[1] + .05 * (hi_h[1] - lo_h[1]), 2].mean(); bz = Ph[Ph[:, 1] > hi_h[1] - .05 * (hi_h[1] - lo_h[1]), 2].mean()
    back_sign = 1 if fz > bz else -1                     # 꼬리 쪽 y 부호(부리 반대)
    sole = Ph[Ph[:, 2] < lo_h[2] + .03 * Hh]; my = np.median(sole[:, 1])
    pegs = []
    for sx in (1, -1):
        for sy in (1, -1):
            m = (np.sign(sole[:, 0] - np.median(sole[:, 0])) == sx) & (np.sign(sole[:, 1] - my) == sy)
            if m.any(): pegs.append((sole[m, :2].mean(0), sy))
    zcut = lo_h[2] + float(arg('--legcut', '.112')) * Hh; rr = .07 * Hh
    if len(pegs) == 4 and abs(pegs[0][0][1] - pegs[1][0][1]) > rr:
        backs = [c_ for c_, sy in pegs if sy == back_sign]
        tan_uv = None
        kill = []
        for f in bm.faces:
            cc = f.calc_center_median()
            if cc.z < zcut and any(np.hypot(cc.x - b_[0], cc.y - b_[1]) < rr for b_ in backs): kill.append(f)
        # 막는 색: 배 아래 가운데 흰 면의 UV
        tan_uv, bb_ = None, 1e9
        for f in bm.faces:
            cc = f.calc_center_median()
            if cc.z > zcut and abs(cc.x) < .05 * Hh:
                d = abs(cc.z - (zcut + .06 * Hh)) + abs(cc.y - my)
                if d < bb_: bb_ = d; tan_uv = f.loops[0][uvh].uv.copy()
        edges_k = {e for f in kill for e in f.edges}
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        bnd_h = [e for e in edges_k if e.is_valid and e.is_boundary]
        fl = bmesh.ops.holes_fill(bm, edges=bnd_h, sides=0)
        fl = bmesh.ops.poke(bm, faces=fl["faces"])   # 가운데 점을 배 안쪽(위)으로 들여 막음 → 평평한 뚜껑이 휜 구멍 밖으로 삐져나오지 않게
        for v in fl["verts"]: v.co.z += .04 * Hh
        for f in fl["faces"]:
            for lp in f.loops: lp[uvh].uv = tan_uv
        bm.to_mesh(me); me.update(); print("LEGS removed back pair:", len(kill), "faces, caps", len(fl["faces"]))
    bm.free()

# ── 낮은 면 복사본 만들기: 점 붙이기 → 면 줄이기. 날개는 뒤에서 한 벌 더 떼어 내므로 그만큼(약 13%) 덜 남김 ──
#  Meshy 아틀라스는 조각 사이 틈이 없어(차콜 조각 옆에 갈색·흰 조각) 512로 줄이고 면을 줄이면 이음매마다 갈색·흰 점이 번짐
#  → 낮은 면 모델에 새 UV(조각 사이 여백)를 펴고, 원본(고면+원본 텍스처)에서 색만 구워 옮긴다(이음매 번짐·찢김 없음)
hi_o = o; hi_o.name = NAME + "_hi"
o = hi_o.copy(); o.data = hi_o.data.copy(); bpy.context.scene.collection.objects.link(o); me = o.data
bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5); bm.to_mesh(me); bm.free(); me.update()
f0 = len(hi_o.data.polygons)
WING_SHARE = 0.10
for ob in bpy.context.selected_objects: ob.select_set(False)
bpy.context.view_layer.objects.active = o; o.select_set(True)
dm = o.modifiers.new("dec", 'DECIMATE'); dm.ratio = NF * (1 - WING_SHARE) / len(me.polygons); bpy.ops.object.modifier_apply(modifier="dec")

# ── 방향·크기·원점: Meshy 새는 이미 부리가 -Y(렌더 front 카메라 쪽), 위가 +Z. 길이(Y) = SIZE, 원점 = 두 발바닥 사이 ──
P0 = np.array([v.co[:] for v in me.vertices]); lo, hi = P0.min(0), P0.max(0)
front_z = P0[P0[:, 1] < lo[1] + .05 * (hi[1] - lo[1]), 2].mean(); back_z = P0[P0[:, 1] > hi[1] - .05 * (hi[1] - lo[1]), 2].mean()
FLIP = front_z < back_z   # 부리(앞 끝)가 꼬리 끝보다 높아야 정상. 반대면 Z축으로 180도
if FLIP: P0[:, :2] *= -1; lo, hi = P0.min(0), P0.max(0)
s = SIZE / float(hi[1] - lo[1])
feet = P0[P0[:, 2] < lo[2] + .06 * (hi[2] - lo[2])]
c = np.array([(lo[0] + hi[0]) / 2, (feet[:, 1].min() + feet[:, 1].max()) / 2, lo[2]])
K = 1.903 / float(hi[1] - lo[1])   # 아래 무게·뼈 자리는 Meshy 원본 치수(부리~꼬리 1.903, 몸 가운데 높이 ≈ 0, 발바닥 -.857)로 적어 둠
def Lo(x, y, z):   # 원본 치수 좌표 → 최종 좌표
    return Vector(((np.array([x, y, z]) / K + np.array([c[0], 0, 0]) - c) * s).tolist())
def place(ob):     # 고면·저면 똑같이 옮김
    Q = np.array([v.co[:] for v in ob.data.vertices])
    if FLIP: Q[:, :2] *= -1
    Q = (Q - c) * s; ob.data.vertices.foreach_set("co", Q.ravel().astype(np.float32)); ob.data.update()
place(o); place(hi_o)
for ob in bpy.context.selected_objects: ob.select_set(False)
o.select_set(True); bpy.context.view_layer.objects.active = o; bpy.ops.object.shade_smooth()
o.name = NAME; me.name = NAME

# ── 새 UV + 색 굽기(고면 → 저면, 색만. 빛·그림자 없음) ──
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.02); bpy.ops.object.mode_set(mode='OBJECT')
bimg = bpy.data.images.new(NAME + "_col", TEX, TEX, alpha=False); bimg.generated_color = (0.29, 0.31, 0.33, 1)
mat = bpy.data.materials.new(NAME); mat.use_nodes = True; nt = mat.node_tree
bsdf = [n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'][0]; bsdf.inputs['Roughness'].default_value = .8; bsdf.inputs['Metallic'].default_value = 0
tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = bimg; nt.nodes.active = tn
me.materials.clear(); me.materials.append(mat)
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 4; sc.cycles.device = 'CPU'
for ob in bpy.context.selected_objects: ob.select_set(False)
hi_o.select_set(True); o.select_set(True); bpy.context.view_layer.objects.active = o
bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, use_selected_to_active=True, cage_extrusion=.012 * SIZE, max_ray_distance=.05 * SIZE, margin=6)
nt.links.new(tn.outputs['Color'], bsdf.inputs['Base Color'])
fn = os.path.join(TMP, NAME + "_col.png"); bimg.file_format = 'PNG'; bimg.filepath_raw = fn; bimg.save(); bimg.source = 'FILE'; bimg.reload()
for i in [i for i in bpy.data.images if i != bimg]: bpy.data.images.remove(i)
for m_ in [m_ for m_ in bpy.data.materials if m_ != mat]: bpy.data.materials.remove(m_)
hm = hi_o.data; bpy.data.objects.remove(hi_o); bpy.data.meshes.remove(hm)
f_dec = len(me.polygons)

# ── 뼈 자리(원본 치수. 부리 끝 y -.95·꼬리 끝 +.95, 발바닥 z -.857, 몸 아래 -.62, 정수리 +.86, 날개 = |x| .62~.82·y -.5~.44·z -.45~.32) ──
#  몸은 목이 따로 없는 둥근 한 덩어리 → 머리 = 날개 윗선(눈 아래)부터 위쪽 반구. 날개 = 몸 옆에 붙은 납작한 타원
FY = float(c[1] * K)   # 두 발 가운데 y(원본 치수)
BONES = {   # 이름: (머리, 꼬리, 부모)
    "bird_root":  ((0, FY, -.857), (0, FY, -.6), None),
    "bird_body":  ((0, -.05, -.62), (0, -.05, .1), "bird_root"),
    "bird_head":  ((0, -.12, .08), (0, -.12, .8), "bird_body"),
    "bird_tail":  ((0, .5, -.12), (0, .95, .14), "bird_body"),
    "bird_wingL": ((.6, -.12, .26), (.74, .25, -.32), "bird_body"),    # 새 기준 왼쪽 = +X(부리가 -Y를 봄). 머리 = 어깨(날개 윗끝)
    "bird_wingR": ((-.6, -.12, .26), (-.74, .25, -.32), "bird_body"),
}
def ss(a, b, v):   # a→b 사이 0→1 부드럽게(a>b 면 반대 방향)
    t = np.clip((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)
def to_src(Q):     # 최종 좌표 → 원본 치수 좌표
    Q = Q / s + c - np.array([c[0], 0, 0]); return Q * K
def wing_w(A):     # 날개 정도(0~1): 옆 타원 안, 몸 표면보다 바깥
    x, y, z = A[:, 0], A[:, 1], A[:, 2]; rE = np.sqrt(((y + .04) / .50) ** 2 + ((z + .07) / .41) ** 2)
    return ss(.55, .63, np.abs(x)) * (1 - ss(.92, 1.06, rE)), rE

# ── 날개 떼기: 날갯짓(110도)에서 몸에 붙은 면이 막처럼 늘어나 흰 배 무늬가 찢겨 보임(1차 시험) → 날개는 단단한 조각으로 ──
#  0) 날개 둘레 고리(날개 바로 바깥 옆구리)로 '날개 없는 몸 옆면' x = f(y, z) 를 타원면으로 맞춤(날개 가운데에서 몸 .69, 날개 겉 .82)
#  1) 날개 = 그 면보다 .02 넘게 튀어나온 면(옆 타원 안). 한쪽에 가장 큰 덩어리 하나만 → 복사해 떨어진 조각으로, 열린 안쪽은 평평한 뚜껑(차콜, 각진 면)
#  2) 원래 자리의 몸 면은 테두리만 남기고 f - .005 까지 눌러 넣음(더 깊으면 펼쳤을 때 분화구 둑처럼 보임) → 날개를 펴면 매끈한 차콜 옆구리(구멍·유령 날개 없음)
#     (테두리를 다듬거나 몸 쪽 둘레까지 누르면 둘레 면이 접히고 굽기 찌꺼기가 톱니 띠로 보였음 → 하지 않음)
#  3) 날개 조각은 날개 뼈에 무게 1(늘어남 없음), 몸은 날개 무게 0
Pm = np.array([v.co[:] for v in me.vertices]); A = to_src(Pm)
x, y, z = A[:, 0], A[:, 1], A[:, 2]
_, rE = wing_w(A)
ring = (np.abs(x) > .3) & (rE > 1.15) & (rE < 1.7) & (z > -.58)
Bq = A[ring]; Mx = np.stack([Bq[:, 0] ** 2, Bq[:, 1] ** 2, Bq[:, 2] ** 2, Bq[:, 1], Bq[:, 2], Bq[:, 1] * Bq[:, 2]], 1)
qf = np.linalg.lstsq(Mx, np.ones(len(Bq)), rcond=None)[0]   # 타원면 a·x² + b·y² + c·z² + d·y + e·z + f·yz = 1 (1차식 x = f(y,z) 는 날개 쪽으로 부풀게 뻗어 틀림)
def side_x(y_, z_): return np.sqrt(np.clip((1 - qf[1] * y_ ** 2 - qf[2] * z_ ** 2 - qf[3] * y_ - qf[4] * z_ - qf[5] * y_ * z_) / qf[0], 0, None))
print("WINGFIT ring", int(ring.sum()), "x(center) =", round(float(side_x(-.04, -.07)), 3), "fit err", round(float(np.abs(side_x(Bq[:, 1], Bq[:, 2]) - np.abs(Bq[:, 0])).mean()), 4))
def to_fin(a_): return Vector(((a_ / K + np.array([c[0], 0, 0]) - c) * s).tolist())
bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table()
uvl = bm.loops.layers.uv.active
FC = to_src(np.array([f.calc_center_median()[:] for f in bm.faces]))
_, frE = wing_w(FC)
prot = np.abs(FC[:, 0]) - side_x(FC[:, 1], FC[:, 2])
cand = set(i for i in np.nonzero((prot > .02) & (frE < 1.15) & (np.abs(FC[:, 0]) > .4))[0])
wfaces = []
for sgn in (1, -1):   # 한쪽에 가장 큰 연결 덩어리만(떨어진 부스러기 면 빼기)
    pool = {i for i in cand if FC[i, 0] * sgn > 0}; best_c = []
    while pool:
        st = [pool.pop()]; cc_ = []
        while st:
            i = st.pop(); cc_.append(i)
            for e in bm.faces[i].edges:
                for g in e.link_faces:
                    if g.index in pool: pool.discard(g.index); st.append(g.index)
        if len(cc_) > len(best_c): best_c = cc_
    wfaces += [bm.faces[i] for i in best_c]
dup = bmesh.ops.duplicate(bm, geom=wfaces); nf = [g for g in dup["geom"] if isinstance(g, bmesh.types.BMFace)]
cap_uv = None; best = 1e9
for f in nf:   # 뚜껑 색: 날개 바깥 가운데 면의 UV(조각 안쪽이라 번짐 없음)
    cc = to_src(np.array([f.calc_center_median()[:]]))[0]
    d = abs(abs(cc[0]) - .8) + abs(cc[1] + .04) + abs(cc[2] + .07)
    if d < best: best = d; cap_uv = f.loops[0][uvl].uv.copy()
bnd = [e for e in {e for f in nf for e in f.edges} if e.is_boundary]
fill = bmesh.ops.holes_fill(bm, edges=bnd, sides=0)
# 뚜껑 = 테두리에서 가운데 한 점으로 모이는 부채꼴. 가운데 점은 몸 쪽으로 .06 들임(평평하게 채우면 휜 테두리 위쪽에서 삼각형이 겉으로 삐져나와 검은 이빨처럼 보였음)
pk = bmesh.ops.poke(bm, faces=fill["faces"])
for v in pk["verts"]:
    a_ = to_src(np.array([v.co[:]]))[0]; a_[0] -= np.sign(a_[0]) * .06; v.co = to_fin(a_)
caps = pk["faces"]
for f in caps: f.smooth = True   # 뚜껑 안은 부드럽게(각지면 펼친 날개 밑이 검은 부채살로 보임). 테두리 모서리만 각지게
# 날개 조각·뚜껑·날개 자리 몸 면은 모두 차콜 한 점 색(날개는 원래 통 차콜. 몸과 맞닿은 홈에 구운 색은 흰·검정 톱니 찌꺼기라 펼치면 보였음)
for f in nf + caps + wfaces:
    for lp in f.loops: lp[uvl].uv = cap_uv
wing_verts = {v for f in nf + caps for v in f.verts}
for e in bnd: e.smooth = False   # 뚜껑 테두리는 각지게(날개 겉면 그림자가 뚜껑 쪽으로 번지지 않게)
# 몸 눌러 넣기: 날개 자리(복사한 면)의 몸 점 중 테두리가 아닌 점만 옆면 f - .005 까지. 테두리 점은 그대로 둬서
#  쉬는 자세는 원본과 똑같고(날개 조각 테두리 = 몸 테두리, 틈·겹침 없음), 테두리 밖 몸 면은 손대지 않음(굽기 이음 무늬가 드러나지 않게)
foot = {v for f in wfaces for v in f.verts}; rim = {v for f in wfaces for v in f.verts if any(g not in set(wfaces) for g in v.link_faces)}
# 세 점이 다 테두리인 몸 면은 눌러지지 않아 날개 조각 면과 딱 겹침(겹친 면이 번갈아 보이며 날개 윗쪽에 검은 삼각형) → 가운데 점을 찍어 그 점을 누름
flat = [f for f in wfaces if all(v in rim for v in f.verts)]
if flat:
    pk2 = bmesh.ops.poke(bm, faces=flat); foot |= set(pk2["verts"])
    for f in pk2["faces"]:
        for lp in f.loops: lp[uvl].uv = cap_uv
    wfaces = [f for f in wfaces if f.is_valid] + list(pk2["faces"])
moved = 0
for v in foot - rim:
    a_ = to_src(np.array([v.co[:]]))[0]; xe = float(side_x(a_[1], a_[2])) - .005
    if abs(a_[0]) > xe: a_[0] = np.sign(a_[0]) * xe; v.co = to_fin(a_); moved += 1
# 날개 둘레 몸 면(날개 자리 바깥 두 겹): Meshy 텍스처가 가려진 홈이라 흰·검정 톱니 찌꺼기 → 면마다 차콜/흰색 한 점 색으로
PX = np.array(bimg.pixels[:]).reshape(TEX, TEX, 4)
def texel(uv_): return PX[min(TEX - 1, int(uv_[1] * TEX)), min(TEX - 1, int(uv_[0] * TEX)), :3]
white_uv, wbest = None, 1e9
for f in bm.faces:   # 흰 배 가운데 면의 UV
    if f in wing_verts or not f.loops: continue
    cc = to_src(np.array([f.calc_center_median()[:]]))[0]; d = np.abs(cc - np.array([0, -.72, -.3])).sum()
    if d < wbest: wbest = d; white_uv = f.loops[0][uvl].uv.copy()
wset = set(wfaces); ring1 = {g for v in rim for g in v.link_faces if g not in wset and not any(u in wing_verts for u in g.verts if u not in foot)}
ring = set(ring1)
for f in ring1:
    for v in f.verts: ring |= {g for g in v.link_faces if g not in wset and g not in set(nf) and g not in set(caps)}
for f in ring:
    lum = np.mean([texel(lp[uvl].uv).mean() for lp in f.loops])
    for lp in f.loops: lp[uvl].uv = (white_uv if lum > .55 else cap_uv)
print("WINGCUT faces", len(wfaces), "caps", len(caps), "body pushed", moved, "poked", len(flat))
bm.verts.index_update(); bm.to_mesh(me); bm.free(); me.update()
is_wing = np.zeros(len(me.vertices), bool)
bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
# 날개 조각 = 떨어진 조각 중 몸이 아닌 것(가장 큰 조각 = 몸)
seen = np.full(len(bm.verts), -1); comp = 0; sizes = []
for v0 in bm.verts:
    if seen[v0.index] >= 0: continue
    st = [v0]; seen[v0.index] = comp; n_ = 0
    while st:
        v_ = st.pop(); n_ += 1
        for e in v_.link_edges:
            u = e.other_vert(v_)
            if seen[u.index] < 0: seen[u.index] = comp; st.append(u)
    sizes.append(n_); comp += 1
body_comp = int(np.argmax(sizes)); is_wing = seen != body_comp
bm.free()
wing_parts = len(sizes) - 1

# ── 무게(점 위치로. 같은 자리 점은 같은 무게) ──
A = to_src(np.array([v.co[:] for v in me.vertices])); x, y, z = A[:, 0], A[:, 1], A[:, 2]
_, rE = wing_w(A)
w_leg = (1 - ss(-.66, -.56, z)) * ~is_wing                                         # 다리: 뿌리 뼈(제자리에 서 있음)
w_wing = is_wing.astype(float)                                                     # 날개 조각: 날개 뼈에 통째로
w_tail = ss(.48, .70, y) * ss(-.45, -.25, z) * ~is_wing                            # 꼬리
near_w = ss(.40, .56, np.abs(x)) * (1 - ss(1.0, 1.35, rE))                         # 날개 둘레 옆구리는 고개 돌릴 때 덜 비틀림(날개와 어긋나지 않게)
w_head = ss(-.15, .25, z) * (1 - near_w) * (1 - w_tail) * ~is_wing                 # 머리: 가슴 위부터 서서히(부리 아래 턱받이 무늬가 구겨지지 않게 넓게)
w_body = np.clip(1 - w_head - w_wing - w_tail, 0, 1)
R = 1 - w_leg
WG = {"bird_root": w_leg, "bird_body": w_body * R, "bird_head": w_head * R, "bird_tail": w_tail * R,
      "bird_wingL": w_wing * (x > 0), "bird_wingR": w_wing * (x < 0)}

# ── 뼈대 만들기 ──
ad_ = bpy.data.armatures.new(NAME + "_rig"); arm = bpy.data.objects.new(NAME + "_rig", ad_); bpy.context.scene.collection.objects.link(arm)
for ob in bpy.context.selected_objects: ob.select_set(False)
bpy.context.view_layer.objects.active = arm; arm.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
for n, (h, t, p) in BONES.items():
    eb = ad_.edit_bones.new(n); eb.head = Lo(*h); eb.tail = Lo(*t); eb.roll = 0
    if p: eb.parent = ad_.edit_bones[p]; eb.use_connect = False
bpy.ops.object.mode_set(mode='OBJECT')
for n, w in WG.items():
    vg = o.vertex_groups.new(name=n)
    for i in np.nonzero(w > 1e-3)[0]: vg.add([int(i)], float(w[i]), 'REPLACE')
o.parent = arm; mod = o.modifiers.new("rig", 'ARMATURE'); mod.object = arm
for pb in arm.pose.bones: pb.rotation_mode = 'QUATERNION'

# ── 동작: 뼈마다 '뼈대 공간 축·각도'로 적고 뼈 로컬 회전으로 바꿔 키 ──
UP, FWD, SIDE = Vector((0, 0, 1)), Vector((0, -1, 0)), Vector((1, 0, 0))
def bq(bn, *rots):   # rots = (축, 도) 여러 개(뼈대 공간) → 포즈 쿼터니언
    B = arm.data.bones[bn].matrix_local.to_quaternion(); Rq = Quaternion()
    for ax, deg in rots: Rq = Quaternion(ax, math.radians(deg)) @ Rq
    return B.inverted() @ Rq @ B
def bl(bn, v):   # 뼈대 공간 이동 → 포즈 로컬 이동
    return arm.data.bones[bn].matrix_local.to_quaternion().inverted() @ Vector(v)
H = SIZE   # 몸 길이(.3) 기준 높이
def wing_open(deg, side):   # 날개 펴기: 어깨에서 앞뒤 축으로 돌려 아래 끝이 바깥·위로(+deg = 펼침)
    return (Vector((0, 1, 0)), -deg if side > 0 else deg)
def pose(fr, root_z=0., body=(), bscale=(1, 1, 1), head=(), wing=0., wing_tw=0., tail=0.):
    """한 프레임 자세. body·head = (축, 도) 목록, bscale = (가로, 세로, 앞뒤) 몸 배율, wing = 펼친 각, tail = 꼬리 들기(도)."""
    vals = {
        "bird_root": dict(location=bl("bird_root", (0, 0, root_z)), rotation_quaternion=Quaternion(), scale=Vector((1, 1, 1))),
        "bird_body": dict(location=Vector(), rotation_quaternion=bq("bird_body", *body), scale=Vector((bscale[0], bscale[1], bscale[2]))),
        "bird_head": dict(location=Vector(), rotation_quaternion=bq("bird_head", *head), scale=Vector((1, 1, 1))),
        "bird_tail": dict(location=Vector(), rotation_quaternion=bq("bird_tail", (SIDE, tail)), scale=Vector((1, 1, 1))),
        "bird_wingL": dict(location=Vector(), rotation_quaternion=bq("bird_wingL", wing_open(wing, 1), (SIDE, wing_tw)), scale=Vector((1, 1, 1))),
        "bird_wingR": dict(location=Vector(), rotation_quaternion=bq("bird_wingR", wing_open(wing, -1), (SIDE, wing_tw)), scale=Vector((1, 1, 1))),
    }
    for bn, d in vals.items():
        pb = arm.pose.bones[bn]
        for k, v in d.items():
            setattr(pb, k, v); pb.keyframe_insert(k, frame=fr)
# 몸 배율: 몸 뼈가 위(+Z)를 봐서 로컬 Y = 세로. pose 의 bscale 은 (가로, 세로, 앞뒤) 순으로 그대로 X·Y·Z 에 들어감
CLIPS = {}
def clip(name, frames, keys):
    act = bpy.data.actions.new(name); act.use_fake_user = True
    arm.animation_data_create(); arm.animation_data.action = act
    for fr, kw in keys: pose(fr, **kw)
    for fc in _fcurves(act):
        for kp in fc.keyframe_points: kp.interpolation = 'BEZIER'; kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
        fc.update()
    CLIPS[name] = (act, frames)
def _fcurves(act):   # Blender 4.4+ 층 액션과 옛 액션 둘 다
    if hasattr(act, "layers") and len(act.layers):
        out = []
        for ly in act.layers:
            for st in ly.strips:
                for cb in st.channelbags: out += list(cb.fcurves)
        return out
    return list(act.fcurves)
TL, TR = (UP, 32), (UP, -32)   # 고개 왼쪽(새 기준 왼쪽 = +X 쪽으로 부리) / 오른쪽
def tilt(d): return (FWD, d)  # 갸웃
# 숨쉬기 2초: 몸이 살짝 부풀었다 가라앉고 머리가 따라 아주 조금 끄덕
clip("idle_breathe", 60, [(0, {}), (30, dict(bscale=(1.035, .975, 1.035), head=[(SIDE, 2)])), (60, {})])
# 고개 돌리기 2.5초: 왼쪽 보고 멈칫 → 오른쪽 보고 멈칫(갸웃) → 제자리
clip("head_turn", 75, [(0, {}), (9, dict(head=[TL])), (27, dict(head=[TL, tilt(8)])), (39, dict(head=[TR])), (57, dict(head=[TR, tilt(-8)])), (66, dict(head=[(UP, -6)])), (75, {})])
# 쪼기 0.8초: 몸이 앞으로 살짝 숙이며 머리를 콕
clip("peck", 24, [(0, {}), (5, dict(body=[(SIDE, 8)], head=[(SIDE, 26)], tail=6)), (8, dict(body=[(SIDE, 10)], head=[(SIDE, 32)], tail=8)),
                  (14, dict(body=[(SIDE, 3)], head=[(SIDE, 6)], tail=2)), (24, {})])
# 뛰기 0.6초: 움츠렸다 → 위로 쏙(날개 살짝) → 착지 눌림 → 제자리
clip("hop", 18, [(0, {}), (3, dict(bscale=(1.06, .9, 1.06))), (8, dict(root_z=.17 * H, bscale=(.97, 1.05, .97), wing=18, tail=8)),
                 (13, dict(root_z=0., bscale=(1.05, .92, 1.05), wing=6)), (18, {})])
# 날갯짓 0.5초(반복): 날개 위(110°)↔아래(25°), 몸은 내려칠 때 살짝 떠오름. 비행 중 계속 틀어 둠
FU, FD = 110, 25
clip("flap", 15, [(0, dict(wing=FU, root_z=0., tail=10, body=[(SIDE, 6)])), (7, dict(wing=FD, root_z=.05 * H, tail=6, body=[(SIDE, 6)])),
                  (15, dict(wing=FU, root_z=0., tail=10, body=[(SIDE, 6)]))])
# 날아오르기 0.6초: 움츠림 → 날개 펼치며 뛰어오름 → 날갯짓 첫 자세(flap 0프레임)로 끝남
clip("takeoff", 18, [(0, {}), (4, dict(bscale=(1.06, .9, 1.06), body=[(SIDE, 5)], wing=10)), (9, dict(root_z=.12 * H, wing=FD, tail=6, body=[(SIDE, 6)])),
                     (18, dict(wing=FU, root_z=0., tail=10, body=[(SIDE, 6)]))])
# 내려앉기 0.6초: flap 0프레임 자세에서 시작 → 날개 한 번 내려치고 착지 눌림 → 날개 접고 제자리
clip("land", 18, [(0, dict(wing=FU, root_z=0., tail=10, body=[(SIDE, 6)])), (6, dict(wing=FD + 10, root_z=.04 * H, tail=8, body=[(SIDE, 3)])),
                  (11, dict(bscale=(1.06, .9, 1.06), wing=20, tail=4)), (18, {})])
# 비행 중 뿌리 위치는 앱이 움직이므로, flap·takeoff·land 의 root_z 는 몸이 '들썩'이는 작은 값만(0~.04)

# ── NLA 트랙으로 하나씩 → glTF 애니메이션 이름 = 트랙 이름 ──
ad = arm.animation_data; ad.action = None
for n, (act, fr) in CLIPS.items():
    tr = ad.nla_tracks.new(); tr.name = n; st = tr.strips.new(n, 0, act); st.name = n; tr.mute = False
for pb in arm.pose.bones: pb.location = Vector(); pb.rotation_quaternion = Quaternion(); pb.scale = Vector((1, 1, 1))
bpy.context.scene.render.fps = FPS
for ob in bpy.context.selected_objects: ob.select_set(False)
o.select_set(True); arm.select_set(True); bpy.context.view_layer.objects.active = arm
GLB = os.path.join(OUT, NAME + ".glb")
bpy.ops.export_scene.gltf(filepath=GLB, use_selection=True, export_format='GLB', export_animations=True, export_animation_mode='NLA_TRACKS',
                          export_force_sampling=True, export_frame_step=1, export_skins=True, export_def_bones=False, export_optimize_animation_size=False)

# ── 보고 ──
Pf = np.array([v.co[:] for v in me.vertices]); dims = (Pf.max(0) - Pf.min(0)).round(3).tolist()
import struct
b = open(GLB, 'rb').read(); jn = json.loads(b[20:20 + struct.unpack('<I', b[12:16])[0]])
anims = []
for a in jn.get("animations", []):
    tmax = max(jn["accessors"][s["input"]]["max"][0] for s in a["samplers"]); anims.append({"name": a["name"], "sec": round(tmax, 3), "frames": round(tmax * FPS)})
rep = {"name": NAME, "faces_meshy": f0, "faces": len(me.polygons), "faces_body_after_decimate": f_dec, "wing_parts": wing_parts, "verts": len(me.vertices), "dims_xyz": dims,
       "axes": "Blender Z-up, 부리 -Y (glTF: Y-up, 부리 +Z). 원점 = 두 발 사이 바닥", "length_beak_tail": round(dims[1], 3),
       "bones": [{"name": n, "parent": p, "head": [round(v, 4) for v in Lo(*h)], "tail": [round(v, 4) for v in Lo(*t)]} for n, (h, t, p) in BONES.items()],
       "gltf_nodes": [nd.get("name") for nd in jn["nodes"]], "clips": anims, "fps": FPS,
       "tex": sorted({f"{i.size[0]}x{i.size[1]}" for i in bpy.data.images if i.users and i.size[0]}), "recolor": recolor_rep,
       "material": "색 텍스처 1장(고면에서 구움) + 거칠기 .8, 금속 0"}
json.dump(rep, open(os.path.join(OUT, NAME + "_report.json"), "w"), indent=1, ensure_ascii=False)
print("BIRD", json.dumps(rep, ensure_ascii=False))
if '--norender' in argv: sys.exit(0)

# ── 확인 렌더: 내보낸 GLB 를 다시 불러서(앱이 받는 그대로) ──
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
arm = [x for x in bpy.data.objects if x.type == 'ARMATURE'][0]
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = int(arg("--samples", "24")); sc.cycles.use_denoising = True
sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'; sc.render.fps = FPS
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[1].default_value = 0.7
k = SIZE / 1.0   # prop_prep 조명은 키 1~3 짜리 소품 기준 → 새 크기에 맞춰 줄임(거리·크기·세기)
for loc, e in (((-2, -4, 3), 260), ((3, -3, 1.5), 110), ((0, 3, 3), 120)):
    l = bpy.data.lights.new("k", 'AREA'); l.energy = e * k * k; l.size = 4 * k; lo_ = bpy.data.objects.new("k", l); lo_.location = Vector(loc) * k; sc.collection.objects.link(lo_)
    lo_.rotation_euler = (Vector((0, 0, .4 * k)) - lo_.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.type = 'ORTHO'
cam.data.clip_start = .01; cam.data.clip_end = 100
def shoot(path, yaw, el, cz, osc, res):
    a = math.radians(yaw); e = math.radians(el); d = 3
    cam.location = (d * math.sin(a) * math.cos(e), -d * math.cos(a) * math.cos(e), cz + d * math.sin(e)); cam.data.ortho_scale = osc
    cam.rotation_euler = (Vector((0, 0, cz)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.resolution_x = sc.render.resolution_y = res; sc.render.filepath = path; bpy.ops.render.render(write_still=True)
ad = arm.animation_data
acts = {}
if ad:
    for tr in ad.nla_tracks:
        for st in tr.strips: acts[tr.name] = st.action
    for tr in list(ad.nla_tracks): ad.nla_tracks.remove(tr)
    if ad.action: acts.setdefault(ad.action.name, ad.action)
else: arm.animation_data_create(); ad = arm.animation_data
for a in bpy.data.actions: acts.setdefault(a.name, a)
def use(act):
    ad.action = act
    if hasattr(ad, "action_slot") and act is not None and len(getattr(act, "slots", [])): ad.action_slot = act.slots[0]
use(None)
for pb in arm.pose.bones: pb.location = Vector(); pb.rotation_quaternion = Quaternion(); pb.scale = Vector((1, 1, 1))
sc.frame_set(0)
D = [d for d in rep["dims_xyz"]]; cz = D[2] / 2
for vn, yaw, el in (("front", 0, 0), ("side", 90, 0), ("back", 180, 0), ("top45", 35, 30)):
    shoot(os.path.join(OUT, f"{NAME}_{vn}.png"), yaw, el, cz, max(D) * 1.3, 480)
# 동작 표: 줄 = 동작, 칸 = 4장(0·1/3·2/3·끝 직전). 3/4 시점, 날개 편 것까지 들어가게 크게 잡음
order = ["idle_breathe", "head_turn", "peck", "hop", "flap", "takeoff", "land"]
CELL = int(arg("--cell", "256")); TMPR = tempfile.mkdtemp(); rows = []
pick = {"head_turn": [9, 27, 39, 57], "peck": [0, 5, 8, 14], "hop": [3, 8, 13, 16], "flap": [0, 4, 7, 11], "takeoff": [4, 9, 13, 17], "land": [0, 6, 11, 18], "idle_breathe": [0, 15, 30, 45]}
for n in order:
    act = acts.get(n)
    if act is None: rows.append([None] * 4); continue
    use(act); row = []
    for fr in pick[n]:
        sc.frame_set(fr); pth = os.path.join(TMPR, f"{n}_{fr}.png"); shoot(pth, 35, 18, cz + .03, max(D) * 1.75, CELL); row.append((pth, fr))
    rows.append(row)
use(None)
# 모으기: 연회색 바탕(#E9EAEC)에 알파로 얹고, 칸 왼쪽 위에 동작 이름·프레임을 점 글씨로
BG = np.array([0xE9, 0xEA, 0xEC]) / 255
FONT = {c: r for c, r in zip("abcdefghijklmnopqrstuvwxyz_0123456789f", [
    "0111010001111111000110001", "1111010001111101000111110", "0111110000100001000001111", "1111010001100011000111110", "1111110000111101000011111",
    "1111110000111101000010000", "0111110000100111000101111", "1000110001111111000110001", "0111000100001000010001110", "0011100010000101001001100",
    "1000110010111001001010001", "1000010000100001000011111", "1000111011101011000110001", "1000111001101011001110001", "0111010001100011000101110",
    "1111010001111101000010000", "0111010001101011001001101", "1111010001111101001010001", "0111110000011100000111110", "1111100100001000010000100",
    "1000110001100011000101110", "1000110001010100101000100", "1000110001101011101110001", "1000101010001000101010001", "1000101010001000010000100",
    "1111100010001000100011111", "0000000000000000000011111", "0111010011101011100101110", "0010001100001000010001110", "1111000001011101000011111",
    "1111000001011100000111110", "1001010010111110001000010", "1111110000111100000111110", "0111010000111101000101110", "1111100001000100010000100",
    "0111010001011101000101110", "0111010001011110000101110", "1111110000111101000010000"])}
def text(img, s, x0, y0, sc_=3):
    for ci, ch in enumerate(s):
        r = FONT.get(ch)
        if r is None: continue
        for k_, bit in enumerate(r):
            if bit == "1":
                yy, xx = y0 + (k_ // 5) * sc_, x0 + ci * 6 * sc_ + (k_ % 5) * sc_
                img[yy:yy + sc_, xx:xx + sc_] = .35
sheet = np.ones((CELL * len(order), CELL * 4, 3)) * BG
for ri, row in enumerate(rows):
    for ci, it in enumerate(row):
        if it is None: continue
        pth, fr = it; im = bpy.data.images.load(pth); W_, H_ = im.size
        px = np.array(im.pixels[:]).reshape(H_, W_, 4)[::-1]; bpy.data.images.remove(im)
        a = px[:, :, 3:4]; cell = px[:, :, :3] * a + BG * (1 - a)   # 렌더 결과는 sRGB 저장값(Standard), 알파는 곧은 알파
        sheet[ri * CELL:(ri + 1) * CELL, ci * CELL:(ci + 1) * CELL] = cell
        text(sheet, (order[ri] + " f" + str(fr)) if ci == 0 else ("f" + str(fr)), ci * CELL + 8, ri * CELL + 8, 2)
    sheet[ri * CELL, :] = .8
out = bpy.data.images.new("sheet", CELL * 4, CELL * len(order), alpha=False)
out.pixels.foreach_set(np.concatenate([sheet[::-1], np.ones(sheet.shape[:2] + (1,))], 2).astype(np.float32).ravel())
out.file_format = 'JPEG'
try: out.save(filepath=os.path.join(OUT, NAME + "_anim.jpg"), quality=90)
except TypeError: out.filepath_raw = os.path.join(OUT, NAME + "_anim.jpg"); out.save()
print("SHEET", os.path.join(OUT, NAME + "_anim.jpg"))
