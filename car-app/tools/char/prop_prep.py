# 도담도담 소품 정리: Meshy 텍스처 모델(손 소품·광장 소품)을 앱에 쓰기 좋게 다듬는다.
#  - 이음매 점 붙이기 → 면 수 줄이기(UV·텍스처 유지) → 바닥 가운데를 원점으로 → 가장 긴 변을 --size로 → 3방향 렌더
# 실행: Blender -b --factory-startup -P prop_prep.py -- --in TEX.glb --out OUT --name NAME [--faces 3000] [--size 1.0]
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
IN, OUT, NAME = arg("--in"), arg("--out"), arg("--name")
NF, SIZE = int(arg("--faces", "3000")), float(arg("--size", "1.0"))
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=IN)
ms = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
for o in bpy.context.selected_objects: o.select_set(False)
for o in ms: o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
if len(ms) > 1: bpy.ops.object.join()
o = bpy.context.view_layer.objects.active; bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for x in [x for x in bpy.data.objects if x not in before and x.type != 'MESH']: bpy.data.objects.remove(x)
me = o.data
if arg("--rotz"):   # 위축 기준 돌리기(도). Meshy가 앞뒤를 바꿔 만든 경우(나무2: 새 가지가 앞에서 왼쪽에 생김) 180으로 앞을 맞춤
    from mathutils import Matrix
    me.transform(Matrix.Rotation(math.radians(float(arg("--rotz"))), 4, 'Z')); me.update()
# ── 아래 옵션들은 고를 때만 켜짐(기본 동작 그대로). --nonormal·--captop·--rotz 설명은 각 자리에 ──
#  --dropsmall F : 전체 면의 F 비율보다 작은 떨어진 조각(떠 있는 찌꺼기) 지우기. 연결은 위치가 같은 점끼리 본다(UV 이음매로 갈라진 건 한 덩어리)
#  --tex N       : 텍스처 전부 N×N으로 줄이기(Pleos 앱 RAM 400MB 예산. 2048 세 장이면 소품 하나에 밉맵 포함 약 64MB)
#  --recolor R   : 바탕색 텍스처 색 맞추기(문서 64-13 팔레트). R = "조건+조건>#HEX;..." 조건은 Lab LCh 범위 h(색상각)·C(채도)·L(밝기), 예 h100-160+C15-999, 전체는 all
#               고른 텍셀의 (면적 가중) 평균만 목표색으로 옮김 → 무늬·명암 차이는 그대로. 경계는 범위 밖 h±8·C±5·L±5에서 서서히 줄어 이음이 안 생김
def _parts(me):   # 떨어진 조각 = 같은 위치 점을 공유하는 면끼리 묶은 덩어리. 면별 조각 번호 반환
    P = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", P); P = P.reshape(-1, 3)
    _, key = np.unique(np.round(P / 1e-5).astype(np.int64), axis=0, return_inverse=True); key = key.ravel()
    par = list(range(key.max() + 1))
    def fd(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", lv); lk = key[lv]
    ls = np.empty(len(me.polygons), np.int64); me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(len(me.polygons), np.int64); me.polygons.foreach_get("loop_total", lt)
    for s, t in zip(ls, lt):
        r = fd(lk[s])
        for k in lk[s + 1:s + t]:
            q = fd(k)
            if q != r: par[q] = r
    return np.array([fd(lk[s]) for s in ls])
if arg("--dropsmall"):
    fp = _parts(me); ids, cnt = np.unique(fp, return_counts=True); small = set(ids[cnt < float(arg("--dropsmall")) * len(fp)].tolist())
    if small:
        bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[i] for i in range(len(fp)) if fp[i] in small], context='FACES')
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS'); bm.to_mesh(me); bm.free(); me.update()
    print("DROPSMALL", len(small), "parts")
import tempfile
TMP = tempfile.mkdtemp()
def _swap(img, ext):   # 고친 그림을 파일로 저장→다시 불러 노드에 끼움(내보내기가 그 파일을 그대로 씀). sRGB 그림은 저장값이 곧 sRGB
    fn = os.path.join(TMP, img.name.replace("/", "_") + ext); img.file_format = 'PNG' if ext == '.png' else 'JPEG'
    try: img.save(filepath=fn, quality=90)
    except TypeError: img.filepath_raw = fn; img.save()
    ni = bpy.data.images.load(fn); ni.colorspace_settings.name = img.colorspace_settings.name
    for m in me.materials:
        for nd in (m.node_tree.nodes if m and m.use_nodes else []):
            if nd.type == 'TEX_IMAGE' and nd.image == img: nd.image = ni
    return ni
