# 도담도담 캐릭터 공정: Meshy '분할'(Meshy 7.1 + 분할 켜기)로 나온 부품 중 머리카락 부품만 떼어 기준 머리에 얹는다.
# 11/09 사용자 지시: "meshy 기능으로 원본 모델에서 머리통만 분리해서 머리카락만 우리 모델에 조립" — 색·거리로 자르지 않음.
#  - 부품 구분: 가장 면이 많고 위쪽에 있는 부품 = 머리카락, 가장 큰 공 모양 = 머리통, 양옆 작은 것 = 귀
#  - 머리통 부품으로만 기준 머리에 맞춤(배율·이동·좌우 ±10도), 같은 변환을 머리카락에 적용
#  - 머리카락은 면 수만 줄임(모양은 Meshy 그대로), 두피 안쪽으로 들어간 점만 두피 위로
# (attach_seg_head: 부품 전부를 통째 머리로 써서 B3 몸 목 위에 붙임)
# 실행: Blender -b --factory-startup -P attach_seg_head.py -- --seg SPLIT.glb --master MASTER_DIR --out OUT_DIR --name NAME [--faces 5000] [--face FACE.png]
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
SEG, MD, OUT, NAME, FACE = arg("--seg"), arg("--master"), arg("--out"), arg("--name"), arg("--face")
NF = int(arg("--faces", "5000")); LIFT = 0.004; BROW_Z = 0.17
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(MD, "master_head.glb"))
master = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]; master.name = "master"
before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=SEG)
parts = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
for o in parts:
    o.select_set(True); bpy.context.view_layer.objects.active = o
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
def pts(o): return np.array([v.co[:] for v in o.data.vertices])
info = []
for o in parts:
    P = pts(o); info.append((o, P, P.max(0) - P.min(0)))
# 귀: 폭이 아주 좁은 것 / 머리카락: 위쪽 끝이 가장 높은 것 / 머리통: 나머지 중 가장 큰 것
big = [x for x in info if x[2][0] > 0.4 * max(i[2][0] for i in info)]
hair_o = max(big, key=lambda x: x[1][:, 2].max())[0]
head_o = max([x for x in big if x[0] is not hair_o], key=lambda x: len(x[1]))[0]
M = pts(master); H = pts(head_o)
H = H[np.random.default_rng(0).choice(len(H), min(30000, len(H)), replace=False)]
src = M[(M[:, 1] < -0.15) & (M[:, 2] < 0.05) & (M[:, 2] > -0.35)]
src = src[np.random.default_rng(1).choice(len(src), min(1500, len(src)), replace=False)]
kd = KDTree(len(H))
for i, p in enumerate(H): kd.insert(p, i)
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
guess = (H[:, 0].max() - H[:, 0].min()) / (M[:, 0].max() - M[:, 0].min() - 0.12)   # 기준 머리 폭에서 귀 빼고 대충
ctr = (H.max(0) + H.min(0)) / 2
cands = [icp(guess * f, ctr + np.array([0, 0, dz * guess]), rotz(y)) for y in (-10, -5, 0, 5, 10) for f in (0.9, 1.0, 1.1) for dz in (-0.05, 0, 0.05)]
s, Rm, t, fit_err = min(cands, key=lambda c: c[3])
inv = np.linalg.inv(Rm) / s
# 부품 전부 기준 좌표 → 몸 좌표, 면 수만 줄임(모양은 Meshy 그대로). 머리통·귀=피부(+얼굴 그림), 머리카락=머리색
mj = json.load(open(os.path.join(MD, "master_head.json"))); C = Vector(mj["center_body"]); RB = mj["radius_body"]
M2B = Matrix.Translation(C) @ Matrix.Scale(RB / 0.5, 4)
def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]; return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1]
SK, HC = arg("--skin", "#F2C9AC"), arg("--hair", "#4A3226")
bpy.data.objects.remove(master)
skin_objs = []
for o in parts:
    me = o.data; is_hair = o is hair_o
    target = NF if is_hair else (int(NF * 0.7) if o is head_o else 400)
    for x in bpy.context.selected_objects: x.select_set(False)
    o.select_set(True); bpy.context.view_layer.objects.active = o
    if len(me.polygons) > target:
        dm = o.modifiers.new("dec", 'DECIMATE'); dm.ratio = target / len(me.polygons); bpy.ops.object.modifier_apply(modifier="dec")
    Wm = (pts(o) - t) @ inv.T
    if not is_hair:
        uvf = me.uv_layers.new(name="face")
        for poly in me.polygons:
            front = min(Wm[me.loops[li].vertex_index][1] for li in poly.loop_indices) < 0.0
            for li in poly.loop_indices:
                v = Wm[me.loops[li].vertex_index]; uvf.data[li].uv = (0.5 + v[0], 0.5 + v[2]) if front else (0.001, 0.001)
    for i, v in enumerate(me.vertices): v.co = M2B @ Vector(Wm[i])
    me.update()
    m = bpy.data.materials.new("hair" if is_hair else "skin"); m.use_nodes = True; nt = m.node_tree; bs = nt.nodes["Principled BSDF"]
    bs.inputs["Roughness"].default_value = 0.65 if is_hair else 0.6
    if is_hair or not FACE: bs.inputs["Base Color"].default_value = srgb(HC if is_hair else SK)
    else:
        un = nt.nodes.new("ShaderNodeUVMap"); un.uv_map = "face"; tx = nt.nodes.new("ShaderNodeTexImage"); tx.extension = 'CLIP'
        tx.image = bpy.data.images.load(FACE, check_existing=True); tx.image.alpha_mode = 'STRAIGHT'
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = 'RGBA'; mx.inputs[6].default_value = srgb(SK)
        nt.links.new(un.outputs[0], tx.inputs[0]); nt.links.new(tx.outputs["Alpha"], mx.inputs[0]); nt.links.new(tx.outputs["Color"], mx.inputs[7]); nt.links.new(mx.outputs[2], bs.inputs["Base Color"])
    me.materials.clear(); me.materials.append(m); bpy.ops.object.shade_smooth()
