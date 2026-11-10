"""목소리·사진 검수: Gemini 한 번 호출로 말소리 유무, 욕설·부적절, 놀라게 하는 소리, 운전 지시를 판정한다.
키는 pleos-contest/.env 의 GEMINI_API_KEY (출력하지 않는다). 사용: python3 moderate.py 파일...
"""
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.request

ENV = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
# 클라우드에서는 환경 변수로, 맥에서는 .env 파일에서 읽는다
KEY = os.environ.get("GEMINI_API_KEY") or next(
    (l.split("=", 1)[1].strip().strip('"') for l in open(ENV) if l.startswith("GEMINI_API_KEY=")) if os.path.exists(ENV) else iter(()), "")
# 무료 한도는 모델마다 따로라 차례로 넘긴다(목소리·사진 검수 모두 이 순서). 구글 요금 표에 있는 정식 모델만 쓴다(11/04 확인).
# 1순위를 두 번 넣은 건 잠깐 바쁠 때(503) 한 번 더 묻기 위해서. 뒤로 갈수록 비싸거나 느리다.
# 뺀 것: gemini-3.5-flash(요금 표에 없는 이름이라 막힐 수 있음), gemini-2.5-flash(지원 종료 예정, 12/1부터 3.5-flash-lite로 넘어감),
#        gemini-3-flash-preview(미리보기), flash-lite-latest(말소리를 '없음'으로 잘못 봄), gemma-4(목소리 입력 안 됨)
MODELS = os.environ.get("MOD_MODELS", "gemini-3.1-flash-lite,gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-2.5-flash-lite,"
                        "gemini-3.6-flash").split(",")

PROMPT = """너는 차량용 음성 메시지 앱의 검수기다. 이 음성은 운전 중인 사람에게 재생된다. 들은 말을 받아 적지 말고 아래 항목만 판정하라.
"speech": 사람 말소리가 들리는지(bool). 잡음이나 무음뿐이면 false.
"profanity": 욕설·혐오·성적·위협 표현 여부(bool).
"startling": 사이렌·경적·비명·경고음·갑작스러운 큰 소리 등 운전자를 놀라게 할 소리 여부(bool). 일정한 잡음은 false.
"driving_command": 운전 중인 사람에게 지금 당장 운전에서 눈·손을 떼게 하는 말 여부(bool).
true: "멈춰", "브레이크 밟아", "핸들 꺾어" 같은 다급한 조작 지시, "지금 문자 확인해", "사진 찍어 보내", "바로 전화해" 같은 휴대폰·화면 조작 요구.
false: "천천히 와", "조심히 와", "졸리면 쉬었다 와" 같은 당부, "우유 사 와", "들어오는 길에 세탁소 들러" 같은 나중에 할 부탁.
"verdict": profanity·startling·driving_command 중 하나라도 true면 "block", 판단이 애매하면 "review", 아니면 "pass".
"reason": 20자 이내 한 줄."""

# 답 모양을 고정한다. 받아쓰기를 시키면 잡음에서 같은 글자를 끝없이 뱉어 시간이 초과됐다.
SCHEMA = {"type": "OBJECT", "properties": {
    "speech": {"type": "BOOLEAN"}, "profanity": {"type": "BOOLEAN"}, "startling": {"type": "BOOLEAN"}, "driving_command": {"type": "BOOLEAN"},
    "verdict": {"type": "STRING", "enum": ["pass", "review", "block"]}, "reason": {"type": "STRING"}},
    "required": ["speech", "profanity", "startling", "driving_command", "verdict", "reason"]}


def ask(prompt, mime, data_b64, schema, timeout=60, budget=None, tokens=200):
    """앞 모델이 한도·장애로 막히면 다음 모델로 넘어간다(무료 한도가 모델마다 따로다). 첫 모델은 잠깐 바쁠 때가 있어(503) 한 번 더 묻는다."""
    last = None
    end = time.time() + budget if budget else None  # 전체 대기 상한: 넘으면 다음 모델로 안 간다
    for model in MODELS:
        if end and time.time() > end - 1:
            break
        config = {"response_mime_type": "application/json", "response_schema": schema, "temperature": 0, "maxOutputTokens": tokens}
        if model.startswith("gemini-2.5"):
            config["thinkingConfig"] = {"thinkingBudget": 0}
        elif not "lite" in model:   # 생각하는 데 쓰는 글자까지 한도에 들어가 답이 잘렸다
            config["maxOutputTokens"] = 1500
        body = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": data_b64}}]}], "generationConfig": config}
        req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={KEY}",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            out = json.load(urllib.request.urlopen(req, timeout=min(timeout, end - time.time()) if end else timeout))
            return json.loads(out["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as e:
            last = e
            print("검수 모델 실패:", model, type(e).__name__, getattr(e, "code", ""), flush=True)
    raise last or TimeoutError("검수 대기 상한")


def check(path, timeout=60, budget=None):
    """목소리 파일 하나를 검수한다."""
    mime = mimetypes.guess_type(path)[0] or "audio/mp4"
    if path.endswith(".m4a"):
        mime = "audio/mp4"
    audio = base64.b64encode(open(path, "rb").read()).decode()
    return ask(PROMPT, mime, audio, SCHEMA, timeout, budget)


PHOTO_PROMPT = """너는 차량용 음성 메시지 앱의 프로필 사진 검수기다. 이 사진은 메시지를 남긴 사람을 알아보게 차 화면에 작게 보인다.
보이는 사람이 누구인지 말하지 말고 아래 항목만 판정하라. 얼굴·풍경·반려동물·그림 같은 평범한 프로필 사진은 문제없다.
"sexual": 노출·성적인 내용(bool). "violent": 폭력·피·잔인한 장면(bool). "hate": 혐오 상징·혐오 표현(bool).
"spam": 광고·홍보 문구·연락처·QR 등 글자 위주 홍보(bool). "private": 남의 신분증·카드·주소·전화번호 같은 개인정보가 읽히는지(bool).
"verdict": 위 항목 중 하나라도 분명히 true면 "block", 판단이 애매하면 "review", 모든 나이가 봐도 괜찮으면 "pass".
"reason": 20자 이내 한 줄."""

PHOTO_SCHEMA = {"type": "OBJECT", "properties": {
    "sexual": {"type": "BOOLEAN"}, "violent": {"type": "BOOLEAN"}, "hate": {"type": "BOOLEAN"}, "spam": {"type": "BOOLEAN"}, "private": {"type": "BOOLEAN"},
    "verdict": {"type": "STRING", "enum": ["pass", "review", "block"]}, "reason": {"type": "STRING"}},
    "required": ["sexual", "violent", "hate", "spam", "private", "verdict", "reason"]}


def check_photo(raw, timeout=60, budget=None):
    """프로필 사진(JPEG 바이트) 하나를 검수한다."""
    return ask(PHOTO_PROMPT, "image/jpeg", base64.b64encode(raw).decode(), PHOTO_SCHEMA, timeout, budget)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        try:
            r = check_photo(open(p, "rb").read()) if p.lower().endswith((".jpg", ".jpeg")) else check(p)
            print(os.path.basename(p), json.dumps(r, ensure_ascii=False))
        except Exception as e:
            print(os.path.basename(p), "실패:", getattr(e, "code", ""), str(e)[:200])
