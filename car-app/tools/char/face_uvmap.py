# 얼굴 그림(face.png) 칸 ↔ 정면 배치(문서 56: 1024 그림, 512px = 머리 반지름) 대응표 만들기.
#  - plaza_char2.glb 의 'face' 조각은 기준 머리 중심에서 본 방향으로 펼친 UV(FACE_PHI 1.8 / FACE_THETA 1.9).
#  - 정면 배치는 머리 중심 기준 정투영 좌표. 둘은 공 모양 펼침이라 비율이 다르다 → 칸마다 실제 얼굴 면을 쏴서 맞춘다.
#  - 결과 face_uvmap.npz: map[v, u] = (정면 X, 정면 Y) / 머리 반지름(오른쪽·아래가 +), 못 맞힌 칸은 nan.
# 실행: Blender -b --factory-startup -P face_uvmap.py -- --glb plaza_char2.glb --out face_uvmap.npz [--n 192]
import bpy, math, sys
import numpy as np
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
N = int(arg("--n", "192"))
PHI, THETA = 1.8, 1.9; TH0 = math.pi / 2 - THETA / 2
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=arg("--glb"))
for a in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
    a.data.pose_position = 'REST'
bpy.context.view_layer.update()
face = bpy.data.objects["face"]
dg = bpy.context.evaluated_depsgraph_get(); fe = face.evaluated_get(dg); me = fe.to_mesh()
W = fe.matrix_world
P = np.array([(W @ v.co)[:] for v in me.vertices])
uvl = me.uv_layers.active.data
UV = np.zeros((len(me.vertices), 2))
for l in me.loops: UV[l.vertex_index] = uvl[l.index].uv[:]
def dirs(u, fv):
    ph = (u - 0.5) * PHI + math.pi / 2; th = fv * THETA + TH0
    return np.stack([-np.sin(th) * np.cos(ph), -np.sin(th) * np.sin(ph), np.cos(th)], -1)
D = dirs(UV[:, 0], 1 - UV[:, 1])
# 모든 꼭짓점이 '중심 + r·방향' 이므로 중심 C 는 (I - d dᵀ)(P - C) = 0 의 최소제곱 해
A = np.zeros((3, 3)); b = np.zeros(3)
for p, d in zip(P, D):
    M = np.eye(3) - np.outer(d, d); A += M; b += M @ p
C = np.linalg.solve(A, b)
res = np.linalg.norm([(np.eye(3) - np.outer(d, d)) @ (p - C) for p, d in zip(P, D)], axis=1)
r = np.linalg.norm(P - C, axis=1)
R = float(arg("--radius", "0")) or 0.5 * 0.7014320445407606   # build_report K_master_to_rig × 0.5
print("FACEMAP center", C.round(4), "ray residual max", res.max().round(5), "p95", np.percentile(res, 95).round(5), "n", len(P), "R", round(R, 4), "|P-C|/R median", np.median(r / R).round(3), "min", (r / R).min().round(3))
inner = (UV[:, 0] > .1) & (UV[:, 0] < .9) & (UV[:, 1] > .1) & (UV[:, 1] < .9)
print("FACEMAP residual inner p95", np.percentile(res[inner], 95).round(5), "outer p95", np.percentile(res[~inner], 95).round(5))
# 앱(Filament)·블렌더는 삼각형 안에서 UV를 직선으로 보간한다 → 칸마다 그 칸을 품은 삼각형의 무게중심 좌표로 3D 점을 구한다(렌더와 똑같은 대응)
out = np.full((N, N, 3), np.nan, np.float32)
Q = np.c_[UV[:, 0], 1 - UV[:, 1]] * N - 0.5          # 칸 좌표(u 오른쪽, fv 아래)
for poly in me.polygons:
    vs = list(poly.vertices)
    for k in range(1, len(vs) - 1):
        t = [vs[0], vs[k], vs[k + 1]]; q = Q[t]
        i0, i1 = int(np.floor(q[:, 0].min())), int(np.ceil(q[:, 0].max())); j0, j1 = int(np.floor(q[:, 1].min())), int(np.ceil(q[:, 1].max()))
        i0, j0 = max(i0, 0), max(j0, 0); i1, j1 = min(i1, N - 1), min(j1, N - 1)
        if i1 < i0 or j1 < j0: continue
        jj, ii = np.mgrid[j0:j1 + 1, i0:i1 + 1]
        T = np.array([[q[1, 0] - q[0, 0], q[2, 0] - q[0, 0]], [q[1, 1] - q[0, 1], q[2, 1] - q[0, 1]]])
        if abs(np.linalg.det(T)) < 1e-12: continue
        ab = np.linalg.solve(T, np.stack([ii.ravel() - q[0, 0], jj.ravel() - q[0, 1]]))
        a_, b_ = ab; ok = (a_ >= -1e-6) & (b_ >= -1e-6) & (a_ + b_ <= 1 + 1e-6)
        S = P[t[0]] + np.outer(a_, P[t[1]] - P[t[0]]) + np.outer(b_, P[t[2]] - P[t[0]]) - C
        out[jj.ravel()[ok], ii.ravel()[ok]] = np.stack([S[ok, 0] / R, -S[ok, 2] / R, -S[ok, 1] / R], -1)   # 정면 X(오른쪽+), Y(아래+), 앞으로 나온 깊이
print("FACEMAP hit", np.isfinite(out[..., 0]).mean().round(3))
np.savez_compressed(arg("--out"), map=out, center=C, radius=R, phi=PHI, theta=THETA, verts=P, uv=UV)
print("FACEMAP saved", arg("--out"))
