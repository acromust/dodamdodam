# 도담도담 얼굴 부품 아틀라스: GPT가 그린 투명 부품 그림(dev_parts_1109) → 앱 assets/face_atlas.png + face_atlas.json
#
#  1) 그림판에서 부품을 투명 덩어리별로 자동 분리(알파 연결 덩어리).
#  2) 문서 56 '11/09 새벽 개발용 얼굴 부품' 정면 배치(1024 그림, 512px = 머리 반지름)에 놓는다.
#     (asm_test_1109_dev.png 를 만든 조립 스크립트의 배율 KE·KB·KN 그대로)
#  3) 앱 얼굴 조각(plaza_char2.glb 'face')은 공 모양 펼침 UV라 정면 배치와 비율이 다르다.
#     face_uvmap.py 가 실제 얼굴 면을 쏴서 만든 대응표로, 부품을 face.png 칸 좌표로 '미리 휘어서' 잘라 둔다.
#     → 앱은 좌표 계산 없이 칸(dst)에 붙이기만 하면 정면에서 시험 조립 그림과 같은 자리·비율로 보인다.
#  4) 눈은 그려 온 왼쪽·오른쪽 한 쌍을 따로 휜다(11/10 78·79번: 흰자 + 눈동자 + 윗눈꺼풀, 눈동자는 따뜻한 검정, 기준점 = 눈동자 원 가운데). 눈썹·볼터치·눈가 주름은 왼쪽만 담고 앱이 좌우로 뒤집어 한 번 더.
#  5) 눈썹·짧은 수염은 회색/회갈색 명암만 담고 앱이 머리색·수염색을 곱한다(mean = 기준 밝기).
#  6) 피부색 맞춤(11/10, 짙은 피부에서 주름·코·볼터치가 안 보이던 것): 주름·코·볼터치도 회색 명암만 담고 앱이 피부에 맞는 색을 곱한다.
#     t = 피부 밝기(luma)를 skin_t 범위로 0(짙은 갈색)~1(밝은)로 편 값. 층(layer) 칸:
#       tint "skin": 색 = 피부색 × (k[1] + (k[0]-k[1])·t)   — 주름·코 그림자: 피부보다 한 단 어둡게, 짙은 피부일수록 조금 더
#       tint "pair": 색 = c[1] + (c[0]-c[1])·t                — 볼터치: 밝은 피부는 분홍, 짙은 피부는 진한 장밋빛
#       sep D(머리색·수염색): 그 색과 피부 밝기 차가 D보다 작으면 피부 밝기 - D 까지 어둡게(금발·흰머리 눈썹이 밝은 피부에 묻히지 않게)
#       alpha_dark: 짙은 피부 쪽 alpha(그 사이는 t로 섞음)
#     FaceSheet.kt · avatar3d.js · 아래 compose() 가 같은 식이다(바꾸면 셋 다).
#
# 실행: python3 face_atlas.py [--parts DIR] [--map face_uvmap.npz] [--out ASSETS_DIR] [--sheet CONTACT.png] [--faces DIR]
import argparse, json, math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
# GPT 부품 그림 폴더: 인자로 주거나 DODAM_REFS(style_refs 폴더) 아래 dev_parts_*. 저장소에는 원본 그림을 넣지 않는다
REFS = os.environ.get("DODAM_REFS", os.path.join(HERE, "style_refs"))
ap.add_argument("--parts", default=os.path.join(REFS, "dev_parts_1109"))
ap.add_argument("--parts2", default=os.path.join(REFS, "dev_parts_1110"))
ap.add_argument("--parts3", default=os.path.join(REFS, "dev_parts_1110b"))   # 11/10 흰자 눈(78·79번)·긴 꼬리 눈썹
ap.add_argument("--parts4", default=os.path.join(REFS, "dev_parts_1110d"))   # 11/10 84번 Mii풍 개성 눈(굵은 선·라이너·곁눈)
ap.add_argument("--parts5", default=os.path.join(REFS, "dev_parts_1110e"))   # 11/10 점·주근깨(83번 5절 (b))
ap.add_argument("--web", default=os.path.normpath(os.path.join(HERE, "../../../server/web/avatar")))   # 같은 두 파일을 웹에도(빈 문자열이면 안 씀)
ap.add_argument("--check"); ap.add_argument("--check-base")   # --check-base: 바꾸기 전 아틀라스 폴더(다시 그린 작은 눈·다문 입 비교용)                               # 새 부품 검사 시트 폴더(피부 5 × 새 부품, 지금 부품과 나란히)
ap.add_argument("--map", default=os.path.join(HERE, "face_uvmap.npz"))
ap.add_argument("--out", default=os.path.normpath(os.path.join(HERE, "../../app/src/main/assets")))
ap.add_argument("--sheet"); ap.add_argument("--faces")
ap.add_argument("--nf", type=int, default=512)          # 부품을 이 크기 얼굴 그림 기준으로 담는다(앱 FACE_PX보다 크게 두고 줄여 씀)
ap.add_argument("--name", default="face_atlas")          # 내보낼 파일 이름(.png·.json)
# 11/10 사장 '코·입 고르는 칸이 아직 흐림': 칸(390 폭 3칸, DPR3 약 340px)이 얼굴 512 기준 그림(코·입 칸 174px)을 늘려 그렸다.
# → 웹 고르는 칸만 쓰는 큰 아틀라스(얼굴 1024 기준, face_atlas_hd)를 같은 층·같은 칸으로 한 벌 더 만든다. GPT 원본은 얼굴 1024 기준으로
#   입 0.83·코 0.96·눈 약 1.2 배라 1024 가 원본 해상도와 거의 같다(더 키우면 늘린 그림). 차·웹 3D 얼굴은 지금 512 아틀라스 그대로(차 메모리).
ap.add_argument("--hd-nf", type=int, default=1024)       # 0 이면 큰 아틀라스를 안 만듦(--web 이 있을 때만 만든다)
ap.add_argument("--webp", action="store_true")          # 그림을 무손실 WebP 로(큰 아틀라스: PNG 2.4MB → 1.6MB, 값은 같음)
ap.add_argument("--stub-k", type=float, default=0.58)    # 짧은 수염 그림 배율(1254 그림 → 1024 정면 배치)
ap.add_argument("--stub-gain", type=float, default=5.0)  # 짧은 수염 진하기(원본 최대 불투명도 52/255에 곱함)
A = ap.parse_args()
NF, SS = A.nf, 2                                         # 2배로 휘어 그린 뒤 줄여서 계단 없애기

# ── 1. 부품 자르기 ─────────────────────────────────────────────────────────────
def load(f): return np.array(Image.open(os.path.join(A.parts, f)).convert("RGBA")).astype(np.float32) / 255
def split(f, rows=1):
    im = load(f); a = im[..., 3] > 8 / 255
    lab, n = ndi.label(ndi.binary_dilation(a, iterations=6)); objs = ndi.find_objects(lab)
    if rows == 1:   # 한 줄 그림: 가로 범위가 겹치는 덩어리는 한 부품(이마 주름 선 3개 등)
        ids = [i for i, s in enumerate(objs) if (lab[s] == i + 1).sum() >= 400]; ids.sort(key=lambda i: objs[i][1].start)
        grp = []
        for i in ids:
            if grp and objs[i][1].start < max(objs[j][1].stop for j in grp[-1]): grp[-1].append(i)
            else: grp.append([i])
    else: grp = [[i] for i, s in enumerate(objs) if (lab[s] == i + 1).sum() >= 400]
    items = []
    for g in grp:
        y0 = min(objs[i][0].start for i in g); y1 = max(objs[i][0].stop for i in g)
        x0 = min(objs[i][1].start for i in g); x1 = max(objs[i][1].stop for i in g)
        crop = im[y0:y1, x0:x1].copy(); crop[..., 3] *= np.isin(lab[y0:y1, x0:x1], [i + 1 for i in g])
        items.append(((y0 + y1) / 2, (x0 + x1) / 2, crop))
    if rows == 2:
        mid = np.median([y for y, _, _ in items])
        items = sorted([t for t in items if t[0] < mid], key=lambda t: t[1]) + sorted([t for t in items if t[0] >= mid], key=lambda t: t[1])
    else: items = sorted(items, key=lambda t: t[1])
    return [c for _, _, c in items]
EYES = split("face_eyes7.png")                         # 그림 순서 = 앱 eyes 0~6 (동그란·큰·작은·긴·실눈·반달눈·순한 눈)
BM = split("face_brows_mouths.png", 2)                 # 윗줄 눈썹 0~3(짧은·아치·일자·숱 많은), 아랫줄 입 0~3(미소·활짝·다문·동그란)
NW = split("face_nose_wrinkle_blush.png")              # 코 0~2(작은·동그란·넓은), 눈가 주름, 이마 주름, 볼터치
assert len(EYES) == 7 and len(BM) == 8 and len(NW) == 6, (len(EYES), len(BM), len(NW))
BROWS, MOUTHS, NOSES = BM[:4], BM[4:], NW[:3]
WR_EYE, WR_FORE, BLUSH = NW[3], NW[4], NW[5]
STUB = load("face_stubble.png")                        # 얼굴 전체 크기 한 장(입 자리 비움)

# ── 1b. 11/10 새 부품(문서 76 B·C절, dev_parts_1110) ─────────────────────────────
# 시트마다 첫 칸 = 지금 부품을 다시 그린 기준 칸 → 그 칸과 지금 부품의 크기 비로 시트 전체 배율(s)을 정하고 기준 칸은 버린다.
# 칸 자르기: 작은 점(<200px)을 지운 뒤 가로·세로 빈 줄로 나눈다(쌍꺼풀 선·속눈썹처럼 떨어진 조각도 같은 칸이면 한 부품).
def cells(f, rows=1, ncol=None, gap=20):
    im = np.array(Image.open(os.path.join(A.parts2, f)).convert("RGBA")).astype(np.float32) / 255
    a = im[..., 3] > 8 / 255; lab, n = ndi.label(a)
    keep = np.isin(lab, [i + 1 for i, c in enumerate(ndi.sum(a, lab, range(1, n + 1))) if c >= 200])
    def runs(m, gap):
        idx = np.nonzero(m)[0]; out = []
        for i in idx:
            if out and i <= out[-1][1] + gap: out[-1][1] = i + 1
            else: out.append([i, i + 1])
        return out
    rr = runs(keep.any(1), gap); assert len(rr) == rows, (f, rr)
    out = []
    for y0, y1 in rr:
        cc = runs(keep[y0:y1].any(0), gap); assert ncol is None or len(cc) == ncol, (f, cc)
        row = []
        for x0, x1 in cc:
            ys, xs = np.nonzero(keep[y0:y1, x0:x1]); m = 4
            Y0, Y1, X0, X1 = y0 + ys.min() - m, y0 + ys.max() + 1 + m, x0 + xs.min() - m, x0 + xs.max() + 1 + m
            c = im[Y0:Y1, X0:X1].copy(); c[..., 3] *= keep[Y0:Y1, X0:X1]; row.append(c)
        out.append(row)
    return out if rows > 1 else out[0]

