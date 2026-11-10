# 도담도담 캐릭터: 머리카락·수염·목도리가 몸을 뚫지 않게 (build_char.py 8단계 뒤 한 줄로 부름: char_fix_hair.apply(...))
#  1) 쉬는 자세 밀어내기: 목 아래 몸(몸통·다리) 안쪽이거나 너무 가까운 점을 가까운 몸 면 바깥으로 민다.
#     거리 d → c + w·softplus((d - c)/w) (순서가 안 바뀌어 겹이 뒤집히지 않음, 몸에서 4 cm 넘게 떨어진 점은 그대로) + 이웃으로 퍼지게
#  2) 무게: 점마다 s (0 = 집 뼈 100 %, 1 = 바로 밑 몸 겉면의 뼈 무게 그대로). 동작 전부를 0.25초마다 돌려 뚫리는 점만 s를 올리고
#     → (머리에 달린 부품은) 아래로 번지게 → 넓혀서 퍼지게. s가 전부 0인 부품은 뼈 자식 그대로(짧은 머리).
#     팔·손 뼈는 겉면 무게에서 빼서 어깨(쇄골) 뼈로, 다리 뼈는 Hips로 돌린다(손 흔들 때 머리카락이 끌려 올라가지 않게).
#  노드 이름·재질 이름·모프·삼각형 수는 그대로(점 위치·뼈 무게만 바뀜).
# 측정:  Blender -b --factory-startup -P char_fix_hair.py -- --measure GLB OUT.json
# 렌더:  Blender -b --factory-startup -P char_fix_hair.py -- --render GLB TAG DIR    (비교 시트는 --sheet DIR OUT.jpg, 시스템 python3)
import json, math, os, sys, time
import numpy as np
try:
    import bpy
    from mathutils import Vector, Matrix
    from mathutils.bvhtree import BVHTree
    from mathutils.kdtree import KDTree
except ImportError: bpy = None   # --sheet 은 시스템 python3

HEAD, HIPS = "mixamorig:Head", "mixamorig:Hips"
FPS = 30
CLASSES = ("head", "torso", "arm", "hand", "leg")
CLEAR, SOFT = 0.006, 0.008          # 쉬는 자세 여유(m)·부드럽게 붙는 폭
TOL = 0.004                         # 동작 중 이만큼(4 mm)까지는 봐줌
S_STEP = 0.25
IDLE_POSE = ("Short_Breathe_and_Look_Around", 0.0)   # 팔 내린 기본 서기 자세
FRAME_STEP = 0.25                   # 동작 표본 간격(초)

def _chain(bones, name):
    b, out = bones[name], []
    while b: out.append(b.name); b = b.parent
    return out

def bone_class(bones, name):
    ch = _chain(bones, name)
    if HEAD in ch: return "head"
    if any("UpLeg" in c for c in ch): return "leg"
    if any("ForeArm" in c for c in ch): return "hand"
    if any(c.endswith(("LeftArm", "RightArm")) for c in ch): return "arm"
    return "torso"

LEG_SHARE = 0.0                     # 다리 겉면 무게 중 넓적다리 뼈 몫(나머지 Hips). 0.35 시험: 앉을 때 긴 머리 끝이 정강이 앞으로 끌려 나와 탈락
ARM_SHARE = 0.5                     # 팔·손 겉면 무게 중 위팔 뼈로 가는 몫(나머지는 쇄골): 팔이 머리카락을 밀되 팔 들 때 끌려 올라가진 않게
def bind_map(bones, name):
    """몸 뼈 → 부품이 따라갈 뼈 {이름: 몫}."""
    ch = _chain(bones, name); cls = bone_class(bones, name)
    if cls == "head": return {HEAD: 1.0}
    if cls == "leg":
        side = "Left" if any("Left" in c for c in ch) else "Right"
        return {f"mixamorig:{side}UpLeg": LEG_SHARE, HIPS: 1 - LEG_SHARE}
    if cls in ("arm", "hand"):
        side = "Left" if any("Left" in c for c in ch) else "Right"
        return {f"mixamorig:{side}Arm": ARM_SHARE, f"mixamorig:{side}Shoulder": 1 - ARM_SHARE}
    return {name: 1.0}

