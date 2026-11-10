# 도담도담 캐릭터: 보통 비율용 동작을 큰 머리(2.5등신)에 맞게 고치기 — 손·팔뚝·컵이 머리 속으로 들어가지 않게.
#  - 머리 모양: 목 위(Head 뼈 100%) 몸 점 + 얼굴형 모프까지 넣은 '방향별 반지름 표'(쉬는 자세, Head 뼈 기준이라 동작 중에도 그대로)
#  - 프레임마다 팔 점(위팔·팔뚝·손) + 컵(Sit_and_Drink만)을 머리 공간에서 재고, 안쪽이면 작은 2뼈 IK 보정
#    (어깨 관절 회전 3 + 팔꿈치 접기 1, 손은 세계 방향 그대로 → 컵 기울기·손바닥 방향 유지)
#  - 마시기: 컵 테두리를 입 자리(얼굴 그림 v=0.71, Plaza.kt mouth.y) 겉면에 닿게
#  - 보정은 앞뒤 0.2초에 걸쳐 부드럽게 켜고 끔, 반복 동작은 처음·끝 이어짐 유지, 30fps 회전 키에 다시 굽기
#  - 손 드는 동작(RAISE: 손 인사·기지개): 큰 머리 위로는 팔이 못 넘어가니(어깨→머리 꼭대기 0.81 m, 팔+손 0.45 m) 팔을 옆으로 벌려
#    머리·머리카락 겉 바깥에서 최대한 높이(빗장뼈 올림 + 고개를 손 반대쪽으로 조금 기울임), 손바닥은 앞, 손 인사는 원래 동작 박자로 팔뚝 흔들기
#  - 마시기: 마시는 구간은 원래의 고개 젖힘을 붙잡는 자세 고개로 되돌리고 숙이기, 손목은 실제 꺾임(팔뚝 기준)으로 제한, 컵 윗부분·테두리는 입에 닿게
#  - 채널 구성(회전 + Hips 이동)·이름은 그대로, 바뀌는 건 팔(빗장뼈·Arm·ForeArm·Hand)·Head 회전 값뿐(Hips·다리는 그대로)
# 사용: build_char.py 안에서 fix_clips(arm, body, out_acts, FPS, log, centre)  (centre = 기준 머리 중심, 리깅 좌표)
import json, math, os, re
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

HEAD = "mixamorig:Head"
SIDES = {s: tuple(f"mixamorig:{s}{b}" for b in ("Shoulder", "Arm", "ForeArm", "Hand")) for s in ("Left", "Right")}
FACE_PHI, FACE_THETA = 1.8, 1.9; TH0 = math.pi / 2 - FACE_THETA / 2     # build_char.py 7번(얼굴 펼침)과 같게
DRINK_CLAV = 35
MOUTH_V = 0.71                                                           # Plaza.kt 얼굴 JSON mouth.y(그림 위=0)
CLR, CLR_CUP, CLR_MOUTH = 0.02, 0.006, 0.004                            # 머리 겉면에서 띄울 거리(m): 팔·손 / 컵 몸통 / 컵 테두리 ↔ 입(테두리는 입술에 닿게)
CLR_RIM, CLR_DRINK = 0.0025, 0.008                                                         # 컵 테두리 점은 얼굴 겉면 안으로만 안 들어가면 됨
MARGIN = 0.004                                                           # 풀 때 조금 더 띄움(부드럽게 섞을 때 줄어드는 몫)
PAD_SEC, SIGMA_FR = 0.2, 1.5
DRINK_CLIP, HOLD_T, DRINK_TILT, NOD_MAX, WRIST_MAX, YAW_MAX = "Sit_and_Drink", 2.0, 50, 65, 85, 35   # 마실 때 컵 기울기(세로에서 얼굴 쪽으로, 도)
# 손 드는 동작(큰 머리 위로는 팔이 못 넘어감) → 팔을 옆으로 벌려 머리 옆에서: wave = 꼬마 손 인사(팔뚝 위·바깥, 손바닥 앞), v = 두 팔 V자 기지개
RAISE = {"Big_Wave_Hello": "wave", "Sit_Wave": "wave", "Wave_One_Hand": "wave", "Stand_Wave_and_Sit_Down": "wave", "Stretch": "v", "Sit_Stretch": "v"}
RAISE_LO, RAISE_HI = -0.02, 0.14     # 원래 손끝이 어깨 관절보다 이만큼(m, 몸통 위 방향) 높으면 0→1로 켬
SMOOTH = 0.8                         # 손 드는 구간: 이웃 프레임 해와의 차이 벌점(라디안당)
HAND_UP = 0.35                       # 손 방향 = 팔뚝 각도의 이만큼(0 = 똑바로 위, 1 = 팔뚝 따라)
KUP = 4.0                            # 손끝을 머리 꼭대기 높이 쪽으로 끄는 힘(못 닿는 목표 → 머리·머리카락 겉에 막힐 때까지 최대한 높이)
WAVE_EXTRA = 0.035                   # 1차(흔들기 빼고) 풀 때 더 띄울 거리: 팔뚝이 안쪽으로 흔들릴 몫
WAVE_IN, WAVE_OUT = 9, 18            # 팔뚝 흔들기 최대(도): 머리 쪽 / 바깥쪽
CLAV_MAX, ROLL_MAX, RWRIST_MAX = 40, 16, 110   # 손 드는 동작: 빗장뼈 올림·고개 옆으로 기울임(손 반대쪽)·손목 최대(도)


def _fcurves(act):
    for l in act.layers:
        for s in l.strips:
            for cb in s.channelbags:
                yield from cb.fcurves


def _rod(v):
    v = np.asarray(v, float); a = float(np.linalg.norm(v))
    if a < 1e-12: return np.eye(3)
    k = v / a; K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * (K @ K)


def _about(R, p):
    T = np.eye(4); T[:3, :3] = R; T[:3, 3] = p - R @ p; return T


def _q2m(q):   # (n,4) wxyz → (n,3,3)
    w, x, y, z = q.T
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
                     np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
                     np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)


