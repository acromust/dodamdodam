# 도담도담 캐릭터 공정 5단계: Meshy가 뽑은 '마네킹 머리 + 가발' 모델을 기준 머리에 맞추고, 머리를 지워 가발만 남긴 뒤 검사한다.
# 실행: Blender -b --factory-startup -P fit_wig.py -- --wig WIG.glb --master MASTER_DIR --out OUT_DIR --name ponytail
# 결과: OUT/<name>.glb(기준 좌표의 가발), OUT/<name>_report.json(검사 숫자·통과 여부), OUT/<name>_*.png(기준 머리에 씌운 4방향)
# 기준 좌표: 머리 중심 원점, 머리 지름 1, 앞 -Y, 위 +Z (master_head.py와 같음)
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
WIG = arg("--wig"); MD = arg("--master"); OUT = arg("--out"); NAME = arg("--name", "wig")
CUT = float(arg("--cut", "0.03"))        # 기준 머리에서 이만큼 안에 있는 면은 마네킹으로 보고 지움
DECIMATE = int(arg("--decimate", "0"))   # 0이 아니면 이 면 수로 줄임(무료 Lite처럼 무거운 결과용)
BOOL = "--bool" in argv                   # 마네킹을 점 지우기 대신 '부풀린 기준 머리'로 매끈하게 도려냄(끝단이 닫힌 덩어리로 남음)
TUCK = float(arg("--tuck", "0"))       # 지운 테두리를 머리 속으로 접어 넣는 깊이(0이면 안 함)
os.makedirs(OUT, exist_ok=True)
# 통과 기준(56번 문서 11/08 밤 절)
LIM = {"fit": 0.02, "penetration_depth": 0.005, "face_cover_verts": 0, "faces": 2500}
# Meshy 결과는 가발과 마네킹이 한 겉면으로 붙어 나와서, 마네킹을 지우면 가발은 바깥 껍데기만 남고 머리에 딱 붙는다(뜰 수 없음).
# 그래서 '뜬 틈' 대신 '가발 두께'를 재서 보고만 한다.
BROW_Z = 0.17   # 앞머리가 내려와도 되는 가장 낮은 높이(눈썹 위)

bpy.ops.wm.read_factory_settings(use_empty=True)
def load(path, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    ms = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in ms: o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1: bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for x in [x for x in bpy.data.objects if x not in before and x.type != 'MESH']: bpy.data.objects.remove(x)
    o.name = name; return o
master = load(os.path.join(MD, "master_head.glb"), "master")
wig = load(WIG, "wig")
M = np.array([v.co[:] for v in master.data.vertices]); W = np.array([v.co[:] for v in wig.data.vertices])

# 1) 맞출 기준점: 기준 머리에서 머리카락에 안 덮이는 아래쪽 앞얼굴(볼·턱)
src = M[(M[:, 1] < -0.15) & (M[:, 2] < 0.05) & (M[:, 2] > -0.35)]
src = src[np.random.default_rng(0).choice(len(src), min(1500, len(src)), replace=False)]
kd = KDTree(len(W))
for i, p in enumerate(W): kd.insert(p, i)
kd.balance()
def nn(P):
    return np.array([kd.find(p)[0][:] for p in P])
def fit_st(A, B):  # A→B 배율·이동만(회전 없음): 머리는 공 모양이라 회전을 풀면 미끄러져 엉뚱하게 돌아감
    ma, mb = A.mean(0), B.mean(0); A0, B0 = A - ma, B - mb
    s = (A0 * B0).sum() / (A0 ** 2).sum()
    return s, mb - s * ma
def rotz(deg):
    a = math.radians(deg); c, s_ = math.cos(a), math.sin(a)
    return np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])
def icp(s0, t0, Rm, iters=40):
    S0 = (Rm @ src.T).T; s, t = s0, t0
    for _ in range(iters):
        X = s * S0 + t; Y = nn(X)
        d = np.linalg.norm(X - Y, axis=1); keep = d < np.percentile(d, 85)
        s, t = fit_st(S0[keep], Y[keep])
    X = s * S0 + t; d = np.linalg.norm(X - nn(X), axis=1)
    return s, Rm, t, float(np.mean(d) / s)   # 오차는 기준 좌표(머리 지름 1) 기준