def bbox(img, rel=0.3):
    """알파가 최대의 rel 이상인 상자(x0,y0,x1,y1). 기준 칸·지금 부품을 같은 방식으로 재야 배율이 맞다."""
    a = img[..., 3]; ys, xs = np.nonzero(a > rel * a.max())
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1

def calib(new, old, what):
    """기준 칸(new) → 지금 부품(old) 배율. 가로·세로 비의 기하 평균, 둘 차이를 같이 알린다."""
    nx0, ny0, nx1, ny1 = bbox(new); ox0, oy0, ox1, oy1 = bbox(old)
    sw, sh = (ox1 - ox0) / (nx1 - nx0), (oy1 - oy0) / (ny1 - ny0)
    print(f"  기준 칸 {what}: 가로비 {sw:.3f} 세로비 {sh:.3f} → s {math.sqrt(sw * sh):.3f}")
    return math.sqrt(sw * sh)

def line_anchor(img):
    """가장 큰 검은 덩어리의 상자 가운데(입: 메롱 혀·시원한 웃음 입 안이 아니라 입 선 기준). 검은 덩어리가 없으면 None(상자 가운데)."""
    y = img[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    m = (img[..., 3] > 0.5) & (y < 0.3); lab, n = ndi.label(m)
    if n == 0 or m.sum() < 50: return None
    big = 1 + int(np.argmax(ndi.sum(m, lab, range(1, n + 1)))); ys, xs = np.nonzero(lab == big)
    return ((xs.min() + xs.max() + 1) / 2, (ys.min() + ys.max() + 1) / 2)

NBR = cells("face_brows_new.png", 1, 6); NMO = cells("face_mouths_new.png", 1, 7); NLN = cells("face_lines_new.png", 1, 3)
S_BR = calib(NBR[0], BROWS[3], "눈썹(숱 많은)"); S_MO = calib(NMO[0], MOUTHS[0], "입(미소)"); S_LN = calib(NLN[0], WR_EYE, "얼굴 선(눈가 주름)")
NEW_BROWS = [(1, "각진 눈썹"), (2, "올라간 눈썹"), (3, "순한 눈썹"), (4, "가는 눈썹"), (5, "동글 눈썹")]   # → 눈썹 4~8
NEW_MOUTHS = [(2, "잔잔한 미소"), (3, "한쪽 미소"), (4, "시원한 웃음"), (5, "분홍 입술"), (6, "메롱")]       # → 입 4~8
TIGHT_MOUTH = 1                                        # 다문 입(2) 다시 그림: 꾹 다문 입
WR_MOUTH, WR_UNDER = NLN[1], NLN[2]                    # 입가 주름 '(', 눈 밑 선

# ── 2. 정면 배치(문서 56, 1024 그림 가운데 = 머리 중심, 512px = 반지름) ─────────
KE, KB, KN = 195 / 149, 215 / 304, 0.74                # 시험 조립(asm_test_1109_dev)과 같은 배율
# 짧은 수염: 입 구멍 가운데를 입 자리(0,+310)에 맞춘다
_sa = STUB[..., 3] < 1.5 / 255; _hl, _ = ndi.label(_sa)
_edge = set(np.unique(np.r_[_hl[0], _hl[-1], _hl[:, 0], _hl[:, -1]]))
_cands = [(int((_hl == i).sum()), i) for i in np.unique(_hl) if i not in _edge and i != 0]
_hole = _hl == max(_cands)[1]; _hy, _hx = [float(v.mean()) for v in np.nonzero(_hole)]
STUB_ANCHOR = (_hx, _hy)
def place(sprite, cx, cy, k, flip=False, anchor=None):
    return dict(img=sprite, cx=cx, cy=cy, k=k, flip=flip, anchor=anchor)
P_EYE_L = lambda s: place(s, -215, 51, KE)
P_EYE_R = lambda s: place(s, 215, 51, KE)
P_BROW = lambda s: place(s, -235, -150, KB)
P_MOUTH = lambda s: place(s, 0, 310, KB)
P_NOSE = lambda s: place(s, 0, 178, KN * 1.3)
P_WR_EYE_XY = (-315, 45)                             # 11/09: -335 는 바깥 끝 9%가 얼굴 그림 밖(테두리)이라 잘림 → -315(99% 이상 안쪽)
P_WR_MOUTH_XY = (-175, 245)                          # 11/10 입가 주름: 코(0,+178)와 입(0,+310) 사이 바깥(문서 76)
P_WR_UNDER_XY = (-215, 180)                          # 11/10 눈 밑 선: 큰 눈 아래 끝(정면 약 +151) 바로 아래. 문서 76 의 +140 은 큰 눈과 겹쳐 내림
WR_UNDER_K = 1.25                                    # 눈 밑 선은 기준 배율 그대로면 큰 눈 너비의 57%·선이 너무 가늘어 안 보임 → 1.25배(눈 너비의 약 70%, 문서 76)
WR_UNDER_A = 1.3                                     # 눈 밑 선 진하기(그림이 입가 주름의 약 70%로 옅게 그려짐 → 79번 한 단 진하게, 담을 때 알파 × 1.3)
WR_UNDER_KD = [0.60, 0.38]                           # 눈 밑 선 색 = 피부 × 0.60(밝은) ~ 0.38(짙은): 다른 주름(WR_K)보다 한 단 어둡게
LIP_DARK = 0.80                                      # 분홍 입술: 짙은 피부 쪽 색 = 그려 온 색 × 0.80
P_WR_FORE_XY = (0, -265)                             # 문서에 자리 없음: 눈썹 위 이마 가운데, 눈가 주름과 같은 배율(선 굵기 맞춤)
# 볼터치: 문서 56 자리(-330, 225, ×0.9)는 공 모양 펼침 UV가 담는 범위(그 높이에서 정면 ±321px) 밖으로 절반 가까이 나가
# 3/4 각도에서 반쪽·세모로 보였다(11/09) → 눈 아래 볼 쪽에 동그라미 전체가 들어가게(테두리 띠 밖 98.5% 이상) 조금 안쪽·위·작게
BLUSH_X, BLUSH_Y, BLUSH_K = -245, 210, KN * 0.9 * 0.85
P_STUB = place(STUB, 0, 310, A.stub_k, anchor=STUB_ANCHOR)

# ── 3. 정면 배치 → face.png 칸으로 휘기 ────────────────────────────────────────
MP = np.load(A.map); MAP = MP["map"]; MN = MAP.shape[0]
G = NF * SS
_jj, _ii = np.mgrid[0:G, 0:G].astype(np.float32)
_c = ((_jj + 0.5) / G * MN - 0.5, (_ii + 0.5) / G * MN - 0.5)
def _mapch(ch):
    m = MAP[..., ch].copy(); bad = ~np.isfinite(m)
    if bad.any():   # 빈 칸(모서리)은 가까운 값으로
        idx = ndi.distance_transform_edt(bad, return_distances=False, return_indices=True); m = m[tuple(idx)]
    return ndi.map_coordinates(m, _c, order=1, mode="nearest")
PX = 512 + _mapch(0) * 512; PY = 512 + _mapch(1) * 512   # face.png 칸마다 정면 1024 좌표
FV = (_jj + 0.5) / G

def warp(p):
    img = p["img"]; h, w = img.shape[:2]
    ax, ay = p["anchor"] if p["anchor"] else (w / 2, h / 2)
    dx = (PX - (512 + p["cx"])) / p["k"]; dy = (PY - (512 + p["cy"])) / p["k"]
    sx = (ax - dx if p["flip"] else ax + dx) - 0.5; sy = ay + dy - 0.5
    pm = img.copy(); pm[..., :3] *= pm[..., 3:4]           # 미리 곱한 알파로 보간
    out = np.stack([ndi.map_coordinates(pm[..., c], (sy, sx), order=1, cval=0.0) for c in range(4)], -1)
    return out

def downsample(pm):
    t = pm.reshape(NF, SS, NF, SS, 4).mean((1, 3))
    return t

def crop(pm, fade_bottom=False):
    if fade_bottom:   # 얼굴 조각 끝(턱 밑·귀 앞)에서 칼같이 잘리지 않게
        t = (np.arange(NF) + 0.5) / NF; sm = lambda x: (lambda c: c * c * (3 - 2 * c))(np.clip(x, 0, 1))
        pm = pm * sm((1 - t) / 0.06)[:, None, None] * sm(np.minimum(t, 1 - t) / 0.12)[None, :, None]
    a = pm[..., 3]; ys, xs = np.nonzero(a > 0.6 / 255)
    if len(ys) == 0: return None
    y0, y1, x0, x1 = max(ys.min() - 1, 0), min(ys.max() + 2, NF), max(xs.min() - 1, 0), min(xs.max() + 2, NF)
    c = pm[y0:y1, x0:x1].copy(); al = c[..., 3:4]
    c[..., :3] = np.where(al > 1e-6, c[..., :3] / np.maximum(al, 1e-6), 0)
    return c, (x0, y0, x1, y1)

def grey_mean(img):
    a = img[..., 3]; g = img[..., :3].mean(-1); m = a > 0.5 * a.max()
    return float(g[m].mean())

# face.png 테두리 띠: 얼굴 조각은 UV가 0~1 밖(-0.10~1.09, 귀 앞·턱 밑)까지 이어지고 텍스처는 CLAMP 라 테두리 칸 색이 그 밖으로 늘어난다.
# 테두리에 부품이 닿으면(볼터치 l=0, 11/09 폰 피드백 '볼에 분홍 번짐') 0~1 경계에서 칼같이 잘리고 그 밖으로 줄무늬처럼 번진다 →
# 모든 부품을 테두리 BORDER 폭 안에서 0으로 부드럽게 줄여, 테두리 칸은 항상 피부 바탕만 남게 한다(머리 피부와 같은 색으로 이어짐).
BORDER = 0.05
_sm = lambda x: (lambda c: c * c * (3 - 2 * c))(np.clip(x, 0, 1))
_t = (np.arange(NF) + 0.5) / NF; _e = _sm(np.minimum(_t, 1 - _t) / BORDER)
EDGE = (_e[:, None] * _e[None, :])[..., None]            # 좌우 대칭이라 mirror 부품에도 그대로 맞음

SPRITES = []   # (이름, 그림 float RGBA straight, dst 칸)
LOSS, FRONT = {}, {}
def add(name, p, fade=False, alpha_scale=1.0):
    pm0 = downsample(warp(p)); pm = pm0 * EDGE
    tot = float(pm0[..., 3].sum()); LOSS[name] = 1 - float(pm[..., 3].sum()) / max(tot, 1e-6)   # 테두리 띠에서 잃은 몫(검사용)
    x0, y0, x1, y1 = bbox(p["img"]); ax, ay = p["anchor"] if p["anchor"] else (p["img"].shape[1] / 2, p["img"].shape[0] / 2)
    FRONT[name] = (p["cx"] + (x0 - ax) * p["k"], p["cy"] + (y0 - ay) * p["k"], p["cx"] + (x1 - ax) * p["k"], p["cy"] + (y1 - ay) * p["k"])   # 정면 1024 상자(검사용)
    if alpha_scale != 1.0: pm = pm * alpha_scale
    r = crop(pm, fade)
    if r is None: raise SystemExit(f"{name}: 얼굴 조각 밖으로 나감")
    img, box = r; SPRITES.append([name, img, box]); return len(SPRITES) - 1

def layer(si, mirror=False, alpha=1.0, tint=None, mean=None, **kw):
    d = dict(sprite=si, mirror=mirror, alpha=round(alpha, 3))
    if tint: d["tint"] = tint; d["mean"] = round(mean, 4)
    d.update(kw)
    return d

def grey(img):
    """색은 버리고 밝기(luma) 명암만 남긴다(앱이 피부 맞춤 색을 곱한다). 알파는 그대로."""
    g = img.copy(); y = img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114
    g[..., 0] = g[..., 1] = g[..., 2] = y; return g

# 피부 맞춤 값(11/10). 5가지 피부 × 주름·코·볼터치·눈썹·짧은 수염 시트로 맞췄다(밝은 피부는 예전과 비슷하게)
SKIN_T = [0.40, 0.89]                      # 피부 luma 이 범위를 t 0~1로(짙은 갈색 0.404 → 0, 밝은 0.887 → 1)
WR_K = [0.70, 0.45]                        # 주름 = 피부 × 0.70(밝은) ~ 0.45(짙은)
NOSE_K = [0.80, 0.70]                      # 코 그림자 = 피부 × 0.80 ~ 0.70(예전 코 몸통은 밝은 피부의 약 0.8배)
BLUSH_C = ["#F8B3BE", "#D4607E"]           # 볼터치 분홍(예전 그림 평균) ~ 진한 장밋빛
BLUSH_A = [0.6, 0.7]                       # 볼터치 alpha(밝은, 짙은)
SEP = 0.22                                 # 눈썹·짧은 수염: 피부와 밝기 차 최소값
STUB_A = [0.75, 1.0]                       # 짧은 수염 alpha(밝은, 짙은). 그림 자체는 STUB_GAMMA 로 진하게 담는다
STUB_GAMMA = 0.7
# 11/10 사장 '건강한 피부 + 짧은 수염 + 주근깨가 지저분': 수염색(검정 등)을 반투명으로 얹으면 따뜻한 중간 피부 위에서 회색 먼지처럼 보였다.
# → 볼터치처럼 피부에 맞춰: 밝은 피부는 수염색 그대로, 짙어질수록 피부 그늘색(피부 × 0.45) 쪽으로 섞어 '수염 그늘'로 읽히게(shade)
STUB_SHADE = [0.0, 0.45, 0.45]

groups = {k: [] for k in ("eyes", "brows", "nose", "mouth", "wrinkle", "blush", "beard")}
# 번호는 뒤에만 붙인다(저장된 캐릭터의 번호 뜻 그대로). 다문 입(2)은 같은 번호에 다시 그린 그림(문서 76 B절).
# ── 눈(11/10 78·79번): 흰자 + 눈동자 + 윗눈꺼풀. GPT 시트(2줄 × 5칸, 윗줄 = 화면 왼쪽 눈, 1칸 = 예전 반달눈 기준 칸)를 합치기만 한다.
# 시트마다 배율 = 1칸(반달눈) 가로가 예전 반달눈 가로와 같게, 전체 EYE_GLOBAL(바깥 끝이 얼굴 그림 테두리 띠에서 잘리지 않게).
# 기준점 = 눈동자 원 가운데(위가 눈꺼풀에 가려져도 아래 끝 - 반지름), 감은 눈은 선 상자 가운데. 눈동자(갈색 판 + 동공)만 IRIS 로 칠한다.
# 고르는 칸에서 숨긴 0 동그란·3 긴 눈은 그림을 담지 않고 7·1 층을 그대로 쓴다(서버가 읽을 때 옮기지만 차가 옛 값을 받아도 같은 얼굴)
EYE_SHEETS = {"A": "eyes_w1_basic.png", "B": "eyes_w2_tilt.png", "C": "eyes_w3_size.png", "D": "eyes_w4_closed.png", "E": "eyes_w5_lash.png",
              "F": "eyes_w6_redraw.png", "M": "eyes_m1.png", "N": "eyes_m2.png",
              "P": "eyes_m3.png", "Q": "eyes_m4.png"}   # Q(84번 3차): 도도한 눈 다시 그림(꼬리가 바깥 끝)   # M·N·P(84번): dev_parts_1110d. P = 검은 눈동자로 그린 시트(눈웃음·온화한)   # F(79번): 차분한(두꺼운 눈꺼풀)·날렵한(길고 가는 꼬리)·무쌍(평평한 윗선)·애교살(밝고 바짝 붙은 살)
EYE_GLOBAL, IRIS = 0.85, "#1E1A18"
# 번호 → (시트, 칸, 크기 배율, 이름[, 줄 바꿈]). 줄 바꿈: GPT가 그 칸만 좌우 눈을 바꿔 그려 옴(F 날렵한: 꼬리가 윗줄 오른쪽)
EYE_MAP = {1: ("A", 1, 1, "큰 눈"), 2: ("C", 2, 1, "작은 눈"), 4: ("D", 3, 1, "실눈"), 5: ("D", 1, 1, "반달눈"),
           6: ("F", 1, 1, "차분한 눈"), 7: ("A", 2, 1, "또렷한 눈"), 8: ("F", 2, 1, "날렵한 눈", True), 9: ("A", 3, 1, "쌍꺼풀 눈"),
           10: ("B", 1, 1, "고양이 눈"), 11: ("B", 2, 1, "강아지 눈"), 12: ("A", 4, 1, "속눈썹 눈"), 13: ("D", 2, 1, "속눈썹 반달눈"),
           14: ("F", 3, 1, "무쌍 눈"), 15: ("F", 4, 1, "애교살 눈"), 16: ("Q", 2, 1, "도도한 눈", False, "dark"),
           17: ("M", 1, 1, "왕눈"),
           18: ("M", 2, 1, "아몬드 눈"),
           19: ("P", 1, 1, "눈웃음 눈", False, "dark"),   # 84번 2차: 라이너 눈 → 같은 번호에 눈웃음 눈
           20: ("M", 4, 1, "아래 속눈썹 눈"),
           21: ("N", 1, 1, "무심한 눈"),
           22: ("P", 4, 1, "온화한 눈", False, "dark"),   # 84번 2차: 날카로운 눈 → 같은 번호에 온화한 눈
           23: ("N", 3, 1, "진한 쌍꺼풀 눈"),
           24: ("N", 4, 1, "곁눈", False, "sclera")}
EYE_ALIAS = {0: 7, 3: 1, 2: 7, 6: 21, 9: 23, 10: 16, 15: 1}   # 숨긴 눈 → 같은 층(server/avatar.py MOVED). 84번: 2 작은 → 7, 6 차분한 → 21 무심한, 9 쌍꺼풀 → 23 진한 쌍꺼풀, 10 고양이 → 16 도도한(올라간 꼬리, 2차), 15 애교살 → 1(그림은 안 담고 옮긴 눈 층을 그대로)
EYE_N = 25
EYE_NAMES = ["동그란 눈", "큰 눈", "작은 눈", "긴 눈"] + [EYE_MAP[i][3] for i in range(4, EYE_N)]
AEGYO_EYE = 15                               # 애교살 눈: 눈 밑 선(주름 8)과 같은 자리라 같이 고르면 눈 밑 선은 안 그린다(층 unless_eyes)

def cells2(f, d=None):
    """흰자 눈 시트: 2줄 × 5칸. 작은 점(<150px) 지우고 빈 줄(40px)로 나눔. 애교살·속눈썹처럼 떨어진 조각도 같은 칸이면 한 부품."""
    im = np.array(Image.open(os.path.join(d or A.parts3, f)).convert("RGBA")).astype(np.float32) / 255
    a = im[..., 3] > 30 / 255; lab, n = ndi.label(a)
    keep = np.isin(lab, [i + 1 for i, c in enumerate(ndi.sum(a, lab, range(1, n + 1))) if c >= 150])
    def runs(m, gap):
        idx = np.nonzero(m)[0]; out = []
        for i in idx:
            if out and i <= out[-1][1] + gap: out[-1][1] = i + 1
            else: out.append([i, i + 1])
        return out
    rr = runs(keep.any(1), 40); assert len(rr) == 2, (f, rr)
    rows = []
    for y0, y1 in rr:
        cc = runs(keep[y0:y1].any(0), 40); assert len(cc) == 5, (f, cc)
        row = []
        for x0, x1 in cc:
            ys, xs = np.nonzero(keep[y0:y1, x0:x1]); m = 4
            Y0, Y1, X0, X1 = max(0, y0 + ys.min() - m), y0 + ys.max() + 1 + m, max(0, x0 + xs.min() - m), x0 + xs.max() + 1 + m
            c = im[Y0:Y1, X0:X1].copy(); c[..., 3] *= keep[Y0:Y1, X0:X1]; row.append(c)
        rows.append(row)
    return rows
def _wid(img):
    x0, _, x1, _ = bbox(img); return x1 - x0
def _hsv(img):
    rgb = img[..., :3]; mx = rgb.max(-1); mn = rgb.min(-1)
    return np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0), mx
