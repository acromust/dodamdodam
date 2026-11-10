"""심어둠 프로토타입 서버.

숨기는 사람은 웹 링크(/)로 목소리를 숨기고, 차 앱은 /api 로 오늘 메시지를 받아 간다.
표준 라이브러리만 쓴다. 실행: python3 server.py [포트]  (기본 8090)
에뮬레이터에서는 http://10.0.2.2:8090 으로 닿는다.
"""
import array
import base64
import hashlib
import hmac
import html
import json
import math
import os
import queue
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import avatar
import push
import store

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
DATA = os.path.join(ROOT, "data")
AUDIO = os.path.join(DATA, "audio")
PHOTO = os.path.join(DATA, "photo")  # 남기는 사람이 내 정보에 넣은 사진. 웹은 자기 것만(/api/photo), 그 초대 링크를 만든 차만(/api/car/photo) 받는다
DB = os.path.join(DATA, "db.json")
os.makedirs(AUDIO, exist_ok=True)
os.makedirs(PHOTO, exist_ok=True)
CAR_KEY = os.environ.get("CAR_KEY", "")
KAKAO_JS_KEY = os.environ.get("KAKAO_JS_KEY", "").strip()    # 카카오 지도(웹에 그대로 내려 주는 공개 키)
KAKAO_REST_KEY = os.environ.get("KAKAO_REST_KEY", "").strip()  # 카카오 장소 검색(서버에만 둔다)
_place_log = {}   # 요청한 곳 → 최근 검색 시각들(한 곳이 몰아 쓰지 못하게)
_place_day = [0, 0]   # [오늘 날짜 번호, 오늘 검색 수]


def kakao_place(q, lat, lon, who):
    """카카오 키워드 검색 → [{lat, lon, name, addr}] 최대 5개. 키가 없거나 막히면 None(웹이 다른 검색으로)."""
    q = (q or "").strip()[:60]
    if not KAKAO_REST_KEY or not q:
        return None
    now = time.time()
    day = int(now // 86400)
    if _place_day[0] != day:
        _place_day[:] = [day, 0]
    recent = [t for t in _place_log.get(who, []) if now - t < 60]
    if len(recent) >= 30 or _place_day[1] >= 50000:   # 한 곳 1분 30번, 하루 전체 5만 번(카카오 무료 한도 안)
        return None
    _place_log[who] = recent + [now]
    if len(_place_log) > 5000:
        _place_log.clear()
    _place_day[1] += 1
    args = {"query": q, "size": "5"}
    try:
        la, lo = float(lat), float(lon)
        if 33 <= la <= 39 and 124 <= lo <= 132:
            args.update(y=f"{la:.5f}", x=f"{lo:.5f}")   # 지도 가운데와 가까운 곳이 앞쪽으로(정확도 순서는 그대로)
    except ValueError:
        pass
    import urllib.request
    from urllib.parse import urlencode
    req = urllib.request.Request("https://dapi.kakao.com/v2/local/search/keyword.json?" + urlencode(args),
                                 headers={"Authorization": "KakaoAK " + KAKAO_REST_KEY})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            docs = json.loads(r.read().decode("utf-8")).get("documents", [])
    except Exception as e:
        print("카카오 검색 안 됨:", type(e).__name__, getattr(e, "code", ""), flush=True)
        return None
    hits = []
    for d in docs[:5]:
        try:
            hits.append({"lat": float(d["y"]), "lon": float(d["x"]), "name": d.get("place_name", "")[:40],
                         "addr": (d.get("road_address_name") or d.get("address_name") or "")[:60]})
        except (KeyError, ValueError):
            continue
    return hits
CLOUD = bool(os.environ.get("PORT"))  # 렌더 같은 클라우드에서 도는지


class Gone(ValueError):
    """운전자가 끊은 초대 링크. 웹은 410을 받으면 '더 이상 쓸 수 없는 링크' 화면으로 간다."""


class Taken(ValueError):
    """이 폰의 링크가 아니다. 웹은 403을 받으면 안내 화면으로 간다. taken: 다른 폰이 먼저 연 링크."""
    def __init__(self, msg, taken=True):
        super().__init__(msg)
        self.taken = taken


class Quiet(ValueError):
    """녹음에 말소리가 거의 없다. 웹은 422를 받으면 '이대로 남길까요?'를 묻고, 남기기를 고르면 quiet_ok로 다시 보낸다."""


class NoInvite(ValueError):
    """없는 초대 코드. 코드를 아무거나 넣어 보는 것으로 보고 센다(guess_miss)."""


class TooMany(ValueError):
    """같은 곳에서 없는 코드를 GUESS_MAX번 넣었다. 웹은 429를 받으면 몇 분 뒤에 다시 하라고 알린다."""
    def __init__(self, wait, everyone=False):
        m = max(1, math.ceil(wait / 60))
        # everyone: 여러 곳에서 한꺼번에 틀린 코드가 몰려 코드 넣기 전체를 잠시 막았다(이 사람이 틀린 게 아니다)
        super().__init__(f"지금은 코드를 확인할 수 없어요. {m}분 뒤에 다시 입력해 주세요" if everyone
                         else f"코드를 여러 번 틀렸어요. {m}분 뒤에 다시 입력해 주세요")
        self.wait = wait
        self.everyone = everyone


class TooBig(ValueError):
    """본문이 너무 크다(Content-Length를 보고 읽기 전에 막는다). 웹은 413의 error 글을 그대로 보여 준다."""


# 초대 코드는 숫자 6자리라 아무거나 넣어 보면 맞을 수 있다: 같은 곳(IP)에서 없는 코드를 쉬지 않고(10분 넘게 쉬면 새로 센다) GUESS_MAX번 넣으면 GUESS_LOCK초 막는다.
# 맞는 코드를 넣어도 세던 것을 지우지 않는다(아는 코드를 섞어 넣으며 계속 시도하지 못하게). 서버를 다시 켜면 새로 센다.
# 곳(IP)을 바꿔 가며 넣는 것까지 막으려고 모든 곳을 합친 것도 센다(EVERYONE): ALL_MAX번이면 잠시 동안 '이미 틀린 적이 있는 곳'만 막는다.
# 처음부터 맞는 코드를 넣는 가족은 그대로 들어온다. 같은 곳이 같은 코드를 잠깐 사이에 또 틀리면(첫 화면 /와 /api/invite처럼 한 번 여는 데 두 번 묻는 것) 한 번만 센다.
GUESS_MAX, GUESS_LOCK, ALL_MAX = 10, 600, 300
GUESS_SAME = 120  # 같은 코드를 이 초 안에 또 틀리면 한 번으로 센다
EVERYONE = "*"
guesses = {}  # 곳 → [틀린 횟수, 막힌 끝 시각, 마지막으로 틀린 시각, 마지막으로 틀린 코드]
guess_mu = threading.Lock()


def guess_wait(who):
    """막혀 있으면 남은 초, 아니면 0."""
    with guess_mu:
        g = guesses.get(who)
        left = g[1] - time.time() if g else 0
    return math.ceil(left) if left > 0 else 0


def guess_seen(who):
    """이 곳이 최근에 없는 코드를 넣은 적이 있는지(GUESS_LOCK 안에 틀렸거나, 막혔다가 풀린 지 GUESS_LOCK이 안 됨)."""
    now = time.time()
    with guess_mu:
        g = guesses.get(who)
        return bool(g) and (g[1] > now - GUESS_LOCK or (g[0] > 0 and now - g[2] <= GUESS_LOCK))


def guess_miss(who, code=""):
    now = time.time()
    with guess_mu:
        if len(guesses) > 5000:  # 오래 조용한 곳은 잊는다
            for k in [k for k, g in guesses.items() if g[2] < now - GUESS_LOCK and g[1] < now - GUESS_LOCK and k != EVERYONE]:
                del guesses[k]
        mine = guesses.get(who)
        if code and mine and mine[3] == code and now - mine[2] < GUESS_SAME:
            mine[2] = now
            return   # 한 번 여는 데 같은 코드를 두 번 물었다: 한 번만 센다
        for key, limit in ((who, GUESS_MAX), (EVERYONE, ALL_MAX)):
            g = guesses.setdefault(key, [0, 0, now, ""])
            if now - g[2] > GUESS_LOCK:
                g[0] = 0
            g[0] += 1
            g[2] = now
            if g[0] >= limit:
                g[0], g[1] = 0, now + GUESS_LOCK
        guesses[who][3] = code


def norm_code(s):
    """사람이 손으로 넣은 코드: 띄어쓰기·하이픈을 빼고 대문자로(예전 영문+숫자 코드 7x3-rgx도 7X3RGX로 찾는다)."""
    return re.sub(r"[\s\-‐‑–—.]", "", str(s or "")).upper()[:12]


TAKEN = "차 화면에서 새 초대 코드를 받아 주세요"  # 같은 사람이 카톡→Safari로 옮겨도 뜬다(웹 제목은 '이미 다른 폰에서 연 코드예요')
OOPS = "잠시 문제가 생겼어요. 다시 눌러 주세요"  # 예상 못 한 오류(영어 예외 글은 로그에만)
BLOCKED = "들려줄 수 없는 내용이에요. 다시 녹음해 주세요"  # 검수에서 막힘(무엇을 막는지는 약관에만 적는다)


def user_error(e):
    """사람에게 보여 줄 오류 글. 우리가 쓴 한글 글만 그대로 내보내고, 파이썬 예외 글(KeyError 'audio',
    base64 'Incorrect padding', JSON 'Expecting value' 등)은 로그에만 남기고 한글 한 줄로 바꾼다."""
    msg = str(e) if isinstance(e, ValueError) else ""
    if re.search("[가-힣]", msg):
        return msg
    print("요청 오류:", type(e).__name__, str(e)[:80], flush=True)
    return OOPS


# 예시 듣기(웹 홈 아래): 순간별 예시 목소리 6개. 차 앱 res/raw/demo_*.m4a를 그대로 복사해 둔 것
EXAMPLES = ("start", "arrive", "home", "rain", "long", "battery")
# 예시 듣기 목소리(11/10 확정): 순간마다 하나, 여섯 개. (파일, 순간, 보내는 사람, 듣는 사람, 문장). 파일은 /ex/<file>.m4a,
# 제미나이 TTS(gemini-2.5-flash-preview-tts 하나)로 만들고 받아쓰기로 마지막 글자까지 확인, 끝 처리(0.4초 쉼) 포함 5초 안.
# 이름표는 보내는 사람 나이 + 관계, 듣는 사람 나이는 필요할 때만. 웹은 /api/examples 로 받는다
EX_VOICES = (
    ("ex_start", "start", "30대 아내", "남편", "여보, 오늘 발표 날이죠? 잘하고 와요!"),
    ("ex_arrive", "arrive", "8살 딸", "아빠", "아빠, 오늘도 운전하느라 수고했어요!"),
    ("ex_home", "home", "30대 아내", "남편", "여보, 애들 방금 잠들었어요. 문 살살 열어요."),
    ("ex_rain", "rain", "딸", "아빠", "아빠, 비 오니까 천천히 와요. 우산은 뒷자리 아래!"),
    ("ex_long", "long", "70대 엄마", "40대 아들", "아들, 명절이라 길 막히지? 쉬엄쉬엄 와~"),
    ("ex_battery", "battery", "아내", "남편", "여보, 충전할 때 글로브박스 포인트카드 적립해요."),
)
# 예전 순간별 6개(demo_*, 차 앱 res/raw 사본). 새 파일(ex_<순간>.m4a)이 아직 없는 순간에만 목록에 넣는다(주소는 늘 열린다)
EX_DEMO = (("start", "아내", "남편", "오늘 3시 치과 예약 있는 거 잊지 마요."),
           ("arrive", "딸", "아빠", "아빠, 오늘도 운전하느라 수고 많으셨어요!"),
           ("home", "딸", "아빠", "아빠, 오는 길에 바나나 우유 하나만 사다 주시면 안 돼요?"),
           ("rain", "딸", "아빠", "아빠, 비 오니까 천천히 와요. 엄마가 뒷자리 아래 우산 있대요!"),
           ("long", "아내", "남편", "여보, 많이 달렸죠? 다음 휴게소에서 커피 한잔하고 좀 쉬었다 가요."),
           ("battery", "아내", "남편", "여보, 글로브박스 안에 포인트카드 있으니까 충전할 때 적립 꼭 해요."))


def _examples():
    """예시 목록: 순간마다 하나, 순간 차례대로. 새 파일이 있으면 새 목소리, 없으면 예전 demo_(그때 문장·이름표)"""
    ex = os.path.join(WEB, "ex")
    new = {m: {"moment": m, "from": f, "to": t, "text": x, "audio": f"/ex/{n}.m4a"} for n, m, f, t, x in EX_VOICES
           if os.path.exists(os.path.join(ex, f"{n}.m4a"))}
    old = {m: {"moment": m, "from": f, "to": t, "text": x, "audio": f"/ex/demo_{m}.m4a"} for m, f, t, x in EX_DEMO}
    return [new.get(m) or old[m] for m in EXAMPLES]


EX_LIST = _examples()
# 폰 웹 캐릭터 미리보기(avatar3d.js): 차 앱 plaza_char2.glb 의 웹용 가벼운 사본 + 얼굴 부품 그림(car-app/tools/char/web_char.py 가 만든다).
# 주소에 ?v= 를 붙여 받으므로 오래 담아 두게 한다. 큰 파일이라 브라우저가 gzip을 받으면 줄여서 보낸다
AVATAR_FILES = ("/avatar/char.glb", "/avatar/face_atlas.png", "/avatar/face_atlas.json", "/avatar/plaza.glb",  # plaza.glb: 광장 그림 장면(car-app/tools/web_plaza.py)
                "/avatar/face_atlas_hd.webp", "/avatar/face_atlas_hd.json")  # 11/10 캐릭터 만들기 고르는 칸용 큰 얼굴 부품 그림(face_atlas.py, 얼굴 1024 기준)
WEB_FILES = ("/manifest.json", "/sw.js", "/icon-192.png", "/icon-512.png", "/hello-car.jpg", "/hello-plaza.jpg", "/hello-plaza-720.webp", "/hello-plaza-1080.webp", "/hello-plaza-1440.webp", "/home-ios.jpg", "/home-android.jpg", "/kakao-out.jpg", "/badge-96.png", "/icon-maskable-512.png", "/avatar3d.js") + tuple(f"/ex/demo_{k}.m4a" for k in EXAMPLES) + tuple(e["audio"] for e in EX_LIST if "/demo_" not in e["audio"]) + AVATAR_FILES  # 홈 화면에 추가·알림용  # 인터넷에 올렸을 때 차 앱만 쓰는 주소를 여는 열쇠(차 앱 빌드에 같이 넣는다)


_GZ = {}


def gzipped(path):
    """파일을 gzip으로 줄인 것(파일이 바뀌면 다시). 캐릭터 모델(약 3.9MB → 2.2MB)처럼 큰 정적 파일용."""
    import gzip
    key = (path, os.path.getmtime(path))
    with lock:
        hit = _GZ.get(path)
    if hit and hit[0] == key:
        return hit[1]
    with open(path, "rb") as f:
        body = gzip.compress(f.read(), 6)
    with lock:
        _GZ[path] = (key, body)
    return body


def audio_file(name):
    """목소리 파일의 로컬 경로. 서버가 재시작돼 로컬에 없으면 클라우드 보관에서 내려받는다."""
    p = os.path.join(AUDIO, os.path.basename(name))
    if not os.path.exists(p):
        store.download("audio/" + os.path.basename(name), p)
    return p


def remove_audio(name):
    p = os.path.join(AUDIO, os.path.basename(name))
    if os.path.exists(p):
        os.remove(p)
    store.remove("audio/" + os.path.basename(name))


MAX_PHOTO = 300 * 1024  # 웹이 256px JPEG로 줄여 보낸다. 보통 30KB 안팎
CODE_RE = re.compile(r"[A-Z0-9]{4,12}")  # 초대 코드 모양(지금은 숫자 6자리로 만든다. 예전 코드는 대문자·숫자 6자리)


def photo_file(name):
    p = os.path.join(PHOTO, os.path.basename(name))
    if not os.path.exists(p):
        store.download("photo/" + os.path.basename(name), p)
    return p


def remove_photo(name):
    p = os.path.join(PHOTO, os.path.basename(name))
    if os.path.exists(p):
        os.remove(p)
    store.remove("photo/" + os.path.basename(name))


def photo_v(inv):
    """차가 받아 두는 사진의 판 번호(사진을 바꿀 때마다 파일 이름이 새로 생겨 같이 바뀐다).
    검수를 통과한 사진(photo_ok가 True)만 준다. 사진이 없거나 검수 전·탈락이면 None(차에는 안 나간다)."""
    inv = inv or {}
    p = inv.get("photo")
    return p[:12] if p and inv.get("photo_ok") is True else None


def owner_name(v):
    """초대장에 쓰는 운전자 이름(예: 홍길동). 뒤에 붙인 '님'은 뗀다(웹이 '홍길동님'으로 붙인다). 없으면 None."""
    n = re.sub(r"\s+", " ", str(v or "")).strip()
    n = re.sub(r"\s*님$", "", n).strip()[:10]
    return n or None


def new_code(db):
    """새 초대 코드: 숫자 6자리(차 화면을 보고 말로 불러 주기 쉽게). 0으로 시작하지 않고, 111111·123456 같은 건 뺀다.
    끊은 링크도 기록에 남아 있어서 예전 코드(영문+숫자 포함)와 겹치지 않는다."""
    taken = {i["code"] for i in db["invites"]}
    while True:
        code = str(secrets.choice("123456789")) + "".join(secrets.choice("0123456789") for _ in range(5))
        if code not in taken and len(set(code)) > 2 and code not in "1234567890" and code not in "9876543210":
            return code


PHOTO_BAD = "이 사진은 쓸 수 없어요. 다른 사진을 골라 주세요"  # 웹이 사진 고를 때 보여 주는 말과 같다


def check_photo(raw, timeout, budget=None):
    """사진 검수 한 번(moderate.py, 목소리와 같은 키·모델 순서). pass/review/block, 검수 자체가 안 되면 None."""
    try:
        import moderate
        return moderate.check_photo(raw, timeout=timeout, budget=budget).get("verdict", "review")
    except Exception as e:
        print("사진 검수 실패:", type(e).__name__, getattr(e, "code", ""), flush=True)
        return None


def moderate_photo(raw):
    """올린 사진의 검수 상태: True(통과) · "pending"(검수를 못 함·애매함: 뒤에서 다시 본다). 분명히 안 되면 ValueError."""
    if os.environ.get("MODERATE") == "0":
        return True   # 검수를 끈 시연·테스트
    verdict = check_photo(raw, timeout=6, budget=8)  # 남기는 사람을 오래 세우지 않는다
    if verdict == "block":
        raise ValueError(PHOTO_BAD)
    return True if verdict == "pass" else "pending"


def store_photo(b64):
    """내 정보 사진. JPEG만, 크기 제한, 검수. (파일 이름, 검수 상태)를 돌려준다."""
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError):
        raise ValueError("사진을 올리지 못했어요. 다른 사진을 골라 주세요")
    if len(raw) > MAX_PHOTO:
        raise ValueError("사진이 너무 커요. 다른 사진을 골라 주세요")
    if not raw.startswith(b"\xff\xd8\xff"):
        raise ValueError("사진을 올리지 못했어요. 다른 사진을 골라 주세요")
    ok = moderate_photo(raw)
    name = f"{uuid.uuid4().hex}.jpg"
    with open(os.path.join(PHOTO, name), "wb") as f:
        f.write(raw)
    store.upload(os.path.join(PHOTO, name), "photo/" + name, "image/jpeg")
    print("사진 검수:", "통과" if ok is True else "보류", flush=True)
    return name, ok