# 시작값: 가발 모델 아래쪽 폭으로 배율 짐작. Meshy 결과는 똑바로 서서 앞을 보므로 회전은 좌우 ±10도만 살펴봄
wl = W[(W[:, 2] < np.percentile(W[:, 2], 45))]
guess = (wl[:, 0].max() - wl[:, 0].min()) / (M[:, 0].max() - M[:, 0].min())
cands = []
for yaw in (-10, -5, 0, 5, 10):
    for f in (0.75, 0.85, 1.0, 1.15):          # 옆으로 늘어진 머리(가르마펌 등)는 폭으로 짐작한 배율이 틀려서 범위를 넓게
        s0 = guess * f
        for dz in (0.0, 0.08, -0.08):           # 위아래 시작 위치도 몇 개
            ctr_w = np.array([np.median(W[:, 0]), np.median(wl[:, 1]), W[:, 2].min() + s0 * (0 - M[:, 2].min() + dz)])
            cands.append(icp(s0, ctr_w, rotz(yaw)))
s, Rm, t, fit_err = min(cands, key=lambda c: c[3])

# 2) 가발 모델을 기준 좌표로 옮김(역변환)
inv = np.linalg.inv(Rm) / s
Wm = ((W - t) @ inv.T)
for i, v in enumerate(wig.data.vertices): v.co = Vector(Wm[i])
wig.data.update()

# 3) 기준 머리 표면 가까이 있는 점 = 마네킹 머리 → 지움. 나머지가 가발
bmM = bmesh.new(); bmM.from_mesh(master.data); bvhM = BVHTree.FromBMesh(bmM)
def sdist(p):  # 기준 머리 바깥 +, 안 -
    loc, nrm, idx, d = bvhM.find_nearest(Vector(p))
    return d if (Vector(p) - loc).dot(nrm) >= 0 else -d
sd = np.array([sdist(p) for p in Wm])

if "--whole" in argv:
    # 11/09 사용자 지적: 머리카락만 떼어 씌우면 경계가 '빡빡이에 가발' 느낌 → Meshy 머리+머리카락을 통째로 머리로 쓰고,
    # 색만 나눔: 기준 머리 표면에서 떨어진 높이(sd)로 머리카락 0~1을 부드럽게(헤어라인이 Meshy가 조각한 모양 그대로 남음)
    h = np.clip((sd - 0.006) / 0.02, 0, 1); h = h * h * (3 - 2 * h)
    me = wig.data
    ca = me.color_attributes.new("hair", 'FLOAT_COLOR', 'POINT')
    for i, v in enumerate(ca.data): v.color = (h[i], h[i], h[i], 1)
    FACE = arg("--face")
    uv = me.uv_layers.new(name="face")
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = Wm[me.loops[li].vertex_index]
            uv.data[li].uv = (0.5 + v[0], 0.5 + v[2]) if v[1] < 0.2 else (0.001, 0.001)
    def srgb(hx):
        c = [int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1]
    m = bpy.data.materials.new("head"); m.use_nodes = True; nt = m.node_tree; bs = nt.nodes["Principled BSDF"]; bs.inputs["Roughness"].default_value = 0.6
    att = nt.nodes.new("ShaderNodeAttribute"); att.attribute_name = "hair"
    skin = nt.nodes.new("ShaderNodeMix"); skin.data_type = 'RGBA'; skin.inputs[6].default_value = srgb("#F2C9AC")
    if FACE:
        un = nt.nodes.new("ShaderNodeUVMap"); un.uv_map = "face"; tx = nt.nodes.new("ShaderNodeTexImage"); tx.extension = 'CLIP'
        tx.image = bpy.data.images.load(FACE); tx.image.alpha_mode = 'STRAIGHT'
        nt.links.new(un.outputs[0], tx.inputs[0]); nt.links.new(tx.outputs["Alpha"], skin.inputs[0]); nt.links.new(tx.outputs["Color"], skin.inputs[7])
    else:
        skin.inputs[0].default_value = 0
    hm = nt.nodes.new("ShaderNodeMix"); hm.data_type = 'RGBA'; hm.inputs[7].default_value = srgb("#4A3226")
    nt.links.new(att.outputs["Fac"], hm.inputs[0]); nt.links.new(skin.outputs[2], hm.inputs[6]); nt.links.new(hm.outputs[2], bs.inputs["Base Color"])
    me.materials.clear(); me.materials.append(m)
    master.hide_render = True
    for o in bpy.context.selected_objects: o.select_set(False)
    wig.select_set(True); bpy.context.view_layer.objects.active = wig; bpy.ops.object.shade_smooth()
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), use_selection=True, export_format='GLB')
    sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 32; sc.cycles.use_denoising = True
    sc.render.resolution_x = sc.render.resolution_y = 500; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    for loc, e in (((-2, -4, 2), 260), ((3, -3, 0.5), 110), ((0, 3, 3), 120)):
        l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = loc; sc.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0, 0, 0)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.5
    for vn, yaw in (("front", 0), ("45", 40), ("side", 90), ("back", 180)):
        a = math.radians(yaw); cam.location = (6 * math.sin(a), -6 * math.cos(a), 0.05); cam.rotation_euler = (math.pi / 2, 0, a)
        sc.render.filepath = os.path.join(OUT, f"{NAME}_{vn}.png"); bpy.ops.render.render(write_still=True)
    print("WHOLE", NAME, "verts", len(me.vertices), "faces", len(me.polygons), "fit_error", round(fit_err, 4)); sys.exit(0)

