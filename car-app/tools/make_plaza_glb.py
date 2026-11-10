#!/usr/bin/env python3
"""차 광장 장면 GLB 만들기 (numpy + Pillow, 블렌더 없이).

만드는 파일 세 개 (car-app/app/src/main/assets/):
  plaza_scene.glb  흰 원형 받침판(모래색 옆면), 바닥 그림자, 쿠션마다 '+' 표시, 말 거는 자리(앞쪽 가운데 연베이지 원판),
                   유리 돔(비·눈 때만), 비·눈 덩어리, 받침판 눈 테는 코드로 만들고,
                   나무·가로등·빈백 쿠션 5(반원, 왼쪽부터 slot 1~5)·풀 7·디딤돌·화분·눈사람·충전 기둥·벤치는 Meshy 소품(pr_*.glb, 11/09)을
                   예전과 같은 노드 이름으로 끼운다(텍스처 512·기본색만). 나무·가로등·화분 위 눈 캡은 소품 윗면에서 만든다
  plaza_bird.glb   새(pr_bird.glb 그대로: 뼈 + 동작 7개). 앱이 Animator 로 재생
  plaza_char.glb   캐릭터 더미 1명: 머리·몸·팔·벙어리장갑 손·다리·신발 노드 분리 + 머리카락 14종 + 수염 2 + 안경 3
                   (머리카락 실루엣·좌표는 server/web/avatar3d.js 와 같게: 머리 반지름 0.5 기준, 머리 노드 스케일 0.92)

규칙
- 좌표: y 위, +z 앞(카메라 쪽). 단위는 대충 m(캐릭터 선 키 약 1.9).
- 노드에는 위치·스케일만 둔다(회전은 메시에 구워 넣음). 차 앱이 노드 위치를 읽어 자세를 만든다(PlazaView).
- 동작(뼈 애니메이션)은 넣지 않는다: Filament가 애니메이션 재생 때 뼈 크기를 덮어쓰므로, 자세·키는 앱이 노드 변환으로 직접 정한다.
- 색은 런타임에 재질 색값만 바꾼다(재질 이름 = 바꾸는 단위). 얼굴은 'face' 재질에 앱이 그린 텍스처를 꽂는다.
- 쿠션 자리·나무·말 거는 자리 위치는 PlazaView.kt 가 노드 위치를 읽어 쓰므로 여기만 고치면 된다.
- 소품 노드는 y축 회전을 가질 수 있다(앱은 쿠션·돌판의 위치만 읽는다). 캐릭터 노드는 위치·스케일만.

사용: python3 car-app/tools/make_plaza_glb.py   (저장소 어디서 실행해도 됨. 소품 읽기에 Pillow 필요, 소품 폴더는 DODAM_PROPS)
"""
import json
import math
import os
import struct
import zlib

import numpy as np

PI = math.pi
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "src", "main", "assets")


# ---------------------------------------------------------------- 메시 기본형
class M:
    def __init__(self, p, n, uv, idx):
        self.p = np.asarray(p, np.float32).reshape(-1, 3)
        self.n = np.asarray(n, np.float32).reshape(-1, 3)
        self.uv = np.asarray(uv, np.float32).reshape(-1, 2)
        self.i = np.asarray(idx, np.uint32).reshape(-1)

    @property
    def tris(self):
        return len(self.i) // 3


def merge(ms):
    ms = [m for m in ms if m is not None]
    off, idx = 0, []
    for m in ms:
        idx.append(m.i + off)
        off += len(m.p)
    return M(np.concatenate([m.p for m in ms]), np.concatenate([m.n for m in ms]),
             np.concatenate([m.uv for m in ms]), np.concatenate(idx))


def euler(rx=0.0, ry=0.0, rz=0.0):
    """three.js 기본 순서 'XYZ': R = Rx · Ry · Rz."""
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


def xf(m, t=(0, 0, 0), r=None, s=(1, 1, 1), R=None):
    """three.js 메시 변환과 같게 v' = T + R(S v). 법선은 역전치로."""
    if m is None:
        return None
    S = np.diag(np.asarray(s, np.float64))
    Rm = R if R is not None else (euler(*r) if r is not None else np.eye(3))
    A = Rm @ S
    p = m.p.astype(np.float64) @ A.T + np.asarray(t, np.float64)
    N = np.linalg.inv(A).T
    n = m.n.astype(np.float64) @ N.T
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    idx = m.i
    if np.linalg.det(A) < 0:  # 거울 변환이면 감는 방향을 뒤집는다
        idx = idx.reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)
    return M(p, n, m.uv, idx)


def grid_index(ws, hs, skip_top=False, skip_bottom=False):
    out = []
    for iy in range(hs):
        for ix in range(ws):
            a = iy * (ws + 1) + ix + 1
            b = iy * (ws + 1) + ix
            c = (iy + 1) * (ws + 1) + ix
            d = (iy + 1) * (ws + 1) + ix + 1
            if iy != 0 or not skip_top:
                out += [a, b, d]
            if iy != hs - 1 or not skip_bottom:
                out += [b, c, d]
    return out


def sphere(r, ws=16, hs=10, phi0=0.0, phil=2 * PI, th0=0.0, thl=PI):
    """three.js SphereGeometry 와 같은 좌표·UV(v=0이 위)."""
    p, n, uv = [], [], []
    for iy in range(hs + 1):
        v = iy / hs
        th = th0 + v * thl
        for ix in range(ws + 1):
            u = ix / ws
            ph = phi0 + u * phil
            x, y, z = -math.cos(ph) * math.sin(th), math.cos(th), math.sin(ph) * math.sin(th)
            p.append((r * x, r * y, r * z)); n.append((x, y, z)); uv.append((u, v))
    return M(p, n, uv, grid_index(ws, hs, skip_top=th0 == 0, skip_bottom=th0 + thl >= PI - 1e-6))


def capsule(r, length, cap=4, ws=12):
    """y축 캡슐(가운데 원점, 전체 길이 length + 2r)."""
    rows = [(i / cap * PI / 2, length / 2) for i in range(cap + 1)] + [(PI / 2 + i / cap * PI / 2, -length / 2) for i in range(cap + 1)]
    p, n, uv = [], [], []
    hs = len(rows) - 1
    for iy, (th, yo) in enumerate(rows):
        for ix in range(ws + 1):
            ph = ix / ws * 2 * PI
            x, y, z = -math.cos(ph) * math.sin(th), math.cos(th), math.sin(ph) * math.sin(th)
            p.append((r * x, r * y + yo, r * z)); n.append((x, y, z)); uv.append((ix / ws, iy / hs))
    return M(p, n, uv, grid_index(ws, hs, True, True))


def cylinder(rt, rb, h, ws=16, th0=0.0, thl=2 * PI, caps=True):
    """three.js CylinderGeometry: theta 0 = +z, x = r sinθ."""
    slope = (rb - rt) / h
    p, n, uv = [], [], []
    for iy in range(2):
        r = rt if iy == 0 else rb
        y = h / 2 if iy == 0 else -h / 2
        for ix in range(ws + 1):
            t = th0 + ix / ws * thl
            nn = np.array([math.sin(t), slope, math.cos(t)]); nn /= np.linalg.norm(nn)
            p.append((r * math.sin(t), y, r * math.cos(t))); n.append(nn); uv.append((ix / ws, iy))
    idx = []
    for ix in range(ws):
        a, b, c, d = ix, ws + 1 + ix, ws + 1 + ix + 1, ix + 1
        idx += [a, b, d, b, c, d]
    m = M(p, n, uv, idx)
    if not caps:
        return m
    parts = [m]
    for top in (True, False):
        r = rt if top else rb
        if r <= 0:
            continue
        y = h / 2 if top else -h / 2
        cp, cn, cu, ci = [(0, y, 0)], [(0, 1 if top else -1, 0)], [(0.5, 0.5)], []
        for ix in range(ws + 1):
            t = th0 + ix / ws * thl
            cp.append((r * math.sin(t), y, r * math.cos(t))); cn.append(cn[0]); cu.append((0.5, 0.5))
        for ix in range(ws):
            ci += [0, ix + 1, ix + 2] if top else [0, ix + 2, ix + 1]
        parts.append(M(cp, cn, cu, ci))
    return merge(parts)


