# 도담도담 캐릭터 공정 v3 (11/09 사용자와 정한 근본 개선 2가지)
#  1) 머리통 맞추기: Meshy가 머리 모양마다 다르게 만든 머리통(회색)을 우리 기준 머리 표면에 딱 맞게 휘고,
#     머리카락은 가까운 머리통 점들이 움직인 만큼 부드럽게 따라 움직임 → 끝단이 우리 두피 위, 구레나룻이 우리 귀 앞에 놓임
#  2) 오려내기: 면을 갈색/회색으로 자르지 않고(톱니·검은 부스러기의 원인), 경계 면은 넉넉히 남긴 뒤
#     Meshy 텍스처의 갈색 정도로 만든 마스크로 픽셀 단위로 오려냄(Meshy 화면처럼 끝선이 깔끔). glTF alphaMode MASK.
# 실행: Blender -b --factory-startup -P wig_v3.py -- --wig TEX.glb --master MASTER_DIR --out OUT --name NAME [--face FACE.png]
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
WIG, MD, OUT, NAME, FACE = arg("--wig"), arg("--master"), arg("--out"), arg("--name"), arg("--face")
HAIR, SKIN = arg("--hair", "#4A3226"), arg("--skin", "#F2C9AC")
os.makedirs(OUT, exist_ok=True)
def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]; return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1]
bpy.ops.wm.read_factory_settings(use_empty=True)
def load(path):
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=path)
    ms = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in ms: o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1: bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active; bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o
master = load(os.path.join(MD, "master_head.glb")); M = np.array([v.co[:] for v in master.data.vertices])
wig = load(WIG); me = wig.data
ROTZ = float(arg("--rotz", "0"))   # 11/09 Meshy가 앞모습을 뒤통수로 읽고 모델을 돌려 만든 경우(옆머리 대머리) → 세로축으로 돌려 앞을 맞춤
if ROTZ:
    from mathutils import Matrix
    me.transform(Matrix.Rotation(math.radians(ROTZ), 4, 'Z')); me.update()
# 11/09: 이음매에서 갈라진 점을 먼저 붙임(UV는 면 모서리별로 유지됨) → 면 줄이기 후에도 머리카락이 조각나지 않음
import bmesh as _bm
_b = _bm.new(); _b.from_mesh(me); _bm.ops.remove_doubles(_b, verts=_b.verts[:], dist=1e-5); _b.to_mesh(me); _b.free(); me.update()
DEC = int(arg("--dec", "12000"))   # 고품질(멀티 뷰) 모델은 면이 수십만 → 처리 전에 이 면 수로 줄임(UV 유지)
if len(me.polygons) > DEC:
    for o in bpy.context.selected_objects: o.select_set(False)
    wig.select_set(True); bpy.context.view_layer.objects.active = wig
    dm = wig.modifiers.new("dec", 'DECIMATE'); dm.ratio = DEC / len(me.polygons); bpy.ops.object.modifier_apply(modifier="dec"); me = wig.data
def base_color_image(mats):   # 11/09: PBR 모델은 이미지가 여러 장(색·요철·거칠기) → '기본 색'에 연결된 이미지만
    for m in mats:
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
    return [n.image for m in mats for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image][0]
img = base_color_image(me.materials)
TW, TH = img.size; px = np.array(img.pixels[:]).reshape(TH, TW, 4)
rgb = px[:, :, :3]
# 픽셀마다 갈색 정도(빨강-파랑 비율: 회색≈0, 머리카락 0.4~0.9)
chroma_img = (rgb[:, :, 0] - rgb[:, :, 2]) / (rgb[:, :, 0] + 1e-3)
LO, HI = float(arg("--lo", "0.12")), float(arg("--hi", "0.30"))
mask_img = np.clip((chroma_img - LO) / (HI - LO), 0, 1)
# 11/09: 어두운 회색 그늘(두피에 칠해진)은 값이 작아 비율이 튐 → 빨강-파랑 실제 차이도 있어야 머리카락
DIFF_LO = float(arg("--dlo", "0.012"))
mask_img = mask_img * np.clip(((rgb[:, :, 0] - rgb[:, :, 2]) - DIFF_LO) / 0.02, 0, 1)
# 점마다 갈색 정도
uv = me.uv_layers.active.data
W = np.array([v.co[:] for v in me.vertices]); hsum = np.zeros(len(W)); cnt = np.zeros(len(W))
for p in me.polygons:
    for li in p.loop_indices:
        u = uv[li].uv; x = min(TW - 1, max(0, int(u[0] * TW))); y = min(TH - 1, max(0, int(u[1] * TH)))
        hsum[me.loops[li].vertex_index] += mask_img[y, x]; cnt[me.loops[li].vertex_index] += 1
