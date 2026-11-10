"""폰 웹 광장 그림용 가벼운 장면: assets/plaza_scene.glb + plaza_bird.glb → server/web/avatar/plaza.glb

차 앱 광장(맑은 낮)에 보이는 것만 남긴다: 받침판·옆면·그림자, 나무(줄기·잎)·가로등, 벤치, 풀 7, 빈백 쿠션 5·쿠션 그림자 5·'+' 5,
말 거는 자리, 잔디, 디딤돌, 화분, 그리고 나뭇가지 끝의 새(idle_breathe 0초 자세로 굳혀 뼈 없이).
비·눈·돔·눈사람·충전 기둥·빛 웅덩이·물웅덩이는 뺀다. 노드 이름·재질 이름(cushion1..5, plus1..5, cshadow1..5)은 차 장면과 같다.
줄이는 법(web_char.py 와 같은 결): 그림은 한 변 256 이하 WebP, 법선 BYTE·UV UNSIGNED_SHORT·위치 SHORT(KHR_mesh_quantization).
위치를 SHORT 로 줄인 메시는 '<이름>_q' 자식 노드(가운데 이동 + 균일 크기)에 달아 둔다. 같은 모양(쿠션 5개·풀 7포기)은 한 번만 넣는다.
쓰는 법: python3 car-app/tools/web_plaza.py   (저장소 어디서 실행해도 됨). 다시 만들면 server/web/avatar3d.js 의 PLAZA_V 를 올린다.
초대장 첫 화면 그림(server/web/hello-plaza-720/1080/1440.webp + 받침 JPEG hello-plaza.jpg 1080)도 이 장면으로 만든다(11/10 선명하게):
  1) 그림 크게 넣은 장면·캐릭터: 이 파일과 char/web_char.py 를 MAX_TEX=2048(원본 크기 그대로)·WebP 무손실로 바꿔 서버 사본의 web/avatar 에만 만든다(저장소 파일은 그대로)
  2) 그 사본 서버를 띄운 헤드리스 Chrome 페이지에서
     m = await import("/avatar3d.js"); await m.plazaReady(); m.plazaPicture([가족 4명 엄마·할머니·아빠·형을 자리 1~4에(11/10 사장이 고른 가족, 부품 값은 커밋 메시지), cat.base 에 부품만 덮어 씀], cat, 2160, 1620, 2)
     (안에서 4320×3240 으로 그려 반으로 줄인 PNG. 5번 자리는 회색 '+' 쿠션)
  3) PIL LANCZOS 로 1440·1080·720 폭으로 줄여 cwebp -q 95 -m 6 -sharp_yuv, JPEG 은 1080 품질 92(4:4:4)
"""
import hashlib
import io
import json
import math
import os
import struct

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS = os.path.join(ROOT, "car-app", "app", "src", "main", "assets")
OUT = os.path.join(ROOT, "server", "web", "avatar", "plaza.glb")
KEEP = ["plate", "rim", "plate_shadow", "lawn", "shadows", "tree_trunk", "tree_crown", "lamp_pole", "lamp_head", "bench"] \
    + [f"grass{i}" for i in range(1, 8)] + ["stones", "talk", "pot", "pot_flowers"] \
    + [f"{k}{i}" for i in range(1, 6) for k in ("cshadow", "cushion", "plus")]
