# 차 안내 녹음 4개(75번 B-2): 이름·순간·숫자 없는 고정 문장. 모델 하나(gemini-2.5-flash-preview-tts)만 쓴다.
# 끝은 자르지 않고 마지막 40ms만 줄인 뒤 0.4초 쉼(칼같이 자르면 마지막 글자가 '치지직'). 네 개 소리 크기를 같게 맞춘다.
# 받아쓰기(gemini-2.5-flash)로 글자 하나하나(마지막 글자까지) 맞는지 확인한다. 소리는 내지 않는다(파일만).
# 제미나이 하루 한도는 한국 시간 17시쯤 풀린다. 한도에 걸리면 다른 모델로 바꾸지 말고 멈춘다(나중에 같은 모델로 이어서).
# 사용: python3 make_ann.py 작업폴더 [--install] [이름...]
#   결과: 작업폴더/ok/ann_*.m4a + result.json. --install이면 통과한 것을 app/src/main/res/raw/로 복사(앱이 다음 빌드부터 씀).
import json, urllib.request, urllib.error, base64, sys, subprocess, time, re, os, socket, shutil

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = ARGS[0]; ONLY = ARGS[1:]
INSTALL = "--install" in sys.argv
MODEL = "gemini-2.5-flash-preview-tts"; STT = "gemini-2.5-flash"
# 키: 환경 변수 GEMINI_API_KEY, 없으면 DODAM_ENV(.env 파일 경로, 기본은 저장소 맨 위 .env)에서 읽는다. 출력하지 않는다
ENV = os.environ.get("DODAM_ENV", os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../.env"))
KEY = os.environ.get("GEMINI_API_KEY") or next((l.split("=", 1)[1].strip().strip('"') for l in open(ENV) if l.startswith("GEMINI_API_KEY=")), "")
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../app/src/main/res/raw")

# 차 안내 목소리: 가족 예시 목소리(Leda·Sulafat 등)와 겹치지 않는 맑은 여성 목소리 하나로 통일
VOICE = "Erinome"
# 11/11 사용자 '템포가 느림': 녹음 뒤 속도를 바꾸지 않고 지시문으로 또렷하고 경쾌한 안내 방송 속도를 요청한다
STYLE = ("a clear, polite Korean in-car system announcer (like a Korean car navigation voice), "
         "clear standard Seoul pronunciation, crisp and light, brisk announcement pace like a modern car's notification voice "
         "(do not drag or stretch syllables, no long pauses), warm but no exaggerated emotion")

# (파일 이름, 문장, 최대 길이 초) — 앱 Ann.kt와 같은 문장이어야 한다
JOBS = [
    ("ann_arrive_first", "음성 메시지가 도착했습니다. 들으시려면 핸들 가운데 버튼을 눌러 주세요.", 7.0),
    ("ann_arrive", "음성 메시지가 도착했습니다.", 3.5),
    ("ann_parked", "도착한 음성 메시지가 있습니다.", 3.5),
    ("ann_depart", "예약된 음성 메시지가 있습니다.", 3.5),
]


class DayLimit(Exception): pass


def post(model, body):
    r = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                               json.dumps(body).encode(), {"Content-Type": "application/json", "x-goog-api-key": KEY})
    for t in range(6):
        try: return json.load(urllib.request.urlopen(r, timeout=120))
        except urllib.error.HTTPError as e:
            txt = e.read().decode()
            if e.code == 429 and "PerDay" in txt: raise DayLimit(model)
            if e.code in (429, 500, 503): print(f"  {model} {e.code} 기다림", flush=True); time.sleep(30); continue
            raise RuntimeError(f"{e.code} {txt[:160]}")
        except (TimeoutError, socket.timeout, urllib.error.URLError): time.sleep(5); continue
    raise RuntimeError("계속 실패 " + model)


def norm(s): return re.sub(r"[^가-힣0-9]", "", s)
def dur(p): return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).decode())


def transcribe(p):
    b64 = base64.b64encode(open(p, "rb").read()).decode()
    tj = post(STT, {"contents": [{"parts": [{"inlineData": {"mimeType": "audio/mp4", "data": b64}},
                                            {"text": "Transcribe this Korean audio exactly, every syllable including the sentence ending. Output only the transcript."}]}],
                    "generationConfig": {"temperature": 0}})
    return tj["candidates"][0]["content"]["parts"][0]["text"].strip()


# 앞 무음만 자르고, 소리 크기를 맞춘 뒤(네 개가 같은 크기로), 끝은 자르지 않고 마지막 40ms만 줄이고 0.4초 쉼
AF = ("silenceremove=start_periods=1:start_threshold=-50dB,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=24000,"
      "areverse,afade=t=in:d=0.04,areverse,apad=pad_dur=0.4")
def encode(raw, out): subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", raw,
                                      "-af", AF, "-ar", "24000", "-ac", "1", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", out], check=True)


os.makedirs(f"{OUT}/ok", exist_ok=True)
RES = f"{OUT}/result.json"
res = json.load(open(RES)) if os.path.exists(RES) else {}
for name, line, max_sec in JOBS:
    if ONLY and name not in ONLY: continue
    if not ONLY and name in res and res[name].get("ok"): continue
    ok = False
    for a in range(4):
        raw = f"{OUT}/{name}_{a}.pcm"; cand = f"{OUT}/cand_{name}_{a}.m4a"
        prompt = (f"Speak only the Korean line below, exactly as written, nothing else. Voice: {STYLE}. "
                  f"Polite and short, like a car announcement. Pronounce the last syllable fully and let it end naturally, then stay silent.\n\n{line}")
        if not os.path.exists(raw):
            try:
                j = post(MODEL, {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["AUDIO"],
                         "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}})
            except DayLimit as e:
                print("하루 한도:", e, "— 멈춤(17시쯤 다시)", flush=True); json.dump(res, open(RES, "w"), ensure_ascii=False, indent=1); sys.exit(2)
            open(raw, "wb").write(base64.b64decode(j["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]))
        encode(raw, cand); d = dur(cand)
        try: tr = transcribe(cand)
        except DayLimit as e:
            print("받아쓰기 하루 한도:", e, "— 멈춤", flush=True); json.dump(res, open(RES, "w"), ensure_ascii=False, indent=1); sys.exit(3)
        exact = norm(tr) == norm(line)
        print(f"{name}#{a} {d:.2f}초 {'일치' if exact else '다름'} | {tr}", flush=True)
        if exact and d <= max_sec:
            shutil.copy(cand, f"{OUT}/ok/{name}.m4a")
            res[name] = dict(ok=True, text=line, voice=VOICE, model=MODEL, sec=round(d, 2), transcript=tr, attempt=a)
            print("  → 채택", name, flush=True); ok = True; break
        time.sleep(6)
    if not ok:
        res[name] = dict(ok=False, text=line, voice=VOICE, model=MODEL)
        print("  → 실패", name, flush=True)
    json.dump(res, open(RES, "w"), ensure_ascii=False, indent=1)

done = [n for n, *_ in JOBS if res.get(n, {}).get("ok")]
print("채택", len(done), "/", len(JOBS))
if INSTALL:
    for n in done:
        shutil.copy(f"{OUT}/ok/{n}.m4a", os.path.join(RAW, f"{n}.m4a")); print("넣음", n)
    print("앱에 넣었다: 다시 빌드하면 띵동 뒤에 녹음이 나온다(없는 것은 띵동만)")
