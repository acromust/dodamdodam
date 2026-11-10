"""도담도담 회귀 테스트 (2026-11-03, 실시간 받기 뒤). 에뮬레이터 + 콘솔(8088) + 서버(8090).
주의: 서버 메시지를 비우고 시작한다(돌리기 전에 server/data/db.json을 따로 복사해 둘 것).
콘솔은 페이지를 연 브라우저가 3초 넘게 멈추면 503이 난다. 화면 없는 크롬으로 콘솔을 열어 두면 안 끊긴다.
쓰는 법: python3 tests/reg.py [케이스 이름 ...]   (없으면 전부)
서버만(에뮬레이터·콘솔 없이): python3 tests/reg.py --server   (서버는 MODERATE=0으로 띄운다: 사진·목소리 검수를 건너뛴다)
  다른 포트·기록 파일: DODAM_SRV=http://127.0.0.1:8097 DODAM_DB=경로/db.json python3 tests/reg.py --server"""
import json, subprocess, sys, time, urllib.request, base64, os, re, itertools

ADB = os.path.expanduser('~/Library/Android/sdk/platform-tools/adb')
VC = 'http://localhost:8088'
SRV = os.environ.get('DODAM_SRV', 'http://127.0.0.1:8090')
HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('DODAM_DB') or os.path.join(HERE, '../server/data/db.json')
# 서버는 5초 넘는 녹음을 거절한다. 예시 음성을 새로 만들면서(11/03 밤) demo_rain이 5.9초가 돼 3.3초짜리로 바꿈(11/04)
VOICE = os.path.join(HERE, '../car-app/app/src/main/res/raw/demo_start.m4a')
HOME = (37.4127, 127.0947)
FAR = (37.5000, 127.2000)


def req(url, body=None, method=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data, {'Content-Type': 'application/json'}, method=method or ('POST' if data is not None else 'GET'))
    for i in range(4):
        try:
            return urllib.request.urlopen(r, timeout=timeout).read().decode()
        except urllib.error.HTTPError as e:
            if e.code == 503 and url.startswith(VC):
                raise SystemExit('콘솔 503: 콘솔 탭을 새로 고친 뒤 이 케이스부터 다시')
            if e.code == 503 and i < 3:
                time.sleep(3); continue
            raise


def vc(path, body=None): req(VC + path, body if body is not None else {})
def gear(g): vc('/vehicle/gear', {'gear': g})
def speed(v): vc('/vehicle/controls', {'speed': v})
def steer(d): vc('/vehicle/controls', {'steering': d})
def wiper(w): vc('/vehicle/body', {'front_wiper': w})
def signal(m): vc('/vehicle/turn-signal', {'mode': m})
def soc(p): req(f'{VC}/vehicle/ev-battery?field=soc&value={p}', {})
def seat(area, v): req(f'{VC}/vehicle/seat?kind=occupied&area={area}&value={"true" if v else "false"}', {})
def adb(*a): return subprocess.run([ADB, *a], capture_output=True, text=True).stdout
def car(cmd, **ex):
    args = ['shell', 'am', 'start', '-n', 'ai.simeodum.car/.MainActivity', '--es', 'cmd', cmd]
    for k, v in ex.items(): args += ['--es', k, str(v)]
    adb(*args)
def key(): adb('shell', 'input', 'keyevent', 'KEYCODE_MEDIA_PLAY_PAUSE')
def geo(lat, lon): adb('emu', 'geo', 'fix', str(lon), str(lat))
def log(): return adb('logcat', '-d', '-s', 'SIM')


def wait_for(pat, timeout, since=0):
    """로그에 pat(정규식)이 나올 때까지 기다린다. since: 이미 본 줄 수."""
    end = time.time() + timeout
    while time.time() < end:
        lines = log().splitlines()[since:]
        for l in lines:
            if re.search(pat, l):
                return l
        time.sleep(0.5)
    return None


def nlines(): return len(log().splitlines())


def hide(sender, moment, repeat='once', date='today', invite=None, place=None):
    b = {"sender": sender, "date": date, "moment": moment, "mime": "audio/mp4", "duration": 3,
         "repeat": repeat, "dev": True, "audio": base64.b64encode(open(VOICE, 'rb').read()).decode()}
    if invite: b['invite'] = invite
    if place: b['place'] = place
    return json.loads(req(SRV + '/api/messages', b, timeout=45))['id']


def fresh(mode='button'):
    """차를 그날 첫 출발 전 상태로, 서버 메시지는 비운다."""
    signal('Off'); wiper('Off'); speed(0); steer(0); gear('Park'); soc(60)
    for a in ('passenger', 'rear_left', 'rear_right'):
        try: seat(a, False)   # 콘솔 false = 빈자리(앱이 에뮬레이터 뒤집힘을 바로잡음)
        except Exception: pass
    geo(*FAR)
    d = json.load(open(DB)); d['messages'] = []; d['replies'] = []; json.dump(d, open(DB, 'w'), ensure_ascii=False)
    req(SRV + '/api/demo/reset', {})
    adb('shell', 'am', 'start', '-n', 'ai.simeodum.car/.MainActivity'); time.sleep(2)
    car('mode', value=mode); time.sleep(1)
    car('reset_day'); time.sleep(3)
    # 시동 끔·켬 흉내: 앞 케이스의 '앱 닫음'을 푼다
    adb('shell', 'input', 'keyevent', 'KEYCODE_SLEEP'); time.sleep(2); adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP'); time.sleep(2)
    adb('shell', 'input', 'keyevent', 'KEYCODE_HOME'); time.sleep(1)
    adb('logcat', '-c')


def stopped(limit=30):
    """콘솔이 속도를 서서히 줄이므로(11/03 밤) 실제로 0이 될 때까지 기다린다."""
    end = time.time() + limit
    while time.time() < end:
        try:
            if json.loads(req(VC + '/vehicle/controls') or '{}').get('speed_kph', 1) < 1: return True
        except Exception: pass
        time.sleep(0.5)
    return False


def drive(v=40):
    gear('Drive'); time.sleep(1); speed(v); steer(0)


R = []
def check(name, cond, note=''):
    R.append((name, bool(cond), note))
    print(('PASS' if cond else 'FAIL'), name, note); sys.stdout.flush()


# ---------- 케이스 ----------
def c_realtime_button():
    """비 오며 달리는 중 새로 남김 → 몇 초 안에 받음 → 버튼 듣기 알림 → 핸들 버튼 → 재생"""
    fresh(); drive(); wiper('Low'); time.sleep(12)
    t0 = time.time(); hide('지윤', 'rain')
    got = wait_for(r'이미 와 있는 순간\(rain\)|순간 도착', 15)
    check('실시간 받기', got, f'{round(time.time()-t0,1)}초' if got else '')
    ask = wait_for(r'버튼 듣기: .* 알림', 40)
    check('버튼 듣기 알림', ask)
    time.sleep(4); key()
    check('핸들 버튼 → 재생', wait_for(r'메시지 재생', 15))


def c_no_answer_arrive():
    """버튼 듣기에서 대답 없음 → 주행 중엔 아무것도 → 주차하면 목록"""
    fresh(); hide('지윤', 'rain'); time.sleep(3); drive(); time.sleep(3); wiper('Low')
    check('알림', wait_for(r'버튼 듣기: .* 알림', 60))
    n = nlines()
    nr = wait_for(r'대답 없음|도착해서', 30)
    check('대답 없음 → 도착으로', nr)
    played_drive = wait_for(r'메시지 재생', 5, n)
    check('주행 중 재생 없음', not played_drive)
    wiper('Off'); speed(0); time.sleep(2); gear('Park')
    # 11/08 C8 · 11/09: 못 들은 것 하나는 주차해도 저절로 안 틀고 주차 목록에 둔다(화면 [듣기])
    check('주차하면 목록에(자동 재생 없음)', wait_for(r'주차 목록 1개', 20, n) and not wait_for(r'메시지 재생 \(', 3, n))


def c_auto():
    fresh('auto'); hide('지윤', 'rain'); time.sleep(3); drive(); time.sleep(3); wiper('Low')
    check('바로 듣기 → 누르지 않아도 재생', wait_for(r'메시지 재생', 60))


def c_arrive_mode():
    fresh('arrive'); hide('지윤', 'rain'); time.sleep(3); drive(); time.sleep(3); wiper('Low')
    check('주행 집중 모드 → 주행 중 미룸', wait_for(r"주행 집중 모드라 주차해서", 40))
    check('주행 중 재생 없음', not wait_for(r'메시지 재생', 3))
    wiper('Off'); speed(0); time.sleep(2); gear('Park')
    check('주차 때 재생', wait_for(r'메시지 재생', 30))


def c_steer():
    fresh(); hide('지윤', 'rain'); time.sleep(3); drive(); time.sleep(25)  # 출발 안내 뒤 간격(20초) 지나게
    steer(90); time.sleep(1); wiper('Low')
    check('조향 중 → 잠시 후', wait_for(r'잠시 후: .*조향', 20))
    check('조향 중엔 알림 없음', not wait_for(r'버튼 듣기: .* 알림', 3))
    t = time.time(); steer(0)
    a = wait_for(r'버튼 듣기: .* 알림', 15)
    check('직진 3초 뒤 알림', a, f'{round(time.time()-t,1)}초')


def c_signal():
    fresh(); hide('지윤', 'rain'); time.sleep(3); drive(); time.sleep(25)
    # 콘솔은 가속 페달이 0이면 속도가 저절로 줄어든다(11/03 밤 확인: 40 → 3초 뒤 34) → 깜빡이 켜기 직전에 다시 맞춘다
    speed(40); time.sleep(1)
    signal('BlinkLeft'); time.sleep(1); wiper('Low')
    check('달리며 깜빡이 → 잠시 후', wait_for(r'잠시 후: .*(방향|깜빡)', 20))
    speed(0); stopped()
    # 11/08 C10: 서 있어도(신호 대기) 깜빡이가 켜져 있으면 기다린다. 끄고 3초 뒤에 알린다
    check('서 있어도 깜빡이 켜져 있으면 기다림', not wait_for(r'버튼 듣기: .* 알림', 6))
    signal('Off')
    check('깜빡이 끄면 알림', wait_for(r'버튼 듣기: .* 알림', 15))


def c_lot():
    """출발부터 15km/h를 못 넘김 → 기다림, 넘기면 알림"""
    fresh(); hide('지윤', 'rain'); time.sleep(3); drive(10); time.sleep(25); wiper('Low')
    check('15km 전 → 잠시 후', wait_for(r'잠시 후', 20))
    speed(40)
    check('15km 넘으면 알림', wait_for(r'버튼 듣기: .* 알림', 15))


def c_battery():
    fresh(); hide('아내', 'battery'); time.sleep(3); drive(); time.sleep(25); soc(14)
    check('배터리 14% → 순간', wait_for(r'부족 순간', 15))
    check('알림', wait_for(r'버튼 듣기: .* 알림', 20))


def c_home():
    fresh(); hide('엄마', 'home'); time.sleep(3)
    car('sethome', lat=HOME[0], lon=HOME[1]); time.sleep(3)
    drive(); time.sleep(25); geo(*HOME)
    check('집 근처 들어옴', wait_for(r'집 근처 들어옴', 20))
    check('알림', wait_for(r'버튼 듣기: .* 알림', 20))


def c_place():
    fresh(); hide('엄마', 'place', place={"lat": 37.4300, "lon": 127.1000, "name": "학교"}); time.sleep(5)
    drive(); time.sleep(25); geo(37.4300, 127.1000)
    check('고른 장소 근처 들어옴', wait_for(r'학교 근처 들어옴', 20))
    check('알림', wait_for(r'버튼 듣기: .* 알림', 20))


def c_arrive_moment():
    fresh(); hide('아빠', 'arrive'); time.sleep(3); drive(); time.sleep(18); speed(0); time.sleep(1); gear('Park')
    check('주차했을 때 순간 재생', wait_for(r'메시지 재생', 30))


def c_short_park():
    """15초(실제 3분) 안 되게 달리고 주차 → '주차했을 때'로 치지 않음"""
    fresh(); hide('아빠', 'arrive'); time.sleep(3); drive(); time.sleep(5); speed(0); time.sleep(1); gear('Park')
    check('짧게 달리면 주차 순간 아님', not wait_for(r'메시지 재생', 12))


def c_start_parked():
    fresh(); hide('아빠', 'start'); time.sleep(3); car('startp')
    check('출발 전(P) 알림', wait_for(r'출발 전\(P\)', 15))
    time.sleep(6); key()
    check('핸들 버튼 → 재생', wait_for(r'메시지 재생', 15))


def c_start_later():
    """출발 전에 안 들으면 출발한 뒤 그 순간에"""
    fresh(); hide('아빠', 'start'); time.sleep(3); car('startp'); wait_for(r'출발 전\(P\)', 15)
    car('later'); time.sleep(1); drive()
    check('출발 뒤 다시 알림', wait_for(r'버튼 듣기: .* 알림', 60))


def c_depart_announce():
    fresh(); hide('지윤', 'rain'); hide('엄마', 'home'); time.sleep(3); drive()
    a = wait_for(r'안내: "예약된 음성 메시지가 있습니다\."', 20)   # 75번 B-2: 녹음 고정 문장(숫자 없음)
    check('출발 안내(녹음)', a, a[a.find('안내'):][:60] if a else '')


