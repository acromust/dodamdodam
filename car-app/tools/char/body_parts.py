# 도담도담 캐릭터 공정: Meshy가 칠한 몸(텍스처)에서 면마다 부위를 읽어 재질을 나눈다(피부·윗옷·바지·신발).
# 앱은 부위별 재질 색만 바꾸면 된다(피부 5·대표색 8). 결과 GLB는 텍스처 없이 재질 4개 + UV 유지.
# 실행: Blender -b --factory-startup -P body_parts.py -- --body BODY_TEXTURED.glb --out OUT_DIR [--render]
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
BODY = arg("--body"); OUT = arg("--out"); RENDER = "--render" in argv
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=BODY)
o = [x for x in bpy.context.scene.objects if x.type == 'MESH'][0]; me = o.data
img = None
for m in me.materials:
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image: img = n.image
W, H = img.size; px = np.array(img.pixels[:]).reshape(H, W, 4)[:, :, :3]
uv = me.uv_layers.active.data
zs = np.array([(o.matrix_world @ v.co).z for v in me.vertices]); zmin, zmax = zs.min(), zs.max(); Ht = zmax - zmin
def classify(rgb, zc):
    r, g, b = rgb; mx, mn = max(rgb), min(rgb); sat = (mx - mn) / (mx + 1e-6)
    if b > r + 0.15 and sat > 0.35: return 1                 # 윗옷(파랑)
    if r > b + 0.15 and sat > 0.2: return 0                  # 피부(주황빛)
    return 3 if zc < zmin + 0.11 * Ht else 2                 # 회색: 발 높이면 신발, 아니면 바지
labels = []
for p in me.polygons:
    us = np.mean([uv[li].uv[:] for li in p.loop_indices], axis=0)
    x = min(W - 1, max(0, int(us[0] * W))); y = min(H - 1, max(0, int(us[1] * H)))
    rgb = px[y, x]; zc = (o.matrix_world @ p.center).z
    labels.append(classify(rgb, zc))
labels = np.array(labels)
# 외톨이 면 정리: 이웃 다수결 2번
bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
for _ in range(2):
    new = labels.copy()
    for f in bm.faces:
        nb = [labels[l.link_face.index] for e in f.edges for l in e.link_loops if l.face is not f] if False else \
             [labels[g.index] for e in f.edges for g in e.link_faces if g.index != f.index]
        if nb:
            vals, cnt = np.unique(nb, return_counts=True)
            if cnt.max() >= 2 and vals[cnt.argmax()] != labels[f.index]: new[f.index] = vals[cnt.argmax()]
    labels = new
# 경계 높이를 텍스처 다수결에서 뽑고, 그 높이로 몸을 곧게 잘라 다시 나눔(톱니·턱 물듦 방지)
cz_f = np.array([(o.matrix_world @ p.center).z for p in me.polygons]); cx_f = np.array([(o.matrix_world @ p.center).x for p in me.polygons])
mid = np.abs(cx_f) < 0.12 * Ht
neck_z = float(np.percentile(cz_f[(labels == 1) & mid], 97))     # 윗옷이 끝나는 목 높이
# 윗옷 밑단: 색이 아니라 모양으로 — 윗옷이 바지보다 도톰하게 끝나며 아래를 향하는 면들의 윗선(11/09 사용자 지적: 색 기준은 바지 위 띠까지 먹음)
nz_f = np.array([p.normal.z for p in me.polygons])
ring = (np.abs(cx_f) < 0.15 * Ht) & (nz_f < -0.45) & (cz_f > zmin + 0.18 * Ht) & (cz_f < zmin + 0.42 * Ht)
hem_z = float(np.percentile(cz_f[ring], 85)) if ring.sum() > 20 else float(np.percentile(cz_f[(labels == 1) & mid], 3))
ank_z = float(np.percentile(cz_f[labels == 3], 95))              # 신발 윗선
bm.free(); bm = bmesh.new(); bm.from_mesh(me)
for zc in (neck_z, hem_z, ank_z):
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, zc), plane_no=(0, 0, 1))
bm.to_mesh(me); bm.free(); me.update()
uv = me.uv_layers.active.data
labels = []
for p in me.polygons:
    zc = (o.matrix_world @ p.center).z
    if zc >= neck_z: labels.append(0); continue              # 목 위: 피부
    if zc < ank_z: labels.append(3); continue                 # 발목 아래: 신발
    if zc < hem_z: labels.append(2); continue                 # 밑단~발목: 바지
    us = np.mean([uv[li].uv[:] for li in p.loop_indices], axis=0)
    x = min(W - 1, max(0, int(us[0] * W))); y = min(H - 1, max(0, int(us[1] * H)))
    labels.append(0 if classify(px[y, x], zc) == 0 else 1)  # 몸통·팔: 손만 피부, 나머지 윗옷
labels = np.array(labels)
bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
for _ in range(2):   # 팔 위 외톨이 면만 다수결로 정리
    new = labels.copy()
    for f in bm.faces:
        nb = [labels[g.index] for e in f.edges for g in e.link_faces if g.index != f.index]
        if nb:
            vals, cnt = np.unique(nb, return_counts=True)
            if cnt.max() >= 2 and vals[cnt.argmax()] != labels[f.index]: new[f.index] = vals[cnt.argmax()]
    labels = new
print("CUTS", round(neck_z, 3), round(hem_z, 3), round(ank_z, 3))
NAMES = ["skin", "shirt", "pants", "shoes"]
def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1]
DEF = {"skin": "#F2C9AC", "shirt": "#5AA9F0", "pants": "#6A6C70", "shoes": "#3F4145"}
me.materials.clear()
mats = {}
for nm in NAMES:
    m = bpy.data.materials.new(nm); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(DEF[nm]); b.inputs["Roughness"].default_value = 0.6 if nm == "skin" else 0.8
    me.materials.append(m); mats[nm] = m
for i, p in enumerate(me.polygons): p.material_index = int(labels[i])
counts = {NAMES[k]: int((labels == k).sum()) for k in range(4)}
for x in [x for x in bpy.data.images]: pass
for o2 in bpy.context.selected_objects: o2.select_set(False)
o.select_set(True); bpy.context.view_layer.objects.active = o; bpy.ops.object.shade_smooth()
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "body_parts.glb"), use_selection=True, export_format='GLB')
json.dump({"faces_per_part": counts}, open(os.path.join(OUT, "body_parts.json"), "w"), indent=1)
print("PARTS", json.dumps(counts))
if RENDER:
    sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 24; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 360, 480; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[1].default_value = 0.55
    for loc, e in (((-2, -4, 2), 160), ((3, -3, 0.5), 60)):
        l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = loc; sc.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0, 0, 0)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = Ht * 1.12; cz = (zmin + zmax) / 2
    a = math.radians(20); cam.location = (6 * math.sin(a), -6 * math.cos(a), cz); cam.rotation_euler = (math.pi / 2, 0, a)
    VARS = [("A", "#F2C9AC", "#5AA9F0"), ("B", "#C98E64", "#F08AAE"), ("C", "#8E5B3E", "#7CC36B"), ("D", "#F8DCC8", "#3F5BA9")]
    for nm, sk, sh in VARS:
        mats["skin"].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = srgb(sk)
        mats["shirt"].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = srgb(sh)
        sc.render.filepath = os.path.join(OUT, f"recolor_{nm}.png"); bpy.ops.render.render(write_still=True)