def hull_fill(m):
    """덩어리의 볼록 껍질 안을 채운 마스크(곁눈 눈동자: 위가 눈꺼풀에 덮여 U자로 열린 고리)."""
    from scipy.spatial import ConvexHull
    ys, xs = np.nonzero(m); pts = np.c_[xs, ys].astype(np.float64); E = ConvexHull(pts).equations
    yy, xx = np.mgrid[0:m.shape[0], 0:m.shape[1]]
    return np.all(E[:, 0, None, None] * xx + E[:, 1, None, None] * yy + E[:, 2, None, None] <= 0.5, axis=0)
def iris_mask(img, closed=False):
    """갈색 눈동자(채도 높고 중간 밝기) + 그 안 동공·반사광(구멍 메움). 감은 눈 선·애교살(채도 낮음)은 None."""
    S, V = _hsv(img); al = img[..., 3] > 0.5
    m = al & (S > 0.42) & (V > 0.26)
    if closed: m = ndi.binary_opening(m, iterations=3)   # 곁눈(84번): 아래 선 둘레의 가는 띠를 걷음
    if m.sum() < 30: return None
    lab, n = ndi.label(m); big = lab == 1 + int(np.argmax(ndi.sum(m, lab, range(1, n + 1))))
    if closed: big = hull_fill(big)   # 윗눈꺼풀·반사광에 끊긴 고리(U자)를 볼록 껍질로 메움
    big = ndi.binary_fill_holes(big); ys, xs = np.nonzero(big); h, w = np.ptp(ys) + 1, np.ptp(xs) + 1
    if big.sum() < 0.06 * al.sum() or h < 0.45 * w or big.sum() < 0.5 * h * w: return None
    return big