def body_weights(body, bones):
    """몸 점별 뼈 무게 (N, B) + 뼈 이름 목록."""
    names = [g.name for g in body.vertex_groups if g.name in bones]
    col = {g.index: names.index(g.name) for g in body.vertex_groups if g.name in bones}
    W = np.zeros((len(body.data.vertices), len(names)))
    for v in body.data.vertices:
        for g in v.groups:
            if g.group in col: W[v.index, col[g.group]] = g.weight
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    return W, names

def face_classes(body, W, names, bones):
    cls_of = np.array([CLASSES.index(bone_class(bones, n)) for n in names])
    C = np.zeros((len(W), len(CLASSES)))
    for j, c in enumerate(cls_of): C[:, c] += W[:, j]
    return np.array([int(C[list(p.vertices)].sum(0).argmax()) for p in body.data.polygons])

def mesh_world(o, dg):
    eo = o.evaluated_get(dg); m = eo.to_mesh()
    X = np.empty(len(m.vertices) * 3); m.vertices.foreach_get("co", X); eo.to_mesh_clear()
    Mw = np.array(eo.matrix_world); return X.reshape(-1, 3) @ Mw[:3, :3].T + Mw[:3, 3]

def signed_near(bvh, pts, reach):
    """점마다 (부호 거리, 바깥 방향, 면 번호). 못 찾으면 면 -1. 부호: 몸 안쪽이 음수."""
    n = len(pts); sd = np.full(n, 9.0); nr = np.zeros((n, 3)); fi = np.full(n, -1)
    for i, p in enumerate(pts):
        loc, nn, f, d = bvh.find_nearest(Vector(p), reach)
        if loc is None: continue
        s = (p[0] - loc[0]) * nn[0] + (p[1] - loc[1]) * nn[1] + (p[2] - loc[2]) * nn[2]
        sd[i] = d if s >= 0 else -d; nr[i] = nn[:]; fi[i] = f
    return sd, nr, fi

def kd_of(X):
    kd = KDTree(len(X))
    for i, p in enumerate(X): kd.insert(p, i)
    kd.balance(); return kd

def blur(kd, X, F, sig, r=None):
    r = r or 2.5 * sig; out = np.zeros_like(F)
    for i, p in enumerate(X):
        nb = kd.find_range(p, r); ix = np.array([b[1] for b in nb]); d = np.array([b[2] for b in nb])
        w = np.exp(-0.5 * (d / sig) ** 2); out[i] = (F[ix] * (w[:, None] if F.ndim > 1 else w)).sum(0) / w.sum()
    return out

def softplus_target(sd):
    return CLEAR + SOFT * np.logaddexp(0, (sd - CLEAR) / SOFT)

# ════════════════════════════════════════════════════════════════════ 0. 너무 긴 머리 줄이기(발목까지 → 허리)
# 자르지 않고 z_start 아래를 위로 눌러 담음: 원래 머리끝 모양(가늘어지는 끝·알파)·UV·텍스처·삼각형 수 그대로.
# 처음 ease m 동안은 눌림이 0에서 서서히 커져(어깨 쪽 모양 그대로) 이음매가 안 보임. 좌표 = 리깅 몸 기준(m, 1.7 m 키)
SHORTEN = {"hair_w_long": dict(z_start=1.00, z_end=0.78, ease=0.15)}   # 허리 위·등 가운데(Spine1 0.80, 엉덩이 옆 0.70보다 위: 걸을 때 골반·허벅지에 안 걸리게). w_wave(끝 0.66)는 다리에 안 닿아 그대로
# 올라온 아래쪽 머리(다리를 감싸던 안쪽 겹)가 허리·엉덩이 속으로 들어가지 않게: 올라간 높이에서 원래 머리의 안쪽 반지름(몸 중심축 기준, 방향별)보다 안으로는 못 들어오게

