# 도담도담 캐릭터 공정: Meshy가 칠한 '머리카락(갈색)+마네킹 머리(회색)' 모델에서 색으로 머리카락 면만 떼어 기준 머리에 맞춘다.
# 11/09 사용자 지적으로 바꾼 방식: 거리로 자르면 짧은 옆머리(아이비리그컷)가 같이 사라지고, 튀어나온 마네킹 피부가 검게 남음.
#  1) 면마다 텍스처 색 → 갈색=머리카락, 회색=마네킹(턱 울퉁불퉁 등은 전부 회색이라 버려짐)
#  2) 회색(마네킹) 점들로만 기준 머리에 맞춤(배율·이동·좌우 ±10도) → 늘어진 머리카락에 끌려가지 않음
#  3) 머리카락 면만 남기고, 두피보다 안쪽에 있는 점은 두피 바로 위로 올림(짧은 머리도 얇게 그대로 남음)
# 실행: Blender -b --factory-startup -P split_wig.py -- --wig TEXTURED.glb --master MASTER_DIR --out OUT_DIR --name NAME [--face FACE.png]
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
WIG, MD, OUT, NAME, FACE = arg("--wig"), arg("--master"), arg("--out"), arg("--name"), arg("--face")
LIFT = 0.006          # 머리카락이 두피보다 최소 이만큼 위에(겹쳐 깜빡임 방지)
BROW_Z = 0.17
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
def load(path):
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=path)
    ms = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in ms: o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1: bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active; bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for x in [x for x in bpy.data.objects if x not in before and x.type != 'MESH']: bpy.data.objects.remove(x)
    return o
master = load(os.path.join(MD, "master_head.glb")); master.name = "master"
wig = load(WIG); wig.name = "wig"; me = wig.data
M = np.array([v.co[:] for v in master.data.vertices]); W = np.array([v.co[:] for v in me.vertices])

# 1) 면마다 색
img = None
for m in me.materials:
    if m and m.node_tree:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image: img = n.image
TW, TH = img.size; px = np.array(img.pixels[:]).reshape(TH, TW, 4)[:, :, :3]
uv = me.uv_layers.active.data
def is_hair(rgb):
    r, g, b = rgb; mx, mn = max(rgb), min(rgb); sat = (mx - mn) / (mx + 1e-6)
    return (r - b > 0.06) and sat > 0.18
lab = []
for p in me.polygons:   # 면 안의 점 여러 개(꼭짓점 쪽 + 가운데)로 다수결
    us = [uv[li].uv[:] for li in p.loop_indices]; c = np.mean(us, axis=0)
    samples = [c] + [(np.array(u) * 0.4 + c * 0.6) for u in us]
    votes = [is_hair(px[min(TH - 1, max(0, int(s[1] * TH))), min(TW - 1, max(0, int(s[0] * TW)))]) for s in samples]
    lab.append(sum(votes) * 2 > len(votes))
lab = np.array(lab)
bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
for _ in range(2):   # 외톨이 면 정리
    new = lab.copy()
    for f in bm.faces:
        nb = [lab[g.index] for e in f.edges for g in e.link_faces if g.index != f.index]
        if len(nb) >= 2 and (all(nb) or not any(nb)): new[f.index] = nb[0]   # 이웃이 전부 반대면 따라감
    lab = new
skin_v = sorted({v.index for f in bm.faces if not lab[f.index] for v in f.verts})
S = W[skin_v]

# 2) 회색 마네킹 점으로만 맞춤
src = M[(M[:, 1] < -0.15) & (M[:, 2] < 0.05) & (M[:, 2] > -0.35)]   # 기준 머리 앞얼굴(볼·턱) — 어떤 머리 모양이어도 피부
src = src[np.random.default_rng(0).choice(len(src), min(1500, len(src)), replace=False)]
kd = KDTree(len(S))
for i, p in enumerate(S): kd.insert(p, i)
kd.balance()
def nn(P): return np.array([kd.find(p)[0][:] for p in P])
def fit_st(A, B):
    ma, mb = A.mean(0), B.mean(0); A0, B0 = A - ma, B - mb
    s = (A0 * B0).sum() / (A0 ** 2).sum(); return s, mb - s * ma
