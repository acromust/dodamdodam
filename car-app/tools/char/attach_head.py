# 도담도담 캐릭터 공정(시험): Meshy가 만든 '머리카락+머리통' 모델을 통째로 B3 몸 목 위에 붙인다.
# 11/09 사용자 제안: 분리하지 말고 그대로 머리로 쓰기. 크레딧 안 듦(이미 받은 텍스처 모델 사용).
#  - 위치: 텍스처가 회색(마네킹)인 점으로 기준 머리에 맞춤 → 몸 좌표로
#  - 색: Meshy 텍스처의 빨강-파랑 비율로 머리카락 정도(0~1)를 픽셀마다 계산 → 피부색↔머리색 섞기(옆머리 페이드 그대로)
#  - 얼굴: 우리 GPT 얼굴 그림을 앞에서 비춰 입힘
#  - 몸: 목 위(머리)를 지움
# 실행: Blender -b --factory-startup -P attach_head.py -- --head TEX.glb --body BODY_PARTS.glb --master MASTER_DIR --face FACE.png --out OUT --name NAME
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
HEAD, BODY, MD, FACE, OUT, NAME = arg("--head"), arg("--body"), arg("--master"), arg("--face"), arg("--out"), arg("--name")
SKIN, HAIR, SHIRT = arg("--skin", "#F2C9AC"), arg("--hair", "#2B2522"), arg("--shirt", "#5AA9F0")
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
mj = json.load(open(os.path.join(MD, "master_head.json")))
C = Vector(mj["center_body"]); R = mj["radius_body"]; NECK = mj["neck_z_body"]
M2B = Matrix.Translation(C) @ Matrix.Scale(R / 0.5, 4)
master = load(os.path.join(MD, "master_head.glb")); M = np.array([v.co[:] for v in master.data.vertices])
head = load(HEAD); me = head.data
img = [n.image for m in me.materials for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image][0]
TW, TH = img.size; px = np.array(img.pixels[:]).reshape(TH, TW, 4)[:, :, :3]
W = np.array([v.co[:] for v in me.vertices])
col = np.zeros((len(W), 3)); cnt = np.zeros(len(W)); uv = me.uv_layers.active.data
for p in me.polygons:
    for li in p.loop_indices:
        u = uv[li].uv; col[me.loops[li].vertex_index] += px[min(TH - 1, int(u[1] * TH)), min(TW - 1, int(u[0] * TW))]; cnt[me.loops[li].vertex_index] += 1
col /= np.maximum(cnt, 1)[:, None]
chroma = (col[:, 0] - col[:, 2]) / (col[:, 0] + 1e-3)
S = W[chroma < 0.08]                              # 마네킹(회색) 점
src = M[(M[:, 1] < -0.15) & (M[:, 2] < 0.05) & (M[:, 2] > -0.35)]
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
cands = [icp(guess * f, np.array([np.median(S[:, 0]), np.median(S[:, 1]), S[:, 2].min() - guess * f * M[:, 2].min()]), rotz(y)) for y in (0,) for f in (0.85, 1.0, 1.15)]   # 11/09 사용자 지적: 좌우로 돌아가 보임 → Meshy는 정면 그림으로 만들어 정면이므로 회전 안 함
s, Rm, t, fit_err = min(cands, key=lambda c: c[3])
# 좌우 가운데 맞춤: 마네킹 회색 점의 좌우 중심을 기준 머리 가운데(x=0)로
t[0] = float(np.median(S[:, 0]))
Wm = (W - t) @ (np.linalg.inv(Rm) / s).T                    # 기준 좌표(머리 지름 1)
# 얼굴 그림 UV(기준 좌표에서 앞으로 비추기)
fu = me.uv_layers.new(name="face")
for p in me.polygons:   # 면 단위로 결정(한 면 안에 비춤/안 비춤이 섞이면 얼굴 그림이 늘어나 검은 삼각형이 생김)
    front = min(Wm[me.loops[li].vertex_index][1] for li in p.loop_indices) < 0.0
    for li in p.loop_indices:
        v = Wm[me.loops[li].vertex_index]; fu.data[li].uv = (0.5 + v[0], 0.5 + v[2]) if front else (0.001, 0.001)