def c_repeat_each():
    fresh(); hide('지윤', 'rain', repeat='each'); time.sleep(3); drive(); time.sleep(3); wiper('Low')
    wait_for(r'버튼 듣기: .* 알림', 60); time.sleep(4); key()
    check('반복 메시지 재생', wait_for(r'메시지 재생 끝', 20))
    wiper('Off'); speed(0); time.sleep(2); gear('Park')
    check('주차 때 계속 들을지 물어봄', wait_for(r'계속 들을지 물어봄', 15))


def c_passenger():
    fresh(); hide('지윤', 'rain'); time.sleep(3)
    seat('rear_left', True)
    check('뒷좌석 착석 → 동승자', wait_for(r'동승자 있음', 8))
    drive(); time.sleep(25); n = nlines(); wiper('Low')
    a = wait_for(r'안내: "음성 메시지가 도착했습니다', 40, n)   # 녹음 고정 문장이라 이름이 원래 없다
    check('동승자 있으면 이름 안 말함', a and '지윤' not in a, a[a.find('안내'):][:50] if a else '')
    seat('rear_left', False)
    check('내리면 혼자 탐', wait_for(r'혼자 탐', 8))


def c_long():
    fresh(); hide('엄마', 'long'); time.sleep(3); drive()
    check('오래 달림(시험은 30초) → 알림', wait_for(r'버튼 듣기: .* 알림', 60))


def c_gap_and_two():
    """비 메시지 두 개 → 한 개 들은 뒤 간격 지켜 다음"""
    fresh('auto'); hide('지윤', 'rain'); hide('엄마', 'rain'); time.sleep(3); drive(); time.sleep(25); wiper('Low')
    first = wait_for(r'메시지 재생 끝', 40)
    check('첫 메시지 재생', first)
    t = time.time(); n = nlines()
    second = wait_for(r'메시지 재생 \(', 40, n)
    check('간격(시험 20초) 지켜 두 번째 재생', second and time.time() - t >= 17, f'{round(time.time()-t)}초 뒤')


def c_same_sender():
    """한 사람이 같은 순간에 두 개 → 이번엔 하나만(돌아가며), 나머지는 주차 때"""
    fresh('auto'); hide('지윤', 'rain'); hide('지윤', 'rain'); time.sleep(3); drive(); time.sleep(25); wiper('Low')
    first = wait_for(r'메시지 재생 끝', 40)
    check('첫 메시지 재생', first)
    n = nlines()
    check('같은 사람 두 번째는 주행 중 안 나옴', not wait_for(r'메시지 재생 \(', 35, n))


def c_close():
    fresh('auto'); hide('지윤', 'rain'); time.sleep(3); car('close'); time.sleep(1); drive(); time.sleep(25); wiper('Low')
    check('앱 닫음 → 이번 운행 재생 안 함', not wait_for(r'메시지 재생', 20))


def c_delete_realtime():
    fresh(); inv = json.loads(req(SRV + '/api/invites', {}))
    code = inv.get('code') or re.search(r'code=(\w+)', json.dumps(inv)).group(1)
    mid = hide('엄마', 'rain', invite=code); time.sleep(3); drive(); time.sleep(5)
    n = nlines()
    req(f'{SRV}/api/messages/{mid}/delete', {'invite': code, 'dev': True})  # 맥 안 시험 도구는 폰 열쇠 확인을 건너뛴다
    check('지우면 차 목록에서 바로 빠짐', wait_for(r'지워진 메시지 빼기|숨겨진 메시지 0개', 15, n))
    wiper('Low')
    check('지운 메시지 안 나옴', not wait_for(r'버튼 듣기: .* 알림', 30, n))


def c_tomorrow():
    fresh('auto'); hide('지윤', 'rain', date='tomorrow'); time.sleep(3); drive(); time.sleep(25); wiper('Low')
    check('내일 날짜 메시지는 오늘 안 나옴', not wait_for(r'메시지 재생', 20))


def c_server_rules():
    """서버: 초대 없이 저장 거절, 끊은 링크 거절"""
    b = {"sender": "x", "date": "today", "moment": "rain", "mime": "audio/mp4", "duration": 3, "repeat": "once",
         "audio": base64.b64encode(open(VOICE, 'rb').read()).decode()}
    try: req(SRV + '/api/messages', b); ok = False
    except urllib.error.HTTPError as e: ok = '초대' in e.read().decode()
    check('초대 링크 없이 남기기 거절', ok)
    inv = json.loads(req(SRV + '/api/invites', {})); code = inv.get('code')
    req(f'{SRV}/api/invites/{code}/revoke', {})
    b['invite'] = code
    try: req(SRV + '/api/messages', b); ok = False
    except urllib.error.HTTPError as e: ok = '초대' in e.read().decode()
    check('끊은 링크로 남기기 거절', ok)


def c_photo_reissue():
    """서버: 차는 자기 초대 링크의 사진만 받는다 · 새 폰으로 다시 연결하면 같은 사람(이름·사진·메시지)이 새 링크로 옮겨 가고 예전 링크는 끊긴다"""
    jpg = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=0x3b82f6:s=64x64', '-frames:v', '1', '-f', 'mjpeg', '-'], capture_output=True).stdout
    def call(path, body=None, hdr=None):
        r = urllib.request.Request(SRV + path, json.dumps(body).encode() if body is not None else None,
                                   {'Content-Type': 'application/json', 'X-Car-Id': 'reg-car', **(hdr or {})})
        try:
            res = urllib.request.urlopen(r, timeout=10); return res.status, res.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
    _, b = call('/api/invites', {'from': '홍길동님'}); code = json.loads(b)['code']
    _, b = call('/api/profile', {'invite': code, 'name': '수진', 'claim': True, 'photo': base64.b64encode(jpg).decode()})
    dev = json.loads(b)['device']
    mid = hide('수진', 'rain', invite=code)
    _, b = call('/api/invites'); inv = next(i for i in json.loads(b)['invites'] if i['code'] == code)
    check('초대 목록에 사진 판 번호', inv.get('photo'))
    _, b = call('/api/messages'); msg = next(m for m in json.loads(b)['messages'] if m['id'] == mid)
    check('메시지에 사진 판 번호', msg.get('photo') == inv['photo'])
    st, b = call(f"/api/car/photo?invite={code}&v={inv['photo']}")
    check('차가 사진 받음', st == 200 and b[:3] == b'\xff\xd8\xff')
    st, _ = call(f"/api/car/photo?invite={code}", hdr={'X-Car-Id': 'other-car'})
    check('다른 차는 사진 못 받음', st == 404)
    st, _ = call(f"/api/car/photo?invite={code}", hdr={'X-Forwarded-For': '1.2.3.4'})
    check('밖에서 열쇠 없이 사진 못 받음', st == 404)
    st, b = call(f'/api/invites/{code}/reissue', {'from': '홍길동'}, hdr={'X-Car-Id': 'other-car'})
    check('다른 차는 다시 연결 못 함', st == 400)
    st, b = call(f'/api/invites/{code}/reissue', {'from': '홍길동'}); new = json.loads(b).get('code')
    check('다시 연결 → 새 코드', st == 200 and new and new != code)
    st, _ = call(f'/api/box?invite={code}', hdr={'X-Device': dev})
    check('예전 링크는 끊김(410)', st == 410)
    st, b = call(f'/api/invite?peek=1&code={new}'); j = json.loads(b)
    check('새 폰이 열면 이름 그대로 바로 잠김', st == 200 and j.get('name') == '수진' and j.get('device') and j.get('photo') and j.get('from') == '홍길동')
    st, b = call(f'/api/box?invite={new}', hdr={'X-Device': j.get('device', '')})
    check('새 폰에서 남긴 메시지가 보임', st == 200 and any(m['id'] == mid for m in json.loads(b)['sent']['upcoming']))
    st, _ = call(f'/api/invite?peek=1&code={new}')
    check('새 링크도 다른 폰은 못 씀', st == 403)
    _, b = call('/api/messages'); msg = next((m for m in json.loads(b)['messages'] if m['id'] == mid), {})
    check('차 메시지가 새 링크로 이어짐', msg.get('invite') == new and msg.get('photo') == inv['photo'])
    # 사진 검수 전(pending)·예전 사진(photo_ok 없음)은 차에 안 나간다
    for state in ('pending', None):
        d = json.load(open(DB))
        x = next(i for i in d['invites'] if i['code'] == new)
        if state: x['photo_ok'] = state
        else: x.pop('photo_ok', None)
        json.dump(d, open(DB, 'w'), ensure_ascii=False)
        _, b = call('/api/invites'); i2 = next(i for i in json.loads(b)['invites'] if i['code'] == new)
        st, _ = call(f"/api/car/photo?invite={new}&v={inv['photo']}")
        check(f'검수 전 사진은 차에 안 감({state or "표시 없음"})', not i2.get('photo') and st == 404)
    call(f'/api/invites/{new}/revoke', {})


# ---------- 광장(자리·대표색·캐릭터) — 서버만 ----------
def api(path, body=None, car=None, hdr=None):
    """서버 요청 하나: (상태 코드, JSON 또는 바이트). car: X-Car-Id."""
    h = {'Content-Type': 'application/json', **({'X-Car-Id': car} if car else {}), **(hdr or {})}
    r = urllib.request.Request(SRV + path, json.dumps(body).encode() if body is not None else None, h)
    try:
        res = urllib.request.urlopen(r, timeout=15); st, b = res.status, res.read()
    except urllib.error.HTTPError as e:
        st, b = e.code, e.read()
    try: return st, json.loads(b)
    except ValueError: return st, b


PARTS_N = {'hair': 21, 'hairColor': 12, 'eyes': 25, 'brows': 10, 'nose': 3, 'mouth': 9, 'wrinkle': 16, 'blush': 2,
           'beard': 5, 'glasses': 4, 'face': 7, 'skin': 7, 'height': 3, 'build': 5, 'beardColor': 12, 'acc': 2,
           'scarfColor': 8, 'glassesColor': 4, 'pantsColor': 5, 'mark': 5, 'beards': 8, 'marks': 128}  # 56번 문서 표 + 11/08 수염색 + 11/09 머리 17·소품·목도리 색(대표색 8) + 11/10 머리색/수염색 희끗한 2
# 11/10 83번: 머리색·수염색 12(애쉬 브라운·적갈색·와인·은발), 얼굴형·체형 5(조금 갸름·조금 각진 / 조금 날씬·조금 듬직), 안경테 색 4·바지 색 5(맨 뒤)
# 11/10 76번: 눈 14·눈썹 9·입 9, 주름 = 비트 합 0~15(1 눈가 2 이마 4 입가 8 눈 밑). 눈 0·3은 고르는 칸에서 숨김
# 11/10 79번: 눈 17(14 무쌍·15 애교살·16 도도한, 고르는 칸 15 = 3×5), 눈썹 10(9 긴 꼬리, 1 아치 숨김 → 7), 코 1 동그란 숨김 → 0
# 11/10 84번: 눈 25(17~24 Mii풍 새 눈), 고르는 칸 18 = 3×6. 2 작은·6 차분한·9 쌍꺼풀·10 고양이·15 애교살은 숨기고 옮김
# 11/10 85번: 얼굴형 7(5 넓은 얼굴·6 넓고 각진, 뒤에만), 고르는 칸은 5단계 뒤에
HIDDEN_EYES = (0, 3, 2, 6, 9, 10, 15)
MOVED_N = {'eyes': {0: 7, 3: 1, 2: 7, 6: 21, 9: 23, 10: 16, 15: 1}, 'brows': {1: 7}, 'nose': {1: 0}}
PICK_N = {'eyes': [7, 1, 17, 18, 23, 14, 11, 22, 19, 12, 20, 16, 21, 8, 24, 13, 5, 4], 'brows': [2, 3, 9, 4, 5, 6, 7, 0, 8], 'nose': [0, 2],
          'mouth': [0, 4, 1, 6, 5, 2, 7, 3, 8], 'wrinkle': [1, 2, 4, 8], 'skin': [0, 5, 1, 2, 6, 3, 4],
          'hairColor': [0, 1, 2, 8, 9, 10, 5, 6, 7, 3, 11, 4], 'build': [0, 3, 1, 4, 2], 'face': [1, 3, 0, 4, 2, 5, 6], 'beards': [1, 2, 4], 'marks': [1, 2, 4, 8, 16, 32, 64]}
# 11/10 81번: 피부 7(5 화사한·6 건강한 뒤에 붙임), 고르는 칸은 밝은 순서. 한국 가족 먼저: 묶음은 밝은·화사한·보통·따뜻한 위주
SKIN_KR = (0, 5, 1, 2)


def avatar_ok(a):
    return isinstance(a, dict) and set(a) == set(PARTS_N) and all(isinstance(a[k], int) and 0 <= a[k] < n for k, n in PARTS_N.items())


def join(car, name, **extra):
    """차가 코드를 만들고 폰이 프로필 [완료](claim)로 들어온다. (코드, 폰 열쇠)"""
    _, j = api('/api/invites', {'from': '홍길동'}, car)
    code = j['code']
    st, j = api('/api/profile', {'invite': code, 'name': name, 'claim': True, **extra})
    return code, (j.get('device') if st == 200 else None), st, j