def iris_mask_dark(img):
    """검은 눈동자로 그려 온 눈(84번 2차): 흰자(밝고 채도 낮음) 볼록 껍질 안의 어두운 덩어리 + 그 안 반사광. 가는 선은 걷어 냄."""
    S, V = _hsv(img); al = img[..., 3] > 0.5
    white = al & (V > 0.8) & (S < 0.25)
    if white.sum() < 200: return None
    m = al & (V < 0.4) & hull_fill(white)
    m = ndi.binary_opening(m, iterations=4)
    if m.sum() < 30: return None
    lab, n = ndi.label(m); big = lab == 1 + int(np.argmax(ndi.sum(m, lab, range(1, n + 1))))
    return hull_fill(big)
def iris_anchor(img, closed=False, dark=False):
    """눈동자 원 가운데: x = 상자 가운데, y = 아래 끝 - 반지름(가로 폭/2). 눈동자 없으면(감은 눈) 가장 큰 덩어리 상자 가운데."""
    m = iris_mask_dark(img) if dark else iris_mask(img, closed)
    if m is not None:
        ys, xs = np.nonzero(m); r = (xs.max() + 1 - xs.min()) / 2
        if dark and m[ys.max() - 2].sum() > m[ys.min() + 2].sum():   # 아래가 눈꺼풀에 잘린 눈(눈웃음): 보이는 눈동자 가운데(원 가운데로 잡으면 눈 전체가 위로 뜸)
            return ((xs.min() + xs.max() + 1) / 2, (ys.min() + ys.max() + 1) / 2)
        return ((xs.min() + xs.max() + 1) / 2, ys.max() + 1 - r)
    al = img[..., 3] > 0.5; lab, n = ndi.label(al); big = 1 + int(np.argmax(ndi.sum(al, lab, range(1, n + 1)))); ys, xs = np.nonzero(lab == big)
    return ((xs.min() + xs.max() + 1) / 2, (ys.min() + ys.max() + 1) / 2)
def sclera_anchor(img):
    """곁눈(84번): 눈동자가 한쪽으로 쏠린 눈은 흰자 상자 가운데(x)를 기준으로(눈동자 기준이면 흰자가 반대로 밀림). y 는 눈동자 기준 그대로."""
    S, V = _hsv(img); m = (img[..., 3] > 0.5) & (V > 0.8) & (S < 0.2)
    ax, ay = iris_anchor(img, True)
    if m.sum() < 200: return ax, ay
    xs = np.nonzero(m.any(0))[0]; return ((xs.min() + xs.max() + 1) / 2, ay)