def rotz(deg):
    a = math.radians(deg); c, s_ = math.cos(a), math.sin(a); return np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])
def icp(s0, t0, Rm, iters=40):
    S0 = (Rm @ src.T).T; s, t = s0, t0
    for _ in range(iters):
        X = s * S0 + t; Y = nn(X); d = np.linalg.norm(X - Y, axis=1); keep = d < np.percentile(d, 85)
        s, t = fit_st(S0[keep], Y[keep])
    X = s * S0 + t; d = np.linalg.norm(X - nn(X), axis=1)
    return s, Rm, t, float(np.mean(d) / s)
low = S[S[:, 2] < np.percentile(S[:, 2], 50)]
guess = (low[:, 0].max() - low[:, 0].min()) / (M[:, 0].max() - M[:, 0].min())
cands = []
for yaw in (-10, -5, 0, 5, 10):
    for f in (0.85, 1.0, 1.15):
        s0 = guess * f
        t0 = np.array([np.median(S[:, 0]), np.median(S[:, 1]), S[:, 2].min() - s0 * M[:, 2].min()])
        cands.append(icp(s0, t0, rotz(yaw)))
s, Rm, t, fit_err = min(cands, key=lambda c: c[3])
inv = np.linalg.inv(Rm) / s
Wm = (W - t) @ inv.T

