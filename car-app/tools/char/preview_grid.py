# 도담도담 캐릭터 미리보기: 몸(부위 재질) + GPT 얼굴 그림 + 안경 + 가발을 키×체형 3×3으로 조립해 렌더.
# 실행: Blender -b --factory-startup -P preview_grid.py -- --body BODY_PARTS.glb --master MASTER_DIR --glasses GLASSES.glb
#        --faces kid.png,dad.png,grandma.png [--wig WIG.glb] --out OUT_DIR
import bpy, json, math, os, sys
import numpy as np
from mathutils import Vector, Matrix
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
OUT = arg("--out"); os.makedirs(OUT, exist_ok=True)
mj = json.load(open(os.path.join(arg("--master"), "master_head.json")))
C = Vector(mj["center_body"]); R = mj["radius_body"]; NECK = mj["neck_z_body"]
M2B = Matrix.Translation(C) @ Matrix.Scale(R / 0.5, 4)        # 기준 좌표 → 몸 좌표
def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1]
bpy.ops.wm.read_factory_settings(use_empty=True)
def load(path):
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
body = load(arg("--body"))[0]; me = body.data
P0 = np.array([v.co[:] for v in me.vertices]); zmin = P0[:, 2].min(); H = P0[:, 2].max() - zmin
# 얼굴: 머리 앞쪽에 정면으로 비추듯 UV(1024 그림 가운데 = 머리 중심, 512px = 반지름)
uv = me.uv_layers.new(name="face")
for p in me.polygons:
    for li in p.loop_indices:
        v = P0[me.loops[li].vertex_index]
        uv.data[li].uv = ((0.5 + (v[0] - C.x) / (2 * R), 0.5 + (v[2] - C.z) / (2 * R)) if (v[2] > NECK and v[1] < C.y + 0.4 * R) else (0.001, 0.001))
skin = [m for m in me.materials if m.name.startswith("skin")][0]; shirt = [m for m in me.materials if m.name.startswith("shirt")][0]
nt = skin.node_tree; bs = nt.nodes["Principled BSDF"]
uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "face"
tex = nt.nodes.new("ShaderNodeTexImage"); tex.extension = 'CLIP'
mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'
nt.links.new(uvn.outputs[0], tex.inputs[0]); nt.links.new(tex.outputs["Alpha"], mix.inputs[0])
nt.links.new(tex.outputs["Color"], mix.inputs[7]); nt.links.new(mix.outputs[2], bs.inputs["Base Color"])
bpy.ops.object.select_all(action='DESELECT'); body.select_set(True); bpy.context.view_layer.objects.active = body; bpy.ops.object.shade_smooth()
glasses = {}
for g in load(arg("--glasses")):
    g.matrix_world = M2B @ g.matrix_world; glasses[g.name.replace("glasses_", "")] = g; g.hide_render = True
gbase = {k: g.matrix_world.copy() for k, g in glasses.items()}
wig = None
if arg("--wig"):
    wig = load(arg("--wig"))[0]; wig.matrix_world = M2B @ wig.matrix_world; wbase = wig.matrix_world.copy()
    hm = bpy.data.materials.new("hair"); hm.use_nodes = True; hm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.7
    wig.data.materials.clear(); wig.data.materials.append(hm)
    bpy.context.view_layer.objects.active = wig; wig.select_set(True); bpy.ops.object.shade_smooth()
# 체형·키 (body_shapes.py와 같은 식)
below = np.clip((NECK - P0[:, 2]) / (0.04 * H), 0, 1); belly = np.exp(-((P0[:, 2] - (zmin + 0.42 * H)) / (0.12 * H)) ** 2)
def build(k):
    Q = P0.copy(); f = 1 + k * below * (0.55 + 0.45 * belly)
    Q[:, 0] *= f; Q[:, 1] *= np.where(P0[:, 1] < 0, 1 + k * below * (0.4 + 0.8 * belly), 1 + k * below * 0.4); return Q
hip = zmin + 0.30 * H; sl = P0[np.abs(P0[:, 2] - (zmin + 0.18 * H)) < 0.01 * H]; legw = np.abs(sl[:, 0]).max() * 1.15
is_leg = (P0[:, 2] < hip) & (np.abs(P0[:, 0]) < legw); foot = zmin + 0.10 * H
def height(Q, s):
    Rr = Q.copy(); z = P0[:, 2]; shift = (hip - foot) * (s - 1)
    lm = is_leg & (z >= foot) & (z < hip); Rr[lm, 2] = foot + (z[lm] - foot) * s
    Rr[(z >= foot) & ~lm, 2] += shift; return Rr, shift
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 24; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 300, 470; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
for loc, e in (((-2, -4, 2), 170), ((3, -3, 0.5), 70)):
    l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = loc; sc.collection.objects.link(lo)
    lo.rotation_euler = (Vector((0, 0, 0)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = H * 1.55
a = math.radians(15); cam.location = (6 * math.sin(a), -6 * math.cos(a), zmin + 0.66 * H); cam.rotation_euler = (math.pi / 2, 0, a)
faces = arg("--faces").split(",")
# 열(체형)마다 다른 사람: 얼굴·피부·옷·머리색·안경
PEOPLE = [dict(face=faces[0], skin="#F8DCC8", shirt="#F5C842", hair="#4A3226", glasses=None, k=-0.14),
          dict(face=faces[1], skin="#F2C9AC", shirt="#5AA9F0", hair="#2B2522", glasses="square", k=0.0),
          dict(face=faces[2], skin="#C98E64", shirt="#F49A4A", hair="#A9A6A2", glasses="round", k=0.22)]
for hn, hs in (("short", 0.72), ("mid", 1.0), ("tall", 1.4)):
    for ci, pp in enumerate(PEOPLE):
        Q, shift = height(build(pp["k"]), hs)
        for i, v in enumerate(me.vertices): v.co = Q[i]
        me.update()
        tex.image = bpy.data.images.load(pp["face"], check_existing=True); tex.image.alpha_mode = 'STRAIGHT'
        mix.inputs[6].default_value = srgb(pp["skin"]); shirt.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = srgb(pp["shirt"])
        up = Matrix.Translation((0, 0, shift))
        for k, g in glasses.items(): g.hide_render = (k != pp["glasses"]); g.matrix_world = up @ gbase[k]
        if wig:
            wig.matrix_world = up @ wbase; wig.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = srgb(pp["hair"])
        sc.render.filepath = os.path.join(OUT, f"p_{hn}_{ci}.png"); bpy.ops.render.render(write_still=True)
print("GRID done")