def cone(r, h, ws=10):
    return cylinder(0.0, r, h, ws)


def disc(r, ws=24, y=0.0):
    """위를 보는 납작한 원판(부채꼴 삼각형). 바닥 그림자·빛 웅덩이용."""
    p, n, uv, idx = [(0, y, 0)], [(0, 1, 0)], [(.5, .5)], []
    for ix in range(ws + 1):
        t = ix / ws * 2 * PI
        p.append((r * math.sin(t), y, r * math.cos(t))); n.append((0, 1, 0)); uv.append((.5, .5))
    for ix in range(ws):
        idx += [0, ix + 1, ix + 2]
    m = M(p, n, uv, idx)
    # 위에서 보이게 감기 방향 확인
    e1 = m.p[idx[1]] - m.p[0]; e2 = m.p[idx[2]] - m.p[0]
    if np.cross(e1, e2)[1] < 0:
        m.i = m.i.reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)
    return m


def soft_disc(r, y=0.0, sx=1.0, sz=1.0, ws=24):
    """두 겹 원판(가장자리 옅게 = 흐린 그림자처럼)."""
    return xf(merge([disc(r, ws, y), disc(r * .68, max(20, ws - 8), y + .002)]), s=(sx, 1, sz))


def disc_uv(r, ws=32, y=0.0):
    """위를 보는 원판, UV는 가운데 (.5, .5)·가장자리 반지름 .5(둥근 흐림 텍스처로 가장자리를 부드럽게 지운다)."""
    p, n, uv, idx = [(0, y, 0)], [(0, 1, 0)], [(.5, .5)], []
    for ix in range(ws + 1):
        t = ix / ws * 2 * PI
        p.append((r * math.sin(t), y, r * math.cos(t))); n.append((0, 1, 0)); uv.append((.5 + .5 * math.sin(t), .5 + .5 * math.cos(t)))
    for ix in range(ws):
        idx += [0, ix + 2, ix + 1]
    m = M(p, n, uv, idx)
    e1 = m.p[m.i[1]] - m.p[0]; e2 = m.p[m.i[2]] - m.p[0]
    if np.cross(e1, e2)[1] < 0:
        m.i = m.i.reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)
    return m


def plate_decal(cx, cz, sx, sz, y, r=4.14, ws=56):
    """받침판 모양(반지름 r) 위에 까는 얇은 판. UV는 (cx, cz)를 가운데로 가로 sx·세로 sz 타원이 0~1이 되게(밖은 텍스처 가장자리 = 투명).
    타원이 받침판 밖으로 나가도 판 밖 허공에 빛이 뜨지 않는다."""
    p, uv, idx = [(0, y, 0)], [(.5 - cx / (2 * sx), .5 - cz / (2 * sz))], []
    for ix in range(ws + 1):
        t = ix / ws * 2 * PI
        x, z = r * math.sin(t), r * math.cos(t)
        p.append((x, y, z)); uv.append((.5 + (x - cx) / (2 * sx), .5 + (z - cz) / (2 * sz)))
    for ix in range(ws):
        idx += [0, ix + 1, ix + 2]
    m = M(p, [(0, 1, 0)] * len(p), uv, idx)
    e1 = m.p[m.i[1]] - m.p[0]; e2 = m.p[m.i[2]] - m.p[0]
    if np.cross(e1, e2)[1] < 0:
        m.i = m.i.reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)
    return m