for i, v in enumerate(me.vertices): v.co = M2B @ Vector(Wm[i])     # 몸 좌표로
me.update()
# 머리 재질: 텍스처 빨강-파랑 비율 → 머리카락 정도 → 피부/머리색, 그 위에 얼굴 그림
m = bpy.data.materials.new("head"); m.use_nodes = True; nt = m.node_tree; bs = nt.nodes["Principled BSDF"]; bs.inputs["Roughness"].default_value = 0.6
uv0 = nt.nodes.new("ShaderNodeUVMap"); uv0.uv_map = me.uv_layers[0].name
tx0 = nt.nodes.new("ShaderNodeTexImage"); tx0.image = img; nt.links.new(uv0.outputs[0], tx0.inputs[0])
sep = nt.nodes.new("ShaderNodeSeparateColor"); nt.links.new(tx0.outputs["Color"], sep.inputs[0])
sub = nt.nodes.new("ShaderNodeMath"); sub.operation = 'SUBTRACT'; nt.links.new(sep.outputs[0], sub.inputs[0]); nt.links.new(sep.outputs[2], sub.inputs[1])
add = nt.nodes.new("ShaderNodeMath"); add.operation = 'ADD'; add.inputs[1].default_value = 0.001; nt.links.new(sep.outputs[0], add.inputs[0])
div = nt.nodes.new("ShaderNodeMath"); div.operation = 'DIVIDE'; nt.links.new(sub.outputs[0], div.inputs[0]); nt.links.new(add.outputs[0], div.inputs[1])
mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs[1].default_value = 0.05; mr.inputs[2].default_value = 0.55; nt.links.new(div.outputs[0], mr.inputs[0])
hs = nt.nodes.new("ShaderNodeMix"); hs.data_type = 'RGBA'; hs.inputs[6].default_value = srgb(SKIN); hs.inputs[7].default_value = srgb(HAIR)
hm2 = mr
nt.links.new(mr.outputs[0], hs.inputs[0])
uvf = nt.nodes.new("ShaderNodeUVMap"); uvf.uv_map = "face"; txf = nt.nodes.new("ShaderNodeTexImage"); txf.extension = 'CLIP'
txf.image = bpy.data.images.load(FACE); txf.image.alpha_mode = 'STRAIGHT'; nt.links.new(uvf.outputs[0], txf.inputs[0])
# 얼굴 그림은 머리카락 아래에만(앞머리가 덮으면 머리카락이 위)
inv = nt.nodes.new("ShaderNodeMath"); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0; nt.links.new(hm2.outputs[0], inv.inputs[1])
fa = nt.nodes.new("ShaderNodeMath"); fa.operation = 'MULTIPLY'; nt.links.new(txf.outputs["Alpha"], fa.inputs[0]); nt.links.new(inv.outputs[0], fa.inputs[1])
fm = nt.nodes.new("ShaderNodeMix"); fm.data_type = 'RGBA'; nt.links.new(fa.outputs[0], fm.inputs[0]); nt.links.new(hs.outputs[2], fm.inputs[6]); nt.links.new(txf.outputs["Color"], fm.inputs[7])
# 11/09: Meshy 텍스처의 명암(머리카락 결·그라데이션)을 버리지 않고 색만 바꿈 → 텍스처 밝기를 곱함
bw = nt.nodes.new("ShaderNodeRGBToBW"); nt.links.new(tx0.outputs["Color"], bw.inputs[0])
ref = nt.nodes.new("ShaderNodeMix"); ref.data_type = 'FLOAT'; ref.inputs[2].default_value = 0.62; ref.inputs[3].default_value = 0.10   # 회색 마네킹·갈색 머리 평균 밝기(선형)
nt.links.new(hm2.outputs[0], ref.inputs[0])
shade = nt.nodes.new("ShaderNodeMath"); shade.operation = 'DIVIDE'; nt.links.new(bw.outputs[0], shade.inputs[0]); nt.links.new(ref.outputs[0], shade.inputs[1])
clamp = nt.nodes.new("ShaderNodeClamp"); clamp.inputs[1].default_value = 0.55; clamp.inputs[2].default_value = 1.35; nt.links.new(shade.outputs[0], clamp.inputs[0])
mul = nt.nodes.new("ShaderNodeMix"); mul.data_type = 'RGBA'; mul.blend_type = 'MULTIPLY'; mul.inputs[0].default_value = 1.0
nt.links.new(fm.outputs[2], mul.inputs[6]); nt.links.new(clamp.outputs[0], mul.inputs[7])
nt.links.new(mul.outputs[2], bs.inputs["Base Color"])
me.materials.clear(); me.materials.append(m)
# Meshy 원본에 있는 작은 구멍(턱 검은 삼각형 2개) 메우기: UV 이음매로 갈라진 점만 붙인 뒤 6변 이하 구멍만 메움(면 방향은 그대로)
bmh = bmesh.new(); bmh.from_mesh(me)
bmesh.ops.remove_doubles(bmh, verts=bmh.verts[:], dist=1e-4)
print('BOUNDARY after weld', sum(1 for e in bmh.edges if e.is_boundary))
filled = bmesh.ops.holes_fill(bmh, edges=[e for e in bmh.edges if e.is_boundary], sides=6)["faces"]
# 점을 붙여 거의 닫힌 덩어리가 됐으니 면 방향을 바깥으로 통일(턱 검은 삼각형 = 안쪽을 향한 면)
nf0 = [f.normal.copy() for f in bmh.faces]; bmesh.ops.recalc_face_normals(bmh, faces=bmh.faces[:]); bmh.normal_update()
print('FLIPPED', sum(1 for f, n in zip(bmh.faces, nf0) if f.normal.dot(n) < 0))
bmh.to_mesh(me); bmh.free(); me.update()
print("HOLES", len(filled))
for o in bpy.context.selected_objects: o.select_set(False)
head.select_set(True); bpy.context.view_layer.objects.active = head; SMOOTH = arg("--smooth", "angle")
if SMOOTH == "subd":   # 면을 한 번 둥글게 나눠 각진 삼각형을 없앰(Meshy 2천 면이 거칠 때)
    sd_ = head.modifiers.new("subd", 'SUBSURF'); sd_.levels = 1; sd_.render_levels = 1; bpy.ops.object.modifier_apply(modifier="subd"); bpy.ops.object.shade_smooth()
