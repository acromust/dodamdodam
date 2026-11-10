"""클라우드 보관(수파베이스 Storage). 렌더 무료 서버는 디스크가 재시작 때 지워지므로, 기록(db.json)과 목소리 파일을 여기에도 둔다.
SUPABASE_URL·SUPABASE_KEY(service_role)가 없으면 아무것도 안 한다(맥에서 돌릴 때). 키는 출력하지 않는다.
쓰기는 순서대로 뒤에서 올린다(남기는 사람을 기다리게 하지 않으려고). 읽기는 로컬에 없을 때만 내려받는다.
올리기는 될 때까지 다시 한다(간격을 늘려 가며). 못 지운 파일은 목록(pending_del.json)에 적어 두고 나중에 다시 지운다.
서버가 꺼질 때(SIGTERM) flush로 남은 올리기를 바로 끝낸다.
"""
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_KEY", "")
BUCKET = os.environ.get("SUPABASE_BUCKET", "dodam")
ON = bool(URL and KEY)

_jobs = queue.Queue()
_io = threading.Lock()        # 한 번에 하나만 올린다(뒤 일꾼과 꺼질 때 flush가 겹치지 않게)
_stop = threading.Event()     # 꺼지는 중: 일꾼은 새로 올리지 않고 flush가 넘겨받는다
_current = None               # 일꾼이 붙잡고 다시 하는 중인 일(꺼질 때 flush가 이것부터 한다)
LATEST = ("db.json", "pending_del.json")  # 마지막 것만 올리면 되는 파일(줄에 새것이 있으면 앞의 것은 건너뜀)
PENDING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pending_del.json")
_pend_mu = threading.Lock()
_retrying = set()             # 다시 지우려고 줄에 넣은 것(같은 걸 두 번 넣지 않게)


def _req(method, path, data=None, ctype="application/octet-stream", extra=None, timeout=20):
    h = {"Authorization": f"Bearer {KEY}", "apikey": KEY, "Content-Type": ctype}
    h.update(extra or {})
    req = urllib.request.Request(f"{URL}/storage/v1/{path}", data=data, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def setup():
    """버킷이 없으면 비공개로 만든다. 못 지운 파일 목록이 로컬에 없으면 보관소에서 받아 둔다."""
    if not ON:
        return
    try:
        _req("POST", "bucket", json.dumps({"id": BUCKET, "name": BUCKET, "public": False}).encode(), "application/json")
        print("[보관] 버킷 만듦", flush=True)
    except urllib.error.HTTPError as e:
        if e.code not in (400, 409):  # 이미 있음
            print("[보관] 버킷 확인 실패", e.code, flush=True)
    except Exception as e:
        print("[보관] 버킷 확인 실패", type(e).__name__, flush=True)
    if not os.path.exists(PENDING):
        download("pending_del.json", PENDING)
    threading.Thread(target=_worker, daemon=True).start()


def download(key, local):
    """있으면 내려받아 True, 정말 없으면 False, 보관소 오류(5xx·연결 실패)면 None.
    None을 '없음'으로 보면 빈 기록이 원본을 덮어쓰거나 멀쩡한 메시지를 막게 된다."""
    if not ON:
        return False
    try:
        with _req("GET", f"object/{BUCKET}/{key}") as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):  # 수파베이스는 없는 파일에 400 또는 404로 답한다
            return False
        print("[보관] 내려받기 실패", key, e.code, flush=True)
        return None
    except Exception as e:
        print("[보관] 내려받기 실패", key, type(e).__name__, flush=True)
        return None
    # 같은 파일을 여러 요청이 한꺼번에 받아도 섞이지 않게 받는 것마다 다른 임시 이름에 쓰고 한 번에 바꾼다
    tmp = f"{local}.{uuid.uuid4().hex}.dl"
    try:
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, local)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return True


def upload(local, key, ctype):
    if ON:
        _jobs.put(("put", local, key, ctype))


def remove(key):
    if ON:
        _jobs.put(("del", None, key, None))


def _pending():
    try:
        with open(PENDING, encoding="utf-8") as f:
            v = json.load(f)
        return [k for k in v if isinstance(k, str)] if isinstance(v, list) else []
    except (OSError, ValueError):
        return []


def _set_pending(fn):
    """못 지운 파일 목록을 고친다(fn: 목록 → 새 목록). 바뀌면 로컬에 쓰고 보관소에도 올린다(서버를 다시 켜도 남게)."""
    with _pend_mu:
        old = _pending()
        new = fn(list(old))
        if new == old:
            return
        tmp = f"{PENDING}.{uuid.uuid4().hex}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new, f)
        os.replace(tmp, PENDING)
    upload(PENDING, "pending_del.json", "application/json")


