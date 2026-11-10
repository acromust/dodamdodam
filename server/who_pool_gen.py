"""닮은 모습 풀(83번 4장) 만들기: 첫 화면 16명은 손으로 고정, 그 뒤 5화면 80명은 규칙으로 찍어 avatar.py 에 적어 둔다.
실행할 때 무작위로 만들지 않는다(같은 씨앗 → 늘 같은 값). 서버는 적어 둔 값만 읽는다(이 파일은 렌더 서버에 안 올라간다).

쓰는 법:  python3 server/who_pool_gen.py          → avatar.py 의 WHO 블록을 새로 쓴다
          python3 server/who_pool_gen.py --check  → 적어 둔 값이 지금 규칙으로 찍은 값과 같은지만 본다

화면 = 4칸 × 4줄(줄 이름 없음). 칸 순서 남·여·남·여.
  1줄 어린이 남·여 + 10대 남·여, 2줄 20~30대, 3줄 40~50대, 4줄 60대 이상.
칸마다 6명(화면 6장). [다른 얼굴 보기]는 칸마다 안 본 얼굴부터 낸다(웹 nextWho).
한 화면 규칙(83번 4장, 한국 통계 맞춤):
  60대 이상 4명 중 검정·진한 갈색(염색) 2명 · 성인 12명 중 안경 5명 · 여자 8명 중 듬직 2명 · 갸름·각진 얼굴 4명 이상
  · 성인 남자 수염 1명 이상 · 피부 4가지 이상 · 눈+입 조합 겹침 없음(풀 96명 전체에서) · 한 줄 안 같은 머리 없음 · 목도리 1명
  · 구릿빛·짙은 피부: 첫 화면 0, 뒤 80명 중 3명(약 24명에 1명, 다문화 출생 5.6%)
  · 85번: 듬직한 어른 중 둥근 얼굴은 5 넓은 얼굴(무작위 안 씀, 손으로 고른 첫 화면은 파마 엄마 1명)
11/10 다시 찍음(사장 '눈하고 가발이 바뀌었으니까 경우의 수가 너무 달라졌어'): 새 가발 17 투블럭(10~40대 남)·18 C컬 중단발(30~50대 여)·
  19 웨이브 커트(50대 이상 여), 10 바가지(어린이·10대, 가끔 어른)를 칸마다 허용 목록에 넣고, 새 눈 17~24 그대로.
  닮은꼴 12명(LOOKS, look_01~12): 한눈에 알아보는 생김새(머리·안경·표정)를 우리 부품으로만 따라 한 얼굴. 첫 화면에 4명, 화면 1~5에 8명.
  누구를 참고했는지는 앱·코드·서버 값에 적지 않는다(연구 노트에만). 화면에는 얼굴만 나온다
"""
import os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

W_EYE, W_FORE, W_MOUTH, W_UNDER = 1, 2, 4, 8
CELLS = [[("child", "m"), ("child", "f"), ("teen", "m"), ("teen", "f")],
         [("young", "m"), ("young", "f"), ("young", "m"), ("young", "f")],
         [("middle", "m"), ("middle", "f"), ("middle", "m"), ("middle", "f")],
         [("old", "m"), ("old", "f"), ("old", "m"), ("old", "f")]]
PAGES = 6
ADULT = ("young", "middle", "old")
# 각진형(face_square) 형태가 없는 가발: 스포츠머리 0·옆머리 3·양갈래 7·파마 13·올백 16(char.glb 모프 이름에서 셈). 이 머리엔 각진형을 안 준다
# 10 바가지는 11/10 다시 만들며 얼굴형 모프를 넣어(build_char FORCE_FACE_MORPHS) 뺐다. 새 가발 17·18·19도 모프가 있다
NO_SQUARE = (0, 3, 7, 13, 16)