# 순간: 주행 중 열리므로 5초 이내
MOMENTS = {
    "start": {"label": "차 탈 때", "max_sec": 5},
    "arrive": {"label": "주차했을 때", "max_sec": 5},
    "home": {"label": "집 근처에 왔을 때", "max_sec": 5},
    "rain": {"label": "비 올 때", "max_sec": 5},
    "long": {"label": "오래 달렸을 때", "max_sec": 5},
    "battery": {"label": "배터리·기름이 부족할 때", "max_sec": 5},
    "place": {"label": "장소에 왔을 때", "max_sec": 5},
}
# 반복: once(그날 한 번) · each(그날부터 30일 동안 그 순간마다, 하루 한 번). 운전자는 each를 그만 들을 수 있다(stopped).
REPEATS = ("once", "each")
ANY_DAYS = 30  # 날짜 "언제든"과 반복 "매번": 남긴 날부터 들려주는 최대 일수
MAX_PLACES = 3  # 남기는 사람 한 명이 동시에 남겨 둘 수 있는 특정 장소 메시지
PLACE_FULL = "장소 메시지는 3개까지예요. 하나를 지우면 새로 남길 수 있어요"  # MAX_PLACES개를 다 썼을 때(웹 확인창과 같은 말)
EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3",
       "audio/aac": "aac", "audio/wav": "wav", "audio/x-wav": "wav", "audio/x-m4a": "m4a"}
MAX_BYTES = 3 * 1024 * 1024

lock = threading.Lock()
# 저장할 때마다 바뀌는 번호. 차는 이 번호가 바뀔 때까지 기다렸다가(/api/changes) 바로 목록을 다시 받는다.
# 켤 때마다 다른 값에서 시작해서, 서버를 다시 켜도 차가 놓치지 않는다.
version = int(time.time() * 1000)
changed = threading.Condition()


def bump():
    global version
    with changed:
        version += 1
        changed.notify_all()


def any_open(m, day):
    """날짜를 언제든으로 고른 메시지가 이날 아직 유효한지."""
    return bool(m.get("any")) and m["date"] <= day <= (date.fromisoformat(m["date"]) + timedelta(days=ANY_DAYS)).isoformat()


def place_waiting(m, sender, code):
    """이 사람의 자리를 차지하는 특정 장소 메시지. 날짜만 본다: 들었는지로 세면 새 메시지가 들어가는지를 보고 들은 걸 알게 된다.
    초대 링크가 있으면 링크로, 없으면 이름으로 센다."""
    if m.get("moment") != "place" or (m.get("invite") != code if code else m.get("sender") != sender):
        return False
    return last_day(m) >= date.today().isoformat()


def load(fill=True):
    if not os.path.exists(DB):
        return {"messages": [], "replies": [], "invites": []}
    with open(DB, encoding="utf-8") as f:
        db = json.load(f)
    db.setdefault("invites", [])
    for m in db["messages"]:
        # 예전에 시각으로 남긴 들음·사라짐·그만 듣기를 날짜로 줄인다
        for k in ("played", "expired", "stopped"):
            if isinstance(m.get(k), (int, float)):
                m[k] = date.fromtimestamp(m[k]).isoformat()
    if fill:
        fill_people(db)   # 캐릭터·대표색·자리가 없는 예전 사람에게 채운다(다음 저장 때 같이 남는다)
    return db


def find_invite(db, code):
    return next((i for i in db["invites"] if i["code"] == code), None)


INVITE_TTL = 24 * 3600  # 아무 폰도 열지 않은 초대 코드(다시 연결로 만든 코드 포함)는 만든 지 하루가 지나면 못 쓴다(끊긴 코드와 같게)


def opened(inv):
    """어떤 폰이 이 코드를 가졌는지. 열쇠 이전에 쓰던 옛 코드(이름이 있고 다시 연결로 만든 게 아님)도 연 것으로 본다."""
    return bool(inv.get("device_hash")) or (bool(inv.get("name")) and not inv.get("reissued"))


def expired(inv):
    """아무도 열지 않은 채 하루가 지난 코드."""
    return not inv.get("revoked") and not opened(inv) and (inv.get("created") or 0) < time.time() - INVITE_TTL


def dead(inv):
    """남기는 사람 쪽에서 더는 못 쓰는 코드: 끊겼거나 하루 동안 아무도 안 열었다. 웹에는 둘 다 410(끊긴 링크)으로 답한다."""
    return bool(inv.get("revoked")) or expired(inv)


def own_invite(db, code, device=None, dev=False):
    """남기는 사람 요청: 초대 코드에 처음 연 폰의 열쇠까지 맞아야 한다. 없으면 400, 끊긴 링크면 410, 다른 폰이면 403.
    device: 열쇠 하나 또는 후보 여러 개(헤더·쿠키). 맞은 열쇠는 inv를 돌려주는 대신 own_device로 확인한다."""
    inv = find_invite(db, code) if code else None
    if not inv:
        raise NoInvite("초대 링크로 들어와 주세요")
    if dead(inv):
        raise Gone("이 초대 링크는 열 수 없어요")
    if not dev:
        own_device(inv, device)
    return inv


def device_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


KEY_RE = re.compile(r"[A-Za-z0-9_-]{22,64}")  # 웹이 직접 만든 폰 열쇠 모양(랜덤 24바이트 base64url = 32자)


def own_device(inv, token):
    """링크를 처음 연 폰인지. 서버에는 열쇠의 해시만 둔다(기록이 새도 열쇠는 안 샌다).
    token: 열쇠 하나 또는 후보 목록(헤더, 쿠키 순). 맞은 열쇠를 돌려준다."""
    h = inv.get("device_hash")
    if not h:
        # 아무 폰도 열지 않은 링크로 바로 남기려는 것(옛 화면을 띄워 둔 채였거나 링크를 열지 않은 요청): 링크부터 다시 연다
        raise Taken("초대 링크를 다시 눌러 주세요", taken=False)
    for t in ([token] if isinstance(token, str) or token is None else token):
        if t and hmac.compare_digest(h, device_hash(t)):
            return t
    raise Taken(TAKEN)


def claim_invite(db, inv, token=None):
    """처음 연 폰에 열쇠를 준다. 웹이 직접 만든 열쇠(token)를 보내면 그것을 쓴다: 응답이 끊겨도 웹은 열쇠를 이미 갖고 있어서
    같은 열쇠로 다시 보내면 그대로 이어진다. 안 보내면(옛 웹·시험 도구) 서버가 만든다. 서버에는 해시만 남긴다."""
    if inv.get("guardian"):
        raise Taken(TAKEN)   # 함께 쓰는 사람은 보호자 폰에서만 쓴다(다른 폰이 잠글 수 없다)
    seat(db, inv)   # 자리·대표색·캐릭터. 5명이 다 찼으면 여기서 막는다(열쇠를 주기 전에)
    if not (token and KEY_RE.fullmatch(token)):
        token = secrets.token_urlsafe(24)
    inv["device_hash"] = device_hash(token)
    inv["claimed"] = int(time.time())
    sync_kids(db, inv)   # 다시 연결로 옮겨 온 보호자: 함께 쓰는 사람도 이 폰으로
    save(db)
    return token


def of_car(x, car):
    """이 차의 것인지. 차 번호가 없는 옛 기록·시험 기록은 맥 시연에서만 모든 차에 보이고, 클라우드에선 안 보인다."""
    if not x.get("car"):
        return not CLOUD
    return x.get("car") == car


# ---------- 광장: 사람마다 자리(slot 1~5)·대표색(color 0~7)·캐릭터(avatar) ----------
# 자리는 가입(폰이 코드를 가질 때) 순서대로 가장 왼쪽 빈 번호. 끊긴 사람 자리는 비워 두고 다른 사람을 당기지 않는다.
# 대표색은 같은 차 안에서 겹치지 않는다. 다시 연결(reissue)은 같은 사람이라 자리·색·캐릭터를 새 코드로 옮긴다.
FULL = "이 차는 5명이 다 찼어요"  # 폰 웹: 6번째 사람이 들어오려 할 때(웹은 차 주인 이름을 넣어 '○○님 차는 5명이 다 찼어요')
FULL_CAR = "5명까지 연결할 수 있습니다"  # [확인 필요] 새 문구(차): 5명이 다 찬 차가 초대 코드를 만들려 할 때
COLOR_TAKEN = "다른 분이 쓰는 색이에요. 다른 색을 골라 주세요"  # [확인 필요] 새 문구(폰 웹)
ORDER_BAD = "자리를 바꾸지 못했습니다. 다시 해 주세요"  # [확인 필요] 새 문구(차)


def same_car(a, b):
    """같은 차의 사람인지(차 번호가 같다. 번호 없는 시험 기록은 번호 없는 것끼리)."""
    return (a or None) == (b or None)


def seated(inv):
    return not inv.get("revoked") and isinstance(inv.get("slot"), int)


def joined(inv):
    """광장에 앉을 사람: 끊기지 않았고, 폰이 이 코드를 가졌거나(옛 코드 포함) 다시 연결로 옮겨 온 사람."""
    return not inv.get("revoked") and (opened(inv) or bool(inv.get("reissued") and inv.get("name")))


def peers(db, car, but=None):
    """이 차에 앉은 사람들(but은 뺀다)."""
    return [i for i in db["invites"] if seated(i) and same_car(i.get("car"), car) and i is not but]


def free_slot(db, car):
    used = {i["slot"] for i in peers(db, car)}
    return next((s for s in range(1, avatar.MAX_PEOPLE + 1) if s not in used), None)


def used_colors(db, car, but=None):
    """이 차에서 이미 쓰는 대표색(이름 없이 번호만)."""
    return sorted({i["color"] for i in peers(db, car, but) if isinstance(i.get("color"), int)})


def seat(db, inv):
    """처음 가입할 때 자리·대표색·캐릭터를 정한다(이미 있으면 그대로). 5명이 다 찼으면 ValueError(FULL)."""
    if seated(inv):
        return False
    s = free_slot(db, inv.get("car"))
    if s is None:
        raise ValueError(FULL)
    taken = set(used_colors(db, inv.get("car"), inv))
    inv["slot"] = s
    if not isinstance(inv.get("color"), int) or inv["color"] in taken or not 0 <= inv["color"] < avatar.NCOLORS:
        inv["color"] = next(c for c in range(avatar.NCOLORS) if c not in taken)
    avatar.upgrade(inv.get("avatar"))
    if not avatar.valid(inv.get("avatar")):
        inv["avatar"] = avatar.default_avatar(s)
    return True


def fill_people(db):
    """예전 기록 채우기: 가입했는데 자리가 없는 사람에게 가입 순서대로 자리·색·캐릭터를 준다.
    빈 칸만 채우고 정해진 순서(가입 시각, 코드)로 하므로 두 번 돌려도 같다. 6번째부터는 자리 없이 둔다(메시지는 그대로 오간다)."""
    changed = False
    for inv in sorted((i for i in db["invites"] if joined(i) and not seated(i)),
                      key=lambda i: (i.get("claimed") or i.get("reissued") or i.get("created") or 0, i["code"])):
        try:
            changed = seat(db, inv) or changed
        except ValueError:
            pass
    for inv in db["invites"]:
        if seated(inv) and avatar.upgrade(inv.get("avatar")):   # 새로 붙은 칸(수염색)은 예전 모습 그대로 채운다
            changed = True
        if seated(inv) and not avatar.valid(inv.get("avatar")):
            inv["avatar"] = avatar.default_avatar(inv["slot"])
            changed = True
        if seated(inv) and not (isinstance(inv.get("color"), int) and 0 <= inv["color"] < avatar.NCOLORS):
            taken = set(used_colors(db, inv.get("car"), inv))
            inv["color"] = next(c for c in range(avatar.NCOLORS) if c not in taken)
            changed = True
    return changed


def unseat(inv):
    """끊김·탈퇴·옮김: 자리와 색을 비운다(다른 사람은 그 자리에 그대로). 캐릭터도 지운다."""
    for k in ("slot", "color", "avatar"):
        inv.pop(k, None)


