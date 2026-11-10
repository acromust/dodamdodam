# 도담도담 캐릭터 공정: 키 3(작음·보통·큼) × 체형 3(마름·보통·통통) 시안. 머리는 크기·모양 그대로(가발·안경이 그대로 맞게).
# 체형은 모양 키(모프): 목 아래만 가로로 넓히고 좁힘 → 앱에서도 모프로.
# 키는 앱에서 다리·몸통 뼈 길이로(머리 뼈가 따라 올라가니 가발도 따라감). 여기서는 같은 결과를 미리 보려고 목 아래를 세로로 늘이고 머리를 그만큼 올려서 보여 줌.
# 실행: Blender -b --factory-startup -P body_shapes.py -- --body BODY_PARTS.glb --out OUT_DIR
import bpy, math, os, sys, json
import numpy as np
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
BODY = arg("--body"); OUT = arg("--out"); os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=BODY)
o = [x for x in bpy.context.scene.objects if x.type == 'MESH'][0]; me = o.data
P = np.array([v.co[:] for v in me.vertices]); zmin = P[:, 2].min(); H = P[:, 2].max() - zmin
neck = float(json.load(open(arg("--cuts")))["neck_z"]) if arg("--cuts") else None
if neck is None:   # 목: 키 55~80%에서 가장 좁은 곳
    best = None
    for z in np.linspace(zmin + .55 * H, zmin + .8 * H, 60):
        sl = P[np.abs(P[:, 2] - z) < .006 * H]
        if len(sl) > 8:
            wdt = sl[:, 0].max() - sl[:, 0].min()
            if best is None or wdt < best[0]: best = (wdt, z)
    neck = best[1]
below = np.clip((neck - P[:, 2]) / (0.04 * H), 0, 1)          # 목 아래 1, 목 위 0(부드럽게)
belly = np.exp(-((P[:, 2] - (zmin + 0.42 * H)) / (0.12 * H)) ** 2)   # 배 높이
def build(k):   # k>0 통통, k<0 마름
    Q = P.copy(); f = 1 + k * below * (0.55 + 0.45 * belly)
    Q[:, 0] *= f; Q[:, 1] *= np.where(P[:, 1] < 0, 1 + k * below * (0.4 + 0.8 * belly), 1 + k * below * 0.4)
    return Q
# 키: 다리 길이만 바꾸고(발은 바닥), 그 위(몸통·팔·머리)는 모양 그대로 위아래로만 옮김 → 팔·손이 찌그러지지 않음
hip = zmin + 0.30 * H                                   # 밑단 높이 근처(가랑이 위)
sl = P[np.abs(P[:, 2] - (zmin + 0.18 * H)) < 0.01 * H]   # 허벅지 높이 단면 → 다리 폭
legw = np.abs(sl[:, 0]).max() * 1.15
is_leg = (P[:, 2] < hip) & (np.abs(P[:, 0]) < legw)
def height(Q, s):   # s = 다리 길이 배율
    R = Q.copy(); foot = zmin + 0.10 * H                # 신발(발 높이 아래)은 전부 그대로
    shift = (hip - foot) * (s - 1)
    z = Q[:, 2]
    leg_mid = is_leg & (z >= foot) & (z < hip)
    R[leg_mid, 2] = foot + (z[leg_mid] - foot) * s       # 정강이·허벅지만 늘이고 줄임
    R[(z >= foot) & ~leg_mid, 2] += shift                 # 그 위(몸통·팔·머리)는 통째로 이동
    return R
o.shape_key_add(name="Basis")
for nm, k in (("chubby", 0.22), ("slim", -0.14)):
    sk = o.shape_key_add(name=nm); sk.data.foreach_set("co", build(k).reshape(-1))
bpy.ops.object.shade_smooth()
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 20; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 240, 400; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[1].default_value = 0.55
for loc, e in (((-2, -4, 2), 160), ((3, -3, 0.5), 60)):
    l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = loc; sc.collection.objects.link(lo)
    lo.rotation_euler = (Vector((0, 0, 0)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = H * 1.45
cam.location = (0, -6, zmin + 0.62 * H); cam.rotation_euler = (math.pi / 2, 0, 0)
keys = me.shape_keys.key_blocks
for hn, hs in (("short", 0.72), ("mid", 1.0), ("tall", 1.4)):
    for bn, bk in (("slim", -0.14), ("mid", 0.0), ("chubby", 0.22)):
        Q = height(build(bk), hs)
        keys["Basis"].data.foreach_set("co", Q.reshape(-1)); keys["chubby"].value = 0; keys["slim"].value = 0
        me.update()
        sc.render.filepath = os.path.join(OUT, f"shape_{hn}_{bn}.png"); bpy.ops.render.render(write_still=True)
print("SHAPES done neck", round(float(neck), 3))