class Rig:
    def __init__(self, arm):
        self.names = [b.name for b in arm.data.bones]
        self.idx = {n: i for i, n in enumerate(self.names)}
        self.par = [self.idx[b.parent.name] if b.parent else -1 for b in arm.data.bones]
        self.L = np.array([np.array(b.matrix_local) for b in arm.data.bones])
        self.Li = np.linalg.inv(self.L)
        self.rel = np.array([self.Li[p] @ self.L[i] if p >= 0 else self.L[i] for i, p in enumerate(self.par)])
        order, seen = [], set()
        def visit(i):
            if i in seen: return
            if self.par[i] >= 0: visit(self.par[i])
            seen.add(i); order.append(i)
        for i in range(len(self.names)): visit(i)
        self.order = order

    def read(self, act):
        tab = {}
        for fc in _fcurves(act):
            m = re.match(r'pose\.bones\["(.+)"\]\.(\w+)', fc.data_path)
            if m: tab.setdefault((m.group(1), m.group(2)), {})[fc.array_index] = fc
        f0, f1 = act.frame_range; n = int(round(f1 - f0)) + 1; fr = f0 + np.arange(n)
        Q = np.zeros((len(self.names), n, 4)); Q[..., 0] = 1; Lc = np.zeros((len(self.names), n, 3))
        for (bn, prop), fcs in tab.items():
            if bn not in self.idx: continue
            i = self.idx[bn]
            for k, fc in fcs.items():
                kp = fc.keyframe_points; co = np.empty(len(kp) * 2); kp.foreach_get("co", co); co = co.reshape(-1, 2)
                vals = co[:, 1] if len(co) == n and np.allclose(co[:, 0], fr) else np.array([fc.evaluate(float(f)) for f in fr])
                if prop == "rotation_quaternion": Q[i, :, k] = vals
                elif prop == "location": Lc[i, :, k] = vals
        Q /= np.linalg.norm(Q, axis=2, keepdims=True)
        return dict(tab=tab, Q=Q, loc=Lc, n=n, fr=fr)

    def fk(self, Q, loc):
        nb, n = Q.shape[:2]
        B = np.tile(np.eye(4), (nb, n, 1, 1)); B[:, :, :3, :3] = _q2m(Q.reshape(-1, 4)).reshape(nb, n, 3, 3); B[:, :, :3, 3] = loc
        M = np.zeros_like(B)
        for i in self.order:
            p = self.par[i]
            M[i] = (M[p] @ self.rel[i] @ B[i]) if p >= 0 else (self.rel[i] @ B[i])
        return M


class HeadShape:
    """Head 뼈를 쉬는 자세로 되돌린 공간에서, 중심 c 기준 방향별 겉면 반지름(얼굴형 모프로 커지는 몫 포함)."""
    NT, NP = 72, 144

    def __init__(self, body, rest_X, headw, centre, extra=None):
        hv = np.nonzero(headw > 0.98)[0]; X = rest_X[hv]
        self.c = np.asarray(centre, float) if centre is not None else (X.min(0) + X.max(0)) / 2
        rr = np.linalg.norm(X - self.c, axis=1)
        if body.data.shape_keys:
            for kb in body.data.shape_keys.key_blocks[1:]:
                if not kb.name.startswith("face_"): continue
                S = np.empty(len(kb.data) * 3); kb.data.foreach_get("co", S); S = S.reshape(-1, 3)[hv]
                rr = np.maximum(rr, np.linalg.norm(S - self.c, axis=1))
        th = (np.arange(self.NT) + 0.5) / self.NT * math.pi; ph = np.arange(self.NP) / self.NP * 2 * math.pi - math.pi
        T, P = np.meshgrid(th, ph, indexing="ij")
        D = np.stack([np.sin(T) * np.cos(P), np.sin(T) * np.sin(P), np.cos(T)], -1).reshape(-1, 3)

        def table(Y, ry):
            U = (Y - self.c) / np.linalg.norm(Y - self.c, axis=1, keepdims=True); cosc = math.cos(math.radians(9)); tab = np.zeros(len(D))
            for s in range(0, len(D), 1024):
                tab[s:s + 1024] = np.where(D[s:s + 1024] @ U.T > cosc, ry[None, :], 0).max(1)
            return tab.reshape(self.NT, self.NP)
        self.tab = table(X, rr); self.rmed = float(np.median(rr))
        if extra is not None and len(extra):   # 머리카락·수염 겉(쉬는 자세): 머리 겉에서 HAIR_CAP 까지만 더 부풀림
            tx = table(extra, np.linalg.norm(extra - self.c, axis=1))
            self.tab = np.maximum(self.tab, np.minimum(tx, self.tab + HAIR_CAP))
        self.rmax = float(self.tab.max())
        self.bvh = BVHTree.FromPolygons([Vector(x) for x in rest_X], [list(p.vertices) for p in body.data.polygons
                                                                       if all(headw[i] > 0.98 for i in p.vertices)])

    def radius(self, d):   # d (k,3) 중심 기준 벡터 → 그 방향 겉면 반지름 (겹선형)
        r = np.linalg.norm(d, axis=1) + 1e-12
        th = np.arccos(np.clip(d[:, 2] / r, -1, 1)) / math.pi * self.NT - 0.5
        ph = (np.arctan2(d[:, 1], d[:, 0]) + math.pi) / (2 * math.pi) * self.NP
        t0 = np.clip(np.floor(th), 0, self.NT - 1).astype(int); t1 = np.clip(t0 + 1, 0, self.NT - 1); ft = np.clip(th - t0, 0, 1)
        p0 = np.floor(ph).astype(int) % self.NP; p1 = (p0 + 1) % self.NP; fp = ph - np.floor(ph)
        a = self.tab[t0, p0] * (1 - fp) + self.tab[t0, p1] * fp; b = self.tab[t1, p0] * (1 - fp) + self.tab[t1, p1] * fp
        return a * (1 - ft) + b * ft, r

    def gap(self, p):     # 쉬는 머리 공간 점들 → 겉면까지 거리(+ 바깥, - 안쪽)
        R, r = self.radius(p - self.c); return r - R

    def mouth(self):
        th = TH0 + MOUTH_V * FACE_THETA; d = Vector((0.0, -math.sin(th), math.cos(th)))
        loc, n, _, _ = self.bvh.ray_cast(Vector(self.c), d)
        if loc is None: loc = Vector(self.c) + d * self.rmed; n = d
        return np.array(loc[:]), np.array(n.normalized()[:])