# ---------- 함께 쓰는 사람(만 14세 미만, 11/08 결정 W1) ----------
# 만 14세 미만의 목소리는 법정대리인 동의를 받고 확인해야 한다(개인정보 보호법 22조의2). 그래서 아이가 직접 가입하지 않고,
# 이미 가입한 보호자(14세 이상)가 자기 폰에서 '함께 쓰는 사람'으로 추가하며 보호자 동의를 누른다.
# 같은 차의 새 사람(invite 기록)이라 자리·대표색·캐릭터·이름은 따로이고, 차는 예전처럼 invite 코드로 사람을 찾는다(차 변경 없음).
# guardian: 보호자 코드, consent: 보호자가 동의한 시각. 폰 열쇠는 보호자 것(device_hash를 같게 둔다): 보호자 폰에서만 그 사람으로 남기고 보관함을 본다.
# 다른 폰은 이 코드를 열어 잠글 수 없다(claim_invite·/api/invite). 보호자가 탈퇴하거나 끊기면(차가 끊기·신고) 같이 끊고 지운다.
KID_FULL_LEN = 12   # 함께 쓰는 사람 코드: 손으로 넣을 일이 없어서 길게(맞혀 보기로 찾지 못하게)
NEED_CONSENT = "보호자 동의에 체크해 주세요"  # [확인 필요] 새 문구(폰 웹)
KID_BAD = "프로필을 만든 사람만 추가할 수 있어요"  # [확인 필요] 새 문구(폰 웹): 정상 화면에선 안 나옴
# 보호자 동의 기록(안내서 '동의를 증명할 최소 정보 보관'): consent(동의 시각)·guardian(동의한 보호자 코드)에 더해
# consent_v(그때 보여 준 동의 문구 판)·consent_items(동의한 항목)를 남긴다. 예전 기록에는 없어도 된다(읽는 곳 없음)
KID_CONSENT_V = "2026-11-10"   # 웹 '만 14세 미만 어린이 프로필' 동의 문구: "(필수) {이름}님의 법정대리인으로서 이름, 목소리, 캐릭터 수집과 이용에 동의해요. 목소리는 내용 확인을 위해 Google(미국)로 보내요"
# (2026-11-09 판은 Google 전송 문장이 없던 문구)
KID_CONSENT_ITEMS = ["name", "voice", "character"]


def kid_code(db):
    taken = {i["code"] for i in db["invites"]}
    while True:
        code = "K" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(KID_FULL_LEN - 1))
        if code not in taken:
            return code


def kids_of(db, inv):
    """이 보호자가 추가한 함께 쓰는 사람(끊긴 사람은 빼고)."""
    return [i for i in db["invites"] if inv.get("code") and i.get("guardian") == inv["code"] and not i.get("revoked")]


def kid_view(i):
    return {"code": i["code"], "name": i.get("name"), "avatar": i.get("avatar"), "color": i.get("color")}


def sync_kids(db, inv):
    """보호자 폰 열쇠가 바뀌면(다시 연결한 새 링크를 새 폰이 열었다) 함께 쓰는 사람의 열쇠도 같게."""
    for k in kids_of(db, inv):
        if inv.get("device_hash"):
            k["device_hash"] = inv["device_hash"]
        else:
            k.pop("device_hash", None)


def drop_kids(db, inv, messages):
    """보호자가 탈퇴(messages=True: 남긴 메시지까지)하거나 차가 끊었다(이름·사진·알림만, 메시지는 보관 기간대로).
    함께 쓰는 사람도 끊고 정리한다. 지울 사진 파일 이름들을 돌려준다."""
    now, photos = int(time.time()), []
    for k in kids_of(db, inv):
        if messages:
            for mid in [m["id"] for m in db["messages"] if m.get("invite") == k["code"]]:
                drop_message(db, mid)
            k["left"] = now
        photos.append(forget_person(db, k))
        k.pop("device_hash", None)
        k["revoked"] = now
    return [p for p in photos if p]


def plaza_view(db, car):
    """차 광장: 앉은 사람과 오늘 대기 중인 메시지 개수만. 누가 보냈는지·누구 것이 기다리는지는 넣지 않는다
    (사람 칸은 메시지와 상관없는 값만: 자리·코드·이름·대표색·캐릭터)."""
    today = date.today().isoformat()
    cut = revoked_codes(db)
    pending = 0
    for m in db["messages"]:
        if m.get("invite") in cut or not of_car(m, car):
            continue
        v = day_view(m, today)
        if v and not v.get("played") and not v.get("expired") and not v.get("stopped"):
            pending += 1
    people = sorted(peers(db, car), key=lambda i: i["slot"])
    return {"people": [{"slot": i["slot"], "code": i["code"], "name": i.get("name"), "color": i.get("color"),
                        "avatar": i.get("avatar")} for i in people],
            "pending": pending, "next_slot": free_slot(db, car), "max": avatar.MAX_PEOPLE}


def heard_day(m):
    """운전자가 마지막으로 끝까지 들은 날(날짜만). 안 들었으면 None."""
    days = [d for d in [m.get("played"), m.get("played_day"), *m.get("played_on", [])] if isinstance(d, str)]
    return max(days) if days else None


# 운전자가 차에서 고르는 반응(카톡 공감처럼 하나만, 다른 걸 누르면 바뀐다). 이 순서로 차 화면에 놓인다
REACTIONS = ("\u2764\ufe0f", "\U0001F44D", "\U0001F602", "\U0001F62E", "\U0001F622")   # ❤️ 👍 😂 😮 😢


def reaction_of(m):
    """메시지에 남은 반응 {emoji, at}. 예전 값(시각 숫자뿐, '잘 들었습니다' 시절)은 ❤️로 읽는다. 없으면 None."""
    r = m.get("reaction")
    if isinstance(r, int) and not isinstance(r, bool):
        return {"emoji": REACTIONS[0], "at": r}
    if isinstance(r, dict) and r.get("emoji") in REACTIONS and isinstance(r.get("at"), int):
        return {"emoji": r["emoji"], "at": r["at"]}
    return None


def react_day(m):
    """남긴 사람 보관함에 보일 반응: 이모티콘과 날짜만(시각은 내보내지 않는다). 없으면 None."""
    r = reaction_of(m)
    return {"emoji": r["emoji"], "day": date.fromtimestamp(r["at"]).isoformat()} if r else None


def revoked_codes(db):
    return {i["code"] for i in db["invites"] if i.get("revoked")}


def day_view(m, day):
    """그날 차가 받을 모습. 반복 메시지는 날짜별 들음/사라짐을 그날 값으로 바꿔 보낸다. 해당 없으면 None."""
    if m.get("moderation") in ("pending", "blocked", "lost"):
        return None  # 검수를 못 마쳤거나 막힌 목소리, 파일을 잃은 목소리(lost)는 차에 보내지 않는다
    if m.get("repeat") == "each":
        if m["date"] > day or day > last_day(m):
            return None
        if day in m.get("expired_on", []):
            return None
        v = {k: x for k, x in m.items() if k not in ("played_on", "expired_on")}
        if day in m.get("played_on", []):
            v["played"] = 1
        return v
    if m.get("any"):
        # 언제든: 순간이 올 때까지 날마다 나간다. 들은 날이 지나면 빠진다.
        if not any_open(m, day) or m.get("expired") or (m.get("played_day") and m["played_day"] != day):
            return None
        return m
    if m["date"] != day or m.get("expired"):
        return None
    return m


def box_view(db, code):
    """남기는 사람 보관함. 들었는지·언제인지를 짐작할 값은 넣지 않고, 아래에 적은 값만 골라서 내보낸다."""
    today = date.today().isoformat()
    mine = [m for m in db["messages"] if m.get("invite") == code]
    by_id = {m["id"]: m for m in mine}
    reps = [r for r in db["replies"] if r["message_id"] in by_id]

    def check(m):
        # 상태는 서버에서 일어난 일(검수 결과와 남긴 사람이 고른 날짜)로만 정한다.
        # 차가 받아 갔는지·들었는지·그만 들었는지(played·expired·stopped)는 보지 않는다: 바뀌는 때가 운전한 때를 알려 버린다.
        if m.get("moderation") == "blocked":
            return "stopped" if m.get("was_quick") else "blocked"
        if m.get("moderation") == "lost":
            return "blocked"   # 목소리 파일을 잃었다(차에 안 나간다): 다시 녹음하게 막힌 것과 같은 화면을 쓴다
        if last_day(m) < today:
            return "ended"     # 기간이 끝났다(검수를 못 마쳤어도 더는 차에 안 나간다)
        if m.get("moderation") == "pending":
            return "pending"   # 검수 중: 차에 안 나간다(day_view)
        if m["date"] > today:
            return "ready"     # 통과했고, 고른 날이 되면 차가 받는다
        return "sent"          # 통과했고, 오늘 차가 받을 수 있다

    def sent(m):
        blocked = m.get("moderation") in ("blocked", "lost")
        return {"id": m["id"], "date": m["date"], "any": bool(m.get("any")), "moment": m["moment"],
                "place_name": (m.get("place") or {}).get("name"),
                "repeat": m.get("repeat", "once"), "audio": None if blocked else m["audio"],
                "check": check(m),
                "reply_count": sum(1 for r in reps if r["message_id"] == m["id"]),
                # 운전자가 차에서 직접 고른 반응(이모티콘)만. 날짜까지만(답장 줄과 같게). 들었는지 자체는 여전히 내보내지 않는다
                "reaction": react_day(m)}

    def order(m):
        return (m["date"], m["created"])

    upcoming = [m for m in mine if last_day(m) >= today]
    past = [m for m in mine if m not in upcoming]
    return {"today": today,
            "place_left": max(0, MAX_PLACES - sum(1 for m in mine if place_waiting(m, None, code))),
            "sent": {"upcoming": [sent(m) for m in sorted(upcoming, key=order)],
                     "past": [sent(m) for m in sorted(past, key=order, reverse=True)]},
            "received": [{"id": r["id"], "day": date.fromtimestamp(r["created"]).isoformat(), "audio": r["audio"],
                          "moment": r["moment"], "place_name": (by_id[r["message_id"]].get("place") or {}).get("name"),
                          "message_id": r["message_id"]}
                         for r in sorted(reps, key=lambda r: r["created"], reverse=True)]}


def save(db):
    tmp = DB + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DB)
    store.upload(DB, "db.json", "application/json")
    bump()


def probe_seconds(path):
    """ffprobe로 실제 길이를 잰다. 소리가 아니면 ValueError."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "format=duration:stream=codec_type",
                          "-of", "json", path], capture_output=True, text=True)
    info = json.loads(out.stdout or "{}")
    if not info.get("streams"):
        raise ValueError("녹음이 제대로 안 됐어요. 다시 녹음해 주세요")
    dur = float(info.get("format", {}).get("duration") or 0)
    if dur <= 0:  # 길이 정보가 없는 녹음(일부 브라우저 webm)은 끝까지 풀어서 잰다
        out = subprocess.run(["ffmpeg", "-i", path, "-f", "null", "-"], capture_output=True, text=True)
        times = re.findall(r"time=(\d+):(\d+):([\d.]+)", out.stderr)
        if times:
            h, m, sec = times[-1]
            dur = int(h) * 3600 + int(m) * 60 + float(sec)
    return dur


def check_audio(path, timeout, budget=None):
    """검수 한 번. 통과면 판정, 막아야 하면 (block, 이유), 검수 자체가 안 되면 None."""
    try:
        import moderate
        result = moderate.check(path, timeout=timeout, budget=budget)
    except Exception as e:
        print("검수 실패:", type(e).__name__, getattr(e, "code", ""), flush=True)
        return None
    verdict = result.get("verdict", "review")
    if verdict != "block" and result.get("speech") is False:
        return "silent"
    return verdict


def quick_check(path):
    """AI 검수를 못 할 때(무료 한도 끝·장애) 맥에서 바로 하는 가벼운 검사. 소리 크기만 본다.
    말소리가 거의 없으면 silent, 귀를 찌를 만큼 크게 꽉 찬 소리(비명·경적 흉내)면 loud, 아니면 ok."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True)
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", out.stderr)
    peak = re.search(r"max_volume: (-?[\d.]+) dB", out.stderr)
    if not mean or not peak:
        return "loud"  # 잴 수 없으면 바로 보내지 않는다
    mean, peak = float(mean.group(1)), float(peak.group(1))
    if mean < -50:
        return "silent"
    if peak > -0.3 and mean > -10:
        return "loud"
    return "ok"