def c_presets():
    """서버: 프리셋 8(나이대 이름만)·부품 개수·색 8"""
    st, j = api('/api/presets')
    ps = j.get('presets', []) if st == 200 else []
    check('프리셋 8개', len(ps) == 8 and len({p['id'] for p in ps}) == 8)
    labels = [p['label'] for p in ps]
    check('프리셋 이름은 나이대만(관계 호칭 없음)', set(labels) == {'어린이', '청년', '중년', '노년'} and all(labels.count(x) == 2 for x in set(labels))
          and not any(w in json.dumps(j, ensure_ascii=False) for w in ('아들', '딸', '엄마', '아빠', '할머니', '할아버지', '여보')))
    check('프리셋 값이 부품 범위 안', all(avatar_ok(p['avatar']) for p in ps))
    check('부품 개수 = 56번 표 + 76번', st == 200 and {k: len(v) for k, v in j['parts'].items()} == PARTS_N)
    # 76번 B: 이름(뒤에만 붙임·6 이름 바꿈·2 꾹 다문 입), 고르는 칸 순서, 숨긴 눈
    pt = j.get('parts', {})
    check('눈 이름: 예전 0~5 그대로 + 6 차분한 눈 + 새 7~13', pt.get('eyes', [])[:7] == ['동그란 눈', '큰 눈', '작은 눈', '긴 눈', '실눈', '반달눈', '차분한 눈']
          and pt['eyes'][7:] == ['또렷한 눈', '날렵한 눈', '쌍꺼풀 눈', '고양이 눈', '강아지 눈', '속눈썹 눈', '속눈썹 반달눈', '무쌍 눈', '애교살 눈', '도도한 눈',
                                 '왕눈', '아몬드 눈', '눈웃음 눈', '아래 속눈썹 눈', '무심한 눈', '온화한 눈', '진한 쌍꺼풀 눈', '곁눈'],
          str(pt.get('eyes')))
    check('눈썹 9 = 긴 꼬리 눈썹(뒤에 붙임)', pt.get('brows', [])[4:] == ['각진 눈썹', '올라간 눈썹', '순한 눈썹', '가는 눈썹', '동글 눈썹', '긴 꼬리 눈썹'], str(pt.get('brows')))
    check('눈썹·입 이름(입 2 = 꾹 다문 입)', pt.get('brows', [])[:4] == ['짧은 눈썹', '아치 눈썹', '일자 눈썹', '숱 많은 눈썹']
          and pt.get('mouth', [])[:4] == ['미소', '활짝 웃음', '꾹 다문 입', '동그란 입'] and pt['mouth'][8] == '메롱', str(pt.get('mouth')))
    pk = j.get('pick', {})
    check('고르는 칸 순서 = 79번(눈 15·눈썹 9·코 2·입 9·주름 4칸)', pk == PICK_N, str(pk))
    check('고르는 칸 = 숨긴 부품(눈 0·3, 눈썹 1, 코 1)만 빼고 전부', all(sorted(pk.get(k, []) + list(m)) == list(range(PARTS_N[k])) and not set(pk.get(k, [])) & set(m)
          and all(v in pk.get(k, []) for v in m.values()) for k, m in MOVED_N.items()))
    wn = pt.get('wrinkle', [])
    check('주름 이름 16(비트 이름 합)', len(wn) == 16 and wn[:4] == ['없음', '눈가 주름', '이마 주름', '눈가·이마 주름']
          and wn[4] == '입가 주름' and wn[8] == '눈 밑 주름' and wn[15] == '눈가·이마·입가·눈 밑 주름', str(wn[4:9]))
    check('프리셋·묶음에 숨긴 부품(눈 0·3, 아치 눈썹, 동그란 코) 안 씀', not any(p['avatar'][k] in m for p in ps + j.get('pool', []) for k, m in MOVED_N.items()),
          str([(p['id'], k) for p in ps + j.get('pool', []) for k, m in MOVED_N.items() if p['avatar'][k] in m]))
    check('어르신 묶음에 긴 꼬리 눈썹', any(p['avatar']['brows'] == 9 for p in j.get('pool', []) if p['age'] == 'old'))
    check('부품 이름에 낮추는 말 없음', not any(w in json.dumps(pt, ensure_ascii=False) for w in ('못난', '찢어진', '뚱', '대머리', '흐리멍텅')))
    check('대표색 8·머리색 12·피부 7·안경테 4·바지 5', len(j.get('colors', [])) == 8 and len(j.get('hairColors', [])) == 12 and len(j.get('skins', [])) == 7
          and [c['name'] for c in j.get('glassesColors', [])] == pt.get('glassesColor') == ['검정', '갈색 뿔테', '금테', '은테']
          and [c['name'] for c in j.get('pantsColors', [])] == pt.get('pantsColor') == ['청바지 파랑', '베이지', '검정', '회색', '카키']
          and all(c['hex'].startswith('#') and len(c['hex']) == 7 for c in j.get('glassesColors', []) + j.get('pantsColors', [])))
    check('점 5(맨 뒤에 붙임): 없음·눈 밑 점·입가 점·볼 점·주근깨', pt.get('mark') == ['없음', '눈 밑 점', '입가 점', '볼 점', '주근깨'] and list(pt)[-3:] == ['mark', 'beards', 'marks'], str(list(pt)[-3:]))
    # 11/10 사장 '수염·점 여러 개(점은 좌우 하나씩)': 비트 칸 beards(1 짧은·2 콧·4 턱수염)·marks(눈 밑·입가·볼 왼·오, 주근깨)
    check('수염 비트 이름 8·점 비트 이름 128(없음 + 켜진 것 합)', pt.get('beards', [None])[0] == '없음' and pt['beards'][1:5] == ['짧은 수염', '콧수염', '짧은 수염 + 콧수염', '턱수염']
          and pt['beards'][7] == '짧은 수염 + 콧수염 + 턱수염' and [pt['marks'][1 << b] for b in range(7)] == ['눈 밑 점 왼쪽', '눈 밑 점 오른쪽', '입가 점 왼쪽', '입가 점 오른쪽', '볼 점 왼쪽', '볼 점 오른쪽', '주근깨'],
          str(pt.get('beards')))
    pool = {p['id']: p['avatar'] for p in j.get('pool', [])}
    check('예전 칸과 비트 칸이 같은 모습(프리셋·묶음·처음부터)', all(a['beards'] == {0: 0, 1: 1, 2: 2, 3: 4, 4: 3}[a['beard']] and a['marks'] == {0: 0, 1: 1, 2: 4, 3: 16, 4: 64}[a['mark']]
          for a in [p['avatar'] for p in ps] + list(pool.values()) + [j['base']]))
    check('점: 닮은꼴 look_08(young_f1) 눈 밑 점 + 첫 화면 10대 여 주근깨, 다른 사람은 없음', pool.get('young_f1', {}).get('mark') == 1 and pool.get('teen_f1', {}).get('mark') == 4
          and sorted(i for i, a in pool.items() if a.get('mark')) == ['teen_f1', 'young_f1'] and all('mark' in a for a in pool.values())
          and all(p['avatar'].get('mark') == 0 for p in ps) and j.get('base', {}).get('mark') == 0, str({i: a.get('mark') for i, a in pool.items() if a.get('mark')}))
    check('수염 5: 예전 0~3 그대로 + 4 짧은 수염 + 콧수염(뒤에 붙임)', pt.get('beard') == ['없음', '짧은 수염', '콧수염', '긴 수염', '짧은 수염 + 콧수염'], str(pt.get('beard')))
    check('짧은 수염 + 콧수염: 중년 남자 2명(첫 화면 middle_m2·화면 2 middle_m3)만', sorted(i for i, a in pool.items() if a.get('beards') == 3) == ['middle_m2', 'middle_m3'],
          str([i for i, a in pool.items() if a.get('beards') == 3]))
    check('체형 5·얼굴형 7(뒤에 붙임, 예전 0~2 이름 그대로)', pt.get('build') == ['날씬', '보통', '듬직', '조금 날씬', '조금 듬직']
          and pt.get('face') == ['둥근형', '갸름형', '각진형', '조금 갸름', '조금 각진', '넓은 얼굴', '넓고 각진'], str((pt.get('build'), pt.get('face'))))
    sk = j.get('skins', [])
    lum = lambda h: 0.299 * int(h[1:3], 16) + 0.587 * int(h[3:5], 16) + 0.114 * int(h[5:7], 16)
    check('피부 이름(81번)·고르는 칸이 밝은 순서', [c['name'] for c in sk] == ['밝은', '보통', '따뜻한', '구릿빛', '짙은', '화사한', '건강한']
          and all(lum(sk[a]['hex']) > lum(sk[b]['hex']) for a, b in zip(pk.get('skin', []), pk.get('skin', [])[1:])), str(sk)[:200])
    # 11/10 희끗한 검정·희끗한 갈색: 뒤에만 붙임(예전 0~5 그대로), 웹 3D 가닥 무늬 값(salt: 바탕·흰 가닥·비율)
    hc = j.get('hairColors', [])
    check('머리색 희끗한 2개 뒤에 붙음 + 가닥 무늬 값', [c['name'] for c in hc[:6]] == ['검정', '진한 갈색', '밝은 갈색', '회색', '흰색', '금발']
          and [(c['name'], c['hex']) for c in hc[6:8]] == [('희끗한 검정', '#5E5A58'), ('희끗한 갈색', '#7A6F68')]
          and all(len(c['salt']) == 3 and c['salt'][0].startswith('#') and c['salt'][1].startswith('#') and 0 < c['salt'][2] < 1 for c in hc[6:8])
          and not any('salt' in c for c in hc[:6] + hc[8:]) and j['parts']['beardColor'] == j['parts']['hairColor'], str(hc[6:])[:160])
    check('머리색 83번 4개 뒤에 붙음(애쉬 브라운·적갈색·와인·은발)', [c['name'] for c in hc[8:]] == ['애쉬 브라운', '적갈색', '와인', '은발']
          and len({c['hex'] for c in hc}) == 12, str(hc[8:])[:160])
    # 83번(11/10): 닮은 모습 = 4칸 × 4줄(줄 이름 없음), 칸마다 6명 = 96명. who_rows = 줄 → 화면 → 칸 4개 id
    # 1줄 어린이 남·여 + 10대 남·여, 2줄 20~30대, 3줄 40~50대, 4줄 60대 이상, 칸 순서 남·여·남·여
    pool, rows = j.get('pool', []), j.get('who_rows', [])
    pid = {p['id']: p for p in pool}
    check('닮은 모습 4줄 × 화면 6 × 4칸 = 96명·id 겹침 없음·값 범위 안', len(rows) == 4 and all(len(r) == 6 and all(len(g) == 4 for g in r) for r in rows)
          and sorted(i for r in rows for g in r for i in g) == sorted(pid) and len(pid) == len(pool) == 96
          and all(avatar_ok(p['avatar']) for p in pool) and all(0 <= p['color'] < 8 for p in pool), str([len(r) for r in rows]))
    check('[처음부터] 기본형 값(base)도 보냄·범위 안', avatar_ok(j.get('base')), str(j.get('base'))[:120])
    check('줄 이름·나이대 줄 값은 안 보냄(ages·pool_row·label 없음)', 'ages' not in j and 'pool_row' not in j and not any('label' in p for p in pool))
    ag = lambda i: pid[i]['age'] if i in pid else None
    check('1줄 어린이 둘 + 10대 둘, 2줄 20~30대, 3줄 40~50대, 4줄 60대 이상(나이 순)', len(rows) == 4
          and all([ag(i) for i in g] == ['child', 'child', 'teen', 'teen'] for g in rows[0])
          and all(ag(i) == a for r, a in zip(rows[1:], ('young', 'middle', 'old')) for g in r for i in g))
    sys.path.insert(0, os.path.join(HERE, '../server'))
    import avatar as AV   # 성별은 서버 안 메모(안 보냄): 같은 파일로 확인
    check('칸 순서 남·여·남·여', [[list(g) for g in r] for r in AV.WHO_ROWS] == rows
          and all([AV._BY_ID[i]['sex'] for i in g] == ['m', 'f', 'm', 'f'] for r in AV.WHO_ROWS for g in r))
    check('예전 묶음 id(child_3·young_5·middle_12 등)도 받음', all(f'{a}_{n}' in AV._BY_ID for a in ('child', 'young', 'middle', 'old') for n in range(1, 10))
          and all(f'{a}_{n}' in AV._BY_ID for a in ('middle', 'old') for n in (10, 11, 12)))
    gen = subprocess.run([sys.executable, os.path.join(HERE, '../server/who_pool_gen.py'), '--check'], capture_output=True, text=True)
    check('풀은 미리 찍어 둔 값(who_pool_gen.py 로 다시 찍어도 같음)', gen.returncode == 0, gen.stdout.strip() + gen.stderr[-200:])
    by = {a: [p for p in pool if p['age'] == a] for a in ('child', 'teen', 'young', 'middle', 'old')}
    av_ = lambda p, k: p['avatar'][k]
    sx = lambda p: AV._BY_ID[p['id']]['sex']
    pages = [[pid[r[g][c]] for r in rows for c in range(4)] for g in range(6)]   # 화면 g 16명(줄 순서)
    ADULT = ('young', 'middle', 'old')
    # 한 화면 규칙(83번 4장): 웹은 칸마다 같은 차례로 넘기므로 화면 0~5가 실제로 나오는 16명
    for g, pg in enumerate(pages):
        old = [p for p in pg if p['age'] == 'old']
        ad = [p for p in pg if p['age'] in ADULT]
        bad = []
        if sum(av_(p, 'hairColor') in (0, 1) for p in old) != 2: bad.append('어르신 4명 중 염색 2')
        if not 4 <= sum(av_(p, 'glasses') > 0 for p in ad) <= 6: bad.append('성인 12명 중 안경 4~6')
        if sum(av_(p, 'build') == 2 for p in pg if sx(p) == 'f') != 2: bad.append('여자 8명 중 듬직 2')
        if sum(av_(p, 'face') != 0 for p in pg) < 4: bad.append('둥근형 아닌 얼굴 4 이상')
        if not any(av_(p, 'beard') for p in ad if sx(p) == 'm'): bad.append('성인 남자 수염 1 이상')
        if len({av_(p, 'skin') for p in pg}) < 4: bad.append('피부 4가지 이상')
        if len({(av_(p, 'eyes'), av_(p, 'mouth')) for p in pg}) != 16: bad.append('눈+입')
        if any(len({av_(p, 'hair') for p in pg[r * 4:r * 4 + 4]}) != 4 for r in range(4)): bad.append('줄 안 같은 머리')
        if sum(av_(p, 'acc') == 1 for p in pg) != 1: bad.append('목도리 1')
        if sum(av_(p, 'skin') in (3, 4) for p in pg) > (0 if g == 0 else 1): bad.append('구릿빛·짙은')
        check(f'화면 {g}: 염색 어르신 2/4·성인 안경 4~6/12·여자 듬직 2/8·얼굴형 4+·수염 1+·피부 4+·눈+입·줄 머리·목도리 1', not bad, bad)
    tan = sum(av_(p, 'skin') in (3, 4) for pg in pages[1:] for p in pg)
    check('구릿빛·짙은 피부: 첫 화면 0, 뒤 80명 중 3명(약 24명에 1명)', tan == 3 and not any(av_(p, 'skin') in (3, 4) for p in pages[0]), tan)
    f0 = pages[0]
    check('첫 화면에 빈칸 메움(염색 어르신·듬직한 여자·안경 쓴 20~30대 여자·옆머리/민머리 40~50대 남자·숏컷 여자·수염·목도리)',
          any(p['age'] == 'old' and av_(p, 'hairColor') in (0, 1) for p in f0) and any(sx(p) == 'f' and av_(p, 'build') == 2 for p in f0)
          and any(p['age'] == 'young' and sx(p) == 'f' and av_(p, 'glasses') for p in f0)
          and any(p['age'] == 'middle' and sx(p) == 'm' and av_(p, 'hair') in (3, 4) for p in f0)
          and any(sx(p) == 'f' and av_(p, 'hair') == 12 for p in f0) and any(av_(p, 'beard') for p in f0) and any(av_(p, 'acc') for p in f0))
    check('눈+입 조합 96명 전체에서 겹침 없음(칸마다 따로 넘겨도 같은 얼굴 없음)', len({(av_(p, 'eyes'), av_(p, 'mouth')) for p in pool}) == len(pool))
    check('머리색: 금발 없음, 어린이·10대 검정·진한 갈색, 60대 이상은 검정·진한 갈색(염색) 또는 흰·회색·희끗·은발',
          not any(av_(p, 'hairColor') == 5 for p in pool) and all(av_(p, 'hairColor') in (0, 1) for p in by['child'] + by['teen'])
          and all(av_(p, 'hairColor') in (0, 1, 3, 4, 6, 7, 11) for p in by['old']),
          str([(p['id'], av_(p, 'hairColor')) for p in pool if av_(p, 'hairColor') == 5]))
    check('머리: 올백은 풀에 없음, 파마는 40대 이상만, 세운 머리는 건강한 피부·올라간 눈썹과 같이 안 씀', not any(av_(p, 'hair') == 16 for p in pool)
          and not any(av_(p, 'hair') == 13 for p in by['child'] + by['teen'] + by['young'])
          and not any(av_(p, 'hair') == 2 and (av_(p, 'skin') == 6 or av_(p, 'brows') == 5) for p in pool))
    check('풀 안 메모(vibe·want·sex·cell·page)는 안 보냄', not any(k in p for p in pool for k in ('vibe', 'want', 'sex', 'cell', 'page')))
    check('희끗한 머리색을 쓰는 40~50대가 있음', any(p['avatar']['hairColor'] in (6, 7) for p in by.get('middle', [])))
    # 76번 A: 나이가 얼굴로 읽히게. 중년 모두 입가 주름 + 선 하나, 어린이·청년은 주름 없음, 어르신은 주름 셋 이상
    w = lambda p: p['avatar']['wrinkle']
    check('중년: 모두 입가 주름 + 선 하나 더(눈 밑·눈가·이마), 이마는 한 명까지', all(w(p) & 4 and bin(w(p)).count('1') == 2 for p in by.get('middle', []))
          and sum(w(p) & 2 > 0 for p in by.get('middle', [])) <= 1, str([w(p) for p in by.get('middle', [])]))
    check('어린이·10대·20~30대: 주름 없음', all(w(p) == 0 for p in by.get('child', []) + by.get('teen', []) + by.get('young', [])))
    check('어르신: 주름 셋 이상', all(bin(w(p)).count('1') >= 3 for p in by.get('old', [])), str([w(p) for p in by.get('old', [])]))
    check('중년: 큰 눈·왕눈·반달눈 안 씀', not any(p['avatar']['eyes'] in (1, 5, 13, 17) for p in by.get('middle', [])))
    check('풀 96명·프리셋 8은 고르는 칸에 있는 눈만(84번: 숨긴 눈 안 씀)', all(p['avatar']['eyes'] in PICK_N['eyes'] for p in pool + ps),
          str([(p['id'], p['avatar']['eyes']) for p in pool + ps if p['avatar']['eyes'] not in PICK_N['eyes']][:6]))
    first = [pid[i] for r_ in j.get('who_rows', []) for i in r_[0] if i in pid]
    check('첫 화면 16명에 새 눈(17~24) 8가지가 다 나옴(84번)', len(first) == 16 and {p['avatar']['eyes'] for p in first} >= set(range(17, 25)),
          str(sorted({p['avatar']['eyes'] for p in first})))
    # 11/10 다시 찍은 풀: 새 가발이 나이·성별에 맞게, 바가지는 어린이·10대 위주(어른은 가끔)
    hs = lambda h: [(p['age'], sx(p)) for p in pool if av_(p, 'hair') == h]
    check('투블럭 = 10~40대 남·C컬 중단발 = 30~50대 여·웨이브 커트 = 50대 이상 여, 셋 다 3명 이상',
          all(t in (('teen', 'm'), ('young', 'm'), ('middle', 'm')) for t in hs(17)) and all(t in (('young', 'f'), ('middle', 'f')) for t in hs(18))
          and all(t in (('middle', 'f'), ('old', 'f')) for t in hs(19)) and min(len(hs(17)), len(hs(18)), len(hs(19))) >= 3,
          str({h: len(hs(h)) for h in (17, 18, 19)}))
    check('바가지: 어린이·10대가 절반 이상, 어른은 3명까지', len(hs(10)) >= 4 and sum(a in ('child', 'teen') for a, _ in hs(10)) * 2 >= len(hs(10))
          and sum(a in ADULT for a, _ in hs(10)) <= 3, str(hs(10)))
    check('첫 화면에 새 가발(투블럭·C컬 중단발·웨이브 커트)이 다 나옴', {17, 18, 19} <= {av_(p, 'hair') for p in pages[0]})
    import who_pool_gen as GEN   # 닮은꼴 12명(look_01~12): 첫 화면 4명 + 화면 1~5 자리 그대로(누구 참고인지는 코드에 없음)
    fl = [i for i, (w_, _) in enumerate(GEN.FIRST) if w_.startswith('닮은꼴')]
    lk_ok = all(all(av_(pages[pg][r * 4 + c], k) == v for k, v in a.items() if not k.startswith('_')) for (pg, r, c), (_, _, a) in GEN.LOOKS.items())
    check('닮은꼴 12명: 첫 화면 4명 + 뒤 화면 8명(화면마다 1~2명)', len(fl) == 4 and len(GEN.LOOKS) == 8 and lk_ok
          and sorted({pg for pg, _, _ in GEN.LOOKS}) == [1, 2, 3, 4, 5], str(fl))
    mp = {p['id']: p['avatar'] for p in ps}
    check('예전 프리셋도 중년은 입가 주름, 청년은 주름 없음', all(mp[i]['wrinkle'] & 4 for i in ('middle_m', 'middle_f'))
          and all(mp[i]['wrinkle'] == 0 for i in ('young_m', 'young_f', 'child_m', 'child_f')))
    st, _ = api('/api/presets', hdr={'X-Forwarded-For': '1.2.3.4'})
    check('밖에서도 프리셋 받음(폰 웹)', st == 200)