def _bc_images():   # 바탕색(Base Color)에 꽂힌 그림
    out = []
    for m in me.materials:
        for nd in (m.node_tree.nodes if m and m.use_nodes else []):
            if nd.type == 'BSDF_PRINCIPLED':
                for ln in nd.inputs['Base Color'].links:
                    if ln.from_node.type == 'TEX_IMAGE' and ln.from_node.image not in out: out.append(ln.from_node.image)
    return out
if '--nonormal' in argv:   # 노멀맵 빼기: 고해상 모양에 맞춰 구운 거라 면을 많이 줄이면 얼룩진 삼각형으로 비침(화분 벽). 그림 한 장 덜어 메모리도 줄어듦
    for m in me.materials:
        for nd in (m.node_tree.nodes if m and m.use_nodes else []):
            if nd.type == 'BSDF_PRINCIPLED':
                for ln in list(nd.inputs['Normal'].links):
                    nm = ln.from_node; up = [l.from_node for l in nm.inputs['Color'].links] if 'Color' in nm.inputs else []
                    for x in [nm] + up: m.node_tree.nodes.remove(x)
if arg("--tex"):
    N = int(arg("--tex"))
    for img in [i for i in bpy.data.images if i.size[0] > N]:
        img.scale(N, N); _swap(img, '.jpg')
def _lab(c):   # sRGB(0~1) → CIE Lab(D65)
    l = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    x = l @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(x > 0.008856, np.cbrt(x), 7.787 * x + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)
def _srgb(L):   # Lab → sRGB(0~1)
    fy = (L[:, 0] + 16) / 116; f = np.stack([fy + L[:, 1] / 500, fy, fy - L[:, 2] / 200], 1)
    x = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    l = x @ np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]]).T
    l = np.clip(l, 0, 1); return np.where(l <= 0.0031308, 12.92 * l, 1.055 * l ** (1 / 2.4) - 0.055)
def _w(L, sel):   # 조건 범위 안 1, 밖으로 서서히 0
    w = np.ones(len(L))
    if sel == "all": return w
    C = np.hypot(L[:, 1], L[:, 2]); H = np.degrees(np.arctan2(L[:, 2], L[:, 1])) % 360
    for cnd in sel.split("+"):
        k, (a, b) = cnd[0], map(float, cnd[1:].split("-")); v, fe = {"h": (H, 8.0), "C": (C, 5.0), "L": (L[:, 0], 5.0)}[k]
        d = np.maximum(a - v, v - b) if k != "h" else np.minimum.reduce([np.maximum(a - x, x - b) for x in (v, v - 360, v + 360)])
        w *= np.clip(1 - d / fe, 0, 1) ** 2 * (3 - 2 * np.clip(1 - d / fe, 0, 1))
    return w
