"""폰 웹 캐릭터 미리보기용 가벼운 사본: assets/plaza_char2.glb → server/web/avatar/char.glb (+ 얼굴 부품 그림 복사).

차 앱 자산과 같은 몸·가발·수염·안경·이어폰·목도리·모프(build_slim/build_chubby/face_slim/face_square)를 그대로 두고, 웹에 필요 없는 것만 줄인다.
- 동작: 서 있기(Short_Breathe_and_Look_Around)·쿠션에 앉기(Chair_Sit_Idle_F) 둘만
- 손 소품(prop_book/cup/phone)과 이어폰(earbud)은 뺀다
- 그림: 한 변 256 이하 WebP(EXT_texture_webp). 얼굴 그림(face.png, 차 앱이 사람마다 넣는 자리)은 흰 4×4로 넣어 둔다(웹이 사람마다 바꿔 끼움)
- 얼굴 조각: face_glb.fix_face_patch 로 법선·얼굴형 모프를 머리와 같게(턱·볼 가장자리 톱니 없앰)
- 정점: 법선 BYTE·UV UNSIGNED_SHORT·뼈 가중치 UNSIGNED_BYTE(KHR_mesh_quantization). 모프의 법선 차이는 뺀다(위치 차이만)
쓰는 법: python3 car-app/tools/char/web_char.py   (저장소 맨 위에서)
"""
import io
import json
import os
import shutil
import struct
import sys

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SRC = os.path.join(ROOT, "car-app", "app", "src", "main", "assets", "plaza_char2.glb")
OUT_DIR = os.path.join(ROOT, "server", "web", "avatar")
KEEP_CLIPS = ("Short_Breathe_and_Look_Around", "Chair_Sit_Idle_F")
DROP_NODES = ("prop_book", "prop_cup", "prop_phone", "earbud")   # 이어폰은 11/09 사용자 결정으로 뺐다
MAX_TEX = 256

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(p):
    b = open(p, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    o = 20 + jl
    bl = struct.unpack("<I", b[o:o + 4])[0]
    return j, b[o + 8:o + 8 + bl]


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


def main():
    j, binb = read_glb(SRC)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from face_glb import fix_face_patch   # 얼굴 조각 법선·모프를 머리와 같게(차 앱 plaza_face2.glb 와 같은 고침)
    j, binb = fix_face_patch(j, binb)
    out = Out()

    def raw_view(vi):
        v = j["bufferViews"][vi]
        o = v.get("byteOffset", 0)
        return binb[o:o + v["byteLength"]], v

    def read_acc(ai):
        """밀집 배열(count, n)로 읽기(sparse 포함)."""
        a = j["accessors"][ai]
        dt = CT[a["componentType"]]; n = NC[a["type"]]; cnt = a["count"]
        if "bufferView" in a:
            data, v = raw_view(a["bufferView"])
            es = np.dtype(dt).itemsize
            stride = v.get("byteStride", es * n)
            off = a.get("byteOffset", 0)
            arr = np.ndarray((cnt, n), dtype=dt, buffer=bytes(data), offset=off, strides=(stride, es)).copy()
        else:
            arr = np.zeros((cnt, n), dtype=dt)
        if "sparse" in a:
            s = a["sparse"]
            idata, _ = raw_view(s["indices"]["bufferView"])
            idx = np.frombuffer(bytes(idata), dtype=CT[s["indices"]["componentType"]], count=s["count"], offset=s["indices"].get("byteOffset", 0))
            vdata, _ = raw_view(s["values"]["bufferView"])
            val = np.frombuffer(bytes(vdata), dtype=dt, count=s["count"] * n, offset=s["values"].get("byteOffset", 0)).reshape(-1, n)
            arr[idx] = val
        return arr, a

    def put(arr, ctype, typ, normalized=False, target=None, minmax=False, pad4=False):
        arr = np.ascontiguousarray(arr.astype(CT[ctype]))
        n = NC[typ]; es = arr.dtype.itemsize
        stride = None
        if pad4 and (n * es) % 4:
            w = ((n * es + 3) // 4) * 4 // es
            p = np.zeros((arr.shape[0], w), dtype=arr.dtype); p[:, :n] = arr; arr = p; stride = w * es
        vi = out.view(arr.tobytes(), stride=stride, target=target)
        a = {"bufferView": vi, "componentType": ctype, "count": int(arr.shape[0]), "type": typ}
        if normalized:
            a["normalized"] = True
        if minmax:
            a["min"] = [float(x) for x in arr[:, :n].min(0)]; a["max"] = [float(x) for x in arr[:, :n].max(0)]
        out.accs.append(a)
        return len(out.accs) - 1

    def put_sparse_delta(arr):
        """모프 위치 차이: 0이 아닌 줄만(sparse, 바탕 bufferView 없음 = 0)."""
        nz = np.nonzero(np.any(arr != 0, axis=1))[0]
        a = {"componentType": 5126, "count": int(arr.shape[0]), "type": "VEC3",
             "min": [float(x) for x in arr.min(0)], "max": [float(x) for x in arr.max(0)]}
        if len(nz):
            it = 5123 if arr.shape[0] < 65536 else 5125
            iv = out.view(nz.astype(CT[it]).tobytes())
            vv = out.view(np.ascontiguousarray(arr[nz].astype(np.float32)).tobytes())
            a["sparse"] = {"count": int(len(nz)), "indices": {"bufferView": iv, "componentType": it}, "values": {"bufferView": vv}}
        out.accs.append(a)
        return len(out.accs) - 1

    cache = {}

    def copy_acc(ai, minmax=None, target=None):
        if ai in cache:
            return cache[ai]
        arr, a = read_acc(ai)
        mm = ("min" in a) if minmax is None else minmax
        cache[ai] = put(arr, a["componentType"], a["type"], a.get("normalized", False), target=target, minmax=mm)
        return cache[ai]

    # ---- 노드: 소품 메시 떼기 ----
    nodes = j["nodes"]
    for nd in nodes:
        if nd.get("name") in DROP_NODES:
            nd.pop("mesh", None)

    # ---- 메시 ----
    used_mats = []
    mat_map = {}
    new_meshes = []
    mesh_map = {}
    for nd in nodes:
        if "mesh" not in nd:
            continue
        mi = nd["mesh"]
        if mi not in mesh_map:
            m = j["meshes"][mi]
            prims = []
            for pr in m["primitives"]:
                at = {}
                for k, ai in pr["attributes"].items():
                    arr, a = read_acc(ai)
                    if k == "POSITION":
                        at[k] = put(arr, 5126, "VEC3", target=34962, minmax=True)
                    elif k == "NORMAL":
                        q = np.round(np.clip(arr, -1, 1) * 127).astype(np.int8)
                        at[k] = put(q, 5120, "VEC3", normalized=True, target=34962, pad4=True)
                    elif k == "TEXCOORD_0" and arr.min() >= 0 and arr.max() <= 1:
                        at[k] = put(np.round(arr * 65535), 5123, "VEC2", normalized=True, target=34962)
                    elif k == "WEIGHTS_0" and a["componentType"] == 5126:
                        w = np.clip(arr, 0, 1); s = w.sum(1, keepdims=True); s[s == 0] = 1; w = w / s
                        q = np.floor(w * 255).astype(np.int32)
                        rem = 255 - q.sum(1)
                        frac = w * 255 - q
                        order = np.argsort(-frac, axis=1)
                        for r in range(4):   # 반올림 차이를 큰 소수부터 1씩 나눠 합이 정확히 255
                            sel = rem > r
                            q[np.arange(len(q))[sel], order[sel, r]] += 1
                        at[k] = put(q, 5121, "VEC4", normalized=True, target=34962)
                    else:
                        at[k] = put(arr, a["componentType"], a["type"], a.get("normalized", False), target=34962)
                np2 = {"attributes": at}
                if "indices" in pr:
                    arr, a = read_acc(pr["indices"])
                    np2["indices"] = put(arr, a["componentType"], "SCALAR", target=34963)
                if "material" in pr:
                    om = pr["material"]
                    if om not in mat_map:
                        mat_map[om] = len(used_mats); used_mats.append(om)
                    np2["material"] = mat_map[om]
                if "mode" in pr:
                    np2["mode"] = pr["mode"]
                if pr.get("targets"):
                    np2["targets"] = [{"POSITION": put_sparse_delta(read_acc(t["POSITION"])[0])} for t in pr["targets"]]
                prims.append(np2)
            nm = {"name": m.get("name"), "primitives": prims}
            for k in ("weights", "extras"):
                if k in m:
                    nm[k] = m[k]
            mesh_map[mi] = len(new_meshes); new_meshes.append(nm)
        nd["mesh"] = mesh_map[mi]

    # ---- 재질·텍스처·그림 ----
    tex_map, new_tex, img_map, new_imgs = {}, [], {}, []

    def img_bytes(ii):
        im = j["images"][ii]
        if "bufferView" not in im:   # face.png(차 앱이 사람마다 넣는 자리): 흰 그림
            I = Image.new("RGBA", (4, 4), (255, 255, 255, 255))
        else:
            d, _ = raw_view(im["bufferView"])
            I = Image.open(io.BytesIO(bytes(d))).convert("RGBA")
            if max(I.size) > MAX_TEX:
                k = MAX_TEX / max(I.size)
                I = I.resize((max(1, round(I.width * k)), max(1, round(I.height * k))), Image.LANCZOS)
        buf = io.BytesIO()
        I.save(buf, "WEBP", quality=82, method=6, alpha_quality=100)
        return buf.getvalue()

    def tex(ti):
        if ti in tex_map:
            return tex_map[ti]
        t = j["textures"][ti]
        ii = t["source"]
        if ii not in img_map:
            vi = out.view(img_bytes(ii))
            img_map[ii] = len(new_imgs)
            new_imgs.append({"name": j["images"][ii].get("name", f"img{ii}"), "mimeType": "image/webp", "bufferView": vi})
        nt = {"extensions": {"EXT_texture_webp": {"source": img_map[ii]}}}
        if "sampler" in t:
            nt["sampler"] = t["sampler"]
        tex_map[ti] = len(new_tex); new_tex.append(nt)
        return tex_map[ti]

    new_mats = []
    for om in used_mats:
        m = json.loads(json.dumps(j["materials"][om]))
        pbr = m.get("pbrMetallicRoughness", {})
        if "baseColorTexture" in pbr:
            pbr["baseColorTexture"]["index"] = tex(pbr["baseColorTexture"]["index"])
        for k in ("normalTexture", "occlusionTexture", "emissiveTexture"):
            if k in m:
                m[k]["index"] = tex(m[k]["index"])
        new_mats.append(m)

    # ---- 뼈 ----
    skins = []
    for s in j.get("skins", []):
        s = dict(s)
        if "inverseBindMatrices" in s:
            s["inverseBindMatrices"] = copy_acc(s["inverseBindMatrices"], minmax=False)
        skins.append(s)

    # ---- 동작 ----
    anims = []
    for an in j.get("animations", []):
        if an["name"] not in KEEP_CLIPS:
            continue
        samp = []
        for sp in an["samplers"]:
            samp.append({"input": copy_acc(sp["input"], minmax=True), "output": copy_acc(sp["output"], minmax=False),
                         "interpolation": sp.get("interpolation", "LINEAR")})
        anims.append({"name": an["name"], "channels": an["channels"], "samplers": samp})
    missing = set(KEEP_CLIPS) - {a["name"] for a in anims}
    if missing:
        sys.exit(f"없는 동작: {missing}")

    g = {"asset": {"version": "2.0", "generator": "dodam web_char.py"}, "scene": j.get("scene", 0), "scenes": j["scenes"],
         "nodes": nodes, "meshes": new_meshes, "materials": new_mats, "textures": new_tex, "images": new_imgs,
         "samplers": j.get("samplers", []), "skins": skins, "animations": anims,
         "accessors": out.accs, "bufferViews": out.views, "buffers": [{"byteLength": 0}],
         "extensionsUsed": ["KHR_mesh_quantization", "EXT_texture_webp"],
         "extensionsRequired": ["KHR_mesh_quantization", "EXT_texture_webp"]}
    while len(out.bin) % 4:
        out.bin.append(0)
    g["buffers"][0]["byteLength"] = len(out.bin)
    js = json.dumps(g, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    body = struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(out.bin), b"BIN\0") + bytes(out.bin)
    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, "char.glb")
    with open(dst, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
    a_dir = os.path.dirname(SRC)
    for n in ("face_atlas.png", "face_atlas.json"):
        shutil.copyfile(os.path.join(a_dir, n), os.path.join(OUT_DIR, n))
    print(dst, os.path.getsize(dst), "bytes (원본", os.path.getsize(SRC), ")")


if __name__ == "__main__":
    main()