def c_plaza():
    """서버: 캐릭터 검증·저장, 색 겹침 막기, 5명 상한, 자리 배정·끊기면 빔, 자리 바꾸기, 광장에 보낸 사람 정보 없음"""
    car = f'reg-plaza-{int(time.time() * 1000)}'
    other = car + '-other'
    _, pre = api('/api/presets')
    old_f = next(p['avatar'] for p in pre['presets'] if p['id'] == 'old_f')
    people = []   # (코드, 열쇠)
    c0, d0, st, j = join(car, '하나', avatar={'preset': 'old_f'}, color=3)
    check('가입 + 프리셋 캐릭터·고른 색 저장', st == 200 and j.get('avatar') == old_f and j.get('color') == 3, str(j)[:120])
    people.append((c0, d0))
    for n in ('둘', '셋', '넷'):
        c, d, st, j = join(car, n)
        people.append((c, d))
    _, pz = api('/api/plaza', car=car)
    check('자리는 가입 순서대로 1~4', [p['slot'] for p in pz['people']] == [1, 2, 3, 4] and [p['code'] for p in pz['people']] == [c for c, _ in people])
    check('색을 안 고르면 빈 색 중 첫 번째', [p['color'] for p in pz['people']] == [3, 0, 1, 2], str([p['color'] for p in pz['people']]))
    check('기본 캐릭터도 범위 안', all(avatar_ok(p['avatar']) for p in pz['people']))
    check('다음 빈자리 5', pz.get('next_slot') == 5)
    c1, d1 = people[1]
    # 캐릭터 검증: 범위 밖·정수 아님·모르는 프리셋은 거부, 저장값은 그대로
    bad = [{'hair': 21}, {'skin': 7}, {'hairColor': 12}, {'beardColor': 12}, {'glassesColor': 4}, {'pantsColor': 5}, {'pantsColor': -1}, {'face': 7}, {'build': 5}, {'acc': 2}, {'wrinkle': 16}, {'wrinkle': -1}, {'beard': 5}, {'mark': 5}, {'mark': -1}, {'beards': 8}, {'beards': -1}, {'marks': 128}, {'marks': True}, {'eyes': 25}, {'brows': 10}, {'nose': 3}, {'mouth': 9}, {'scarfColor': 8}, {'scarfColor': -1}, {'hair': -1}, {'eyes': '1'}, {'blush': True}, {'skin': 1.0}, {'preset': 'nope'}, [1, 2], 'x']
    res = [api('/api/profile', {'invite': c1, 'avatar': b}, hdr={'X-Device': d1})[0] for b in bad]
    check('캐릭터 범위 밖·잘못된 값 거부(400)', all(r == 400 for r in res), str(res))
    res = [api('/api/profile', {'invite': c1, 'color': b}, hdr={'X-Device': d1})[0] for b in (8, -1, '2', True)]
    check('대표색 범위 밖 거부(400)', all(r == 400 for r in res), str(res))
    st, me = api(f'/api/me?invite={c1}', hdr={'X-Device': d1})
    check('거부된 값은 저장 안 됨', st == 200 and me['avatar'] == pz['people'][1]['avatar'] and me['color'] == 0)
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'hair': 13, 'glasses': 3}}, hdr={'X-Device': d1})
    check('캐릭터 일부만 바꾸기', st == 200 and j['avatar']['hair'] == 13 and j['avatar']['glasses'] == 3
          and {k: v for k, v in j['avatar'].items() if k not in ('hair', 'glasses')} == {k: v for k, v in me['avatar'].items() if k not in ('hair', 'glasses')})
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'acc': 1, 'scarfColor': 6}}, hdr={'X-Device': d1})
    st2, me2 = api(f'/api/me?invite={c1}', hdr={'X-Device': d1})
    check('목도리 + 목도리 색 저장(대표색과 따로)', st == 200 and st2 == 200 and me2['avatar']['acc'] == 1 and me2['avatar']['scarfColor'] == 6
          and me2['color'] == 0)
    # 주름(11/10): 비트 합 0~15. 0 없음·1 눈가·2 이마·3 눈가+이마 뜻 그대로 + 4 입가·8 눈 밑
    ws = (3, 1, 2, 0, 4, 8, 12, 15, 13)
    res = [api('/api/profile', {'invite': c1, 'avatar': {'wrinkle': w}}, hdr={'X-Device': d1}) for w in ws]
    _, me3 = api(f'/api/me?invite={c1}', hdr={'X-Device': d1})
    check('주름 0~15 저장(비트 합)', all(st == 200 and j['avatar']['wrinkle'] == w for (st, j), w in zip(res, ws))
          and me3['avatar']['wrinkle'] == 13, str([r[0] for r in res]))
    # 새 눈·눈썹·입 저장, 숨긴 눈(0·3)을 보내면 비슷한 새 눈으로(0 → 7 또렷한, 3 → 1 큰 눈)
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'eyes': 13, 'brows': 8, 'mouth': 8}}, hdr={'X-Device': d1})
    check('새 눈 13·눈썹 8·입 8 저장', st == 200 and (j['avatar']['eyes'], j['avatar']['brows'], j['avatar']['mouth']) == (13, 8, 8))
    res = [api('/api/profile', {'invite': c1, 'avatar': {'eyes': e}}, hdr={'X-Device': d1}) for e in HIDDEN_EYES]
    check('숨긴 눈은 받을 때 옮김(0 → 7, 3 → 1, 84번 2 → 7·6 → 21·9 → 23·10 → 16·15 → 1)',
          [(st, j['avatar']['eyes']) for st, j in res] == [(200, MOVED_N['eyes'][e]) for e in HIDDEN_EYES], str([(r[0], r[1].get('avatar', {}).get('eyes') if isinstance(r[1], dict) else None) for r in res]))
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'eyes': 16, 'brows': 1, 'nose': 1}}, hdr={'X-Device': d1})
    check('새 눈 16 저장 + 숨긴 눈썹·코는 받을 때 옮김(아치 1 → 7, 동그란 코 1 → 0)', st == 200
          and (j['avatar']['eyes'], j['avatar']['brows'], j['avatar']['nose']) == (16, 7, 0), str(j)[:160])
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'eyes': 24, 'brows': 9, 'nose': 2}}, hdr={'X-Device': d1})
    check('곁눈 24·긴 꼬리 눈썹 9·넓은 코 2 저장', st == 200 and (j['avatar']['eyes'], j['avatar']['brows'], j['avatar']['nose']) == (24, 9, 2))
    res = [api('/api/profile', {'invite': c1, 'avatar': {'eyes': e}}, hdr={'X-Device': d1}) for e in range(17, 25)]
    check('새 눈 17~24 저장(84번)', [(st, j['avatar']['eyes']) for st, j in res] == [(200, e) for e in range(17, 25)], str([r[0] for r in res]))
    # 11/10 희끗한 머리색·수염색 저장, 닮은 모습 묶음 id·예전 프리셋 id 둘 다 받음
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'hairColor': 6, 'beardColor': 7}}, hdr={'X-Device': d1})
    check('희끗한 머리색 6·수염색 7 저장', st == 200 and j['avatar']['hairColor'] == 6 and j['avatar']['beardColor'] == 7, str(j)[:120])
    # 81번: 피부 5 화사한·6 건강한(뒤에 붙임) 저장, 예전 0~4도 그대로
    res = [api('/api/profile', {'invite': c1, 'avatar': {'skin': v}}, hdr={'X-Device': d1}) for v in (5, 6, 4, 0)]
    check('피부 0~6 저장(새 5·6 + 예전 4·0)', [(st, j['avatar']['skin']) for st, j in res] == [(200, 5), (200, 6), (200, 4), (200, 0)], str([r[0] for r in res]))
    m1 = next(p['avatar'] for p in pre['pool'] if p['id'] == 'middle_m1')
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'preset': 'middle_m1'}}, hdr={'X-Device': d1})
    check('닮은 모습 id로 저장', st == 200 and j['avatar'] == m1, str({k: (v, m1.get(k)) for k, v in j.get('avatar', {}).items() if m1.get(k) != v}))
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'preset': 'middle_1'}}, hdr={'X-Device': d1})
    check('예전 묶음 id(middle_1)도 받음', st == 200 and avatar_ok(j.get('avatar')))
    # 83번: 새 칸(머리색 11 은발·안경테 금테·바지 카키·얼굴형 4·체형 3) 저장, 예전 기록(새 칸 없음)은 0으로 채워 그대로 씀
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'hairColor': 11, 'beardColor': 9, 'glasses': 1, 'glassesColor': 2, 'pantsColor': 4, 'face': 4, 'build': 3}}, hdr={'X-Device': d1})
    check('83번 새 값 저장(은발·적갈색 수염·금테·카키 바지·조금 각진·조금 날씬)', st == 200
          and [j['avatar'][k] for k in ('hairColor', 'beardColor', 'glassesColor', 'pantsColor', 'face', 'build')] == [11, 9, 2, 4, 4, 3], str(j)[:200])
    # 85번: 얼굴형 5 넓은 얼굴·6 넓고 각진(뒤에 붙임) 저장
    res = [api('/api/profile', {'invite': c1, 'avatar': {'face': v}}, hdr={'X-Device': d1}) for v in (5, 6, 0)]
    check('얼굴형 5·6 저장(+ 예전 0)', [(st, j['avatar']['face']) for st, j in res] == [(200, 5), (200, 6), (200, 0)], str([r[0] for r in res]))
    sys.path.insert(0, os.path.join(HERE, '../server'))
    import avatar as AV
    oldrec = {k: v for k, v in AV.default_avatar().items() if k not in ('glassesColor', 'pantsColor')}
    check('예전 기록(안경테·바지 색 없음)은 0으로 채워 온전(기본값으로 안 덮임)', not AV.valid(oldrec) and AV.upgrade(oldrec) and AV.valid(oldrec)
          and oldrec['glassesColor'] == 0 and oldrec['pantsColor'] == 0)
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'beard': 4, 'beardColor': 3}}, hdr={'X-Device': d1})
    check('예전 화면이 보낸 수염 4 → 비트 3(짧은 수염 + 콧수염)·수염색 저장', st == 200 and j['avatar']['beard'] == 4 and j['avatar']['beards'] == 3 and j['avatar']['beardColor'] == 3, str(j)[:120])
    res = [api('/api/profile', {'invite': c1, 'avatar': {'beards': v, 'beard': 0}}, hdr={'X-Device': d1}) for v in (6, 7, 5, 4, 0)]
    # 11/10 사장 '콧수염과 턱수염 두 개는 같이 되는 이유가 없어': 둘 다 보내면 턱수염만(턱수염 3D 에 콧수염이 붙어 있다). 짧은 수염은 어느 쪽과도
    check('수염 비트 저장: 콧수염 + 턱수염은 턱수염만, 짧은 수염은 같이, 예전 칸은 맞춰 둠(비트가 정본)', [(st, j['avatar']['beards'], j['avatar']['beard']) for st, j in res]
          == [(200, 4, 3), (200, 5, 3), (200, 5, 3), (200, 4, 3), (200, 0, 0)], str([(r[0], r[1].get('avatar', {}).get('beards')) for r in res]))
    res = [api('/api/profile', {'invite': c1, 'avatar': {'beards': v}}, hdr={'X-Device': d1}) for v in (3, 2, 1)]
    check('짧은 수염 + 콧수염은 그대로 저장', [(st, j['avatar']['beards'], j['avatar']['beard']) for st, j in res] == [(200, 3, 4), (200, 2, 2), (200, 1, 1)],
          str([r[0] for r in res]))
    oldrec = AV.default_avatar(); oldrec.update(beards=6, beard=3)
    oldrec2 = AV.default_avatar(); oldrec2.update(beards=7, beard=3)
    check('예전 기록 콧수염 + 턱수염 → 읽을 때 턱수염만(짧은 수염은 남김)', AV.upgrade(oldrec) and oldrec['beards'] == 4 and oldrec['beard'] == 3
          and AV.upgrade(oldrec2) and oldrec2['beards'] == 5 and not AV.upgrade(oldrec2) and AV.valid(oldrec2))
    check('같이 안 되는 수염 묶음(catalog one_of: 콧수염 2·턱수염 4)', pre.get('one_of') == {'beards': [6]}, str(pre.get('one_of')))
    check('풀·프리셋·기본형에 콧수염 + 턱수염 같이 켠 사람 없음', not [p['id'] for p in pre['presets'] + pre['pool'] if p['avatar']['beards'] & 6 == 6] and pre['base']['beards'] & 6 != 6)
    res = [api('/api/profile', {'invite': c1, 'avatar': {'marks': v}}, hdr={'X-Device': d1}) for v in (2 | 8, 32 | 64, 127)]
    check('점 비트 저장(좌우·여러 개), 예전 칸은 첫 종류', [(st, j['avatar']['marks'], j['avatar']['mark']) for st, j in res] == [(200, 10, 1), (200, 96, 3), (200, 127, 1)],
          str([r[0] for r in res]))
    res = [api('/api/profile', {'invite': c1, 'avatar': {'mark': v}}, hdr={'X-Device': d1}) for v in (1, 2, 3, 4, 0)]
    check('예전 점 0~4 저장 → 같은 모습 비트(예전 점은 왼쪽)', [(st, j['avatar']['mark'], j['avatar']['marks']) for st, j in res] == [(200, 1, 1), (200, 2, 4), (200, 3, 16), (200, 4, 64), (200, 0, 0)],
          str([r[0] for r in res]))
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'mark': 5}}, hdr={'X-Device': d1})
    check('점 범위 밖(5)은 거절', st == 400)
    oldrec = {k: v for k, v in AV.default_avatar().items() if k != 'mark'}
    check('예전 기록(점 없음)은 0 없음으로 채워 온전', not AV.valid(oldrec) and AV.upgrade(oldrec) and AV.valid(oldrec) and oldrec['mark'] == 0)
    oldrec = {k: v for k, v in AV.default_avatar().items() if k not in ('beards', 'marks')}; oldrec.update(beard=3, mark=2)
    check('예전 기록(비트 칸 없음): 긴 수염 → 턱수염 4, 입가 점 → 입가 점 왼쪽 4', not AV.valid(oldrec) and AV.upgrade(oldrec) and AV.valid(oldrec)
          and oldrec['beards'] == 4 and oldrec['marks'] == 4)
    st, j = api('/api/profile', {'invite': c1, 'avatar': {'preset': 'middle_m'}}, hdr={'X-Device': d1})
    check('예전 프리셋 id도 그대로', st == 200 and j['avatar'] == next(p['avatar'] for p in pre['presets'] if p['id'] == 'middle_m'))
    # 색 겹침
    st, j = api('/api/profile', {'invite': c1, 'color': 3}, hdr={'X-Device': d1})
    check('같은 차에서 쓰는 색은 못 고름', st == 400 and '색' in j.get('error', ''))
    st, j = api('/api/profile', {'invite': c1, 'color': 7}, hdr={'X-Device': d1})
    check('빈 색으로 바꾸기', st == 200 and j['color'] == 7)
    st, me = api(f'/api/me?invite={c1}', hdr={'X-Device': d1})
    check('폰: 내 캐릭터·색 + 쓰인 색 목록(이름 없음)', st == 200 and me['color'] == 7 and me['used_colors'] == [1, 2, 3]
          and set(me) == {'ok', 'name', 'avatar', 'color', 'used_colors'} and me['name'] == '둘')
    st, _ = api(f'/api/me?invite={c1}')
    check('폰: 열쇠 없으면 내 정보 못 봄', st == 403)
    # 다른 차는 색이 따로
    co, do, st, j = join(other, '남', color=3)
    check('다른 차는 같은 색 써도 됨', st == 200 and j.get('color') == 3)
    # 5번째·6번째: 코드는 4명일 때 미리 둘 만든다
    _, j = api('/api/invites', {}, car); c5 = j['code']
    _, j = api('/api/invites', {}, car); c6 = j['code']
    st, j = api(f'/api/invite?peek=1&code={c5}')
    check('가입 전 화면: 쓰인 색 번호만·자리 남음', st == 200 and j.get('open') and sorted(j.get('used_colors', [])) == [1, 2, 3, 7] and j.get('full') is False
          and 'name' not in j)
    st, j = api('/api/profile', {'invite': c5, 'name': '다섯', 'claim': True, 'color': 1})
    st2, j2 = api(f'/api/invite?peek=1&code={c5}')
    check('가입 때 쓰인 색 고르면 거부, 링크도 안 잠김', st == 400 and st2 == 200 and j2.get('open'))
    st, j = api('/api/profile', {'invite': c5, 'name': '다섯', 'claim': True, 'color': 4})
    check('5번째 가입', st == 200 and j.get('color') == 4)
    people.append((c5, j.get('device')))
    _, pz = api('/api/plaza', car=car)
    check('5명 다 참: 자리 1~5, 빈자리 없음', [p['slot'] for p in pz['people']] == [1, 2, 3, 4, 5] and pz['next_slot'] is None)
    st, j = api('/api/profile', {'invite': c6, 'name': '여섯', 'claim': True})
    check('6번째 가입 막힘', st == 400 and '5명' in j.get('error', ''))
    st, j = api(f'/api/invite?peek=1&code={c6}')
    check('6번째 코드: 가입 전 화면에 꽉 참 표시', st == 200 and j.get('full') is True)
    st, j = api('/api/invite?code=' + c6)   # 열 때 잠그는 옛 웹 흐름도 막힌다
    check('옛 웹 흐름도 6번째 막힘', st == 400)
    st, j = api('/api/invites', {}, car)
    check('5명이면 차가 새 코드 못 만듦', st == 400)
    # 광장에 보낸 사람 정보 없음: 메시지 전후로 사람 칸이 똑같고 대기 개수만 바뀐다
    _, before = api('/api/plaza', car=car)
    c2, d2 = people[2]
    b = {"invite": c2, "date": "today", "moment": "rain", "mime": "audio/mp4", "repeat": "once",
         "audio": base64.b64encode(open(VOICE, 'rb').read()).decode()}
    st, j = api('/api/messages', b, hdr={'X-Device': d2})
    mid = j.get('id')
    _, after = api('/api/plaza', car=car)
    check('메시지 남김(셋)', st == 200 and mid, str(j)[:100])
    check('광장 사람 칸은 메시지 전후 똑같음', before['people'] == after['people'])
    check('대기 개수만 늘어남', after['pending'] == before['pending'] + 1, f"{before['pending']}→{after['pending']}")
    txt = json.dumps(after, ensure_ascii=False)
    check('광장 응답에 메시지·보낸 사람 값 없음', mid not in txt and all(set(p) == {'slot', 'code', 'name', 'color', 'avatar'} for p in after['people'])
          and set(after) == {'people', 'pending', 'next_slot', 'max'} and 'sender' not in txt and 'audio' not in txt)
    _, msgs = api('/api/messages', car=car)
    check('차 메시지에는 invite가 있어 도착 장면이 사람을 찾음', any(m['id'] == mid and m.get('invite') == c2 for m in msgs['messages']))
    st, _ = api('/api/plaza', car=car, hdr={'X-Forwarded-For': '1.2.3.4'})
    check('밖에서 차 열쇠 없이 광장 못 봄', st == 404)
    # 끊기면 자리는 비고 다른 사람은 그대로
    api(f'/api/invites/{c2}/revoke', {}, car)
    _, pz = api('/api/plaza', car=car)
    check('끊긴 사람 자리는 빔(당기지 않음)', [p['slot'] for p in pz['people']] == [1, 2, 4, 5] and pz['next_slot'] == 3
          and c2 not in [p['code'] for p in pz['people']])
    st, j = api('/api/profile', {'invite': c6, 'name': '여섯', 'claim': True, 'color': 1})
    check('빈 자리에 새 사람: 가장 왼쪽 빈 번호 + 끊긴 사람 색 다시 씀', st == 200 and j.get('color') == 1)
    _, pz = api('/api/plaza', car=car)
    check('새 사람은 3번 자리', next((p['slot'] for p in pz['people'] if p['code'] == c6), None) == 3)
    # 탈퇴도 자리를 비운다
    c4, d4 = people[3]
    api('/api/leave', {'invite': c4}, hdr={'X-Device': d4})
    _, pz = api('/api/plaza', car=car)
    check('탈퇴하면 자리 빔', [p['slot'] for p in pz['people']] == [1, 2, 3, 5] and pz['next_slot'] == 4)
    # 자리 바꾸기
    st, j = api('/api/plaza/order', {'slots': {c0: 2, c1: 1}}, car)
    check('자리 맞바꾸기 저장', st == 200 and [p['code'] for p in j['people']][:2] == [c1, c0])
    _, pz = api('/api/plaza', car=car)
    check('바꾼 자리가 다시 받아도 그대로', [p['code'] for p in pz['people']][:2] == [c1, c0])
    res = [api('/api/plaza/order', s, car)[0] for s in ({'slots': {c0: 1}}, {'slots': {c0: 6}}, {'slots': {c0: 0}},
                                                         {'slots': {'999999': 1}}, {'slots': {c0: '1'}}, {'slots': {}}, {})]
    check('겹침·범위 밖·모르는 코드는 거부', all(r == 400 for r in res), str(res))
    st, _ = api('/api/plaza/order', {'slots': {c0: 1, c1: 2}}, other)
    check('다른 차는 자리 못 바꿈', st == 400)
    st, j = api('/api/plaza/order', {'slots': {c0: 4}}, car)
    check('빈자리로 옮기기', st == 200 and next(p['slot'] for p in j['people'] if p['code'] == c0) == 4 and j['next_slot'] == 2)
    # 다시 연결: 같은 사람이라 자리·색·캐릭터 그대로
    _, pz = api('/api/plaza', car=car)
    was = next(p for p in pz['people'] if p['code'] == c0)
    st, j = api(f'/api/invites/{c0}/reissue', {'from': '홍길동'}, car); nc = j.get('code')
    _, pz = api('/api/plaza', car=car)
    now = next((p for p in pz['people'] if p['code'] == nc), {})
    check('다시 연결해도 자리·색·캐릭터 그대로', st == 200 and {k: now.get(k) for k in ('slot', 'color', 'avatar', 'name')} ==
          {k: was[k] for k in ('slot', 'color', 'avatar', 'name')} and c0 not in [p['code'] for p in pz['people']])
    # 예전 기록 채우기: 자리·색·캐릭터 없는 옛 사람 → 가입 순서대로, 두 번 받아도 같음, 저장 뒤에도 같음
    legacy = car + '-legacy'
    d = json.load(open(DB))
    for k, t in enumerate((300, 100, 200)):
        d['invites'].append({'code': f'L{t}{k}{int(time.time()) % 1000}', 'created': t, 'claimed': t, 'car': legacy,
                             'name': f'옛{t}', 'device_hash': 'x' * 64})
    json.dump(d, open(DB, 'w'), ensure_ascii=False)
    _, v1 = api('/api/plaza', car=legacy)
    _, v2 = api('/api/plaza', car=legacy)
    check('옛 기록: 가입 순서대로 자리·색 채움', [p['name'] for p in v1['people']] == ['옛100', '옛200', '옛300']
          and [p['slot'] for p in v1['people']] == [1, 2, 3] and [p['color'] for p in v1['people']] == [0, 1, 2]
          and all(avatar_ok(p['avatar']) for p in v1['people']))
    check('옛 기록 채우기는 두 번 해도 같음', v1 == v2)
    api('/api/invites', {}, legacy)   # 저장이 한 번 일어나게
    saved = {i['code']: i for i in json.load(open(DB))['invites'] if i.get('car') == legacy}
    _, v3 = api('/api/plaza', car=legacy)
    check('저장 뒤에도 같은 값', v3['people'] == v1['people'] and all(saved[p['code']].get('slot') == p['slot'] for p in v1['people']))
    # 목도리 색이 없던 때 저장된 캐릭터: 고른 모습 그대로 + 목도리 색만 분홍(1)으로 채움
    oldav = {k: 0 for k in PARTS_N if k != 'scarfColor'}; oldav.update(hair=6, acc=1, skin=2)
    lc = f'S{int(time.time() * 1000) % 100000}'
    d = json.load(open(DB))
    d['invites'].append({'code': lc, 'created': 400, 'claimed': 400, 'car': legacy, 'name': '옛목도리', 'device_hash': 'x' * 64,
                         'slot': 4, 'color': 5, 'avatar': dict(oldav)})
    json.dump(d, open(DB, 'w'), ensure_ascii=False)
    _, v4 = api('/api/plaza', car=legacy)
    op = next((p for p in v4['people'] if p['code'] == lc), {})
    # 예전 눈 0(동그란 눈)은 읽을 때 7(또렷한 눈)로 옮긴다(76번 B)
    check('옛 캐릭터(목도리 색 없음): 모습 그대로 + 목도리 색 분홍(눈 0 → 7)', op.get('avatar') == {**oldav, 'scarfColor': 1, 'eyes': 7}, str(op.get('avatar'))[:160])
    # 숨긴 눈 3(긴 눈)으로 저장된 사람: 기록은 그대로 valid(기본값으로 안 덮임), 읽을 때 1(큰 눈)로. 다른 칸(주름 13 등)은 그대로
    eav = {**{k: 0 for k in PARTS_N}, 'hair': 5, 'eyes': 3, 'brows': 1, 'nose': 1, 'mouth': 7, 'wrinkle': 13, 'skin': 3, 'scarfColor': 1}
    ec = f'E{int(time.time() * 1000) % 100000}'
    d = json.load(open(DB))
    d['invites'].append({'code': ec, 'created': 410, 'claimed': 410, 'car': legacy, 'name': '옛긴눈', 'device_hash': 'x' * 64,
                         'slot': 5, 'color': 6, 'avatar': dict(eav)})
    json.dump(d, open(DB, 'w'), ensure_ascii=False)
    _, v5 = api('/api/plaza', car=legacy)
    ep = next((p for p in v5['people'] if p['code'] == ec), {})
    check('옛 캐릭터(눈 3·아치 눈썹·동그란 코): 눈 1·눈썹 7·코 0으로, 나머지 그대로', ep.get('avatar') == {**eav, 'eyes': 1, 'brows': 7, 'nose': 0}, str(ep.get('avatar'))[:160])
    api(f'/api/invites/{lc}/revoke', {}, legacy)
    api(f'/api/invites/{ec}/revoke', {}, legacy)
    for c in [nc, c1, c5, c6, co] + [p['code'] for p in v3['people']]:   # 시험 사람 정리
        api(f'/api/invites/{c}/revoke', {}, legacy if c.startswith('L') else (other if c == co else car))