def fix_clips(arm, body, actions, fps=30, log=print, centre=None, out_dir=None, clr=CLR):
    t_start = __import__("time").time()
    rig = Rig(arm); I = rig.idx
    Ma_w = np.array(arm.matrix_world); Mb = np.linalg.inv(Ma_w) @ np.array(body.matrix_world)
    me = body.data; nv = len(me.vertices)
    X = np.empty(nv * 3); me.vertices.foreach_get("co", X); X = X.reshape(-1, 3) @ Mb[:3, :3].T + Mb[:3, 3]
    vgn = {g.index: g.name for g in body.vertex_groups}
    Wd = {}
    for v in me.vertices:
        for g in v.groups:
            if g.weight > 1e-4 and vgn[g.group] in I: Wd.setdefault(vgn[g.group], np.zeros(nv))[v.index] = g.weight
    tot = sum(Wd.values()); Wd = {k: w / np.maximum(tot, 1e-9) for k, w in Wd.items()}
    hs = HeadShape(body, X, Wd.get(HEAD, np.zeros(nv)), centre)      # 맨 머리(컵·턱-가슴)
    hair, beard = _envelope(arm, Ma_w, hs)
    hs_env = HeadShape(body, X, Wd.get(HEAD, np.zeros(nv)), centre, np.vstack([hair, beard]))   # 팔·손: 머리 + 부피 큰 머리카락·긴 수염
    hs_env_nb = HeadShape(body, X, Wd.get(HEAD, np.zeros(nv)), centre, hair)                  # 마시는 손: 수염 빼고(컵이 입에 닿아야 해서)
    mouth_p, mouth_n = hs.mouth(); target = mouth_p + mouth_n * CLR_MOUTH
    nh = np.array([mouth_n[0], mouth_n[1], 0.0]); nh /= np.linalg.norm(nh)
    cup_axis = np.array([0, 0, 1.0]) * math.cos(math.radians(DRINK_TILT)) - nh * math.sin(math.radians(DRINK_TILT))   # 쉬는 머리 공간에서 컵 바닥→입구
    log("clipfix head r median %.3f max %.3f, +hair max %.3f, mouth" % (hs.rmed, hs.rmax, hs_env.rmax), np.round(mouth_p, 3), "envelope pts", len(hair), len(beard))
    hi = I[HEAD]
    Xh = X[Wd.get(HEAD, np.zeros(nv)) > 0.98]; isp = I["mixamorig:Spine2"]; sp_z = rig.L[isp][2, 3]
    head_bot, head_top = float(Xh[:, 2].min()), float(Xh[:, 2].max())

    # 팔 점(쉬는 자세에서 이미 머리 근처인 점은 뺌)
    side_pts = {}
    for s, (bsh, ba, bf, bh) in SIDES.items():
        wa = sum(Wd.get(b, 0) for b in (ba, bf, bh))
        sel = np.nonzero(wa > 0.5)[0]
        sel = sel[hs_env.gap(X[sel]) > clr + 0.03]
        if len(sel) > 240: sel = sel[np.linspace(0, len(sel) - 1, 240).astype(int)]
        used = [b for b in Wd if Wd[b][sel].max() > 1e-4]
        side_pts[s] = dict(v=np.column_stack([X[sel], np.ones(len(sel))]), w=np.stack([Wd[b][sel] for b in used], 1),
                           bones=[I[b] for b in used], hand=Wd.get(bh, np.zeros(nv))[sel] > 0.5)
        # 손끝·손바닥 방향(손 뼈 기준): 손 뼈 + 그 아래 손가락 뼈 무게가 반 넘는 점
        ihb = I[bh]; sub = [i for i in range(len(rig.names)) if _under(rig, i, ihb)]
        hw_ = sum(Wd.get(rig.names[i], 0) for i in sub); hv_ = np.nonzero(hw_ > 0.5)[0]
        Pl = (rig.Li[ihb] @ np.column_stack([X[hv_], np.ones(len(hv_))]).T).T[:, :3]
        tip = Pl[Pl[:, 1] > np.percentile(Pl[:, 1], 92)].mean(0)
        Cc = (Pl - Pl.mean(0))[:, [0, 2]]; e2 = np.linalg.eigh(Cc.T @ Cc)[1][:, 0]; pn = np.array([e2[0], 0.0, e2[1]])   # 가장 얇은 방향 = 손바닥 법선
        if (rig.L[ihb][:3, :3] @ pn)[2] > 0: pn = -pn                  # 쉬는 자세(A자)에서 손바닥은 아래(안쪽)를 봄
        side_pts[s]["tip4"] = np.append(tip, 1.0); side_pts[s]["palm"] = pn
        log("clipfix hand", s, "tip", np.round(tip, 3), "palm(local)", np.round(pn, 2), "palm(rest world)", np.round(rig.L[ihb][:3, :3] @ pn, 2))
    # 컵: RightHand 뼈에 붙은 소품(쉬는 자세 좌표 → 손 뼈 기준)
    cup = None
    if "prop_cup" in __import__("bpy").data.objects:
        import bpy
        o = bpy.data.objects["prop_cup"]; pp = arm.data.pose_position; arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
        Mo = np.linalg.inv(Ma_w) @ np.array(o.matrix_world); V = np.array([v.co[:] for v in o.data.vertices])
        V = V @ Mo[:3, :3].T + Mo[:3, 3]; arm.data.pose_position = pp; bpy.context.view_layer.update()
        if len(V) > 200: V = V[np.linspace(0, len(V) - 1, 200).astype(int)]
        cup = dict(v_hl=(rig.Li[I["mixamorig:RightHand"]] @ np.column_stack([V, np.ones(len(V))]).T).T)

    acts = {a.name: a for a in actions}
    data = {nm: rig.read(a) for nm, a in acts.items()}
    # 팔꿈치 접는 축(팔뚝 뼈 기준): 모든 동작의 팔뚝 회전축 주성분, 각도 범위
    hinge, flex_rng = {}, {}
    for s, (bsh, ba, bf, bh) in SIDES.items():
        rv = []
        for d in data.values():
            for q in d["Q"][I[bf]][::3]:
                qq = Quaternion(q); ax, an = qq.to_axis_angle()
                if an > math.pi: an -= 2 * math.pi
                rv.append(np.array(ax[:]) * an)
        rv = np.array(rv); h = np.linalg.svd(rv, full_matrices=False)[2][0]
        ang = rv @ h
        if np.median(ang) < 0: h = -h; ang = -ang
        hinge[s] = h; flex_rng[s] = (float(np.percentile(ang, 0.5)) - math.radians(5), float(np.percentile(ang, 99.5)) + math.radians(8))
    log("clipfix elbow hinge", {s: (np.round(h, 2).tolist(), [round(math.degrees(x)) for x in flex_rng[s]]) for s, h in hinge.items()})

    # 컵 위쪽 = Sit_and_Drink 붙잡는 자세에서 세계 위(+Z)
    if cup is not None and DRINK_CLIP in data:
        d = data[DRINK_CLIP]; M = rig.fk(d["Q"], d["loc"]); f = min(d["n"] - 1, int(round(HOLD_T * fps)))
        up = M[I["mixamorig:RightHand"], f, :3, :3].T @ np.array([0, 0, 1.0])
        h = cup["v_hl"][:, :3] @ up; cup["rim"] = h > h.max() - 0.12 * (h.max() - h.min()); cup["up"] = up / np.linalg.norm(up)
        hn = (h - h.min()) / (h.max() - h.min()); cup["thr"] = np.where(cup["rim"], CLR_RIM, np.where(hn > 0.6, 0.003, CLR_CUP))   # 입 쪽 윗부분은 얼굴 가까이 와도 됨

    report = {}
    ihd = I[HEAD]; ineck = rig.par[ihd]
    tw = [b for b in ("mixamorig:Spine1", "mixamorig:Spine2") if b in Wd]
    tsel = np.nonzero(sum(Wd[b] for b in tw) > 0.6)[0]; tsel = tsel[hs.gap(X[tsel]) > 0.03]
    tsel = tsel[np.linspace(0, len(tsel) - 1, min(len(tsel), 120)).astype(int)]
    torso = dict(v=np.column_stack([X[tsel], np.ones(len(tsel))]), w=np.stack([Wd[b][tsel] for b in tw], 1), bones=[I[b] for b in tw])
    for nm, a in acts.items():
        d = data[nm]; n = d["n"]; Q = d["Q"].copy(); M = rig.fk(Q, d["loc"])
        loop = n > 2 and np.abs(np.abs(np.einsum("bk,bk->b", Q[:, 0], Q[:, -1])) - 1).max() < 1e-4
        rec = {}
        for s in ("Right", "Left"):
            bsh, ba, bf, bh = SIDES[s]
            M = rig.fk(Q, d["loc"]); Hinv = np.linalg.inv(M[ihd] @ rig.Li[ihd])     # 세계 → 쉬는 머리 공간 (n,4,4)
            sp = side_pts[s]; ia, if_, ih = I[ba], I[bf], I[bh]
            use_cup = cup is not None and s == "Right" and nm == DRINK_CLIP
            mode = None if use_cup else RAISE.get(nm)
            ha = hs_env_nb if use_cup else hs_env
            K = 12 if use_cup else (13 if mode else 4)     # 어깨 3 + 팔꿈치 1 (+ 마시기: 고개 숙이기 1 + 손목 3 — 컵 입구가 입 쪽을 보게 + 빗장뼈 3) (+ 손 들기: 고개 옆 기울임)
            free = np.array([j not in ((4, 11) if mode == "wave" else (4, 11, 12)) for j in range(K)]) if mode else None
            ish = I[bsh]
            fixed = [b for b in sp["bones"] if b not in (ia, if_, ih)]
            phi0 = np.array([_signed_angle(q, hinge[s]) for q in Q[if_]])

            def pose(f, x):
                Msh, Ma, Mf, Mh = M[ish, f], M[ia, f], M[if_, f], M[ih, f]
                if len(x) > 8:   # 빗장뼈(어깨를 앞·위로)
                    Tc = _about(_rod(x[8:11]), Msh[:3, 3]); Msh, Ma, Mf = Tc @ Msh, Tc @ Ma, Tc @ Mf; Mh = Tc @ Mh
                Ta = _about(_rod(x[:3]), Ma[:3, 3]); Mf2 = Ta @ Mf
                ax = Mf2[:3, :3] @ hinge[s]; Te = _about(_rod(ax * x[3]), Mf2[:3, 3])
                Mh2 = Te @ Ta @ Mh; Mh2[:3, :3] = Mh[:3, :3]
                if len(x) > 5: Mh2 = _about(_rod(x[5:8]), Mh2[:3, 3]) @ Mh2
                Mhd = M[ihd, f]
                if len(x) > 4:   # 고개: 숙이기(뼈 X축) + 컵 쪽으로 돌리기(뼈 Y축)
                    yv = Mhd[:3, 1] / np.linalg.norm(Mhd[:3, 1]); xv = Mhd[:3, 0] / np.linalg.norm(Mhd[:3, 0])
                    zv = Mhd[:3, 2] / np.linalg.norm(Mhd[:3, 2])
                    Mhd = _about(_rod(xv * x[4]) @ _rod(yv * (x[11] if len(x) > 11 else 0.0)) @ _rod(zv * (x[12] if len(x) > 12 else 0.0)), Mhd[:3, 3]) @ Mhd
                return Ta @ Ma, Te @ Mf2, Mh2, Mhd, Msh

            def skin(pts, f, S):
                P = np.zeros((len(pts["v"]), 3))
                for j, b in enumerate(pts["bones"]): P += pts["w"][:, j:j + 1] * (pts["v"] @ (S[b] if b in S else M[b, f] @ rig.Li[b]).T)[:, :3]
                return P

            def points(f, mats):
                S = {ia: mats[0] @ rig.Li[ia], if_: mats[1] @ rig.Li[if_], ih: mats[2] @ rig.Li[ih], ish: mats[4] @ rig.Li[ish]}
                Hi = Hinv[f] if len(mats) < 4 or mats[3] is M[ihd, f] else np.linalg.inv(mats[3] @ rig.Li[ihd])
                P = skin(sp, f, S) @ Hi[:3, :3].T + Hi[:3, 3]
                C = T = None
                if use_cup:
                    C = (cup["v_hl"] @ (Hi @ mats[2]).T)[:, :3]
                    T = skin(torso, f, {}) @ Hi[:3, :3].T + Hi[:3, 3]
                return P, C, T

            def measure(f, x):
                P, C, T = points(f, pose(f, x)); g = ha.gap(P)
                return (float(g.min()), (float((hs.gap(C) - cup["thr"]).min()) + CLR_CUP if C is not None else 9.0), float(g[sp["hand"]].min()) if sp["hand"].any() else 9.0,
                        float(hs.gap(P).min()))

            g0 = np.array([measure(f, np.zeros(K)) for f in range(n)])
            need = (g0[:, 0] < clr) | (g0[:, 1] < CLR_CUP)
            wt = np.zeros(n); wr = np.zeros(n); st = dict(ext=0.0, abase=None, wfull=False, xnb=None)
            if mode:   # 손 드는 구간(원래 손끝이 어깨보다 높을 때) + 몸통 방향(위·앞·바깥)
                sgn = -1.0 if s == "Right" else 1.0
                Rsp = M[isp][:, :3, :3] @ rig.Li[isp][:3, :3]; psp = M[isp][:, :3, 3]
                U, Fw, Ow = Rsp @ np.array([0, 0, 1.0]), Rsp @ np.array([0, -1.0, 0]), Rsp @ np.array([sgn, 0, 0])
                tip0 = (M[ih] @ sp["tip4"])[:, :3]
                h = np.einsum("nk,nk->n", tip0 - M[ia][:, :3, 3], U)
                wr = _gs(_smooth01((h - RAISE_LO) / (RAISE_HI - RAISE_LO)), 5, loop); wr[wr < 0.02] = 0
                fa0 = M[ih][:, :3, 3] - M[if_][:, :3, 3]; fa0 /= np.linalg.norm(fa0, axis=1, keepdims=True)
                hd0 = M[ih][:, :3, 1] / np.linalg.norm(M[ih][:, :3, 1], axis=1, keepdims=True)
                a0 = np.unwrap(np.arctan2(np.einsum("nk,nk->n", fa0, Ow), np.einsum("nk,nk->n", fa0, U)))
                ah = np.unwrap(np.arctan2(np.einsum("nk,nk->n", hd0, Ow), np.einsum("nk,nk->n", hd0, U))) - a0
                pj = np.clip(np.minimum(np.hypot(np.einsum("nk,nk->n", fa0, Ow), np.einsum("nk,nk->n", fa0, U)),
                                        np.hypot(np.einsum("nk,nk->n", hd0, Ow), np.einsum("nk,nk->n", hd0, U))) / 0.7, 0, 1)   # 팔뚝·손이 앞을 가리키면 옆 각도가 불안정 → 흔들기 약하게
                osc = _gs(np.clip(a0 - _gs(a0, 8, loop), -math.radians(WAVE_IN), math.radians(WAVE_OUT)) * pj, 1.5, loop) if mode == "wave" else np.zeros(n)
                dh = _gs(np.clip(ah - _gs(ah, 8, loop), -0.5, 0.5) * pj, 1.5, loop) if mode == "wave" else np.zeros(n)
                ztop = head_top - sp_z
                need |= wr > 0
            if use_cup:   # 마시는 구간 = 원래 손·컵이 얼굴 속 깊이(4cm 넘게) 들어간 때, 앞뒤 0.4초에 걸쳐 입 맞추기를 켜고 끔
                core = np.nonzero(np.minimum(g0[:, 1], g0[:, 2]) < -0.04)[0]
                if len(core):
                    for f in range(n):
                        dist = np.abs(core - f).min(); t = float(np.clip(1 - dist / 12.0, 0, 1)); wt[f] = t * t * (3 - 2 * t)
                need |= wt > 0
                # 원래 동작은 마실 때 고개를 뒤로 젖힘(보통 몸 기준) → 큰 머리에선 입이 컵에서 멀어짐: 마시는 구간은 붙잡는 자세의 고개로 되돌린 뒤 숙이기
                fh = min(n - 1, int(round(HOLD_T * fps))); qh = Q[ihd, fh].copy(); tilt = []
                for f in np.nonzero(wt > 0)[0]:
                    q0 = Quaternion(Q[ihd, f]); q1 = Quaternion(qh); tilt.append(math.degrees(q0.rotation_difference(q1).angle) * wt[f])
                    q = q0.slerp(q1, float(wt[f])); Q[ihd, f] = [q.w, q.x, q.y, q.z]
                M = rig.fk(Q, d["loc"]); Hinv = np.linalg.inv(M[ihd] @ rig.Li[ihd])
                log("clipfix drink head back-tilt removed (deg, max)", round(max(tilt), 1))
            clr_f = np.full(n, clr) - (clr - CLR_DRINK) * wt   # 마실 땐 컵 쥔 손이 턱·뺨 가까이 와도 됨
            if not need.any():
                rec[s] = dict(before=_stat(g0), after=_stat(g0), frames=0, worst_sec_before=round(float(np.argmin(g0[:, 0])) / fps, 2)); continue
            REG = np.array([0.35, 0.35, 0.35, 0.25, 0.5, 0.3, 0.3, 0.3, 0.5, 0.5, 0.5, 0.5, 0.5][:K])

            def resid(f, x, xref, pen=1.0):
                mats = pose(f, x); P, C, T = points(f, mats)
                r = [np.maximum(0, clr_f[f] + MARGIN + st["ext"] * wr[f] - ha.gap(P)) * 60 * pen]
                if mode and wr[f] > 0:
                    w_ = 1.0 if st["wfull"] else wr[f]; Ma2, Mf2, Mh2 = mats[0], mats[1], mats[2]
                    tw = (Mh2 @ sp["tip4"])[:3]
                    r.append([KUP * w_ * (ztop - (tw - psp[f]) @ U[f])])                       # 손끝 높이 → 머리 꼭대기 쪽으로
                    r.append((Mh2[:3, :3] @ sp["palm"] - Fw[f]) * 1.0 * w_)                     # 손바닥 앞(카메라)
                    fa = Mh2[:3, 3] - Mf2[:3, 3]; fa /= np.linalg.norm(fa); ua = Mf2[:3, 3] - Ma2[:3, 3]; ua /= np.linalg.norm(ua)
                    r.append(np.array([fa @ Fw[f], ua @ Fw[f]]) * 0.6 * w_)                     # 팔은 몸 옆 평면에
                    af = math.atan2(fa @ Ow[f], fa @ U[f]); th = HAND_UP * af + dh[f]   # 손은 세워서(팔이 비스듬해도 손끝은 위로) — 꼬마 손 인사
                    hd = Mh2[:3, 1] / np.linalg.norm(Mh2[:3, 1])
                    r.append((hd - (math.cos(th) * U[f] + math.sin(th) * Ow[f])) * 0.8 * w_)    # 손가락은 팔뚝 따라(흔들 땐 손목도 조금)
                    if st["xnb"] is not None: r.append((x - st["xnb"]) * SMOOTH)                   # 앞 프레임과 이어지게(다른 갈래로 튀지 않게)
                    if st["abase"] is not None: r.append([((af - st["abase"][f] - osc[f] + math.pi) % (2 * math.pi) - math.pi) * 2.0 * w_])   # 팔뚝 좌우 흔들기(원래 동작 박자)
                    if mode == "v": r.append([(phi0[f] + x[3] - flex_rng[s][0] - math.radians(12)) * 0.5 * w_])   # 기지개: 팔꿈치 펴기
                    r.append(np.array([max(0, np.linalg.norm(x[8:11]) - math.radians(CLAV_MAX)), max(0, np.linalg.norm(x[5:8]) - math.radians(RWRIST_MAX)),
                                       max(0, abs(x[12]) - math.radians(ROLL_MAX))]) * 20)
                if C is not None:
                    r.append(np.maximum(0, cup["thr"] + MARGIN - hs.gap(C)) * 60 * pen)
                    r.append(np.maximum(0, 0.01 - hs.gap(T)) * 60 * pen)       # 고개 숙여도 턱이 가슴에 안 닿게
                    if wt[f] > 0:
                        rim = C[cup["rim"]]; k = np.argmin(np.linalg.norm(rim - target, axis=1))
                        r.append((rim[k] - target) * 40 * wt[f])
                        Hi = np.linalg.inv(mats[3] @ rig.Li[ihd]); ax_ = Hi[:3, :3] @ mats[2][:3, :3] @ cup["up"]
                        r.append((ax_ - cup_axis) * 1.0 * wt[f])        # 컵 입구가 입 쪽(뒤·위)을 보게 기울임
                    r.append(np.array([max(0, -math.radians(5) - x[4]), max(0, x[4] - math.radians(NOD_MAX)),
                                       max(0, np.linalg.norm(x[8:11]) - math.radians(DRINK_CLAV)), max(0, _wrist_angle(mats[1], mats[2], rig.rel[ih]) - math.radians(WRIST_MAX)),
                                       max(0, abs(x[11]) - math.radians(YAW_MAX))]) * 20)
                phi = phi0[f] + x[3]; lo, hi_ = flex_rng[s]
                r.append(np.array([max(0, lo - phi), max(0, phi - hi_), max(0, np.linalg.norm(x[:3]) - math.radians(150 if mode else SHOULDER_MAX))]) * 20)
                r.append((x - xref) * REG * (1 - 0.85 * (1.0 if st["wfull"] and wr[f] > 0 else wr[f])))
                return np.concatenate(r)

            Xs = np.zeros((n, K)); xprev = np.zeros(K)
            if mode == "wave": st["ext"] = WAVE_EXTRA   # 1차: 흔들기 없이, 안쪽으로 흔들 몫만큼 더 띄워서
            order = list(range(n))
            if mode:   # 손이 가장 높은 프레임에서 여러 시작점(팔을 옆으로 벌린 자세들)으로 풀고 → 앞뒤로 이어 풀기(머리 앞쪽 국소해 피함)
                pk = int(np.argmax(wr)); order = [pk] + list(range(pk + 1, n)) + list(range(pk - 1, -1, -1))
                def canon(f, el, eb=None):
                    ua0 = M[if_, f][:3, 3] - M[ia, f][:3, 3]; ua0 /= np.linalg.norm(ua0)
                    ut = Ow[f] * math.cos(math.radians(el)) + U[f] * math.sin(math.radians(el))
                    ax = np.cross(ua0, ut); sn = np.linalg.norm(ax); x0 = np.zeros(K)
                    if sn > 1e-6: x0[:3] = ax / sn * math.atan2(sn, ua0 @ ut)
                    if eb is not None: x0[3] = math.radians(eb) - phi0[f]          # 팔꿈치도 거의 편 자세에서
                    return x0
                fun = lambda x: resid(pk, x, np.zeros(K))
                sols = [_lm(fun, c0, 40, free=free) for c0 in [np.zeros(K)] + [canon(pk, e, eb) for e in (10, 30, 50) for eb in (None, 15, 45)]]
                cost = [float(fun(x_) @ fun(x_)) for x_ in sols]
                xprev = sols[int(np.argmin(cost))]
                log("clipfix raise start", nm, s, "costs", np.round(cost, 2).tolist())
                st["wfull"] = True   # 손 드는 구간은 끝까지 다 든 자세로 풀고(같은 갈래 유지) → 나중에 wr 만큼만 섞음(들고 내리는 사이 튐 방지)
            for f in order:
                if mode and f == pk - 1: xprev = Xs[pk]
                if not need[f]: continue
                st["xnb"] = xprev if (mode and f != pk) else None
                xa = _lm(lambda x: resid(f, x, np.zeros(K)), xprev, free=free)
                if wt[f] > 0:   # 컵이 턱 밑에 걸리는 국소해를 피하려고: 먼저 입만 보고 풀고 → 거기서 뚫림까지 넣어 다시
                    xb = _lm(lambda x: resid(f, x, np.zeros(K)), _lm(lambda x: resid(f, x, np.zeros(K), 0.0), xprev))
                    ca, cb_ = resid(f, xa, np.zeros(K)), resid(f, xb, np.zeros(K))
                    if cb_ @ cb_ < ca @ ca: xa = xb
                Xs[f] = xprev = xa
            if mode: Xs[wr > 0] *= wr[wr > 0][:, None]; st["wfull"] = False; st["xnb"] = None
            Xs = _blend(Xs, need, int(round(PAD_SEC * fps)), loop)
            if mode == "wave":   # 2차: 1차 팔뚝 각도(부드럽게)를 기준으로 원래 동작의 흔들기를 얹어 다시
                ab = np.zeros(n)
                for f in range(n):
                    m_ = pose(f, Xs[f]); fa = m_[2][:3, 3] - m_[1][:3, 3]; ab[f] = math.atan2(fa @ Ow[f], fa @ U[f])
                st["abase"] = _gs(np.unwrap(ab), 6, loop); st["ext"] = 0.0
                X0_ = Xs.copy()
                for f in np.nonzero(wr > 0)[0]:
                    st["xnb"] = Xs[f - 1] if f > 0 and wr[f - 1] > 0 else None
                    Xs[f] = _lm(lambda x: resid(f, x, X0_[f]), Xs[f], free=free)
                st["xnb"] = None
                Xs = _blend(Xs, need, int(round(PAD_SEC * fps)), loop)
            # 섞은 뒤 아직 닿는 프레임은 그 값에서 다시 풀고 한 번 더 섞기
            for it in range(3):
                g1 = np.array([measure(f, Xs[f]) for f in range(n)])
                bad = (g1[:, 0] < clr_f - 0.002) | (g1[:, 1] < CLR_CUP - 0.002)
                if not bad.any(): break
                for f in np.nonzero(bad)[0]:
                    if mode and wr[f] > 0: st["xnb"] = (Xs[max(f - 1, 0)] + Xs[min(f + 1, n - 1)]) / 2
                    Xs[f] = _lm(lambda x: resid(f, x, Xs[f]), Xs[f], free=free); st["xnb"] = None
                Xs = _blend(Xs, need | bad, int(round(PAD_SEC * fps)), loop)
            g1 = np.array([measure(f, Xs[f]) for f in range(n)])
            # 회전 키로 굽기
            for f in range(n):
                if not np.any(Xs[f]): continue
                Ma2, Mf2, Mh2, Mhd2, Msh2 = pose(f, Xs[f])
                if K > 8: Q[ish, f] = _m2q((np.linalg.inv(M[rig.par[ish], f] @ rig.rel[ish]) @ Msh2)[:3, :3])
                Q[ia, f] = _m2q((np.linalg.inv(Msh2 @ rig.rel[ia]) @ Ma2)[:3, :3])
                Q[if_, f] = _m2q((np.linalg.inv(Ma2 @ rig.rel[if_]) @ Mf2)[:3, :3])
                Q[ih, f] = _m2q((np.linalg.inv(Mf2 @ rig.rel[ih]) @ Mh2)[:3, :3])
                if K > 4: Q[ihd, f] = _m2q((np.linalg.inv(M[ineck, f] @ rig.rel[ihd]) @ Mhd2)[:3, :3])
            spd = [0.0, 0.0]   # 바뀐 뼈의 한 프레임 회전 최대(도) — 원래 / 고친 뒤 (튐 확인)
            for b in (ia, if_, ih) + ((ihd, ish) if K > 4 else ()):
                for f in range(1, n):
                    if np.dot(Q[b, f], Q[b, f - 1]) < 0: Q[b, f] = -Q[b, f]
                for k_, QQ in enumerate((d["Q"][b], Q[b])):
                    spd[k_] = max(spd[k_], float(np.degrees(2 * np.arccos(np.clip(np.abs(np.sum(QQ[1:] * QQ[:-1], 1)), 0, 1))).max()))
                _write(arm, a, d, rig.names[b], Q[b])
            on = np.nonzero(np.abs(Xs).sum(1) > 1e-6)[0]
            rec[s] = dict(before=_stat(g0), after=_stat(g1), frames=int(len(on)), worst_sec_before=round(float(np.argmin(np.minimum(g0[:, 0], g0[:, 1]))) / fps, 2),
                          sec=[round(on[0] / fps, 2), round(on[-1] / fps, 2)] if len(on) else [],
                          max_shoulder_deg=round(math.degrees(float(np.linalg.norm(Xs[:, :3], axis=1).max())), 1),
                          max_elbow_deg=round(math.degrees(float(np.abs(Xs[:, 3]).max())), 1),
                          max_step_deg_before_after=[round(spd[0], 1), round(spd[1], 1)])
            if mode and (wr > 0.5).any():
                hs_ = []; pal = []
                for f in np.nonzero(wr > 0.5)[0]:
                    m_ = pose(f, Xs[f]); tw = (m_[2] @ sp["tip4"])[:3]; hs_.append((tw - psp[f]) @ U[f] + sp_z)
                    pal.append(float((m_[2][:3, :3] @ sp["palm"]) @ Fw[f]))
                hs_ = np.array(hs_); f0_ = np.nonzero(wr > 0.5)[0]
                h_before = np.array([(tip0[f] - psp[f]) @ U[f] + sp_z for f in f0_])
                rec[s]["raise"] = dict(mode=mode, sec=[round(f0_[0] / fps, 2), round(f0_[-1] / fps, 2)],
                                       hand_tip_height_frac_of_head_med_max=[round(float((np.median(hs_) - head_bot) / (head_top - head_bot)), 2), round(float((hs_.max() - head_bot) / (head_top - head_bot)), 2)],
                                       before_frac_med_max=[round(float((np.median(h_before) - head_bot) / (head_top - head_bot)), 2), round(float((h_before.max() - head_bot) / (head_top - head_bot)), 2)],
                                       palm_forward_dot_med=round(float(np.median(pal)), 2),
                                       wave_swing_deg=round(math.degrees(float(np.ptp(osc[wr > 0.5]))), 1) if mode == "wave" else 0,
                                       head_roll_max_deg=round(math.degrees(float(np.abs(Xs[:, 12]).max())), 1), clav_max_deg=round(math.degrees(float(np.linalg.norm(Xs[:, 8:11], axis=1).max())), 1))
            if use_cup:
                rec[s]["max_head_nod_deg"] = round(math.degrees(float(Xs[:, 4].max())), 1)
                dist, rgap = [], []
                for f in np.nonzero(wt > 0.99)[0]:
                    _, C, _ = points(f, pose(f, Xs[f])); rim = C[cup["rim"]]; dist.append(float(np.linalg.norm(rim - mouth_p, axis=1).min()))
                    k_ = np.argmin(np.linalg.norm(rim - mouth_p, axis=1)); rgap.append(float(hs.gap(rim[k_:k_ + 1])[0]))
                if dist: rec[s]["cup_rim_to_mouth_m_min_med_max"] = [round(min(dist), 4), round(float(np.median(dist)), 4), round(max(dist), 4)]
                if rgap: rec[s]["rim_to_face_surface_gap_m_min_med_max"] = [round(min(rgap), 4), round(float(np.median(rgap)), 4), round(max(rgap), 4)]
                rec[s]["drink_sec"] = [round(float(np.nonzero(wt > 0.99)[0][0]) / fps, 2), round(float(np.nonzero(wt > 0.99)[0][-1]) / fps, 2)] if (wt > 0.99).any() else []
        report[nm] = rec
        if any(r.get("frames") for r in rec.values()):
            log("clipfix", nm, {s: {k: v for k, v in r.items()} for s, r in rec.items() if r.get("frames")})
    log("clipfix done %.1fs" % (__import__("time").time() - t_start))
    if out_dir:
        json.dump({"clearance_m": {"arm": clr, "cup": CLR_CUP, "cup_rim_mouth": CLR_MOUTH}, "mouth_rest": np.round(mouth_p, 4).tolist(),
                   "note": "gap = 머리 겉면(얼굴형 모프 포함)까지 거리 m, 음수 = 파고듦. before/after: [팔↔머리+머리카락 최소, 컵↔맨 머리 최소, 손↔머리+머리카락 최소, 팔↔맨 머리 최소]",
                   "clips": report}, open(os.path.join(out_dir, "clip_fix_report.json"), "w"), ensure_ascii=False, indent=1)
    return report