recolor_rep = []
if arg("--recolor"):
    uv = me.uv_layers.active.data; U = np.empty(len(uv) * 2); uv.foreach_get("uv", U); U = U.reshape(-1, 2)
    ar = np.empty(len(me.polygons)); me.polygons.foreach_get("area", ar)
    lt = np.empty(len(me.polygons), np.int64); me.polygons.foreach_get("loop_total", lt); la = np.repeat(ar / lt, lt)   # 점마다 면적 몫
    for img in _bc_images():
        W, H = img.size; px = np.empty(W * H * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(-1, 4)
        Lx = _lab(px[:, :3].astype(np.float64)); out = Lx.copy()
        si = (np.floor(U[:, 1] % 1 * H).astype(int).clip(0, H - 1)) * W + np.floor(U[:, 0] % 1 * W).astype(int).clip(0, W - 1)   # UV가 닿는 텍셀(실제로 보이는 색)
        for rule in arg("--recolor").split(";"):
            sel, hx = rule.split(">"); T = _lab(np.array([[int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]]))[0]
            ws = _w(Lx[si], sel) * la; mean = (Lx[si] * ws[:, None]).sum(0) / max(ws.sum(), 1e-12)
            out += _w(Lx, sel)[:, None] * (T - mean)
            hexo = lambda L: '#%02X%02X%02X' % tuple((_srgb(L[None])[0] * 255).round().astype(int))
            recolor_rep.append({"sel": sel, "to": hx, "share": round(float(ws.sum() / la.sum()), 3), "before": hexo(mean), "dE_before": round(float(np.linalg.norm(mean - T)), 1)})
        px[:, :3] = _srgb(out); img.pixels.foreach_set(px.ravel()); img.update(); _swap(img, '.png')
if '--noweld' not in argv:   # 이음매 붙이기는 조각나는 모델만. 붙이면 면 줄이기가 텍스처 이음매를 넘어가 무늬 경계가 울퉁불퉁해짐(폰 화면 테두리)
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5); bm.to_mesh(me); bm.free(); me.update()
if arg("--captop"):   # 윗면 덮기: 그림 위가 잘려서 Meshy가 위를 오목한 컵으로 만든 것(가로등 유리공·눈사람 머리)에 둥근 뚜껑을 새로 얹음
    # 맨 위 테두리 원(위 1% 점들)을 덮는 구면 뚜껑. 구 반지름 = 위에서 F(높이 비율) 안의 가장 넓은 반지름. 뚜껑 UV는 맨 꼭대기 점 색 한 점(흰 유리·흰 눈)
    F = float(arg("--captop")); P = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", P); P = P.reshape(-1, 3)
    z = P[:, 2]; Hh = z.max() - z.min(); zt = z.max(); ring = P[z > zt - 0.01 * Hh]; cxy = ring[:, :2].mean(0)
    r = np.linalg.norm(P[:, :2] - cxy, axis=1); rr = np.linalg.norm(ring[:, :2] - cxy, axis=1).max(); R = max(r[z > zt - F * Hh].max(), rr * 1.0001)
    bm = bmesh.new(); bm.from_mesh(me); ul = bm.loops.layers.uv.active; bm.verts.ensure_lookup_table()
    uv0 = bm.verts[int(z.argmax())].link_loops[0][ul].uv.copy()
    rr *= 0.985; zc = lambda q: zt - 0.015 * Hh + math.sqrt(R * R - q * q) - math.sqrt(R * R - rr * rr)   # 테두리 턱 안쪽에 살짝 묻어 틈·줄이 덜 보이게
    NS, NR = 48, 6; top = bm.verts.new((cxy[0], cxy[1], zc(0)))
    rings = [[bm.verts.new((cxy[0] + q * math.cos(2 * math.pi * k / NS), cxy[1] + q * math.sin(2 * math.pi * k / NS), zc(q))) for k in range(NS)] for q in [rr * (j + 1) / NR for j in range(NR)]]
    fs = [bm.faces.new((top, rings[0][k], rings[0][(k + 1) % NS])) for k in range(NS)]
    fs += [bm.faces.new((a[k], b[k], b[(k + 1) % NS], a[(k + 1) % NS])) for a, b in zip(rings, rings[1:]) for k in range(NS)]
    for f in fs:
        f.material_index = 0
        for lp in f.loops: lp[ul].uv = uv0
    bm.normal_update(); bm.to_mesh(me); bm.free(); me.update()
    print("CAPTOP rim r %.3f R %.3f dome h %.3f" % (rr, R, zc(0) - zt))
f0 = len(me.polygons)
SRCN = '--srcnormals' in argv and f0 > NF   # 11/09 면을 많이 줄이면 매끈한 원기둥 옆면이 길쭉한 삼각형이 돼 세로 줄무늬 음영(충전 기둥) → 원본 고해상 모양의 면 방향을 옮겨 붙임
REBAKE = '--rebake' in argv and f0 > NF   # 11/09 면을 많이 줄이면 UV가 조각 밖 검은 바탕을 집어 세로 검은 줄(충전 기둥) → 새 UV(여백 있게)에 원본 고해상 색을 다시 구움(새 bird_rig.py 방식)
if REBAKE:
    hsrc = o.copy(); hsrc.data = me.copy(); bpy.context.scene.collection.objects.link(hsrc)
if SRCN:
    src = o.copy(); src.data = me.copy(); bpy.context.scene.collection.objects.link(src)
if f0 > NF:
    dm = o.modifiers.new("dec", 'DECIMATE'); dm.ratio = NF / f0; bpy.ops.object.modifier_apply(modifier="dec")
if SRCN:
    for x in bpy.context.selected_objects: x.select_set(False)
    o.select_set(True); bpy.context.view_layer.objects.active = o
    dt = o.modifiers.new("nt", 'DATA_TRANSFER'); dt.object = src; dt.use_loop_data = True; dt.data_types_loops = {'CUSTOM_NORMAL'}; dt.loop_mapping = 'POLYINTERP_NEAREST'
    bpy.ops.object.modifier_apply(modifier="nt"); bpy.data.objects.remove(src); me = o.data