def voice_msg(code, key, moment='rain'):
    b = {"invite": code, "date": "today", "moment": moment, "mime": "audio/mp4", "repeat": "once",
         "audio": base64.b64encode(open(VOICE, 'rb').read()).decode()}
    return api('/api/messages', b, hdr={'X-Device': key} if key else None)


def c_together():
    """서버: 함께 쓰는 사람(만 14세 미만) — 보호자 동의로 추가, 5명 상한, 보호자 열쇠로만 남기기·보관함, 광장에 나옴, 보호자 탈퇴·끊기면 같이 정리"""
    car = f'reg-kid-{int(time.time() * 1000)}'
    g, dg, st, j = join(car, '보호')
    base = {'invite': g, 'name': '지우', 'avatar': {'preset': 'child_f'}, 'color': 5}
    st, j = api('/api/together', base, hdr={'X-Device': dg})
    check('보호자 동의 없으면 추가 안 됨', st == 400 and '동의' in j.get('error', ''), str(j)[:80])
    st, j = api('/api/together', {**base, 'consent': True})
    check('보호자 폰 열쇠 없으면 추가 안 됨', st == 403)
    st, j = api('/api/together', {**base, 'consent': True}, hdr={'X-Device': dg})
    kid = j.get('code')
    check('함께 쓰는 사람 추가: 이름·캐릭터·색 따로', st == 200 and kid and kid != g and j.get('name') == '지우' and j.get('color') == 5
          and avatar_ok(j.get('avatar')) and [k['code'] for k in j.get('together', [])] == [kid], str(j)[:120])
    rec = next(i for i in json.load(open(DB))['invites'] if i['code'] == kid)
    check('보호자 코드·동의 시각 기록', rec.get('guardian') == g and isinstance(rec.get('consent'), int) and abs(rec['consent'] - time.time()) < 60)
    check('보호자 동의 문구 판·항목 기록', isinstance(rec.get('consent_v'), str) and rec['consent_v'] and set(rec.get('consent_items') or []) == {'name', 'voice', 'character'}, str({k: rec.get(k) for k in ('consent_v', 'consent_items')}))
    st, j = api('/api/together', {**base, 'name': '하늘', 'consent': True}, hdr={'X-Device': dg})
    check('같은 차에서 쓰는 색은 못 고름', st == 400 and '색' in j.get('error', ''))
    st, j = api('/api/together', {**base, 'invite': kid, 'name': '또', 'color': None, 'consent': True}, hdr={'X-Device': dg})
    check('함께 쓰는 사람이 또 추가하지 못함', st == 400)
    _, pz = api('/api/plaza', car=car)
    kp = next((p for p in pz['people'] if p['code'] == kid), None)
    check('광장에 그 사람이 따로 앉음(자리 2·색 5)', kp and kp['slot'] == 2 and kp['color'] == 5 and kp['name'] == '지우' and avatar_ok(kp['avatar']))
    st, j = api(f'/api/invite?peek=1&code={g}', hdr={'X-Device': dg})
    check('보호자 웹이 함께 쓰는 사람 목록을 받음', st == 200 and [k['code'] for k in j.get('together', [])] == [kid])
    # 다른 폰은 그 사람 코드를 열거나 잠그지 못함
    st, _ = api(f'/api/invite?peek=1&code={kid}')
    st2, _ = api('/api/profile', {'invite': kid, 'name': '남', 'claim': True, 'device': 'A' * 32})
    check('다른 폰은 함께 쓰는 사람 코드를 못 씀', st == 403 and st2 == 403, f'{st} {st2}')
    # 남기기: 보호자 열쇠로만, 그 사람 이름으로, 차 메시지에 그 사람 코드
    st, _ = voice_msg(kid, None)
    check('열쇠 없이 그 사람으로 남기기 거절', st == 403)
    st, j = voice_msg(kid, dg); mid = j.get('id')
    check('보호자 폰에서 그 사람으로 남김', st == 200 and mid, str(j)[:80])
    _, msgs = api('/api/messages', car=car)
    m = next((x for x in msgs['messages'] if x['id'] == mid), {})
    check('차 메시지: 그 사람 코드·이름(차가 그 사람 캐릭터를 찾음)', m.get('invite') == kid and m.get('sender') == '지우')
    st, b = api(f'/api/box?invite={kid}', hdr={'X-Device': dg})
    st2, b2 = api(f'/api/box?invite={g}', hdr={'X-Device': dg})
    check('그 사람 보관함은 보호자 열쇠로 봄(보호자 보관함과 따로)', st == 200 and any(x['id'] == mid for x in b['sent']['upcoming'])
          and st2 == 200 and not any(x['id'] == mid for x in b2['sent']['upcoming']))
    st, _ = api(f'/api/box?invite={kid}')
    check('열쇠 없이 그 사람 보관함 못 봄', st == 403)
    st, j = api('/api/profile', {'invite': kid, 'avatar': {'hair': 2}}, hdr={'X-Device': dg})
    check('보호자 폰에서 그 사람 캐릭터 바꾸기', st == 200 and j['avatar']['hair'] == 2)
    # 5명 상한: 보호자·지우 + 둘 + 함께 쓰는 사람 하나 = 5
    join(car, '셋'); join(car, '넷')
    st, j = api('/api/together', {'invite': g, 'name': '다섯', 'consent': True}, hdr={'X-Device': dg})
    k5 = j.get('code')
    check('함께 쓰는 사람도 5명 안에서 추가', st == 200 and k5)
    st, j = api('/api/together', {'invite': g, 'name': '여섯', 'consent': True}, hdr={'X-Device': dg})
    check('6번째는 함께 쓰는 사람도 막힘', st == 400 and '5명' in j.get('error', ''))
    # 보호자 탈퇴: 함께 쓰는 사람도 끊기고 메시지까지 지움
    api('/api/leave', {'invite': g}, hdr={'X-Device': dg})
    _, pz = api('/api/plaza', car=car)
    st, _ = api(f'/api/box?invite={kid}', hdr={'X-Device': dg})
    _, msgs = api('/api/messages', car=car)
    d = {i['code']: i for i in json.load(open(DB))['invites']}
    check('보호자 탈퇴 → 함께 쓰는 사람도 광장에서 빠지고 끊김', not ({kid, k5} & {p['code'] for p in pz['people']}) and st == 410
          and d[kid].get('revoked') and not d[kid].get('name') and not d[kid].get('device_hash'))
    check('보호자 탈퇴 → 함께 쓰는 사람 메시지도 지움', not any(x['id'] == mid for x in msgs['messages'])
          and not any(x['id'] == mid for x in json.load(open(DB))['messages']))
    # 차가 보호자를 끊어도 같이 끊긴다
    g2, dg2, _, _ = join(car, '보호둘')
    _, j = api('/api/together', {'invite': g2, 'name': '봄', 'consent': True}, hdr={'X-Device': dg2}); k2 = j.get('code')
    api(f'/api/invites/{g2}/revoke', {}, car)
    _, pz = api('/api/plaza', car=car)
    r2 = next((i for i in json.load(open(DB))['invites'] if i['code'] == k2), {})
    check('차가 보호자를 끊으면 함께 쓰는 사람도 끊김', bool(k2) and k2 not in {p['code'] for p in pz['people']} and bool(r2.get('revoked')) and not r2.get('name'))
    # 보호자가 폰을 바꿔 다시 연결: 함께 쓰는 사람도 새 폰을 따라간다(예전 폰은 못 씀)
    g3, dg3, _, _ = join(car, '보호셋')
    _, j = api('/api/together', {'invite': g3, 'name': '여름', 'consent': True}, hdr={'X-Device': dg3}); k3 = j.get('code')
    _, j = api(f'/api/invites/{g3}/reissue', {'from': '홍길동'}, car); n3 = j.get('code')
    nk = 'N' * 32
    st, j = api(f'/api/invite?peek=1&code={n3}', hdr={'X-Device': nk})
    st1, _ = voice_msg(k3, nk)
    st2, _ = voice_msg(k3, dg3)
    check('보호자 다시 연결 → 함께 쓰는 사람도 새 폰으로', st == 200 and [k['code'] for k in j.get('together', [])] == [k3] and st1 == 200 and st2 == 403, f'{st} {st1} {st2}')
    _, pz = api('/api/plaza', car=car)
    for c in [p['code'] for p in pz['people']]:
        api(f'/api/invites/{c}/revoke', {}, car)


