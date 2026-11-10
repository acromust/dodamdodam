# 도담도담 캐릭터 공정: 얼굴형 3종(동글=기본, 갸름, 각진)을 기준 머리의 '아래쪽'만 바꿔 만든다.
# 정수리·옆머리 자리는 그대로 둬서 가발 13개가 어느 얼굴형에도 그대로 맞게 한다.
# 실행: Blender -b --factory-startup -P face_shapes.py -- --master MASTER_DIR --out OUT_DIR [--wig WIG.glb] [--face FACE.png]
# 결과: OUT/face_shapes.glb(기준 머리 + 모양 키 slim·square·full), OUT/face_shapes_report.json(가발 뚫림 검사), OUT/shape_*.png
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
MD = arg("--master"); OUT = arg("--out"); WIG = arg("--wig"); FACE = arg("--face")
os.makedirs(OUT, exist_ok=True)
Z_KEEP = 0.02     # 이 높이 위(눈 위쪽)는 절대 안 바뀜
Z_FULL = -0.30    # 이 높이 아래는 완전히 바뀜

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(MD, "master_head.glb"))
head = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]; head.name = "head"
me = head.data
base = np.array([v.co[:] for v in me.vertices])
def ramp(z):
    t = np.clip((Z_KEEP - z) / (Z_KEEP - Z_FULL), 0, 1); return t * t * (3 - 2 * t)

def slim(P):   # 갸름: 볼·턱 폭을 좁히고 턱끝을 살짝 내림
    Q = P.copy(); w = ramp(P[:, 2])
    Q[:, 0] *= 1 - 0.16 * w
    Q[:, 1] = np.where(P[:, 1] < 0, P[:, 1] * (1 - 0.06 * w), P[:, 1])
    cx = np.clip(1 - np.abs(P[:, 0]) / 0.3, 0, 1); cx = cx * cx * (3 - 2 * cx)   # 턱끝 쪽만, 옆으로 부드럽게 줄어들게(계단 없이)
    Q[:, 2] -= 0.04 * w * cx
    return Q
def square(P):  # 각진: 앞쪽 턱 모서리만 바깥으로(뒤통수·옆머리 자리는 그대로 → 가발 안 뚫음)
    Q = P.copy(); w = ramp(P[:, 2])
    front = np.clip((0.15 - P[:, 1]) / 0.35, 0, 1)            # 앞(-Y)일수록 1, 뒤쪽은 0
    ang = np.arctan2(P[:, 1], P[:, 0])
    boxy = 1 / np.maximum(np.abs(np.cos(ang)), np.abs(np.sin(ang))) ** 0.3
    f = 1 + (boxy - 1) * w * front * 0.9
    Q[:, 0] = P[:, 0] * f; Q[:, 1] = P[:, 1] * f
    under = np.clip((-0.25 - P[:, 2]) / 0.2, 0, 1)            # 턱 밑을 부드럽게 조금 평평하게(계단 없이)
    Q[:, 2] = P[:, 2] + 0.035 * under * front
    return Q

def full(P):   # 11/10 85번 넓은 얼굴(build_char.f_full 과 같은 식): 볼·턱을 옆으로, 턱 밑을 메워 어깨로 이어지게, 턱 밑을 살짝 아래로
    Q = P.copy(); x, y, z = P[:, 0], P[:, 1], P[:, 2]; w = ramp(z)
    sm = lambda t: np.clip(t, 0, 1) ** 2 * (3 - 2 * np.clip(t, 0, 1))
    deep = sm((-0.28 - z) / 0.22); front = np.clip((0.2 - y) / 0.5, 0, 1)
    Q[:, 0] = x * (1 + 0.20 * w + 0.20 * deep)
    Q[:, 1] = y * (1 + (0.06 * w + 0.12 * deep) * front)
    Q[:, 2] = z - 0.045 * deep * front * sm(1 - np.abs(x) / 0.35)
    return Q

