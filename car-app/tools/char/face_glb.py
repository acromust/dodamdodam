# 도담도담 얼굴 조각만 따로: plaza_char2.glb 의 'face' 노드(머리 뼈 자식, 모프 face_slim·face_square)를 작은 plaza_face2.glb 로 뽑는다.
# 앱은 사람마다 이 파일을 읽으며 face.png 자리에 그 사람 얼굴 그림을 넣고(addResourceData), 뿌리를 그 사람 Head 뼈에 붙인다.
# (인스턴스 5개가 텍스처를 같이 쓰는 plaza_char2 에선 얼굴 텍스처를 사람마다 바꿀 수 없음 — gltfio 재질에 baseColorMap 을 다시 꽂아도 무시됨, 11/09 에뮬레이터 실측)
# 실행: python3 face_glb.py IN/plaza_char2.glb OUT/plaza_face2.glb   (블렌더 필요 없음)
#       python3 face_glb.py IN/plaza_char.glb OUT/plaza_shadow.glb shadow   (다른 노드 하나: 텍스처 없는 재질 그대로, 예: 옛 사람 바닥 그림자 원판)
import json, struct, sys

def read(p):
    d = open(p, "rb").read()
    jl = struct.unpack("<I", d[12:16])[0]; J = json.loads(d[20:20 + jl])
    o = 20 + jl; bl = struct.unpack("<I", d[o:o + 4])[0]
    return J, d[o + 8:o + 8 + bl]

def write(p, J, B):
    js = json.dumps(J, separators=(",", ":")).encode(); js += b" " * ((4 - len(js) % 4) % 4)
    B = bytes(B) + b"\0" * ((4 - len(B) % 4) % 4)
    with open(p, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(B)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
        f.write(struct.pack("<II", len(B), 0x004E4942)); f.write(B)

CT = {5120: "i1", 5121: "u1", 5122: "i2", 5123: "u2", 5125: "u4", 5126: "f4"}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

def acc_np(J, B, ai):
    """accessor → (count, n) float64 배열(sparse·normalized 포함)."""
    import numpy as np
    a = J["accessors"][ai]; dt = np.dtype("<" + CT[a["componentType"]]); n = NC[a["type"]]
    if "bufferView" in a:
        v = J["bufferViews"][a["bufferView"]]; es = dt.itemsize; st = v.get("byteStride", es * n)
        arr = np.ndarray((a["count"], n), dtype=dt, buffer=B, offset=v.get("byteOffset", 0) + a.get("byteOffset", 0), strides=(st, es)).astype(np.float64)
    else:
        arr = np.zeros((a["count"], n))
    if "sparse" in a:
        s = a["sparse"]; iv = J["bufferViews"][s["indices"]["bufferView"]]; vv = J["bufferViews"][s["values"]["bufferView"]]
        idx = np.frombuffer(B, dtype=np.dtype("<" + CT[s["indices"]["componentType"]]), count=s["count"], offset=iv.get("byteOffset", 0) + s["indices"].get("byteOffset", 0))
        val = np.frombuffer(B, dtype=dt, count=s["count"] * n, offset=vv.get("byteOffset", 0) + s["values"].get("byteOffset", 0)).reshape(-1, n)
        arr[idx.astype(np.int64)] = val
    if a.get("normalized") and dt.kind in "iu": arr /= np.iinfo(dt).max
    return arr

def _node_mats(J):
    import numpy as np
    N = J["nodes"]; par = {c: i for i, n in enumerate(N) for c in n.get("children", [])}
    def local(n):
        if "matrix" in n: return np.array(n["matrix"], float).reshape(4, 4).T
        x, y, z, w = n.get("rotation", [0, 0, 0, 1])
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]) * np.array(n.get("scale", [1, 1, 1]))
        M = np.eye(4); M[:3, :3] = R; M[:3, 3] = n.get("translation", [0, 0, 0]); return M
    def world(i):
        M = local(N[i])
        while i in par: i = par[i]; M = local(N[i]) @ M
        return M
    return world