# ---------- 첫 화면 16명(손으로 고름). 81번 '한국 가족 먼저' + 83번 빈칸(염색 어르신·듬직한 엄마·할머니·안경 쓴 청년 여·수염) ----------
# want = 이 사람에게 준 생김새(메모, 화면에 안 나옴). 이름에 낮추는 말 안 씀
FIRST = [
    # 1줄: 어린이 남·여, 10대 남·여
    ("바가지 머리·큰 눈·동글 눈썹·활짝 웃음", dict(hair=10, eyes=1, brows=8, mouth=1, blush=1, skin=0)),
    ("양갈래·왕눈·짧은 눈썹·동그란 입", dict(hair=7, eyes=17, brows=0, mouth=3, blush=1, skin=5)),
    ("숏컷·곁눈·일자 눈썹·미소", dict(hair=12, eyes=24, brows=2, mouth=0, skin=1, face=1)),
    ("포니테일·속눈썹 반달눈·순한 눈썹·활짝 웃음·주근깨", dict(hair=6, hairColor=1, eyes=13, brows=6, mouth=1, blush=1, skin=1, mark=4)),
    # 2줄: 20~30대
    ("닮은꼴 look_04: 투블럭·눈웃음 눈·일자 눈썹·활짝 웃음·조금 각진", dict(hair=17, eyes=19, brows=2, mouth=1, face=4, skin=2, height=2, pantsColor=2)),
    ("닮은꼴 look_08: 긴 생머리 검정(가운데 가르마)·속눈썹 눈·가는 눈썹·활짝 웃음·볼터치·눈 밑 점·갸름·큰 키", dict(hair=5, eyes=12, brows=7, mouth=1, blush=1, face=1, skin=0, height=2, build=0, mark=1)),
    ("옆가르마·갈색 뿔테 네모 안경·아몬드 눈·일자 눈썹·잔잔한 미소", dict(hair=1, eyes=18, brows=2, mouth=4, glasses=2, glassesColor=1, skin=1, height=2)),
    ("C컬 중단발 밝은 갈색·동그란 안경·아래 속눈썹 눈·가는 눈썹·미소", dict(hair=18, hairColor=2, eyes=20, brows=7, mouth=0, blush=1, glasses=1, face=3, skin=5)),
    # 3줄: 40~50대
    ("닮은꼴 look_01: 바가지 검정·검정 네모 안경·무쌍 눈·일자 눈썹·활짝 웃음·갸름·날씬", dict(hair=10, eyes=14, brows=2, mouth=1, wrinkle=W_EYE | W_MOUTH,
                                                                    glasses=2, face=1, skin=1, height=2, build=0, pantsColor=1, _color=2)),
    ("파마 진한 갈색·강아지 눈·순한 눈썹·잔잔한 미소·넓은 얼굴·듬직", dict(hair=13, hairColor=1, eyes=11, brows=6, mouth=4,
                                                 wrinkle=W_EYE | W_MOUTH, blush=1, face=5, skin=1, build=2)),
    ("옆머리 희끗·무심한 눈·일자 눈썹·짧은 수염 + 콧수염·활짝 웃음", dict(hair=3, hairColor=6, eyes=21, brows=2, nose=2, mouth=1,
                                                wrinkle=W_EYE | W_MOUTH, beard=4, skin=6, height=2)),
    ("웨이브 커트 희끗한 갈색·진한 쌍꺼풀 눈·가는 눈썹·미소", dict(hair=19, hairColor=7, eyes=23, brows=7, mouth=0,
                                               wrinkle=W_MOUTH | W_UNDER, blush=1, face=1, skin=0)),
    # 4줄: 60대 이상(염색 2명)
    ("옆머리 흰머리·동그란 안경·실눈·긴 꼬리 눈썹·잔잔한 미소", dict(hair=3, hairColor=4, eyes=4, brows=9, nose=2, mouth=4,
                                                   wrinkle=W_EYE | W_FORE | W_MOUTH, glasses=1, glassesColor=2, skin=1)),
    ("뽀글 파마 진한 갈색·반달 안경·반달눈·순한 눈썹·미소·듬직", dict(hair=13, hairColor=1, eyes=5, brows=6, mouth=0,
                                                     wrinkle=W_EYE | W_MOUTH | W_UNDER, blush=1, glasses=3, glassesColor=3, skin=0, height=0, build=2)),
    ("2:8 가르마 검정·온화한 눈·긴 꼬리 눈썹·콧수염·꾹 다문 입", dict(hair=15, hairColor=0, eyes=22, brows=9, nose=2, mouth=2,
                                                     wrinkle=W_EYE | W_FORE | W_MOUTH, beard=2, face=2, skin=2)),
    ("닮은꼴 look_11: 숏컷 은발·무심한 눈·가는 눈썹·한쪽 미소·갸름·날씬·목도리", dict(hair=12, hairColor=11, eyes=21, brows=7, mouth=5,
                                                            wrinkle=W_EYE | W_FORE | W_MOUTH, face=1, skin=0, height=1, build=0, acc=1, scarfColor=0)),
]