ENV_HAIR = ("hair_w_perm", "hair_w_bob", "hair_m_spiky", "hair_w_bun")   # 머리 높이의 부피 큰 짧은·중간 머리(뒤로 늘어진 긴 머리는 뺌)
ENV_BEARD = ("beard_long",)
SHOULDER_MAX = 100                                                         # 어깨 보정 최대(도)
HAIR_CAP = 0.08                                                            # 머리카락·수염이 머리 겉보다 더 나온 몫은 8 cm까지만 비킴(팔 길이 한계)


def _envelope(arm, Ma_w, hs):
    """쉬는 자세의 부품 점(뼈 자식 그대로일 때) → 머리카락: 턱 높이 위만, 수염: 얼굴 앞쪽만."""
    import bpy
    pp = arm.data.pose_position; arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
    Mi = np.linalg.inv(Ma_w); out = []
    for names in (ENV_HAIR, ENV_BEARD):
        pts = []
        for nm in names:
            o = bpy.data.objects.get(nm)
            if o is None: continue
            M = Mi @ np.array(o.matrix_world); V = np.empty(len(o.data.vertices) * 3); o.data.vertices.foreach_get("co", V)
            V = V.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
            if names is ENV_HAIR: V = V[V[:, 2] > hs.c[2] - 0.6 * hs.rmed]
            else: V = V[(V[:, 1] < hs.c[1]) & (V[:, 2] > hs.c[2] - 0.95 * hs.rmed)]   # 턱 앞쪽만(가슴까지 늘어진 끝은 뺌)
            pts.append(V[::2])
        out.append(np.vstack(pts) if pts else np.zeros((0, 3)))
    arm.data.pose_position = pp; bpy.context.view_layer.update()
    return out