def c_reactions():
    """서버: 차 반응(이모티콘 5개 중 하나) — 그 차에 온 메시지만, 5개 밖은 거부, 다른 걸 고르면 바뀜, 같은 걸 두 번 눌러도 알림 한 번"""
    HEART, LIKE, LOL, WOW, SAD = '\u2764\ufe0f', '\U0001F44D', '\U0001F602', '\U0001F62E', '\U0001F622'
    car = f'reg-react-{int(time.time() * 1000)}'
    c, d, _, _ = join(car, '반응')
    st, j = voice_msg(c, d); mid = j.get('id')
    st, j = api('/api/reactions', {'message_id': mid, 'emoji': HEART}, car + '-other')
    check('다른 차 메시지엔 반응 못 누름', st == 410)
    st, j = api('/api/reactions', {'message_id': mid, 'emoji': HEART}, hdr={'X-Forwarded-For': '1.2.3.4', 'X-Car-Id': car})
    check('밖에서 차 열쇠 없이 반응 못 누름', st == 404)
    bad = [api('/api/reactions', {'message_id': mid, **e}, car)[0] for e in ({}, {'emoji': '🔥'}, {'emoji': '잘 들었습니다'}, {'emoji': 1}, {'emoji': HEART + LIKE})]
    check('5개 밖의 반응은 거부(400)', bad == [400] * 5, str(bad))
    _, b = api(f'/api/box?invite={c}', hdr={'X-Device': d})
    check('누르기 전엔 보관함에 반응 없음', b['sent']['upcoming'][0].get('reaction') is None)
    st, j = api('/api/reactions', {'message_id': mid, 'emoji': HEART}, car)
    st2, j2 = api('/api/reactions', {'message_id': mid, 'emoji': HEART}, car)
    check('반응 저장, 같은 걸 두 번 눌러도 알림 한 번', st == 200 and j.get('new') is True and j.get('notify') is True
          and st2 == 200 and j2.get('new') is False and j2.get('notify') is False and j2.get('reaction') == j.get('reaction')
          and j['reaction'].get('emoji') == HEART)
    _, b = api(f'/api/box?invite={c}', hdr={'X-Device': d})
    m = next(x for x in b['sent']['upcoming'] if x['id'] == mid)
    check('보낸 사람 보관함에 반응(이모티콘·날짜만)', m.get('reaction') == {'emoji': HEART, 'day': time.strftime('%Y-%m-%d')})
    st, j = api('/api/reactions', {'message_id': mid, 'emoji': LOL}, car)
    st2, j2 = api('/api/reactions', {'message_id': mid, 'emoji': LOL}, car)
    check('다른 걸 고르면 바뀌고 알림, 다시 같은 건 알림 없음', st == 200 and j.get('changed') is True and j.get('notify') is True
          and j['reaction'].get('emoji') == LOL and st2 == 200 and j2.get('notify') is False)
    _, b = api(f'/api/box?invite={c}', hdr={'X-Device': d})
    m = next(x for x in b['sent']['upcoming'] if x['id'] == mid)
    check('바꾼 반응이 보관함에 하나만', m.get('reaction', {}).get('emoji') == LOL)
    st, j = api('/api/reactions', {'message_id': mid, 'emoji': '\u2764'}, car)
    check('FE0F 없는 하트도 같은 하트로', st == 200 and j['reaction'].get('emoji') == HEART)
    _, msgs = api('/api/messages', car=car)
    check('차 메시지에도 반응 이모티콘', any(x['id'] == mid and (x.get('reaction') or {}).get('emoji') == HEART for x in msgs['messages']))
    # 예전 값(시각 숫자뿐)은 ❤️로 읽는다
    db = json.load(open(DB))
    for x in db['messages']:
        if x['id'] == mid: x['reaction'] = int(time.time())
    json.dump(db, open(DB + '.reg', 'w'), ensure_ascii=False, indent=1); os.replace(DB + '.reg', DB)
    _, b = api(f'/api/box?invite={c}', hdr={'X-Device': d})
    m = next(x for x in b['sent']['upcoming'] if x['id'] == mid)
    st, j = api('/api/reactions', {'message_id': mid, 'emoji': HEART}, car)
    check('예전 반응(시각만)은 ❤️로 읽고, 같은 ❤️는 알림 없음', (m.get('reaction') or {}).get('emoji') == HEART and st == 200 and j.get('notify') is False)
    st, j = api('/api/reactions', {'message_id': mid, 'emoji': SAD}, car)
    check('예전 반응에서 다른 걸 고르면 바뀜', st == 200 and j.get('changed') is True and j['reaction'].get('emoji') == SAD)
    st, _ = api('/api/reactions', {'message_id': 'nope', 'emoji': LIKE}, car)
    check('없는 메시지엔 반응 못 누름', st == 410)
    api(f'/api/invites/{c}/revoke', {}, car)