# ---------- 닮은꼴(11/10 사장 '실제 있는 캐릭터 느낌 최대한'): 한눈에 알아보는 생김새를 우리 부품으로만 따라 한 12명 ----------
# 첫 화면에 4명(look_01·04·08·11, 위 FIRST), 화면 1~5에 8명(아래, (화면, 줄, 칸) 자리 고정). 한 화면 규칙·눈+입 안 겹침은 그대로 지킨다.
# 누구를 참고했는지는 여기·서버 값·화면에 적지 않는다(연구 노트에만). 메모는 생김새만. _color = 추천 대표색(옆 칸과 겹치지 않을 때만)
LOOKS = {
    (1, 1, 1): ("look_07", "앞머리 내린 긴 웨이브 검정·날렵한 눈(올라간 눈꼬리)·가는 눈썹·분홍 입술·볼터치 없음·갸름·날씬",
                dict(hair=8, hairColor=0, eyes=8, brows=7, mouth=7, blush=0, face=1, skin=0, height=1, build=0, pantsColor=2)),
    (1, 2, 2): ("look_02", "짧은 스포츠머리 검정·실눈(크게 웃어 감긴 눈)·숱 많은 눈썹·활짝 웃음·넓은 코·넓은 얼굴·듬직",
                dict(hair=20, hairColor=0, eyes=4, brows=3, nose=2, mouth=1, wrinkle=W_MOUTH | W_UNDER, face=5, skin=2, height=2, build=2, pantsColor=0)),
    (2, 2, 1): ("look_10", "C컬 중단발 진한 갈색·강아지 눈·순한 눈썹·시원한 웃음·넓은 얼굴·듬직",
                dict(hair=18, hairColor=1, eyes=11, brows=6, mouth=6, wrinkle=W_EYE | W_MOUTH, blush=1, face=5, skin=1, height=1, build=2, pantsColor=2)),
    (2, 3, 0): ("look_05", "애즈펌 검정(염색)·또렷한 눈·숱 많은 눈썹·콧수염·시원한 웃음",
                dict(hair=14, hairColor=0, eyes=7, brows=3, nose=2, mouth=6, wrinkle=W_EYE | W_FORE | W_MOUTH, beard=2, skin=2, height=1, build=1, pantsColor=0)),
    (3, 2, 0): ("look_03", "2:8 가르마 검정·무심한 눈·각진 눈썹·짧은 수염·꾹 다문 입·넓고 각진 얼굴·듬직",
                dict(hair=15, hairColor=0, eyes=21, brows=4, nose=2, mouth=2, wrinkle=W_EYE | W_MOUTH, beard=1, face=6, skin=6, height=2, build=2, pantsColor=2)),
    (3, 2, 3): ("look_09", "바가지 단발 검정·동그란 검정 안경·또렷한 눈·활짝 웃음·둥근 얼굴",
                dict(hair=10, hairColor=0, eyes=7, brows=2, mouth=1, wrinkle=W_MOUTH | W_UNDER, blush=1, glasses=1, glassesColor=0, skin=1, height=0, build=1, pantsColor=0)),
    (4, 3, 2): ("look_06", "옆가르마 검정(염색)·반달눈·숱 많은 눈썹·짧은 수염·활짝 웃음·넓은 얼굴·듬직",
                dict(hair=1, hairColor=0, eyes=5, brows=3, nose=2, mouth=1, wrinkle=W_EYE | W_MOUTH | W_UNDER, beard=1, face=5, skin=1, height=1, build=2, pantsColor=1)),
    (5, 3, 1): ("look_12", "뽀글 파마 검정(염색)·실눈·순한 눈썹·시원한 웃음",
                dict(hair=13, hairColor=0, eyes=4, brows=6, mouth=6, wrinkle=W_EYE | W_MOUTH | W_UNDER, blush=1, skin=1, height=0, build=1, pantsColor=3)),
}