def _wrist_angle(Mf, Mh, rel):   # 손목 실제 꺾임(팔뚝 기준 손의 쉬는 자세 대비 회전, rad)
    R = rel[:3, :3].T @ Mf[:3, :3].T @ Mh[:3, :3]
    return math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2)))


def _under(rig, i, top):
    while i >= 0:
        if i == top: return True
        i = rig.par[i]
    return False


def _smooth01(t): t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)


def _gs(a, sig, loop):   # 시간 가우스(프레임)
    k = int(3 * sig); xs = np.arange(-k, k + 1); ker = np.exp(-0.5 * (xs / sig) ** 2); ker /= ker.sum()
    if loop: core = a[:-1]; e = np.concatenate([core[-k:], core, core[:k]]); o = np.convolve(e, ker, "valid"); return np.append(o, o[0])
    e = np.concatenate([np.repeat(a[:1], k), a, np.repeat(a[-1:], k)]); return np.convolve(e, ker, "valid")


def _stat(g): return [round(float(g[:, 0].min()), 4), round(float(g[:, 1].min()), 4) if g[:, 1].min() < 8 else None, round(float(g[:, 2].min()), 4), round(float(g[:, 3].min()), 4)]


def _signed_angle(q, h):
    w, v = q[0], np.asarray(q[1:]); s = float(v @ h)
    a = 2 * math.atan2(s, w)
    return (a + math.pi) % (2 * math.pi) - math.pi