if "--sink" in argv:
    # 11/09: 자르지 말고 묻기. 기준 머리 표면 가까이(sd<CUT) 있는 점(마네킹 피부·앞머리 끝)을 부드럽게 머리 속 SINK 깊이로 가라앉힘.
    # 머리카락 덩어리는 그대로, 경계는 두피에 매끈하게 파묻힘(톱니·종이 끝 없음). 점은 하나도 안 지움.
    SINK = 0.02
    for i, v in enumerate(wig.data.vertices):
        face_low = v.co.y < 0.05 and v.co.z < -0.12          # 볼·턱 앞쪽은 가발이 올 자리가 아님(Meshy 턱이 튀어나온 것) → 무조건 묻음
        if sd[i] < CUT or face_low:
            w = 1.0 if face_low else np.clip((CUT - sd[i]) / CUT, 0, 1); w = w * w * (3 - 2 * w)
            loc, nrm, idx, d = bvhM.find_nearest(v.co)
            v.co = v.co - nrm * (w * (sd[i] + SINK))
    wig.data.update()
    zcut = M[:, 2].min() + 0.06                  # 기준 머리 아래(목) 쪽으로 튀어나온 Meshy 목 조각은 몸에 가려지지 않으니 지움
    bm0 = bmesh.new(); bm0.from_mesh(wig.data)
    bmesh.ops.delete(bm0, geom=[v for v in bm0.verts if v.co.z < zcut], context='VERTS'); bm0.to_mesh(wig.data); bm0.free(); wig.data.update()
bm = bmesh.new(); bm.from_mesh(wig.data); bm.verts.ensure_lookup_table()
if BOOL:
    # 11/09 사용자 지적: 점 단위로 지우면 앞머리 끝이 톱니·종이처럼 얇아짐 → 기준 머리를 CUT만큼 부풀린 닫힌 틀로 빼기(불리언)
    cm = master.data.copy(); cb = bmesh.new(); cb.from_mesh(cm)
    bmesh.ops.holes_fill(cb, edges=cb.edges[:], sides=0)
    bmesh.ops.recalc_face_normals(cb, faces=cb.faces[:]); cb.normal_update()
    for v in cb.verts: v.co = v.co + v.normal * CUT
    cb.to_mesh(cm); cb.free()
    cutter = bpy.data.objects.new("cutter", cm); bpy.context.scene.collection.objects.link(cutter)
    bm.to_mesh(wig.data); bm.free()
    md = wig.modifiers.new("cut", 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.object = cutter; md.solver = 'EXACT'
    bpy.context.view_layer.objects.active = wig
    for o in bpy.context.selected_objects: o.select_set(False)
    wig.select_set(True); bpy.ops.object.modifier_apply(modifier="cut"); bpy.data.objects.remove(cutter)
    bm = bmesh.new(); bm.from_mesh(wig.data)
elif "--sink" not in argv:
    head_v = [bm.verts[i] for i in range(len(sd)) if sd[i] < CUT]
    bmesh.ops.delete(bm, geom=head_v, context='VERTS')
# 지운 자리 테두리를 머리 속으로 접어 넣음(11/09 사용자 지적: 지우면 겉껍질만 남아 앞머리가 종이처럼 얇아 보임)
# 열린 테두리를 머리 중심 쪽으로 TUCK만큼 밀어 넣어 두께 있는 끝단을 만들고, 그 안쪽은 머리에 가려 안 보이게
if TUCK > 0:
    bnd = [e for e in bm.edges if e.is_boundary]
    ret = bmesh.ops.extrude_edge_only(bm, edges=bnd)
    for v in [x for x in ret["geom"] if isinstance(x, bmesh.types.BMVert)]:
        loc, nrm, idx, d = bvhM.find_nearest(v.co)
        v.co = loc - nrm * TUCK
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
# 떨어져 남은 부스러기 제거(가장 큰 덩어리들만)
bm.to_mesh(wig.data); bm.free(); wig.data.update()
bpy.context.view_layer.objects.active = wig
for o in bpy.context.selected_objects: o.select_set(False)
wig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.separate(type='LOOSE'); bpy.ops.object.mode_set(mode='OBJECT')
parts = [o for o in bpy.context.selected_objects]
big = max(len(o.data.vertices) for o in parts)

for o in parts:
    if len(o.data.vertices) < 0.03 * big: bpy.data.objects.remove(o)
parts = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith("wig")]
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
if len(parts) > 1: bpy.ops.object.join()
hair = bpy.context.view_layer.objects.active; hair.name = NAME
if DECIMATE and len(hair.data.polygons) > DECIMATE:
    dm = hair.modifiers.new('dec', 'DECIMATE'); dm.ratio = DECIMATE / len(hair.data.polygons)
    bpy.ops.object.modifier_apply(modifier='dec')