# ---------- 칸마다 허용 목록(나이 × 성별). (값, 무게) ----------
HAIR = {   # 11/10 다시 찍음: 17 투블럭(10~40대 남)·18 C컬 중단발(30~50대 여)·19 웨이브 커트(50대 이상 여)·10 바가지(어린이·10대, 가끔 어른)
    ("child", "m"): [(10, 4), (0, 3), (2, 2), (1, 2), (12, 1)],
    ("child", "f"): [(7, 3), (6, 3), (11, 3), (5, 2), (8, 1), (10, 2)],
    ("teen", "m"): [(12, 3), (17, 3), (0, 2), (14, 2), (1, 2), (10, 2), (2, 1)],
    ("teen", "f"): [(5, 3), (6, 3), (11, 3), (8, 1), (12, 1), (10, 1)],
    ("young", "m"): [(12, 3), (17, 4), (14, 3), (15, 2), (1, 3), (0, 2), (10, 1)],
    ("young", "f"): [(5, 3), (11, 3), (18, 3), (8, 2), (6, 2), (9, 1), (12, 2)],
    ("middle", "m"): [(15, 3), (1, 3), (17, 2), (0, 2), (12, 2), (14, 2), (3, 1), (4, 1), (10, 1)],
    ("middle", "f"): [(13, 3), (18, 3), (19, 3), (11, 2), (8, 2), (9, 1), (6, 1), (12, 2)],
    ("old", "m"): [(3, 2), (15, 3), (0, 2), (12, 2), (1, 2), (4, 1)],
    ("old", "f"): [(13, 3), (19, 3), (9, 2), (11, 2), (12, 3)],   # 웨이브(8)는 검정으로 염색하면 젊은 사람처럼 보여 뺌
}
HAIR_COLOR = {   # 0 검정 1 진한 갈색 2 밝은 갈색 3 회색 4 흰색 6 희끗한 검정 7 희끗한 갈색(금발 5는 풀에 안 씀)
    "child": [(0, 4), (1, 1)], "teen": [(0, 4), (1, 2)],
    # 83번 새 색: 8 애쉬 브라운·9 적갈색·10 와인(염색한 엄마·딸), 11 은발(어르신)
    ("young", "m"): [(0, 4), (1, 2)], ("young", "f"): [(1, 3), (0, 2), (2, 2), (8, 1), (9, 1)],
    ("middle", "m"): [(0, 2), (6, 3), (1, 1)], ("middle", "f"): [(1, 2), (0, 2), (7, 2), (2, 1), (9, 1), (10, 1)],
    "old_dark": [(0, 1), (1, 1)], "old_light": [(4, 3), (3, 3), (11, 2), (6, 1), (7, 1)],
}
EYES = {   # 중년은 큰 눈·왕눈·반달눈 안 씀(76번). 무쌍·무심한은 칸에서 졸려 보여 적게(81번). 84번: 숨긴 눈(2·6·9·10·15) 대신 새 눈 17~24
    # 84번 2차: 19 눈웃음 눈(다정한 엄마·할머니·아빠), 22 온화한 눈(처진 눈꼬리, 20대 이상)
    ("child", "m"): [1, 5, 7, 11, 17, 24], ("child", "f"): [1, 5, 7, 11, 12, 13, 17, 19],
    ("teen", "m"): [7, 1, 23, 14, 11, 8, 18, 24], ("teen", "f"): [7, 1, 23, 20, 11, 19, 12, 16, 13, 17],
    ("young", "m"): [7, 23, 14, 11, 22, 8, 18, 24, 21], ("young", "f"): [7, 23, 20, 11, 19, 12, 16, 13, 8, 18],
    ("middle", "m"): [7, 8, 23, 21, 22, 11, 18, 14, 19], ("middle", "f"): [7, 8, 23, 21, 19, 11, 12, 18, 20, 22],
    ("old", "m"): [4, 5, 21, 18, 11, 7, 22, 19], ("old", "f"): [4, 5, 21, 18, 11, 7, 13, 19, 22],
}
BROWS = {
    "child": [8, 0, 6, 2], "teen_m": [2, 0, 3, 4, 5, 6], "teen_f": [7, 0, 6, 2, 8],
    "young_m": [2, 3, 4, 6, 0, 5], "young_f": [7, 6, 2, 0],
    "middle_m": [3, 2, 4, 6], "middle_f": [7, 6, 2],
    "old_m": [9, 6, 3, 2], "old_f": [9, 6, 7],
}
MOUTH = {
    "child": [1, 3, 8, 0, 4], "teen_m": [0, 1, 4, 5, 6, 2], "teen_f": [0, 1, 4, 5, 7, 3],
    "young_m": [0, 4, 1, 6, 5, 2], "young_f": [0, 4, 1, 5, 7, 6],
    "middle_m": [0, 4, 6, 2, 1, 5], "middle_f": [0, 4, 1, 5, 7, 6],
    "old_m": [4, 0, 6, 1, 2, 5], "old_f": [4, 0, 1, 7, 5, 6],
}
SKIN_KR = [(0, 3), (5, 3), (1, 4), (2, 3), (6, 1)]   # 밝은·화사한·보통·따뜻한·건강한
# 뒤 화면 구릿빛·짙은(3명): (화면, 줄, 칸, 피부)
TAN = [(2, 0, 0, 3), (3, 1, 3, 4), (5, 2, 2, 3)]