body = None
before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=arg("--body"))
body = [o for o in bpy.data.objects if o not in before and o.type == 'MESH'][0]
bm = bmesh.new(); bm.from_mesh(body.data); NECK = mj["neck_z_body"]; zc = NECK + 0.25 * (C.z - RB - NECK) + 0.02 * RB
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z > zc], context='VERTS'); bm.to_mesh(body.data); bm.free()
for mat in body.data.materials:
    b_ = mat.node_tree.nodes["Principled BSDF"]
    if mat.name.startswith("skin"): b_.inputs["Base Color"].default_value = srgb(SK)
    if mat.name.startswith("shirt"): b_.inputs["Base Color"].default_value = srgb(arg("--shirt", "#5AA9F0"))
for x in bpy.context.selected_objects: x.select_set(False)
body.select_set(True); bpy.context.view_layer.objects.active = body; bpy.ops.object.shade_smooth()
P = np.array([v.co[:] for o in bpy.data.objects if o.type == 'MESH' for v in o.data.vertices]); zmin, zmax = P[:, 2].min(), P[:, 2].max(); Ht = zmax - zmin
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 420, 560; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True; wd.node_tree.nodes["Background"].inputs[1].default_value = 0.6
for loc, e in (((-2, -4, 2), 220), ((3, -3, 0.5), 90), ((0, 3, 3), 100)):
    l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = loc; sc.collection.objects.link(lo)
    lo.rotation_euler = (Vector((0, 0, zmin + 0.6 * Ht)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.type = 'ORTHO'
for vn, yaw, scale, cz in (("full_front", 0, 1.15, 0.5), ("full_45", 40, 1.15, 0.5), ("head_front", 0, 0.5, 0.78), ("head_45", 40, 0.5, 0.78), ("head_side", 90, 0.5, 0.78), ("head_back", 180, 0.5, 0.78), ("zoom_side", 70, 0.22, 0.80)):
    cam.data.ortho_scale = Ht * scale; a = math.radians(yaw)
    cam.location = (6 * math.sin(a), -6 * math.cos(a), zmin + cz * Ht); cam.rotation_euler = (math.pi / 2, 0, a)
    sc.render.filepath = os.path.join(OUT, f"{NAME}_{vn}.png"); bpy.ops.render.render(write_still=True)
print("SEGHEAD", json.dumps({"name": NAME, "fit_error": round(fit_err, 4), "faces": {o.name: len(o.data.polygons) for o in bpy.data.objects if o.type == 'MESH'}}))