def shorten(me, z_start, z_end, ease=0.15):
    X = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", X); X = X.reshape(-1, 3)
    L, Ln = z_start - X[:, 2].min(), z_start - z_end
    if L <= Ln: return {"skipped": True}
    c = (Ln - 0.5 * ease) / (L - 0.5 * ease)                          # 눌린 뒤 길이 비율(ease 다음 구간)
    d = np.maximum(0.0, z_start - X[:, 2])
    g = np.where(d < ease, d - (1 - c) * d * d / (2 * ease), c * d + (1 - c) * ease / 2)
    dz = (d - g)                                                       # 위로 올리는 양
    X0 = X.copy(); X[:, 2] += dz
    cy, NB, ZB = 0.02, 24, 0.03                                        # 몸 중심축(y), 방향 칸, 높이 칸(m)
    def polar(P): return np.arctan2(P[:, 1] - cy, P[:, 0]), np.hypot(P[:, 0], P[:, 1] - cy)
    ph0, r0 = polar(X0); pb0 = ((ph0 + np.pi) / (2 * np.pi) * NB).astype(int) % NB; zb0 = np.floor(X0[:, 2] / ZB).astype(int)
    rmin = {}
    for zb, pb, r in zip(zb0, pb0, r0): rmin.setdefault((zb, pb), []).append(r)
    rmin = {k: float(np.percentile(v, 15)) for k, v in rmin.items() if len(v) >= 4}
    ph, r = polar(X); pb = ((ph + np.pi) / (2 * np.pi) * NB).astype(int) % NB; zb = np.floor(X[:, 2] / ZB).astype(int); moved = 0
    for i in np.nonzero(dz > 1e-4)[0]:
        rm = rmin.get((zb[i], pb[i]))
        if rm is not None and r[i] < rm:
            k = rm / max(r[i], 1e-6); X[i, 0] *= k; X[i, 1] = cy + (X[i, 1] - cy) * k; moved += 1
    if moved:   # 이웃도 같이 조금씩 밀려 나와 겹이 찢어지지 않게
        D = X - X0; D[:, 2] = 0; Db = blur(kd_of(X0), X0, D, 0.02)
        X[:, :2] = X0[:, :2] + np.where((np.linalg.norm(D, axis=1) > np.linalg.norm(Db, axis=1))[:, None], D, Db)[:, :2]
    dz = X - X0
    me.vertices.foreach_set("co", X.ravel())
    if me.shape_keys:
        for kb in me.shape_keys.key_blocks:
            K = np.empty(len(me.vertices) * 3); kb.data.foreach_get("co", K); K = K.reshape(-1, 3) + dz; kb.data.foreach_set("co", K.ravel())
    me.update()
    return {"z_min_before": round(float(z_start - L), 3), "z_min_after": round(float(X[:, 2].min()), 3), "squeeze": round(float(c), 3), "pushed_out_verts": moved}

# ════════════════════════════════════════════════════════════════════ 1. 쉬는 자세 밀어내기
def push_out(o, bvh, fcls, push_cls, Mh=None, iters=4, sig=0.012):
    """Mh: 부품 집 뼈의 스킨 행렬(그 자세의 몸과 비교, 밀린 만큼은 쉬는 자세 좌표로 되돌려 넣음). None = 쉬는 자세."""
    me = o.data; X0 = np.array([v.co[:] for v in me.vertices]); kd = kd_of(X0)
    Mh = np.eye(4) if Mh is None else Mh; Xp = X0 @ Mh[:3, :3].T + Mh[:3, 3]
    tot = np.zeros_like(X0); ok = np.array([CLASSES.index(c) for c in push_cls])
    for it in range(iters):
        Y = Xp + tot
        sd, nr, fi = signed_near(bvh, Y, 0.15)
        hit = (fi >= 0) & np.isin(np.where(fi >= 0, fcls[np.maximum(fi, 0)], -1), ok) & (sd < CLEAR + 4 * SOFT)
        d = np.zeros_like(X0)
        d[hit] = ((softplus_target(sd[hit]) - sd[hit]))[:, None] * nr[hit]
        if np.abs(d).max(initial=0) < 3e-4: break
        b = blur(kd, X0, d, sig)
        mag_d, mag_b = np.linalg.norm(d, axis=1), np.linalg.norm(b, axis=1)
        tot += np.where((mag_d > mag_b)[:, None], d, b)
    tot = tot @ np.linalg.inv(Mh[:3, :3]).T
    if np.abs(tot).max(initial=0) > 1e-5:
        X1 = X0 + tot
        me.vertices.foreach_set("co", X1.ravel())
        if me.shape_keys:
            for kb in me.shape_keys.key_blocks:
                K = np.empty(len(me.vertices) * 3); kb.data.foreach_get("co", K)
                kb.data.foreach_set("co", (K.reshape(-1, 3) + tot).ravel())
        me.update()
    return float(np.linalg.norm(tot, axis=1).max(initial=0)), int((np.linalg.norm(tot, axis=1) > 1e-3).sum())