head.shape_key_add(name="Basis")
shapes = {"round": base, "slim": slim(base), "square": square(base), "full": full(base)}
for nm in ("slim", "square", "full"):
    k = head.shape_key_add(name=nm); k.data.foreach_set("co", shapes[nm].reshape(-1))

rep = {"unchanged_above_z": Z_KEEP,
       "max_move_above_keep": {nm: float(np.abs(shapes[nm] - base)[base[:, 2] > Z_KEEP].max()) for nm in ("slim", "square", "full")}}

# 가발이 있으면 얼굴형마다 머리를 뚫는지 검사
hair = None
if WIG:
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=WIG)
    hair = [o for o in bpy.data.objects if o not in before and o.type == 'MESH'][0]; hair.name = "hair"
    H = np.array([hair.matrix_world @ v.co for v in hair.data.vertices])
    tris = [tuple(p.vertices) for p in me.polygons]
    for nm, P in shapes.items():
        bvh = BVHTree.FromPolygons([Vector(p) for p in P], tris)
        depth = 0.0
        for p in H:
            loc, n, i, d = bvh.find_nearest(Vector(p))
            if loc is not None and (Vector(p) - loc).dot(n) < 0: depth = max(depth, d)
        rep.setdefault("wig_penetration", {})[nm] = round(depth, 4)
    rep["wig_pass"] = all(v <= 0.005 for v in rep["wig_penetration"].values())

for o in bpy.context.selected_objects: o.select_set(False)
head.select_set(True); bpy.context.view_layer.objects.active = head
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "face_shapes.glb"), use_selection=True, export_format='GLB', export_morph=True)
json.dump(rep, open(os.path.join(OUT, "face_shapes_report.json"), "w"), indent=1)

# 그림: 얼굴 그림을 정면에서 비추듯 입혀서(앱과 같은 배치: 1024 그림 가운데 = 머리 중심, 512px = 반지름 0.5)
def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1]
skin = bpy.data.materials.new("skin"); skin.use_nodes = True; nt = skin.node_tree; bs = nt.nodes["Principled BSDF"]
bs.inputs["Roughness"].default_value = 0.55
if FACE:
    uv = me.uv_layers.new(name="face")
    for p in me.polygons:
        for li in p.loop_indices:
            v = base[me.loops[li].vertex_index]
            uv.data[li].uv = (0.5 + v[0], 0.5 + v[2]) if v[1] < 0.2 else (0.001, 0.001)
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = bpy.data.images.load(FACE); tex.image.alpha_mode = 'STRAIGHT'; tex.extension = 'CLIP'
    mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = 'RGBA'; mx.inputs[6].default_value = srgb("#F2C9AC")
    nt.links.new(tex.outputs["Alpha"], mx.inputs[0]); nt.links.new(tex.outputs["Color"], mx.inputs[7]); nt.links.new(mx.outputs[2], bs.inputs["Base Color"])
else:
    bs.inputs["Base Color"].default_value = srgb("#F2C9AC")
me.materials.clear(); me.materials.append(skin)
bpy.ops.object.shade_smooth()
if hair:
    hm = bpy.data.materials.new("hair"); hm.use_nodes = True; hm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = srgb("#4A3226")
    hair.data.materials.clear(); hair.data.materials.append(hm)
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 600; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[1].default_value = 0.5
for loc, e in (((-2, -4, 2), 260), ((3, -3, 0.5), 110)):
    l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = loc; sc.collection.objects.link(lo)
    lo.rotation_euler = (Vector((0, 0, 0)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.5
keys = head.data.shape_keys.key_blocks
for nm in ("round", "slim", "square", "full"):
    for k in ("slim", "square", "full"): keys[k].value = 1.0 if k == nm else 0.0
    for vn, yaw in (("front", 0), ("45", 35)):
        a = math.radians(yaw); cam.location = (6 * math.sin(a), -6 * math.cos(a), 0.05); cam.rotation_euler = (math.pi / 2, 0, a)
        sc.render.filepath = os.path.join(OUT, f"shape_{nm}_{vn}.png"); bpy.ops.render.render(write_still=True)
print("FACE_SHAPES", json.dumps(rep))
