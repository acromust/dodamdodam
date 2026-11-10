# 도담도담 캐릭터 공정: 안경 3종(동그란·네모·반달)을 기준 머리에 맞춰 만든다.
# 실행: Blender -b --factory-startup -P glasses.py -- --master MASTER_DIR --out OUT_DIR
# 결과: OUT/glasses.glb(노드 glasses_round / glasses_square / glasses_half, 기준 좌표), OUT/glasses_report.json, OUT/glasses_*.png
# 위치는 얼굴 그림 배치(67·56번 문서)와 같다: 눈 중심 x=±0.21, z=-0.05(기준 좌표, 머리 지름 1, 앞 -Y)
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
MD = arg("--master"); OUT = arg("--out"); os.makedirs(OUT, exist_ok=True)
EYE_X, EYE_Z = 0.21, -0.05
GAP = 0.02            # 테와 얼굴 사이 최소 간격
WIRE = 0.011          # 테 굵기(반지름)
SHAPES = {"round": dict(w=0.25, h=0.25, r=0.125, top=True, wire=0.011),
          "square": dict(w=0.27, h=0.21, r=0.05, top=True, wire=0.016),   # 시안의 아빠처럼 굵은 검은 테
          "half": dict(w=0.26, h=0.26, r=0.13, top=False, wire=0.011)}    # 반달(돋보기): 동그라미 아래 절반 + 곧은 윗변

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(MD, "master_head.glb"))
head = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]
bm = bmesh.new(); bm.from_mesh(head.data); bvh = BVHTree.FromBMesh(bm)
def surf(x, z):
    hit = bvh.ray_cast(Vector((x, -5, z)), Vector((0, 1, 0)))
    return hit[0].y if hit[0] else -0.5

def outline(w, h, r, top, n=12):
    """테 모양(눈 중심 기준 x,z). 둥근 네모를 돌며 점을 찍는다. 반달은 위쪽 변을 곧게."""
    pts = []
    cx, cz = w / 2 - r, h / 2 - r
    corners = [(cx, cz, 0), (-cx, cz, 90), (-cx, -cz, 180), (cx, -cz, 270)]
    for (ox, oz, a0) in corners:
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((ox + r * math.cos(a), oz + r * math.sin(a)))
    if not top:  # 반달: 위 둥근 모서리 대신 곧은 윗변(눈 중심보다 조금 아래)
        pts = [(x, min(z, -0.015)) for x, z in pts]
    return pts

def tube(points3d, name, closed=True, wire=WIRE):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'; cu.bevel_depth = wire; cu.bevel_resolution = 3
    sp = cu.splines.new('POLY'); sp.points.add(len(points3d) - 1)
    for i, p in enumerate(points3d): sp.points[i].co = (*p, 1)
    sp.use_cyclic_u = closed
    o = bpy.data.objects.new(name, cu); bpy.context.scene.collection.objects.link(o)
    return o

report = {}
made = {}
for sname, sp in SHAPES.items():
    parts = []; worst = 9; inner = {}
    for sx in (-1, 1):
        ex = sx * EYE_X
        ol = outline(sp["w"], sp["h"], sp["r"], sp["top"])
        # 테 둘레의 얼굴 표면을 재서, 얼굴 곡면 기울기대로 비스듬히 + 어디도 파묻히지 않게 앞으로
        sy = [surf(ex + x, EYE_Z + z) for x, z in ol]
        xs = [x for x, z in ol]; mx = sum(xs) / len(xs); my = sum(sy) / len(sy)
        b = sum((x - mx) * (y - my) for x, y in zip(xs, sy)) / sum((x - mx) ** 2 for x in xs)
        a = min(y - b * x for x, y in zip(xs, sy)) - GAP
        pts = [(ex + x, a + b * x, EYE_Z + z) for x, z in ol]
        worst = min(worst, min(surf(px, pz) - py for px, py, pz in pts))
        parts.append(tube(pts, f"{sname}_rim{sx}", wire=sp["wire"]))
        out_i = max(range(len(pts)), key=lambda i: sx * pts[i][0]); in_i = min(range(len(pts)), key=lambda i: sx * pts[i][0])
        inner[sx] = pts[in_i]
        # 다리: 바깥 끝 → 귀 위
        p0 = Vector(pts[out_i]); p1 = Vector((sx * 0.43, 0.05, EYE_Z + 0.04))
        parts.append(tube([p0[:], ((p0 + p1) / 2 + Vector((sx * 0.02, 0, 0)))[:], p1[:]], f"{sname}_arm{sx}", closed=False))
    # 코다리
    bz = EYE_Z + (0.03 if sp["top"] else -0.015)   # 반달은 곧은 윗변 높이에 코다리
    q0, q1 = Vector(inner[-1]), Vector(inner[1]); yb = min(q0.y, q1.y, surf(0, bz) - GAP)
    parts.append(tube([(q0.x, yb, bz), (0, yb - 0.01, bz + 0.01), (q1.x, yb, bz)], f"{sname}_bridge", closed=False))
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in parts: o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.convert(target='MESH'); bpy.ops.object.join()
    g = bpy.context.view_layer.objects.active; g.name = f"glasses_{sname}"
    bpy.ops.object.shade_smooth()
    made[sname] = g
    report[sname] = {"min_clearance": round(worst, 4), "faces": len(g.data.polygons), "pass": worst >= GAP * 0.9}

metal = bpy.data.materials.new("glasses"); metal.use_nodes = True
b_ = metal.node_tree.nodes["Principled BSDF"]; b_.inputs["Base Color"].default_value = (0.08, 0.08, 0.09, 1); b_.inputs["Roughness"].default_value = 0.35
for g in made.values(): g.data.materials.append(metal)
for o in bpy.context.selected_objects: o.select_set(False)
for g in made.values(): g.select_set(True)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "glasses.glb"), use_selection=True, export_format='GLB')
json.dump(report, open(os.path.join(OUT, "glasses_report.json"), "w"), indent=1)

# 기준 머리에 씌워 정면·45도
skin = bpy.data.materials.new("skin"); skin.use_nodes = True
skin.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.86, 0.62, 0.47, 1)
head.data.materials.clear(); head.data.materials.append(skin)
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 600; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
l = bpy.data.lights.new("k", 'AREA'); l.energy = 160; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = (-2, -4, 2); sc.collection.objects.link(lo)
lo.rotation_euler = (Vector((0, 0, 0)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.4
for sname, g in made.items():
    for o in made.values(): o.hide_render = (o is not g)
    for nm, yaw in (("front", 0), ("45", 40)):
        a = math.radians(yaw); cam.location = (6 * math.sin(a), -6 * math.cos(a), 0); cam.rotation_euler = (math.pi / 2, 0, a)
        sc.render.filepath = os.path.join(OUT, f"glasses_{sname}_{nm}.png"); bpy.ops.render.render(write_still=True)
print("GLASSES", json.dumps(report))