# ════════════════════════════════════════════════════════════════════ 2. 뼈 무게 풀기
def skin_mats(arm, names):
    return {n: np.array(arm.matrix_world @ arm.pose.bones[n].matrix @ arm.data.bones[n].matrix_local.inverted() @ arm.matrix_world.inverted()) for n in names}

def apply(arm, body, parts, out_dir=None, log=print, actions=None):
    """parts: 이름 목록 또는 dict(이름→정보). 부품 메시 좌표 = 쉬는 자세 세계 좌표(build_char finish() 그대로)라고 가정."""
    t0 = time.time()
    sc = bpy.context.scene; bones = arm.data.bones; ad = arm.animation_data
    names_all = [n for n in parts if n.startswith(("hair_", "beard_")) or n == "scarf"]
    objs = {n: bpy.data.objects[n] for n in names_all}
    keep_pp = arm.data.pose_position
    arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
    W, wn = body_weights(body, bones)
    fcls = face_classes(body, W, wn, bones)
    P = np.array([v.co[:] for v in body.data.vertices]) @ np.array(body.matrix_world)[:3, :3].T + np.array(body.matrix_world)[:3, 3]
    polys = [list(p.vertices) for p in body.data.polygons]
    bvh0 = BVHTree.FromPolygons([Vector(x) for x in P], polys)
    rep = {}
    # 1) 밀어내기 (목 아래 몸통·다리만. 팔은 쉬는 자세(A자)와 실제 자세가 달라 2)에서)
    for n, o in objs.items():
        assert np.allclose(np.array(o.matrix_world), np.eye(4), atol=1e-5), n + " 쉬는 자세 세계 행렬이 단위가 아님"
        mx, cnt = push_out(o, bvh0, fcls, ("torso", "leg"))
        rep[n] = {"rest_push_max_m": round(mx, 4), "rest_push_verts": cnt}
    # 1b) 서 있는 기본 자세(팔을 내린 자세)에서 한 번 더: 쉬는 자세는 팔을 벌린 A자라 팔 자리가 다름
    if IDLE_POSE[0] in bpy.data.actions:
        a = bpy.data.actions[IDLE_POSE[0]]; keep_act = ad.action; ad.action = a
        try: ad.action_slot = a.slots[0]
        except Exception: pass
        arm.data.pose_position = 'POSE'; sc.frame_set(int(round(a.frame_range[0] + IDLE_POSE[1] * FPS))); bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get(); dg.update()
        bvh_i = BVHTree.FromPolygons([Vector(x) for x in mesh_world(body, dg)], polys)
        Ms = skin_mats(arm, sorted({o.parent_bone or HEAD for o in objs.values()}))
        for n, o in objs.items():
            mx, cnt = push_out(o, bvh_i, fcls, ("torso", "arm", "leg"), Ms[o.parent_bone or HEAD])
            rep[n].update(idle_push_max_m=round(mx, 4), idle_push_verts=cnt)
        ad.action = keep_act; arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
    # 2) 겉면 무게 (팔·손 → 어깨, 다리 → Hips), 부품 안에서 퍼지게
    tgt = sorted({t for n in wn for t in bind_map(bones, n)})
    M = np.zeros((len(wn), len(tgt)))
    for j, n in enumerate(wn):
        for t, k in bind_map(bones, n).items(): M[j, tgt.index(t)] += k
    Wt = W @ M
    # 머리에 달린 부품의 턱 아래 점(수염 아랫부분·늘어진 머리)은 머리 면을 빼고 가장 가까운 몸 면(목 아래)의 무게를 따름
    nh = [i for i in range(len(polys)) if fcls[i] != 0]
    bvh_nh = BVHTree.FromPolygons([Vector(x) for x in P], [polys[i] for i in nh])
    zcut = arm.data.bones[HEAD].head_local.z + 0.06
    arm_z = arm.data.bones["mixamorig:Neck"].head_local.z + 0.03   # 이보다 높은 점은 팔에 밀려도 s를 안 올림
    data = {}
    for n, o in objs.items():
        X = np.array([v.co[:] for v in o.data.vertices]); kd = kd_of(X)
        home = o.parent_bone or HEAD
        Wb = np.zeros((len(X), len(tgt)))
        for i, p in enumerate(X):
            if home == HEAD and p[2] < zcut: loc, nn, f, d = bvh_nh.find_nearest(Vector(p)); f = nh[f]
            else: loc, nn, f, d = bvh0.find_nearest(Vector(p))
            vs = polys[f]; dd = np.linalg.norm(P[vs] - np.array(loc), axis=1); w = 1 / (dd + 1e-4) ** 2
            Wb[i] = (Wt[vs] * w[:, None]).sum(0) / w.sum()
        sig = 0.07 if home == HEAD else 0.04   # 넓게 퍼뜨림: 이웃 가닥이 서로 다른 뼈를 따라가 접히지 않게(목도리는 몸에 감겨 있어 좁게)
        Wb = blur(kd, X, Wb, sig, 2 * sig); Wb /= Wb.sum(1, keepdims=True)
        hi = tgt.index(home) if home in tgt else None
        free = Wb[:, hi] < 0.98 if hi is not None else np.ones(len(X), bool)   # 겉면 무게가 집 뼈와 같으면 s가 소용없음
        data[n] = dict(o=o, X=X, kd=kd, home=home, Wb=Wb, s=np.zeros(len(X)), free=np.nonzero(free)[0], resid=0.0)
    acts = actions or [a for a in bpy.data.actions if any(fc.data_path.startswith("pose.bones") for l in a.layers for s in l.strips for cb in s.channelbags for fc in cb.fcurves)]
    need = sorted(set(tgt) | {d["home"] for d in data.values()})
    arm.data.pose_position = 'POSE'
    keep_act = ad.action if ad else None
    dg = bpy.context.evaluated_depsgraph_get(); nfr = 0
    for a in acts:
        ad.action = a
        try: ad.action_slot = a.slots[0]
        except Exception: pass
        f0, f1 = a.frame_range
        for f in np.arange(f0, f1 + 1e-6, FRAME_STEP * FPS):
            sc.frame_set(int(round(f))); dg.update(); nfr += 1
            X = mesh_world(body, dg); bvh = BVHTree.FromPolygons([Vector(x) for x in X], polys)
            Ms = skin_mats(arm, need)
            for n, d in data.items():
                ix = d["free"]
                if not len(ix): continue
                Xh = np.c_[d["X"][ix], np.ones(len(ix))]
                xh = Xh @ Ms[d["home"]].T
                xb = sum(d["Wb"][ix, j:j + 1] * (Xh @ Ms[t].T) for j, t in enumerate(tgt) if d["Wb"][ix, j].max() > 1e-4)
                xh, xb = xh[:, :3], xb[:, :3]
                s = d["s"]; zr = d["X"][:, 2]
                for k, i in enumerate(ix):
                    while True:
                        y = (1 - s[i]) * xh[k] + s[i] * xb[k]
                        loc, nn, fi, dist = bvh.find_nearest(Vector(y), 0.12)
                        if loc is None or fcls[fi] in (0, 3): break        # 머리(두피·턱)·손은 무게로 못 고침
                        if fcls[fi] == 2 and zr[i] > arm_z: break          # 팔을 머리 높이로 드는 동작(큰 머리 속 팔)은 동작 쪽 문제 → 짧은 머리는 머리 뼈 그대로
                        if (Vector(y) - loc).dot(nn) >= -TOL: break
                        if s[i] >= 1: d["resid"] = max(d["resid"], dist); break
                        s[i] = min(1.0, s[i] + S_STEP)
    log("hairfix frames", nfr, "clips", len(acts), round(time.time() - t0, 1), "s")
    ad.action = keep_act
    arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
    # 3) s 다듬기 → 무게 넣기
    for n, d in data.items():
        o, X, kd, s = d["o"], d["X"], d["kd"], d["s"].copy()
        rep[n].update(s_raw_max=round(float(s.max()), 2), s_raw_verts=int((s > 0).sum()))
        if s.max() <= 0:
            rep[n]["skinned"] = False; continue
        if d["home"] == HEAD:   # 아래로 번지게: 머리끝이 위쪽보다 덜 따라가지 않게
            for i in np.argsort(-X[:, 2]):
                for _, j, _ in kd.find_range(X[i], 0.03):
                    if X[j, 2] < X[i, 2] and s[j] < s[i]: s[j] = s[i]
        sd_ = s.copy()
        for i, p in enumerate(X): sd_[i] = max(s[j] for _, j, _ in kd.find_range(p, 0.04))
        s = np.clip(blur(kd, X, sd_, 0.04), 0, 1)
        hi = np.zeros(len(tgt) + 1); Wf = np.zeros((len(X), len(tgt)))
        hj = tgt.index(d["home"]) if d["home"] in tgt else None
        Wf = s[:, None] * d["Wb"]
        hw = 1 - s
        cols = list(tgt)
        if hj is None: cols.append(d["home"]); Wf = np.c_[Wf, hw]
        else: Wf[:, hj] += hw
        for i in range(len(X)):   # 4개까지
            r = Wf[i]; keep = np.argsort(-r)[:4]; m = np.zeros_like(r); m[keep] = r[keep]; m[m < 0.01] = 0; Wf[i] = m / m.sum()
        to_skin(o, arm, {c: Wf[:, j] for j, c in enumerate(cols) if Wf[:, j].max() > 0})
        rep[n].update(skinned=True, s_max=round(float(s.max()), 2), s_verts=int((s > 0.01).sum()), resid_m=round(d["resid"], 3),
                      bones=sorted(c for j, c in enumerate(cols) if Wf[:, j].max() > 0))
    for pb in arm.pose.bones: pb.matrix_basis = Matrix()
    sc.frame_set(0); arm.data.pose_position = keep_pp; bpy.context.view_layer.update()
    for n in names_all: log("hairfix", n, rep[n])
    if out_dir: json.dump(rep, open(os.path.join(out_dir, "hairfix_report.json"), "w"), ensure_ascii=False, indent=1)
    log("hairfix done", round(time.time() - t0, 1), "s")
    return rep