def _m2q(R):
    q = Matrix(R.tolist()).to_quaternion(); return np.array([q.w, q.x, q.y, q.z])


def _lm(fun, x0, iters=25, free=None):
    if free is not None:   # 일부 자유도만
        base = np.array(x0, float); ix = np.nonzero(free)[0]
        def full(y): z = base.copy(); z[ix] = y; return z
        return full(_lm(lambda y: fun(full(y)), base[ix], iters))
    x = np.array(x0, float); r = fun(x); c = r @ r; mu = 1e-2
    for _ in range(iters):
        J = np.empty((len(r), len(x)))
        for j in range(len(x)):
            e = np.zeros(len(x)); e[j] = 1e-4; J[:, j] = (fun(x + e) - r) / 1e-4
        A = J.T @ J; g = J.T @ r
        while True:
            dx = -np.linalg.solve(A + mu * np.diag(np.diag(A) + 1e-6), g)
            nd = np.linalg.norm(dx)
            if nd > 0.3: dx *= 0.3 / nd   # 한 번에 17도 넘게 돌지 않게(먼 국소해로 튀지 않게)
            r2 = fun(x + dx); c2 = r2 @ r2
            if c2 < c: x, r, c = x + dx, r2, c2; mu = max(mu / 3, 1e-6); break
            mu *= 4
            if mu > 1e6: return x
        if np.linalg.norm(dx) < 1e-5: break
    return x