def c_web_files():
    """서버: 예시 듣기 목소리 6개·초대장 광장 그림·대표색 8번(남색)"""
    for k in ('start', 'arrive', 'home', 'rain', 'long', 'battery'):
        st, b = api(f'/ex/demo_{k}.m4a')
        check(f'예시 목소리 {k}', st == 200 and isinstance(b, bytes) and len(b) > 1000)
    st, b = api('/hello-plaza.jpg', hdr={'X-Forwarded-For': '1.2.3.4'})
    check('초대장 광장 그림(밖에서도)', st == 200 and b[:3] == b'\xff\xd8\xff')
    _, j = api('/api/presets')
    check('대표색 8번 = 남색', j['colors'][7] == {'name': '남색', 'hex': '#3F5BA9'})
    check('예전 얼굴 그리기 규칙(face_spec)도 그대로', isinstance(j.get('face_spec'), dict) and 'eyes' in j['face_spec'])
    st, b = api('/avatar/char.glb', hdr={'X-Forwarded-For': '1.2.3.4'})
    check('웹 캐릭터 모델(밖에서도)', st == 200 and isinstance(b, bytes) and b[:4] == b'glTF')
    if isinstance(b, bytes) and b[:4] == b'glTF':   # 85번: 넓은 얼굴 모프(face_full)가 몸·얼굴 조각·가발 20개(머리 21 중 민머리 빼고) 모두에(얼굴형 5·6 이 가발을 안 뚫게)
        gj = json.loads(b[20:20 + int.from_bytes(b[12:16], 'little')])
        mn = {n['name']: (gj['meshes'][n['mesh']].get('extras') or {}).get('targetNames', []) for n in gj['nodes'] if 'mesh' in n}
        hn = [k for k in mn if k.startswith('hair_')]
        check('넓은 얼굴 모프: 몸·얼굴·가발 20 모두', len(hn) == 20 and all('face_full' in mn[k] for k in hn + ['body', 'face']), str({k: v for k, v in mn.items() if 'face_full' not in v})[:200])
    _, pj0 = api('/api/presets')
    st, j = api('/avatar/face_atlas.json', hdr={'X-Forwarded-For': '1.2.3.4'})
    check('웹 얼굴 부품 그림 표', st == 200 and isinstance(j, dict) and 'sprites' in j)
    wr = j.get('groups', {}).get('wrinkle', []) if isinstance(j, dict) else []
    check('얼굴 그림: 주름 16 = 비트마다 한 층(3 = 눈가 + 이마, 15 = 네 층)', len(wr) == 16 and wr[0] == [] and wr[3] == wr[1] + wr[2]
          and all(len(wr[v]) == bin(v).count('1') for v in range(16)) and wr[15] == wr[1] + wr[2] + wr[4] + wr[8], str(wr)[:120])
    gs = j.get('groups', {}) if isinstance(j, dict) else {}
    check('얼굴 그림: 눈 25·눈썹 10·코 3·입 9(서버 개수와 같음)', [len(gs.get(k, [])) for k in ('eyes', 'brows', 'nose', 'mouth')] == [25, 10, 3, 9]
          and all(gs[k][i] for k in ('eyes', 'brows', 'nose', 'mouth') for i in range(len(gs[k]))))
    check('얼굴 그림: 숨긴 부품은 옮기는 곳과 같은 층(옛 값을 받아도 같은 얼굴)', all(gs[k][a] == gs[k][b] for k, m in MOVED_N.items() for a, b in m.items()))
    nm = j.get('names', {}) if isinstance(j, dict) else {}
    check('얼굴 그림 이름 = 서버 부품 이름(눈·눈썹·입)', all(nm.get(k) == pj0['parts'][k] for k in ('eyes', 'brows', 'mouth')), str(nm.get('eyes'))[:120])
    un = [L for o in wr for L in o if L.get('unless_eyes')]
    check('눈 밑 선만 애교살 눈(15)과 같이 안 그림', un and all(L['unless_eyes'] == [15] for L in un) and {L['sprite'] for L in un} == {L['sprite'] for L in wr[8]}, str(un)[:120])
    lay = [L for g in (j.get('groups', {}) if isinstance(j, dict) else {}).values() for o in g for L in o]
    check('얼굴 그림: 피부 맞춤 칸(주름·코 skin, 볼터치 pair, 눈썹·수염 sep)', isinstance(j.get('skin_t'), list) and len(j['skin_t']) == 2
          and all(L.get('tint') == 'skin' and len(L.get('k', [])) == 2 for o in j['groups']['wrinkle'] + j['groups']['nose'] for L in o)
          and all(L.get('tint') == 'pair' and len(L.get('c', [])) == 2 for o in j['groups']['blush'] for L in o)
          and all(L.get('sep', 0) > 0 for L in lay if L.get('tint') in ('hair', 'beard')), str(j.get('skin_t')))
    bd = gs.get('beard', [])
    check('얼굴 그림: 수염 4 = 짧은 수염(1)과 같은 층(콧수염은 3D)', len(bd) == 5 and bd[4] == bd[1] and bd[1] and bd[2] == bd[3] == [], str(bd)[:120])
    bs, ms = gs.get('beards', []), gs.get('marks', [])
    # 11/10: 짧은 수염 비트 뒤에 '피부색 비우기' 층(need: 주름 4·8, 주근깨 64 를 골랐을 때만)이 붙는다
    check('얼굴 그림: 수염 비트 8(짧은 수염 비트만 얼굴 그림, 콧·턱수염은 3D)', len(bs) == 8 and all((bs[v][:len(bd[1])] == bd[1] and all(L.get('need') and L.get('tint') == 'skin' for L in bs[v][len(bd[1]):])) if v & 1 else bs[v] == [] for v in range(8)), str(bs)[:100])
    ew = gs.get('wrinkle', [[], []])[1]
    check('얼굴 그림: 눈가 주름은 눈마다 자리(by_eyes 25칸)', len(ew) == 1 and len(ew[0].get('by_eyes', [])) == 25 and all(0 <= i < len(j['sprites']) for i in ew[0]['by_eyes']), str(ew)[:100])
    spr = j.get('sprites', [])
    one = [ms[1 << b] for b in range(7)] if len(ms) == 128 else []
    check('얼굴 그림: 점 비트 128 = 켜진 비트 층 합, 오른쪽 점은 왼쪽 점의 좌우 거울 자리', len(ms) == 128 and all(len(o) == 1 for o in one)
          and all(ms[v] == [L for b in range(7) if v >> b & 1 for L in one[b]] for v in range(128))
          and all(abs(spr[one[b + 1][0]['sprite']]['dst'][0] - (1 - spr[one[b][0]['sprite']]['dst'][2])) < 2e-3 for b in (0, 2, 4))
          and [one[b] for b in (0, 2, 4, 6)] == gs.get('mark', [])[1:5], str(one)[:120])
    check('얼굴 그림: 그리는 칸은 비트 칸(beards·marks), 예전 beard·mark 는 안 그림', 'beards' in j['draw_order'] and 'marks' in j['draw_order']
          and 'beard' not in j['draw_order'] and 'mark' not in j['draw_order'] and nm.get('mark_bits') == [pj0['parts']['marks'][1 << b] for b in range(7)], str(j['draw_order']))
    mk = gs.get('mark', [])
    check('얼굴 그림: 점 5(0 없음, 1~3 한쪽 점 한 층, 4 주근깨 좌우), 피부 맞춤 pair, 볼터치 다음·주름 앞', len(mk) == 5 and mk[0] == []
          and all(len(mk[v]) == 1 and mk[v][0].get('tint') == 'pair' and len(mk[v][0].get('c', [])) == 2 for v in range(1, 5))
          and [mk[v][0].get('mirror') for v in range(1, 5)] == [False, False, False, True] and nm.get('mark') == pj0['parts']['mark']
          and j['draw_order'].index('marks') == j['draw_order'].index('blush') + 1, str(mk)[:160])
    _, pj = api('/api/presets')
    check('주름 이름 16개(0~3 예전 이름 그대로)', pj['parts']['wrinkle'][:4] == ['없음', '눈가 주름', '이마 주름', '눈가·이마 주름']
          and len(pj['parts']['wrinkle']) == 16 and len(pj['face_spec']['wrinkle']['options']) == 16)