def fix_face_patch(J, B, log=print):
    """얼굴 조각을 머리 피부와 이음매 없이(11/09 폰 피드백: 턱·볼 가장자리가 톱니·삼각형 얼룩).
    원인: build_char 가 머리 면 248개를 떼어 낸 조각의 법선을 조각만 보고 다시 계산함 → 같은 자리 꼭짓점 63곳이 서로 다른 법선(쪼개짐),
    머리 법선과 3~10° 차이 → 조각 안은 삼각형마다 명암이 달라 보이고, 테두리(턱 밑·볼 옆)는 머리와 명암이 갈려 삼각형 모서리 톱니가 보인다.
    고침: 조각 꼭짓점마다 짝인 머리(몸 skin) 꼭짓점을 찾아(조각 = 머리 점 + 법선×간격) 법선을 머리 법선 그대로,
    얼굴형 모프(face_slim·face_square)도 머리 모프 이동(+ 바뀐 법선 방향 간격)으로 다시 만든다 → 조각과 머리가 같은 삼각형·같은 법선이라 명암이 같다.
    J·B 를 고쳐서 돌려준다(새 데이터는 B 뒤에 붙임). 머리와 짝이 안 맞으면(간격이 들쭉날쭉) 손대지 않는다."""
    import numpy as np
    from scipy.spatial import cKDTree
    N = J["nodes"]; world = _node_mats(J)
    fi = [i for i, n in enumerate(N) if n.get("name") == "face"][0]
    bi = [i for i, n in enumerate(N) if n.get("name") == "body"][0]
    fpr = J["meshes"][N[fi]["mesh"]]["primitives"][0]
    bm = J["meshes"][N[bi]["mesh"]]
    spr = [p for p in bm["primitives"] if J["materials"][p["material"]].get("name") == "skin"][0]
    Mf = world(fi); Mb = world(bi); Rf = Mf[:3, :3]; Rb = Mb[:3, :3]; Rfi = np.linalg.inv(Rf)
    FPl = acc_np(J, B, fpr["attributes"]["POSITION"]); FP = FPl @ Rf.T + Mf[:3, 3]
    BP = acc_np(J, B, spr["attributes"]["POSITION"]) @ Rb.T + Mb[:3, 3]
    BN = acc_np(J, B, spr["attributes"]["NORMAL"]) @ Rb.T; BN /= np.linalg.norm(BN, axis=1, keepdims=True)
    d, ix = cKDTree(BP).query(FP)
    off = float(np.median(d))
    if d.max() - d.min() > 0.05 * off + 1e-5:
        log(f"fix_face_patch: 머리와 짝이 안 맞음(간격 {d.min():.5f}~{d.max():.5f}) — 그대로 둠"); return J, B
    tn = lambda m: (m.get("extras") or {}).get("targetNames", [])
    bnames, fnames = tn(bm), tn(J["meshes"][N[fi]["mesh"]])
    Nw = BN[ix]
    old_n = acc_np(J, B, fpr["attributes"]["NORMAL"]) @ Rf.T; old_n /= np.linalg.norm(old_n, axis=1, keepdims=True)
    ang = np.degrees(np.arccos(np.clip((old_n * Nw).sum(1), -1, 1)))
    P0 = BP[ix] + off * Nw                                  # 기본 자리(지금과 같음: 머리 점 + 법선 × 간격)
    nb = bytearray(B)
    def put(arr):
        arr = np.ascontiguousarray(arr, dtype="<f4")
        while len(nb) % 4: nb.append(0)
        J["bufferViews"].append({"buffer": 0, "byteOffset": len(nb), "byteLength": arr.nbytes}); nb.extend(arr.tobytes())
        J["accessors"].append({"bufferView": len(J["bufferViews"]) - 1, "componentType": 5126, "count": len(arr), "type": "VEC3",
                               "min": [float(x) for x in arr.min(0)], "max": [float(x) for x in arr.max(0)]})
        return len(J["accessors"]) - 1
    to_local = lambda W: (W - Mf[:3, 3]) @ Rfi.T
    fpr["attributes"]["POSITION"] = put(to_local(P0))
    fpr["attributes"]["NORMAL"] = put(Nw @ Rfi.T / np.linalg.norm(Nw @ Rfi.T, axis=1, keepdims=True))
    moved = {}
    for k, t in enumerate(fpr.get("targets", [])):
        nm = fnames[k] if k < len(fnames) else None
        if nm not in bnames: continue
        bt = spr["targets"][bnames.index(nm)]
        dP = acc_np(J, B, bt["POSITION"])[ix] @ Rb.T
        dN = acc_np(J, B, bt["NORMAL"])[ix] @ Rb.T if "NORMAL" in bt else np.zeros_like(dP)
        n1 = Nw + dN; n1 /= np.linalg.norm(n1, axis=1, keepdims=True)
        P1 = BP[ix] + dP + off * n1
        t["POSITION"] = put((P1 - P0) @ Rfi.T)
        if "NORMAL" in t: t["NORMAL"] = put((n1 - Nw) @ Rfi.T)
        moved[nm] = round(float(np.linalg.norm(dP, axis=1).max()), 4)
    J["buffers"][0]["byteLength"] = len(nb)
    log(f"fix_face_patch: 꼭짓점 {len(FP)}개 법선을 머리 법선으로(예전 차이 중간 {np.median(ang):.1f}° 최대 {ang.max():.1f}°), 간격 {off:.5f}, 모프 {moved}")
    return J, bytes(nb)