def recolor_dark(img, hexc):
    """검은 눈동자 시트: 눈동자를 다른 눈과 같은 따뜻한 검정(hexc)으로 맞춤. 흰 반사광은 그대로."""
    m = iris_mask_dark(img)
    if m is None: return img
    S, V = _hsv(img)
    w = m * (1 - np.clip((V - 0.45) / 0.2, 0, 1))
    t = np.array([int(hexc[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
    lum = img[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    new = np.clip(t[None, None] * np.clip(0.85 + 0.3 * lum / max(float(lum[m].mean()), 0.02), 0.7, 1.3)[..., None], 0, 1)
    out = img.copy(); out[..., :3] = img[..., :3] * (1 - w[..., None]) + new * w[..., None]; return out
def recolor_iris(img, hexc, closed=False):
    """눈동자(갈색 판 + 동공)만 hexc 로. 흰 반사광·흰자·눈꺼풀 선(채도 낮은 고동색)은 그대로 → 흰자 안의 검은 눈동자(78번 v2)."""
    m = iris_mask(img, closed)
    if m is None: return img
    S, V = _hsv(img); ys, xs = np.nonzero(m); r = (xs.max() + 1 - xs.min()) / 2; cx = (xs.min() + xs.max() + 1) / 2; cy = ys.max() + 1 - r
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]] + 0.5
    d = np.hypot(xx - cx, yy - cy)
    disc = np.clip((r + 3 - d) / 2, 0, 1)
    brown = np.clip((S - 0.30) / 0.12, 0, 1) * np.clip((V - 0.20) / 0.06, 0, 1) * (d < r * 1.35)
    lid = np.clip((0.47 - S) / 0.06, 0, 1) * np.clip((0.30 - V) / 0.06, 0, 1)
    region = np.maximum(disc, brown) * (1 - lid)
    keep = np.clip((V - 0.55) / 0.2, 0, 1) * np.clip((0.35 - S) / 0.15, 0, 1)
    w = region * (1 - keep)
    t = np.array([int(hexc[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
    lum = img[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    new = np.clip(t[None, None] * (0.8 + 0.4 * lum / 0.36)[..., None], 0, 1)
    out = img.copy(); out[..., :3] = img[..., :3] * (1 - w[..., None]) + new * w[..., None]; return out
ESH = {k: cells2(f, A.parts4 if k in ("M", "N", "P", "Q") else None) for k, f in EYE_SHEETS.items()}
EYE_K = {k: KE * _wid(EYES[5]) / _wid(v[0][0]) for k, v in ESH.items()}   # 시트마다: 1칸(반달) 가로 = 예전 반달눈 가로
for k, v in EYE_K.items(): print(f"  눈 시트 {k}: 배율 {v:.4f}")
_eye = {}
for i in range(EYE_N):
    if i in EYE_ALIAS: continue
    sk, c, mul, nm, *sw = EYE_MAP[i]
    L, R = ESH[sk][0][c], ESH[sk][1][c]
    if sw and sw[0]: L, R = R, L
    k = EYE_K[sk] * EYE_GLOBAL * mul
    sc, dk = len(sw) > 1 and sw[1] == "sclera", len(sw) > 1 and sw[1] == "dark"
    aL, aR = (sclera_anchor(L), sclera_anchor(R)) if sc else (iris_anchor(L, dark=dk), iris_anchor(R, dark=dk))
    paint = (lambda x: recolor_dark(x, IRIS)) if dk else (lambda x: recolor_iris(x, IRIS, sc))
    _eye[i] = [layer(add(f"eye{i}_L", place(paint(L), -215, 51, k, anchor=aL))),
               layer(add(f"eye{i}_R", place(paint(R), 215, 51, k, anchor=aR)))]
groups["eyes"] = [_eye[EYE_ALIAS.get(i, i)] for i in range(EYE_N)]

# ── 눈썹: 1 아치는 숨김(79번, → 7 가는 눈썹 층), 9 긴 꼬리 눈썹(어르신, dev_parts_1110b 시트, 1칸 = 숱 많은 눈썹 기준) ──
BROW9_SHEET, BROW9_CELL, BROW9_K, BROW9_FX = "brows_w9_long.png", 2, 0.8, 0.85
_b9 = cells(os.path.join(A.parts3, BROW9_SHEET), 1)
S_B9 = calib(_b9[0], BROWS[3], "긴 꼬리 눈썹 시트(숱 많은)")
BROW_ALIAS = {1: 7}
BROW3_THICK = 1.15                                    # 숱 많은(3)을 일자(2)보다 굵어 보이게: 세로만 늘이는 배율
BROW_NAMES = ["짧은 눈썹", "아치 눈썹", "일자 눈썹", "숱 많은 눈썹"] + [n for _, n in NEW_BROWS] + ["긴 꼬리 눈썹"]
def stretch(img, fx=1.0, fy=1.0):
    if fx == 1.0 and fy == 1.0: return img
    h, w = img.shape[:2]
    return np.array(Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8), "RGBA").resize((int(round(w * fx)), int(round(h * fy))), Image.LANCZOS)).astype(np.float32) / 255
_brow = {}
for i, s in enumerate(BROWS):
    if i in BROW_ALIAS: continue
    if i == 3: s = stretch(s, 1.0, BROW3_THICK)
    _brow[i] = [layer(add(f"brow{i}", P_BROW(s)), mirror=True, tint="hair", mean=grey_mean(s), sep=SEP)]
for j, (c, _) in enumerate(NEW_BROWS):   # 왼쪽 하나만 그림(회색) → 앱이 머리색을 곱하고 오른쪽은 뒤집어 한 번 더
    s = NBR[c]; _brow[4 + j] = [layer(add(f"brow{4 + j}", place(s, -235, -150, KB * S_BR)), mirror=True, tint="hair", mean=grey_mean(s), sep=SEP)]
_s9 = stretch(grey(_b9[BROW9_CELL]), BROW9_FX)   # GPT가 기준 칸보다 1.4배 길게 그려 옴 → 숱 많은 눈썹의 약 1.1배 길이로(가로만 더 줄여 굵기는 남김)
_brow[9] = [layer(add("brow9", place(_s9, -235, -150, KB * S_B9 * BROW9_K)), mirror=True, tint="hair", mean=grey_mean(_s9), sep=SEP)]
groups["brows"] = [_brow[BROW_ALIAS.get(i, i)] for i in range(len(BROW_NAMES))]
# ── 코: 1 동그란 코는 숨김(79번, → 0 작은 코 층) ──
NOSE_ALIAS = {1: 0}
_nose = {}
for i, s in enumerate(NOSES):
    if i in NOSE_ALIAS: continue
    g = grey(s); _nose[i] = [layer(add(f"nose{i}", P_NOSE(g)), tint="skin", mean=grey_mean(g), k=NOSE_K)]
groups["nose"] = [_nose[NOSE_ALIAS.get(i, i)] for i in range(len(NOSES))]
MOUTH_NAMES = ["미소", "활짝 웃음", "꾹 다문 입", "동그란 입"] + [n for _, n in NEW_MOUTHS]
def mouth_place(s, mul=1.0): return place(s, 0, 310, KB * S_MO * mul, anchor=line_anchor(s))   # 입 선(검은 덩어리) 상자 가운데 = 입 자리
LIP_C = None
LIP_K, LIP_STEP = 1.2, 0.85                            # 79번: 분홍 입술은 12명 칸에서 거의 안 보여 1.2배 크게, 색은 한 단 진하게
for i, s in enumerate(MOUTHS):
    if i == 2: s = NMO[TIGHT_MOUTH]; groups["mouth"].append([layer(add("mouth2", mouth_place(s)))]); continue
    groups["mouth"].append([layer(add(f"mouth{i}", P_MOUTH(s)))])
for j, (c, nm) in enumerate(NEW_MOUTHS):
    s = NMO[c]
    if nm == "분홍 입술":   # 색 그림 → 회색 명암 + 피부 맞춤 색(밝은 피부 = 그려 온 장밋빛보다 한 단 진하게, 짙은 피부 = 거기서 한 단 더)
        a = s[..., 3] > 0.5; LIP_C = s[..., :3][a].mean(0) * LIP_STEP; g = grey(s)
        hx = lambda c: "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in np.clip(c, 0, 1))
        groups["mouth"].append([layer(add(f"mouth{4 + j}", mouth_place(g, LIP_K)), tint="pair", mean=grey_mean(g), c=[hx(LIP_C), hx(LIP_C * LIP_DARK)])])
    else: groups["mouth"].append([layer(add(f"mouth{4 + j}", mouth_place(s)))])
# 주름 값: 0 없음, 1 눈가, 2 이마, 3 눈가+이마(11/10 추가, 두 층을 같이). 예전 저장값 0~2 뜻 그대로
_we, _wf = grey(WR_EYE), grey(WR_FORE)
L_WR_EYE = layer(add("wr_eye", place(_we, *P_WR_EYE_XY, KN)), mirror=True, tint="skin", mean=grey_mean(_we), k=WR_K)
L_WR_FORE = layer(add("wr_fore", place(_wf, *P_WR_FORE_XY, KN)), tint="skin", mean=grey_mean(_wf), k=WR_K)
# 11/10 주름 값 = 눈가 1 + 이마 2 + 입가 4 + 눈 밑 8 (0~15, 켜고 끄기 4개). 칸 i 의 층 = 켜진 비트 순서대로 → 예전 0~3 은 같은 층 그대로
# 79번: 눈 밑 선은 짙은 피부·12명 칸에서 거의 안 보여 한 단 진하게(WR_UNDER_KD, 진하기 WR_UNDER_A), 애교살 눈과는 같이 안 그림(unless_eyes)
_wm, _wu = grey(WR_MOUTH), grey(WR_UNDER)
L_WR_MOUTH = layer(add("wr_mouth", place(_wm, *P_WR_MOUTH_XY, KN * S_LN)), mirror=True, tint="skin", mean=grey_mean(_wm), k=WR_K)
L_WR_UNDER = layer(add("wr_under", place(_wu, *P_WR_UNDER_XY, KN * S_LN * WR_UNDER_K), alpha_scale=WR_UNDER_A), mirror=True, tint="skin",
                   mean=grey_mean(_wu), k=WR_UNDER_KD, unless_eyes=[AEGYO_EYE])
# ── 11/10 눈가 주름 눈마다(사장: 새 흰자 눈의 굵은 윤곽·속눈썹이 눈가 주름을 가림) ──
# 원인: 눈가 주름은 한 자리(정면 -315,45)·한 크기인데 흰자 눈은 바깥 끝이 정면 -327~-390 까지 와서, 주름(-363~-267)의 2/3 이상이
# 눈 밑(층 순서상 눈 아래)에 깔렸다. 눈 바깥은 얼굴 그림 끝(정면 약 -404, 테두리 띠 시작 -375)까지 좁아 한 자리로는 못 피한다.
# → 눈마다 자리·가로 길이를 찾는다: 후보(안쪽 끝 자리 x·y, 가로 배율 sx) 가운데 '눈(윤곽을 CF_GAP 만큼 넓힘) 밖 + 테두리 띠 안'에
#   보이는 몫이 CF_VIS 이상인 것 중 눈 바깥 끝(가운데 높이)에 가장 가깝고 덜 줄인 것. 정면 그림(반 해상도)에서 잰다.
# 선은 한 단 굵게(CF_DIL, 원본 px)·진하게(CF_K): 흰자 눈의 굵은 윤곽 옆에서 예전 가는 선은 묻혔다.
# 결과는 눈가 주름 층의 by_eyes(눈 번호 0~24 → 그림 번호)로 담는다. 앱은 그 눈이면 그 그림을 쓰고, 모르는 앱은 예전 그림(sprite).
CF_GAP, CF_VIS, CF_DIL, CF_K = 6, 0.8, 2, [0.60, 0.40]
CF_SX = (1.0, 0.85, 0.72, 0.6, 0.5, 0.42)
_cf0 = grey(WR_EYE); _cf0[..., :3] = grey_mean(_we)   # 선은 고른 회색: 넓힌 알파 자리에도 같은 회색(층 mean 그대로)
_cf0[..., 3] = ndi.grey_dilation(_cf0[..., 3], size=(2 * CF_DIL + 1, 2 * CF_DIL + 1))
_cf0[..., 3] = ndi.gaussian_filter(_cf0[..., 3], 0.8)
_cfa = _cf0[..., 3] > 0.3 * _cf0[..., 3].max(); _cys, _cxs = np.nonzero(_cfa)
CF_INNER = (_cxs.max() + 1.0, (_cys.min() + _cys.max() + 1) / 2)   # 안쪽(눈 쪽) 끝 가운데 = 기준점
_cf_small = _cf0.copy(); _cf_small[..., 3] = ndi.grey_dilation(_cf_small[..., 3], size=(3, 3))   # 0.8배로 줄일 때 선 굵기는 그대로 남게 한 번 더 넓힘
def _front_edge():
    """정면(반 해상도 512, 1 칸 = 정면 2px)에서 얼굴 그림 테두리 띠 값(EDGE). 얼굴 조각 밖 = 0"""
    from scipy.interpolate import griddata
    ok = np.isfinite(MAP[..., 0]); jj, ii = np.nonzero(ok)
    uv = np.c_[(ii + 0.5) / MN, (jj + 0.5) / MN]; pts = MAP[ok][:, :2] * 512
    gy, gx = np.mgrid[0:512, 0:512] * 2.0 - 512 + 1.0
    U = griddata(pts, uv, (gx, gy), method="linear")
    e = _sm(np.minimum(U[..., 0], 1 - U[..., 0]) / BORDER) * _sm(np.minimum(U[..., 1], 1 - U[..., 1]) / BORDER)
    return np.nan_to_num(e)
CF_WIN = (slice(160, 400), slice(0, 200))                # 왼쪽 눈 둘레만 잰다(정면 x -512~-112, y -192~288)
def _front_alpha(img, cx, cy, k, anchor, fx=1.0):
    """부품을 정면 반 해상도 칸(CF_WIN)에 놓은 알파(place 와 같은 자리, 가로 배율 fx)"""
    gy, gx = np.mgrid[CF_WIN] * 2.0 - 512 + 1.0
    ax, ay = anchor
    sx = ax + (gx - cx) / (k * fx) - 0.5; sy = ay + (gy - cy) / k - 0.5
    return ndi.map_coordinates(img[..., 3], (sy, sx), order=1, cval=0.0)
CF_EDGE = _front_edge()[CF_WIN]
_cf_by = {}
for _e in range(EYE_N):
    if _e in EYE_ALIAS: continue
    _sk, _c, _mul, _nm, *_sw = EYE_MAP[_e]
    _L = ESH[_sk][1][_c] if (_sw and _sw[0]) else ESH[_sk][0][_c]
    _ki = EYE_K[_sk] * EYE_GLOBAL * _mul
    _sc, _dk = len(_sw) > 1 and _sw[1] == "sclera", len(_sw) > 1 and _sw[1] == "dark"
    _an = sclera_anchor(_L) if _sc else iris_anchor(_L, dark=_dk)
    _ea = _front_alpha(_L, -215, 51, _ki, _an)
    _ed = ndi.grey_dilation(_ea, size=(2 * (CF_GAP // 2) + 1,) * 2)
    _m = _ea > 0.5; _ys, _xs = np.nonzero(_m); _y0, _y1 = _ys.min(), _ys.max()
    _band = (_ys >= _y0 + 0.3 * (_y1 - _y0)) & (_ys <= _y0 + 0.75 * (_y1 - _y0))   # 바깥 끝 = 가운데 높이 띠에서 가장 왼쪽(속눈썹 끝은 뺌)
    _i = np.argmin(np.where(_band, _xs, 1 << 20)); ox, oy = (_xs[_i] + CF_WIN[1].start) * 2.0 - 511, (_ys[_i] + CF_WIN[0].start) * 2.0 - 511
    best = fallback = None
    for sc, fx in [(1.0, f) for f in CF_SX] + [(0.8, f) for f in CF_SX[-3:]]:   # 가로만 줄여도 안 되면(바깥 끝이 얼굴 그림 끝에 닿는 눈) 전체를 0.8배로
        for dx in range(-4, 44, 4):
            for dy in range(-36, 28, 6):
                cx, cy = ox - CF_GAP - dx, oy + dy
                a = _front_alpha(_cf0, cx, cy, KN * sc, CF_INNER, fx); tot = a.sum()
                if tot <= 0: continue
                vis = float((a * CF_EDGE * (1 - np.clip(_ed, 0, 1))).sum() / tot)
                cost = dx + abs(dy) * 1.2 + (1 - fx) * 60 + (1 - sc) * 100
                if vis >= CF_VIS and (best is None or cost < best[0]): best = (cost, fx, cx, cy, vis, sc)
                if fallback is None or vis > fallback[4]: fallback = (cost, fx, cx, cy, vis, sc)
        if best is not None and best[1] == fx and best[5] == sc: break   # 덜 줄인 배율에서 찾았으면 더 줄이지 않는다
    if best is None: best = fallback; print(f"  ! 눈 {_e}: 보이는 몫 {CF_VIS} 못 채움 → 가장 많이 보이는 자리")
    _, fx, cx, cy, vis, sc = best
    _img = _cf0 if sc == 1.0 else _cf_small
    _img = stretch(_img, fx) if fx != 1.0 else _img
    _cf_by[_e] = add(f"wr_eye_e{_e}", place(_img, cx, cy, KN * sc, anchor=(CF_INNER[0] * fx, CF_INNER[1])))
    print(f"  눈가 주름 눈 {_e:2d}: 바깥 끝 ({ox:.0f},{oy:.0f}) → 안쪽 끝 ({cx:.0f},{cy:.0f}) 가로 {fx:.2f} 크기 {sc:.1f} 보임 {vis:.2f}")
L_WR_EYE["by_eyes"] = [_cf_by[EYE_ALIAS.get(i, i)] for i in range(EYE_N)]
L_WR_EYE["k"] = CF_K
WR_BITS = [L_WR_EYE, L_WR_FORE, L_WR_MOUTH, L_WR_UNDER]
WR_BIT_NAMES = ["눈가", "이마", "입가", "눈 밑"]
groups["wrinkle"] = [[L for b, L in enumerate(WR_BITS) if v >> b & 1] for v in range(16)]
_bl = grey(BLUSH)
groups["blush"] = [[], [layer(add("blush", place(_bl, BLUSH_X, BLUSH_Y, BLUSH_K)), mirror=True, alpha=BLUSH_A[0], alpha_dark=BLUSH_A[1],
                              tint="pair", mean=grey_mean(_bl), c=BLUSH_C)]]
smax = float(STUB[..., 3].max()); s_alpha = min(1.0, smax * A.stub_gain)
STUB_N = STUB.copy(); STUB_N[..., 3] /= smax           # 담을 때는 최대 불투명으로 펴서(8비트 손실 줄임), 진하기는 alpha로
STUB_N[..., 3] = STUB_N[..., 3] ** STUB_GAMMA         # 11/10: 짙은 피부에서도 보이게 그림은 진하게, 밝은 피부는 alpha 로 예전만큼
STUB_N[..., :3] = 0.5                                   # 원본 색은 점마다 제멋대로(흰·빨강 점) → 결은 알파로만, 색은 앱이 수염색 한 가지로
_sx = (np.arange(STUB_N.shape[1]) + 0.5) / STUB_N.shape[1]   # 원본 그림은 좌우 끝까지 점이 있어 볼 옆(정면 ±0.71R)에서 세로로 칼같이 끊겼다 → 좌우 끝 18%를 부드럽게
STUB_N[..., 3] *= (lambda c: c * c * (3 - 2 * c))(np.clip(np.minimum(_sx, 1 - _sx) / 0.18, 0, 1))[None, :]
groups["beard"] = [[], [layer(add("stubble", place(STUB_N, 0, 310, A.stub_k, anchor=STUB_ANCHOR), fade=True), alpha=s_alpha * STUB_A[0],
                               alpha_dark=round(s_alpha * STUB_A[1], 3), tint="beard", mean=0.5, sep=SEP, shade=STUB_SHADE)], [], []]
groups["beard"].append(groups["beard"][1])   # 11/10 수염 4 = 짧은 수염 + 콧수염: 얼굴 그림은 짧은 수염 층 그대로(콧수염은 3D 노드 beard_mus)

# ── 점(11/10, 83번 5절 (b)·84번 look_08 눈 밑 점): GPT 시트 face_marks.png(dev_parts_1110e, 1칸 = 눈가 주름 기준 칸, 2칸 점, 3칸 작은 점, 4칸 주근깨 한쪽 볼 몫)
# 값 0 없음, 1 눈 밑 점, 2 입가 점, 3 볼 점, 4 주근깨. 점은 한쪽(화면 왼쪽 = 본인 오른쪽)에만, 주근깨는 좌우로 한 번 더(mirror).
# 크기는 정면 1024 그림에서 지름(MARK_D, px)으로 정한다: 실제 점(얼굴 폭의 1% 안팎)이면 16칸 닮은 모습 그림에서 1px 이 안 돼 안 보여서 3배쯤 크게.
# 색은 피부 맞춤 tint pair(볼터치와 같은 식): 밝은 피부는 갈색, 짙은 피부는 그보다 짙은 고동색(점이 피부보다 늘 한 단 이상 어둡게)
MK = cells(os.path.join(A.parts5, "face_marks.png"), 1, 4, gap=60)
S_MK = calib(MK[0], WR_EYE, "점 시트(눈가 주름)")   # 기록용: 시트 배율. 점 크기는 아래 지름으로 맞춘다
def _mk_k(img, d):
    x0, y0, x1, y1 = bbox(img, 0.5); return d / math.sqrt((x1 - x0) * (y1 - y0))
MARK_DOT, MARK_SMALL, MARK_FRECKLE = grey(MK[1]), grey(MK[2]), grey(MK[3])
MARK_D = dict(under=42, mouth=36, cheek=42)            # 정면 1024 지름(px)
MARK_XY = dict(under=(-258, 168), mouth=(-130, 290), cheek=(-268, 265))
FRECKLE_W, FRECKLE_XY = 230, (-185, 175)               # 주근깨 무리 가로(px)·가운데: 눈 밑 볼에서 콧등 쪽으로
MARK_C = ["#6E4634", "#1A0E0A"]                        # 점 색: 밝은 피부(t=1) ~ 짙은 피부(t=0)
FRECKLE_C, FRECKLE_A = ["#A0603F", "#1E110C"], [0.85, 1.0]
def _mark(nm, img, xy, k, c, al=(1.0, 1.0), mirror=False):
    return layer(add(nm, place(img, *xy, k)), mirror=mirror, alpha=al[0], alpha_dark=al[1], tint="pair", mean=grey_mean(img), c=c)
_fx0, _, _fx1, _ = bbox(MARK_FRECKLE, 0.3)
groups["mark"] = [[], [_mark("mark_under", MARK_DOT, MARK_XY["under"], _mk_k(MARK_DOT, MARK_D["under"]), MARK_C)],
                  [_mark("mark_mouth", MARK_SMALL, MARK_XY["mouth"], _mk_k(MARK_SMALL, MARK_D["mouth"]), MARK_C)],
                  [_mark("mark_cheek", MARK_DOT, MARK_XY["cheek"], _mk_k(MARK_DOT, MARK_D["cheek"]), MARK_C)],
                  [_mark("mark_freckle", MARK_FRECKLE, FRECKLE_XY, FRECKLE_W / (_fx1 - _fx0), FRECKLE_C, FRECKLE_A, mirror=True)]]
MARK_NAMES = ["없음", "눈 밑 점", "입가 점", "볼 점", "주근깨"]
# 11/10 사장 '여러 개 고르고, 좌·우 종류별 하나씩': marks 비트 1·2 눈 밑 왼·오, 4·8 입가 왼·오, 16·32 볼 왼·오, 64 주근깨(두 볼).
# 오른쪽 점 = 같은 그림을 좌우로 뒤집어(place flip, 기준점 = 그림 가운데) 정면 x 만 반대 자리에. 예전 mark 칸(groups.mark)은 그대로 두고 그리지는 않는다
def _mark_r(nm, img, key, d):
    x, y = MARK_XY[key]
    return layer(add(nm + "_R", place(img, -x, y, _mk_k(img, d), flip=True)), mirror=False, alpha=1.0, alpha_dark=1.0, tint="pair", mean=grey_mean(img), c=MARK_C)
MARK_BIT_L = [groups["mark"][1][0], _mark_r("mark_under", MARK_DOT, "under", MARK_D["under"]),
              groups["mark"][2][0], _mark_r("mark_mouth", MARK_SMALL, "mouth", MARK_D["mouth"]),
              groups["mark"][3][0], _mark_r("mark_cheek", MARK_DOT, "cheek", MARK_D["cheek"]), groups["mark"][4][0]]
MARK_BIT_NAMES = ["눈 밑 점 왼쪽", "눈 밑 점 오른쪽", "입가 점 왼쪽", "입가 점 오른쪽", "볼 점 왼쪽", "볼 점 오른쪽", "주근깨"]
groups["marks"] = [[L for b, L in enumerate(MARK_BIT_L) if v >> b & 1] for v in range(1 << len(MARK_BIT_L))]
# 수염 비트(beards): 1 짧은 수염(얼굴 그림), 2 콧수염·4 턱수염은 3D. 얼굴 그림은 짧은 수염 층만
BEARD_BIT_NAMES = ["짧은 수염", "콧수염", "턱수염"]
# 11/10 짧은 수염 위 주름·주근깨(사장: 입가 주름·눈 밑 선이 짧은 수염에 묻힘, 건강한 피부 + 짧은 수염 + 주근깨가 지저분):
# 원인: 주름 선(피부 × 0.70~0.45)이 그보다 짙은 수염 점·회색 안개 위에 그려져 선과 수염이 한 덩어리로 보이고,
# 주근깨(갈색 점)는 수염 윗가장자리(볼)와 겹쳐 점 두 겹이 섞였다.
# → 짧은 수염 층 바로 다음(볼터치·점·주름보다 먼저)에 '피부색 비우기' 층: 주름 선·주근깨 무리를 넓혀 흐린 모양을 피부색 그대로 덮어
#   그 자리 수염을 걷는다(그 주름·주근깨를 골랐을 때만, 층 need). 선·주근깨는 그 위 깨끗한 피부에 그려진다. 수염이 없으면 안 그린다.
CLEAR_GREY = 0.5
def clear_shape(img, r, blur, a=1.0):
    """부품 알파를 r(원본 px)만큼 넓히고 흐린 비우기 그림(고른 회색 = mean, 앱이 피부색을 곱함). 기준점(가운데)은 그대로"""
    pad = int(r + 3 * blur + 2); h, w = img.shape[:2]
    al = np.zeros((h + 2 * pad, w + 2 * pad), np.float32); al[pad:pad + h, pad:pad + w] = img[..., 3] / max(float(img[..., 3].max()), 1e-6)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]; al = ndi.grey_dilation(al, footprint=(xx * xx + yy * yy) <= r * r)
    al = ndi.gaussian_filter(al, blur); out = np.zeros(al.shape + (4,), np.float32); out[..., :3] = CLEAR_GREY; out[..., 3] = np.clip(al * a, 0, 1)
    return out
def clear_layer(nm, img, xy, k, r_front, blur_front, need, **kw):
    """정면 r_front px 만큼 넓힌 비우기 층(부품과 같은 자리·배율)"""
    return layer(add(nm, place(clear_shape(img, max(1, round(r_front / k)), blur_front / k), *xy, k)), tint="skin", mean=CLEAR_GREY, k=[1, 1], need=need, **kw)
STUB_CLEAR = [clear_layer("clr_wr_mouth", _wm, P_WR_MOUTH_XY, KN * S_LN, 12, 5, {"wrinkle": 4}, mirror=True),
              clear_layer("clr_wr_under", _wu, P_WR_UNDER_XY, KN * S_LN * WR_UNDER_K, 10, 4, {"wrinkle": 8}, mirror=True, unless_eyes=[AEGYO_EYE]),
              clear_layer("clr_freckle", MARK_FRECKLE, FRECKLE_XY, FRECKLE_W / (_fx1 - _fx0), 26, 12, {"marks": 64}, mirror=True)]
groups["beards"] = [list(groups["beard"][1]) + STUB_CLEAR if v & 1 else [] for v in range(8)]

# ── 4. 한 장으로 담기(선반 쌓기) ────────────────────────────────────────────────
PAD = 2
order = sorted(range(len(SPRITES)), key=lambda i: -SPRITES[i][1].shape[0])
def pack(W):
    x = y = sh = 0; pos = {}
    for i in order:
        h, w = SPRITES[i][1].shape[:2]
        if w + PAD > W: return None
        if x + w + PAD > W: x = 0; y += sh; sh = 0
        pos[i] = (x + PAD // 2, y + PAD // 2); x += w + PAD; sh = max(sh, h + PAD)
    return pos, y + sh
best = None
for W in (256, 320, 384, 448, 512, 640, 768, 1024, 1280, 1536, 2048):
    r = pack(W)
    if r and (best is None or W * r[1] < best[0] * best[2]): best = (W, r[0], r[1])
W, pos, H = best
atlas = np.zeros((H, W, 4), np.float32)
for i, (nm, img, box) in enumerate(SPRITES):
    x, y = pos[i]; h, w = img.shape[:2]; atlas[y:y + h, x:x + w] = img
os.makedirs(A.out, exist_ok=True)
ATL = os.path.join(A.out, A.name + (".webp" if A.webp else ".png"))
if A.webp: Image.fromarray(np.round(np.clip(atlas, 0, 1) * 255).astype(np.uint8), "RGBA").save(ATL, "WEBP", lossless=True, quality=100, method=6, exact=True)
else: Image.fromarray(np.round(np.clip(atlas, 0, 1) * 255).astype(np.uint8), "RGBA").save(ATL, optimize=True)
spr = []
for i, (nm, img, (x0, y0, x1, y1)) in enumerate(SPRITES):
    x, y = pos[i]; h, w = img.shape[:2]
    spr.append(dict(name=nm, src=[x, y, w, h], dst=[round(x0 / NF, 5), round(y0 / NF, 5), round(x1 / NF, 5), round(y1 / NF, 5)]))
J = dict(version=2, image=os.path.basename(ATL), note="face_atlas.py 로 만듦. dst = face.png 한 변 1.0 기준 칸(l,t,r,b). mirror = u 0.5 기준 좌우로 한 번 더. tint = 회색 명암 × 색/mean. "
                         "t = (피부 luma - skin_t[0])/(skin_t[1]-skin_t[0]) 0~1. skin: 피부×lerp(k[1],k[0],t), pair: lerp(c[1],c[0],t), sep: 피부와 밝기 차 최소, alpha_dark: t=0 쪽 alpha",
         face_size=NF, skin_t=SKIN_T, draw_order=["beards", "blush", "marks", "wrinkle", "nose", "mouth", "eyes", "brows"],
         sprites=spr, groups=groups,
         layout=dict(frame="정면 1024, 512px=머리 반지름(문서 56)", eyes=[215, 51, KE], brows=[235, -150, KB], nose=[0, 178, KN * 1.3], mouth=[0, 310, KB],
                     blush=[-BLUSH_X, BLUSH_Y, BLUSH_K, BLUSH_A[0]], wrinkle_eye=[-P_WR_EYE_XY[0], P_WR_EYE_XY[1], KN], wrinkle_forehead=[*P_WR_FORE_XY, KN],
                     stubble=[0, 310, A.stub_k, round(s_alpha * STUB_A[0], 3)]))
J["layout"].update(wrinkle_mouth=[-P_WR_MOUTH_XY[0], P_WR_MOUTH_XY[1], round(KN * S_LN, 4)], wrinkle_under=[-P_WR_UNDER_XY[0], P_WR_UNDER_XY[1], round(KN * S_LN * WR_UNDER_K, 4)])
# 정보용(앱은 안 읽어도 됨): 칸 번호 → 이름, 주름 비트. 서버 avatar.py PARTS 와 같은 순서여야 한다
J["names"] = dict(eyes=EYE_NAMES, brows=BROW_NAMES, mouth=MOUTH_NAMES, wrinkle_bits=WR_BIT_NAMES, mark=MARK_NAMES, beard_bits=BEARD_BIT_NAMES, mark_bits=MARK_BIT_NAMES)
json.dump(J, open(os.path.join(A.out, A.name + ".json"), "w"), ensure_ascii=False, separators=(",", ":"))
if A.web:   # 웹(server/web/avatar)도 차 assets 와 같은 두 파일 + 고르는 칸용 큰 아틀라스(face_atlas_hd, 같은 층·같은 칸)
    import shutil, subprocess, sys
    for f in (A.name + ".png", A.name + ".json"): shutil.copyfile(os.path.join(A.out, f), os.path.join(A.web, f))
    print("web ->", A.web)
    if A.hd_nf:
        subprocess.run([sys.executable, os.path.abspath(__file__), "--nf", str(A.hd_nf), "--name", "face_atlas_hd", "--out", A.web, "--web", "", "--hd-nf", "0", "--webp",
                        "--parts", A.parts, "--parts2", A.parts2, "--parts3", A.parts3, "--parts4", A.parts4, "--parts5", A.parts5, "--map", A.map,
                        "--stub-k", str(A.stub_k), "--stub-gain", str(A.stub_gain)], check=True, stdout=subprocess.DEVNULL)
        hp = os.path.join(A.web, "face_atlas_hd.webp"); print(f"web hd -> {hp} {Image.open(hp).size} {os.path.getsize(hp) / 1024:.0f}KB")
print(f"atlas {W}x{H} = {W * H * 4 / 2 ** 20:.2f}MB decoded, png {os.path.getsize(ATL) / 1024:.0f}KB, sprites {len(SPRITES)}")
for g, opts in groups.items(): print(" ", g, len(opts), [len(o) for o in opts])
for nm, v in LOSS.items():
    if v > 0.03 and nm != "stubble": print(f"  ! {nm}: 테두리 띠에서 {v * 100:.1f}% 잃음")

# ── 5. 앱과 같은 방식으로 얼굴 한 장 합치기(검사·시트용) ─────────────────────────
ATLAS = atlas
def hexrgb(h): return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
SKIN = ["#FFE0CC", "#F9C9AA", "#F4C49E", "#B8774F", "#85503A", "#FFD5C0", "#DA9E74"]   # 서버 SKINS 와 같은 순서(11/10 81번: 7가지, 5·6은 뒤에 붙임)
HAIR = ["#2B2522", "#4A3226", "#8A5A3C", "#A9A6A2", "#EDEBE7", "#E2B85A"]
KEYI = dict(eyes=2, brows=3, nose=4, mouth=5, wrinkle=6, blush=7, beard=8, mark=19, beards=20, marks=21)
def _luma(c): return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255
def _rnd(c): return np.array([min(255, max(0, math.floor(v + 0.5))) for v in c], np.float32)
def layer_paint(L, av, skin255):
    """층 하나의 칠할 색(0~255, 없으면 None)과 alpha. FaceSheet.kt paintOf · avatar3d.js paintOf 와 같은 식."""
    lo, hi = J["skin_t"]; t = min(1.0, max(0.0, (_luma(skin255) - lo) / (hi - lo)))
    al = L.get("alpha", 1.0)
    if "alpha_dark" in L: al = L["alpha_dark"] + (al - L["alpha_dark"]) * t
    tint, col = L.get("tint"), None
    if tint in ("hair", "beard"):
        col = hexrgb(HAIR[av["hairColor"] if tint == "hair" else av["beardColor"]]) * 255
        if "sep" in L:
            d, lc, ls = L["sep"], _luma(col), _luma(skin255)
            if abs(lc - ls) < d: col = _rnd(col * (max(ls - d, 0.04) / max(lc, 1e-3)))
        if "shade" in L:   # 11/10 짧은 수염: 피부 그늘색 쪽으로 섞기(w = 밝은 피부 shade[0] ~ 짙은 피부 shade[1], 그늘 = 피부 × shade[2])
            w = L["shade"][1] + (L["shade"][0] - L["shade"][1]) * t; col = _rnd(col * (1 - w) + skin255 * L["shade"][2] * w)
    elif tint == "skin":
        k = L["k"][1] + (L["k"][0] - L["k"][1]) * t; col = _rnd(skin255 * k)
    elif tint == "pair":
        a, b = hexrgb(L["c"][0]) * 255, hexrgb(L["c"][1]) * 255; col = _rnd(b + (a - b) * t)
    return col, max(0.0, min(1.0, al))

def compose(av, size=256, src=None):
    """av: dict(eyes,brows,nose,mouth,wrinkle,blush,beard,skin,hairColor,beardColor) — FaceSheet.kt 와 같은 순서·방식.
    src = (json, 아틀라스 float RGBA): 다른 아틀라스(예: 바꾸기 전)로 합칠 때."""
    Jx, ATx = src if src else (J, ATLAS)
    out = np.zeros((size, size, 4), np.float32); out[..., :3] = hexrgb(SKIN[av["skin"]]); out[..., 3] = 1
    for g in Jx["draw_order"]:
        opts = Jx["groups"][g]; i = av.get(g, 0)
        if i >= len(opts): continue
        for L in opts[i]:
            if av.get("eyes", 0) in L.get("unless_eyes", ()): continue   # 애교살 눈 + 눈 밑 선: 같은 자리라 눈 밑 선은 안 그림(79번)
            if any(not (av.get(k, 0) & b) for k, b in L.get("need", {}).items()): continue   # 그 비트가 켜졌을 때만(짧은 수염 비우기)
            si = L["by_eyes"][av.get("eyes", 0)] if "by_eyes" in L else L["sprite"]           # 눈가 주름: 눈마다 자리
            s = Jx["sprites"][si]; x, y, w, h = s["src"]; img = ATx[y:y + h, x:x + w].copy()
            col, al = layer_paint(L, av, np.round(hexrgb(SKIN[av["skin"]]) * 255))
            if col is not None:
                img[..., :3] = np.clip(img[..., :3] * (col / 255 / max(L["mean"], 0.05)), 0, 1)
            img[..., 3] *= al
            for mir in ([False, True] if L["mirror"] else [False]):
                l, t, r, b = s["dst"]
                if mir: l, r = 1 - r, 1 - l
                X0, Y0, X1, Y1 = l * size, t * size, r * size, b * size
                ix0, iy0, ix1, iy1 = int(math.floor(X0)), int(math.floor(Y0)), int(math.ceil(X1)), int(math.ceil(Y1))
                yy, xx = np.mgrid[iy0:iy1, ix0:ix1] + 0.5
                sxx = (xx - X0) / (X1 - X0) * w - 0.5; syy = (yy - Y0) / (Y1 - Y0) * h - 0.5
                if mir: sxx = w - 1 - sxx
                pm = img.copy(); pm[..., :3] *= pm[..., 3:4]
                smp = np.stack([ndi.map_coordinates(pm[..., c], (syy, sxx), order=1, cval=0.0) for c in range(4)], -1)
                reg = out[iy0:iy1, ix0:ix1]
                reg[..., :3] = smp[..., :3] + reg[..., :3] * (1 - smp[..., 3:4])
    return out

# 정면 미리보기: face.png 를 대응표 역으로 정면에 다시 비춤(머리 공 + 간단한 명암)
def front_preview(face, skin_hex, size=200, span=1.08):
    from scipy.interpolate import griddata
    global _INV
    if "_INV" not in globals(): _INV = {}
    if size not in _INV:
        ok = np.isfinite(MAP[..., 0]); jj, ii = np.nonzero(ok)
        pts = MAP[ok][:, :2]; uv = np.c_[(ii + 0.5) / MN, (jj + 0.5) / MN]
        gy, gx = np.mgrid[0:size, 0:size]; X = ((gx + 0.5) / size * 2 - 1) * span; Y = ((gy + 0.5) / size * 2 - 1) * span
        U = griddata(pts, uv, (X, Y), method="linear")
        _INV[size] = (X, Y, U)
    X, Y, U = _INV[size]; n = face.shape[0]
    r2 = X ** 2 + Y ** 2; inside = r2 < 1
    Z = np.sqrt(np.clip(1 - r2, 0, 1)); L = np.array([-0.35, -0.45, 0.82]); L /= np.linalg.norm(L)
    sh = np.clip(0.55 + 0.5 * (X * L[0] + Y * L[1] + Z * L[2]), 0, 1.08)
    img = np.ones((size, size, 3), np.float32)
    base = np.broadcast_to(hexrgb(skin_hex), (size, size, 3)).copy()
    ok = np.isfinite(U[..., 0])
    u = np.clip(U[..., 0], 0, 1) * n - 0.5; v = np.clip(U[..., 1], 0, 1) * n - 0.5
    for c in range(3):
        smp = ndi.map_coordinates(face[..., c], (np.nan_to_num(v), np.nan_to_num(u)), order=1, mode="nearest")
        base[..., c] = np.where(ok, smp, base[..., c])
    img[inside] = np.clip(base[inside] * sh[inside, None], 0, 1)
    return img

def to8(a): return Image.fromarray(np.round(np.clip(a, 0, 1) * 255).astype(np.uint8))

PEOPLE = [("아빠(동그란 눈·일자 눈썹·짧은 수염)", dict(eyes=0, brows=2, nose=1, mouth=0, wrinkle=0, blush=0, beard=1, skin=1, hairColor=0, beardColor=0)),
          ("할머니(반달눈·아치·눈가 주름·볼터치)", dict(eyes=5, brows=1, nose=1, mouth=0, wrinkle=1, blush=1, beard=0, skin=0, hairColor=3, beardColor=3)),
          ("아이(큰 눈·짧은 눈썹·활짝)", dict(eyes=1, brows=0, nose=0, mouth=1, wrinkle=0, blush=1, beard=0, skin=2, hairColor=1, beardColor=1)),
          ("할아버지(순한 눈·숱 많은·이마 주름·흰 수염)", dict(eyes=6, brows=3, nose=2, mouth=2, wrinkle=2, blush=0, beard=1, skin=3, hairColor=4, beardColor=4)),
          ("청년(긴 눈·아치·동그란 입)", dict(eyes=3, brows=1, nose=0, mouth=3, wrinkle=0, blush=1, beard=0, skin=4, hairColor=1, beardColor=1)),
          ("학생(실눈·짧은 눈썹·금발)", dict(eyes=4, brows=0, nose=1, mouth=0, wrinkle=0, blush=0, beard=0, skin=2, hairColor=5, beardColor=5))]

if A.faces:
    os.makedirs(A.faces, exist_ok=True)
    for k, (nm, av) in enumerate(PEOPLE):
        to8(compose(av, 512)).save(os.path.join(A.faces, f"face_p{k}.png"))
    print("faces ->", A.faces)

if A.sheet:
    FONT = None
    for f in ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/Supplemental/AppleGothic.ttf"):
        if os.path.exists(f): FONT = ImageFont.truetype(f, 15); break
    base = dict(eyes=0, brows=0, nose=1, mouth=0, wrinkle=0, blush=0, beard=0, skin=1, hairColor=1, beardColor=1)
    WR_NAMES = ["없음"] + ["+".join(n for b, n in enumerate(WR_BIT_NAMES) if v >> b & 1) for v in range(1, 16)]
    rows0 = [("눈", "eyes", EYE_NAMES), ("눈썹(머리색 칠함)", "brows", BROW_NAMES), ("코", "nose", ["작은", "동그란(→작은)", "넓은"]),
             ("입", "mouth", MOUTH_NAMES), ("주름", "wrinkle", WR_NAMES), ("볼터치", "blush", ["없음", "볼터치"]),
             ("수염(2D)", "beard", ["없음", "짧은 수염"])]
    rows = []   # 한 줄 7칸씩 접기(번호는 그대로)
    for title, g, names in rows0:
        for k0 in range(0, len(names), 7): rows.append((title if k0 == 0 else "", g, list(enumerate(names))[k0:k0 + 7]))
    CELL, LAB = 200, 22
    nrow = len(rows) + 2
    sheet = Image.new("RGB", (150 + CELL * 7, (CELL + LAB) * nrow + 10), "white"); d = ImageDraw.Draw(sheet)
    def put(img, r, c, text):
        x = 150 + c * CELL; y = r * (CELL + LAB) + 5
        sheet.paste(img.resize((CELL - 8, CELL - 8), Image.LANCZOS) if img.size[0] != CELL - 8 else img, (x + 4, y)); d.text((x + 6, y + CELL - 6), text, fill="#333", font=FONT)
    for r, (title, g, names) in enumerate(rows):
        d.text((8, r * (CELL + LAB) + 80), title, fill="black", font=FONT)
        for c, (ii, nm) in enumerate(names):
            av = dict(base); av[g] = ii
            if g == "beard": av.update(hairColor=0, beardColor=0)
            put(to8(front_preview(compose(av, 256), SKIN[av["skin"]], CELL - 8)), r, c, f"{ii} {nm}")
    r = len(rows); d.text((8, r * (CELL + LAB) + 70), "사람 6명\n(정면 미리보기)", fill="black", font=FONT)
    for c, (nm, av) in enumerate(PEOPLE):
        put(to8(front_preview(compose(av, 256), SKIN[av["skin"]], CELL - 8)), r, c, nm.split("(")[0] + f" 피부{av['skin']}")
    r += 1; d.text((8, r * (CELL + LAB) + 70), "face.png 그대로\n(앱이 넣는 256)", fill="black", font=FONT)
    for c, (nm, av) in enumerate(PEOPLE):
        put(to8(compose(av, 256)[..., :3]), r, c, nm.split("(")[0])
    sheet.save(A.sheet); print("sheet ->", A.sheet)

# ── 7. 새 부품 검사(11/10): 피부 5 × 새 부품, 왼쪽 칸 = 비교할 지금 부품, 앱과 같은 합치기·정면 미리보기 ─────────────
if A.check:
    os.makedirs(A.check, exist_ok=True)
    FONT = None
    for f in ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/Supplemental/AppleGothic.ttf"):
        if os.path.exists(f): FONT = ImageFont.truetype(f, 14); break
    OLD = None
    if A.check_base:
        OLD = (json.load(open(os.path.join(A.check_base, "face_atlas.json"))),
               np.array(Image.open(os.path.join(A.check_base, "face_atlas.png")).convert("RGBA")).astype(np.float32) / 255)
    PV, SPAN = 480, 1.08
    REG = dict(eyes=(-0.9, -0.55, 0.9, 0.5), brows=(-0.9, -0.55, 0.9, 0.5), mouth=(-0.55, 0.3, 0.55, 0.9), wrinkle=(-0.95, -0.7, 0.95, 0.85))
    def view(av, g, src=None, size=PV):
        im = to8(front_preview(compose(av, 512, src), SKIN[av["skin"]], size, SPAN))
        x0, y0, x1, y1 = REG[g]; f = lambda v: int(round((v / SPAN + 1) / 2 * size))
        return im.crop((f(x0), f(y0), f(x1), f(y1)))
    base = dict(eyes=1, brows=2, nose=1, mouth=0, wrinkle=0, blush=0, beard=0, skin=1, hairColor=0, beardColor=0)
    # (그룹, 새 번호, 이름, 비교 칸 번호, 비교 칸 출처: None=새 아틀라스, "old"=바꾸기 전)
    ROWS = [("eyes", i, EYE_NAMES[i], i if i < 14 else 7, "old" if i < 14 else None) for i in range(EYE_N) if i not in EYE_ALIAS] + \
           [("brows", 9, "긴 꼬리 눈썹", 3, None), ("brows", 3, "숱 많은 눈썹", 2, None)] + \
           [("mouth", 7, "분홍 입술", 7, "old")] + \
           [("wrinkle", 8, "눈 밑 선", 8, "old"), ("wrinkle", 15, "주름 4개 모두", 15, "old")]
    for g in ("eyes", "brows", "mouth", "wrinkle"):
        rows = [r for r in ROWS if r[0] == g]
        w0, h0 = view(base, g).size; CW, CH, LW = w0 // 2, h0 // 2, 170
        sh = Image.new("RGB", (LW + CW * 6 + 20, (CH + 24) * len(rows) + 30), "white"); d = ImageDraw.Draw(sh)
        d.text((LW, 6), "비교(지금 부품, 피부1)", fill="#555", font=FONT)
        for c in range(5): d.text((LW + CW * (c + 1) + 4, 6), f"피부{c} {SKIN[c]}", fill="#555", font=FONT)
        for r, (_, i, nm, ref, rs) in enumerate(rows):
            y = 30 + r * (CH + 24); d.text((8, y + CH // 2 - 8), f"{g} {i}\n{nm}", fill="black", font=FONT)
            av = dict(base); av[g] = ref
            if rs == "old" and OLD is None: pass
            else:
                im = view(av, g, OLD if rs == "old" else None).resize((CW, CH), Image.LANCZOS); sh.paste(im, (LW, y))
                d.text((LW + 4, y + CH + 2), f"{ref} {'바꾸기 전' if rs == 'old' else '지금'}", fill="#777", font=FONT)
            for c in range(5):
                av = dict(base); av[g] = i; av["skin"] = c; av["hairColor"] = [0, 1, 0, 0, 0][c]
                sh.paste(view(av, g).resize((CW, CH), Image.LANCZOS), (LW + CW * (c + 1), y))
        sh.save(os.path.join(A.check, f"check_{g}.png"))
    # 크기·자리 줄자: 눈 14개를 같은 칸(왼쪽 눈 자리)에, 큰 눈 상자(빨강)·눈 자리 가운데(파랑)를 겹쳐 그림
    def strip(g, idx, names, ref, box):
        tiles = []
        for i in idx:
            av = dict(base); av[g] = i; im = to8(compose(av, 512)[..., :3]); dd = ImageDraw.Draw(im)
            x0, y0, x1, y1 = box; dd.rectangle([x0, y0, x1, y1], outline=(230, 40, 40))
            tiles.append(im.crop(REGC[g]).resize((240, int(240 * (REGC[g][3] - REGC[g][1]) / (REGC[g][2] - REGC[g][0]))), Image.LANCZOS))
        tw, th = tiles[0].size; cols = 7; rws = (len(tiles) + cols - 1) // cols
        out = Image.new("RGB", (tw * cols, (th + 20) * rws), "white"); d = ImageDraw.Draw(out)
        for k, (t, i) in enumerate(zip(tiles, idx)):
            out.paste(t, ((k % cols) * tw, (k // cols) * (th + 20))); d.text(((k % cols) * tw + 4, (k // cols) * (th + 20) + th + 2), f"{i} {names[i]}", fill="black", font=FONT)
        out.save(os.path.join(A.check, f"ruler_{g}.png"))
    # face.png 칸 좌표(512)에서 '기준 부품' 상자: 앱이 실제로 쓰는 텍스처 위 크기 비교
    def dst_box(nm):
        s_ = next(x for x in spr if x["name"] == nm); l, t, r, b = s_["dst"]; return (l * 512, t * 512, r * 512, b * 512)
    REGC = dict(eyes=(40, 200, 220, 360), brows=(20, 130, 210, 230), mouth=(150, 360, 362, 470))
    strip("eyes", list(range(EYE_N)), EYE_NAMES, 1, dst_box("eye1_L"))
    strip("brows", list(range(len(BROW_NAMES))), BROW_NAMES, 3, dst_box("brow3"))
    strip("mouth", list(range(9)), MOUTH_NAMES, 0, dst_box("mouth0"))
    print("정면 1024 상자(가로×세로, 가운데 x,y):")
    for nm, (x0, y0, x1, y1) in FRONT.items():
        if nm.endswith("_R") or nm.startswith(("nose", "blush", "stubble", "wr_fore")): continue
        print(f"  {nm:9s} {x1 - x0:6.1f}×{y1 - y0:6.1f}  ({(x0 + x1) / 2:7.1f},{(y0 + y1) / 2:7.1f})")
    print("check ->", A.check)