hv = hsum / np.maximum(cnt, 1)
# 11/09 이음매 번짐 막기: 텍스처 조각 테두리에 옆 조각 갈색이 번져 있으면 오려내기가 금 같은 가는 선을 그림
# → 점마다 갈색 정도(같은 위치의 갈라진 점끼리 평균)를 '문'으로: 주변 점이 피부면 텍스처가 갈색이어도 안 그림
from collections import defaultdict
grp = defaultdict(list)
for i, p_ in enumerate(W): grp[(round(p_[0], 5), round(p_[1], 5), round(p_[2], 5))].append(i)
hv_w = hv.copy()
for idx in grp.values(): hv_w[idx] = hv[idx].mean()
g_ = np.clip((hv_w - 0.15) / 0.20, 0, 1); gate = g_ * g_ * (3 - 2 * g_)
ga = me.color_attributes.new("gate", 'FLOAT_COLOR', 'POINT')
for i, c_ in enumerate(ga.data): c_.color = (1, 1, 1, float(gate[i]))
# --- 1단계: 얼굴(볼·턱)로 큰 위치 맞춤(배율·이동, 정면 고정)
S = W[hv < 0.05]
src = M[(M[:, 1] < -0.15) & (M[:, 2] < 0.05) & (M[:, 2] > -0.35)]
src = src[np.random.default_rng(0).choice(len(src), min(1500, len(src)), replace=False)]
kd = KDTree(len(S))
for i, p in enumerate(S): kd.insert(p, i)
kd.balance()
def nn(P): return np.array([kd.find(p)[0][:] for p in P])
def fit_st(A, B):
    ma, mb = A.mean(0), B.mean(0); A0, B0 = A - ma, B - mb
    s = (A0 * B0).sum() / (A0 ** 2).sum(); return s, mb - s * ma
def icp(s0, t0, iters=40):
    s, t = s0, t0
    for _ in range(iters):
        X = s * src + t; Y = nn(X); d = np.linalg.norm(X - Y, axis=1); keep = d < np.percentile(d, 85)
        s, t = fit_st(src[keep], Y[keep])
    X = s * src + t; d = np.linalg.norm(X - nn(X), axis=1); return s, t, float(np.mean(d) / s)
low = S[S[:, 2] < np.percentile(S[:, 2], 50)]
guess = (low[:, 0].max() - low[:, 0].min()) / (M[:, 0].max() - M[:, 0].min())
cands = [icp(guess * f, np.array([np.median(S[:, 0]), np.median(S[:, 1]), S[:, 2].min() - guess * f * M[:, 2].min()])) for f in (0.6, 0.7, 0.85, 1.0, 1.15, 1.3)]   # 긴 머리·꼬리가 있으면 처음 짐작이 크게 틀려서 범위를 넓힘
print('CANDS', [(round(float(c[0]),3), round(c[2],4)) for c in cands])
s, t, fit_err = min(cands, key=lambda c: c[2])
t[0] = float(np.median(S[:, 0]))            # 좌우 가운데
Wm = (W - t) / s                             # 기준 좌표
# --- 2단계: 머리통 맞추기(휘기). 회색(마네킹) 점 → 기준 머리 표면 위 가장 가까운 점으로 옮기는 양을 구하고,
#     모든 점(머리카락 포함)은 가까운 회색 점 16개의 이동량을 거리로 섞어서 따라 움직임
bmM = bmesh.new(); bmM.from_mesh(master.data); bvhM = BVHTree.FromBMesh(bmM)
ctrl = np.where(hv < 0.15)[0]
# 11/10 회색 섬: 마네킹 본체(가장 큰 이어진 회색 덩어리)와 안 이어진 작은 회색 조각은 머리통이 아님
#  (Meshy가 머리카락 골 바닥·앞머리 틈에 칠한 회색). 기준점에 넣으면 그 조각이 두피로 끌려가며 둘레 머리카락까지
#  기준 머리 속으로 파묻혀 골 사이로 두피가 보였다(숏컷 뒤통수). → 머리통 맞추기 기준점은 본체만
_par = np.arange(len(hv)); _grey = hv < 0.15
def _root(a):
    while _par[a] != a: _par[a] = _par[_par[a]]; a = _par[a]
    return a
for _p in me.polygons:
    _vs = list(_p.vertices)
    for _a, _b in zip(_vs, _vs[1:] + _vs[:1]):
        if _grey[_a] and _grey[_b]: _par[_root(_a)] = _root(_b)