def retry_deletes():
    """못 지운 파일을 다시 지우게 줄에 넣는다(서버의 정리 루프가 몇 분마다 부른다)."""
    if not ON:
        return
    for key in _pending()[:50]:
        if key not in _retrying:
            _retrying.add(key)
            _jobs.put(("del", None, key, "retry"))


def _newer(key):
    return any(j[0] == "put" and j[2] == key for j in list(_jobs.queue))


def _try(job):
    """한 번 해 본다. 됐으면 None, 안 됐으면 HTTP 코드(연결 실패는 0)."""
    op, local, key, _ = job
    try:
        if op == "put":
            if not os.path.exists(local):
                return None   # 그사이 지운 파일: 올릴 것이 없다
            with open(local, "rb") as f:
                _req("POST", f"object/{BUCKET}/{key}", f.read(), job[3], {"x-upsert": "true"}).close()
        else:
            _req("DELETE", f"object/{BUCKET}", json.dumps({"prefixes": [key]}).encode(), "application/json").close()
        return None
    except urllib.error.HTTPError as e:
        print("[보관] 올리기 실패", op, key, e.code, flush=True)
        return e.code
    except Exception as e:
        print("[보관] 올리기 실패", op, key, type(e).__name__, flush=True)
        return 0


def _done(job, ok):
    """지우기가 끝났을 때 목록 정리: 됐으면 목록에서 빼고, 끝내 안 됐으면 목록에 넣는다."""
    op, _, key, tag = job
    if op != "del":
        return
    _retrying.discard(key)
    if ok and (tag == "retry" or key in _pending()):
        _set_pending(lambda l: [k for k in l if k != key])
    elif not ok:
        _set_pending(lambda l: l if key in l else l + [key])


def _worker():
    """줄에 든 일을 차례로 한다. 올리기는 될 때까지 다시(2초부터 두 배씩, 길어야 60초 간격).
    지우기는 3번 해 보고 안 되면 목록에 적어 두고 나중에 다시(줄을 막지 않게).
    '없는 요청'처럼 다시 해도 안 될 오류(4xx, 408·429 빼고)는 db.json이 아니면 5번 해 보고 그만둔다."""
    global _current
    while True:
        job = _jobs.get()
        _current = job   # 바로 적어 둔다: 그사이 꺼지면 flush가 이것부터 한다
        with _io:
            if _stop.is_set():
                return   # 꺼지는 중: flush가 _current부터 한다
        op, _, key, _ = job
        tries = 0
        while True:
            if op == "put" and key in LATEST and _newer(key):
                ok, give_up = True, True   # 더 새 것이 줄에 있다: 이건 건너뛴다
            else:
                with _io:
                    if _stop.is_set():
                        return
                    code = _try(job)
                ok, give_up = code is None, False
                tries += 1
                if not ok:
                    if op == "del" and tries >= 3:
                        give_up = True
                    elif op == "put" and key not in LATEST and 400 <= code < 500 and code not in (408, 429) and tries >= 5:
                        print("[보관] 올리기 그만둠", key, code, flush=True)
                        give_up = True
            if ok or give_up:
                with _io:
                    _current = None
                _done(job, ok)
                break
            _stop.wait(min(60, 2 ** tries))


def flush(deadline):
    """꺼지기 전에 남은 일을 지금 한다(deadline 시각까지). db.json 같은 건 마지막 것만 올린다.
    지우기는 한 번만 해 보고 안 되면 목록에 적는다(다음에 켜진 서버가 지운다)."""
    if not ON:
        return
    _stop.set()
    if not _io.acquire(timeout=max(0.1, deadline - time.time())):
        print("[보관] 꺼지기 전 올리기: 일꾼이 끝나지 않음", flush=True)
        return
    try:
        jobs = [_current] if _current else []
        while True:
            try:
                jobs.append(_jobs.get_nowait())
            except queue.Empty:
                break
        last = {j[2]: i for i, j in enumerate(jobs) if j[0] == "put" and j[2] in LATEST}
        failed = []
        for i, job in enumerate(jobs):
            if job[0] == "put" and job[2] in LATEST and last[job[2]] != i:
                continue
            if job[0] == "del":
                if _try(job) is not None:
                    failed.append(job[2])
                continue
            while _try(job) is not None and time.time() < deadline - 1:
                time.sleep(1)
        if failed:
            pend = _pending()
            new = pend + [k for k in failed if k not in pend]
            with open(PENDING, "w", encoding="utf-8") as f:
                json.dump(new, f)
            _try(("put", PENDING, "pending_del.json", "application/json"))
        print(f"[보관] 꺼지기 전 올리기 {len(jobs)}건 끝", flush=True)
    finally:
        _io.release()