def wpick(rng, opts, avoid=()):
    o = [(v, w) for v, w in opts if v not in avoid] or list(opts)
    t = rng.uniform(0, sum(w for _, w in o))
    for v, w in o:
        t -= w
        if t <= 0:
            return v
    return o[-1][0]


def deck(rng, opts, n):
    """무게대로 n장을 나눠(큰 나머지 순) 섞은 목록. 몇 명뿐인 묶음에서도 한 값으로 몰리지 않게"""
    tot = sum(w for _, w in opts)
    q = [(v, n * w / tot) for v, w in opts]
    cnt = {v: int(x) for v, x in q}
    for v, x in sorted(q, key=lambda t: -(t[1] - int(t[1])))[:n - sum(cnt.values())]:
        cnt[v] += 1
    d = [v for v, k in cnt.items() for _ in range(k)]
    rng.shuffle(d)
    return d


def hair_plan(rng):
    """칸마다 화면 1~5 머리 차례(무게대로 나눠 섞은 deck). 같은 줄 두 칸(같은 나이·성별)은 한 화면에서 서로 다르게.
    몇 명뿐인 칸에서도 무게가 실제 개수로 이어지게(예전엔 칸마다 매번 뽑아 바가지·양갈래가 첫 화면에만 나오기도 했다)"""
    plan = {}
    for r in range(4):
        types = {}
        for c in range(4):
            types.setdefault(CELLS[r][c], []).append(c)
        for t, cs in types.items():
            d = deck(rng, HAIR[t], (PAGES - 1) * len(cs))
            if len(cs) == 2:
                for _ in range(100):
                    bad = [i for i in range(0, len(d), 2) if d[i] == d[i + 1]]
                    if not bad:
                        break
                    i = bad[0]
                    j = rng.choice([k for k in range(len(d)) if d[k] != d[i]])
                    d[i], d[j] = d[j], d[i]
            for n, c in enumerate(cs):
                plan[(r, c)] = d[n::len(cs)]
    return plan


