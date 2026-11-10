# 도담도담 캐릭터 공정 2단계: 몸 모델에서 '기준 머리'를 떼어 저장하고, GPT 가발 의뢰용 회색 그림을 뽑는다.
# 실행: Blender -b --factory-startup -P master_head.py -- --body BODY.glb --out OUTDIR [--smooth]
# 결과:
#   OUTDIR/master_head.json  머리 중심·반지름·목 높이, 몸 → 기준 좌표 변환(머리 중심 원점, 머리 지름 1)
#   OUTDIR/master_head.glb   목 위 머리만(기준 좌표)
#   OUTDIR/head_front.png, head_45.png, head_side.png  흰 바탕 회색 머리(정투영, 1024)
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default
BODY = arg("--body"); OUT = arg("--out"); SMOOTH = "--smooth" in argv
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=BODY)
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1: bpy.ops.object.join()
body = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
if SMOOTH:  # 무료 Lite처럼 표면이 거친 모델만
    m = body.modifiers.new("rm", 'REMESH'); m.mode = 'VOXEL'; m.voxel_size = 0.011
    s = body.modifiers.new("sm", 'SMOOTH'); s.factor = 0.9; s.iterations = 14
    bpy.ops.object.modifier_apply(modifier="rm"); bpy.ops.object.modifier_apply(modifier="sm")
me = body.data
P = np.array([v.co[:] for v in me.vertices])
zmin, zmax = P[:, 2].min(), P[:, 2].max(); H = zmax - zmin

# 1) 목 높이: 키의 40~75% 구간에서 가로 폭이 가장 좁은 곳
best = None
for z in np.linspace(zmin + 0.40 * H, zmin + 0.75 * H, 80):
    sl = P[np.abs(P[:, 2] - z) < 0.006 * H]
    if len(sl) < 12: continue
    w = sl[:, 0].max() - sl[:, 0].min()
    if best is None or w < best[0]: best = (w, z)
neck_z = float(best[1])

# 2) 머리 구 맞추기(목 위, 귀를 빼려고 가로 가운데만)
Hd = P[P[:, 2] > neck_z + 0.03 * H]
xw = np.percentile(np.abs(Hd[:, 0]), 80)
core = Hd[np.abs(Hd[:, 0]) < xw]
A = np.c_[2 * core, np.ones(len(core))]; b = (core ** 2).sum(1)
sol = np.linalg.lstsq(A, b, rcond=None)[0]; C = sol[:3]; R = float(math.sqrt(sol[3] + (C ** 2).sum()))
resid = np.abs(np.linalg.norm(core - C, axis=1) - R).mean() / R

# 3) 기준 좌표: 머리 중심 원점, 머리 지름 1
k = 0.5 / R
T = Matrix.Scale(k, 4) @ Matrix.Translation(Vector(-C))
info = {"center_body": [float(x) for x in C], "radius_body": R, "neck_z_body": neck_z,
        "body_height": float(H), "sphere_fit_error": float(resid),
        "to_master": [list(r) for r in T], "note": "기준 좌표 = (몸 좌표 - center) * 0.5/radius. 앞은 -Y, 위는 +Z"}

# 4) 목 위만 남겨 저장
bm = bmesh.new(); bm.from_mesh(me)
bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, neck_z), plane_no=(0, 0, 1), clear_inner=True)
bm.to_mesh(me); bm.free()
body.data.transform(T); body.matrix_world = Matrix.Identity(4); me.update()
body.name = "master_head"
for mt in list(me.materials): pass
me.materials.clear()
grey = bpy.data.materials.new("grey"); grey.use_nodes = True
bs = grey.node_tree.nodes["Principled BSDF"]; bs.inputs["Base Color"].default_value = (0.32, 0.32, 0.32, 1); bs.inputs["Roughness"].default_value = 0.7
me.materials.append(grey)
bpy.ops.object.shade_smooth()
info["faces"] = len(me.polygons)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "master_head.glb"), use_selection=True, export_format='GLB')
json.dump(info, open(os.path.join(OUT, "master_head.json"), "w"), ensure_ascii=False, indent=1)

# 5) GPT용 그림: 흰 바탕, 고른 빛, 정투영
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 1024; sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.35
sc.render.film_transparent = True  # 바탕은 나중에 흰색으로 깔아 머리만 회색으로 또렷하게
def area(loc, power):
    l = bpy.data.lights.new("a", 'AREA'); l.energy = power; l.size = 4
    o = bpy.data.objects.new("a", l); o.location = loc; sc.collection.objects.link(o)
    o.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
area((-2, -4, 2), 120); area((2.5, -3, 0.5), 60)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.6
for name, yaw in (("head_front", 0), ("head_45", 45), ("head_side", 90)):
    a = math.radians(yaw)
    cam.location = (6 * math.sin(a), -6 * math.cos(a), 0.0); cam.rotation_euler = (math.pi / 2, 0, a)
    sc.render.filepath = os.path.join(OUT, name + ".png"); bpy.ops.render.render(write_still=True)
# 투명 바탕 → 흰 바탕
try:
    from PIL import Image  # 블렌더 파이썬에 없으면 건너뜀(투명 PNG 그대로)
except Exception:
    Image = None
print("MASTER_HEAD", json.dumps({k_: info[k_] for k_ in ("radius_body", "neck_z_body", "sphere_fit_error", "faces")}))