_rt = np.array([_root(i) for i in ctrl], int)
_ru, _rc = np.unique(_rt, return_counts=True)
ISLAND = ctrl[_rt != _ru[np.argmax(_rc)]]
ctrl = ctrl[_rt == _ru[np.argmax(_rc)]]
# 11/09 2단계 휘기: ①머리통 비율(가로·앞뒤·세로 배율+이동)을 통째로 먼저 맞춤 ②남은 차이만 넓고 부드럽게
# (뒤통수처럼 피부 점이 먼 곳에서 이웃 점끼리 다른 피부를 따라가 머리카락이 찢어지던 문제)
W0m = Wm.copy(); cum = np.ones(3); off = np.zeros(3)
for _ in range(15):
    Pc = W0m[ctrl] * cum + off; Y = np.array([bvhM.find_nearest(Vector(p))[0][:] for p in Pc])
    for ax in range(3):
        A_ = np.vstack([W0m[ctrl][:, ax], np.ones(len(ctrl))]).T; sa, ba = np.linalg.lstsq(A_, Y[:, ax], rcond=None)[0]
        cum[ax] = float(np.clip(sa, 0.92, 1.08)); off[ax] = float(np.mean(Y[:, ax] - cum[ax] * W0m[ctrl][:, ax]))   # 축마다 배율은 ±8%까지만
Wm = W0m * cum + off
disp = np.zeros((len(ctrl), 3))
for k, i in enumerate(ctrl):
    loc = bvhM.find_nearest(Vector(Wm[i]))[0]; disp[k] = np.array(loc[:]) - Wm[i]
kdc = KDTree(len(ctrl))
for k, i in enumerate(ctrl): kdc.insert(Vector(Wm[i]), k)
kdc.balance()
Wn = Wm.copy()
for i in range(len(Wm)):
    res = kdc.find_n(Vector(Wm[i]), 64)
    ws = np.array([math.exp(-(r[2] / 0.18) ** 2) + 1e-6 for r in res]); ds = np.array([disp[r[1]] for r in res])   # 넓고 부드러운 가중
    Wn[i] = Wm[i] + (ws[:, None] * ds).sum(0) / ws.sum()
warp_mag = float(np.median(np.linalg.norm(disp, axis=1)))
RIGID = '--rigid' in argv   # 11/09 이어폰 같은 딱딱한 부품: 머리카락처럼 휘지 않고 통째 크기·위치만 맞춤
if RIGID: Wn = Wm.copy()
for i, v in enumerate(me.vertices): v.co = Vector(Wn[i])
# 11/10 회색 섬 중 기준 두피보다 3% 넘게 떠 있는 것 = 머리카락 골 바닥 칠 → 오려내지 않고 머리카락(골 그늘색)으로.
#  오려내면 그 구멍으로 안쪽 두피가 보인다. 두피에 붙은 섬(앞머리 사이로 보이는 이마)은 그대로 오려냄
GROOVE_SHADE = 0.75
shade_ovr = np.full((TH, TW), np.nan)
groove = [] if RIGID else [i for i in ISLAND if (lambda r: (Vector(Wn[i]) - r[0]).dot(r[1]))(bvhM.find_nearest(Vector(Wn[i]))) > 0.03]
if groove:
    hv[groove] = 1.0; gate[groove] = 1.0; _gs = set(groove)
    for p in me.polygons:
        if not any(v in _gs for v in p.vertices): continue
        q = np.array([uv[li].uv[:] for li in p.loop_indices]) * [TW, TH]
        for k in range(1, len(q) - 1):
            A_, B_, C_ = q[0], q[k], q[k + 1]
            x0, x1 = int(max(0, np.floor(min(A_[0], B_[0], C_[0])) - 1)), int(min(TW, np.ceil(max(A_[0], B_[0], C_[0])) + 2))
            y0, y1 = int(max(0, np.floor(min(A_[1], B_[1], C_[1])) - 1)), int(min(TH, np.ceil(max(A_[1], B_[1], C_[1])) + 2))
            dd = (B_[1] - C_[1]) * (A_[0] - C_[0]) + (C_[0] - B_[0]) * (A_[1] - C_[1])
            if x1 <= x0 or y1 <= y0 or abs(dd) < 1e-9: continue
            xs, ys = np.meshgrid(np.arange(x0, x1) + .5, np.arange(y0, y1) + .5)
            l1 = ((B_[1] - C_[1]) * (xs - C_[0]) + (C_[0] - B_[0]) * (ys - C_[1])) / dd
            l2 = ((C_[1] - A_[1]) * (xs - C_[0]) + (A_[0] - C_[0]) * (ys - C_[1])) / dd
            yy, xx = np.nonzero((l1 >= -0.05) & (l2 >= -0.05) & (1 - l1 - l2 >= -0.05))   # 삼각형 + 둘레 조금(경계 텍셀까지)
            mask_img[yy + y0, xx + x0] = 1.0; shade_ovr[yy + y0, xx + x0] = GROOVE_SHADE