# 3) 머리카락 면만 남기고 기준 좌표로
for v in bm.verts: v.co = Vector(Wm[v.index])
bmesh.ops.delete(bm, geom=[f for f in bm.faces if not lab[f.index]], context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
bmM = bmesh.new(); bmM.from_mesh(master.data); bvhM = BVHTree.FromBMesh(bmM)
# 11/09 앉히기: 얼굴로만 맞추면 머리 윗부분 크기 차이로 가발이 붕 뜸 → 머리카락이 끝나는 선(헤어라인·뒷머리 끝 = 열린 테두리)이
# 우리 두피에 닿도록 배율·이동을 한 번 더 맞춤(모양은 그대로, 앉는 자리만)
seat = {}
if "--noseat" not in argv:
    bnd = [v for v in bm.verts if any(e.is_boundary for e in v.link_edges)]
    def sdv_(p):
        loc, nrm, idx, d = bvhM.find_nearest(p); return d if (p - loc).dot(nrm) >= 0 else -d
    seat["boundary_sd_before"] = round(float(np.mean([sdv_(v.co) for v in bnd])), 4)
    # 머리 중심 기준으로 조금씩 줄이다가, 두피가 머리카락을 뚫기 시작하기 직전 크기에서 멈춤(헤어라인을 억지로 붙이면 너무 조여서 두피가 뚫고 나옴)
    A0 = np.array([v.co[:] for v in bm.verts])
    def pen(k):
        P_ = A0 * k; return float(np.mean([sdv_(Vector(p)) < 0 for p in P_[::3]]))
    base = pen(1.0); best = 1.0
    for k in np.arange(0.99, 0.80, -0.01):
        if pen(k) > base + 0.02: break
        best = float(k)
    for i, v in enumerate(bm.verts): v.co = Vector(A0[i] * best)
    seat["scale"] = round(best, 3)
    seat["boundary_sd_after"] = round(float(np.mean([sdv_(v.co) for v in bnd])), 4)
# 11/09 가장자리 붙이기: 갈색 겉껍질만 남아서 가장자리가 두피보다 떠 있으면 그 틈으로 속이 보임
# → 열린 테두리 근처 점만 두피 쪽으로 당김(테두리에서 EDGE_R 멀어질수록 덜 당김, 볼륨·모양은 그대로)
EDGE_R = float(arg("--edge", "0"))   # 11/09 시험 결과 머리카락이 찢어져서 기본 끔
if EDGE_R > 0:
    bnd_v = [v for v in bm.verts if any(e.is_boundary for e in v.link_edges)]
    kdb = KDTree(len(bnd_v))
    for i, v in enumerate(bnd_v): kdb.insert(v.co, i)
    kdb.balance()
    moved = 0
    for v in bm.verts:
        dB = kdb.find(v.co)[2]
        if dB >= EDGE_R: continue
        t_ = 1 - dB / EDGE_R; w_ = t_ * t_ * (3 - 2 * t_)
        loc, nrm, idx, d = bvhM.find_nearest(v.co)
        tgt = loc + nrm * 0.006
        if (v.co - loc).dot(nrm) > 0.006:
            v.co = v.co.lerp(tgt, w_); moved += 1
    seat["edge_pulled"] = moved
# 11/09 두피에 붙이기: 가장자리가 두피에서 뜬 만큼(테두리 높이 중앙값) 모든 점을 두피 쪽으로 같은 거리만큼 당김(두피 밑으로는 안 감)
DEFL = arg("--deflate", "0")   # 11/09 시험: 얇아져 두피가 비쳐서 기본 끔
bnd_all = [v for v in bm.verts if any(e.is_boundary for e in v.link_edges)]
def sd_(p):
    loc, nrm, idx, d = bvhM.find_nearest(p); return (d if (p - loc).dot(nrm) >= 0 else -d), loc, nrm
c_off = float(np.median([sd_(v.co)[0] for v in bnd_all])) if DEFL == "auto" else float(DEFL)
c_off = max(0.0, c_off)
for v in bm.verts:
    d_, loc, nrm = sd_(v.co)
    if d_ > 0.006: v.co = loc + nrm * max(0.006, d_ - c_off)
seat["deflate"] = round(c_off, 3)
lifted = 0
for v in bm.verts:   # 두피보다 안쪽·딱 붙은 점은 두피 바로 위로(짧은 옆머리도 얇은 층으로 남음)
    loc, nrm, idx, d = bvhM.find_nearest(v.co)
    sdv = d if (v.co - loc).dot(nrm) >= 0 else -d
    if sdv < LIFT: v.co = loc + nrm * LIFT; lifted += 1
bm.to_mesh(me); bm.free(); me.update()
# 떨어진 부스러기 정리
for o in bpy.context.selected_objects: o.select_set(False)
wig.select_set(True); bpy.context.view_layer.objects.active = wig
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.separate(type='LOOSE'); bpy.ops.object.mode_set(mode='OBJECT')
parts = [o for o in bpy.context.selected_objects]; big = max(len(o.data.polygons) for o in parts)
for o in parts:
    if len(o.data.polygons) < 0.02 * big: bpy.data.objects.remove(o)
parts = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith("wig")]
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
if len(parts) > 1: bpy.ops.object.join()
hair = bpy.context.view_layer.objects.active; hair.name = NAME
for uvl in list(hair.data.uv_layers): pass
# 11/09 가발 안감: 가발이 덮는 두피 부분에 머리색 얇은 막(두피 위 0.004) → 가발과 두피 사이 틈으로 빈 속이 안 보이게
if "--nocap" not in argv:
    bmH = bmesh.new(); bmH.from_mesh(hair.data); bvhH = BVHTree.FromBMesh(bmH)
    capm = master.data.copy(); bc = bmesh.new(); bc.from_mesh(capm); bc.normal_update()
    keep = set()
    for f in bc.faces:
        c = f.calc_center_median(); n = f.normal
        if bvhH.ray_cast(c + n * 1e-3, n, 0.6)[0] is not None: keep.add(f.index)
    bmesh.ops.delete(bc, geom=[f for f in bc.faces if f.index not in keep], context='FACES')
    bmesh.ops.delete(bc, geom=[v for v in bc.verts if not v.link_faces], context='VERTS')
    for v in bc.verts: v.co = v.co + v.normal * 0.004
    bc.to_mesh(capm); bc.free(); bmH.free()
    cap = bpy.data.objects.new("cap", capm); bpy.context.scene.collection.objects.link(cap)
    for o in bpy.context.selected_objects: o.select_set(False)
    cap.select_set(True); hair.select_set(True); bpy.context.view_layer.objects.active = hair; bpy.ops.object.join()