def to_skin(o, arm, W):
    Wm = o.matrix_world.copy()
    o.parent = arm; o.parent_type = 'OBJECT'; o.parent_bone = ""; bpy.context.view_layer.update(); o.matrix_world = Wm
    for bn, w in W.items():
        g = o.vertex_groups.new(name=bn)
        for i in np.nonzero(w > 0)[0]: g.add([int(i)], float(w[i]), 'REPLACE')
    md = o.modifiers.new("Armature", 'ARMATURE'); md.object = arm

# ════════════════════════════════════════════════════════════════════ 측정(GLB 다시 읽어서)
def _load(glb):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]; body = bpy.data.objects["body"]
    sc = bpy.context.scene; sc.render.fps = FPS; sc.render.fps_base = 1
    ad = arm.animation_data
    for t in ad.nla_tracks: t.mute = True
    return arm, body, ad

def _use(ad, a):
    ad.action = a
    try: ad.action_slot = a.slots[0]
    except Exception: pass

def measure(glb, out_json, step=0.2, every=2):
    t0 = time.time()
    arm, body, ad = _load(glb); sc = bpy.context.scene; bones = arm.data.bones
    W, wn = body_weights(body, bones); fcls = face_classes(body, W, wn, bones)
    polys = [list(p.vertices) for p in body.data.polygons]
    parts = sorted(o.name for o in bpy.data.objects if o.type == 'MESH' and (o.name.startswith(("hair_", "beard_")) or o.name == "scarf"))
    info = {n: {"skinned": any(m.type == 'ARMATURE' for m in bpy.data.objects[n].modifiers), "tris": sum(len(p.vertices) - 2 for p in bpy.data.objects[n].data.polygons),
                "morphs": [k.name for k in bpy.data.objects[n].data.shape_keys.key_blocks[1:]] if bpy.data.objects[n].data.shape_keys else [],
                "mats": [m.name for m in bpy.data.objects[n].data.materials]} for n in parts}
    res = {n: {} for n in parts}
    dg = bpy.context.evaluated_depsgraph_get()
    def frame(tag, t=None):
        X = mesh_world(body, dg); bvh = BVHTree.FromPolygons([Vector(x) for x in X], polys)
        for n in parts:
            Y = mesh_world(bpy.data.objects[n], dg)[::every]
            sd, nr, fi = signed_near(bvh, Y, 0.12)
            inside = (fi >= 0) & (sd < 0)
            r = res[n].setdefault(tag, {})
            for ci, c in enumerate(CLASSES):
                if c == "head": continue
                m = inside & (fcls[np.maximum(fi, 0)] == ci)
                dep = float(-sd[m].min()) if m.any() else 0.0
                if dep > r.get(c, [0, 0])[0]: r[c] = [round(dep, 3), t]
                k = int((m & (sd < -0.01)).sum())
                if k > r.get("n1_" + c, [0, 0])[0]: r["n1_" + c] = [k, t]
            m = inside & np.isin(fcls[np.maximum(fi, 0)], [1, 2, 4]) & (sd < -0.01)   # 몸통·팔·다리에 1 cm 넘게 들어간 점 수(최대)
            r["n_over_1cm"] = max(r.get("n_over_1cm", 0), int(m.sum()))
    arm.data.pose_position = 'REST'; bpy.context.view_layer.update(); dg.update(); frame("REST")
    arm.data.pose_position = 'POSE'
    acts = sorted(bpy.data.actions, key=lambda a: a.name)
    for a in acts:
        _use(ad, a); f0, f1 = a.frame_range
        for f in np.arange(f0, f1 + 1e-6, step * FPS):
            sc.frame_set(int(round(f))); dg.update(); frame(a.name, round(float((f - f0) / FPS), 2))
    out = {"glb": glb, "step_sec": step, "every_nth_vertex": every, "classes": "torso=몸통·목·쇄골, arm=위팔, hand=아래팔·손, leg=다리. 머리(두피·턱)는 뺌",
           "parts": info, "penetration": res, "animations": [[a.name, round((a.frame_range[1] - a.frame_range[0]) / FPS, 3)] for a in acts],
           "bones": len(arm.data.bones), "nodes": sorted(o.name for o in bpy.data.objects), "body_morphs": [k.name for k in body.data.shape_keys.key_blocks[1:]],
           "sec": round(time.time() - t0, 1)}
    json.dump(out, open(out_json, "w"), ensure_ascii=False, indent=1)
    print("MEASURE done", out_json, out["sec"], "s")