# ---------- 73번(11/09): 정차 중 순간 · 남은 시간 막대 · 주차 목록 · 상한 없음 ----------
def keepalive(client='reg'):
    """콘솔은 붙은 브라우저가 없으면 503: 화면 없이 돌릴 때 1초마다 심장 박동을 보낸다."""
    import threading
    def loop():
        while True:
            try: req(f'{VC}/browser/session?client={client}', {})
            except BaseException: pass
            time.sleep(1)
    threading.Thread(target=loop, daemon=True).start()

def park_list():
    n = nlines(); car('list'); return wait_for(r'\[테스트\] 주차 목록', 8, n) or ''

def c_bat_park():
    """P에서 배터리 부족 → 바로 알림(대기열 아님) → 들으면 출발해도 다시 안 알림"""
    fresh(); hide('아내', 'battery'); time.sleep(3); soc(14)
    check('P에서 바로 알림', wait_for(r'정차 중 순간: .* 알림', 15))
    check('대기열에 안 넣음', not wait_for(r'대기열에 넣음', 2))
    time.sleep(3); car('listen')
    check('P [듣기] → 재생 끝', wait_for(r'메시지 재생 끝', 25))
    n = nlines(); drive(); time.sleep(30)
    check('출발 뒤 같은 메시지 다시 알림 없음', not wait_for(r'버튼 듣기: .* 알림', 1, n))

def c_drive_timeout():
    """주행 중 대답 없음 → 이번 운행엔 다시 안 물음 → 주차 목록 1개(자동 재생 안 함)"""
    fresh(); hide('지윤', 'rain'); time.sleep(3); drive(); time.sleep(3); wiper('Low')
    wait_for(r'버튼 듣기: .* 알림', 60)
    check('남은 시간 막대 시작', wait_for(r'핸들 버튼 기다림', 20))
    check('대답 없음', wait_for(r'대답 없음', 20))
    wiper('Off'); speed(0); stopped(); gear('Park'); time.sleep(4)
    l = park_list(); check('주차 목록 1개', '주차 목록 1개' in l, l[l.find('주차'):][:80])

def c_park_list():
    """비·집 미룸 + 주차했을 때 → '음성 메시지 3개입니다.' + 받은 차례 목록, 저절로 안 틂"""
    fresh(); hide('지윤', 'rain'); hide('엄마', 'home'); hide('아빠', 'arrive'); time.sleep(3)
    car('sethome', lat=HOME[0], lon=HOME[1]); time.sleep(2)
    drive(); time.sleep(3); wiper('Low'); wait_for(r'버튼 듣기: .* 알림', 60); wait_for(r'대답 없음', 30)
    time.sleep(22); n = nlines(); geo(*HOME)
    check('집 알림 → 대답 없음', wait_for(r'버튼 듣기: 엄마', 60, n) and wait_for(r'대답 없음 → 엄마', 30, n))
    n = nlines(); wiper('Off'); speed(0); stopped(); gear('Park')
    check('주차 안내(녹음, 개수 없음)', wait_for(r'안내: "도착한 음성 메시지가 있습니다\."', 20, n))
    check('자동 재생 안 함', not wait_for(r'메시지 재생 \(', 4, n))
    l = park_list(); check('받은 차례', re.search(r'지윤·rain.*엄마·home.*아빠·arrive', l), l[l.find('주차'):][:120])
    car('listplay', value=1)
    check('줄 하나 → 그 메시지만', wait_for(r'엄마 메시지 재생 끝', 25))

def c_ann_clips():
    """75번 B-2 녹음 안내: 운행 첫 알림은 긴 것, 두 번째는 짧은 것. 이름·숫자 없음. 녹음 파일이 없으면 띵동만(기기 TTS 없음)"""
    fresh(); hide('지윤', 'rain'); hide('엄마', 'rain'); time.sleep(3); drive()
    d = wait_for(r'안내: "예약된 음성 메시지가 있습니다\."', 20)
    check('출발: 예약된 음성 메시지가 있습니다', d, d[d.find('안내'):][:70] if d else '')
    time.sleep(22); n = nlines(); wiper('Low')
    a1 = wait_for(r'안내: "음성 메시지가 도착했습니다\. 들으시려면 핸들 가운데 버튼을 눌러 주세요\."', 40, n)
    check('첫 알림: 긴 안내', a1, a1[a1.find('안내'):][:90] if a1 else '')
    check('이름 없음', a1 and '지윤' not in a1 and '엄마' not in a1)
    check('파일 없으면 띵동만', a1 and ('녹음 없음 → 띵동만' in a1 or '(ann_arrive_first)' in a1), a1[-30:] if a1 else '')
    wait_for(r'대답 없음', 30, n); n = nlines()
    a2 = wait_for(r'안내: "음성 메시지가 도착했습니다\." ', 60, n)
    check('두 번째 알림: 짧은 안내', a2, a2[a2.find('안내'):][:70] if a2 else '')
    wait_for(r'대답 없음', 30, n)
    l = park_list(); check('주행 중 줄: 도착 2개', '도착(주행 중 줄) 2개' in l, l[l.find('예약'):][:60])
    n = nlines(); wiper('Off'); speed(0); stopped(); gear('Park')
    check('주차: 도착한 음성 메시지가 있습니다', wait_for(r'안내: "도착한 음성 메시지가 있습니다\."', 20, n))
    check('기기 TTS 안 씀', not wait_for(r'안내 음성', 1, 0))

def c_home_in_R():
    """운행 중 R로 집 반경에 들어와도 순간(D가 되면 알림)"""
    fresh(); hide('엄마', 'home'); time.sleep(3); car('sethome', lat=HOME[0], lon=HOME[1]); time.sleep(2)
    drive(); time.sleep(25); speed(0); stopped(); gear('Reverse'); time.sleep(1); geo(*HOME)
    check('R에서 집 근처 → 대기열', wait_for(r'대기열에 넣음', 20))
    gear('Drive'); time.sleep(1); speed(40); steer(0)
    check('D 되면 알림', wait_for(r'버튼 듣기: .* 알림', 40))

def c_no_cap():
    """하루 5개 상한 없음: 6번째도 주행 중에 나옴"""
    fresh('auto')
    for i in range(6): hide(f'사람{i}', 'rain')
    time.sleep(4); drive(); time.sleep(25); wiper('Low')
    ok, n = 0, 0
    for i in range(6):
        if wait_for(r'메시지 재생 끝', 60, n): ok += 1
        n = nlines()
    check('6개 모두 주행 중 재생', ok == 6, f'{ok}개')


def c_examples():
    """서버: 예시 듣기 목록(/api/examples) — 순간마다 하나, 여섯 개(순간 차례), 보내는 사람·듣는 사람·문장, 파일은 밖에서도 열림, 예전 demo_ 주소도 그대로"""
    st, j = api('/api/examples', hdr={'X-Forwarded-For': '1.2.3.4'})
    ex = j.get('examples', []) if st == 200 and isinstance(j, dict) else []
    check('예시 목록 딱 6개(밖에서도)', st == 200 and len(ex) == 6, f'{st} {len(ex)}개')
    # 새 목소리(ex_<순간>)가 아직 없는 순간(제미나이 하루 한도)은 예전 demo_로 채운다. 어느 쪽이든 순간마다 하나
    check('순간마다 하나, 순간 차례', [e.get('moment') for e in ex] == ['start', 'arrive', 'home', 'rain', 'long', 'battery'],
          [e.get('moment') for e in ex])
    check('파일은 ex_<순간> 또는 demo_<순간>', all(e.get('audio') in (f"/ex/ex_{e.get('moment')}.m4a", f"/ex/demo_{e.get('moment')}.m4a") for e in ex),
          [e.get('audio') for e in ex])
    check('보내는 사람·듣는 사람·문장', all(e.get('from') and e.get('to') and e.get('text') for e in ex))
    bad = []
    for e in ex:
        st, b = api(e['audio'], hdr={'X-Forwarded-For': '1.2.3.4'})
        if not (st == 200 and isinstance(b, bytes) and len(b) > 1000 and b[4:8] == b'ftyp'): bad.append(e['audio'])
    check('예시 파일 모두 열림(m4a)', ex and not bad, bad[:3])
    st, b = api('/ex/demo_rain.m4a', hdr={'X-Forwarded-For': '1.2.3.4'})
    check('예전 demo_ 주소도 열림', st == 200 and isinstance(b, bytes) and len(b) > 1000)
    for nope in ('/ex/ex_nope.m4a', '/ex/ex_start_1.m4a'):   # 밖에서 모르는 주소(예전 ex_start_1~3 포함)는 첫 화면으로 돌려보낸다
        st, b = api(nope, hdr={'X-Forwarded-For': '1.2.3.4'})
        check(f'목록에 없는 파일은 안 열림 {nope}', not (isinstance(b, bytes) and b[4:8] == b'ftyp'), st)


SERVER_CASES = [c_server_rules, c_photo_reissue, c_presets, c_plaza, c_together, c_reactions, c_web_files, c_examples]

CASES = [c_server_rules, c_photo_reissue, c_presets, c_plaza, c_together, c_reactions, c_web_files, c_examples, c_realtime_button, c_no_answer_arrive, c_auto, c_arrive_mode, c_steer, c_signal, c_lot,
         c_battery, c_home, c_place, c_arrive_moment, c_short_park, c_start_parked, c_start_later, c_depart_announce,
         c_repeat_each, c_passenger, c_long, c_gap_and_two, c_same_sender, c_delete_realtime, c_tomorrow,
         c_bat_park, c_drive_timeout, c_park_list, c_ann_clips, c_home_in_R, c_no_cap,
         c_close]  # 앱 닫기는 '시동 끔'이나 앱 새로 열기로만 풀리므로 맨 끝

if __name__ == '__main__':
    only_server = '--server' in sys.argv
    pick = [a for a in sys.argv[1:] if a != '--server']
    if not only_server: keepalive(); time.sleep(2)   # 첫 박동이 닿기 전에 콘솔을 부르면 503
    for c in (SERVER_CASES if only_server else CASES):
        if pick and c.__name__ not in pick: continue
        print('==', c.__name__, (c.__doc__ or '').strip().split('\n')[0]); sys.stdout.flush()
        try: c()
        except Exception as e: check(c.__name__ + ' 오류', False, repr(e)[:200])
    if not only_server:
        try: signal('Off'); wiper('Off'); speed(0); steer(0); gear('Park')
        except Exception as e: print('콘솔 되돌리기 실패:', repr(e)[:100])
    print(f'\n합계 {sum(ok for _, ok, _ in R)}/{len(R)} 통과')
    for n, ok, note in R:
        if not ok: print('  실패:', n, note)