H = np.array([v.co[:] for v in hair.data.vertices])
cover = int(((H[:, 1] < -0.2) & (np.abs(H[:, 0]) < 0.3) & (H[:, 2] < BROW_Z)).sum())
rep = {"name": NAME, "fit_error": round(fit_err, 4), "scale": round(float(1 / s), 4), "hair_faces": len(hair.data.polygons),
       "skin_faces_dropped": int((~lab).sum()), "lifted_verts": lifted, "seat": seat, "face_cover_verts": cover,
       "pass": {"fit": fit_err <= 0.03, "face_cover": cover == 0}}
json.dump(rep, open(os.path.join(OUT, NAME + "_report.json"), "w"), indent=1)
hm = bpy.data.materials.new("hair"); hm.use_nodes = True
def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]; return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1]
hm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = srgb("#4A3226"); hm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.65
hair.data.materials.clear(); hair.data.materials.append(hm)
for o in bpy.context.selected_objects: o.select_set(False)
hair.select_set(True); bpy.context.view_layer.objects.active = hair; bpy.ops.object.shade_smooth()
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), use_selection=True, export_format='GLB')
# 기준 머리 + 얼굴 그림 위에 얹어 4방향
mm = master.data; P = np.array([v.co[:] for v in mm.vertices])
sk = bpy.data.materials.new("skin"); sk.use_nodes = True; nt = sk.node_tree; bs = nt.nodes["Principled BSDF"]; bs.inputs["Roughness"].default_value = 0.6
if FACE:
    fu = mm.uv_layers.new(name="face")
    for poly in mm.polygons:
        for li in poly.loop_indices:
            v = P[mm.loops[li].vertex_index]; fu.data[li].uv = (0.5 + v[0], 0.5 + v[2]) if v[1] < 0.2 else (0.001, 0.001)
    un = nt.nodes.new("ShaderNodeUVMap"); un.uv_map = "face"; tx = nt.nodes.new("ShaderNodeTexImage"); tx.extension = 'CLIP'
    tx.image = bpy.data.images.load(FACE); tx.image.alpha_mode = 'STRAIGHT'
    mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = 'RGBA'; mx.inputs[6].default_value = srgb("#F2C9AC")
    nt.links.new(un.outputs[0], tx.inputs[0]); nt.links.new(tx.outputs["Alpha"], mx.inputs[0]); nt.links.new(tx.outputs["Color"], mx.inputs[7]); nt.links.new(mx.outputs[2], bs.inputs["Base Color"])
else:
    bs.inputs["Base Color"].default_value = srgb("#F2C9AC")
mm.materials.clear(); mm.materials.append(sk)
master.select_set(True); bpy.context.view_layer.objects.active = master; bpy.ops.object.shade_smooth()
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 500; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True; wd.node_tree.nodes["Background"].inputs[1].default_value = 0.6
for loc, e in (((-2, -4, 2), 260), ((3, -3, 0.5), 110), ((0, 3, 3), 120)):
    l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = loc; sc.collection.objects.link(lo)
    lo.rotation_euler = (Vector((0, 0, 0)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.5
for vn, yaw in (("front", 0), ("45", 40), ("side", 90), ("back", 180)):
    a = math.radians(yaw); cam.location = (6 * math.sin(a), -6 * math.cos(a), 0.05); cam.rotation_euler = (math.pi / 2, 0, a)
    sc.render.filepath = os.path.join(OUT, f"{NAME}_{vn}.png"); bpy.ops.render.render(write_still=True)
print("SPLIT", json.dumps(rep))