def voiced_sec(path):
    """말소리로 보이는 길이(초). 30ms마다 말소리 대역 크기를 재서, 바닥 소음보다 9dB 넘게 큰 구간만 센다.
    계속 나는 소음(방·차 소리)은 바닥과 차이가 없어 0에 가깝고, 말은 음절마다 튀어 짧은 말도 0.3초를 넘는다.
    앞 0.5초(폰 마이크가 켜지며 크게 잡힘)와 끝 0.25초(멈춤 버튼 누르는 소리)는 뺀다.
    2026-11-05 실측: 폰에서 말 없이 녹음 0초 · 톡톡 소리 0.15초 · 1.4초짜리 말 0.36초 · 보통 말 0.7초 이상."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-af", "highpass=f=250,lowpass=f=3500",
                          "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    a = array.array("h")
    a.frombytes(raw[:len(raw) // 2 * 2])
    n = 480
    db = [10 * math.log10(sum(x * x for x in a[i:i + n]) / n / 32768 ** 2 + 1e-12) for i in range(0, len(a) - n, n)][17:-8]
    if not db:
        return 0.0
    th = max(sorted(db)[len(db) * 15 // 100] + 9, -45)
    return sum(1 for d in db if d > th) * 0.03


QUIET = "녹음에 목소리가 거의 들리지 않아요"
SOFT = "소리가 작아서 목소리가 거의 들리지 않아요"


def peak_db(path):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True)
    m = re.search(r"max_volume: (-?[\d.]+) dB", out.stderr)
    return float(m.group(1)) if m else 0.0


def moderate_audio(name, quiet_ok=False, peak=None):
    """남길 때 바로 하는 검사: 소리 크기만 본다(1초 안쪽). 말소리가 거의 없으면 막지 않고 한 번 묻는다(Quiet → 웹이 '이대로 남길까요?').
    남기는 사람이 그대로 남기기를 고르면(quiet_ok) 받는다.
    AI 검수는 응답을 보낸 뒤 뒤에서 한다(queue_check): 그동안 메시지는 보류(pending)라 차에 안 나가고, 남긴 사람 화면에는
    '확인이 끝나면 들려줘요'가 뜬다. (상태, 소리 크기 결과)를 돌려준다. 검수를 끈 시연·테스트는 ("off", None)."""
    if os.environ.get("MODERATE") == "0":
        return "off", None
    path = audio_file(name)
    quick = quick_check(path)
    if not quiet_ok:
        soft = quick == "silent" or (peak if peak is not None else peak_db(path)) < -24   # 원래 녹음의 가장 큰 소리도 작다: 폰을 멀리 뒀다(보통 말은 -12dB 위)
        if soft or voiced_sec(path) < 0.3:
            remove_audio(name)
            raise Quiet(SOFT if soft else QUIET)
    return "pending", quick


# 뒤에서 하는 AI 검수. 한 번에 하나씩(무료 한도가 분당·하루로 묶여 있어 한꺼번에 부르지 않는다). 메시지 하나에 검수 한 번은 예전과 같다.
checks = queue.Queue()
checking = {}   # 줄에 넣었거나 검수 중인 메시지 id → 줄에 든 개수: 다시 검수 루프(recheck_pending)가 같은 걸 또 부르지 않게


def queue_check(mid, reserved=False):
    """뒤 검수 줄에 넣는다. reserved: 저장하는 잠금 안에서 이미 checking에 넣었다(저장과 줄 사이에 다시 검수 루프가 끼지 않게)."""
    if not reserved:
        with lock:
            if mid in checking:
                return
            checking[mid] = 1
    checks.put(mid)


def check_worker():
    while True:
        mid = checks.get()
        try:
            check_message(mid)
        except Exception as e:
            print("뒤 검수 오류:", type(e).__name__, flush=True)
        finally:
            with lock:
                checking[mid] = checking.get(mid, 1) - 1
                if checking[mid] <= 0:
                    checking.pop(mid, None)


def check_message(mid):
    """남긴 뒤 처음 하는 AI 검수. 통과면 차에 나가고, 막히면 목소리를 지우고 남긴 사람 화면에 표시만 한다.
    AI 검수를 못 하면(무료 한도 끝·장애) 소리 크기가 괜찮은 것만 먼저 보낸다(quick, 나중에 다시 검수해서 걸리면 뺀다)."""
    with lock:
        m = next((x for x in load()["messages"] if x["id"] == mid), None)
    if not m or m.get("moderation") != "pending":
        return
    audio, t0 = m["audio"], time.time()
    path = audio_file(audio)
    verdict = check_audio(path, timeout=20, budget=40) if os.path.exists(path) else None  # 아무도 기다리지 않아 넉넉히
    reviews = 0
    if verdict is None:
        state = "quick" if m.get("quick") == "ok" else "pending"   # 큰 소리는 보류(다시 검수 루프가 본다)
    elif verdict == "review":
        state, reviews = "pending", 1   # 애매하면 보류했다가 한 번 더 본다
    elif verdict == "block":
        state = "blocked"
    else:
        state = "pass" if verdict == "silent" else verdict   # 말소리가 없는 건 막을 내용이 아니다(남길 때 이미 물었다)
    with lock:
        db = load()
        x = next((x for x in db["messages"] if x["id"] == mid), None)
        if not x or x["audio"] != audio or x.get("moderation") != "pending":
            return   # 그사이 지웠거나 다시 녹음했다(새 녹음은 따로 검수한다)
        x["moderation"] = state
        if reviews:
            x["reviews"] = reviews
        save(db)
    if state == "blocked":
        remove_audio(audio)
    print(f"[시간] 뒤 검수 {mid}: {time.time() - t0:.1f}초({verdict or '못 함'} → {state})", flush=True)


KEEP_DAYS = 30  # 들려줄 기간이 끝난 뒤 목소리를 보관하는 날 수


def last_day(m):
    """이 메시지를 차가 들을 수 있는 마지막 날. 반복 메시지도 남긴 날부터 ANY_DAYS까지다.
    운전자가 그만 들어도 이 날은 그대로다: 남긴 사람 화면과 지우는 날이 같아야 그만 들었는지 알 수 없다."""
    if m.get("repeat") == "each" or m.get("any"):
        return (date.fromisoformat(m["date"]) + timedelta(days=ANY_DAYS)).isoformat()
    return m["date"]


def drop_message(db, mid):
    """메시지와 거기에 온 답장을 목소리 파일까지 지운다."""
    gone = [m for m in db["messages"] if m["id"] == mid] + [r for r in db["replies"] if r["message_id"] == mid]
    for x in gone:
        remove_audio(x["audio"])
    db["messages"] = [m for m in db["messages"] if m["id"] != mid]
    db["replies"] = [r for r in db["replies"] if r["message_id"] != mid]


REPORT_DAYS = 90  # 신고된 메시지를 운영자가 볼 수 있게 두는 날 수(신고한 날부터)


def forget_person(db, inv):
    """운전자가 연결을 끊거나 신고한 사람의 이름·사진·알림 구독(위치 포함)을 지운다(남긴 메시지는 보관 기간대로 둔다).
    메시지·답장에 복사해 둔 이름도 지운다. 지울 사진 파일 이름을 돌려준다(파일은 잠금 밖에서 지운다). 다시 연결(reissue)에는 쓰지 않는다."""
    code = inv["code"]
    photo = inv.pop("photo", None)
    inv.pop("photo_ok", None); inv.pop("photo_reviews", None)
    inv["name"] = None
    unseat(inv)
    db.get("push", {}).pop(code, None)
    mine = {m["id"] for m in db["messages"] if m.get("invite") == code}
    for m in db["messages"]:
        if m["id"] in mine:
            m["sender"] = ""
    for r in db["replies"]:
        if r.get("message_id") in mine:
            r["to"] = ""
    return photo


def needs_forget(db, inv):
    """끊긴 링크에 아직 지울 개인정보가 남았는지(이 정리 전에 끊은 링크)."""
    code = inv["code"]
    return bool(inv.get("name") or inv.get("photo") or code in db.get("push", {})
                or any(m.get("invite") == code and m.get("sender") for m in db["messages"]))


def reported_at(db, m):
    """신고한 시각(초). 예전 기록(reported=True)은 신고 기록에서 찾는다."""
    r = m.get("reported")
    if not r:
        return None
    if r is not True and isinstance(r, (int, float)):
        return int(r)
    return next((x["created"] for x in db.get("reports", []) if x.get("message_id") == m["id"]), None)


def prune_old():
    """들려줄 기간이 끝나고 KEEP_DAYS가 지난 메시지를 지운다. 신고된 메시지는 신고하고 REPORT_DAYS가 지나면 지운다(신고 기록도).
    끊긴 링크에 남은 이름·사진·알림 구독도 지운다(이 정리를 넣기 전에 끊은 링크)."""
    cut = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
    report_cut = time.time() - REPORT_DAYS * 86400
    photos = []
    with lock:
        db = load()
        changed = False
        old = []
        for m in db["messages"]:
            if m.get("reported"):
                t = reported_at(db, m)
                if t is None:
                    m["reported"] = t = int(time.time())  # 신고 시각을 모르는 예전 기록: 오늘부터 센다
                    changed = True
                if t < report_cut:
                    old.append(m["id"])
            elif last_day(m) < cut:
                old.append(m["id"])
        for mid in old:
            drop_message(db, mid)
        reports = [r for r in db.get("reports", []) if r.get("created", 0) >= report_cut]
        if len(reports) != len(db.get("reports", [])):
            db["reports"] = reports
            changed = True
        for inv in db["invites"]:
            if inv.get("revoked") and not inv.get("moved") and needs_forget(db, inv):
                photos.append(forget_person(db, inv))
                changed = True
        if old or changed:
            save(db)
    for p in photos:
        if p:
            remove_photo(p)
    if old or photos:
        print("보관 기간 지나 지움:", len(old), "· 끊긴 링크 정리:", len(photos), flush=True)


RECHECK_SEC = 300  # 보류한 목소리를 다시 검수하는 간격. 무료 한도를 아끼려고 한 번에 하나씩
LOST_AFTER = 3     # 보관소에도 목소리 파일이 정말 없다고 이만큼 나오면 잃은 것으로 친다(lost: 차에 안 나가고 다시 검수하지 않는다)
recheck_at = {}    # 메시지 id → 마지막으로 다시 검수해 본 시각(메모리). 한 메시지가 계속 실패해도 다른 메시지 차례가 온다


def recheck_pending():
    """보류했거나 가벼운 검사만 한 목소리 하나를 다시 검수한다. 통과하면 차에 나가고, 막히면 지우고 남긴 사람 화면에 표시만 한다.
    차례: 가장 오래 안 본 것부터(같으면 보류 먼저). 들려줄 기간이 끝난 것은 건너뛴다."""
    today = date.today().isoformat()
    with lock:
        ms = [x for x in load()["messages"] if x["id"] not in checking   # 뒤 검수 줄에 있는 건 거기서 본다
              and x.get("moderation") in ("pending", "quick") and last_day(x) >= today]
    for k in [k for k in recheck_at if k not in {x["id"] for x in ms}]:
        recheck_at.pop(k, None)
    if not ms:
        return
    m = min(ms, key=lambda x: (recheck_at.get(x["id"], 0), x.get("moderation") != "pending"))
    recheck_at[m["id"]] = time.time()
    name = os.path.basename(m["audio"])
    path = os.path.join(AUDIO, name)
    if not os.path.exists(path):
        got = store.download("audio/" + name, path)
        if got is None:
            return  # 보관소 오류(잠깐일 수 있음): 막지 않고 다음 차례에 다시
        if not got:
            # 보관소에도 정말 없다: 몇 번 거듭되면 잃은 것으로 표시한다(먼저 보낸 quick도 차 목록에서 빠진다)
            with lock:
                db = load()
                x = next((x for x in db["messages"] if x["id"] == m["id"] and x["audio"] == m["audio"]), None)
                if x and x.get("moderation") in ("pending", "quick"):
                    x["audio_miss"] = x.get("audio_miss", 0) + 1
                    if x["audio_miss"] >= LOST_AFTER:
                        x["moderation"] = "lost"
                    save(db)
                    print("보류 검수: 목소리 파일 없음", m["id"], x["audio_miss"], "→ 잃음" if x["moderation"] == "lost" else "", flush=True)
            return
    verdict = check_audio(path, timeout=30)
    if verdict is None:
        if m.get("moderation") == "pending" and m.get("quick") == "ok" and not m.get("reviews"):
            # AI 검수를 한 번도 못 한 것(서버가 다시 켜져 뒤 검수가 끊김 등): 남길 때처럼 소리 크기가 괜찮으면 먼저 보낸다
            with lock:
                db = load()
                x = next((x for x in db["messages"] if x["id"] == m["id"] and x["audio"] == m["audio"]), None)
                if x and x.get("moderation") == "pending":
                    x["moderation"] = "quick"
                    save(db)
        return
    # 확실히 통과(pass)한 것만 차에 보낸다. 애매함(review)이 두 번 나오면 막은 것으로 친다(남긴 사람은 다시 녹음하면 된다)
    reviews = m.get("reviews", 0) + (verdict == "review")
    if verdict == "review" and reviews < 2:
        state = "pending"
    elif verdict in ("block", "review"):
        state = "blocked"
    else:
        state = "pass" if verdict == "silent" else verdict
    with lock:
        db = load()
        for x in db["messages"]:
            if x["id"] == m["id"] and x["audio"] == m["audio"]:   # 그사이 다시 녹음했으면 새 녹음은 따로 본다
                if state == "blocked" and x.get("moderation") == "quick":
                    x["was_quick"] = True  # 가볍게 먼저 보냈다가 나중에 걸림: 이미 들었을 수 있어 문구를 다르게
                x["moderation"] = state
                x["reviews"] = reviews
        save(db)
    if state == "blocked":
        remove_audio(m["audio"])
    print("보류 검수:", m["id"], verdict, "→", state, flush=True)


def recheck_photo():
    """검수 전 사진(올릴 때 검수를 못 했거나 애매했던 것, photo_ok가 없는 예전 사진) 하나를 다시 본다.
    통과하면 차에 나가고, 안 되면 사진을 지운다(남긴 사람 화면에서는 사진이 빠진다). 애매함이 두 번이면 지운다."""
    if os.environ.get("MODERATE") == "0":
        return
    with lock:
        inv = next((i for i in load()["invites"] if i.get("photo") and not i.get("revoked") and i.get("photo_ok") is not True), None)
        if not inv:
            return
        code, name, reviews = inv["code"], inv["photo"], inv.get("photo_reviews", 0)
    p = photo_file(name)
    if not os.path.exists(p):
        return  # 보관소에서 못 받았다(잠깐 오류일 수 있음): 다음 차례에 다시
    verdict = check_photo(open(p, "rb").read(), timeout=30)
    if verdict is None:
        return
    reviews += verdict == "review"
    gone = verdict == "block" or reviews >= 2
    with lock:
        db = load()
        x = find_invite(db, code)
        if not x or x.get("photo") != name:
            return   # 그사이 사진을 바꿨거나 지웠다
        if gone:
            x.pop("photo", None); x.pop("photo_ok", None); x.pop("photo_reviews", None)
            x["photo_blocked"] = int(time.time())
        elif verdict == "pass":
            x["photo_ok"] = True; x.pop("photo_reviews", None)
        else:
            x["photo_ok"], x["photo_reviews"] = "pending", reviews
        save(db)
    if gone:
        remove_photo(name)
    print("보류 사진 검수:", code, verdict, "→", "지움" if gone else x.get("photo_ok"), flush=True)


NUDGE_HOUR = 18  # 남길 때 알림은 전날 저녁에(이 시각이 지나고 처음 도는 때 하루 한 번)


def nudge_daily(force=False):
    """남기는 사람에게 '내일 비 온대요' 알림. 예보·전송은 잠금 밖에서 하고, 결과만 합친다."""
    today = date.today().isoformat()
    with lock:
        db = load()
        if not force and (time.localtime().tm_hour < NUDGE_HOUR or db.get("nudged") == today):
            return 0
        work = {"push": json.loads(json.dumps(db.get("push", {})))}
        revoked = revoked_codes(db)
    before = {c: (len(p.get("sent", [])), (p.get("sub") or {}).get("endpoint")) for c, p in work["push"].items()}
    push.rain_nudges(work, today, revoked)
    with lock:
        db = load()
        subs = db.setdefault("push", {})
        for code in list(subs):
            if code not in before:
                continue                             # 보내는 사이 새로 켠 구독: 이번엔 안 보냈다
            same = (subs[code].get("sub") or {}).get("endpoint") == before[code][1]
            if code not in work["push"]:
                if same:
                    subs.pop(code)                   # 이번에 보내다 구독이 끝난 폰(그사이 다시 켠 구독은 그대로)
            elif work["push"][code].get("sent") != subs[code].get("sent"):
                subs[code]["sent"] = work["push"][code].get("sent", [])
        db["nudged"] = today
        save(db)
    sent = sum(1 for c, p in work["push"].items() if len(p.get("sent", [])) > before.get(c, (0,))[0])
    print(f"[알림] 비 예보 알림 {sent}명", flush=True)
    return sent


def push_label(target):
    """알림 본문의 순간 이름(장소 메시지면 '학교 근처에 왔을 때')."""
    place = (target.get("place") or {}).get("name") if target["moment"] == "place" else None
    return f"{place} 근처에 왔을 때" if place else MOMENTS.get(target["moment"], {}).get("label", "")


def push_owner(target, code):
    """알림 제목에 넣을 차 주인 이름(초대장의 from). 모르면 None."""
    with lock:
        db = load()
        for c in (target.get("invite"), code):   # 함께 남기는 사람 메시지면 보호자 초대장의 이름
            inv = find_invite(db, c or "") or {}
            if owner_name(inv.get("from")):
                return owner_name(inv.get("from"))
    return None


def reply_push(target, sub, code=None):
    """운전자가 답장하면 남긴 사람 폰에 알림. 답장은 운전자가 직접 보낸 것이라 공유 원칙에 걸리지 않는다.
    code: 알림을 켠 링크(함께 쓰는 사람이 남긴 메시지면 보호자 링크). 없으면 메시지의 링크"""
    code = code or target["invite"]
    label = push_label(target)
    who = push_owner(target, code)
    r = push.send(sub["sub"], f"{who}님 답장이 왔어요" if who else "답장이 왔어요", f"{label} 남긴 메시지에 온 답장이에요".strip(),
                  f"/?invite={code}&box=1", "reply")
    if r is None:  # 폰에서 알림을 끈 경우
        with lock:
            db = load()
            db.get("push", {}).pop(code, None)
            save(db)
    print("[알림] 답장 알림", "보냄" if r else "못 보냄", flush=True)


REACT_HOLD_S = 3   # 이모티콘을 고르고 이만큼 기다렸다가 알림(그사이 바꾸면 마지막 것 하나만)


def react_push_later(mid, at, sub, code):
    """기다린 뒤에도 그 반응이 마지막 것이고, 아직 그 이모티콘으로 알린 적이 없을 때만 보낸다."""
    with lock:
        db = load()
        target = next((x for x in db["messages"] if x["id"] == mid), None)
        now = reaction_of(target) if target else None
        if not now or now.get("at") != at or target.get("reaction_notified") == now["emoji"]:
            return
        target["reaction_notified"] = now["emoji"]
        save(db)
    react_push(target, sub, code, now["emoji"])


def react_push(target, sub, code, emoji):
    """운전자가 차에서 이모티콘을 고르면 남긴 사람 폰에 알림(제목 '홍길동님 ❤️', 차 주인 이름을 모르면 이모티콘만).
    운전자가 직접 보낸 것만 알린다(들었는지 자체는 알리지 않는다)."""
    label = push_label(target)
    who = push_owner(target, code)
    r = push.send(sub["sub"], f"{who}님 {emoji}" if who else emoji, f"{label} 남긴 메시지".strip(), f"/?invite={code}&box=1", "react")
    if r is None:  # 폰에서 알림을 끈 경우
        with lock:
            db = load()
            db.get("push", {}).pop(code, None)
            save(db)
    print("[알림] 반응 알림", "보냄" if r else "못 보냄", flush=True)


def recheck_loop():
    pruned = None
    while True:
        try:
            if pruned != date.today():   # 하루 한 번(켤 때 포함) 오래된 목소리 정리
                prune_old(); pruned = date.today()
        except Exception as e:
            print("정리 오류:", type(e).__name__, flush=True)
        try:
            nudge_daily()
        except Exception as e:
            print("알림 오류:", type(e).__name__, flush=True)
        try:
            store.retry_deletes()   # 보관소에서 못 지운 파일을 다시 지운다
        except Exception as e:
            print("보관소 지우기 다시 오류:", type(e).__name__, flush=True)
        time.sleep(RECHECK_SEC)
        try:
            recheck_pending()
        except Exception as e:
            print("보류 검수 오류:", type(e).__name__, flush=True)
        try:
            recheck_photo()
        except Exception as e:
            print("보류 사진 검수 오류:", type(e).__name__, flush=True)


def store_audio(mime, b64, max_sec, info=None):
    """검증 → 표준 음량(-16 LUFS)·같은 형식(m4a)으로 바꿔 저장. 파일 이름을 돌려준다. info를 주면 잰 길이(sec)를 넣는다."""
    try:
        raw = base64.b64decode(b64 or "")
    except (ValueError, TypeError):
        raw = b""
    if not raw:
        raise ValueError("녹음을 올리지 못했어요. 다시 녹음해 주세요")
    if len(raw) > MAX_BYTES:
        raise ValueError("녹음 파일이 너무 커요. 더 짧게 녹음해 주세요")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in." + EXT.get(mime.split(';')[0].strip(), "bin"))
        with open(src, "wb") as f:
            f.write(raw)
        dur = probe_seconds(src)
        if dur > max_sec + 0.5:
            raise ValueError(f"{max_sec}초까지만 녹음해 주세요")
        if dur < 0.3:
            raise ValueError("조금 더 길게 말해 주세요")
        if info is not None:
            info["sec"] = round(dur, 1)
            info["peak"] = peak_db(src)   # 저장할 때 소리 크기를 맞추므로(loudnorm) 원래 크기는 여기서 잰다
        name = f"{uuid.uuid4().hex}.m4a"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100",
                            "-ac", "1", "-c:a", "aac", "-b:a", "64k", os.path.join(AUDIO, name)], capture_output=True, text=True)
        if r.returncode != 0:
            raise ValueError("녹음을 저장하지 못했어요. 다시 녹음해 주세요")
    store.upload(os.path.join(AUDIO, name), "audio/" + name, "audio/mp4")
    return name


def resolve_date(value, allow_past=False):
    if value == "today" or not value:
        return date.today().isoformat()
    if value == "tomorrow":
        return (date.today() + timedelta(days=1)).isoformat()
    try:
        d = date.fromisoformat(value)
    except ValueError:
        raise ValueError("날짜를 다시 골라 주세요")
    if not allow_past and d < date.today():
        raise ValueError("오늘부터 고를 수 있어요")
    if d > date.today() + timedelta(days=366):
        raise ValueError("오늘부터 1년 안에서 골라 주세요")
    return d.isoformat()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # 주소에 붙은 폰 열쇠(d)와 초대 코드는 가린다(서버에는 열쇠의 해시만 둔다)
        sys.stderr.write("[서버] " + re.sub(r"([?&](?:d|invite|code)=)[^&\s\"]+", r"\1…", fmt % args) + "\n")

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.key_cookie()
        self.end_headers()
        self.wfile.write(body)

    # 폰 열쇠 쿠키: 아이폰 사파리는 스크립트가 쓴 저장 공간(localStorage)을 7일 동안 안 오면 지운다.
    # 서버가 붙인 HttpOnly 쿠키는 그 대상이 아니라서, 열쇠를 초대 코드마다 쿠키(dd_코드)로도 둔다(한 폰이 여러 차 코드를 가질 수 있다).
    # 웹이 열쇠를 잃으면 /api/invite가 쿠키로 확인하고 열쇠를 다시 돌려준다(그 쿠키를 가진 폰에게만).
    KEY_AGE = 400 * 86400  # 브라우저가 받아 주는 가장 긴 쿠키 기간(크롬 400일)

    def cookie_key(self, code):
        """이 요청에 붙은 그 초대 코드의 열쇠 쿠키."""
        if not code or not CODE_RE.fullmatch(code):
            return ""
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "dd_" + code:
                return v.strip()[:64]
        return ""

    def key_cookie(self):
        """이번 응답에 붙일 열쇠 쿠키(받아들였거나 새로 준 열쇠, 탈퇴면 지우기)."""
        out, clear = getattr(self, "key_out", None), getattr(self, "key_clear", None)
        secure = "; Secure" if CLOUD or self.headers.get("X-Forwarded-Proto") == "https" else ""
        if out and (out[1] != self.cookie_key(out[0]) or self.path.startswith("/api/invite")):
            self.send_header("Set-Cookie", f"dd_{out[0]}={out[1]}; Max-Age={self.KEY_AGE}; Path=/; HttpOnly; SameSite=Lax{secure}")
        if clear and CODE_RE.fullmatch(clear):
            self.send_header("Set-Cookie", f"dd_{clear}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax{secure}")
        self.key_out = self.key_clear = None

    def keys(self, code, q=None):
        """이 폰의 열쇠 후보: X-Device 헤더(웹), 주소의 d(헤더를 못 붙이는 사진 img), 그 초대 코드의 쿠키 순."""
        out = []
        for k in (self.headers.get("X-Device"), (q or {}).get("d", [""])[0], self.cookie_key(code)):
            k = (k or "")[:64]
            if k and k not in out:
                out.append(k)
        return out

    def own(self, inv, q=None, extra=()):
        """이 폰의 링크인지 확인하고(아니면 Taken) 맞은 열쇠를 쿠키로도 붙인다. 맞은 열쇠를 돌려준다."""
        k = own_device(inv, [*[e for e in extra if e], *self.keys(inv["code"], q)])
        self.key_out = (inv["code"], k)
        return k

    def own_invite(self, db, code, dev=False, extra=()):
        inv = own_invite(db, code, None, dev=True)
        if not dev:
            self.own(inv, extra=extra)
        return inv

    def send_file(self, path, ctype, cache=None, gz=False):
        # 아이폰 사파리는 Range에 206으로 답하지 않으면 소리를 재생하지 못한다.
        if gz and not self.headers.get("Range") and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            body = gzipped(path)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(body)))
            if cache:
                self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body)
            return
        size = os.path.getsize(path)
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
            first, last = m.groups() if m else ("", "")
            if first:
                start, end = int(first), min(int(last), size - 1) if last else size - 1
            elif last:
                start = max(size - int(last), 0)  # 끝에서 n바이트
            if not (first or (last and int(last) > 0)) or start >= size or start > end:
                self.send_response(416)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        with open(path, "rb") as f:
            f.seek(start)
            body = f.read(end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def not_found(self, path):
        """모르는 주소. 브라우저가 연 페이지 주소(/api·/audio가 아닌 것)는 첫 화면으로 보낸다(웹이 '받은 초대 링크로 열어 주세요'를 띄운다).
        API는 예전처럼 404 JSON."""
        if path.startswith(("/api/", "/audio/")):
            return self.send_json({"error": "없는 주소"}, 404)
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_index(self, code):
        """첫 화면. 초대 링크(?invite=)로 열리면 카톡 미리보기 글에 운전자 이름을 넣는다(예: 홍길동님 차에 음성 메시지를 남기는 초대장)."""
        with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
            page = f.read()
        if CODE_RE.fullmatch(code or "") and not self.locked()[0]:
            with lock:
                inv = find_invite(load(), code)
            if not inv:
                self.miss(code)  # 미리보기 글(운전자 이름)로도 코드가 있는지 알 수 있어서 같이 센다(이어서 오는 /api/invite와 한 번으로)
            frm = inv.get("from") if inv and not dead(inv) else None
            if frm:
                page = page.replace('<meta property="og:description" content="차에 음성 메시지를 남기는 초대장">',
                                    f'<meta property="og:description" content="{html.escape(frm)}님 차에 음성 메시지를 남기는 초대장">', 1)
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def car(self):
        """차 앱이 처음 켤 때 만든 차 번호. 서버 하나를 여러 차가 같이 써도 메시지가 섞이지 않게 한다."""
        return (self.headers.get("X-Car-Id") or "")[:64]

    def local(self):
        """맥 안에서 바로 온 요청인지(시험 도구 dev·시연 알림용). 프록시를 거치지 않고(전달 헤더 없음) 127.0.0.1로 붙었고,
        주소가 127.0.0.1·localhost 또는 에뮬레이터가 맥을 부르는 10.0.2.2일 때만. 차 열쇠(CAR_KEY)가 있어도 밖에서 온 건 아니다."""
        h = self.headers
        if CLOUD or h.get("X-Forwarded-For") or h.get("CF-Connecting-IP") or h.get("Forwarded") or h.get("X-Real-IP"):
            return False
        if self.client_address[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return False
        host = (h.get("Host") or "").strip().lower()
        host = host[1:host.index("]")] if host.startswith("[") and "]" in host else host.split(":")[0]
        return host in ("127.0.0.1", "localhost", "10.0.2.2", "::1")

    def external(self):
        """프록시(tailscale serve)를 거쳐 온 요청인지. 차는 10.0.2.2에서 127.0.0.1로 바로 붙어서 여기에 걸리지 않는다."""
        if CAR_KEY and self.headers.get("X-Car-Key") == CAR_KEY:
            return False  # 차 앱(열쇠를 가진 것)은 밖에서 와도 차 주소를 쓴다
        return bool(self.headers.get("X-Forwarded-For")) or (self.headers.get("Host") or "").split(":")[0].endswith(".ts.net")

    def blocked(self, method, path):
        """밖에서 온 요청은 남기는 사람 웹이 쓰는 주소만 받는다."""
        if not self.external():
            return False
        if method == "POST":
            # 남기기·자기 메시지 바꾸기/지우기·내 정보·탈퇴(초대 코드 확인은 처리하는 쪽에서 한다)
            return path not in ("/api/messages", "/api/push", "/api/profile", "/api/leave", "/api/together") and \
                not re.fullmatch(r"/api/messages/\w+/(delete|edit)|/api/replies/\w+/delete", path)
        return path not in ("/", "/index.html", "/privacy", "/terms", "/location", "/api/invite", "/api/code", "/api/box", "/api/push", "/api/photo",
                            "/api/presets", "/api/me", "/api/examples", "/api/map", "/api/place") + WEB_FILES \
            and not path.startswith("/audio/")

    def client(self):
        """요청한 곳(코드 넣어 보기 막기용). 렌더 앞의 Cloudflare가 늘 덮어쓰는 CF-Connecting-IP만 믿는다.
        없으면 X-Forwarded-For의 맨 끝 칸(바로 앞 프록시가 붙인 것). 앞 칸들과 True-Client-IP는 보낸 쪽이 지어낼 수 있어 보지 않는다."""
        h = self.headers
        ip = (h.get("CF-Connecting-IP") or "").strip()
        if not ip:
            hops = [x.strip() for x in (h.get("X-Forwarded-For") or "").split(",") if x.strip()]
            ip = hops[-1] if hops else ""
        return (ip or self.client_address[0])[:64]

    def miss(self, code=None):
        guess_miss(self.client(), self.req_code if code is None else code)

    def locked(self):
        """이 곳이 지금 코드를 확인할 수 없는지: (남은 초, 모두 막힘 여부). 모두 막힘은 이미 틀린 적이 있는 곳에만 걸린다."""
        who = self.client()
        left = guess_wait(who)
        if left:
            return left, False
        if guess_seen(who):
            left = guess_wait(EVERYONE)
            if left:
                return left, True
        return 0, False

    def guard(self, code, keys=()):
        """막힌 곳이면 코드를 확인하지 않고 429. 이 폰의 열쇠가 맞는 요청(자기 링크를 쓰는 중)은 막지 않는다."""
        self.req_code = code or ""
        left, everyone = self.locked()
        if not left:
            return
        if keys:
            with lock:
                inv = find_invite(load(), code)
            h = inv.get("device_hash") if inv else None
            if h and any(hmac.compare_digest(h, device_hash(k)) for k in keys if k):
                return
        raise TooMany(left, everyone)

    # 본문 크기 상한: 가장 큰 것은 녹음 파일(MAX_BYTES)을 base64로 바꾼 것(4/3배)에 JSON 몇 줄. 사진은 300KB라 그 안에 든다
    MAX_BODY = MAX_BYTES * 4 // 3 + 64 * 1024

    def read_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("남기지 못했어요. 다시 눌러 주세요")
        if n < 0:
            raise ValueError("남기지 못했어요. 다시 눌러 주세요")
        if n > self.MAX_BODY:
            self.close_connection = True   # 다 읽지 않은 본문이 남아 있어 이 연결은 다시 쓰지 않는다
            raise TooBig("녹음 파일이 너무 커요. 더 짧게 녹음해 주세요")
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise ValueError("남기지 못했어요. 다시 눌러 주세요")
        if not isinstance(body, dict):
            raise ValueError("남기지 못했어요. 다시 눌러 주세요")
        return body

    def fresh(self):
        """요청마다 새로(같은 연결로 여러 요청이 와도 앞 요청 값이 남지 않게)."""
        self.key_out = self.key_clear = None
        self.req_code = ""

    def do_GET(self):
        self.fresh()
        try:
            return self._get()
        except Gone as e:
            return self.send_json({"ok": False, "error": str(e), "gone": True}, 410)
        except Taken as e:
            return self.send_json({"ok": False, "error": str(e), "taken": e.taken}, 403)
        except TooMany as e:
            return self.send_json({"ok": False, "error": str(e), "wait": e.wait, "everyone": e.everyone}, 429)
        except ValueError as e:
            if isinstance(e, NoInvite):
                self.miss()
            return self.send_json({"ok": False, "error": user_error(e)}, 400)
        except Exception as e:
            print("서버 오류:", type(e).__name__, flush=True)
            return self.send_json({"error": OOPS}, 500)

    def _get(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if self.blocked("GET", u.path):
            return self.not_found(u.path)
        if u.path in ("/api/code", "/api/invite", "/api/push", "/api/box", "/api/photo", "/api/me"):
            gc = q.get("code", q.get("invite", [""]))[0]
            if u.path == "/api/code":
                gc = norm_code(gc)
            self.guard(gc, self.keys(gc, q))  # 코드를 여러 번 틀린 곳은 잠시 막는다(모두 막힘은 틀린 적이 있는 곳만)
        if u.path in ("/", "/index.html"):
            return self.send_index(q.get("invite", [""])[0])
        if u.path == "/api/code":
            # 남기는 사람 웹: 링크 없이 연 첫 화면에서 차에 뜬 코드를 손으로 넣는다. 맞으면 그 초대 코드를 돌려주고 웹이 ?invite=로 연다
            code = norm_code(q.get("code", [""])[0])
            with lock:
                inv = find_invite(load(), code) if CODE_RE.fullmatch(code) else None
            if not inv:
                self.miss(code)
                return self.send_json({"ok": False}, 404)
            if dead(inv):   # 끊긴 코드와 하루 동안 아무도 안 연 코드는 같게
                return self.send_json({"ok": False, "gone": True}, 410)
            return self.send_json({"ok": True, "code": inv["code"]})
        if u.path in ("/privacy", "/terms", "/location"):
            return self.send_file(os.path.join(WEB, u.path[1:] + ".html"), "text/html; charset=utf-8", cache="no-cache")
        if u.path == "/manifest.json":
            # 홈 화면에 추가한 앱이 초대 링크로 열리게: ?invite=코드면 시작 주소에 코드를 넣어 준다(모양만 확인)
            with open(os.path.join(WEB, "manifest.json"), encoding="utf-8") as f:
                man = json.load(f)
            code = q.get("invite", [""])[0]
            if CODE_RE.fullmatch(code):
                man["start_url"] = f"/?invite={code}"
                # 홈 화면 앱은 브라우저와 저장 공간이 따로라(아이폰) 열쇠를 시작 주소에 같이 넣는다. 이 링크의 열쇠가 맞을 때만
                d = q.get("d", [""])[0][:64]
                if d:
                    with lock:
                        inv = find_invite(load(), code)
                    if inv and not dead(inv) and inv.get("device_hash") and hmac.compare_digest(inv["device_hash"], device_hash(d)):
                        man["start_url"] += f"&d={d}"
            body = json.dumps(man, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path in WEB_FILES:
            name = u.path[1:]
            ctype = {"json": "application/manifest+json", "js": "text/javascript; charset=utf-8", "png": "image/png", "jpg": "image/jpeg", "webp": "image/webp",
                     "m4a": "audio/mp4", "glb": "model/gltf-binary"}[name.rsplit(".", 1)[-1]]
            if u.path in AVATAR_FILES:
                return self.send_file(os.path.join(WEB, name), "application/json" if name.endswith(".json") else ctype,
                                      cache="public, max-age=2592000", gz=not name.endswith((".png", ".webp")))
            return self.send_file(os.path.join(WEB, name), ctype, cache="no-cache")
        if u.path == "/api/push":
            # 남기는 사람 웹: 알림을 켤 수 있는지(서버 키)와 이 링크가 켜 뒀는지
            code = q.get("invite", [""])[0]
            with lock:
                db = load()
            inv = find_invite(db, code)
            if not inv:
                self.miss()
                return self.send_json({"ok": False}, 404)
            if dead(inv):
                raise Gone("이 초대 링크는 열 수 없어요")
            self.own(inv, q)
            return self.send_json({"ok": True, "ready": push.ON, "key": push.PUBLIC,
                                   "on": bool(db.get("push", {}).get(code, {}).get("on"))})
        if u.path.startswith("/audio/"):
            name = os.path.basename(u.path)
            p = audio_file(name)
            if not os.path.exists(p):
                return self.send_json({"error": "not found"}, 404)   # 화면에 뜨지 않게 한글을 뺐다(웹은 한글 오류만 보여 준다)
            ctype = {"webm": "audio/webm", "ogg": "audio/ogg", "m4a": "audio/mp4", "mp3": "audio/mpeg",
                     "aac": "audio/aac", "wav": "audio/wav"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
            return self.send_file(p, ctype)
        if u.path == "/api/moments":
            return self.send_json(MOMENTS)
        if u.path == "/api/examples":
            # 폰 웹 홈 '예시 듣기': 순간·보내는 사람·듣는 사람·문장·파일(누구나 받아도 되는 고정 값)
            return self.send_json({"examples": EX_LIST})
        if u.path == "/api/map":
            # 폰 웹 지도: 카카오 지도 JavaScript 키(카카오에 등록한 사이트 주소에서만 쓰이는 공개 키). 없으면 웹이 지금 지도를 쓴다
            return self.send_json({"kakao": KAKAO_JS_KEY})
        if u.path == "/api/place":
            # 폰 웹 장소 검색: 카카오 키워드 검색을 서버가 대신 묻는다(REST 키는 서버에만). 안 되면 웹이 다른 검색으로 넘어간다
            return self.send_json({"hits": kakao_place(q.get("q", [""])[0], q.get("lat", [""])[0], q.get("lon", [""])[0], self.client())})
        if u.path == "/api/presets":
            # 폰 웹 캐릭터 만들기·차 광장: 프리셋 8, 부품 이름, 색 값, 얼굴 그리기 규칙(누구나 받아도 되는 고정 값)
            return self.send_json(avatar.catalog())
        if u.path == "/api/plaza":
            # 차 광장(밖에서는 차 열쇠가 있어야 열린다: blocked). 누가 보냈는지 드러나는 값은 없다(plaza_view)
            with lock:
                db = load()
            return self.send_json(plaza_view(db, self.car() or None))
        if u.path == "/api/me":
            # 폰 웹: 내 캐릭터·대표색과 같은 차에서 이미 쓰는 색(번호만, 이름 없이)
            code = q.get("invite", [""])[0]
            with lock:
                db = load()
            inv = find_invite(db, code)
            if not inv:
                self.miss()
                return self.send_json({"ok": False}, 404)
            if dead(inv):
                raise Gone("이 초대 링크는 열 수 없어요")
            self.own(inv, q)
            return self.send_json({"ok": True, "name": inv.get("name"), "avatar": inv.get("avatar"), "color": inv.get("color"),
                                   "used_colors": used_colors(db, inv.get("car"), inv)})
        if u.path == "/api/changes":
            # 차가 붙어 기다린다: 번호가 since와 달라지면(새로 남김·지움·검수 통과 등) 바로, 아니면 25초 뒤 답한다
            try:
                since = int(q.get("since", ["-1"])[0])
            except ValueError:
                since = -1
            with changed:
                changed.wait_for(lambda: version != since, timeout=25)
                v = version
            return self.send_json({"version": v})
        if u.path == "/api/invites":
            # 운전자 차 화면: 내가 보낸 초대 링크와 연결된 사람(끊은 링크는 빼고)
            with lock:
                db = load()
            return self.send_json({"invites": [{"code": i["code"], "name": i.get("name"), "created": i["created"],
                                                "claimed": bool(i.get("device_hash")), "photo": photo_v(i),
                                                # 다시 연결로 만든 새 링크를 새 폰이 아직 열지 않음(차 사람 화면 '새 링크 보냄')
                                                "reissued": bool(i.get("reissued")) and not i.get("device_hash"),
                                                # 아무 폰도 열지 않은 채 하루가 지나 못 쓰는 코드(차는 '만료'로 보이거나 다시 연결하면 된다). 옛 차 앱은 이 값을 안 읽는다
                                                "expired": expired(i),
                                                # 광장 자리·대표색(가입 전이면 null)
                                                "slot": i.get("slot") if seated(i) else None, "color": i.get("color") if seated(i) else None}
                                               for i in db["invites"] if not i.get("revoked") and of_car(i, self.car())]})
        if u.path == "/api/invite":
            # 숨기는 사람 웹: 이 링크로 숨길 수 있는지
            # 처음 연 폰이 링크를 갖는다: 그다음부터는 그 열쇠를 가진 폰만 들어온다(받은 링크를 남에게 넘겨도 못 쓴다)
            code = q.get("code", [""])[0]
            # peek=1(새 웹): 열기만 해서는 잠그지 않는다. 프로필 [완료](/api/profile claim)에서 잠근다.
            # 카카오톡 안 브라우저에서 먼저 열었다가 Safari·Chrome으로 옮겨도 잠기지 않게. peek 없는 옛 웹은 예전처럼 열 때 잠근다
            # peek=2(앱 안 브라우저): 이름이 있는 링크(다시 연결로 만든 새 링크)도 잠그지 않는다. 웹이 바깥 브라우저로 넘기고 거기서 잠근다
            # 열 때 잠그는 링크(다시 연결 링크 · 옛 웹): 새 웹은 직접 만든 열쇠를 X-Device로 보내고 그것으로 잠근다(응답이 끊겨도 같은 열쇠로 이어진다)
            pv = q.get("peek", [""])[0]
            peek, hold = pv in ("1", "2"), pv == "2"
            token, unclaimed, back = None, False, None
            with lock:
                db = load()
                inv = find_invite(db, code)
                if not inv:
                    self.miss(code)
                    return self.send_json({"ok": False, "reason": "열 수 없는 초대 링크예요"}, 404)
                if dead(inv):
                    return self.send_json({"ok": False, "reason": "이 초대 링크는 열 수 없어요"}, 410)
                if inv.get("guardian") and not inv.get("device_hash"):
                    raise Taken(TAKEN)   # 함께 쓰는 사람 코드는 다른 폰이 열어 잠글 수 없다
                if not inv.get("device_hash"):
                    if peek and (hold or not inv.get("name")):
                        unclaimed = True
                    else:
                        token = claim_invite(db, inv, self.headers.get("X-Device") or "")  # 이 변경 전에 만든 링크(이름이 있어도)도 처음 여는 폰이 갖는다
                        self.key_out = (code, token)
                else:
                    k = self.own(inv, q)
                    if k != (self.headers.get("X-Device") or "")[:64]:
                        back = k   # 웹이 열쇠를 잃었는데 쿠키로 맞았다: 열쇠를 돌려줘 웹 저장 공간을 되살린다
            if unclaimed:
                # 아직 아무 폰도 안 가진 링크: 이름·사진은 주지 않는다(링크를 연 아무나 보지 못하게). 초대장 제목에 쓰는 차 주인 이름만
                # used_colors: 캐릭터 만들기에서 못 고르는 색(번호만). full: 이 차에 5명이 다 차서 들어올 수 없다
                return self.send_json({"ok": True, "open": True, "from": inv.get("from"),
                                       "used_colors": used_colors(db, inv.get("car"), inv), "full": free_slot(db, inv.get("car")) is None})
            res = {"ok": True, "name": inv.get("name"), "photo": inv.get("photo"), "created": inv.get("created"),
                   "claimed": inv.get("claimed"), "from": inv.get("from"),
                   "avatar": inv.get("avatar"), "color": inv.get("color"), "used_colors": used_colors(db, inv.get("car"), inv),
                   # 이 폰에서 같이 남기는 함께 쓰는 사람(보호자일 때만). 함께 쓰는 사람 코드로 열면 guardian이 참
                   "together": [kid_view(k) for k in kids_of(db, inv)], "kid": bool(inv.get("guardian"))}
            if token or back:
                res["device"] = token or back
            return self.send_json(res)
        if u.path == "/api/photo":
            # 남기는 사람 웹 내 정보: 자기 링크의 사진만 본다
            code = q.get("invite", [""])[0]
            with lock:
                db = load()
            inv = find_invite(db, code)
            if not inv:
                self.miss()
            if not inv or dead(inv) or not inv.get("photo"):
                return self.send_json({"error": "not found"}, 404)   # 화면에 뜨지 않게 한글을 뺐다(웹은 한글 오류만 보여 준다)
            self.own(inv, q)
            p = photo_file(inv["photo"])
            if not os.path.exists(p):
                return self.send_json({"error": "not found"}, 404)   # 화면에 뜨지 않게 한글을 뺐다(웹은 한글 오류만 보여 준다)
            return self.send_file(p, "image/jpeg", cache="private, max-age=86400")
        if u.path == "/api/car/photo":
            # 차 앱: 이 차가 만든 초대 링크의 사진만(밖에서는 차 열쇠가 있어야 이 주소가 열린다: blocked). v가 지금 사진과 다르면 404(다음에 새 판으로 다시 받는다)
            code, v = q.get("invite", [""])[0], q.get("v", [""])[0]
            with lock:
                db = load()
            inv = find_invite(db, code)
            if not inv or inv.get("revoked") or not of_car(inv, self.car()) or not photo_v(inv) or (v and v != photo_v(inv)):
                return self.send_json({"error": "not found"}, 404)   # 화면에 뜨지 않게 한글을 뺐다(웹은 한글 오류만 보여 준다)
            p = photo_file(inv["photo"])
            if not os.path.exists(p):
                return self.send_json({"error": "not found"}, 404)   # 화면에 뜨지 않게 한글을 뺐다(웹은 한글 오류만 보여 준다)
            return self.send_file(p, "image/jpeg", cache="private, max-age=86400")
        if u.path == "/api/box":
            # 남기는 사람 웹: 남긴 메시지와 답장. 초대 코드가 곧 로그인이라 끊긴 링크로는 못 본다.
            code = q.get("invite", [""])[0]
            with lock:
                db = load()
            inv = find_invite(db, code)
            if not inv:
                self.miss()
                return self.send_json({"ok": False, "reason": "열 수 없는 초대 링크예요"}, 404)
            if dead(inv):
                return self.send_json({"ok": False, "reason": "이 초대 링크는 열 수 없어요"}, 410)
            self.own(inv, q)
            return self.send_json(box_view(db, code))
        if u.path == "/api/heard":
            # 정차 중 '지난 메시지': 보관 기간 안에서 전에 들은 것(오늘 들은 건 오늘 목록에 있다). 끊은 링크·막힌 건 뺀다.
            day = resolve_date(q.get("date", ["today"])[0], allow_past=True)
            with lock:
                db = load()
            cut, car = revoked_codes(db), self.car()
            past = [(heard_day(m), m) for m in db["messages"]
                    if of_car(m, car) and m.get("invite") not in cut and m.get("moderation") not in ("pending", "blocked", "lost")]
            past = sorted(((d, m) for d, m in past if d and d < day), key=lambda x: x[0], reverse=True)
            keep = ("id", "sender", "moment", "audio", "repeat", "date", "picked", "place", "sec", "invite")
            replied = {r.get("message_id") for r in db.get("replies", [])}
            invs = {i["code"]: i for i in db["invites"]}
            return self.send_json({"messages": [{**{k: m[k] for k in keep if k in m}, "heard_day": d, "replied": m["id"] in replied,
                                                 "reaction": reaction_of(m), "photo": photo_v(invs.get(m.get("invite")))} for d, m in past]})
        if u.path == "/api/messages":
            # 차가 오늘 메시지를 받아 간다. 내용은 차가 열 때까지 운전자 화면에 안 나온다.
            day = resolve_date(q.get("date", ["today"])[0], allow_past=True)
            with lock:
                db = load()
            cut = revoked_codes(db)  # 운전자가 끊은 링크로 숨긴 건 더는 안 나온다
            car = self.car()
            replied = {r.get("message_id") for r in db.get("replies", [])}
            invs = {i["code"]: i for i in db["invites"]}  # photo: 남긴 사람 사진의 판 번호(차가 /api/car/photo로 받아 둔다)
            return self.send_json({"date": day, "messages": [{**v, "replied": v["id"] in replied, "reaction": reaction_of(v), "photo": photo_v(invs.get(v.get("invite")))} for v in (day_view(m, day) for m in db["messages"]
                                                                          if m.get("invite") not in cut and of_car(m, car)) if v]})
        return self.not_found(u.path)

    def do_POST(self):
        self.fresh()
        u = urlparse(self.path)
        if self.blocked("POST", u.path):
            self.close_connection = True   # 본문을 읽지 않고 답한다
            return self.send_json({"error": "없는 주소"}, 404)
        try:
            body = self.read_json()
            # 시험 도구(dev)의 초대 확인 건너뛰기는 맥 안에서 바로 온 요청만. 차 열쇠(CAR_KEY)로는 안 된다
            dev = bool(body.get("dev")) and self.local()
            if u.path in ("/api/messages", "/api/push", "/api/profile", "/api/leave", "/api/together") or \
                    re.fullmatch(r"/api/messages/\w+/(delete|edit)|/api/replies/\w+/delete", u.path):
                gc = str(body.get("invite") or "")
                self.guard(gc, self.keys(gc) + ([body["device"]] if u.path == "/api/profile" and isinstance(body.get("device"), str) else []))  # 코드를 여러 번 틀린 곳은 잠시 막는다(아무 링크나 잡지 못하게)
            if u.path == "/api/invites":
                # 운전자가 차에서 [초대 링크 보내기]: 사람마다 따로 쓰는 링크
                # from: 운전자 이름(예: 홍길동). 웹 초대장에 '홍길동님 차'로 보인다(예전 차 앱은 '아빠' 같은 부르는 말을 보냈다)
                frm = owner_name(body.get("from"))
                with lock:
                    db = load()
                    if free_slot(db, self.car() or None) is None:
                        raise ValueError(FULL_CAR)   # 5명이 다 찼다: 새 초대 코드를 만들지 않는다
                    code = new_code(db)
                    db["invites"].append({"code": code, "created": int(time.time()), "car": self.car() or None, "from": frm})
                    save(db)
                return self.send_json({"ok": True, "code": code, "link": f"/?invite={code}"})
            m = re.fullmatch(r"/api/invites/(\w+)/revoke", u.path)
            if m:
                with lock:
                    db = load()
                    inv = find_invite(db, m.group(1))
                    if not inv or not of_car(inv, self.car()):
                        raise ValueError("열 수 없는 초대 링크예요")
                    if not inv.get("revoked"):
                        inv["revoked"] = int(time.time())
                    # 끊는 순간 이름·사진·알림 구독(위치 포함)을 지운다. 남긴 메시지는 보관 기간대로(차에는 더 안 나간다)
                    photo = forget_person(db, inv) if not inv.get("moved") else None
                    # 이 사람이 추가한 함께 쓰는 사람도 같이 끊는다(보호자 폰 열쇠로만 쓰던 사람이라 혼자 남지 않게)
                    kid_photos = drop_kids(db, inv, False) if not inv.get("moved") else []
                    save(db)
                for p in [photo, *kid_photos]:
                    if p:
                        remove_photo(p)
                return self.send_json({"ok": True})
            m = re.fullmatch(r"/api/invites/(\w+)/reissue", u.path)
            if m:
                # 운전자가 차 사람 화면에서 [다시 연결]: 폰을 바꾼 사람에게 새 링크를 준다. 같은 사람으로 이어진다
                # (이름·사진·부르는 말·남긴 메시지와 답장은 새 링크로 옮기고, 예전 링크와 예전 폰은 더 이상 못 쓴다)
                with lock:
                    db = load()
                    old = find_invite(db, m.group(1))
                    if not old or not of_car(old, self.car()) or old.get("revoked"):
                        raise ValueError("다시 연결할 수 없는 링크예요")
                    if not old.get("name"):
                        raise ValueError("연결되지 않은 링크예요")  # 이름이 정해진(프로필을 마친) 사람만 다시 연결한다
                    now = int(time.time())
                    code = new_code(db)
                    # 새 링크는 아무 폰도 잠그지 않은 채 이름이 있다: 새 폰이 열면 그 폰에 잠기고 바로 들어간다(/api/invite)
                    # 초대장 이름은 차가 지금 쓰는 것으로(안 보내면 예전 링크 것 그대로)
                    new = {"code": code, "created": now, "car": old.get("car"), "from": owner_name(body.get("from")) or old.get("from"), "name": old["name"], "reissued": now}
                    if old.get("photo"):
                        new["photo"] = old["photo"]
                        if "photo_ok" in old:
                            new["photo_ok"] = old["photo_ok"]
                    for k in ("slot", "color", "avatar"):   # 같은 사람: 광장 자리·대표색·캐릭터도 그대로
                        if k in old:
                            new[k] = old[k]
                    unseat(old)
                    # 함께 쓰는 사람은 새 링크(보호자)를 따라간다. 새 폰이 새 링크를 열면 그 폰 열쇠로 이어진다(claim_invite)
                    for k in kids_of(db, old):
                        k["guardian"] = code
                        k.pop("device_hash", None)
                    db["invites"].append(new)
                    moved = 0
                    for x in db["messages"]:
                        if x.get("invite") == old["code"]:
                            x["invite"] = code   # 답장은 메시지 id로 붙어 있어서 같이 따라간다
                            moved += 1
                    # 알림 구독은 예전 폰의 브라우저 것이라 옮기지 않고 지운다(새 폰에서 다시 켠다). 옮기면 예전 폰에 답장 알림이 간다
                    db.get("push", {}).pop(old["code"], None)
                    old.pop("photo", None); old.pop("photo_ok", None)   # 사진 파일은 새 링크가 그대로 쓴다(지우지 않는다)
                    old["name"] = None
                    old.pop("device_hash", None)
                    old["revoked"] = old["moved"] = now
                    save(db)
                print("[다시 연결] 옮긴 메시지", moved, flush=True)
                return self.send_json({"ok": True, "code": code, "link": f"/?invite={code}", "moved": moved})
            if u.path == "/api/messages":
                t_in = time.time()  # 목소리가 다 올라온 때(본문을 다 읽은 뒤)
                sender = (body.get("sender") or "").strip()[:20]
                # 초대 링크를 연 사람만 숨길 수 있다(테스트 도구는 dev로 건너뜀)
                code = body.get("invite") or ""
                car = self.car() or None  # 시험 도구(dev)는 차 번호를 직접 보낸다. 없으면 모든 차에 보인다
                rid = str(body.get("rid") or "")[:40]  # 웹이 보낼 때마다 붙이는 번호: 끊긴 뒤 다시 눌러도 하나만
                with lock:
                    db = load()
                    if not dev:
                        inv = find_invite(db, code)
                        if inv and not dead(inv):
                            self.own(inv)  # 다시 보내기 확인보다 먼저: 남의 폰은 남긴 결과도 못 본다
                    dup = next((x for x in db["messages"] if rid and x.get("rid") == rid and x.get("invite") == (code or None)), None)
                    if dup:
                        return self.send_json({"ok": True, "id": dup["id"], "date": dup["date"], "check": dup.get("moderation")})
                    if not dev:
                        inv = find_invite(db, code)
                        if not inv:
                            raise NoInvite("초대 링크로 들어와 주세요")
                        if dead(inv):
                            raise Gone("이 초대 링크는 열 수 없어요")
                        car = inv.get("car")  # 남기는 사람이 고를 수 없다: 초대 링크를 만든 차로만 간다
                        if inv.get("name"):
                            sender = inv["name"]          # 한 링크는 한 사람: 처음 쓴 이름으로 고정(저장은 남기기가 성공한 뒤)
                moment = body.get("moment")
                if not sender:
                    raise ValueError("이름을 적어 주세요")
                if moment not in MOMENTS:
                    raise ValueError("언제 들려줄지 골라 주세요")
                repeat = body.get("repeat", "once")
                if repeat not in REPEATS:
                    raise ValueError("몇 번 들려줄지 골라 주세요")
                any_day = body.get("date") == "any"
                day = resolve_date("today" if any_day else body.get("date"))
                place = None
                if moment == "place":
                    p = body.get("place") or {}
                    try:
                        place = {"lat": float(p["lat"]), "lon": float(p["lon"]), "name": str(p["name"]).strip()[:20]}
                    except (KeyError, TypeError, ValueError):
                        raise ValueError("지도에서 장소를 골라 주세요")
                    if not place["name"] or not (-90 <= place["lat"] <= 90 and -180 <= place["lon"] <= 180):
                        raise ValueError("장소 이름을 적어 주세요")
                    with lock:
                        waiting = sum(1 for m in load()["messages"] if place_waiting(m, sender, code))
                    if waiting >= MAX_PLACES:
                        raise ValueError(PLACE_FULL)   # 녹음을 다루기 전에 먼저 알려 준다(정할 때는 저장하는 잠금 안에서 다시 센다)
                # 길이는 보낸 값이 아니라 서버가 직접 잰다. 검수(moderate.py)는 키 사용량 때문에 시연에서 따로 켠다.
                info = {}
                name = store_audio(body.get("mime", "audio/webm"), body.get("audio"), MOMENTS[moment]["max_sec"], info)
                t_mod = time.time()
                verdict, quick = (None, None) if dev else moderate_audio(name, bool(body.get("quiet_ok")), info.get("peak"))  # 소리 크기만 보고 바로 답한다. AI 검수는 뒤에서
                t_done = time.time()
                msg = {"id": uuid.uuid4().hex[:10], "sender": sender, "date": day,
                       "moment": moment, "repeat": repeat, "invite": code or None,
                       "any": any_day, "picked": str(body.get("date")) not in ("today", "tomorrow", "any", "None"),  # 달력에서 고른 날짜(들은 뒤 문구에 쓴다)
                       "audio": f"/audio/{name}", "created": int(time.time()), "car": car, "rid": rid or None, "sec": info.get("sec")}
                if verdict:
                    msg["moderation"] = verdict   # pending: 뒤 검수가 끝날 때까지 차에 안 나간다
                if quick:
                    msg["quick"] = quick          # AI 검수를 못 할 때 먼저 보낼지 정하는 소리 크기 결과
                if place:
                    msg["place"] = place
                with lock:
                    db = load()
                    dup = next((x for x in db["messages"] if rid and x.get("rid") == rid and x.get("invite") == (code or None)), None)
                    # 세는 것과 넣는 것을 같은 잠금 안에서: 동시에 보낸 장소 메시지가 MAX_PLACES를 넘지 않게
                    full = not dup and bool(place) and sum(1 for m in db["messages"] if place_waiting(m, sender, code)) >= MAX_PLACES
                    if not dup and not full:
                        db["messages"].append(msg)
                        inv = find_invite(db, code) if not dev else None
                        if inv and not inv.get("name"):
                            inv["name"] = sender  # 첫 메시지가 실제로 남았을 때 이름을 정한다(거절된 시도의 오타가 굳지 않게)
                        if verdict == "pending":
                            checking[msg["id"]] = checking.get(msg["id"], 0) + 1
                        save(db)
                if dup or full:
                    remove_audio(name)   # 그사이 같은 것이 먼저 남았거나(다시 보내기) 장소 자리가 찼다: 새 파일은 버린다
                    if full:
                        raise ValueError(PLACE_FULL)
                    return self.send_json({"ok": True, "id": dup["id"], "date": dup["date"], "check": dup.get("moderation")})
                if verdict == "pending":
                    queue_check(msg["id"], reserved=True)
                # 시간만 남긴다(누가·무엇은 빼고). 대표 장면 시간을 재는 데 쓴다.
                print(f"[시간] 남김 {msg['id']}: 받음 {time.strftime('%H:%M:%S', time.localtime(t_in))}"
                      f" · 저장 준비 {t_mod - t_in:.1f}초 · 소리 크기 {t_done - t_mod:.1f}초({quick or verdict or '건너뜀'})"
                      f" · 저장까지 {time.time() - t_in:.1f}초", flush=True)
                return self.send_json({"ok": True, "id": msg["id"], "date": msg["date"], "check": msg.get("moderation")})
            m = re.fullmatch(r"/api/messages/(\w+)/delete", u.path)
            if m:
                # 남긴 사람이 자기 메시지를 지운다. 차에서도 다음에 받아 갈 때 빠지고, 거기에 온 답장도 함께 지운다.
                code = body.get("invite") or ""
                with lock:
                    db = load()
                    inv = find_invite(db, code)
                    if not inv:
                        raise NoInvite("초대 링크로 들어와 주세요")
                    if dead(inv):
                        raise Gone("이 초대 링크는 열 수 없어요")
                    if not dev:
                        self.own(inv)
                    # 이미 지운 메시지면 그대로 성공(원하던 결과). 남의 메시지는 건드리지 않는다
                    if any(x["id"] == m.group(1) and x.get("invite") == code for x in db["messages"]):
                        drop_message(db, m.group(1))
                        save(db)
                return self.send_json({"ok": True})
            m = re.fullmatch(r"/api/messages/(\w+)/edit", u.path)
            if m:
                # 남긴 사람이 자기 메시지의 날짜·반복·녹음을 바꾼다. 남길 때와 같은 검사를 하고, 답장은 그대로 둔다.
                code, mid = body.get("invite") or "", m.group(1)
                with lock:
                    db = load()
                    self.own_invite(db, code, dev)
                    msg = next((x for x in db["messages"] if x["id"] == mid and x.get("invite") == code), None)
                    if not msg:
                        raise ValueError("이미 지운 메시지예요")
                    moment = msg["moment"]
                change = {}
                if body.get("repeat") is not None:
                    if body["repeat"] not in REPEATS:
                        raise ValueError("몇 번 들려줄지 골라 주세요")
                    change["repeat"] = body["repeat"]
                if body.get("date"):
                    any_day = body["date"] == "any"
                    change.update(any=any_day, date=resolve_date("today" if any_day else body["date"]),
                                  picked=str(body["date"]) not in ("today", "tomorrow", "any"))
                name = verdict = None
                if body.get("audio"):
                    info = {}
                    name = store_audio(body.get("mime", "audio/webm"), body["audio"], MOMENTS[moment]["max_sec"], info)
                    change["sec"] = info.get("sec")  # 차 '들은 메시지' 줄의 길이
                    verdict, quick = moderate_audio(name, bool(body.get("quiet_ok")), info.get("peak"))  # 말소리가 없으면 새 파일을 지우고 묻는다(예전 녹음은 그대로). AI 검수는 뒤에서
                if not change and not name:
                    raise ValueError("바꿀 내용이 없어요")
                old = None
                with lock:
                    db = load()
                    try:
                        self.own_invite(db, code, dev)
                        msg = next((x for x in db["messages"] if x["id"] == mid and x.get("invite") == code), None)
                        if not msg:
                            raise ValueError("이미 지운 메시지예요")
                        if moment == "place" and not place_waiting(msg, None, code) and place_waiting({**msg, **change}, None, code):
                            if sum(1 for x in db["messages"] if place_waiting(x, None, code)) >= MAX_PLACES:
                                raise ValueError(PLACE_FULL)
                    except ValueError:
                        if name:
                            remove_audio(name)
                        raise
                    msg.update(change)
                    if name:
                        # 다시 녹음: 새 파일 이름(uuid)이라 차는 새 목소리를 받는다. 예전 녹음에 온 답장은 그대로 두고 표시만 한다(before_edit)
                        old = msg["audio"]
                        msg["audio"] = f"/audio/{name}"
                        for k in ("moderation", "reviews", "was_quick", "quick", "audio_miss"):
                            msg.pop(k, None)
                        for r in db["replies"]:
                            if r.get("message_id") == mid:
                                r["before_edit"] = True
                        if verdict:
                            msg["moderation"] = verdict
                        if quick:
                            msg["quick"] = quick
                    # 바꾼 메시지는 새로 보내는 것: 들음·사라짐 표시를 지운다(운전자가 '그만 듣기'한 것은 그대로)
                    for k in ("played", "played_day", "expired", "played_on", "expired_on"):
                        msg.pop(k, None)
                    msg["edited"] = int(time.time())
                    if name and verdict == "pending":
                        checking[msg["id"]] = checking.get(msg["id"], 0) + 1
                    save(db)
                if old:
                    remove_audio(old)
                if name and verdict == "pending":
                    queue_check(msg["id"], reserved=True)
                return self.send_json({"ok": True, "id": msg["id"], "date": msg["date"], "check": msg.get("moderation")})
            if u.path == "/api/profile":
                # 남기는 사람 내 정보: 이름 바꾸기·사진 넣기/지우기. 한 링크는 한 사람이라 남긴 메시지의 이름도 같이 바꾼다.
                code = body.get("invite") or ""
                new_name = None
                if "name" in body:
                    new_name = str(body.get("name") or "").strip()[:20]
                    if not new_name:
                        raise ValueError("이름을 적어 주세요")
                # claim: 아무 폰도 잠그지 않은 링크를 이 폰이 갖는다(첫 프로필 [완료]). 새 웹은 직접 만든 열쇠(device)를 같이 보낸다:
                # 응답이 끊겨 다시 눌러도 같은 열쇠라 그대로 성공한다(이미 이 열쇠로 잠겼으면 그 폰이다). 열쇠를 안 보내면(옛 웹·시험 도구) 서버가 만든다
                claim = bool(body.get("claim"))
                ckey = body.get("device") if claim and isinstance(body.get("device"), str) and KEY_RE.fullmatch(body["device"]) else None
                # 캐릭터(avatar: 부품 14칸 또는 preset)·대표색(color 0~7). 사진을 저장하기 전에 값부터 확인한다
                av = body.get("avatar")
                col = avatar.clean_color(body["color"]) if body.get("color") is not None else None
                if av is not None:
                    avatar.clean(av)
                free = lambda i: claim and i and not dead(i) and not i.get("device_hash") and not i.get("guardian")
                with lock:
                    db0 = load()
                    if not free(find_invite(db0, code)):
                        self.own_invite(db0, code, dev, extra=(ckey,))  # 사진을 저장하기 전에 먼저 확인
                photo, photo_ok = store_photo(body["photo"]) if body.get("photo") else (None, None)
                old, token = None, None
                with lock:
                    db = load()
                    try:
                        inv = find_invite(db, code)
                        # 같은 차의 다른 사람이 쓰는 색은 못 고른다(가입 전에 먼저 본다: 막히면 링크를 잠그지 않는다)
                        if inv and col is not None and col != inv.get("color") and col in used_colors(db, inv.get("car"), inv):
                            raise ValueError(COLOR_TAKEN)
                        if free(inv):
                            token = claim_invite(db, inv, ckey)
                        inv = self.own_invite(db, code, dev, extra=(token or ckey,))
                    except ValueError:
                        if photo:
                            remove_photo(photo)
                        raise
                    if new_name:
                        inv["name"] = new_name
                        mine = {x["id"] for x in db["messages"] if x.get("invite") == code}
                        for x in db["messages"]:
                            if x["id"] in mine:
                                x["sender"] = new_name
                        for r in db["replies"]:
                            if r["message_id"] in mine:
                                r["to"] = new_name
                    if photo or body.get("photo_remove"):
                        old = inv.pop("photo", None)
                        inv.pop("photo_ok", None)
                        if photo:
                            inv["photo"], inv["photo_ok"] = photo, photo_ok
                    if seated(inv):   # 자리가 없는 사람(예전 기록 6번째)은 광장에 안 나오므로 캐릭터를 두지 않는다
                        if av is not None:
                            inv["avatar"] = avatar.clean(av, inv.get("avatar"))
                        if col is not None:
                            inv["color"] = col
                    save(db)
                if old:
                    remove_photo(old)
                res = {"ok": True, "name": inv.get("name"), "photo": inv.get("photo"),
                       "avatar": inv.get("avatar"), "color": inv.get("color"), "used_colors": used_colors(db, inv.get("car"), inv)}
                if claim and (token or (self.key_out and self.key_out[1] == ckey)):
                    res.update(device=token or ckey, claimed=inv.get("claimed"))   # 다시 보낸 같은 열쇠도 성공으로
                return self.send_json(res)
            m = re.fullmatch(r"/api/replies/(\w+)/delete", u.path)
            if m:
                # 남긴 사람이 받은 답장을 지운다(자기 메시지에 온 답장만)
                code = body.get("invite") or ""
                with lock:
                    db = load()
                    self.own_invite(db, code, dev)
                    mine = {x["id"] for x in db["messages"] if x.get("invite") == code}
                    rep = next((r for r in db["replies"] if r["id"] == m.group(1) and r["message_id"] in mine), None)
                    if rep:   # 이미 지운 답장이면 그대로 성공
                        db["replies"] = [r for r in db["replies"] if r["id"] != rep["id"]]
                        save(db)
                if rep:
                    remove_audio(rep["audio"])
                return self.send_json({"ok": True})
            if u.path == "/api/together":
                # 보호자가 '함께 쓰는 사람'(만 14세 미만)을 추가한다: 같은 차의 새 사람. 보호자 동의(consent: true)가 있어야 한다.
                # 차당 5명 상한은 그대로(자리가 없으면 FULL). 대표색은 같은 차에서 겹치지 않는다
                code = body.get("invite") or ""
                name = str(body.get("name") or "").strip()[:20]
                if body.get("consent") is not True:
                    raise ValueError(NEED_CONSENT)
                if not name:
                    raise ValueError("이름을 적어 주세요")
                av = body.get("avatar")
                if av is not None:
                    av = avatar.clean(av)
                col = avatar.clean_color(body["color"]) if body.get("color") is not None else None
                with lock:
                    db = load()
                    g = self.own_invite(db, code, dev)
                    if g.get("guardian") or not g.get("name") or not seated(g):
                        raise ValueError(KID_BAD)   # 함께 쓰는 사람이 또 추가하거나, 프로필을 안 만든 사람
                    if free_slot(db, g.get("car")) is None:
                        raise ValueError(FULL)
                    if col is not None and col in used_colors(db, g.get("car")):
                        raise ValueError(COLOR_TAKEN)
                    now = int(time.time())
                    kid = {"code": kid_code(db), "created": now, "claimed": now, "car": g.get("car"), "from": g.get("from"),
                           "name": name, "guardian": g["code"], "consent": now, "consent_v": KID_CONSENT_V, "consent_items": KID_CONSENT_ITEMS}
                    if g.get("device_hash"):
                        kid["device_hash"] = g["device_hash"]
                    if col is not None:
                        kid["color"] = col
                    if av is not None:
                        kid["avatar"] = av
                    seat(db, kid)
                    db["invites"].append(kid)
                    save(db)
                    out = {"ok": True, **kid_view(kid), "together": [kid_view(k) for k in kids_of(db, g)],
                           "used_colors": used_colors(db, g.get("car"), g)}
                print("[함께 쓰는 사람] 추가", flush=True)
                return self.send_json(out)
            if u.path == "/api/leave":
                # 탈퇴: 남긴 메시지(목소리·답장까지)·알림 구독·사진·이름을 지우고 이 링크를 끊는다
                code = body.get("invite") or ""
                with lock:
                    db = load()
                    inv = self.own_invite(db, code, dev)
                    mids = [x["id"] for x in db["messages"] if x.get("invite") == code]
                    for mid in mids:
                        drop_message(db, mid)
                    db.get("push", {}).pop(code, None)
                    photo = inv.pop("photo", None)
                    inv["name"] = None
                    unseat(inv)   # 자리는 비워 둔다(다른 사람을 당기지 않는다)
                    inv["revoked"] = inv["left"] = int(time.time())
                    kid_photos = drop_kids(db, inv, True)   # 보호자가 탈퇴하면 함께 쓰는 사람도 메시지까지 같이 지운다
                    save(db)
                for p in [photo, *kid_photos]:
                    if p:
                        remove_photo(p)
                print("[탈퇴] 지운 메시지", len(mids), flush=True)
                self.key_out, self.key_clear = None, code   # 이 폰의 열쇠 쿠키도 지운다
                return self.send_json({"ok": True})
            m = re.fullmatch(r"/api/messages/(\w+)/(played|expired|stop|resume)", u.path)
            if m:
                # 차가 열었거나(played) 못 열고 사라졌다(expired)고 표시. 숨긴 사람에게는 알리지 않는다.
                # 반복 메시지는 날짜별로 남기고, 운전자가 그만 들어도(stop) 남긴 사람 화면은 바뀌지 않는다.
                day = resolve_date(body.get("date"), allow_past=True)
                with lock:
                    db = load()
                    for msg in db["messages"]:
                        if msg["id"] != m.group(1) or not of_car(msg, self.car()):
                            continue
                        kind = m.group(2)
                        # 언제 들었는지는 날짜까지만 남긴다(시각이 있으면 운행 시간을 짐작할 수 있다)
                        if kind == "stop":
                            msg["stopped"] = day
                        elif kind == "resume":
                            msg.pop("stopped", None)
                        elif msg.get("repeat") == "each":
                            days = msg.setdefault(kind + "_on", [])
                            if day not in days:
                                days.append(day)
                        else:
                            if kind == "played" and msg.get("any"):
                                msg["played_day"] = day
                            msg[kind] = day
                    save(db)
                return self.send_json({"ok": True})
            if u.path == "/api/push":
                # 남기는 사람이 '비 오기 전날 알려 주기'를 켜거나 끈다. 위치는 그 사람 폰의 대략 위치(날씨용, 소수 둘째 자리까지)
                code = body.get("invite") or ""
                with lock:
                    db = load()
                    inv = find_invite(db, code)
                    if not inv:
                        raise NoInvite("초대 링크로 들어와 주세요")
                    if dead(inv):
                        raise Gone("이 초대 링크는 열 수 없어요")
                    if not dev:
                        self.own(inv)
                    subs = db.setdefault("push", {})
                    if not body.get("on"):
                        subs.pop(code, None)
                    else:
                        sub = body.get("sub") or {}
                        if not isinstance(sub, dict) or not push.allowed(sub.get("endpoint")):   # 알려진 푸시 서비스 주소만(아무 곳으로나 요청을 보내지 않게)
                            raise ValueError("알림을 켜지 못했어요. 다시 눌러 주세요")
                        lat, lon = body.get("lat"), body.get("lon")
                        loc = (round(float(lat), 2), round(float(lon), 2)) if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) else (None, None)
                        subs[code] = {"on": True, "sub": sub, "lat": loc[0], "lon": loc[1],
                                      "sent": subs.get(code, {}).get("sent", []), "created": int(time.time())}
                    save(db)
                return self.send_json({"ok": True, "on": bool(body.get("on"))})
            if u.path == "/api/push/test":
                # 시연·시험용(맥 안에서만): 예보와 상관없이 지금 보낸다. 차 열쇠로 밖에서 부를 수 없다
                if not self.local():
                    return self.send_json({"error": "없는 주소"}, 404)
                p = load().get("push", {}).get(body.get("invite") or "")
                if not p:
                    raise ValueError("이 폰에서 켠 알림이 아니에요")
                r = push.send(p["sub"], push.RAIN_TITLE, push.RAIN_BODY, f"/?invite={body['invite']}&m=rain", "rain")
                return self.send_json({"ok": bool(r)})
            if u.path == "/api/reports":
                # 운전자가 정차 중 '이 사람 신고': 그 사람의 초대 링크를 끊고(남은 메시지도 더는 안 나옴) 운영자가 볼 수 있게 남긴다.
                with lock:
                    db = load()
                    target = next((x for x in db["messages"] if x["id"] == body.get("message_id") and of_car(x, self.car())), None)
                    if not target:
                        raise ValueError("신고할 메시지가 없어요")
                    inv = find_invite(db, target.get("invite") or "")
                    photo = None
                    if inv:
                        if not inv.get("revoked"):
                            inv["revoked"] = int(time.time())
                        if not inv.get("moved"):
                            photo = forget_person(db, inv)   # 끊을 때와 같이 이름·사진·알림 구독을 바로 지운다
                            for p in drop_kids(db, inv, False):   # 보호자를 신고하면 함께 쓰는 사람도 같이 끊는다
                                remove_photo(p)
                    # 운영자가 볼 수 있게 신고한 날부터 REPORT_DAYS 동안 둔다(prune_old). 신고 시각을 남긴다
                    target["reported"] = int(time.time())
                    db.setdefault("reports", []).append({"id": uuid.uuid4().hex[:10], "car": self.car() or None,
                                                         "invite": target.get("invite"), "message_id": target["id"],
                                                         "created": int(time.time())})
                    save(db)
                if photo:
                    remove_photo(photo)
                print("[신고] 메시지", target["id"], flush=True)
                return self.send_json({"ok": True})
            if u.path == "/api/plaza/order":
                # 차 주인이 ⋯ → 자리 바꾸기: {slots: {코드: 자리}}. 보낸 것만 바꾸고 나머지는 그대로, 겹치면 거절(맞바꾸기는 둘 다 보낸다)
                slots = body.get("slots")
                if not isinstance(slots, dict) or not slots:
                    raise ValueError(ORDER_BAD)
                car = self.car() or None
                with lock:
                    db = load()
                    ppl = {i["code"]: i for i in peers(db, car)}
                    want = {c: i["slot"] for c, i in ppl.items()}
                    for c, s in slots.items():
                        if c not in ppl or isinstance(s, bool) or not isinstance(s, int) or not 1 <= s <= avatar.MAX_PEOPLE:
                            raise ValueError(ORDER_BAD)
                        want[c] = s
                    if len(set(want.values())) != len(want):
                        raise ValueError(ORDER_BAD)
                    if any(ppl[c]["slot"] != s for c, s in want.items()):
                        for c, s in want.items():
                            ppl[c]["slot"] = s
                        save(db)
                    view = plaza_view(db, car)
                return self.send_json({"ok": True, **view})
            if u.path == "/api/demo/reset":
                # 시연 반복용: 오늘 메시지를 다시 안 연 상태로 되돌린다
                with lock:
                    db = load()
                    for msg in db["messages"]:
                        if not of_car(msg, self.car()):
                            continue
                        for k in ("played", "played_day", "expired", "played_on", "expired_on", "stopped"):
                            msg.pop(k, None)
                    save(db)
                return self.send_json({"ok": True})
            if u.path == "/api/reactions":
                # 차: 들은 메시지에 운전자가 고르는 이모티콘 반응(녹음 없음). {message_id, emoji}. emoji는 REACTIONS 다섯 개 중 하나.
                # 하나만 남는다: 다른 걸 고르면 바뀌고, 같은 걸 다시 누르면 그대로(취소 없음). 이 차에 온 메시지만
                # (밖에서는 차 열쇠가 있어야 이 주소가 열린다: blocked). 처음 보낼 때와 바뀔 때만 남긴 사람 폰에 알림(함께 쓰는 사람 메시지면 보호자 폰)
                emoji = body.get("emoji")
                if emoji == "\u2764":
                    emoji = REACTIONS[0]   # 글자 모양 고르개(FE0F) 없이 온 하트도 같은 하트로
                if emoji not in REACTIONS:
                    raise ValueError("보낼 수 없는 반응이에요")
                sub, to, first, changed = {}, "", False, False
                with lock:
                    db = load()
                    target = next((x for x in db["messages"] if x["id"] == body.get("message_id") and of_car(x, self.car())), None)
                    if not target:
                        raise Gone("남긴 사람이 지운 메시지예요")   # 답장과 같게: 지웠거나 다른 차의 메시지
                    was = reaction_of(target)
                    if not was or was["emoji"] != emoji:
                        first, changed = not was, bool(was)
                        target["reaction"] = {"emoji": emoji, "at": int(time.time())}
                        save(db)
                        owner = find_invite(db, target.get("invite") or "") or {}
                        to = owner.get("guardian") or target.get("invite") or ""
                        sub = db.get("push", {}).get(to, {})
                    now = reaction_of(target)
                notify = first or changed
                if notify and sub.get("on"):
                    # 잘못 눌러 바로 바꾸는 경우 알림이 두 번 가지 않게: 잠깐 기다렸다가 그때 남아 있는 이모티콘 하나만 보낸다(11/08 사용자)
                    threading.Timer(REACT_HOLD_S, react_push_later, args=(target["id"], now["at"], sub, to)).start()
                return self.send_json({"ok": True, "id": target["id"], "reaction": now, "new": first, "changed": changed, "notify": notify})
            if u.path == "/api/replies":
                with lock:
                    db = load()
                    target = next((x for x in db["messages"] if x["id"] == body.get("message_id") and of_car(x, self.car())), None)
                if not target:
                    raise Gone("남긴 사람이 지운 메시지예요")  # 차는 410 gone을 보고 '지운 메시지라 답장할 수 없습니다'를 띄운다
                name = store_audio(body.get("mime", "audio/mp4"), body.get("audio"), 6)
                rep = {"id": uuid.uuid4().hex[:10], "to": target["sender"], "message_id": target["id"],
                       "moment": target["moment"], "audio": f"/audio/{name}", "created": int(time.time())}
                with lock:
                    db = load()
                    db["replies"].append(rep)
                    save(db)
                    # 함께 쓰는 사람이 남긴 메시지면 보호자 폰(보호자 링크의 알림)으로 알린다
                    owner = find_invite(db, target.get("invite") or "") or {}
                    to = owner.get("guardian") or target.get("invite") or ""
                    sub = db.get("push", {}).get(to, {})
                if sub.get("on"):
                    threading.Thread(target=reply_push, args=(target, sub, to), daemon=True).start()
                return self.send_json({"ok": True, "id": rep["id"]})
            return self.send_json({"error": "없는 주소"}, 404)
        except Gone as e:
            return self.send_json({"error": str(e), "gone": True}, 410)
        except Taken as e:
            return self.send_json({"error": str(e), "taken": e.taken}, 403)
        except Quiet as e:
            return self.send_json({"error": str(e), "quiet": True}, 422)
        except TooMany as e:
            return self.send_json({"error": str(e), "wait": e.wait, "everyone": e.everyone}, 429)
        except TooBig as e:
            return self.send_json({"error": str(e)}, 413)
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            if isinstance(e, NoInvite):
                self.miss()
            return self.send_json({"error": user_error(e)}, 400)
        except Exception as e:  # 예상 못 한 오류도 연결을 끊지 않고 알려 준다
            print("서버 오류:", type(e).__name__, flush=True)
            return self.send_json({"error": OOPS}, 500)


if __name__ == "__main__":
    # 클라우드(렌더)는 PORT를 주고 밖에서 들어온다. 맥에서는 맥 안에서만 연다(에뮬레이터의 10.0.2.2는 맥의 127.0.0.1).
    cloud = bool(os.environ.get("PORT"))
    port = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8090))
    if cloud and not CAR_KEY:
        sys.exit("CAR_KEY가 없으면 인터넷에서 차 주소를 열 수 없어요")
    store.setup()
    if store.ON and not os.path.exists(DB):
        # 보관소가 '정말 없다'고 할 때만 빈 기록으로 시작한다. 오류면 기다렸다 다시, 끝내 안 되면 띄우지 않는다(빈 기록이 원본을 덮지 않게)
        for attempt in range(6):
            got = store.download("db.json", DB)
            if got is not None:
                break
            time.sleep(5 * (attempt + 1))
        else:
            sys.exit("보관소에서 기록을 받지 못해 서버를 띄우지 않아요")  # 빈 기록이 원본을 덮지 않게
        print("[보관] 기록 내려받음" if got else "[보관] 기록 없음: 새로 시작", flush=True)
    if os.path.exists(DB):
        with lock:
            raw = load(fill=False)
            if fill_people(raw):   # 예전 사람에게 자리·색·캐릭터를 한 번 채워 저장(두 번 돌려도 같다)
                save(raw)
                print("[광장] 예전 기록에 자리·대표색·캐릭터 채움", flush=True)
    print(f"도담도담 서버: 포트 {port}" + (" (클라우드)" if cloud else f"  (에뮬레이터: http://10.0.2.2:{port})"), flush=True)
    threading.Thread(target=recheck_loop, daemon=True).start()
    threading.Thread(target=check_worker, daemon=True).start()
    if os.environ.get("MODERATE") != "0":
        # 꺼지기 전에 뒤 검수를 못 마친 것(AI 검수를 한 번도 안 한 것)을 다시 줄에 넣는다
        for x in load()["messages"]:
            if x.get("moderation") == "pending" and x.get("quick") and not x.get("reviews"):
                queue_check(x["id"])
    def bye(signum, frame):
        # 렌더가 새 판을 띄우고 이 서버를 끌 때(SIGTERM): 아직 못 올린 기록(db.json)과 파일을 보관소에 바로 올리고 끝낸다.
        # 저장하는 잠금을 먼저 잡아 그사이 새 저장이 끼지 않게 한다(잠금을 못 잡아도 올리기는 한다)
        print("[종료] 못 올린 기록을 보관소에 올리는 중", flush=True)
        lock.acquire(timeout=5)
        try:
            store.flush(time.time() + 20)
        except Exception as e:
            print("[종료] 올리기 오류:", type(e).__name__, flush=True)
        finally:
            print("[종료] 끝", flush=True)
            os._exit(0)
    signal.signal(signal.SIGTERM, bye)
    ThreadingHTTPServer(("0.0.0.0" if cloud else "127.0.0.1", port), Handler).serve_forever()