# 새: PlazaView.BIRD_TREE·BIRD_SCALE·camYaw(BIRD_TREE) - 0.5 와 같게(나무 오른쪽 앞 맨가지 끝, 1.5배)
BIRD_TREE = (1.31, 1.70, -2.14)
BIRD_SCALE = 1.5
TARGET_Z = 6.0
BIRD_YAW = math.atan2(0 - BIRD_TREE[0], TARGET_Z - BIRD_TREE[2]) - 0.5
MAX_TEX = 256

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(p):
    b = open(p, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    o = 20 + jl
    return j, b[o + 8:o + 8 + struct.unpack("<I", b[o:o + 4])[0]]


def reader(j, binb):
    def acc(ai):
        a = j["accessors"][ai]; v = j["bufferViews"][a["bufferView"]]
        dt = CT[a["componentType"]]; n = NC[a["type"]]; es = np.dtype(dt).itemsize
        st = v.get("byteStride", es * n); off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.ndarray((a["count"], n), dtype=dt, buffer=binb, offset=off, strides=(st, es)).copy()

    def image(ii):
        v = j["bufferViews"][j["images"][ii]["bufferView"]]; o = v.get("byteOffset", 0)
        return Image.open(io.BytesIO(binb[o:o + v["byteLength"]])).convert("RGB")
    return acc, image


# ---- 행렬 ----
def quat_m(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def trs(t=None, r=None, s=None):
    m = np.eye(4)
    m[:3, :3] = quat_m(r if r is not None else (0, 0, 0, 1)) @ np.diag(s if s is not None else (1, 1, 1))
    if t is not None:
        m[:3, 3] = t
    return m


class Out:
    def __init__(self):
        self.bin = bytearray(); self.views = []; self.accs = []

    def view(self, data, stride=None, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if stride:
            v["byteStride"] = stride
        if target:
            v["target"] = target
        self.bin += data
        self.views.append(v)
        return len(self.views) - 1

    def put(self, arr, ctype, typ, normalized=False, target=None, minmax=False):
        arr = np.ascontiguousarray(arr.astype(CT[ctype]))
        n = NC[typ]; es = arr.dtype.itemsize; stride = None
        if target == 34962 and (n * es) % 4:   # 정점 속성은 4바이트 줄 맞춤
            w = ((n * es + 3) // 4) * 4 // es
            p = np.zeros((arr.shape[0], w), dtype=arr.dtype); p[:, :n] = arr; arr = p; stride = w * es
        a = {"bufferView": self.view(arr.tobytes(), stride=stride, target=target), "componentType": ctype, "count": int(arr.shape[0]), "type": typ}
        if normalized:
            a["normalized"] = True
        if minmax:
            a["min"] = [int(x) if ctype != 5126 else float(x) for x in arr[:, :n].min(0)]
            a["max"] = [int(x) if ctype != 5126 else float(x) for x in arr[:, :n].max(0)]
        self.accs.append(a)
        return len(self.accs) - 1


def bird_baked():
    """새를 idle_breathe 0초 자세로 굳힌 위치·법선·UV·번호와 그림(뼈 없이)."""
    j, binb = read_glb(os.path.join(ASSETS, "plaza_bird.glb"))
    acc, image = reader(j, binb)
    nodes = j["nodes"]
    local = {i: trs(n.get("translation"), n.get("rotation"), n.get("scale")) for i, n in enumerate(nodes)}
    an = next(a for a in j["animations"] if a["name"] == "idle_breathe")
    pose = {}
    for c in an["channels"]:
        sp = an["samplers"][c["sampler"]]
        pose.setdefault(c["target"]["node"], {})[c["target"]["path"]] = acc(sp["output"])[0]
    for ni, d in pose.items():
        n = nodes[ni]
        local[ni] = trs(d.get("translation", n.get("translation")), d.get("rotation", n.get("rotation")), d.get("scale", n.get("scale")))
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}

    def world(i):
        m = local[i]
        while i in parent:
            i = parent[i]; m = local[i] @ m
        return m
    sk = j["skins"][0]
    ibm = acc(sk["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)   # glTF 열 우선
    mesh_node = next(i for i, n in enumerate(nodes) if "skin" in n)
    inv_mesh = np.linalg.inv(world(mesh_node))
    J = np.array([inv_mesh @ world(jn) @ ibm[k] for k, jn in enumerate(sk["joints"])])
    pr = j["meshes"][0]["primitives"][0]; at = pr["attributes"]
    p = acc(at["POSITION"]).astype(np.float64); nrm = acc(at["NORMAL"]).astype(np.float64)
    jt = acc(at["JOINTS_0"]).astype(int); w = acc(at["WEIGHTS_0"]).astype(np.float64)
    wct = j["accessors"][at["WEIGHTS_0"]]["componentType"]
    if wct != 5126:   # 정수 가중치(정규화)
        w = w / (255.0 if wct == 5121 else 65535.0)
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-9)
    M = (J[jt] * w[:, :, None, None]).sum(1)          # 정점마다 4×4
    ph = np.concatenate([p, np.ones((len(p), 1))], 1)
    P = np.einsum("nij,nj->ni", M, ph)[:, :3]
    N = np.einsum("nij,nj->ni", np.linalg.inv(M[:, :3, :3]).transpose(0, 2, 1), nrm)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    mat = j["materials"][pr["material"]]
    img = image(j["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"])
    return P, N, acc(at["TEXCOORD_0"]).astype(np.float64), acc(pr["indices"]).reshape(-1), img, mat


def main():
    j, binb = read_glb(os.path.join(ASSETS, "plaza_scene.glb"))
    acc, image = reader(j, binb)
    out = Out()
    geo = {}   # 같은 모양 → (mesh 번호 없이) 속성 accessor 묶음과 가운데·크기

    def put_geo(P, N, UV, I):
        key = hashlib.sha1(np.ascontiguousarray(P, np.float32).tobytes() + np.ascontiguousarray(I, np.uint32).tobytes()).hexdigest()
        if key in geo:
            return geo[key]
        lo, hi = P.min(0), P.max(0); c = (lo + hi) / 2; s = float(max((hi - lo).max() / 2, 1e-6))
        q = np.round((P - c) / s * 32767).clip(-32767, 32767)
        at = {"POSITION": out.put(q, 5122, "VEC3", normalized=True, target=34962, minmax=True),
              "NORMAL": out.put(np.round(np.clip(N, -1, 1) * 127), 5120, "VEC3", normalized=True, target=34962)}
        if UV.min() >= 0 and UV.max() <= 1:
            at["TEXCOORD_0"] = out.put(np.round(UV * 65535), 5123, "VEC2", normalized=True, target=34962)
        else:
            at["TEXCOORD_0"] = out.put(UV, 5126, "VEC2", target=34962)
        it = 5123 if len(P) < 65536 else 5125
        ind = out.put(np.asarray(I).reshape(-1, 1), it, "SCALAR", target=34963)
        geo[key] = (at, ind, [float(x) for x in c], s)
        return geo[key]

    # ---- 그림·재질 ----
    images, textures, mats, img_map, mat_map = [], [], [], {}, {}

    def webp(img):
        if max(img.size) > MAX_TEX:
            k = MAX_TEX / max(img.size)
            img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
        b = io.BytesIO(); img.save(b, "WEBP", quality=80, method=6)
        images.append({"mimeType": "image/webp", "bufferView": out.view(b.getvalue())})
        textures.append({"sampler": 0, "extensions": {"EXT_texture_webp": {"source": len(images) - 1}}})
        return len(textures) - 1

    def material(mi, src_j=None, img_fn=None):
        src_j = src_j or j; img_fn = img_fn or image
        key = (id(src_j), mi)
        if key in mat_map:
            return mat_map[key]
        m = json.loads(json.dumps(src_j["materials"][mi]))
        pbr = m.get("pbrMetallicRoughness", {})
        if "baseColorTexture" in pbr:
            si = src_j["textures"][pbr["baseColorTexture"]["index"]]["source"]
            ik = (id(src_j), si)
            if ik not in img_map:
                img_map[ik] = webp(img_fn(si))
            pbr["baseColorTexture"] = {"index": img_map[ik]}
        m.pop("emissiveFactor", None) if m.get("emissiveFactor") == [0.0, 0.0, 0.0] else None
        mats.append(m); mat_map[key] = len(mats) - 1
        return mat_map[key]

    # ---- 노드 ----
    nodes, meshes, roots = [], [], []

    def add_mesh_node(name, prims, t=None, r=None, s=None):
        """name 노드(원래 자리) 아래 '<name>_q' 자식(가운데·크기)에 메시. 프리미티브가 여럿이면 첫 것의 가운데·크기를 쓴다(이 장면은 하나씩)."""
        (at, ind, c, sc), mat = prims[0]
        meshes.append({"name": name, "primitives": [{"attributes": at, "indices": ind, "material": mat}]})
        nodes.append({"name": f"{name}_q", "mesh": len(meshes) - 1, "translation": c, "scale": [sc, sc, sc]})
        nd = {"name": name, "children": [len(nodes) - 1]}
        for k, v in (("translation", t), ("rotation", r), ("scale", s)):
            if v is not None:
                nd[k] = [float(x) for x in v]
        nodes.append(nd)
        roots.append(len(nodes) - 1)

    by_name = {n["name"]: n for n in j["nodes"]}
    tris = 0
    for name in KEEP:
        n = by_name[name]
        prs = j["meshes"][n["mesh"]]["primitives"]
        assert len(prs) == 1, name
        pr = prs[0]; a = pr["attributes"]
        I = acc(pr["indices"]).reshape(-1); tris += len(I) // 3
        g = put_geo(acc(a["POSITION"]).astype(np.float64), acc(a["NORMAL"]).astype(np.float64), acc(a["TEXCOORD_0"]).astype(np.float64), I)
        add_mesh_node(name, [(g, material(pr["material"]))], n.get("translation"), n.get("rotation"), n.get("scale"))
    # 새
    P, N, UV, I, bimg, bmat = bird_baked()
    tris += len(I) // 3
    bj = {"materials": [bmat], "textures": [{"source": 0}]}
    g = put_geo(P, N, UV, I)
    q = (0.0, math.sin(BIRD_YAW / 2), 0.0, math.cos(BIRD_YAW / 2))
    add_mesh_node("bird", [(g, material(0, bj, lambda _i: bimg))], BIRD_TREE, q, (BIRD_SCALE,) * 3)

    g = {"asset": {"version": "2.0", "generator": "dodam web_plaza.py"}, "scene": 0, "scenes": [{"name": "plaza", "nodes": roots}],
         "nodes": nodes, "meshes": meshes, "materials": mats, "textures": textures, "images": images,
         "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
         "accessors": out.accs, "bufferViews": out.views, "buffers": [{"byteLength": 0}],
         "extensionsUsed": ["KHR_mesh_quantization", "EXT_texture_webp"],
         "extensionsRequired": ["KHR_mesh_quantization", "EXT_texture_webp"]}
    while len(out.bin) % 4:
        out.bin.append(0)
    g["buffers"][0]["byteLength"] = len(out.bin)
    js = json.dumps(g, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    body = struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(out.bin), b"BIN\0") + bytes(out.bin)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
    import gzip
    print(OUT, os.path.getsize(OUT), "bytes, gzip", len(gzip.compress(open(OUT, "rb").read(), 6)), "bytes, 삼각형", tris, "그림", len(images))


if __name__ == "__main__":
    main()