if '--wnormal' in argv:   # 11/09 면 줄인 뒤 길쭉한 삼각형 음영 줄무늬 → 면 넓이 가중 법선으로 고르게(원기둥 옆면)
    for x in bpy.context.selected_objects: x.select_set(False)
    o.select_set(True); bpy.context.view_layer.objects.active = o; bpy.ops.object.shade_smooth()
    wn = o.modifiers.new("wn", 'WEIGHTED_NORMAL'); wn.mode = 'FACE_AREA'; wn.weight = 100; wn.keep_sharp = False
    bpy.ops.object.modifier_apply(modifier="wn"); me = o.data; SRCN = True   # 아래 shade_smooth가 법선을 지우지 않게
if REBAKE:
    Pb = np.array([v.co[:] for v in me.vertices]); diag = float((Pb.max(0) - Pb.min(0)).max()); TB = int(arg("--tex", "1024"))
    for x in bpy.context.selected_objects: x.select_set(False)
    o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.02); bpy.ops.object.mode_set(mode='OBJECT')
    bimg = bpy.data.images.new(NAME + "_col", TB, TB, alpha=False)
    bm_ = bpy.data.materials.new(NAME); bm_.use_nodes = True; bnt = bm_.node_tree
    bb_ = [n for n in bnt.nodes if n.type == 'BSDF_PRINCIPLED'][0]; bb_.inputs['Roughness'].default_value = .8; bb_.inputs['Metallic'].default_value = 0
    btn = bnt.nodes.new('ShaderNodeTexImage'); btn.image = bimg; bnt.nodes.active = btn
    me.materials.clear(); me.materials.append(bm_)
    sc0 = bpy.context.scene; sc0.render.engine = 'CYCLES'; sc0.cycles.samples = 4; sc0.cycles.device = 'CPU'
    hsrc.select_set(True); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, use_selected_to_active=True, cage_extrusion=.012 * diag, max_ray_distance=.05 * diag, margin=8)
    bnt.links.new(btn.outputs['Color'], bb_.inputs['Base Color'])
    bfn = os.path.join(OUT, NAME + "_col.png"); bimg.file_format = 'PNG'; bimg.filepath_raw = bfn; bimg.save(); bimg.source = 'FILE'; bimg.reload()
    hm_ = hsrc.data; bpy.data.objects.remove(hsrc); bpy.data.meshes.remove(hm_)
    for x in bpy.context.selected_objects: x.select_set(False)
    o.select_set(True); bpy.context.view_layer.objects.active = o; me = o.data
P = np.array([v.co[:] for v in me.vertices]); lo, hi = P.min(0), P.max(0)
s = SIZE / float((hi - lo).max()); c = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
for v in me.vertices: v.co = Vector(((np.array(v.co[:]) - c) * s).tolist())
me.update()
if not SRCN: bpy.ops.object.shade_smooth()   # 옮겨 붙인 면 방향은 지우지 않음
o.name = NAME
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), use_selection=True, export_format='GLB')
P = np.array([v.co[:] for v in me.vertices]); dims = (P.max(0) - P.min(0)).round(3).tolist()
rep = {"name": NAME, "faces_meshy": f0, "faces": len(me.polygons), "dims": dims}
if arg("--dropsmall") or arg("--tex") or arg("--recolor") or arg("--captop") or arg("--rotz") or '--nonormal' in argv:   # 새 옵션 쓸 때만 보고에 덧붙임
    fp = _parts(me); rep["parts"] = sorted(np.unique(fp, return_counts=True)[1].tolist(), reverse=True)[:8]
    rep["tex"] = sorted({f"{i.size[0]}x{i.size[1]}" for i in bpy.data.images if i.users and i.size[0]})
    if recolor_rep: rep["recolor"] = recolor_rep
json.dump(rep, open(os.path.join(OUT, NAME + "_report.json"), "w"), indent=1)
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 480; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[1].default_value = 0.7
for loc, e in (((-2, -4, 3), 260), ((3, -3, 1.5), 110), ((0, 3, 3), 120)):
    l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo_ = bpy.data.objects.new("k", l); lo_.location = loc; sc.collection.objects.link(lo_)
    lo_.rotation_euler = (Vector((0, 0, .4)) - lo_.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.type = 'ORTHO'; cam.data.ortho_scale = max(dims) * 1.3
cz = dims[2] / 2
for vn, yaw, el in (("front", 0, 0), ("side", 90, 0), ("back", 180, 0), ("top45", 35, 30)):
    a = math.radians(yaw); e = math.radians(el); d = 6
    cam.location = (d * math.sin(a) * math.cos(e), -d * math.cos(a) * math.cos(e), cz + d * math.sin(e))
    cam.rotation_euler = (Vector((0, 0, cz)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, f"{NAME}_{vn}.png"); bpy.ops.render.render(write_still=True)
print("PROP", json.dumps(rep))