elif SMOOTH == "smooth": bpy.ops.object.shade_smooth()
else: bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
for vn in ("head_side_zoom",): pass
bpy.data.objects.remove(master)
# 몸: 목 위 지움 + 부위 색
body = load(BODY); bm = bmesh.new(); bm.from_mesh(body.data)
zc = NECK + 0.25 * (C.z - R - NECK) + 0.02 * R      # 목 윗부분(머리 바닥 바로 아래)까지만 남김
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z > zc], context='VERTS'); bm.to_mesh(body.data); bm.free()
HZ = np.array([v.co.z for v in me.vertices]); BZ = np.array([v.co.z for v in body.data.vertices])
print("NECK head_bottom", round(float(HZ.min()), 4), "body_top", round(float(BZ.max()), 4), "gap", round(float(HZ.min() - BZ.max()), 4), "head_R", round(R, 4))
for mat in body.data.materials:
    b_ = mat.node_tree.nodes["Principled BSDF"]
    if mat.name.startswith("skin"): b_.inputs["Base Color"].default_value = srgb(SKIN)
    if mat.name.startswith("shirt"): b_.inputs["Base Color"].default_value = srgb(SHIRT)
for o in bpy.context.selected_objects: o.select_set(False)
body.select_set(True); bpy.context.view_layer.objects.active = body; bpy.ops.object.shade_smooth()
P = np.array([v.co[:] for o in (body, head) for v in o.data.vertices]); zmin, zmax = P[:, 2].min(), P[:, 2].max(); Ht = zmax - zmin
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
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + "_head.glb"), use_selection=False, export_format='GLB')
print("ATTACH", json.dumps({"name": NAME, "fit_error": round(fit_err, 4), "head_faces": len(me.polygons)}))