def _blend(X, need, pad, loop):
    """보정 구간 앞뒤 pad 프레임에 가까운 보정 값을 이어 붙이고 0으로 부드럽게, 그다음 가우스로 다듬기."""
    n = len(X); idx = np.nonzero(need)[0]
    if not len(idx): return X
    out = np.zeros_like(X)
    for f in range(n):
        dd = np.abs(idx - f)
        if loop: dd = np.minimum(dd, n - 1 - dd)
        k = int(np.argmin(dd)); dist = dd[k]
        src = X[idx[k]]
        if dist == 0: out[f] = X[f]
        elif dist <= pad: t = 1 - dist / (pad + 1); out[f] = src * (t * t * (3 - 2 * t))
    xs = np.arange(-4, 5); ker = np.exp(-0.5 * (xs / SIGMA_FR) ** 2); ker /= ker.sum()
    if loop:
        core = out[:-1]; ext = np.concatenate([core[-4:], core, core[:4]])
        sm = np.stack([np.convolve(ext[:, j], ker, "valid") for j in range(X.shape[1])], 1); sm = np.vstack([sm, sm[:1]])
    else:
        ext = np.concatenate([np.repeat(out[:1], 4, 0), out, np.repeat(out[-1:], 4, 0)])
        sm = np.stack([np.convolve(ext[:, j], ker, "valid") for j in range(X.shape[1])], 1)
    # 보정이 꼭 필요한 프레임은 다듬어도 원래 크기보다 작아지지 않게(방향은 다듬은 쪽)
    for f in idx:
        a, b = np.linalg.norm(sm[f]), np.linalg.norm(X[f])
        if a > 1e-9 and a < b: sm[f] *= b / a
    return sm


def _write(arm, act, d, bone, q):
    tab = d["tab"]; fr = d["fr"]; fcs = tab.get((bone, "rotation_quaternion"), {})
    cb = None
    for l in act.layers:
        for s in l.strips:
            for c in s.channelbags: cb = cb or c
    for k in range(4):
        fc = fcs.get(k)
        if fc is None:
            fc = cb.fcurves.new(f'pose.bones["{bone}"].rotation_quaternion', index=k); fcs[k] = fc
            try: fc.group = cb.groups.get(bone) or cb.groups.new(bone)
            except Exception: pass
        kp = fc.keyframe_points
        if len(kp) != len(fr):
            kp.clear(); kp.add(len(fr))
        kp.foreach_set("co", np.column_stack([fr, q[:, k]]).ravel().astype(np.float32))
        try: kp.foreach_set("interpolation", [1] * len(fr))
        except Exception:
            for p in kp: p.interpolation = 'LINEAR'
        fc.update()
    tab[(bone, "rotation_quaternion")] = fcs