# ════════════════════════════════════════════════════════════════════ 비교 렌더
ROWS = [("w_long", ["hair_w_long"]), ("w_wave", ["hair_w_wave"]), ("w_pigtail", ["hair_w_pigtail"]), ("beard_long+scarf", ["hair_m_man50", "beard_long", "scarf"])]
COLS = [("REST", 0), ("Chair_Sit_Idle_F", 5.4), ("Chair_Sit_Idle_F", 10.2), ("Sit_and_Doze_Off", 9.4), ("Sit_and_Doze_Off", 3.4),
        ("Walking", 0.2), ("Sit_and_Drink", 3.4), ("Long_Breathe_and_Look_Around", 1.2), ("Long_Breathe_and_Look_Around", 8.2)]
YAWS = (35, 100)   # 앞 3/4 (팔·가슴·수염) / 옆 (등·어깨)
def render(glb, tag, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    arm, body, ad = _load(glb); sc = bpy.context.scene
    parts = [o for o in bpy.data.objects if o.type == 'MESH' and o is not body]
    sc.render.engine = 'CYCLES'; sc.cycles.samples = 10; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 240, 300; sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    for loc, e in (((-2, -4, 3), 250), ((3, -3, 1), 90), ((0, 4, 2), 120)):
        l = bpy.data.lights.new("k", 'AREA'); l.energy = e; l.size = 4; lo = bpy.data.objects.new("k", l); lo.location = loc; sc.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0, 0, 0.8)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    for m in body.data.materials:   # 몸은 밝은 단색(뚫린 자리 잘 보이게)
        bs = [n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'][0]
        for l in list(bs.inputs["Base Color"].links): m.node_tree.links.remove(l)
        bs.inputs["Base Color"].default_value = {"skin": (0.85, 0.6, 0.45, 1), "top": (0.15, 0.55, 0.9, 1)}.get(m.name, (0.35, 0.37, 0.42, 1))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = 2.2
    for ri, (rn, show, yaw) in enumerate((rn, sh, y) for rn, sh in ROWS for y in YAWS):
        for o in parts: o.hide_render = o.name not in show
        for ci, (clip, t) in enumerate(COLS):
            if clip == "REST": arm.data.pose_position = 'REST'
            else:
                arm.data.pose_position = 'POSE'; _use(ad, bpy.data.actions[clip])
                sc.frame_set(int(round(bpy.data.actions[clip].frame_range[0] + t * FPS)))
            bpy.context.view_layer.update()
            c = np.array(arm.matrix_world @ arm.pose.bones["mixamorig:Neck"].head) if clip != "REST" else np.array(arm.data.bones["mixamorig:Neck"].head_local)
            c[2] -= 0.1
            a = math.radians(yaw); cam.location = (c[0] + 6 * math.sin(a), c[1] - 6 * math.cos(a), c[2]); cam.rotation_euler = (math.pi / 2, 0, a)
            sc.render.filepath = os.path.join(out_dir, f"{tag}_r{ri}_c{ci}.png"); bpy.ops.render.render(write_still=True)
    print("RENDER done", tag)

def sheet(in_dir, out_path):   # 시스템 python3 (PIL). 부품마다 한 장: out_path 의 .jpg 앞에 _부품이름
    from PIL import Image, ImageDraw
    W_, H_ = 240, 300; R = [(rn, y) for rn, _ in ROWS for y in YAWS]; nc = len(COLS)
    for rn0, _ in ROWS:
        rows = [(ri, rn, yaw) for ri, (rn, yaw) in enumerate(R) if rn == rn0]
        S = Image.new("RGB", (nc * W_, len(rows) * 2 * H_ + 30), "white"); dr = ImageDraw.Draw(S)
        for ci, (clip, t) in enumerate(COLS): dr.text((ci * W_ + 4, 8), f"{clip[:24]} {t}s" if clip != "REST" else "REST(bind)", fill="black")
        for k0, (ri, rn, yaw) in enumerate(rows):
            for k, tag in enumerate(("before", "after")):
                y = 30 + (k0 * 2 + k) * H_
                for ci in range(nc):
                    p = os.path.join(in_dir, f"{tag}_r{ri}_c{ci}.png")
                    if os.path.exists(p): S.paste(Image.open(p).convert("RGB"), (ci * W_, y))
                dr.rectangle([0, y, 170, y + 16], fill="white"); dr.text((3, y + 2), f"{rn} {yaw}deg {tag.upper()}", fill="red" if tag == "before" else "green")
        op = out_path.replace(".jpg", f"_{rn0.replace('+', '_')}.jpg"); S.save(op, quality=88); print("SHEET", op)

if __name__ == "__main__":
    av = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if "--measure" in av: i = av.index("--measure"); measure(av[i + 1], av[i + 2])
    elif "--render" in av: i = av.index("--render"); render(av[i + 1], av[i + 2], av[i + 3])
    elif "--sheet" in av: i = av.index("--sheet"); sheet(av[i + 1], av[i + 2])
