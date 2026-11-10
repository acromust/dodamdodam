"""남길 때 알림(웹 푸시). 남기는 사람 폰에만 간다. 운전자 정보(위치·들었는지)는 쓰지 않는다.
지금은 한 종류: 남기는 사람이 있는 곳에 내일 비가 오면 전날 저녁에 "비 올 때 들려줄 메시지를 남길 수 있어요".
한 사람에게 일주일에 두 번까지. 키는 VAPID_PRIVATE·VAPID_PUBLIC(환경 변수 또는 pleos-contest/.env). 출력하지 않는다.
pywebpush가 없으면 꺼진다(서버는 그대로 돈다).
"""
import json
import os
import urllib.request
from datetime import date, timedelta
from urllib.parse import urlparse

ENV = os.path.join(os.path.dirname(__file__), "..", "..", ".env")


def _env(name):
    if os.environ.get(name):
        return os.environ[name]
    if os.path.exists(ENV):
        for l in open(ENV):
            if l.startswith(name + "="):
                return l.split("=", 1)[1].strip().strip('"')
    return ""


PUBLIC = _env("VAPID_PUBLIC")
PRIVATE = _env("VAPID_PRIVATE")
CONTACT = "mailto:noreply@dodam.invalid"  # 푸시 서비스에 알리는 연락처(실제 주소 아님)
PER_WEEK = 2
FORCE = os.environ.get("FORECAST") == "rain"  # 시연용: 예보와 상관없이 내일 비로 본다
RAIN_TITLE = "내일 비가 온대요"
RAIN_BODY = "비 올 때 들려줄 메시지를 남길 수 있어요"  # 서버 시험 알림(/api/push/test)도 이 글을 쓴다

try:
    from pywebpush import WebPushException, webpush
    ON = bool(PUBLIC and PRIVATE)
except ImportError:
    ON = False


# 받아 주는 푸시 서비스 주소(브라우저가 정한다): 크롬·삼성·엣지 일부(FCM), 사파리(애플), 파이어폭스(모질라), 엣지(윈도우)
PUSH_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com")
PUSH_SUFFIXES = (".push.apple.com", ".notify.windows.com", ".push.services.mozilla.com")


def allowed(endpoint):
    """알림을 보낼 주소가 알려진 푸시 서비스인지. 아무 주소나 받으면 서버가 남이 고른 곳으로 요청을 보내게 된다."""
    try:
        u = urlparse(str(endpoint or ""))
        host = (u.hostname or "").lower()
        port = u.port
    except ValueError:
        return False
    if u.scheme != "https" or u.username or u.password or port not in (None, 443):
        return False
    return host in PUSH_HOSTS or host.endswith(PUSH_SUFFIXES)


def rain_tomorrow(lat, lon):
    """내일 비 예보(강수 확률 60% 이상이고 1mm 이상). 예보를 못 받으면 False."""
    if FORCE:
        return True
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat:.2f}&longitude={lon:.2f}"
           "&daily=precipitation_probability_max,precipitation_sum&timezone=Asia%2FSeoul&forecast_days=2")
    try:
        d = json.load(urllib.request.urlopen(url, timeout=10))["daily"]
        return (d["precipitation_probability_max"][1] or 0) >= 60 and (d["precipitation_sum"][1] or 0) >= 1
    except Exception as e:
        print("[알림] 예보 실패", type(e).__name__, flush=True)
        return False


def send(sub, title, body, url, tag):
    """True면 보냄, None이면 구독이 끝남(지워야 함), False면 실패."""
    if not ON:
        return False
    if not allowed((sub or {}).get("endpoint")):
        print("[알림] 모르는 푸시 주소라 안 보냄", flush=True)
        return None   # 구독을 지운다
    try:
        webpush(sub, json.dumps({"title": title, "body": body, "url": url, "tag": tag}, ensure_ascii=False),
                vapid_private_key=PRIVATE, vapid_claims={"sub": CONTACT}, ttl=12 * 3600)
        return True
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        print("[알림] 보내기 실패", code, flush=True)
        return None if code in (404, 410) else False
    except Exception as e:  # 연결 실패 등: 다음에 다시
        print("[알림] 보내기 실패", type(e).__name__, flush=True)
        return False


def recent(sent, today):
    week = (date.fromisoformat(today) - timedelta(days=6)).isoformat()
    return [d for d in sent if d >= week]


def rain_nudges(db, today, revoked):
    """구독한 사람마다 내일 비면 한 번 보낸다. 바뀐 게 있으면 True(저장 필요)."""
    changed = False
    for code, p in list(db.get("push", {}).items()):
        if code in revoked or not p.get("on"):
            continue
        if today in p.get("sent", []) or len(recent(p.get("sent", []), today)) >= PER_WEEK:
            continue
        if p.get("lat") is None or not rain_tomorrow(p["lat"], p["lon"]):
            continue
        r = send(p["sub"], RAIN_TITLE, RAIN_BODY, f"/?invite={code}&m=rain", "rain")
        if r is None:
            db["push"].pop(code, None)
        elif r:
            p["sent"] = recent(p.get("sent", []), today) + [today]
        changed = True
    return changed