def facing_quad(w, h, center, eye):
    """카메라(eye)를 바라보는 네모(빛 번짐·바탕 흐린 빛). 카메라가 고정이라 방향을 메시에 굽는다."""
    c = np.asarray(center, np.float64); f = np.asarray(eye, np.float64) - c; f /= np.linalg.norm(f)
    r = np.cross([0, 1, 0], f); r /= np.linalg.norm(r); u = np.cross(f, r)
    p = [c + (sx * w / 2) * r + (sy * h / 2) * u for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return M(p, [f] * 4, [(0, 1), (1, 1), (1, 0), (0, 0)], [0, 1, 2, 0, 2, 3])


def radial_png(n, curve):
    """흰색 + 가운데서 바깥으로 옅어지는 알파(curve: 0~1 거리 → 0~1 알파). 가장자리(거리 1 이상)는 0."""
    yy, xx = np.mgrid[0:n, 0:n]
    d = np.hypot((xx + .5) / n - .5, (yy + .5) / n - .5) / .5
    a = np.clip(curve(np.clip(d, 0, 1)), 0, 1) * (d < 1)
    rgba = np.zeros((n, n, 4), np.uint8); rgba[..., :3] = 255; rgba[..., 3] = np.round(a * 255).astype(np.uint8)
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(n))
    def chunk(t, d_):
        return struct.pack(">I", len(d_)) + t + d_ + struct.pack(">I", zlib.crc32(t + d_) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def smooth(d):
    return d * d * (3 - 2 * d)


def torus(R, tube, rs=8, ts=24, arc=2 * PI):
    """three.js TorusGeometry (xy 평면, z축 둘레)."""
    p, n, uv = [], [], []
    for j in range(rs + 1):
        for i in range(ts + 1):
            u = i / ts * arc
            v = j / rs * 2 * PI
            x = (R + tube * math.cos(v)) * math.cos(u)
            y = (R + tube * math.cos(v)) * math.sin(u)
            z = tube * math.sin(v)
            c = np.array([R * math.cos(u), R * math.sin(u), 0.0])
            nn = np.array([x, y, z]) - c; nn /= np.linalg.norm(nn)
            p.append((x, y, z)); n.append(nn); uv.append((i / ts, j / rs))
    idx = []
    for j in range(1, rs + 1):
        for i in range(1, ts + 1):
            a = (ts + 1) * j + i - 1
            b = (ts + 1) * (j - 1) + i - 1
            c = (ts + 1) * (j - 1) + i
            d = (ts + 1) * j + i
            idx += [a, b, d, b, c, d]
    return M(p, n, uv, idx)


def box(w, h, d):
    p, n, uv, idx = [], [], [], []
    for ax in range(3):
        for sgn in (1, -1):
            nn = [0, 0, 0]; nn[ax] = sgn
            u_ax, v_ax = [(1, 2), (0, 2), (0, 1)][ax]
            base = len(p)
            for (a, b) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                v = [0.0, 0.0, 0.0]
                v[ax] = sgn * 0.5; v[u_ax] = a * 0.5; v[v_ax] = b * 0.5
                p.append((v[0] * w, v[1] * h, v[2] * d)); n.append(nn); uv.append(((a + 1) / 2, (b + 1) / 2))
            q = [base, base + 1, base + 2, base, base + 2, base + 3]
            # 바깥을 향하게 감기 방향 맞추기
            e1 = np.subtract(p[base + 1], p[base]); e2 = np.subtract(p[base + 2], p[base])
            if np.dot(np.cross(e1, e2), nn) < 0:
                q = [base, base + 2, base + 1, base, base + 3, base + 2]
            idx += q
    return M(p, n, uv, idx)


# ------------------------------------------------- avatar3d.js 의 머리 도형 (R=0.5 기준, 머리 공간)
R = 0.5
FACE_PHI, FACE_THETA = 1.8, 1.9
TH0 = PI / 2 - FACE_THETA / 2


def on_face(u, v, r=R):
    ph = PI / 2 + (u - .5) * FACE_PHI
    th = TH0 + v * FACE_THETA
    return (-r * math.cos(ph) * math.sin(th), r * math.cos(th), r * math.sin(ph) * math.sin(th))


def ball(r, p=(0, 0, 0), s=(1, 1, 1), rt=(0, 0, 0), ws=10, hs=6):
    return xf(sphere(r, ws, hs), p, rt, s)


def cap(k, th, tilt=0.0, s=(1, 1, 1)):
    return xf(sphere(R * k, 16, 6, 0, 2 * PI, 0, th), r=(tilt, 0, 0), s=s)


def bangs(k, phil, th0, th1, shift=0.0):
    return sphere(R * k, 12, 5, PI / 2 - phil / 2 + shift, phil, th0, th1 - th0)


def shell(rt, rb, h, top, gap):
    return xf(cylinder(rt, rb, h, 18, gap / 2, 2 * PI - gap, caps=False), (0, top - h / 2, 0))


def band(k, th0, th1, gap):
    return sphere(R * k, 18, 4, PI / 2 + gap / 2, 2 * PI - gap, th0, th1 - th0)


def on_head(m, th, ph, r):
    nrm = np.array([math.sin(th) * math.sin(ph), math.cos(th), math.sin(th) * math.cos(ph)])
    # y축 → nrm 으로 돌리는 회전
    y = np.array([0.0, 1.0, 0.0])
    v = np.cross(y, nrm); c = float(np.dot(y, nrm))
    if np.linalg.norm(v) < 1e-8:
        Rm = np.eye(3)
    else:
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        Rm = np.eye(3) + vx + vx @ vx * (1 / (1 + c))
    return xf(m, tuple(nrm * r), R=Rm)


def hair(i):
    """머리 14종(56번 순서 = server/avatar.py PARTS). 실루엣 4갈래(솟음·퍼짐·긺·없음)."""
    g = []
    if i == 0:    # 짧은 스포츠
        g.append(cap(1.07, 1.25, -.38))
        for k in range(7):
            g.append(on_head(ball(.12, s=(1, .7, 1), ws=8, hs=5), .32 + (k % 2) * .25, k * .9, .52))
    elif i == 1:  # 옆가르마
        g += [cap(1.08, 1.32, -.3), bangs(1.1, 1.1, .45, 1.15, -.3), ball(.26, (.1, .36, .16), (1.45, .62, 1.15), (0, 0, -.35))]
    elif i == 2:  # 삐죽 세운 머리
        g.append(cap(1.05, 1.2, -.42))
        for k in range(10):
            g.append(on_head(cone(.085, .3, 8), .18 + (k % 3) * .26, k * 1.3 + .2, .5))
    elif i == 3:  # 짧은 옆머리
        for s in (-1, 1):
            g.append(ball(.2, (s * .46, -.02, -.1), (.55, 1, 1.25)))
        g.append(ball(.3, (0, -.06, -.38), (1.35, .6, .6)))
    elif i == 4:  # 민머리: 빈 노드(머리카락 없음)
        return None
    elif i == 5:  # 긴 생머리
        g += [cap(1.08, 1.42, -.2), bangs(1.1, 1.6, .4, 1.22), shell(.54, .6, 1.15, .18, 1.55)]
    elif i == 6:  # 높은 포니테일
        g += [cap(1.07, 1.38, -.3), bangs(1.1, 1.3, .45, 1.15, .2), ball(.11, (.14, .4, -.38)),
              xf(capsule(.12, .5, 3, 10), (.36, .02, -.5), (.35, 0, .45)), ball(.12, (.5, -.28, -.45), (.9, 1.2, .9))]
    elif i == 7:  # 양갈래 (묶은 끈은 'tie' 재질로 따로)
        g += [cap(1.07, 1.4, -.25), bangs(1.1, 1.5, .4, 1.2)]
        for s in (-1, 1):
            g.append(ball(.17, (s * .56, -.24, -.12), (.85, 1.15, .85)))
    elif i == 8:  # 어깨 웨이브
        g += [cap(1.1, 1.45, -.25), bangs(1.12, 1.2, .42, 1.12, -.25)]
        for s in (-1, 1):
            for k in range(3):
                g.append(ball(.2 - k * .015, (s * (.5 + k * .05), -.05 - k * .24, -.08 - k * .05)))
        g += [ball(.32, (0, -.18, -.34)), ball(.3, (0, -.48, -.3), (1.2, 1, 1))]
    elif i == 9:  # 올림머리
        g += [cap(1.06, 1.4, -.2), ball(.2, (0, .56, -.12)), ball(.09, (0, .44, -.1), (1.4, .5, 1.4))]
    elif i == 10:  # 일자 앞머리
        g += [cap(1.12, 1.28, 0, (1, 1.02, 1)), band(1.12, 1.2, 1.7, 2.1)]
    elif i == 11:  # 단발 보브
        g += [cap(1.09, 1.35, -.15), bangs(1.11, 1.55, .4, 1.2), shell(.55, .6, .6, .1, 1.7)]
    elif i == 12:  # 숏컷
        g += [cap(1.09, 1.3, -.3), ball(.22, (-.12, .33, .3), (1.6, .6, .9), (0, 0, .25))]
        for s in (-1, 1):
            g.append(ball(.16, (s * .47, 0, -.04), (.6, 1.2, 1.1)))
    elif i == 13:  # 뽀글 파마: 작은 공(삼각형 아끼려고 수를 줄임)
        g.append(cap(1.05, 1.45, -.2))
        N, ga = 34, PI * (3 - math.sqrt(5))
        for k in range(N):
            y = 1 - (k / (N - 1)) * 2
            rr = math.sqrt(max(0.0, 1 - y * y))
            x, z = math.cos(k * ga) * rr, math.sin(k * ga) * rr
            if y < -.4 or (z > .2 and y < .3 and abs(x) < .8):
                continue
            g.append(ball(.16, (x * .57, y * .57 + .03, z * .57), ws=7, hs=5))
    return merge(g)


def hair_tie():
    return merge([ball(.055, (s * .5, -.07, -.1), ws=8, hs=5) for s in (-1, 1)])


def beard(kind):
    ny = on_face(.5, .60)[1]
    my = on_face(.5, .71)[1]
    g = [ball(.09, (s * .075, (ny + my) / 2 - .01, R * .97), (1.15, .5, .6), (0, 0, s * -.25), 10, 6) for s in (-1, 1)]
    if kind == 3:
        g.append(ball(.3, (0, -.37, .2), (1.15, 1, .75)))
        for s in (-1, 1):
            g.append(ball(.2, (s * .27, -.24, .16), (.8, 1.1, .8)))
    return merge(g)


def glasses(kind):
    ex, ey, _ = on_face(.5 + .15, .50)
    z = R * 1.06
    tube = .02 if kind == 2 else .009
    dy = -.04 if kind == 3 else 0.0
    g = []
    for s in (-1, 1):
        if kind == 2:
            lens = xf(xf(torus(.12, tube, 6, 4), r=(0, 0, PI / 4)), s=(1, .78, 1))
        elif kind == 3:
            lens = xf(torus(.085, tube, 6, 12, PI), r=(0, 0, PI))
        else:
            lens = torus(.088, tube, 6, 16)
        g.append(xf(lens, (s * ex, ey + dy, z)))
        g.append(xf(cylinder(tube * .8, tube * .8, R * .9, 6), (s * R * .9, ey + dy + .01, z * .5), (PI / 2, 0, 0)))
    if kind != 3:
        g.append(xf(cylinder(tube * .8, tube * .8, ex * 2 - .2, 6), (0, ey + .02, z + .01), (0, 0, PI / 2)))
    return merge(g)


# ---------------------------------------------------------------- glTF 쓰기
def png_rgba(w, h, rgba):
    raw = b"".join(b"\x00" + bytes(rgba) * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class Gltf:
    def __init__(self):
        self.bin = bytearray()
        self.views, self.accs, self.meshes, self.mats, self.nodes = [], [], [], [], []
        self.mat_ix = {}
        self.images, self.textures, self.samplers = [], [], []
        self.tris = 0
        self.geo = {}        # 같은 메시를 여러 노드가 나눠 쓰게(쿠션 5·풀 7): id → (메시, 속성)
        self.mesh_ix = {}    # (메시 id, 재질) → glTF 메시 번호
        self.tex_ix = {}     # 소품 텍스처(이름 → 번호)
        self.tex_bytes = 0   # 텍스처 GPU 메모리 추정(RGBA8 + 밉맵)
        self.unlit = False

    def _view(self, data, target=None):
        while len(self.bin) % 4:
            self.bin += b"\x00"
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.bin += data
        self.views.append(v)
        return len(self.views) - 1

    def _acc(self, arr, ctype, typ, target, minmax=False):
        a = {"bufferView": self._view(arr.tobytes(), target), "componentType": ctype, "count": int(arr.shape[0]), "type": typ}
        if minmax:
            a["min"] = [float(x) for x in arr.min(axis=0)]
            a["max"] = [float(x) for x in arr.max(axis=0)]
        self.accs.append(a)
        return len(self.accs) - 1

    def texture(self, key, img):
        """소품 기본색 텍스처(PIL 그림)를 JPEG로 파일 안에 넣는다. 밉맵·반복 샘플러."""
        if key in self.tex_ix:
            return self.tex_ix[key]
        import io
        if not any(sm.get("minFilter") == 9987 for sm in self.samplers):
            self.samplers.append({"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})
        smp = next(i for i, sm in enumerate(self.samplers) if sm.get("minFilter") == 9987)
        buf = io.BytesIO(); img.convert("RGB").save(buf, "JPEG", quality=90)
        self.images.append({"bufferView": self._view(buf.getvalue()), "mimeType": "image/jpeg", "name": key})
        self.textures.append({"sampler": smp, "source": len(self.images) - 1})
        self.tex_ix[key] = len(self.textures) - 1
        self.tex_bytes += img.width * img.height * 4 * 4 // 3
        return self.tex_ix[key]

    def texture_png(self, key, png):
        """알파가 있는 PNG(빛 번짐·웅덩이 가장자리). 밉맵·가장자리 고정 샘플러."""
        if key in self.tex_ix:
            return self.tex_ix[key]
        if not any(sm.get("minFilter") == 9987 and sm.get("wrapS") == 33071 for sm in self.samplers):
            self.samplers.append({"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071})
        smp = next(i for i, sm in enumerate(self.samplers) if sm.get("minFilter") == 9987 and sm.get("wrapS") == 33071)
        self.images.append({"bufferView": self._view(png), "mimeType": "image/png", "name": key})
        self.textures.append({"sampler": smp, "source": len(self.images) - 1})
        self.tex_ix[key] = len(self.textures) - 1
        return self.tex_ix[key]

    def material(self, name, rgb, rough=.85, metal=0.0, alpha=1.0, double=False, texture=False, emissive=False, tex=None, unlit=False):
        if name in self.mat_ix:
            return self.mat_ix[name]
        pbr = {"baseColorFactor": [*rgb, alpha], "metallicFactor": metal, "roughnessFactor": rough}
        if tex is not None:
            pbr["baseColorTexture"] = {"index": tex}
        if texture:
            if not self.images:
                self.samplers.append({"magFilter": 9729, "minFilter": 9729, "wrapS": 33071, "wrapT": 33071})
                self.images.append({"uri": "face.png", "mimeType": "image/png"})  # 얼굴 그림은 앱이 사람마다 face.png로 넣어 준다(ResourceLoader.addResourceData)
                self.textures.append({"sampler": 0, "source": 0})
            pbr["baseColorTexture"] = {"index": 0}
        m = {"name": name, "pbrMetallicRoughness": pbr}
        if emissive:
            m["emissiveFactor"] = [0.0, 0.0, 0.0]   # 앱이 밤에 켠다(가로등 유리)
        if alpha < 1:
            m["alphaMode"] = "BLEND"
        if unlit:   # 빛을 받지 않는 색(빛 번짐·바탕 흐린 빛)
            m["extensions"] = {"KHR_materials_unlit": {}}
            self.unlit = True
        if double:
            m["doubleSided"] = True
        self.mats.append(m)
        self.mat_ix[name] = len(self.mats) - 1
        return self.mat_ix[name]

    def mesh(self, m, mat):
        self.tris += m.tris   # 그려지는 삼각형(노드마다)
        if (id(m), mat) in self.mesh_ix:
            return self.mesh_ix[(id(m), mat)]
        if id(m) not in self.geo:
            big = len(m.p) > 65535
            idx = m.i.astype(np.uint32 if big else np.uint16)
            attrs = {"POSITION": self._acc(m.p, 5126, "VEC3", 34962, True), "NORMAL": self._acc(m.n, 5126, "VEC3", 34962),
                     "TEXCOORD_0": self._acc(m.uv, 5126, "VEC2", 34962)}
            self.geo[id(m)] = (m, attrs, self._acc(idx.reshape(-1, 1), 5125 if big else 5123, "SCALAR", 34963))
        _, attrs, ia = self.geo[id(m)]
        self.meshes.append({"primitives": [{"attributes": dict(attrs), "indices": ia, "material": mat}]})
        self.mesh_ix[(id(m), mat)] = len(self.meshes) - 1
        return len(self.meshes) - 1

    def node(self, name, mesh=None, mat=None, t=None, s=None, children=None, yaw=None):
        n = {"name": name}
        if mesh is not None:
            n["mesh"] = self.mesh(mesh, mat)
        if t is not None:
            n["translation"] = [float(x) for x in t]
        if yaw is not None:   # 소품만: y축 회전(앱은 위치만 읽는다)
            n["rotation"] = [0.0, float(math.sin(yaw / 2)), 0.0, float(math.cos(yaw / 2))]
        if s is not None:
            n["scale"] = [float(x) for x in s]
        if children:
            n["children"] = children
        self.nodes.append(n)
        return len(self.nodes) - 1

    def write(self, path, roots):
        while len(self.bin) % 4:
            self.bin += b"\x00"
        doc = {"asset": {"version": "2.0", "generator": "dodam make_plaza_glb.py"}, "scene": 0, "scenes": [{"nodes": roots}],
               "nodes": self.nodes, "meshes": self.meshes, "materials": self.mats, "accessors": self.accs,
               "bufferViews": self.views, "buffers": [{"byteLength": len(self.bin)}]}
        if self.images:
            doc.update(images=self.images, textures=self.textures, samplers=self.samplers)
        if self.unlit:
            doc["extensionsUsed"] = ["KHR_materials_unlit"]
        js = json.dumps(doc, separators=(",", ":")).encode()
        js += b" " * ((4 - len(js) % 4) % 4)
        out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(self.bin))
        out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(self.bin), 0x004E4942) + bytes(self.bin)
        with open(path, "wb") as f:
            f.write(out)
        return len(out)


def quat_x(a):
    """x축 회전 사원수(glTF 노드 rotation: x, y, z, w)."""
    return (math.sin(a / 2), 0.0, 0.0, math.cos(a / 2))


def hexrgb(h):
    h = h.lstrip("#")
    # glTF 색은 선형: sRGB 값을 선형으로 바꿔 둔다(앱은 런타임에 sRGB로 다시 칠함)
    return [round(((int(h[i:i + 2], 16) / 255) ** 2.2), 4) for i in (0, 2, 4)]


# ---------------------------------------------------------------- 장면(받침판·나무·쿠션)
PLATE_R = 4.2
CUSHION_ARC = [(160, ), (125, ), (90, ), (55, ), (20, )]
TALK = (0.0, 0.0, 2.3)
FACE_TARGET = (0.0, 6.0)   # 쿠션·앉은 사람이 바라보는 점(카메라 쪽 앞). PlazaView.TARGET_Z 와 같게


def cushion_pos(i):
    ph = math.radians(160 - 35 * i)
    return (2.7 * math.cos(ph), 0.0, 0.6 - 2.4 * math.sin(ph))


def yaw_to(x, z):
    return math.atan2(FACE_TARGET[0] - x, FACE_TARGET[1] - z)


LAMP_XZ = (-2.69, -2.44)     # 가로등: 받침판 왼쪽 뒤(64번 9, 사용자 11/08 고름). 앉은 사람의 약 2배 높이
TREE_XZ = (0.0, -3.0)
CROWN_PIVOT = 1.95           # 잎이 흔들리는 축 높이(tree_crown 노드 원점). pr_tree2 실측: 잎 아래 끝 1.77~1.92, 줄기 갈라지는 곳
GRASS_DEG = (195, 240, 258, 282, 300, 338, 352)   # 뒤쪽 반원 가장자리 풀 7포기(가로등 222°·벤치 319° 자리는 비움)
POT_XZ = (2.65, 1.55)        # 낮은 화분: 앞 오른쪽(64번 25)
SNOWMAN_XZ = (-2.7, 1.8)   # 눈사람: 앞 왼쪽(눈 오는 날 정차 5·10·15분마다 자람)
CHARGER_XZ = (2.0, 2.3)      # 충전 기둥: 앞 오른쪽(충전구 열면 올라옴)
BENCH = (2.72, -2.36, math.radians(-45))   # 벤치(11/09): 오른쪽 뒤 가장자리, 가로등과 마주 보는 자리. 받침판 가운데를 보게(x, z, 방향)
PUDDLES = ((-1.7, 1.7, .55, .32), (1.45, 1.05, .42, .26))   # 비 오는 날 물웅덩이(x, z, 가로, 세로)
BIRD_PERCH = (1.31, 1.70, -2.14)   # 새가 앉는 곳: pr_tree2 오른쪽 앞 맨가지 끝 윗면(나무 기준 1.31, 1.70, .86). PlazaView 와 같게
STONES = ((.1, -.15), (-.12, .45), (.08, 1.0))   # 쿠션 줄에서 말 거는 자리로 가는 디딤돌 3개(모두에게 같은 길)
EYE = (0.0, 5.4, 11.2)       # 카메라(PlazaView.EYE·LOOK 와 같게). 빛 번짐·바탕 흐린 빛 네모가 카메라를 보게
LOOK = (0.0, 0.9, 0.2)
FX_H = 11.0      # 비·눈 덩어리 높이(앱 PlazaView.FX_H 와 같게)
FX_Y0 = -3.0     # 덩어리 아래 끝 높이


def lawn(r=4.1, zcut=.3, y=.006, ws=48):
    """받침판 뒤쪽 반원 옅은 잔디(z <= zcut). 볼록한 모양이라 안쪽 한 점에서 부채꼴로."""
    t0 = PI - math.asin(zcut / r); t1 = 2 * PI + math.asin(zcut / r)
    p, n, uv, idx = [(0, y, -1.9)], [(0, 1, 0)], [(.5, .5)], []
    for i in range(ws + 1):
        t = t0 + (t1 - t0) * i / ws
        p.append((r * math.cos(t), y, r * math.sin(t))); n.append((0, 1, 0)); uv.append((.5, .5))
    for i in range(ws):
        idx += [0, i + 1, i + 2]
    m = M(p, n, uv, idx)
    e1 = m.p[idx[1]] - m.p[0]; e2 = m.p[idx[2]] - m.p[0]
    if np.cross(e1, e2)[1] < 0:
        m.i = m.i.reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)
    return m


# ---------------------------------------------------------------- Meshy 소품 읽기(11/09)
# 소품 원본: style_refs/meshy_1109/props/out/pr_*.glb (미터 단위, 바닥 가운데 원점, 앞 = +z). style_refs 폴더는 DODAM_REFS, 소품 폴더를 바로 줄 때는 DODAM_PROPS
PROPS_DIR = os.environ.get("DODAM_PROPS") or os.path.join(os.environ.get("DODAM_REFS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "char/style_refs")), "meshy_1109/props/out")
TEX = 512        # 소품 텍스처 한 변(Pleos 램 400MB). 기본색만, 거칠기 상수, 금속 없음
_CT = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_prop(name):
    """pr_<name>.glb 의 첫 메시(위치·법선·UV)와 기본색 그림(PIL). 노드 변환이 없는 파일만(정리 도구가 그렇게 만든다)."""
    import io
    from PIL import Image
    b = open(os.path.join(PROPS_DIR, f"pr_{name}.glb"), "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    o = 20 + jl
    bn = b[o + 8:o + 8 + struct.unpack("<I", b[o:o + 4])[0]]
    def acc(i):
        a = j["accessors"][i]; v = j["bufferViews"][a["bufferView"]]
        dt = np.dtype(_CT[a["componentType"]]); k = _NC[a["type"]]
        st = v.get("byteStride", dt.itemsize * k); off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        rows = [np.frombuffer(bn, dt, k, off + r * st) for r in range(a["count"])] if st != dt.itemsize * k else None
        return np.array(rows) if rows is not None else np.frombuffer(bn, dt, a["count"] * k, off).reshape(-1, k)
    assert not any(k in nd for nd in j["nodes"] for k in ("translation", "rotation", "scale", "matrix")), name
    pr = j["meshes"][0]["primitives"][0]
    m = M(acc(pr["attributes"]["POSITION"]), acc(pr["attributes"]["NORMAL"]), acc(pr["attributes"]["TEXCOORD_0"]), acc(pr["indices"]).reshape(-1))
    src = j["textures"][j["materials"][pr["material"]]["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"]
    v = j["bufferViews"][j["images"][src]["bufferView"]]
    img = Image.open(io.BytesIO(bn[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]])).convert("RGB")
    return m, img


def small(img, n=TEX):
    from PIL import Image
    return img if img.width <= n else img.resize((n, n), Image.LANCZOS)


def tri_rgb(m, img):
    """삼각형마다 UV 가운데 점의 기본색(0~1). 줄기/잎·기둥/유리처럼 색으로 나눌 때 쓴다."""
    a = np.asarray(img, np.float32) / 255; h, w = a.shape[:2]
    c = m.uv[m.i.reshape(-1, 3)].mean(1)
    return a[np.clip((c[:, 1] % 1) * h, 0, h - 1).astype(int), np.clip((c[:, 0] % 1) * w, 0, w - 1).astype(int)]


def tri_center(m):
    return m.p[m.i.reshape(-1, 3)].mean(1)


def sub(m, keep, shift=(0, 0, 0)):
    """고른 삼각형만 떼어 새 메시로(점 번호 다시 매김). shift 만큼 옮긴다(노드 원점 맞추기)."""
    t = m.i.reshape(-1, 3)[keep]
    used, inv = np.unique(t.reshape(-1), return_inverse=True)
    return M(m.p[used] + np.asarray(shift, np.float32), m.n[used], m.uv[used], inv.astype(np.uint32))


def snow_cap(m, occ, keep=None, up=.5, lift=.04, cell=.05):
    """위에서 보이는 윗면에만 얹는 눈 껍질(받은 메시를 법선·위로 살짝 띄움). occ = 가림 판정용 전체 메시."""
    c = tri_center(m); nt = m.n[m.i.reshape(-1, 3)].mean(1)
    pts = np.concatenate([occ.p, tri_center(occ)])
    x0, z0 = pts[:, 0].min(), pts[:, 2].min()
    gx = ((pts[:, 0] - x0) / cell).astype(int); gz = ((pts[:, 2] - z0) / cell).astype(int)
    hm = np.full((gx.max() + 1, gz.max() + 1), -1e9); np.maximum.at(hm, (gx, gz), pts[:, 1])
    cx = np.clip(((c[:, 0] - x0) / cell).astype(int), 0, hm.shape[0] - 1); cz = np.clip(((c[:, 2] - z0) / cell).astype(int), 0, hm.shape[1] - 1)
    ok = (nt[:, 1] > up) & (c[:, 1] >= hm[cx, cz] - .06)
    if keep is not None:
        ok &= keep
    s = sub(m, ok)
    w = np.clip((s.n[:, 1:2] - up) / (1 - up), 0, 1)
    s.p = (s.p + s.n * .01 + np.array([0, 1, 0], np.float32) * lift * w).astype(np.float32)
    return s


def grey(img, mean=.85):
    """쿠션 텍스처: 회색으로 바꾸고 평균 밝기를 맞춘다(색은 앱이 baseColorFactor 로 칠함)."""
    from PIL import Image
    a = np.asarray(img.convert("L"), np.float32) / 255
    a = np.clip(a * (mean / max(a.mean(), 1e-3)), 0, 1)
    return Image.fromarray((a * 255 + .5).astype(np.uint8)).convert("RGB")


def make_scene():
    g = Gltf()
    roots = []
    # 받침판: 윗면 흰색 한 장 + 옆면 모래색 두꺼운 한 겹(64번 23) + 아래 옅은 그림자
    plate = g.material("plate", hexrgb("#F4F4F2"), .9)
    rim = g.material("rim", hexrgb("#E9E2D6"), .9)
    shade = g.material("shade", [0, 0, 0], 1.0, alpha=.07)
    roots.append(g.node("plate", xf(cylinder(PLATE_R, PLATE_R, .06, 56), (0, -.03, 0)), plate))
    roots.append(g.node("rim", merge([xf(cylinder(PLATE_R, PLATE_R - .04, .3, 56, caps=False), (0, -.21, 0)),
                                       xf(cylinder(PLATE_R - .04, PLATE_R - .04, .01, 56), (0, -.36, 0))]), rim))
    roots.append(g.node("plate_shadow", soft_disc(PLATE_R + .35, -.45, 1, .9, 64), shade))
    white = [1.0, 1.0, 1.0]
    snow = g.material("snow", hexrgb("#FFFFFF"), .95)
    def tex(name, img):
        return g.texture(name, small(img))

    # 나무(pr_tree2, 11/09): 오른쪽 앞 맨가지 끝에 새가 앉는다. 잎(초록)만 tree_crown 으로 떼어 흔든다
    tm_, timg = read_prop("tree2")
    t_tex = tex("tree", timg)
    col = tri_rgb(tm_, timg)
    leafy = (col[:, 1] > col[:, 0] + .04) & (col[:, 1] > col[:, 2] + .04) & (tri_center(tm_)[:, 1] > 1.4)
    roots.append(g.node("tree_trunk", sub(tm_, ~leafy), g.material("trunk", white, .9, tex=t_tex), t=(TREE_XZ[0], 0, TREE_XZ[1])))
    crown = sub(tm_, leafy, (0, -CROWN_PIVOT, 0))
    cap = snow_cap(crown, xf(tm_, (0, -CROWN_PIVOT, 0)))
    cy = float(cap.p[:, 1].min())   # 눈은 아래 끝을 원점으로(앱이 높이 0 → 1 로 키워 소복이 쌓이게)
    snow_tree = g.node("snow_tree", sub(cap, np.ones(cap.tris, bool), (0, -cy, 0)), snow, t=(0, cy, 0))   # 잎과 같이 흔들리게 잎의 자식
    roots.append(g.node("tree_crown", crown, g.material("leaf", white, .85, tex=t_tex), t=(TREE_XZ[0], CROWN_PIVOT, TREE_XZ[1]), children=[snow_tree]))
    bcap = snow_cap(tm_, tm_, keep=~leafy, up=.55, lift=.03)   # 가지 위 눈(앉는 가지 포함, 흔들리지 않음)
    by = float(bcap.p[:, 1].min())
    roots.append(g.node("snow_branch", sub(bcap, np.ones(bcap.tris, bool), (0, -by, 0)), snow, t=(TREE_XZ[0], by, TREE_XZ[1])))

    # 가로등(pr_lamp): 기둥은 텍스처, 둥근 유리는 단색 재질(밤에 앱이 호박색으로 켠다). 깜빡이지 않는다
    lm_, limg = read_prop("lamp")
    glass_k = tri_center(lm_)[:, 1] > 2.2
    roots.append(g.node("lamp_pole", sub(lm_, ~glass_k), g.material("pole", white, .85, tex=tex("lamp", limg)), t=(LAMP_XZ[0], 0, LAMP_XZ[1])))
    head = sub(lm_, glass_k)
    hy = float((head.p[:, 1].min() + head.p[:, 1].max()) / 2)
    roots.append(g.node("lamp_head", sub(head, np.ones(head.tris, bool), (0, -hy, 0)), g.material("lamp_glass", hexrgb("#F3EDE2"), .4, emissive=True),
                        t=(LAMP_XZ[0], hy, LAMP_XZ[1])))
    lcap = snow_cap(head, head, up=.6, lift=.035)
    ly = float(lcap.p[:, 1].min())
    roots.append(g.node("snow_lamp", sub(lcap, np.ones(lcap.tris, bool), (0, -ly, 0)), snow, t=(LAMP_XZ[0], ly, LAMP_XZ[1])))
    # 밤 빛 웅덩이(11/10): 가로등 발치에서 둥글게 옅어지는 따뜻한 빛(가장자리 없는 흐림 텍스처, 받침판 밖으로는 안 나감). 점광원은 CPU가 커서 이걸로 바닥 빛을 그린다
    soft = g.texture_png("soft", radial_png(128, lambda d: 1 - smooth(d)))
    pool = g.material("lamp_pool", hexrgb("#FFE2B0"), 1.0, alpha=.0, tex=soft, unlit=True)
    roots.append(g.node("lamp_pool", plate_decal(LAMP_XZ[0] + .8, LAMP_XZ[1] + 1.15, 3.2, 3.0, .014), pool))
    # 젖은 바닥에 비친 가로등(11/10): 가로등 발치에서 카메라 쪽으로 길게 늘어진 옅은 따뜻한 빛(비 올 때만, 앱이 젖은 정도 × 켜짐 정도로 칠함)
    roots.append(g.node("lamp_wet", plate_decal(LAMP_XZ[0] + .45, LAMP_XZ[1] + 3.0, .5, 2.6, .018), g.material("lamp_wet", hexrgb("#FFE2B0"), 1.0, alpha=0.0, tex=soft, unlit=True)))
    # 가로등 빛 번짐(11/10): 유리 둘레로 번지는 따뜻한 빛. 카메라를 보는 네모에 둥근 흐림(빛을 받지 않는 색), 앱이 켜짐 정도만큼 진하게
    glow = g.texture_png("glow", radial_png(128, lambda d: (1 - d) ** 2.4))
    roots.append(g.node("lamp_halo", facing_quad(1.7, 1.7, (LAMP_XZ[0], hy, LAMP_XZ[1]), EYE),
                        g.material("lamp_halo", hexrgb("#FFD9A0"), 1.0, alpha=0.0, tex=glow, unlit=True)))
    # 바닥 그림자(가짜, 흐린 타원 12~20%): 나무·가로등·벤치는 한 덩어리, 쿠션은 쿠션과 같이 보이고 숨게 자리마다
    bx, bz, byaw = BENCH
    roots.append(g.node("shadows", merge([xf(soft_disc(1.35, .012, 1.15, .8), (TREE_XZ[0] + .25, 0, TREE_XZ[1] + .15)),
                                           xf(soft_disc(.36, .012), (LAMP_XZ[0], 0, LAMP_XZ[1])),
                                           xf(soft_disc(.5, .012, 1.35, .7), (bx, 0, bz), (0, byaw, 0))]), g.material("shadow", [0, 0, 0], 1.0, alpha=.09)))
    # 벤치(pr_bench, 11/09 추가): 오른쪽 뒤 가장자리(가로등과 맞은편). 쿠션 4·5번 뒤 0.6 넘게 떨어져 앉은 사람을 가리지 않고, 나무·말 거는 자리와 멀다
    bm_, bimg = read_prop("bench")
    roots.append(g.node("bench", bm_, g.material("bench", white, .85, tex=tex("bench", bimg)), t=(bx, 0, bz), yaw=byaw))
    # 풀 7포기(pr_grass 한 메시를 나눠 씀): 포기마다 돌려 같은 모양이 안 보이게
    gm_, gimg = read_prop("grass")
    grass = g.material("grass", white, .9, tex=tex("grass", gimg))
    for k, deg in enumerate(GRASS_DEG):
        ph = math.radians(deg)
        roots.append(g.node(f"grass{k + 1}", gm_, grass, t=(3.72 * math.cos(ph), 0, 3.72 * math.sin(ph)), s=(1 + (k % 3) * .12,) * 3, yaw=k * 2.1))
    # 빈백 쿠션 5(pr_cushion 한 메시를 나눠 씀). 텍스처는 회색, 색은 재질 cushion1..5 를 앱이 칠한다(stageColors)
    cm_, cimg = read_prop("cushion")
    c_tex = g.texture("cushion", small(grey(cimg)))
    plus = merge([xf(box(.30, .08, .05), (0, .80, -.06)), xf(box(.08, .30, .05), (0, .80, -.06))])
    for i in range(5):
        x, _, z = cushion_pos(i)
        yw = yaw_to(x, z)
        mat = g.material(f"cushion{i + 1}", hexrgb("#B9BCC2"), .9, tex=c_tex)
        roots.append(g.node(f"cushion{i + 1}", cm_, mat, t=(x, 0, z), yaw=yw))
        roots.append(g.node(f"cshadow{i + 1}", soft_disc(.82, .012), g.material("shadow", [0, 0, 0], 1.0, alpha=.09), t=(x, 0, z + .08)))
        roots.append(g.node(f"plus{i + 1}", plus, g.material("plus", hexrgb("#FFFFFF"), .6), t=(x, 0, z), yaw=yw))
    # 말 거는 자리: 높이 0.12 돌판(64번 24). PlazaView 의 talk 높이와 같게
    roots.append(g.node("talk", cylinder(.85, .85, .12, 40), g.material("talk", hexrgb("#EBDCC6"), .9), t=(TALK[0], .06, TALK[2])))
    # ---- 11/08 추가 소품(64번 21·24·25·26·27). 소품 색은 #F4F4F2 #E4DED4 #B58A64 #8A5A3C #9CC48A #4A4E55 + 흰·크림 꽃만
    roots.append(g.node("lawn", lawn(), g.material("lawn", hexrgb("#E6EEDC"), .95)))
    sm_, simg = read_prop("stone")
    roots.append(g.node("stones", merge([xf(sm_, (x, 0, z), (0, k * 1.3, 0), (1 + k * .08, .6, .85 - k * .05)) for k, (x, z) in enumerate(STONES)]),
                        g.material("stone", white, .9, tex=tex("stone", simg))))
    # 화분(pr_pot): 화분 몸통은 가만히, 잎·꽃(pot_flowers, 원점 = 흙 높이 .2)만 흔들린다. 카메라 쪽을 보게
    pm_, pimg = read_prop("pot")
    p_tex = tex("pot", pimg)
    pc = tri_center(pm_); col = tri_rgb(pm_, pimg); green = (col[:, 1] > col[:, 0] + .04) & (col[:, 1] > col[:, 2] + .04)
    body = ~green & (pc[:, 1] < .3)   # 흙·테두리까지 몸통(흔들려도 화분 테두리가 갈라지지 않게), 잎과 그 위 꽃만 흔들림
    soil = .2
    pyaw = yaw_to(*POT_XZ)
    roots.append(g.node("pot", sub(pm_, body), g.material("pot", white, .85, tex=p_tex), t=(POT_XZ[0], 0, POT_XZ[1]), yaw=pyaw))
    flowers = sub(pm_, ~body, (0, -soil, 0))
    pcap = snow_cap(flowers, flowers, up=.55, lift=.03)
    py = float(pcap.p[:, 1].min())
    snow_pot = g.node("snow_pot", sub(pcap, np.ones(pcap.tris, bool), (0, -py, 0)), snow, t=(0, py, 0))   # 꽃과 같이 흔들리게 자식
    roots.append(g.node("pot_flowers", flowers, g.material("flowers", white, .85, tex=p_tex), t=(POT_XZ[0], soil, POT_XZ[1]), yaw=pyaw, children=[snow_pot]))
    # 비: 물웅덩이 2개(비 올 때만)
    # 가장자리는 흐림 텍스처로 부드럽게(두 겹 원판의 띠가 보이지 않게, 11/10). 색·하늘 비침은 앱이 칠한다
    edge = g.texture_png("edge", radial_png(64, lambda d: 1 - smooth(np.clip((d - .45) / .55, 0, 1))))
    roots.append(g.node("puddles", merge([xf(disc_uv(1, 32, .016), (x, 0, z), s=(sx, 1, sz)) for x, z, sx, sz in PUDDLES]),
                        g.material("puddle", hexrgb("#A9B8C8"), .1, alpha=.35, tex=edge)))
    # 눈사람(pr_snowman): 몸통+팔(snowman1, 원점 바닥)·머리(snowman2, 원점 목 .6) 따로. 앱이 단계마다 원점 기준으로 키운다. 눈·코는 텍스처
    nm_, nimg = read_prop("snowman")
    n_tex = tex("snowman", nimg)
    nc = tri_center(nm_); col = tri_rgb(nm_, nimg)
    twig = (col[:, 0] > col[:, 2] + .12) & (col[:, 0] > .25)   # 갈색 나뭇가지 팔
    neck = .6
    headk = (nc[:, 1] > neck - .005) & ~twig
    nyaw = yaw_to(*SNOWMAN_XZ)
    snowm = g.material("snowman", white, .9, tex=n_tex)
    roots.append(g.node("snowman1", sub(nm_, ~headk), snowm, t=(SNOWMAN_XZ[0], 0, SNOWMAN_XZ[1]), yaw=nyaw))
    roots.append(g.node("snowman2", sub(nm_, headk, (0, -neck, 0)), snowm, t=(SNOWMAN_XZ[0], neck, SNOWMAN_XZ[1]), yaw=nyaw))
    # 충전 기둥(pr_charger, 충전구 열면 땅에서 올라옴): 케이블이 카메라 쪽. 위쪽 띠 자리에 배터리 5칸 고리(숫자 없음, 띠를 덮음)
    hm_, himg = read_prop("charger")
    segs = []
    arc = 2 * PI / 5 - .12
    for k in range(5):
        a0 = PI / 2 - k * 2 * PI / 5
        seg = merge([torus(.21, .047, 6, 6, arc)] + [ball(.047, (.21 * math.cos(a), .21 * math.sin(a), 0), ws=8, hs=5) for a in (0, arc)])   # 칸 끝은 둥글게 막음
        segs.append(g.node(f"charge_seg{k + 1}", xf(xf(seg, r=(0, 0, a0 - arc / 2)), r=(PI / 2, 0, 0)),
                           g.material(f"charge_seg{k + 1}", hexrgb("#E4DED4"), .7), t=(0, .625, -.055)))
    roots.append(g.node("charger", hm_, g.material("post", white, .8, tex=tex("charger", himg)),
                        t=(CHARGER_XZ[0], 0, CHARGER_XZ[1]), yaw=yaw_to(*CHARGER_XZ), children=segs))
    # 새는 뼈 동작이 있어 따로 plaza_bird.glb(앱이 Animator 로 재생). 앉는 자리는 BIRD_PERCH
    # 비·눈(11/08 밤): 2D 층으로 그리면 매 장 비용이 커서(비 올 때 CPU 2배) 3D 장면 안에 한 덩어리로 넣고 앱이 아래로 흘린다.
    # 같은 덩어리 둘(a·b)을 위아래로 이어 놓고 높이 FX_H 만큼 돌린다. 돔 안·말 거는 자리 앞(얼굴 쪽)에는 두지 않는다
    rng = np.random.default_rng(7)
    def fx_points(n):
        pts = []
        while len(pts) < n:
            x = rng.uniform(-6.2, 6.2); z = rng.uniform(-6.5, 1.2); y = rng.uniform(0, FX_H)
            if math.hypot(x, z) < 4.75 and y < 4.8: continue          # 돔 안
            if z > -1.0 and abs(x) < 4.9: continue                    # 받침판 앞쪽(사람 얼굴 앞)
            pts.append((x, y + FX_Y0, z))
        return pts
    rain = []
    for x, y, z in fx_points(150):
        edge = max(0.35, 1 - max(0.0, abs(x) - 4.2) / 2.2)            # 칸 양끝으로 갈수록 가늘게(칸 모양으로 끊겨 보이지 않게)
        rain.append(xf(box(.018 * edge, .42, .018 * edge), (x, y, z), (0, 0, .12)))
    rain_m = merge(rain); rain_mat = g.material("rain", hexrgb("#8A9AAD"), .6, alpha=.55)
    flakes = []
    for x, y, z in fx_points(170):
        flakes.append(ball(.065, (x, y, z), ws=4, hs=2))
    snow_m = merge(flakes); snow_mat = g.material("snowfx", hexrgb("#FFFFFF"), .9, alpha=.9, emissive=True)   # 앱이 스스로 빛나게 해서 하얗게
    for k in ("a", "b"):
        roots.append(g.node(f"rain_{k}", rain_m, rain_mat))
        roots.append(g.node(f"snowfx_{k}", snow_m, snow_mat))
    roots.append(g.node("leaf_fall", ball(.07, (0, 0, 0), (1, .25, .6), ws=8, hs=4), g.material("leaf_fall", hexrgb("#9CC48A"), .85), t=(0, -5, 0)))
    roots.append(g.node("snow_rim", xf(torus(PLATE_R - .12, .16, 6, 56), r=(PI / 2, 0, 0), s=(1, 1, .5)), snow, t=(0, .02, 0)))
    dome = g.material("dome", hexrgb("#EAF4FF"), .08, alpha=.16)
    roots.append(g.node("dome", sphere(PLATE_R + .25, 36, 14, 0, 2 * PI, 0, PI / 2), dome))
    # 바탕 흐린 빛(11/10): 장면 뒤 멀리, 카메라를 보는 큰 네모에 둥근 흐림. 비·눈·밤에 바탕색보다 조금 밝은 빛이 받침판 뒤에서 퍼지고
    # 가장자리는 바탕색 그대로(투명 0)라 오른쪽 정보 칸과 경계가 생기지 않는다. 색·진하기는 앱이 정한다(맑은 낮은 숨김)
    fwd = np.asarray(LOOK) - np.asarray(EYE); fwd = fwd / np.linalg.norm(fwd)
    hz = np.asarray(EYE) + fwd * 24 + np.array([0, 2.6, 0])
    roots.append(g.node("haze", facing_quad(17, 21, hz, EYE),
                        g.material("haze", [1, 1, 1], 1.0, alpha=0.0, tex=g.texture_png("haze", radial_png(128, lambda d: (1 - smooth(d)) ** 1.6)), unlit=True)))
    n = g.write(os.path.join(OUT, "plaza_scene.glb"), roots)
    return n, g.tris, g.tex_bytes


def make_bird():
    """새(pr_bird.glb: 뼈 6개 + 동작 7개, 텍스처 512)는 그대로 복사한다. 앱이 Animator 로 재생."""
    import shutil
    dst = os.path.join(OUT, "plaza_bird.glb")
    shutil.copyfile(os.path.join(PROPS_DIR, "pr_bird.glb"), dst)
    return os.path.getsize(dst)


# ---------------------------------------------------------------- 캐릭터 더미
HEAD_SCALE = .92
HIP_Y = .46          # 엉덩이 관절 높이(뿌리 기준). PlazaView.HIP_Y 와 같게


def make_char():
    g = Gltf()
    skin = g.material("skin", hexrgb("#F2C9AC"), .8)
    cloth = g.material("cloth", hexrgb("#5AA9F0"), .9)
    pants = g.material("pants", hexrgb("#5B6270"), .9)
    shoe = g.material("shoe", hexrgb("#454A52"), .8)
    hairm = g.material("hair", hexrgb("#4A3226"), .9, double=True)
    face = g.material("face", [1, 1, 1], .8, texture=True)
    beardw = g.material("beardW", hexrgb("#F2F0EC"), .95)
    metal = g.material("metal", hexrgb("#8E949C"), .35, .6)
    horn = g.material("horn", hexrgb("#2B2522"), .5)
    tie = g.material("tie", hexrgb("#E58A9A"), .8)

    # 다리: 엉덩이 관절이 노드 원점. 다리는 아래로(-y), 신발은 끝
    legs = []
    for s, nm in ((-1, "L"), (1, "R")):
        shoe_n = g.node(f"shoe{nm}", ball(.13, (0, -.40, .05), (1, .55, 1.35), ws=10, hs=6), shoe)
        legs.append(g.node(f"leg{nm}", xf(capsule(.115, .2, 3, 10), (0, -.17, 0)), pants, t=(s * .15, HIP_Y, 0), children=[shoe_n]))

    # 팔: 어깨가 노드 원점. 바깥으로 조금 벌린 채 아래로(avatar3d.js rotation.z = ±0.32)
    arms = []
    for s, nm in ((-1, "L"), (1, "R")):
        hand = g.node(f"hand{nm}", xf(ball(.12, (0, -.38, .01), (1, 1.05, .95), ws=10, hs=7), r=(0, 0, s * .32)), skin)
        arm = xf(xf(capsule(.095, .24, 3, 10), (0, -.16, 0)), r=(0, 0, s * .32))
        arms.append(g.node(f"arm{nm}", arm, cloth, t=(s * .31, .52, 0), children=[hand]))

    # 머리: 노드 원점 = 머리 가운데(머리 공간은 avatar3d.js 와 같은 R=0.5, 노드 스케일 0.92)
    head_kids = [g.node("face", sphere(R * 1.004, 12, 12, PI / 2 - FACE_PHI / 2, FACE_PHI, TH0, FACE_THETA), face)]
    for k in range(14):
        hm = hair(k)
        if hm is None:
            head_kids.append(g.node(f"hair{k}"))
        else:
            head_kids.append(g.node(f"hair{k}", hm, hairm))
    head_kids.append(g.node("hairtie7", hair_tie(), tie))
    head_kids.append(g.node("beard2", beard(2), hairm))
    head_kids.append(g.node("beard3", beard(3), beardw))
    head_kids.append(g.node("glasses1", glasses(1), metal))
    head_kids.append(g.node("glasses2", glasses(2), horn))
    head_kids.append(g.node("glasses3", glasses(3), metal))
    head_mesh = merge([sphere(R, 14, 10)] + [ball(.1, (s * R * .98, -.03, -.02), (.6, 1, .8), ws=8, hs=6) for s in (-1, 1)])
    head = g.node("head", head_mesh, skin, t=(0, .96, 0), s=(HEAD_SCALE,) * 3, children=head_kids)

    # 몸(대표색 옷): 엉덩이 높이가 원점. 팔·머리는 몸 아래에 붙어 같이 기울어진다
    torso = xf(capsule(.31, .2, 4, 14), (0, .30, 0), s=(1, 1, .88))
    # 책(산책 중·앉아서 읽기): 가슴 앞, 위가 얼굴 쪽으로 기울게. 평소엔 앱이 크기 0으로 숨긴다
    pages = g.node("book_pages", merge([xf(box(.12, .02, .18), (s * .066, .022, 0), (0, 0, s * -.08)) for s in (-1, 1)]), g.material("pages", hexrgb("#F6F1E4"), .9))
    book = g.node("book", merge([xf(box(.12, .022, .19), (s * .064, 0, 0), (0, 0, s * -.08)) for s in (-1, 1)]), g.material("book", hexrgb("#B58A64"), .8),
                  t=(0, .40, .36), children=[pages])
    book_r = g.nodes[book]; book_r["rotation"] = [float(v) for v in quat_x(-.55)]
    body = g.node("body", torso, cloth, t=(0, HIP_Y, 0), children=arms + [head, book])
    root = g.node("char", t=(0, 0, 0), children=legs + [body])
    # 사람 바닥 그림자(따로 뿌리: 앱이 서 있는 자리 바닥에 둔다, 키·체형 스케일을 받지 않게)
    shadow = g.node("shadow", soft_disc(.42, 0), g.material("shadow", [0, 0, 0], 1.0, alpha=.1))
    n = g.write(os.path.join(OUT, "plaza_char.glb"), [root, shadow])
    return n, g.tris


def visible_tris_estimate():
    base = sum(m.tris for m in [sphere(R, 14, 10), sphere(R * 1.004, 12, 12, 0, 1, 0, 1)]) + 2 * 96
    body = capsule(.31, .2, 4, 14).tris + 2 * (capsule(.095, .24, 3, 10).tris + sphere(1, 10, 7).tris + capsule(.115, .2, 3, 10).tris + sphere(1, 10, 6).tris)
    worst_hair = max((hair(k).tris if hair(k) is not None else 0) for k in range(14))
    return base + body, worst_hair


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    sn, st, sx = make_scene()
    bn = make_bird()
    cn, ct = make_char()
    b, h = visible_tris_estimate()
    print(f"plaza_scene.glb {sn / 1024:.0f}KB, 삼각형 {st}(비·눈·눈 캡 포함, 노드마다 셈), 텍스처 약 {sx / 2**20:.1f}MB(RGBA8+밉맵)")
    print(f"plaza_bird.glb  {bn / 1024:.0f}KB (pr_bird.glb 그대로)")
    print(f"plaza_char.glb  {cn / 1024:.0f}KB, 파일 안 삼각형 {ct} (머리 14종 전부 포함)")
    print(f"한 명이 보일 때: 몸·얼굴 {b} + 머리카락 최대 {h} = 최대 {b + h} (안경·수염 더하면 조금 더)")
    for k in range(14):
        m = hair(k)
        print(f"  hair{k}: {m.tris if m else 0}")