# 11/09: Meshy 텍스처가 회색 머리통에 얼굴(눈썹·눈·입·볼)을 그려 넣는 경우 → 얼굴 자리(앞쪽, 눈썹 높이 아래)는 갈색이어도 머리카락 아님
FACE_Z = float(arg("--facez", "0.16"))
# 두피에 붙어 칠해진 것만(얼굴 그림). 이마에서 떠 있는 진짜 앞머리는 남김(11/09: 일자로 잘려 바가지 앞머리가 되던 문제)
sd_face = np.array([(Vector(p) - bvhM.find_nearest(Vector(p))[0]).dot(bvhM.find_nearest(Vector(p))[1]) for p in Wn])
face_zone = (Wn[:, 1] < -0.2) & (np.abs(Wn[:, 0]) < 0.33) & (Wn[:, 2] < FACE_Z) & (sd_face < 0.02)
gate[face_zone] = 0.0; hv[face_zone] = 0.0
for i, c_ in enumerate(ga.data): c_.color = (1, 1, 1, float(gate[i]))
me.update()
# --- 3단계: 경계 면은 넉넉히 남김(갈색이 조금이라도 있는 면), 완전 회색 면만 버림
bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
fmax = []
for f in bm.faces: fmax.append(max(hv[v.index] for v in f.verts))
bmesh.ops.delete(bm, geom=[f for f, m_ in zip(list(bm.faces), fmax) if m_ < 0.05], context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
# 11/09 찌꺼기 지우기: 실제로 보이는(마스크로 머리카락인) 부분끼리 이어진 덩어리를 찾아, 본체에 안 붙은 작은 섬은 지움
uvl = bm.loops.layers.uv.active
bm.faces.ensure_lookup_table(); bm.faces.index_update()
def cover(f):
    us = [np.array(l[uvl].uv[:]) for l in f.loops]; c = np.mean(us, axis=0)
    pts = [c] + [u * 0.7 + c * 0.3 for u in us] + [(us[i] + us[(i + 1) % len(us)]) * 0.5 for i in range(len(us))]
    return float(np.mean([mask_img[min(TH - 1, max(0, int(p_[1] * TH))), min(TW - 1, max(0, int(p_[0] * TW)))] > 0.5 for p_ in pts]))
cov = np.array([cover(f) for f in bm.faces]); area = np.array([f.calc_area() for f in bm.faces])
hairy = cov > 0.25
# 이웃 면 찾기는 '점 위치'로(Meshy glTF는 텍스처 이음매마다 점이 갈라져 있어 이어진 머리카락도 따로 떨어진 걸로 보임)
def key(v): return (round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5))
from collections import defaultdict
edge_f = defaultdict(list)
for f in bm.faces:
    ks = [key(v) for v in f.verts]
    for i_ in range(len(ks)):
        e_ = tuple(sorted((ks[i_], ks[(i_ + 1) % len(ks)]))); edge_f[e_].append(f.index)
nbr = defaultdict(set)
for fl in edge_f.values():
    for a_ in fl:
        for b_ in fl:
            if a_ != b_: nbr[a_].add(b_)
seen = np.zeros(len(cov), bool); comps = []
for i in range(len(cov)):
    if not hairy[i] or seen[i]: continue
    st = [i]; seen[i] = True; cc = []
    while st:
        k = st.pop(); cc.append(k)
        for g in nbr[k]:
            if hairy[g] and not seen[g]: seen[g] = True; st.append(g)
    comps.append(cc)
tot = float((area * cov)[hairy].sum())
drop = set()
print('SPECK comps', len(comps), 'top', sorted([round(float((area[cc]*cov[cc]).sum()/max(tot,1e-9)),3) for cc in comps])[-5:], 'hairy', int(hairy.sum()), 'faces', len(cov))
for cc in (comps if '--nospeck' not in argv else []):
    if float((area[cc] * cov[cc]).sum()) < 0.01 * tot: drop.update(cc)