def gen_page(rng, p, used_em, hair_hist, hc_deck, hplan=None):
    """화면 p(1~5) 16명. used_em: 이미 쓴 (눈, 입). hair_hist: 칸마다 이미 쓴 머리. hc_deck: 나이 × 성별 → 머리색 차례(어르신 빼고)
    닮은꼴(LOOKS) 자리는 그 값을 그대로 두고, 한 화면 규칙의 몫(안경·듬직·염색·목도리)을 닮은꼴이 이미 채운 만큼 빼고 뽑는다"""
    cells = [(r, c) for r in range(4) for c in range(4)]
    fixed = {(r, c): {k: v for k, v in a.items() if not k.startswith("_")} for (pp, r, c), (_, _, a) in LOOKS.items() if pp == p}
    free = [x for x in cells if x not in fixed]
    fx = lambda k, f=lambda v: v: sum(1 for a in fixed.values() if f(a.get(k, 0)))
    adults = [(r, c) for r, c in free if CELLS[r][c][0] in ADULT]
    women = [(r, c) for r, c in free if CELLS[r][c][1] == "f" and r >= 1]
    men_ad = [(r, c) for r, c in adults if CELLS[r][c][1] == "m"]
    glasses = set(rng.sample(adults, max(0, 5 - fx("glasses"))))
    if rng.random() < .4:   # 어린이·10대 안경은 가끔
        glasses.add(rng.choice([x for x in free if x[0] == 0]))
    sturdy_f = set(rng.sample([x for x in women if x[0] >= 2] + [x for x in women if x[0] == 1][:1],
                              2 - sum(a.get("build") == 2 for (r, c), a in fixed.items() if CELLS[r][c][1] == "f")))
    beard = {rng.choice(men_ad)} if not fx("beard") or rng.random() < .3 else set()
    if rng.random() < .3:
        beard.add(rng.choice(men_ad))
    old_free = [x for x in free if x[0] == 3]
    dyed = set(rng.sample(old_free, 2 - sum(a.get("hairColor") in (0, 1) for (r, c), a in fixed.items() if r == 3)))
    shaped = set(rng.sample([x for x in free if x[0] >= 1] + [x for x in free if x in ((0, 2), (0, 3))], 5 - fx("face", lambda v: bool(v) and v != 5)))   # 85번 5 넓은 얼굴(둥근 바탕)은 둥근형처럼 셈(뽑는 차례 그대로)
    scarf = None if fx("acc") else rng.choice([x for x in adults if x[0] >= 2])
    out = dict(fixed)
    for r, c in free:
        age, sex = CELLS[r][c]
        k = f"{age}_{sex}"
        a = {}
        row_hair = {out[(r, j)]["hair"] for j in range(4) if (r, j) in out}
        hopts = HAIR[(age, sex)]
        # 머리: 칸 차례(hair_plan)대로. 같은 줄에 이미 있으면 같은 줄에 없는 것·이 칸에서 덜 쓴 것부터
        want_h = hplan[(r, c)][p - 1] if hplan else None
        if want_h is not None and want_h not in row_hair:
            a["hair"] = want_h
        else:
            cand = [(v, w / (1 + 2 * hair_hist[(r, c)].count(v))) for v, w in hopts if v not in row_hair]
            a["hair"] = wpick(rng, cand)
        if (r, c) in shaped:
            sq_ok = sex == "m" and a["hair"] not in NO_SQUARE and age != "teen"
            # 83번 5단계: 2 각진·4 조금 각진 / 1 갸름·3 조금 갸름
            a["face"] = rng.choice([2, 4]) if sq_ok and rng.random() < .7 else rng.choice([1, 3])
        if age == "old":
            a["hairColor"] = wpick(rng, HAIR_COLOR["old_dark" if (r, c) in dyed else "old_light"])
        else:
            a["hairColor"] = hc_deck[(age, sex)][p - 1 if r == 0 else (p - 1) * 2 + c // 2]
        # 눈·입: 풀 전체에서 겹치지 않게
        for _ in range(200):
            e, m = rng.choice(EYES[(age, sex)]), rng.choice(MOUTH.get(k) or MOUTH[age])
            if (e, m) not in used_em:
                break
        else:
            raise RuntimeError(f"눈+입 다 씀 {k}")
        used_em.add((e, m))
        a["eyes"], a["mouth"] = e, m
        a["brows"] = rng.choice(BROWS.get(k) or BROWS[age])
        if a["hair"] == 2 and a["brows"] == 5:   # 세운 머리 + 올라간 눈썹(+ 건강한 피부)은 외국 아이처럼 보임(81번 4장)
            a["brows"] = 2
        a["nose"] = 2 if sex == "m" and (age in ("middle", "old") or (age == "young" and rng.random() < .4)) else 0
        if age == "middle":
            a["wrinkle"] = W_MOUTH | (W_UNDER if rng.random() < .55 else W_EYE)
        elif age == "old":
            a["wrinkle"] = rng.choice([W_EYE | W_FORE | W_MOUTH, W_EYE | W_MOUTH | W_UNDER, W_EYE | W_FORE | W_MOUTH | W_UNDER])
        a["blush"] = 1 if age == "child" or (sex == "f" and rng.random() < .8) or (age == "teen" and rng.random() < .3) else 0
        if (r, c) in beard:
            a["beard"] = 1 if age == "young" else rng.choice([1, 2]) if age == "middle" else rng.choice([2, 2, 1])   # 긴 수염은 산타처럼 보여 풀에 안 씀
        if (r, c) in glasses:
            a["glasses"] = rng.choice([1, 2]) if age != "old" else rng.choice([1, 2, 3] if sex == "f" else [1, 2])
            # 테 색(83번): 어르신은 금테·은테가 흔하고, 젊을수록 검정·갈색 뿔테
            a["glassesColor"] = wpick(rng, [(0, 2), (1, 1), (2, 2), (3, 2)] if age == "old" else [(0, 3), (1, 2), (2, 1), (3, 1)])
        a["skin"] = wpick(rng, SKIN_KR)
        a["height"] = {"child": 0, "teen": 1, "young": 2 if sex == "m" else rng.choice([1, 1, 0]),
                       "middle": rng.choice([2, 2, 1]) if sex == "m" else rng.choice([1, 1, 0]), "old": 1 if sex == "m" else 0}[age]
        if sex == "f":
            a["build"] = 2 if (r, c) in sturdy_f else rng.choice([1, 1, 0, 3]) if age in ("teen", "young") else rng.choice([1, 1, 4])
        else:
            a["build"] = {"child": 1, "teen": rng.choice([1, 1, 0, 3]), "young": rng.choice([1, 1, 2, 0, 3, 4]),
                          "middle": rng.choice([2, 1, 4]), "old": rng.choice([1, 2, 1, 4])}[age]
        if (r, c) == scarf:
            a["acc"] = 1
        a["pantsColor"] = wpick(rng, [(0, 4), (1, 2), (2, 2), (3, 2), (4, 1)])   # 바지 색(광장 몸 전체에서 보임)
        out[(r, c)] = a
    for (r, c), a in out.items():
        if a["hair"] == 2 and a["skin"] == 6 and (r, c) not in fixed:
            a["skin"] = 1
    for (r, c), a in out.items():   # 85번: 듬직한 어른 중 둥근 얼굴은 넓은 얼굴로(얼굴 칸에서도 몸집이 보이게). 무작위 안 씀 → 다른 값 그대로
        if (r, c) not in fixed and a.get("build") == 2 and not a.get("face") and CELLS[r][c][0] in ADULT:
            a["face"] = 5
    for tp, tr, tc, ts in TAN:
        if tp == p:
            assert (tr, tc) not in fixed
            out[(tr, tc)]["skin"] = ts
    return [out[(r, c)] for r, c in cells]


def page_ok(page):
    """한 화면 규칙(83번 4장). 틀린 규칙 이름 목록"""
    bad = []
    who = [(CELLS[i // 4][i % 4], a) for i, a in enumerate(page)]
    g = lambda a, k: a.get(k, 0)
    old = [a for (ag, _), a in who if ag == "old"]
    if sum(g(a, "hairColor") in (0, 1) for a in old) != 2: bad.append("염색 어르신 2")
    ad = [a for (ag, _), a in who if ag in ADULT]
    if not 4 <= sum(g(a, "glasses") > 0 for a in ad) <= 6: bad.append("성인 안경 4~6")
    if sum(g(a, "build") == 2 for (ag, s), a in who if s == "f") != 2: bad.append("여자 듬직 2")
    if sum(g(a, "face") != 0 for a in page) < 4: bad.append("얼굴형 4")
    if not any(g(a, "beard") for (ag, s), a in who if ag in ADULT and s == "m"): bad.append("수염 1")
    if len({g(a, "skin") for a in page}) < 4: bad.append("피부 4")
    if len({(g(a, "eyes"), g(a, "mouth")) for a in page}) != 16: bad.append("눈+입")
    for r in range(4):
        if len({g(page[r * 4 + c], "hair") for c in range(4)}) != 4: bad.append(f"{r}줄 머리")
    if any(g(a, "face") in (2, 6) and g(a, "hair") in NO_SQUARE for a in page): bad.append("각진형 가발")
    if sum(g(a, "acc") == 1 for a in page) != 1: bad.append("목도리 1")
    return bad


# 11/10 수염 4(짧은 수염 + 콧수염): 규칙으로 찍은 뒤 이 자리 사람만 바꾼다(무작위 순서는 그대로라 다른 사람 값은 안 바뀜). (화면, 줄, 칸)
BEARD_BOTH = [(1, 2, 0)]


def build():
    rng = random.Random(831110)
    pages = [[{k: v for k, v in a.items() if not k.startswith("_")} for _, a in FIRST]]
    assert not page_ok(pages[0]), page_ok(pages[0])
    used_em = {(a.get("eyes", 7), a.get("mouth", 0)) for a in pages[0]}
    looks_em = [(a["eyes"], a["mouth"]) for _, _, a in LOOKS.values()]
    assert len(set(looks_em)) == len(looks_em) and not used_em & set(looks_em), "닮은꼴 눈+입 겹침"
    used_em |= set(looks_em)   # 닮은꼴 자리는 미리 잡아 둔다(다른 사람이 같은 얼굴을 먼저 가져가지 않게)
    hair_hist = {(i // 4, i % 4): [a["hair"]] for i, a in enumerate(pages[0])}
    hc_deck = {(age, sex): deck(rng, HAIR_COLOR.get((age, sex)) or HAIR_COLOR[age], (PAGES - 1) * (1 if age in ("child", "teen") else 2))
               for row in CELLS for age, sex in row if age != "old"}
    hplan = hair_plan(rng)
    for p in range(1, PAGES):
        for _ in range(400):
            u = set(used_em)
            pg = gen_page(rng, p, u, hair_hist, hc_deck, hplan)
            for (pp, r, c), (_, _, la) in LOOKS.items():
                if pp == p:
                    assert all(pg[r * 4 + c].get(k) == v for k, v in la.items() if not k.startswith("_")), "닮은꼴 자리 바뀜"
            if not page_ok(pg):
                used_em = u
                break
        else:
            raise RuntimeError(f"화면 {p} 규칙 못 맞춤")
        for i, a in enumerate(pg):
            hair_hist[(i // 4, i % 4)].append(a["hair"])
            if (p, i // 4, i % 4) in BEARD_BOTH:
                assert a.get("beard") in (1, 2), ("짧은 수염 + 콧수염 자리는 수염 있는 사람", p, i)
                a["beard"] = 4
        pages.append(pg)
    # 대표색(추천): 옆 칸·윗 칸과 겹치지 않게(가로 +1, 세로 +4, 화면 +1)
    rows = []
    for p, pg in enumerate(pages):
        for i, a in enumerate(pg):
            r, c = divmod(i, 4)
            age, sex = CELLS[r][c]
            color = (4 * r + c + p) % 8
            want_c = (FIRST[i][1] if p == 0 else LOOKS.get((p, r, c), (0, 0, {}))[2]).get("_color")
            if want_c is not None:   # 닮은꼴 추천 대표색: 왼쪽·위 칸과 겹치면 안 씀
                left = (4 * r + c - 1 + p) % 8 if c else None
                up = (4 * (r - 1) + c + p) % 8 if r else None
                right = (4 * r + c + 1 + p) % 8 if c < 3 else None
                down = (4 * (r + 1) + c + p) % 8 if r < 3 else None
                assert want_c not in (left, up, right, down), ("닮은꼴 대표색 옆 칸과 겹침", p, r, c)
                color = want_c
            if a.get("acc") == 1:
                a["scarfColor"] = a.get("scarfColor", (color + 3) % 8)
                if a["scarfColor"] == color:
                    a["scarfColor"] = (color + 3) % 8
            n = p + 1 if r == 0 else p * 2 + c // 2 + 1
            want = FIRST[i][0] if p == 0 else ("닮은꼴 %s: %s" % LOOKS[(p, r, c)][:2] if (p, r, c) in LOOKS else "")
            rows.append((r, c, p, f"{age}_{sex}{n}", age, sex, color, want, a))
    return rows


ORDER = ["hair", "hairColor", "eyes", "brows", "nose", "mouth", "wrinkle", "blush", "beard", "glasses", "face", "skin", "height", "build",
         "acc", "scarfColor", "glassesColor", "pantsColor", "mark"]


def render(rows):
    L = ["# >>> who_pool_gen.py 가 만든 값(손으로 고치지 말 것: who_pool_gen.py 를 고치고 다시 돌린다)",
         "# (줄, 칸, 화면, id, 나이, 성별, 추천 대표색, 메모, 부품). 첫 화면(화면 0)은 손으로 고른 16명",
         "WHO_DATA = ["]
    for r, c, p, i, age, sex, color, want, a in rows:
        kv = ", ".join(f"{k}={a[k]}" for k in ORDER if k in a)
        L.append(f'    ({r}, {c}, {p}, "{i}", "{age}", "{sex}", {color}, "{want}", dict({kv})),')
    L.append("]")
    L.append("# <<< who_pool_gen.py")
    return "\n".join(L)


def main():
    block = render(build())
    path = os.path.join(HERE, "avatar.py")
    src = open(path, encoding="utf-8").read()
    pat = re.compile(r"# >>> who_pool_gen\.py.*?# <<< who_pool_gen\.py", re.S)
    if "--check" in sys.argv:
        m = pat.search(src)
        ok = bool(m) and m.group(0) == block
        print("같음" if ok else "다름")
        sys.exit(0 if ok else 1)
    new = pat.sub(lambda _: block, src) if pat.search(src) else src.replace("# @@WHO_DATA@@", block)
    open(path, "w", encoding="utf-8").write(new)
    print("avatar.py WHO_DATA", len(build()), "명")


if __name__ == "__main__":
    main()