H = np.array([v.co[:] for v in hair.data.vertices])

# 4) 검사
sdH = np.array([sdist(p) for p in H])
vis = sdH > -0.5 * max(TUCK, 0.02 if "--sink" in argv else 0) if (TUCK > 0 or "--sink" in argv) else np.ones(len(sdH), bool)   # 접어 넣은 테두리(머리 속)는 검사에서 뺌
pen_depth = float(max(0.0, -sdH[vis].min()))
top = M[M[:, 2] > 0.15]
bmH = bmesh.new(); bmH.from_mesh(hair.data); bvhH = BVHTree.FromBMesh(bmH)
gaps = []
for p in top:   # 정수리 쪽 머리 표면에서 바깥으로 쏴서 가발 안쪽까지 거리
    n = Vector(p).normalized(); hit = bvhH.ray_cast(Vector(p) + n * 1e-4, n, 0.3)
    if hit[0]: gaps.append(hit[3])
thick_med = float(np.median(gaps)) if gaps else None
cover = int(((H[:, 1] < -0.2) & (np.abs(H[:, 0]) < 0.3) & (H[:, 2] < BROW_Z) & (sdH > 0.01)).sum())
faces = len(hair.data.polygons)
rep = {"name": NAME, "fit_error": fit_err, "penetration_depth": pen_depth, "hair_thickness_median": thick_med,
       "scalp_covered_ratio": len(gaps) / max(1, len(top)), "face_cover_verts": cover, "faces": faces,
       "scale_wig_to_master": float(1 / s)}
rep["pass"] = {"fit": fit_err <= LIM["fit"], "penetration": pen_depth <= LIM["penetration_depth"],
               "face_cover": cover <= LIM["face_cover_verts"], "faces": faces <= LIM["faces"]}
rep["all_pass"] = all(rep["pass"].values())
json.dump(rep, open(os.path.join(OUT, NAME + "_report.json"), "w"), ensure_ascii=False, indent=1)
for o in bpy.context.selected_objects: o.select_set(False)
hair.select_set(True); bpy.context.view_layer.objects.active = hair
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), use_selection=True, export_format='GLB')

# 5) 기준 머리에 씌워 4방향 그림
def mat(col):
    m = bpy.data.materials.new("m"); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = col; b.inputs["Roughness"].default_value = 0.6; return m
master.data.materials.clear(); master.data.materials.append(mat((0.85, 0.62, 0.48, 1)))
hair.data.materials.clear(); hair.data.materials.append(mat((0.22, 0.13, 0.08, 1)))
for o in (master, hair):
    bpy.context.view_layer.objects.active = o; o.select_set(True); bpy.ops.object.shade_smooth()
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 700; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[1].default_value = 0.5
l = bpy.data.lights.new("k", 'AREA'); l.energy = 150; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = (-2, -4, 2.5); sc.collection.objects.link(lo)
lo.rotation_euler = (Vector((0, 0, 0)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = 2.0
for nm, yaw in (("front", 0), ("45", 45), ("side", 90), ("back", 180)):
    a = math.radians(yaw); cam.location = (6 * math.sin(a), -6 * math.cos(a), 0.05); cam.rotation_euler = (math.pi / 2, 0, a)
    sc.render.filepath = os.path.join(OUT, f"{NAME}_{nm}.png"); bpy.ops.render.render(write_still=True)
print("FIT_WIG", json.dumps(rep, ensure_ascii=False))