def main(src, dst, name="face"):
    J, B = read(src)
    if name == "face": J, B = fix_face_patch(J, B)
    fi = [i for i, n in enumerate(J["nodes"]) if n.get("name") == name][0]
    node = dict(J["nodes"][fi]); mesh = J["meshes"][node["mesh"]]
    out = {"asset": {"version": "2.0", "generator": "face_glb.py"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "accessors": [], "bufferViews": [], "buffers": [], "materials": [], "meshes": [], "nodes": [],
           "textures": [{"sampler": 0, "source": 0}], "images": [{"uri": "face.png", "name": "face"}],
           "samplers": [{"magFilter": 9729, "minFilter": 9729, "wrapS": 33071, "wrapT": 33071}]}
    nb = bytearray(); bvmap = {}; accmap = {}
    def bv(i):   # 버퍼 조각 옮기기
        if i in bvmap: return bvmap[i]
        v = dict(J["bufferViews"][i]); s = v.get("byteOffset", 0)
        while len(nb) % 4: nb.append(0)
        v["byteOffset"] = len(nb); v["buffer"] = 0; nb.extend(B[s:s + v["byteLength"]])
        out["bufferViews"].append(v); bvmap[i] = len(out["bufferViews"]) - 1; return bvmap[i]
    def acc(i):
        if i in accmap: return accmap[i]
        a = json.loads(json.dumps(J["accessors"][i]))
        if "bufferView" in a: a["bufferView"] = bv(a["bufferView"])
        if "sparse" in a:
            for k in ("indices", "values"): a["sparse"][k]["bufferView"] = bv(a["sparse"][k]["bufferView"])
        out["accessors"].append(a); accmap[i] = len(out["accessors"]) - 1; return accmap[i]
    mat = json.loads(json.dumps(J["materials"][mesh["primitives"][0]["material"]]))
    if name == "face": mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": 0}
    else:
        for k in ("textures", "images", "samplers"): out.pop(k)
        mat["pbrMetallicRoughness"].pop("baseColorTexture", None)
    out["materials"].append(mat)
    prims = []
    for p in mesh["primitives"]:
        q = {"attributes": {k: acc(v) for k, v in p["attributes"].items()}, "material": 0}
        if "indices" in p: q["indices"] = acc(p["indices"])
        if "targets" in p: q["targets"] = [{k: acc(v) for k, v in t.items()} for t in p["targets"]]
        prims.append(q)
    m = {"name": name, "primitives": prims}
    if "extras" in mesh: m["extras"] = mesh["extras"]
    if "weights" in mesh: m["weights"] = mesh["weights"]
    out["meshes"].append(m)
    n = {"name": name, "mesh": 0}
    for k in ("translation", "rotation", "scale"):   # 머리 뼈 기준 변환 그대로(앱이 뿌리를 Head 뼈에 붙임)
        if k in node: n[k] = node[k]
    out["nodes"].append(n)
    out["buffers"] = [{"byteLength": len(nb)}]
    write(dst, out, nb)
    print("face_glb:", dst, len(nb), "bytes,", len(out["accessors"]), "accessors")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "face")