keep_h = set(i for i in range(len(cov)) if hairy[i] and i not in drop)
for f in bm.faces:   # 보이는 머리카락에 안 붙은 경계 면(거의 투명)도 정리
    if '--nospeck' not in argv and not hairy[f.index] and not any(g in keep_h for g in nbr[f.index]): drop.add(f.index)
bmesh.ops.delete(bm, geom=[bm.faces[i] for i in drop], context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
speck_removed = len(drop)
if RIGID:   # Meshy 귀가 우리 귀보다 작아 부품 앞쪽이 우리 귀 속에 묻힘 → 덩어리마다 통째로 바깥쪽으로 밀어 귀 표면에 얹음
    bm.faces.ensure_lookup_table(); ef2 = defaultdict(list)
    for f in bm.faces:
        ks = [key(v) for v in f.verts]
        for i_ in range(len(ks)): ef2[tuple(sorted((ks[i_], ks[(i_ + 1) % len(ks)])))].append(f.index)
    nb2 = defaultdict(set)
    for fl in ef2.values():
        for a_ in fl: nb2[a_].update(b_ for b_ in fl if b_ != a_)
    sn = set()
    for f0 in range(len(bm.faces)):
        if f0 in sn: continue
        st = [f0]; sn.add(f0); cc = []
        while st:
            k = st.pop(); cc.append(k)
            for g in nb2[k]:
                if g not in sn: sn.add(g); st.append(g)
        vs = list({v for k in cc for v in bm.faces[k].verts})
        for _ in range(40):
            sd = []; nsum = Vector((0, 0, 0))
            for v in vs:
                loc, nrm, _i, _d = bvhM.find_nearest(v.co); s_ = (v.co - loc).dot(nrm); sd.append(s_)
                if s_ < 0.003: nsum += nrm
            if min(sd) >= 0.003 or nsum.length == 0: break
            step = nsum.normalized() * max(0.002, (0.003 - min(sd)) * 0.5)
            for v in vs: v.co += step
    FLUSH = -1e9   # 밀어낸 뒤엔 아무것도 머리 속에 없음 → 지우지 않음
# 11/09: 머리 속으로 파고든 점을 두피 위로 끌어올리면 납작한 줄기가 두피에 들러붙음(고슴도치 귀 옆 선의 원인)
# → 끌어올리지 않고, 머리 속에 완전히 들어간 면만 지움(나머지 파고든 부분은 머리에 가려 안 보임)
if not RIGID: FLUSH = float(arg("--flush", "0.014"))   # 11/09: Meshy가 머리통 피부에 칠한 갈색 조각(귀 앞 찌꺼기)까지 지움
def inside(v):
    loc, nrm, idx, d = bvhM.find_nearest(v.co); return (v.co - loc).dot(nrm) < FLUSH   # 머리 속이거나 두피에 납작하게 깔린 점
ins = {v: inside(v) for v in bm.verts}
dead = [f for f in bm.faces if all(ins[v] for v in f.verts)]
bmesh.ops.delete(bm, geom=dead, context='FACES'); bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
lifted = -len(dead)
bm.to_mesh(me); bm.free(); me.update()
# 떨어진 작은 부스러기 정리
for o in bpy.context.selected_objects: o.select_set(False)
wig.select_set(True); bpy.context.view_layer.objects.active = wig
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.separate(type='LOOSE'); bpy.ops.object.mode_set(mode='OBJECT')
parts = list(bpy.context.selected_objects); big = max(len(o.data.polygons) for o in parts)
NOFACE = '--noface' in argv   # 11/09 이어폰처럼 얼굴에 있으면 안 되는 부품: Meshy가 얼굴 앞에 따로 만든 덩어리는 버림
for o in parts:
    cen = np.mean([v.co[:] for v in o.data.vertices], axis=0)
    if len(o.data.polygons) < 0.02 * big or (NOFACE and cen[1] < -0.2 and abs(cen[0]) < 0.33): bpy.data.objects.remove(o)
parts = [o for o in bpy.data.objects if o.type == 'MESH' and o is not master]
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
if len(parts) > 1: bpy.ops.object.join()
hair = bpy.context.view_layer.objects.active; hair.name = NAME
# --- 오려내기 텍스처: 색 = 머리색 × Meshy 명암, 알파 = 갈색 정도(픽셀 단위)
lum = (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2])
ref = np.median(lum[mask_img > 0.9]) if (mask_img > 0.9).any() else 0.1
shade = np.clip(lum / (ref + 1e-4), 0.55, 1.35)
shade = np.where(np.isnan(shade_ovr), shade, shade_ovr)   # 머리카락으로 살린 골 바닥(회색 칠)은 골 그늘색
hc = np.array(srgb(HAIR)[:3])
lin = np.clip(hc[None, None, :] * shade[:, :, None], 0, 1)
enc = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)   # PNG는 sRGB로 저장(안 하면 머리색이 검게 나옴)
out = np.zeros((TH, TW, 4), np.float32); out[:, :, :3] = enc; out[:, :, 3] = (mask_img > 0.5).astype(np.float32)
# 11/10 안감(--liner 두께): 아주 짧은 머리(짧은 스포츠머리)는 Meshy 머리카락 바닥이 두피와 거의 붙어 있어,
#  머리통을 맞추고 나면 뾰족 다발 사이 바닥이 우리 두피보다 1~2% 아래로 들어가 그 자리 두피가 보임(실측 4곳, 깊이 -0.01~-0.022).
#  → 가발이 덮는 두피 모양 그대로 머리색(골 그늘색) 막을 두피 위 LINER 에 깔아 틈으로는 머리색만 보이게.
#  덮는 곳 = 보이는 머리카락(문 > 0.5) 점의 방향이 가까운 두피 점, 작은 구멍은 메우고(닫기) 끝선에서 한 칸 안쪽까지만(귀 빼고)
LINER = float(arg("--liner", "0"))
liner_faces = 0
if LINER > 0:
    hme = hair.data; Hx = np.array([v.co[:] for v in hme.vertices])
    _ga = hme.color_attributes.get("gate"); gv = np.array([c_.color[3] for c_ in _ga.data]) if _ga else np.ones(len(Hx))
    Hd = Hx[gv > 0.5]; Hd = Hd / np.linalg.norm(Hd, axis=1, keepdims=True)
    kdh = KDTree(len(Hd))
    for i, p_ in enumerate(Hd): kdh.insert(Vector(p_), i)
    kdh.balance()
    # 기준 머리를 두 번 잘게 나눠(칸 약 1.2~2.5%) 막 끝선이 머리카락 끝선을 계단 없이 따라가게
    bs0 = bmesh.new(); bs0.from_mesh(master.data)
    for _ in range(2): bmesh.ops.subdivide_edges(bs0, edges=bs0.edges[:], cuts=1, use_grid_fill=True)
    bs0.normal_update(); bs0.verts.ensure_lookup_table(); bs0.verts.index_update()
    MV = np.array([v.co[:] for v in bs0.verts]); MN = np.array([v.normal[:] for v in bs0.verts])
    rr = np.linalg.norm(MV, axis=1)
    cov = np.array([kdh.find(Vector(p_ / max(np.linalg.norm(p_), 1e-9)))[2] < 0.03 for p_ in MV]) & (rr < 0.52)
    nb = defaultdict(set)
    for e_ in bs0.edges: a_, b_ = e_.verts[0].index, e_.verts[1].index; nb[a_].add(b_); nb[b_].add(a_)
    def grow(c, n):
        for _ in range(n): c = c | np.array([any(c[j] for j in nb[i]) for i in range(len(c))])
        return c
    def shrink(c, n):
        for _ in range(n): c = c & np.array([all(c[j] for j in nb[i]) for i in range(len(c))])
        return c
    # 구멍 메우기: 두 칸 키워 가는 틈을 닫은 뒤, 머리카락에 둘러싸인 빈 곳(얼굴·목·귀로 이어진 가장 큰 빈 곳이 아닌 것)은 모두 덮음.
    #  키우고 줄이기(닫기)만 쓰면 귀 위 오목한 끝선까지 메워져 막이 머리카락 밖으로 보였음 → 오목한 곳은 그대로 두고 갇힌 구멍만
    c1 = grow(cov, 2); seen_ = np.zeros(len(c1), bool); comps_ = []
    for i0 in range(len(c1)):
        if c1[i0] or seen_[i0]: continue
        st_ = [i0]; seen_[i0] = True; cc_ = []
        while st_:
            k_ = st_.pop(); cc_.append(k_)
            for j_ in nb[k_]:
                if not c1[j_] and not seen_[j_]: seen_[j_] = True; st_.append(j_)
        comps_.append(cc_)
    for cc_ in sorted(comps_, key=len)[:-1]: c1[cc_] = True
    cov = shrink(c1, 3) & (rr < 0.52)   # 두 칸 키운 것 + 한 칸 더 줄여 끝선보다 한 칸 안쪽(막이 끝선 밖으로 안 보이게)
    lf = [[v.index for v in f_.verts] for f_ in bs0.faces if all(cov[v.index] for v in f_.verts)]
    bs0.free()
    # 막 색: 텍스처 빈 모서리에 골 그늘색 칸(알파 1)을 칠하고 막의 UV는 모두 그 칸 가운데
    used = np.zeros((TH, TW), bool); _uv = hme.uv_layers.active.data
    for l_ in hme.loops: u_ = _uv[l_.index].uv; used[min(TH - 1, max(0, int(u_[1] * TH))), min(TW - 1, max(0, int(u_[0] * TW)))] = True
    B_ = max(16, TW // 64); spot = None
    for (y0, x0) in ((TH - 3 * B_, TW - 3 * B_), (B_, B_), (TH - 3 * B_, B_), (B_, TW - 3 * B_)):
        if not used[max(0, y0 - 2 * B_):y0 + 3 * B_, max(0, x0 - 2 * B_):x0 + 3 * B_].any() and not (out[y0:y0 + B_, x0:x0 + B_, 3] > 0).any(): spot = (y0, x0); break
    if spot:
        y0, x0 = spot; gl = np.clip(hc * GROOVE_SHADE, 0, 1); ge = np.where(gl <= 0.0031308, gl * 12.92, 1.055 * np.power(gl, 1 / 2.4) - 0.055)
        out[y0:y0 + B_, x0:x0 + B_, :3] = ge; out[y0:y0 + B_, x0:x0 + B_, 3] = 1.0
        uc = ((x0 + B_ / 2) / TW, (y0 + B_ / 2) / TH)
    else:   # 빈 모서리가 없으면(Meshy 조각이 모서리까지 참) 이미 머리카락인 텍셀 중 둘레 5×5가 모두 머리카락이고 골 그늘 밝기에 가장 가까운 곳
        a_ = out[:, :, 3] > 0.5; inner = a_.copy()
        for dy in range(-2, 3):
            for dx in range(-2, 3): inner &= np.roll(np.roll(a_, dy, 0), dx, 1)
        cand = np.argwhere(inner); k_ = int(np.argmin(np.abs(shade[inner] - GROOVE_SHADE)))
        y0, x0 = cand[k_]; uc = ((x0 + 0.5) / TW, (y0 + 0.5) / TH); spot = ("tex", int(y0), int(x0), round(float(shade[y0, x0]), 3))
    if lf:
        bl = bmesh.new(); vmap = {}
        for p_ in lf:
            for v in p_:
                if v not in vmap: vmap[v] = bl.verts.new(Vector((MV[v] + MN[v] * LINER).tolist()))
        for p_ in lf: bl.faces.new([vmap[v] for v in p_])
        lm = bpy.data.meshes.new("liner"); bl.to_mesh(lm); bl.free()
        lm.uv_layers.new(name=hme.uv_layers.active.name)
        for d_ in lm.uv_layers[0].data: d_.uv = uc
        lg = lm.color_attributes.new("gate", 'FLOAT_COLOR', 'POINT')
        for c_ in lg.data: c_.color = (1, 1, 1, 1)
        lo_ = bpy.data.objects.new("liner", lm); bpy.context.scene.collection.objects.link(lo_)
        _nt = sum(len(p_.vertices) - 2 for p_ in lm.polygons)   # 막은 매끈한 곡면이라 면을 줄여도 모양 그대로(가발 면 예산을 머리카락에 남김)
        if _nt > 1500:
            dm_ = lo_.modifiers.new("dec", 'DECIMATE'); dm_.ratio = 1500 / _nt
            for o in bpy.context.selected_objects: o.select_set(False)
            lo_.select_set(True); bpy.context.view_layer.objects.active = lo_; bpy.ops.object.modifier_apply(modifier="dec")
        liner_faces = len(lo_.data.polygons)
        for o in bpy.context.selected_objects: o.select_set(False)
        lo_.select_set(True); hair.select_set(True); bpy.context.view_layer.objects.active = hair; bpy.ops.object.join()
        hair = bpy.context.view_layer.objects.active
    print("LINER", LINER, "faces", liner_faces, "spot", spot)
mimg = bpy.data.images.new(NAME + "_hair", TW, TH, alpha=True); mimg.pixels = out.ravel(); mimg.filepath_raw = os.path.join(OUT, NAME + "_hair.png"); mimg.file_format = 'PNG'; mimg.save()
hm = bpy.data.materials.new("hair"); hm.use_nodes = True; nt = hm.node_tree; bs = nt.nodes["Principled BSDF"]; bs.inputs["Roughness"].default_value = 0.65
tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = mimg; tx.interpolation = 'Closest'
uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = hair.data.uv_layers[0].name; nt.links.new(uvn.outputs[0], tx.inputs[0])
nt.links.new(tx.outputs["Color"], bs.inputs["Base Color"])
gn = nt.nodes.new("ShaderNodeVertexColor"); gn.layer_name = "gate"
am = nt.nodes.new("ShaderNodeMath"); am.operation = 'MULTIPLY'; nt.links.new(tx.outputs["Alpha"], am.inputs[0]); nt.links.new(gn.outputs["Alpha"], am.inputs[1])
gt = nt.nodes.new("ShaderNodeMath"); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = 0.5; nt.links.new(am.outputs[0], gt.inputs[0])
nt.links.new(gt.outputs[0], bs.inputs["Alpha"])
try: hm.surface_render_method = 'DITHERED'
except Exception: pass
try: hm.blend_method = 'CLIP'
except Exception: pass
hair.data.materials.clear(); hair.data.materials.append(hm)
for o in bpy.context.selected_objects: o.select_set(False)
hair.select_set(True); bpy.context.view_layer.objects.active = hair; bpy.ops.object.shade_smooth()
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), use_selection=True, export_format='GLB')
H = np.array([v.co[:] for v in hair.data.vertices])
rep = {"name": NAME, "fit_error": round(fit_err, 4), "scale_master_per_wig": round(float(1 / s), 4), "guess": round(float(guess), 4), "warp_median": round(warp_mag, 4), "hair_faces": len(hair.data.polygons), "lifted": lifted, "speck_faces_removed": speck_removed, "grey_island_pts": int(len(ISLAND)), "groove_kept_pts": len(groove)}
if LINER > 0: rep["liner_faces"] = liner_faces
json.dump(rep, open(os.path.join(OUT, NAME + "_report.json"), "w"), indent=1)
# --- 기준 머리 + 얼굴 그림에 얹어 4방향
mm = master.data; P = M
sk = bpy.data.materials.new("skin"); sk.use_nodes = True; snt = sk.node_tree; sbs = snt.nodes["Principled BSDF"]; sbs.inputs["Roughness"].default_value = 0.6
if FACE:
    fu = mm.uv_layers.new(name="face")
    for poly in mm.polygons:   # 면 단위로 결정(한 면 안에 비춤/안 비춤이 섞이면 얼굴 그림이 늘어나 옆머리 쪽에 가는 선이 생김)
        front = max(P[mm.loops[li].vertex_index][1] for li in poly.loop_indices) < 0.2
        for li in poly.loop_indices:
            v = P[mm.loops[li].vertex_index]; fu.data[li].uv = (0.5 + v[0], 0.5 + v[2]) if front else (0.001, 0.001)
    un = snt.nodes.new("ShaderNodeUVMap"); un.uv_map = "face"; ft = snt.nodes.new("ShaderNodeTexImage"); ft.extension = 'CLIP'
    ft.image = bpy.data.images.load(FACE); ft.image.alpha_mode = 'STRAIGHT'
    mx = snt.nodes.new("ShaderNodeMix"); mx.data_type = 'RGBA'; mx.inputs[6].default_value = srgb(SKIN)
    snt.links.new(un.outputs[0], ft.inputs[0]); snt.links.new(ft.outputs["Alpha"], mx.inputs[0]); snt.links.new(ft.outputs["Color"], mx.inputs[7]); snt.links.new(mx.outputs[2], sbs.inputs["Base Color"])
else:
    sbs.inputs["Base Color"].default_value = srgb(SKIN)
mm.materials.clear(); mm.materials.append(sk)
for o in bpy.context.selected_objects: o.select_set(False)
master.select_set(True); bpy.context.view_layer.objects.active = master; bpy.ops.object.shade_smooth()
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 500; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True; wd.node_tree.nodes["Background"].inputs[1].default_value = 0.6
for loc, e in (((-2, -4, 2), 260), ((3, -3, 0.5), 110), ((0, 3, 3), 160)):
    l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = loc; sc.collection.objects.link(lo)
    lo.rotation_euler = (Vector((0, 0, 0)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.5
for vn, yaw in (("front", 0), ("45", 40), ("side", 90), ("back", 180)):
    a = math.radians(yaw); cam.location = (6 * math.sin(a), -6 * math.cos(a), 0.05); cam.rotation_euler = (math.pi / 2, 0, a)
    sc.render.filepath = os.path.join(OUT, f"{NAME}_{vn}.png"); bpy.ops.render.render(write_still=True)
print("WIG3", json.dumps(rep))
