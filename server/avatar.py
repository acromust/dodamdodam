"""캐릭터 설정값(서버·웹·차 공통). 부품 이름·순서는 research/uiux_1107/ui/56_character_rules.md 표, 색 값은 59번 명세 1절 그대로.

서버에는 사람마다 작은 정수 설정값만 둔다: avatar(부품 칸들, KEYS) + color(대표색 0~7, 같은 차 안에서 겹치지 않게).
범위 밖·정수가 아닌 값은 거부한다(clean). 모르는 칸은 버린다.
"""

# 부품: (칸 이름, 옵션 이름들). 인덱스 = 옵션 번호. 순서를 바꾸면 저장된 값의 뜻이 바뀌므로 뒤에만 붙인다.
PARTS = [
    # 이름은 생김새만 담백하게. 머리숱·체형 등을 낮추거나 놀리는 느낌의 말은 쓰지 않는다(11/08 사용자)
    ("hair", ["스포츠머리", "옆가르마", "세운 머리", "옆머리", "민머리",
              "긴 생머리", "포니테일", "양갈래", "웨이브", "올림머리",
              "일자 앞머리", "단발", "숏컷", "파마",
              # 11/09 Meshy 가발로 바꾸며 뒤에만 붙임(차 앱 노드 hair_m_ez·hair_m_man50·hair_m_allback)
              "애즈펌", "2:8 가르마", "올백",
              # 11/10 83번 (c) Meshy 가발 3개 뒤에만 붙임(차 앱 노드 hair_m_twoblock·hair_w_ccurl·hair_w_wavecut). 10 일자 앞머리는 같은 번호에 앞머리를 둥글게 다시 만듦
              "투블럭", "C컬 중단발", "웨이브 커트",
              # 11/10 짧은 스포츠머리(뒤에만, 차 앱 노드 hair_m_buzz): 짧게 깎아 세운 뾰족 머리
              "짧은 스포츠머리"]),
    # 11/10 추가(뒤에만): 희끗한 검정·희끗한 갈색(76번 중년). 웹 3D는 짙은 머리에 흰 가닥이 섞인 무늬(HAIR_SALT), 눈썹·차는 섞인 평균색
    # 11/10 83번(뒤에만): 염색한 엄마·딸 색(애쉬 브라운·적갈색·와인)과 은발. 수염색도 같은 12가지
    ("hairColor", ["검정", "진한 갈색", "밝은 갈색", "회색", "흰색", "금발", "희끗한 검정", "희끗한 갈색", "애쉬 브라운", "적갈색", "와인", "은발"]),
    # 11/10 76번 B: 7~13 새로(뒤에만). 6은 이름만 바꿈(순한 눈 → 차분한 눈, 그림은 그대로), 2는 같은 번호에 다시 그린 그림.
    # 0 동그란 눈·3 긴 눈은 고르는 칸(PICK)에서만 숨긴다. 이미 저장된 값은 upgrade()가 0 → 7 또렷한 눈, 3 → 1 큰 눈으로 옮긴다
    # 11/10 79번: 눈을 '흰자 + 눈동자 + 윗눈꺼풀'로 다시 그림(78번, 번호 뜻 그대로). 14 무쌍·15 애교살·16 도도한 눈을 뒤에 붙임
    ("eyes", ["동그란 눈", "큰 눈", "작은 눈", "긴 눈", "실눈", "반달눈", "차분한 눈",
              "또렷한 눈", "날렵한 눈", "쌍꺼풀 눈", "고양이 눈", "강아지 눈", "속눈썹 눈", "속눈썹 반달눈",
              "무쌍 눈", "애교살 눈", "도도한 눈",
              # 11/10 84번(뒤에만): Mii·Tomodachi 처럼 선·모양으로 개성을 내는 눈 8(굵은 윤곽·날개 라이너·각진 눈·곁눈). 그림은 dev_parts_1110d
              # 2 작은·6 차분한·9 쌍꺼풀·10 고양이·15 애교살은 고르는 칸에서 숨기고 비슷한 눈으로 옮긴다(MOVED)
              # 84번 2차(사장 "라이너·날카로운 누가 쓰냐"): 19 라이너 → 눈웃음 눈, 22 날카로운 → 온화한 눈(같은 번호에 다시 그림, 저장값 그대로)
              "왕눈", "아몬드 눈", "눈웃음 눈", "아래 속눈썹 눈", "무심한 눈", "온화한 눈", "진한 쌍꺼풀 눈", "곁눈"]),
    # 79번: 1 아치는 고르는 칸에서 숨기고(→ 7 가는 눈썹), 9 긴 꼬리 눈썹(어르신)을 뒤에 붙임
    ("brows", ["짧은 눈썹", "아치 눈썹", "일자 눈썹", "숱 많은 눈썹", "각진 눈썹", "올라간 눈썹", "순한 눈썹", "가는 눈썹", "동글 눈썹",
               "긴 꼬리 눈썹"]),
    # 79번: 1 동그란 코는 고르는 칸에서 숨김(→ 0 작은 코)
    ("nose", ["작은 코", "동그란 코", "넓은 코"]),
    # 2는 같은 번호에 다시 그린 '꾹 다문 입'(예전 다문 입보다 짧고 조금 굵게)
    ("mouth", ["미소", "활짝 웃음", "꾹 다문 입", "동그란 입", "잔잔한 미소", "한쪽 미소", "시원한 웃음", "분홍 입술", "메롱"]),
    # 주름 = 비트 합 0~15(웹은 네 칸을 따로 켜고 끈다): 1 눈가 + 2 이마 + 4 입가 + 8 눈 밑. 예전 0~3은 뜻 그대로. 이름은 WRINKLE_BITS로 만든다
    ("wrinkle", None),
    ("blush", ["없음", "볼터치"]),
    # 11/10(뒤에만): 4 = 짧은 수염(얼굴 그림) + 콧수염(3D)을 같이. 1·2 뜻 그대로
    ("beard", ["없음", "짧은 수염", "콧수염", "긴 수염", "짧은 수염 + 콧수염"]),
    ("glasses", ["없음", "동그란 안경", "네모 안경", "반달 안경"]),
    # 11/10 83번(뒤에만): 3 조금 갸름·4 조금 각진 = 형태 중간값 0.5. 각진형 형태가 없는 가발 6개(스포츠머리·옆머리·양갈래·일자 앞머리·파마·올백)도
    # 각진형 1.0 까지 앞·옆·뒤에서 그려 보고 얼굴이 가발을 뚫지 않아 열었다
    # 11/10 85번(뒤에만, 사장 '퉁퉁한 사람 표현이 안 돼'): 5 넓은 얼굴(볼·턱이 넓고 턱 밑이 어깨로 이어짐, 모프 face_full)·6 넓고 각진(face_full + 각진 0.7).
    # 가발 20개 모두 face_full 모프가 있고, 가장 넓은 6 으로 앞·옆·뒤를 그려 뚫리지 않음을 봤다
    ("face", ["둥근형", "갸름형", "각진형", "조금 갸름", "조금 각진", "넓은 얼굴", "넓고 각진"]),
    # 11/10 81번: 한국 사람 먼저. 0~4는 뜻을 가까운 새 색으로(노란빛 → 따뜻한, 짙은 갈색 → 짙은), 5 화사한·6 건강한을 뒤에 붙임.
    # 고르는 칸은 밝은 순서(PICK skin): 밝은·화사한·보통·따뜻한 / 건강한·구릿빛·짙은
    ("skin", ["밝은", "보통", "따뜻한", "구릿빛", "짙은", "화사한", "건강한"]),
    ("height", ["작음", "보통", "큼"]),
    ("build", ["날씬", "보통", "듬직", "조금 날씬", "조금 듬직"]),   # 83번: 3·4 = 형태 중간값 0.5(뒤에만)
    # 11/08 추가(맨 뒤에만 붙인다): 수염색. 값은 머리색 6가지와 같은 색. 예전 기록에 없으면 upgrade()가 채운다
    ("beardColor", ["검정", "진한 갈색", "밝은 갈색", "회색", "흰색", "금발", "희끗한 검정", "희끗한 갈색", "애쉬 브라운", "적갈색", "와인", "은발"]),
    # 11/09 추가(맨 뒤에만 붙인다): 소품. 차 앱 노드 scarf(1 목도리). 이어폰은 11/09 사용자 결정으로 뺐다. 예전 기록에 없으면 upgrade()가 0(없음)을 채운다
    ("acc", ["없음", "목도리"]),
    # 11/09 추가(맨 뒤에만 붙인다): 목도리 색. 값은 대표색 8가지와 같은 색(COLORS). 윗옷이 대표색이라 따로 고른다.
    # 기본 1 분홍(예전 목도리 #E58A9A와 가까움). 예전 기록에 없으면 upgrade()가 1을 채운다
    ("scarfColor", ["하늘", "분홍", "노랑", "초록", "보라", "주황", "민트", "남색"]),
    # 11/10 83번(맨 뒤에만): 안경테 색(재질 glasses 에 색 입히기). 0 검정 = 예전 테 색. 예전 기록에 없으면 upgrade()가 0을 채운다
    ("glassesColor", ["검정", "갈색 뿔테", "금테", "은테"]),
    # 11/10 83번(맨 뒤에만): 바지 색(재질 pants). 0 청바지 파랑 = 예전 바지 색(#5B6370)과 가까움. 예전 기록에 없으면 upgrade()가 0을 채운다
    ("pantsColor", ["청바지 파랑", "베이지", "검정", "회색", "카키"]),
    # 11/10 83번 5절 (b)(맨 뒤에만): 점. 얼굴 그림 face_atlas groups.mark(GPT 점 시트). 점은 한쪽 볼에만, 주근깨는 두 볼. 예전 기록에 없으면 upgrade()가 0(없음)을 채운다
    ("mark", ["없음", "눈 밑 점", "입가 점", "볼 점", "주근깨"]),
    # 11/10 사장 '수염은 턱수염·콧수염 둘 다, 점은 여러 개·좌우 하나씩'(맨 뒤에만): 여러 개 켜고 끄는 비트 칸. 그리는 건 이 두 칸만 본다.
    # 예전 beard(0~4)·mark(0~4)는 그대로 두고(예전 기록·예전 화면이 보낸 값) 읽을 때·받을 때 새 칸으로 옮긴다(BEARD_OLD·MARK_OLD). 저장할 땐 둘을 맞춰 둔다
    ("beards", None),
    ("marks", None),
]
WRINKLE_BITS = ["눈가", "이마", "입가", "눈 밑"]   # 비트 1·2·4·8(face_atlas.json names.wrinkle_bits 와 같은 순서)
BEARD_BITS = ["짧은 수염", "콧수염", "턱수염"]       # 비트 1·2·4. 턱수염 = 예전 긴 수염(3D beard_long)
# 점 비트 1~64. 왼쪽·오른쪽 = 화면에서 보는 쪽(예전 한쪽 점은 왼쪽에 그렸다)
MARK_BITS = ["눈 밑 점 왼쪽", "눈 밑 점 오른쪽", "입가 점 왼쪽", "입가 점 오른쪽", "볼 점 왼쪽", "볼 점 오른쪽", "주근깨"]
BEARD_OLD = {0: 0, 1: 1, 2: 2, 3: 4, 4: 1 | 2}         # 예전 beard → beards(같은 모습)
MARK_OLD = {0: 0, 1: 1, 2: 4, 3: 16, 4: 64}           # 예전 mark → marks(예전 점은 왼쪽)


def _bit_names(bits, sep, tail=""):
    return ["없음"] + [sep.join(n for b, n in enumerate(bits) if v >> b & 1) + tail for v in range(1, 1 << len(bits))]


def _wrinkle_names():
    return _bit_names(WRINKLE_BITS, "·", " 주름")


# 11/10 사장 '콧수염과 턱수염 두 개는 같이 되는 이유가 없어': 턱수염 3D(beard_long)에 콧수염 모양이 붙어 있다. 콧수염(2)·턱수염(4)은 둘 중 하나만
# (고르는 칸에서 하나를 켜면 다른 하나가 꺼진다, 웹 ONE_OF). 짧은 수염(1)은 어느 쪽과도 같이 된다. 둘 다 켜진 값(예전 기록·예전 화면)은 턱수염만 남긴다
BEARD_MUS, BEARD_LONG = 2, 4


def beards_fix(bits):
    """콧수염 + 턱수염이 둘 다 켜져 있으면 턱수염만 남긴다(같은 모습: 턱수염 3D 에 콧수염이 붙어 있다)"""
    return bits & ~BEARD_MUS if bits & BEARD_LONG and bits & BEARD_MUS else bits


def beard_of(bits):
    """beards 비트 → 예전 beard 하나(예전 화면·예전 차 앱이 읽는 값). 턱수염이 있으면 긴 수염"""
    return 3 if bits & 4 else 4 if bits & 3 == 3 else 2 if bits & 2 else 1 if bits & 1 else 0


def mark_of(bits):
    """marks 비트 → 예전 mark 하나(켜진 것 중 첫 종류)"""
    return 1 if bits & 3 else 2 if bits & 12 else 3 if bits & 48 else 4 if bits & 64 else 0


_NAMES = {"wrinkle": _wrinkle_names, "beards": lambda: _bit_names(BEARD_BITS, " + "), "marks": lambda: _bit_names(MARK_BITS, "·")}
PARTS = [(k, _NAMES[k]() if v is None else v) for k, v in PARTS]
assert dict(PARTS)["wrinkle"][:4] == ["없음", "눈가 주름", "이마 주름", "눈가·이마 주름"]   # 예전 0~3 이름 그대로
KEYS = [k for k, _ in PARTS]
COUNT = {k: len(v) for k, v in PARTS}

# 고르는 칸 순서(79번, 3칸 격자). 번호(저장값)와 따로 둔다. 여기 없는 번호는 고르는 칸에 안 보인다(눈 0·3, 눈썹 1, 코 1).
# 눈 18 = 3칸 × 6줄(84번: 기본·크기 / 윤곽·눈꺼풀 / 순한 눈매 / 속눈썹 / 덮인·곁눈 / 감은 눈). wrinkle 은 따로 켜고 끄는 비트 칸(눈가·이마·입가·눈 밑)
PICK = {
    "eyes": [7, 1, 17, 18, 23, 14, 11, 22, 19, 12, 20, 16, 21, 8, 24, 13, 5, 4],
    "brows": [2, 3, 9, 4, 5, 6, 7, 0, 8],
    "nose": [0, 2],
    "mouth": [0, 4, 1, 6, 5, 2, 7, 3, 8],
    "wrinkle": [1 << b for b in range(len(WRINKLE_BITS))],
    "skin": [0, 5, 1, 2, 6, 3, 4],   # 81번: 밝은 순서(웹 피부색 동그라미 줄 순서)
    # 83번: 머리색 12 = 4칸 × 3줄(검정·갈색 / 염색 / 희끗·센 머리). 수염색 줄도 같은 순서
    "hairColor": [0, 1, 2, 8, 9, 10, 5, 6, 7, 3, 11, 4],
    # 83번: 체형·얼굴형 5단계는 한쪽 끝에서 다른 끝 순서(가운데가 보통·둥근)
    "build": [0, 3, 1, 4, 2],
    "face": [1, 3, 0, 4, 2, 5, 6],   # 85번: 5단계 줄 아래에 넓은 얼굴·넓고 각진
    # 11/10 수염·점은 주름처럼 따로 켜고 끄는 비트 칸. 점은 2칸 × 4줄(왼쪽·오른쪽 짝, 맨 아래 주근깨)
    "beards": [1 << b for b in range(len(BEARD_BITS))],
    "marks": [1 << b for b in range(len(MARK_BITS))],
}
# 고르는 칸에서 뺀 부품 → 비슷한 부품(76번 B·79번). 저장된 값은 읽을 때(upgrade)·받을 때(clean) 옮긴다. 옮기기 전 기록도 범위 안이라 valid()
# 84번 눈: 2 작은 → 7 또렷한(같은 모양, 크기만), 6 차분한 → 21 무심한(덮인 눈꺼풀), 9 쌍꺼풀 → 23 진한 쌍꺼풀, 10 고양이 → 16 도도한(올라간 꼬리, 84번 2차), 15 애교살 → 1 큰 눈(79번 6절)
MOVED = {"eyes": {0: 7, 3: 1, 2: 7, 6: 21, 9: 23, 10: 16, 15: 1}, "brows": {1: 7}, "nose": {1: 0}}
EYES_MOVED = MOVED["eyes"]
assert all(sorted(PICK[k] + list(MOVED.get(k, {}))) == list(range(COUNT[k])) for k in ("eyes", "brows", "nose", "mouth", "skin"))
assert all(v in PICK[k] for k, m in MOVED.items() for v in m.values())
assert sorted(PICK["hairColor"]) == list(range(COUNT["hairColor"]))

HAIR_COLORS = [("검정", "#2B2522"), ("진한 갈색", "#4A3226"), ("밝은 갈색", "#8A5A3C"),
               ("회색", "#A9A6A2"), ("흰색", "#EDEBE7"), ("금발", "#E2B85A"),
               ("희끗한 검정", "#5E5A58"), ("희끗한 갈색", "#7A6F68"),   # 11/10: 76번 값. hex = 섞인 평균색(눈썹·짧은 수염·차·색 동그라미)
               ("애쉬 브라운", "#6E6259"), ("적갈색", "#7B3A24"), ("와인", "#6A2639"), ("은발", "#C5CCD6")]   # 83번(조명 아래 채도가 빠져 실제보다 진하게)
# 희끗한 머리(머리색 번호 → 바탕색·희끗한 자리 색·비율(지금 안 씀)). 웹 3D 가발·수염은 관자놀이·귀밑·뒷머리만 이 색 쪽으로 밝힌다(avatar3d.js, 77번).
# 바탕은 검정·진한 갈색 그대로라 같은 사람이 '희끗'만 바꿔 볼 수 있다
HAIR_SALT = {6: ("#2B2522", "#C9CBCC", 0.28), 7: ("#4A3226", "#CDC7C1", 0.28)}   # 77번: 찬 회색(빛 반사가 아니라 센 머리로 읽히게)
assert [n for n, _ in HAIR_COLORS] == dict(PARTS)["hairColor"] == dict(PARTS)["beardColor"]
# 11/10 81번: 예전 색은 조명 아래 회색빛·누런빛으로 보여 복숭아·장밋빛·꿀빛 쪽으로 다시 고름(웹 3D로 나란히 그려 보고 고름).
# 밝기 순서: 밝은 0 > 화사한 5 > 보통 1 > 따뜻한 2 > 건강한 6 > 구릿빛 3 > 짙은 4. 얼굴 그림 skin_t [0.40, 0.89] 밖은 끝값으로(밝은 0.91·짙은 0.37)
SKINS = [("밝은", "#FFE0CC"), ("보통", "#F9C9AA"), ("따뜻한", "#F4C49E"), ("구릿빛", "#B8774F"), ("짙은", "#85503A"),
         ("화사한", "#FFD5C0"), ("건강한", "#DA9E74")]
assert [n for n, _ in SKINS] == dict(PARTS)["skin"]
# 대표색(color 0~7): 쿠션·옷·재생 패널 얼굴 칸. 같은 차 안에서 겹치지 않는다
COLORS = [("하늘", "#5AA9F0"), ("분홍", "#F08AAE"), ("노랑", "#F5C842"), ("초록", "#7CC36B"),
          ("보라", "#A98BE8"), ("주황", "#F49A4A"), ("민트", "#5FD0B5"), ("남색", "#3F5BA9")]  # 8번: 11/08 회색 → 남색(빈 쿠션 회색 #B9BCC2·하늘·보라와 구분, 결정 C12). 저장값 7은 그대로 남색으로 보인다
NCOLORS = len(COLORS)
assert [n for n, _ in COLORS] == dict(PARTS)["scarfColor"]   # 목도리 색 이름 = 대표색 이름(같은 순서)
# 83번: 안경테 4·바지 5. 3D 재질 색에 곱한다(웹 avatar3d.js dress, 차 PlazaView.dress). 0 = 예전 모습
GLASSES_COLORS = [("검정", "#2B2523"), ("갈색 뿔테", "#6B3F22"), ("금테", "#C9A04A"), ("은테", "#B8BEC6")]
PANTS_COLORS = [("청바지 파랑", "#50637F"), ("베이지", "#CDB89A"), ("검정", "#2E3036"), ("회색", "#8A8E95"), ("카키", "#6E6B4A")]
assert [n for n, _ in GLASSES_COLORS] == dict(PARTS)["glassesColor"] and [n for n, _ in PANTS_COLORS] == dict(PARTS)["pantsColor"]

MAX_PEOPLE = 5   # 차 한 대에 연결되는 사람(광장 쿠션 1~5)


def _beard_color(hairColor, beard):
    """수염색이 없던 때의 모습 그대로: 긴 수염(3)은 흰색, 나머지는 머리색."""
    return 4 if beard == 3 else hairColor


SCARF_DEFAULT = 1   # 목도리 색 기본: 분홍


def _a(hair, hairColor, eyes, brows, nose, mouth, wrinkle, blush, beard, glasses, face, skin, height, build, beardColor=None, acc=0,
       scarfColor=SCARF_DEFAULT, glassesColor=0, pantsColor=0, mark=0):
    return dict(hair=hair, hairColor=hairColor, eyes=eyes, brows=brows, nose=nose, mouth=mouth, wrinkle=wrinkle,
                blush=blush, beard=beard, glasses=glasses, face=face, skin=skin, height=height, build=build,
                beardColor=_beard_color(hairColor, beard) if beardColor is None else beardColor, acc=acc,
                scarfColor=scarfColor, glassesColor=glassesColor, pantsColor=pantsColor, mark=mark,
                beards=BEARD_OLD[beard], marks=MARK_OLD[mark])


# 주름 비트(읽기 쉽게)
W_EYE, W_FORE, W_MOUTH, W_UNDER = 1, 2, 4, 8

# 시작 프리셋 8: 어린이·청년·중년·노년 × 남·여(생김새는 style_refs/PRESET8.png 참고). 지금 첫 화면은 아래 POOL, 이 8개는 예전 id·기본 캐릭터용.
# 얼굴형(face)은 모두 0 둥근형(11/09 사용자: 기본 얼굴은 동글). 이미 저장된 캐릭터는 그대로 둔다.
# 11/10 76번 새 부품으로 다시 맞춤: 청년과 중년은 머리 모양이 아니라 얼굴(입가·눈 밑 선, 또렷한·날렵한 눈, 굵은 눈썹)과 희끗한 머리색으로 갈린다.
# 표시 이름(label)은 나이대만 쓴다. 관계 호칭(아들·엄마 등)은 쓰지 않는다. color는 추천 대표색(이미 쓰인 색이면 빈 색 중 첫 번째)
PRESETS = [
    #                                                                      hair hc eyes brows nose mouth wrinkle blush beard glasses face skin height build
    {"id": "child_m", "label": "어린이", "sex": "m", "color": 0, "avatar": _a(10, 1, 1, 8, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1)},
    {"id": "young_m", "label": "청년", "sex": "m", "color": 1, "avatar": _a(1, 1, 7, 5, 0, 0, 0, 0, 0, 0, 0, 1, 2, 1)},
    {"id": "middle_m", "label": "중년", "sex": "m", "color": 2, "avatar": _a(15, 6, 8, 3, 2, 6, W_MOUTH | W_UNDER, 0, 1, 2, 0, 1, 2, 2)},
    {"id": "old_m", "label": "노년", "sex": "m", "color": 3, "avatar": _a(3, 4, 5, 3, 2, 4, W_EYE | W_FORE | W_MOUTH, 1, 3, 1, 0, 1, 1, 2)},
    {"id": "child_f", "label": "어린이", "sex": "f", "color": 4, "avatar": _a(7, 1, 1, 0, 0, 3, 0, 1, 0, 0, 0, 0, 0, 1)},
    {"id": "young_f", "label": "청년", "sex": "f", "color": 5, "avatar": _a(6, 2, 12, 7, 0, 7, 0, 1, 0, 0, 0, 0, 1, 0)},
    {"id": "middle_f", "label": "중년", "sex": "f", "color": 6, "avatar": _a(8, 7, 23, 7, 0, 4, W_EYE | W_MOUTH, 1, 0, 3, 0, 1, 1, 1)},
    {"id": "old_f", "label": "노년", "sex": "f", "color": 7, "avatar": _a(13, 3, 5, 6, 0, 0, W_EYE | W_MOUTH | W_UNDER, 1, 0, 1, 0, 1, 0, 1)},
]

# ---------- '나와 닮은 모습' 고르기 묶음(76번 D절 → 11/10 81번 4칸) ----------
# 화면(11/10 사용자 "남녀 둘둘씩으로 4개, 구분 없애"): 4칸 × 3줄, 줄 이름 없음. 줄마다 남·여·남·여(번갈아).
#   1줄 = 어린이 남·어린이 여·청년 남·청년 여, 2줄 = 중년, 3줄 = 어르신(위에서 아래로, 왼쪽에서 오른쪽으로 나이 순).
# 줄마다 4명씩 짜 둔 묶음(WHO_ROWS)이 여럿. 첫 화면은 줄마다 첫 묶음, [다른 얼굴 보기]는 줄마다 지금과 다른 묶음(안 본 조합부터).
# 81번: 한국 가족 먼저(피부·머리색·머리 모양 규칙은 POOL 위 주석). 같은 눈+입 조합은 묶음에 나오는 사람 안에서 두 번 안 쓴다(tests/reg.py c_presets 가 확인).
# sex = 남(m)·여(f). 화면에는 안 쓰고 묶음 순서(남·여·남·여)를 맞추는 데만 쓴다(서버 안 메모).
# want = 76번 A·D 표에서 이 사람에게 준 얼굴 부품(메모). 숨긴 눈(0 동그란·3 긴)은 안 쓴다.
# 나이는 얼굴로 읽히게(76번 A '중년이 어려운 이유와 해법'):
#   어린이·청년 = 주름 없음, 어린이는 큰 눈·반달눈·동글 눈썹·동그란 입·메롱 쪽.
#   중년 = 9명 모두 입가 주름 + 선 하나 더(눈 밑 선 또는 눈가 주름, 무뚝뚝한 한 명만 이마 — 이마는 어르신 쪽 선),
#          큰 눈·반달눈 대신 또렷한·날렵한·쌍꺼풀·차분한·고양이·강아지·속눈썹 눈, 굵은 눈썹(숱 많은·각진·일자) 위주, 아빠 4명은 희끗한 검정·엄마 한 명은 희끗한 갈색.
#   어르신 = 흰·회색 머리 + 눈가·이마·입가 주름(셋 이상), 실눈·반달눈·차분한·작은 눈.
AGES = [("child", "어린이"), ("teen", "10대"), ("young", "청년"), ("middle", "중년"), ("old", "어르신")]   # 83번: 10대를 따로(1줄 오른쪽 둘)
_AGE_N = {k: i for i, (k, _) in enumerate(AGES)}
_BASE = dict(hair=0, hairColor=0, eyes=7, brows=0, nose=0, mouth=0, wrinkle=0, blush=0, beard=0, glasses=0, face=0, skin=1,
             height=1, build=1, acc=0, scarfColor=SCARF_DEFAULT, glassesColor=0, pantsColor=0, mark=0)


def _bits(v):
    """예전 칸(beard·mark)만 적은 값에 새 비트 칸(beards·marks)을 채운다(프리셋·묶음은 예전 칸으로 적어 둔다)"""
    v.setdefault("beards", BEARD_OLD[v["beard"]]); v.setdefault("marks", MARK_OLD[v["mark"]])
    return v
_AGE_BASE = {"child": dict(height=0), "teen": {}, "young": {}, "middle": {}, "old": {}}
BASE_AVATAR = {k: _bits(dict(_BASE, beardColor=_beard_color(_BASE["hairColor"], _BASE["beard"])))[k] for k in KEYS}   # [처음부터] 기본형


def _p(age, n, vibe, want, sex, **kw):
    v = dict(_BASE, **_AGE_BASE[age], **kw)
    if "beardColor" not in kw:
        v["beardColor"] = _beard_color(v["hairColor"], v["beard"])
    _bits(v)
    # color(추천 대표색)는 WHO_ROWS 자리로 아래에서 정한다
    return {"id": f"{age}_{n}", "age": age, "label": dict(AGES)[age], "color": 0, "sex": sex,
            "vibe": vibe, "want": want, "avatar": {k2: v[k2] for k2 in KEYS}}


POOL = [
    # 81번(11/10): 한국 가족이 먼저 자기 모습을 찾게. 피부는 밝은·화사한·보통·따뜻한(0·5·1·2), 건강한(6)은 중년 아빠 한 명만,
    # 구릿빛·짙은은 묶음에 안 넣고 만들기 화면에서 고른다. 머리색은 검정·진한 갈색(염색 갈색은 청년 여성 한 명), 중년은 희끗한, 어르신은 흰·회색.
    # 머리는 한국 가족에 흔한 모양만: 올백(16)은 묶음에 안 쓰고, 파마(13)는 중년·어르신 여성만, 세운 머리(2)는 어린이 한 명.
    # 성별은 줄마다 남·여·남·여(WHO_ROWS), 눈+입 조합은 묶음에 나오는 40명 안에서 겹치지 않는다(어느 묶음끼리 섞여 뽑혀도 같은 얼굴 없음).
    # 아래 '묶음 A·B·C' 메모는 76번 3칸 때 나눈 것. 지금 화면 묶음은 WHO_ROWS
    # 어린이(키 작음). 묶음 A: 바가지 남자아이·양갈래·단발
    _p("child", 1, "개구쟁이", "바가지 머리·큰 눈·동글 눈썹·활짝 웃음", sex="m", hair=10, eyes=1, brows=8, mouth=1, blush=1, skin=0),
    _p("child", 2, "귀여운", "양갈래·속눈썹 눈·짧은 눈썹·동그란 입", sex="f", hair=7, eyes=12, brows=0, mouth=3, blush=1, skin=5),
    _p("child", 3, "새침한", "단발·큰 눈·동글 눈썹·잔잔한 미소", sex="f", hair=11, eyes=1, brows=8, mouth=4, blush=1, skin=1),
    # 묶음 B: 포니테일·안경 쓴 남자아이·앞머리 긴 머리
    _p("child", 4, "명랑한", "포니테일·반달눈·순한 눈썹·활짝 웃음", sex="f", hair=6, eyes=5, brows=6, mouth=1, blush=1, skin=1),
    _p("child", 5, "똘똘한", "짧은 머리·안경·또렷한 눈·동그란 입", sex="m", hair=0, eyes=7, brows=2, mouth=3, glasses=1, skin=0),
    _p("child", 6, "사랑스러운", "앞머리 긴 머리·속눈썹 반달눈·동글 눈썹·미소", sex="f", hair=8, eyes=13, brows=8, mouth=0, blush=1, skin=5),
    # 묶음 C: 세운 머리·긴 생머리·숏컷
    _p("child", 7, "장난꾸러기", "세운 머리·강아지 눈·올라간 눈썹·메롱", sex="m", hair=2, eyes=11, brows=5, mouth=8, blush=1, skin=1),
    _p("child", 8, "순한", "긴 생머리·큰 눈·짧은 눈썹·미소", sex="f", hair=5, eyes=1, brows=0, mouth=0, blush=1, skin=0),
    _p("child", 9, "의젓한", "숏컷·아몬드 눈·일자 눈썹·활짝 웃음", sex="m", hair=12, hairColor=1, eyes=18, brows=2, mouth=1, skin=1),
    # 청년(주름 없음). 묶음 A: 댄디 숏컷·긴 생머리·애즈펌
    _p("young", 1, "단정한", "댄디 숏컷·아몬드 눈·일자 눈썹·미소", sex="m", hair=12, eyes=18, brows=2, mouth=0, skin=1, height=2),
    _p("young", 2, "화사한", "긴 생머리·아래 속눈썹 눈·가는 눈썹·분홍 입술", sex="f", hair=5, hairColor=1, eyes=20, brows=7, mouth=7, blush=1, face=1, skin=5, build=0),
    _p("young", 3, "쾌활한", "애즈펌·또렷한 눈·숱 많은 눈썹·시원한 웃음", sex="m", hair=14, eyes=7, brows=3, mouth=6, skin=2, height=2),
    # 묶음 B: 단발·내린 머리·옆가르마 안경
    _p("young", 4, "다정한", "단발·왕눈·가는 눈썹·미소", sex="f", hair=11, eyes=17, brows=7, mouth=0, blush=1, skin=0, build=0),
    _p("young", 5, "털털한", "짧은 머리·또렷한 눈·짧은 눈썹·활짝 웃음", sex="m", hair=0, eyes=7, brows=0, mouth=1, skin=2, height=2, build=2),
    _p("young", 6, "모범생", "옆가르마·네모 안경·진한 쌍꺼풀 눈·일자 눈썹·잔잔한 미소", sex="m", hair=1, hairColor=1, eyes=23, brows=2, mouth=4, glasses=2, skin=1, height=2),
    # 묶음 C: 염색 갈색 웨이브·포니테일·2:8 가르마
    _p("young", 7, "시크", "밝은 갈색 웨이브·도도한 눈·가는 눈썹·분홍 입술", sex="f", hair=8, hairColor=2, eyes=16, brows=7, mouth=7, face=1, skin=5, build=0),
    _p("young", 8, "발랄한", "포니테일·속눈썹 반달눈·순한 눈썹·활짝 웃음", sex="f", hair=6, hairColor=1, eyes=13, brows=6, mouth=1, blush=1, skin=1),
    _p("young", 9, "든든한", "2:8 가르마·또렷한 눈·숱 많은 눈썹·잔잔한 미소", sex="m", hair=15, eyes=7, brows=3, mouth=4, skin=2, height=2, build=2),
    # 중년(40~50대): 모두 입가 주름 + 눈 밑 선 또는 눈가 주름(이마는 한 명). 아빠는 희끗한 검정, 엄마는 진한 갈색·희끗한 갈색. 묶음 A
    _p("middle", 1, "듬직한", "2:8 가르마 희끗·네모 안경·진한 쌍꺼풀 눈·숱 많은 눈썹·시원한 웃음", sex="m", hair=15, hairColor=6, eyes=23, brows=3, nose=2, mouth=6,
       wrinkle=W_MOUTH | W_UNDER, glasses=2, skin=2, height=2, build=2),
    _p("middle", 2, "푸근한", "파마 진한 갈색·강아지 눈·순한 눈썹·잔잔한 미소", sex="f", hair=13, hairColor=1, eyes=11, brows=6, mouth=4,
       wrinkle=W_EYE | W_MOUTH, blush=1, skin=1),
    _p("middle", 3, "차분한", "단발 희끗한 갈색·또렷한 눈·가는 눈썹·미소", sex="f", hair=11, hairColor=7, eyes=7, brows=7, mouth=0,
       wrinkle=W_MOUTH | W_UNDER, face=1, skin=0),
    # 묶음 B
    _p("middle", 4, "꼼꼼한", "옆가르마 희끗·동그란 안경·또렷한 눈·일자 눈썹·꾹 다문 입", sex="m", hair=1, hairColor=6, eyes=7, brows=2, nose=2, mouth=2,
       wrinkle=W_MOUTH | W_UNDER, glasses=1, skin=1, height=2),
    _p("middle", 5, "다정한", "웨이브 진한 갈색·속눈썹 눈·가는 눈썹·잔잔한 미소", sex="f", hair=8, hairColor=1, eyes=12, brows=7, mouth=4,
       wrinkle=W_EYE | W_MOUTH, blush=1, face=1, skin=5),
    _p("middle", 6, "호탕한", "숏컷 희끗·무심한 눈·일자 눈썹·시원한 웃음", sex="m", hair=12, hairColor=6, eyes=21, brows=2, nose=2, mouth=6,
       wrinkle=W_EYE | W_MOUTH, face=2, skin=6, height=2, build=2),
    # 묶음 C
    _p("middle", 7, "상냥한", "단발 진한 갈색·아래 속눈썹 눈·순한 눈썹·미소", sex="f", hair=11, hairColor=1, eyes=20, brows=6, mouth=0,
       wrinkle=W_EYE | W_MOUTH, blush=1, skin=1),
    _p("middle", 8, "무뚝뚝한", "짧은 머리 희끗·네모 안경·무쌍 눈·숱 많은 눈썹·꾹 다문 입·이마 주름", sex="m", hair=0, hairColor=6, eyes=14, brows=3, nose=2, mouth=2,
       wrinkle=W_FORE | W_MOUTH, glasses=2, face=2, skin=2, height=2, build=2),
    _p("middle", 9, "단아한", "올림머리 진한 갈색·강아지 눈·가는 눈썹·미소", sex="f", hair=9, hairColor=1, eyes=11, brows=7, mouth=0,
       wrinkle=W_EYE | W_MOUTH, face=1, skin=0),
    # 어르신: 흰·회색 머리 + 주름 셋 이상. 묶음 A: 옆머리 할아버지·뽀글 파마 할머니·2:8 가르마 할아버지
    _p("old", 1, "인자한", "옆머리 흰머리·동그란 안경·실눈·긴 꼬리 눈썹·잔잔한 미소", sex="m", hair=3, hairColor=4, eyes=4, brows=9, nose=2, mouth=4,
       wrinkle=W_EYE | W_FORE | W_MOUTH, glasses=1, skin=1),
    _p("old", 2, "다정한", "뽀글 파마 흰머리·반달 안경·반달눈·순한 눈썹·미소", sex="f", hair=13, hairColor=4, eyes=5, brows=6, mouth=0,
       wrinkle=W_EYE | W_MOUTH | W_UNDER, blush=1, glasses=3, skin=0, height=0),
    _p("old", 3, "꼿꼿한", "2:8 가르마 회색·네모 안경·무심한 눈·긴 꼬리 눈썹·꾹 다문 입", sex="m", hair=15, hairColor=3, eyes=21, brows=9, nose=2, mouth=2,
       wrinkle=W_EYE | W_FORE | W_MOUTH, glasses=2, skin=2),
    # 묶음 B: 쪽진 할머니·단발 할머니·짧은 흰머리 할아버지
    _p("old", 4, "온화한", "올림머리 회색·실눈·순한 눈썹·미소", sex="f", hair=9, hairColor=3, eyes=4, brows=6, mouth=0,
       wrinkle=W_EYE | W_MOUTH | W_UNDER, blush=1, skin=1, height=0),
    _p("old", 5, "정갈한", "단발 흰머리·반달 안경·아몬드 눈·순한 눈썹·잔잔한 미소", sex="f", hair=11, hairColor=4, eyes=18, brows=6, mouth=4,
       wrinkle=W_EYE | W_FORE | W_MOUTH, glasses=3, skin=5, height=0),
    _p("old", 6, "호쾌한", "짧은 회색 머리·실눈·긴 꼬리 눈썹·시원한 웃음", sex="m", hair=0, hairColor=3, eyes=4, brows=9, nose=2, mouth=6,
       wrinkle=W_EYE | W_FORE | W_MOUTH, skin=2, build=2),
    # 묶음 C: 숏컷 흰머리 할아버지·파마 회색 할머니·콧수염 할아버지
    _p("old", 7, "점잖은", "숏컷 흰머리·반달눈·숱 많은 눈썹·잔잔한 미소", sex="m", hair=12, hairColor=4, eyes=5, brows=3, nose=2, mouth=4,
       wrinkle=W_EYE | W_FORE | W_MOUTH, skin=2, build=2),
    _p("old", 8, "명랑한", "파마 회색·실눈·순한 눈썹·활짝 웃음", sex="f", hair=13, hairColor=3, eyes=4, brows=6, mouth=1,
       wrinkle=W_EYE | W_MOUTH | W_UNDER, blush=1, skin=1, height=0),
    _p("old", 9, "근엄한", "옆머리 회색·동그란 안경·무쌍 눈·긴 꼬리 눈썹·콧수염·꾹 다문 입", sex="m", hair=3, hairColor=3, eyes=14, brows=9, nose=2, mouth=2,
       wrinkle=W_EYE | W_FORE | W_MOUTH | W_UNDER, beard=2, glasses=1, skin=0),
    # 11/10 4칸 개편: 줄마다 남녀 둘둘이 묶음 3개가 되게 중년 남 2·여 1, 어르신 남 1·여 2를 더함(뒤 번호로)
    _p("middle", 10, "성실한", "2:8 가르마 검정·진한 쌍꺼풀 눈·일자 눈썹·활짝 웃음", sex="m", hair=15, eyes=23, brows=2, nose=2, mouth=1,
       wrinkle=W_MOUTH | W_UNDER, face=2, skin=1, height=2),
    _p("middle", 11, "유쾌한", "아저씨 파마(애즈펌) 희끗·강아지 눈·숱 많은 눈썹·시원한 웃음", sex="m", hair=14, hairColor=6, eyes=11, brows=3, nose=2, mouth=6,
       wrinkle=W_EYE | W_MOUTH, skin=0, height=2, build=2),
    _p("middle", 12, "야무진", "묶은 머리 진한 갈색·동그란 안경·속눈썹 눈·가는 눈썹·미소", sex="f", hair=6, hairColor=1, eyes=12, brows=7, mouth=0,
       wrinkle=W_MOUTH | W_UNDER, blush=1, glasses=1, face=1, skin=0),
    _p("old", 10, "푸근한", "민머리·네모 안경·반달눈·긴 꼬리 눈썹·시원한 웃음", sex="m", hair=4, hairColor=4, eyes=5, brows=9, nose=2, mouth=6,
       wrinkle=W_EYE | W_FORE | W_MOUTH, glasses=2, skin=1, build=2),
    _p("old", 11, "고운", "단발 회색·반달눈·순한 눈썹·분홍 입술", sex="f", hair=11, hairColor=3, eyes=5, brows=6, mouth=7,
       wrinkle=W_EYE | W_MOUTH | W_UNDER, blush=1, skin=5, height=0),
    _p("old", 12, "깔끔한", "파마 흰머리·동그란 안경·아몬드 눈·순한 눈썹·한쪽 미소", sex="f", hair=13, hairColor=4, eyes=18, brows=6, mouth=5,
       wrinkle=W_EYE | W_FORE | W_MOUTH, blush=1, glasses=1, skin=0, height=0),
]
# ---------- 닮은 모습 16칸(11/10 83번 4장): 4칸 × 4줄, 칸마다 6명 = 96명 ----------
# 1줄 어린이 남·여 + 10대 남·여, 2줄 20~30대, 3줄 40~50대, 4줄 60대 이상(줄 이름 없음, 칸 순서 남·여·남·여).
# 첫 화면(화면 0) 16명은 손으로 고르고, 화면 1~5 는 who_pool_gen.py 가 칸마다 허용 목록·한 화면 규칙으로 찍어 아래에 적어 둔다
# (실행할 때 무작위로 만들지 않는다: tests/reg.py 로 검사하고, 차와 같은 값). 위 POOL 40명은 예전 id 로 들어온 값을 받으려고 둔다
# 11/10 새 눈·새 가발(투블럭·C컬 중단발·웨이브 커트·바가지 다시)로 96명을 다시 찍음. 메모 '닮은꼴 look_NN' = 한눈에 알아보는 생김새를 따라 한 12명(화면엔 얼굴만)
# >>> who_pool_gen.py 가 만든 값(손으로 고치지 말 것: who_pool_gen.py 를 고치고 다시 돌린다)
# (줄, 칸, 화면, id, 나이, 성별, 추천 대표색, 메모, 부품). 첫 화면(화면 0)은 손으로 고른 16명
WHO_DATA = [
    (0, 0, 0, "child_m1", "child", "m", 0, "바가지 머리·큰 눈·동글 눈썹·활짝 웃음", dict(hair=10, eyes=1, brows=8, mouth=1, blush=1, skin=0)),
    (0, 1, 0, "child_f1", "child", "f", 1, "양갈래·왕눈·짧은 눈썹·동그란 입", dict(hair=7, eyes=17, brows=0, mouth=3, blush=1, skin=5)),
    (0, 2, 0, "teen_m1", "teen", "m", 2, "숏컷·곁눈·일자 눈썹·미소", dict(hair=12, eyes=24, brows=2, mouth=0, face=1, skin=1)),
    (0, 3, 0, "teen_f1", "teen", "f", 3, "포니테일·속눈썹 반달눈·순한 눈썹·활짝 웃음·주근깨", dict(hair=6, hairColor=1, eyes=13, brows=6, mouth=1, blush=1, skin=1, mark=4)),
    (1, 0, 0, "young_m1", "young", "m", 4, "닮은꼴 look_04: 투블럭·눈웃음 눈·일자 눈썹·활짝 웃음·조금 각진", dict(hair=17, eyes=19, brows=2, mouth=1, face=4, skin=2, height=2, pantsColor=2)),
    (1, 1, 0, "young_f1", "young", "f", 5, "닮은꼴 look_08: 긴 생머리 검정(가운데 가르마)·속눈썹 눈·가는 눈썹·활짝 웃음·볼터치·눈 밑 점·갸름·큰 키", dict(hair=5, eyes=12, brows=7, mouth=1, blush=1, face=1, skin=0, height=2, build=0, mark=1)),
    (1, 2, 0, "young_m2", "young", "m", 6, "옆가르마·갈색 뿔테 네모 안경·아몬드 눈·일자 눈썹·잔잔한 미소", dict(hair=1, eyes=18, brows=2, mouth=4, glasses=2, skin=1, height=2, glassesColor=1)),
    (1, 3, 0, "young_f2", "young", "f", 7, "C컬 중단발 밝은 갈색·동그란 안경·아래 속눈썹 눈·가는 눈썹·미소", dict(hair=18, hairColor=2, eyes=20, brows=7, mouth=0, blush=1, glasses=1, face=3, skin=5)),
    (2, 0, 0, "middle_m1", "middle", "m", 2, "닮은꼴 look_01: 바가지 검정·검정 네모 안경·무쌍 눈·일자 눈썹·활짝 웃음·갸름·날씬", dict(hair=10, eyes=14, brows=2, mouth=1, wrinkle=5, glasses=2, face=1, skin=1, height=2, build=0, pantsColor=1)),
    (2, 1, 0, "middle_f1", "middle", "f", 1, "파마 진한 갈색·강아지 눈·순한 눈썹·잔잔한 미소·넓은 얼굴·듬직", dict(hair=13, hairColor=1, eyes=11, brows=6, mouth=4, wrinkle=5, blush=1, face=5, skin=1, build=2)),
    (2, 2, 0, "middle_m2", "middle", "m", 2, "옆머리 희끗·무심한 눈·일자 눈썹·짧은 수염 + 콧수염·활짝 웃음", dict(hair=3, hairColor=6, eyes=21, brows=2, nose=2, mouth=1, wrinkle=5, beard=4, skin=6, height=2)),
    (2, 3, 0, "middle_f2", "middle", "f", 3, "웨이브 커트 희끗한 갈색·진한 쌍꺼풀 눈·가는 눈썹·미소", dict(hair=19, hairColor=7, eyes=23, brows=7, mouth=0, wrinkle=12, blush=1, face=1, skin=0)),
    (3, 0, 0, "old_m1", "old", "m", 4, "옆머리 흰머리·동그란 안경·실눈·긴 꼬리 눈썹·잔잔한 미소", dict(hair=3, hairColor=4, eyes=4, brows=9, nose=2, mouth=4, wrinkle=7, glasses=1, skin=1, glassesColor=2)),
    (3, 1, 0, "old_f1", "old", "f", 5, "뽀글 파마 진한 갈색·반달 안경·반달눈·순한 눈썹·미소·듬직", dict(hair=13, hairColor=1, eyes=5, brows=6, mouth=0, wrinkle=13, blush=1, glasses=3, skin=0, height=0, build=2, glassesColor=3)),
    (3, 2, 0, "old_m2", "old", "m", 6, "2:8 가르마 검정·온화한 눈·긴 꼬리 눈썹·콧수염·꾹 다문 입", dict(hair=15, hairColor=0, eyes=22, brows=9, nose=2, mouth=2, wrinkle=7, beard=2, face=2, skin=2)),
    (3, 3, 0, "old_f2", "old", "f", 7, "닮은꼴 look_11: 숏컷 은발·무심한 눈·가는 눈썹·한쪽 미소·갸름·날씬·목도리", dict(hair=12, hairColor=11, eyes=21, brows=7, mouth=5, wrinkle=7, face=1, skin=0, height=1, build=0, acc=1, scarfColor=0)),
    (0, 0, 1, "child_m2", "child", "m", 1, "", dict(hair=0, hairColor=0, eyes=17, brows=2, nose=0, mouth=4, blush=1, skin=2, height=0, build=1, pantsColor=4)),
    (0, 1, 1, "child_f2", "child", "f", 2, "", dict(hair=7, hairColor=1, eyes=5, brows=2, nose=0, mouth=4, blush=1, skin=0, height=0, build=1, pantsColor=1)),
    (0, 2, 1, "teen_m2", "teen", "m", 3, "", dict(hair=14, hairColor=0, eyes=18, brows=3, nose=0, mouth=2, blush=0, skin=0, height=1, build=1, pantsColor=3)),
    (0, 3, 1, "teen_f2", "teen", "f", 4, "", dict(hair=8, hairColor=0, eyes=12, brows=7, nose=0, mouth=5, blush=0, skin=1, height=1, build=1, pantsColor=1)),
    (1, 0, 1, "young_m3", "young", "m", 5, "", dict(hair=17, hairColor=0, eyes=22, brows=4, nose=0, mouth=4, blush=0, skin=5, height=2, build=1, pantsColor=2)),
    (1, 1, 1, "young_f3", "young", "f", 6, "닮은꼴 look_07: 앞머리 내린 긴 웨이브 검정·날렵한 눈(올라간 눈꼬리)·가는 눈썹·분홍 입술·볼터치 없음·갸름·날씬", dict(hair=8, hairColor=0, eyes=8, brows=7, mouth=7, blush=0, face=1, skin=0, height=1, build=0, pantsColor=2)),
    (1, 2, 1, "young_m4", "young", "m", 7, "", dict(hair=12, hairColor=1, eyes=23, brows=5, nose=2, mouth=2, blush=0, skin=5, height=2, build=1, pantsColor=1)),
    (1, 3, 1, "young_f4", "young", "f", 0, "", dict(hair=6, hairColor=1, eyes=13, brows=0, nose=0, mouth=6, blush=1, face=5, skin=1, height=0, build=2, pantsColor=0)),
    (2, 0, 1, "middle_m3", "middle", "m", 1, "", dict(hair=15, hairColor=1, eyes=21, brows=4, nose=2, mouth=4, wrinkle=5, blush=0, beard=4, glasses=2, face=2, skin=2, height=2, build=2, glassesColor=1, pantsColor=0)),
    (2, 1, 1, "middle_f3", "middle", "f", 2, "", dict(hair=8, hairColor=0, eyes=12, brows=7, nose=0, mouth=0, wrinkle=5, blush=1, glasses=1, face=3, skin=5, height=1, build=1, acc=1, scarfColor=5, glassesColor=2, pantsColor=0)),
    (2, 2, 1, "middle_m4", "middle", "m", 3, "닮은꼴 look_02: 짧은 스포츠머리 검정·실눈(크게 웃어 감긴 눈)·숱 많은 눈썹·활짝 웃음·넓은 코·넓은 얼굴·듬직", dict(hair=20, hairColor=0, eyes=4, brows=3, nose=2, mouth=1, wrinkle=12, face=5, skin=2, height=2, build=2, pantsColor=0)),
    (2, 3, 1, "middle_f4", "middle", "f", 4, "", dict(hair=9, hairColor=7, eyes=23, brows=6, nose=0, mouth=6, wrinkle=12, blush=0, glasses=1, face=5, skin=1, height=0, build=2, glassesColor=0, pantsColor=1)),
    (3, 0, 1, "old_m3", "old", "m", 5, "", dict(hair=4, hairColor=11, eyes=5, brows=2, nose=2, mouth=6, wrinkle=7, blush=0, glasses=2, skin=0, height=1, build=1, glassesColor=2, pantsColor=3)),
    (3, 1, 1, "old_f3", "old", "f", 6, "", dict(hair=13, hairColor=4, eyes=7, brows=7, nose=0, mouth=7, wrinkle=15, blush=1, face=1, skin=1, height=0, build=1, pantsColor=2)),
    (3, 2, 1, "old_m4", "old", "m", 7, "", dict(hair=12, hairColor=0, eyes=11, brows=6, nose=2, mouth=5, wrinkle=15, blush=0, face=2, skin=2, height=1, build=2, pantsColor=3)),
    (3, 3, 1, "old_f4", "old", "f", 0, "", dict(hair=9, hairColor=1, eyes=4, brows=7, nose=0, mouth=5, wrinkle=13, blush=1, glasses=1, skin=1, height=0, build=4, glassesColor=2, pantsColor=0)),
    (0, 0, 2, "child_m3", "child", "m", 2, "", dict(hair=10, hairColor=1, eyes=1, brows=8, nose=0, mouth=3, blush=1, skin=3, height=0, build=1, pantsColor=2)),
    (0, 1, 2, "child_f3", "child", "f", 3, "", dict(hair=6, hairColor=0, eyes=5, brows=2, nose=0, mouth=3, blush=1, skin=0, height=0, build=1, pantsColor=2)),
    (0, 2, 2, "teen_m3", "teen", "m", 4, "", dict(hair=0, hairColor=0, eyes=11, brows=2, nose=0, mouth=2, blush=0, skin=0, height=1, build=1, pantsColor=1)),
    (0, 3, 2, "teen_f3", "teen", "f", 5, "", dict(hair=5, hairColor=1, eyes=19, brows=2, nose=0, mouth=5, blush=1, skin=5, height=1, build=1, pantsColor=3)),
    (1, 0, 2, "young_m5", "young", "m", 6, "", dict(hair=12, hairColor=0, eyes=14, brows=4, nose=0, mouth=2, blush=0, glasses=2, face=4, skin=0, height=2, build=1, glassesColor=3, pantsColor=3)),
    (1, 1, 2, "young_f5", "young", "f", 7, "", dict(hair=18, hairColor=1, eyes=19, brows=0, nose=0, mouth=0, blush=1, face=3, skin=0, height=0, build=1, pantsColor=3)),
    (1, 2, 2, "young_m6", "young", "m", 0, "", dict(hair=0, hairColor=1, eyes=7, brows=2, nose=2, mouth=0, blush=0, glasses=2, face=1, skin=6, height=2, build=1, glassesColor=1, pantsColor=0)),
    (1, 3, 2, "young_f6", "young", "f", 1, "", dict(hair=5, hairColor=0, eyes=23, brows=2, nose=0, mouth=7, blush=1, glasses=2, skin=6, height=0, build=0, glassesColor=0, pantsColor=0)),
    (2, 0, 2, "middle_m5", "middle", "m", 2, "", dict(hair=3, hairColor=6, eyes=22, brows=6, nose=2, mouth=6, wrinkle=12, blush=0, face=5, skin=1, height=1, build=2, pantsColor=0)),
    (2, 1, 2, "middle_f5", "middle", "f", 3, "닮은꼴 look_10: C컬 중단발 진한 갈색·강아지 눈·순한 눈썹·시원한 웃음·넓은 얼굴·듬직", dict(hair=18, hairColor=1, eyes=11, brows=6, mouth=6, wrinkle=5, blush=1, face=5, skin=1, height=1, build=2, pantsColor=2)),
    (2, 2, 2, "middle_m6", "middle", "m", 4, "", dict(hair=15, hairColor=1, eyes=8, brows=4, nose=2, mouth=5, wrinkle=5, blush=0, face=4, skin=0, height=1, build=4, pantsColor=1)),
    (2, 3, 2, "middle_f6", "middle", "f", 5, "", dict(hair=19, hairColor=9, eyes=11, brows=2, nose=0, mouth=1, wrinkle=5, blush=0, skin=5, height=1, build=1, pantsColor=3)),
    (3, 0, 2, "old_m5", "old", "m", 6, "닮은꼴 look_05: 애즈펌 검정(염색)·또렷한 눈·숱 많은 눈썹·콧수염·시원한 웃음", dict(hair=14, hairColor=0, eyes=7, brows=3, nose=2, mouth=6, wrinkle=7, beard=2, skin=2, height=1, build=1, pantsColor=0)),
    (3, 1, 2, "old_f5", "old", "f", 7, "", dict(hair=13, hairColor=1, eyes=5, brows=9, nose=0, mouth=7, wrinkle=13, blush=1, face=1, skin=5, height=0, build=2, acc=1, scarfColor=2, pantsColor=0)),
    (3, 2, 2, "old_m6", "old", "m", 0, "", dict(hair=1, hairColor=11, eyes=18, brows=9, nose=2, mouth=1, wrinkle=13, blush=0, glasses=1, face=5, skin=1, height=1, build=2, glassesColor=1, pantsColor=1)),
    (3, 3, 2, "old_f6", "old", "f", 1, "", dict(hair=12, hairColor=3, eyes=19, brows=9, nose=0, mouth=6, wrinkle=13, blush=1, glasses=2, skin=1, height=0, build=4, glassesColor=3, pantsColor=4)),
    (0, 0, 3, "child_m4", "child", "m", 3, "", dict(hair=10, hairColor=0, eyes=24, brows=8, nose=0, mouth=4, blush=1, skin=0, height=0, build=1, pantsColor=3)),
    (0, 1, 3, "child_f4", "child", "f", 4, "", dict(hair=5, hairColor=0, eyes=13, brows=2, nose=0, mouth=8, blush=1, skin=5, height=0, build=1, pantsColor=3)),
    (0, 2, 3, "teen_m4", "teen", "m", 5, "", dict(hair=1, hairColor=0, eyes=18, brows=2, nose=0, mouth=6, blush=0, skin=5, height=1, build=1, pantsColor=0)),
    (0, 3, 3, "teen_f4", "teen", "f", 6, "", dict(hair=11, hairColor=1, eyes=17, brows=6, nose=0, mouth=1, blush=1, skin=5, height=1, build=3, pantsColor=3)),
    (1, 0, 3, "young_m7", "young", "m", 7, "", dict(hair=17, hairColor=0, eyes=8, brows=6, nose=0, mouth=4, blush=0, skin=1, height=2, build=3, pantsColor=0)),
    (1, 1, 3, "young_f7", "young", "f", 0, "", dict(hair=11, hairColor=0, eyes=18, brows=2, nose=0, mouth=0, blush=1, skin=1, height=0, build=3, pantsColor=3)),
    (1, 2, 3, "young_m8", "young", "m", 1, "", dict(hair=14, hairColor=0, eyes=22, brows=4, nose=0, mouth=5, blush=0, glasses=2, skin=1, height=2, build=3, glassesColor=0, pantsColor=0)),
    (1, 3, 3, "young_f8", "young", "f", 2, "", dict(hair=18, hairColor=2, eyes=19, brows=6, nose=0, mouth=4, blush=1, glasses=2, skin=4, height=1, build=1, glassesColor=3, pantsColor=2)),
    (2, 0, 3, "middle_m7", "middle", "m", 3, "닮은꼴 look_03: 2:8 가르마 검정·무심한 눈·각진 눈썹·짧은 수염·꾹 다문 입·넓고 각진 얼굴·듬직", dict(hair=15, hairColor=0, eyes=21, brows=4, nose=2, mouth=2, wrinkle=5, beard=1, face=6, skin=6, height=2, build=2, pantsColor=2)),
    (2, 1, 3, "middle_f7", "middle", "f", 4, "", dict(hair=18, hairColor=0, eyes=21, brows=2, nose=0, mouth=7, wrinkle=12, blush=1, glasses=2, face=1, skin=6, height=0, build=2, acc=1, scarfColor=7, glassesColor=0, pantsColor=0)),
    (2, 2, 3, "middle_m8", "middle", "m", 5, "", dict(hair=17, hairColor=6, eyes=11, brows=4, nose=2, mouth=0, wrinkle=12, blush=0, face=4, skin=2, height=1, build=1, pantsColor=3)),
    (2, 3, 3, "middle_f8", "middle", "f", 6, "닮은꼴 look_09: 바가지 단발 검정·동그란 검정 안경·또렷한 눈·활짝 웃음·둥근 얼굴", dict(hair=10, hairColor=0, eyes=7, brows=2, mouth=1, wrinkle=12, blush=1, glasses=1, skin=1, height=0, build=1, glassesColor=0, pantsColor=0)),
    (3, 0, 3, "old_m7", "old", "m", 7, "", dict(hair=0, hairColor=0, eyes=18, brows=9, nose=2, mouth=5, wrinkle=13, blush=0, beard=2, face=1, skin=1, height=1, build=1, pantsColor=1)),
    (3, 1, 3, "old_f7", "old", "f", 0, "", dict(hair=12, hairColor=1, eyes=22, brows=9, nose=0, mouth=0, wrinkle=15, blush=1, face=5, skin=1, height=0, build=2, pantsColor=0)),
    (3, 2, 3, "old_m8", "old", "m", 1, "", dict(hair=1, hairColor=3, eyes=21, brows=9, nose=2, mouth=0, wrinkle=7, blush=0, face=3, skin=1, height=1, build=1, pantsColor=2)),
    (3, 3, 3, "old_f8", "old", "f", 2, "", dict(hair=11, hairColor=4, eyes=19, brows=7, nose=0, mouth=7, wrinkle=13, blush=1, glasses=1, skin=0, height=0, build=1, glassesColor=2, pantsColor=0)),
    (0, 0, 4, "child_m5", "child", "m", 4, "", dict(hair=2, hairColor=0, eyes=5, brows=0, nose=0, mouth=8, blush=1, skin=1, height=0, build=1, pantsColor=2)),
    (0, 1, 4, "child_f5", "child", "f", 5, "", dict(hair=10, hairColor=0, eyes=1, brows=6, nose=0, mouth=0, blush=1, glasses=2, skin=0, height=0, build=4, glassesColor=0, pantsColor=0)),
    (0, 2, 4, "teen_m5", "teen", "m", 6, "", dict(hair=17, hairColor=1, eyes=1, brows=6, nose=0, mouth=6, blush=0, skin=5, height=1, build=1, pantsColor=1)),
    (0, 3, 4, "teen_f5", "teen", "f", 7, "", dict(hair=6, hairColor=0, eyes=13, brows=0, nose=0, mouth=5, blush=1, skin=2, height=1, build=0, pantsColor=1)),
    (1, 0, 4, "young_m9", "young", "m", 0, "", dict(hair=1, hairColor=0, eyes=7, brows=5, nose=2, mouth=2, blush=0, skin=5, height=2, build=3, pantsColor=0)),
    (1, 1, 4, "young_f9", "young", "f", 1, "", dict(hair=8, hairColor=9, eyes=16, brows=0, nose=0, mouth=6, blush=1, face=1, skin=1, height=1, build=1, pantsColor=4)),
    (1, 2, 4, "young_m10", "young", "m", 2, "", dict(hair=14, hairColor=0, eyes=23, brows=3, nose=2, mouth=1, blush=0, glasses=2, skin=0, height=2, build=0, glassesColor=1, pantsColor=0)),
    (1, 3, 4, "young_f10", "young", "f", 3, "", dict(hair=6, hairColor=1, eyes=13, brows=2, nose=0, mouth=7, blush=1, glasses=2, skin=1, height=1, build=1, glassesColor=0, pantsColor=0)),
    (2, 0, 4, "middle_m9", "middle", "m", 4, "", dict(hair=14, hairColor=0, eyes=8, brows=2, nose=2, mouth=6, wrinkle=5, blush=0, face=3, skin=2, height=2, build=1, pantsColor=0)),
    (2, 1, 4, "middle_f9", "middle", "f", 5, "", dict(hair=13, hairColor=7, eyes=11, brows=6, nose=0, mouth=7, wrinkle=12, blush=1, face=3, skin=1, height=1, build=2, pantsColor=3)),
    (2, 2, 4, "middle_m10", "middle", "m", 6, "", dict(hair=4, hairColor=6, eyes=14, brows=2, nose=2, mouth=0, wrinkle=12, blush=0, glasses=2, skin=5, height=2, build=4, glassesColor=0, pantsColor=4)),
    (2, 3, 4, "middle_f10", "middle", "f", 7, "", dict(hair=18, hairColor=1, eyes=12, brows=7, nose=0, mouth=4, wrinkle=12, blush=1, skin=1, height=0, build=1, acc=1, scarfColor=2, pantsColor=3)),
    (3, 0, 4, "old_m9", "old", "m", 0, "", dict(hair=15, hairColor=3, eyes=7, brows=9, nose=2, mouth=4, wrinkle=13, blush=0, glasses=1, skin=5, height=1, build=1, glassesColor=0, pantsColor=0)),
    (3, 1, 4, "old_f9", "old", "f", 1, "", dict(hair=11, hairColor=0, eyes=22, brows=6, nose=0, mouth=7, wrinkle=15, blush=1, face=3, skin=2, height=0, build=1, pantsColor=1)),
    (3, 2, 4, "old_m10", "old", "m", 2, "닮은꼴 look_06: 옆가르마 검정(염색)·반달눈·숱 많은 눈썹·짧은 수염·활짝 웃음·넓은 얼굴·듬직", dict(hair=1, hairColor=0, eyes=5, brows=3, nose=2, mouth=1, wrinkle=13, beard=1, face=5, skin=1, height=1, build=2, pantsColor=1)),
    (3, 3, 4, "old_f10", "old", "f", 3, "", dict(hair=19, hairColor=3, eyes=13, brows=9, nose=0, mouth=0, wrinkle=15, blush=1, glasses=2, face=3, skin=2, height=0, build=2, glassesColor=2, pantsColor=0)),
    (0, 0, 5, "child_m6", "child", "m", 5, "", dict(hair=1, hairColor=0, eyes=24, brows=6, nose=0, mouth=8, blush=1, skin=0, height=0, build=1, pantsColor=4)),
    (0, 1, 5, "child_f6", "child", "f", 6, "", dict(hair=11, hairColor=0, eyes=17, brows=8, nose=0, mouth=0, blush=1, skin=2, height=0, build=1, pantsColor=2)),
    (0, 2, 5, "teen_m6", "teen", "m", 7, "", dict(hair=12, hairColor=1, eyes=8, brows=3, nose=0, mouth=2, blush=1, skin=5, height=1, build=1, pantsColor=1)),
    (0, 3, 5, "teen_f6", "teen", "f", 0, "", dict(hair=5, hairColor=0, eyes=7, brows=2, nose=0, mouth=3, blush=1, face=3, skin=5, height=1, build=3, pantsColor=1)),
    (1, 0, 5, "young_m11", "young", "m", 1, "", dict(hair=1, hairColor=0, eyes=24, brows=2, nose=2, mouth=2, blush=0, skin=1, height=2, build=3, pantsColor=0)),
    (1, 1, 5, "young_f11", "young", "f", 2, "", dict(hair=5, hairColor=2, eyes=20, brows=0, nose=0, mouth=7, blush=1, skin=5, height=1, build=1, pantsColor=4)),
    (1, 2, 5, "young_m12", "young", "m", 3, "", dict(hair=15, hairColor=1, eyes=24, brows=0, nose=2, mouth=5, blush=0, glasses=2, face=4, skin=1, height=2, build=4, glassesColor=0, pantsColor=2)),
    (1, 3, 5, "young_f12", "young", "f", 4, "", dict(hair=9, hairColor=1, eyes=23, brows=7, nose=0, mouth=5, blush=1, skin=2, height=1, build=1, pantsColor=3)),
    (2, 0, 5, "middle_m11", "middle", "m", 5, "", dict(hair=1, hairColor=6, eyes=7, brows=2, nose=2, mouth=5, wrinkle=5, blush=0, beard=1, face=4, skin=5, height=2, build=1, acc=1, scarfColor=0, pantsColor=0)),
    (2, 1, 5, "middle_f11", "middle", "f", 6, "", dict(hair=13, hairColor=1, eyes=8, brows=7, nose=0, mouth=0, wrinkle=12, blush=1, face=3, skin=0, height=0, build=2, pantsColor=0)),
    (2, 2, 5, "middle_m12", "middle", "m", 7, "", dict(hair=0, hairColor=0, eyes=14, brows=2, nose=2, mouth=4, wrinkle=12, blush=0, glasses=2, skin=3, height=2, build=4, glassesColor=0, pantsColor=2)),
    (2, 3, 5, "middle_f12", "middle", "f", 0, "", dict(hair=11, hairColor=1, eyes=12, brows=7, nose=0, mouth=7, wrinkle=5, blush=1, skin=0, height=1, build=4, pantsColor=2)),
    (3, 0, 5, "old_m11", "old", "m", 1, "", dict(hair=3, hairColor=1, eyes=19, brows=6, nose=2, mouth=2, wrinkle=15, blush=0, glasses=1, face=3, skin=0, height=1, build=1, glassesColor=3, pantsColor=2)),
    (3, 1, 5, "old_f11", "old", "f", 2, "닮은꼴 look_12: 뽀글 파마 검정(염색)·실눈·순한 눈썹·시원한 웃음", dict(hair=13, hairColor=0, eyes=4, brows=6, mouth=6, wrinkle=13, blush=1, skin=1, height=0, build=1, pantsColor=3)),
    (3, 2, 5, "old_m12", "old", "m", 3, "", dict(hair=15, hairColor=4, eyes=21, brows=2, nose=2, mouth=6, wrinkle=15, blush=0, beard=2, glasses=1, face=5, skin=2, height=1, build=2, glassesColor=3, pantsColor=3)),
    (3, 3, 5, "old_f12", "old", "f", 4, "", dict(hair=19, hairColor=11, eyes=18, brows=7, nose=0, mouth=7, wrinkle=7, blush=1, glasses=3, face=5, skin=0, height=0, build=2, glassesColor=2, pantsColor=3)),
]
# <<< who_pool_gen.py


def _w(r, c, pg, i, age, sex, color, want, kw):
    v = {**_BASE, **_AGE_BASE[age], **kw}
    if "beardColor" not in kw:
        v["beardColor"] = _beard_color(v["hairColor"], v["beard"])
    _bits(v)
    return {"id": i, "age": age, "label": dict(AGES)[age], "color": color, "sex": sex, "vibe": "", "want": want,
            "cell": (r, c), "page": pg, "avatar": {k2: v[k2] for k2 in KEYS}}


WHO = [_w(*row) for row in WHO_DATA]
WHO_PAGES = 1 + max(p["page"] for p in WHO)
# who_rows = 줄 → 화면 → 그 화면의 칸 4개 id(남·여·남·여). 웹은 칸마다 [화면 0, 1, …] 차례로 넘긴다(안 본 얼굴 먼저)
WHO_ROWS = [[[next(p["id"] for p in WHO if p["cell"] == (r, c) and p["page"] == g) for c in range(4)] for g in range(WHO_PAGES)] for r in range(4)]
_BY_ID = {p["id"]: p for p in PRESETS + POOL + WHO}   # 예전 프리셋 8 id(child_m 등)·예전 묶음 id(child_1 등)도 그대로 받는다
assert len(_BY_ID) == len(PRESETS) + len(POOL) + len(WHO)
assert all([_BY_ID[i]["sex"] for i in g] == ["m", "f", "m", "f"] for r in WHO_ROWS for g in r)
WHO_IDS = [i for r in WHO_ROWS for g in r for i in g]
assert len(WHO_IDS) == len(set(WHO_IDS))
# 캐릭터가 없는 예전 사람에게 넣는 기본값: 자리 번호마다 다른 프리셋(광장에 똑같은 사람 5명이 앉지 않게). 정해진 규칙이라 두 번 채워도 같다
DEFAULT_ORDER = ["young_f", "young_m", "middle_f", "middle_m", "child_f"]

# 얼굴 텍스처(2D) 그리기 규칙(더미 v0). 웹 canvas와 차 Android Canvas가 같은 값으로 그린다.
# 좌표·크기는 정사각 텍스처 한 변 = 1.0 기준(그릴 때 size를 곱한다). 눈·눈썹·볼은 가운데(x=0.5)에서 좌우 대칭(dx).
# 색: 눈·입 선은 ink, 눈썹은 머리색, 볼터치는 blushColor(알파 포함), 짧은 수염은 stubble(알파 포함), 바탕은 피부색.
FACE_SPEC = {
    "version": 0,
    "size": 512,
    "ink": "#2B2522", "blushColor": "#F2969A66", "stubble": "#4A322633", "mouthIn": "#E0605E",
    "eyes": {"y": 0.50, "dx": 0.15, "options": [
        {"shape": "dot", "w": 0.070, "h": 0.070, "shine": 0.020},
        {"shape": "dot", "w": 0.090, "h": 0.100, "shine": 0.030},
        {"shape": "dot", "w": 0.050, "h": 0.050, "shine": 0.014},
        {"shape": "dot", "w": 0.060, "h": 0.100, "shine": 0.018},
        {"shape": "line", "w": 0.090, "stroke": 0.016},
        {"shape": "arc_up", "w": 0.100, "h": 0.040, "stroke": 0.018},
        {"shape": "droop", "w": 0.080, "h": 0.070, "tilt": -12}]},
    "brows": {"y": 0.39, "dx": 0.16, "options": [
        {"shape": "short", "w": 0.070, "stroke": 0.022},
        {"shape": "arch", "w": 0.110, "stroke": 0.012},
        {"shape": "flat", "w": 0.110, "stroke": 0.030},
        {"shape": "droop", "w": 0.120, "stroke": 0.034, "tilt": -14}]},
    "nose": {"y": 0.60, "options": [
        {"shape": "dot", "w": 0.030, "h": 0.022},
        {"shape": "button", "w": 0.060, "h": 0.045},
        {"shape": "wide", "w": 0.100, "h": 0.055}]},
    "mouth": {"y": 0.71, "options": [
        {"shape": "smile", "w": 0.120, "h": 0.040, "stroke": 0.016},
        {"shape": "open_smile", "w": 0.140, "h": 0.080},
        {"shape": "line", "w": 0.090, "stroke": 0.014},
        {"shape": "o", "w": 0.040, "h": 0.050}]},
    "wrinkle": {"options": [
        None,
        {"shape": "eye_corner", "y": 0.50, "dx": 0.25, "w": 0.040, "lines": 2, "stroke": 0.008},
        {"shape": "forehead_smile", "y": 0.24, "w": 0.220, "lines": 3, "fold_y": 0.66, "fold_dx": 0.15, "stroke": 0.008},
        {"shape": "both", "of": [1, 2]}]   # 3 눈가+이마: of 의 두 모양을 다 그린다
        # 4~15(입가 4·눈 밑 8 비트가 붙은 값): 예전 도형 그리기에는 입가·눈 밑 모양이 없어 눈가·이마 비트만 그린다
        + [{"shape": "both", "of": [b for b in (1, 2) if v & b]} if v & 3 else None for v in range(4, 16)]},
    "blush": {"y": 0.63, "dx": 0.25, "r": 0.065},
    "beard": {"stubble": {"y": 0.80, "w": 0.46, "h": 0.22}},   # beard 1(짧은 수염)만 2D. 2·3은 3D 부품
}


class Bad(ValueError):
    pass


BAD = "캐릭터를 다시 골라 주세요"  # [확인 필요] 새 문구: 웹이 범위 밖 값을 보냈을 때(정상 화면에선 안 나옴)
BAD_COLOR = "대표색을 다시 골라 주세요"  # [확인 필요] 새 문구


def _int(v, n):
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < n:
        raise Bad(BAD)
    return v


def default_avatar(slot=None):
    i = (slot - 1) % len(DEFAULT_ORDER) if isinstance(slot, int) and slot >= 1 else 0
    return dict(_BY_ID[DEFAULT_ORDER[i]]["avatar"])


def clean(value, base=None):
    """웹이 보낸 avatar를 검사해 모든 칸(KEYS)이 다 찬 새 dict로 돌려준다. 빠진 칸은 base(지금 값) → 기본값으로 채운다.
    preset(프리셋 id)만 보내도 된다(그 프리셋 값 위에 같이 보낸 칸을 덮는다). 범위 밖·정수 아님·dict 아님이면 Bad."""
    if not isinstance(value, dict):
        raise Bad(BAD)
    out = dict(default_avatar())
    if isinstance(base, dict):
        base = dict(base); upgrade(base)
        out.update({k: base[k] for k in KEYS if k in base})
    if "preset" in value:
        p = _BY_ID.get(value["preset"])
        if not p:
            raise Bad(BAD)
        out.update(p["avatar"])
    for k in KEYS:
        if k in value:
            out[k] = _int(value[k], COUNT[k])
    for k in KEYS:   # base가 예전 범위의 값을 갖고 있어도 내보내기 전에 한 번 더 본다
        _int(out[k], COUNT[k])
    for k, m in MOVED.items():   # 고르는 칸에서 뺀 부품은 비슷한 부품으로(예전 화면이 보낸 값)
        out[k] = m.get(out[k], out[k])
    # 수염·점: 새 비트 칸을 보냈으면 그게 정본(예전 칸은 맞춰 둔다), 예전 칸만 보냈으면(예전 화면) 새 칸으로 옮긴다
    for new, old, to_new, to_old in (("beards", "beard", BEARD_OLD, beard_of), ("marks", "mark", MARK_OLD, mark_of)):
        if new in value:
            out[old] = to_old(out[new])
        elif old in value:
            out[new] = to_new[out[old]]
    if out["beards"] != beards_fix(out["beards"]):   # 콧수염 + 턱수염 → 턱수염만(예전 칸도 맞춰 둔다)
        out["beards"] = beards_fix(out["beards"]); out["beard"] = beard_of(out["beards"])
    return out


def upgrade(value):
    """예전에 저장된 캐릭터에 새로 붙은 칸(수염색·소품·목도리 색·안경테 색·바지 색)을 예전 모습 그대로 채우고, 숨긴 눈은 비슷한 새 눈으로 옮긴다. 바꿨으면 True.
    이걸 안 하면 valid()가 False가 되어 사람마다 고른 캐릭터가 기본값으로 덮인다."""
    if not isinstance(value, dict):
        return False
    changed = False
    if "beardColor" not in value:
        hc, bd = value.get("hairColor"), value.get("beard")
        if isinstance(hc, int) and 0 <= hc < COUNT["hairColor"] and isinstance(bd, int):
            value["beardColor"] = _beard_color(hc, bd)
            changed = True
    if "acc" not in value and "hair" in value:   # 소품이 없던 때: 없음(예전 모습 그대로)
        value["acc"] = 0
        changed = True
    elif "acc" in value:
        # 잠깐 있던 4가지 소품(2 목도리, 3 이어폰·목도리)은 목도리(1)로. 범위 밖·정수 아님은 없음(0).
        # 1은 지금 뜻(목도리) 그대로 둔다: 옛 '이어폰 1'과 구별할 수 없고, 바꾸면 고른 목도리가 매번 지워진다(올린 적 없는 값이라 남은 기록도 없음)
        v = value["acc"]
        nv = 1 if v in (2, 3) and not isinstance(v, bool) else v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < COUNT["acc"] else 0
        if nv != v or isinstance(v, bool):
            value["acc"] = nv
            changed = True
    if "scarfColor" not in value and "hair" in value:   # 목도리 색이 없던 때: 분홍(예전 목도리 색과 가까움)
        value["scarfColor"] = SCARF_DEFAULT
        changed = True
    for k in ("glassesColor", "pantsColor", "mark"):   # 83번: 안경테·바지 색이 없던 때 = 0(예전 테·바지 색). 점이 없던 때 = 0 없음
        if k not in value and "hair" in value:
            value[k] = 0
            changed = True
    # 11/10 수염·점 비트 칸이 없던 때: 예전 한 칸 값을 같은 모습의 비트로(예전 수염 4 = 짧은 수염 + 콧수염, 예전 점은 왼쪽)
    for new, old, m in (("beards", "beard", BEARD_OLD), ("marks", "mark", MARK_OLD)):
        v = value.get(old)
        if new not in value and "hair" in value and isinstance(v, int) and not isinstance(v, bool) and v in m:
            value[new] = m[v]
            changed = True
    # 콧수염 + 턱수염이 같이 켜진 기록(11/10 잠깐 고를 수 있었다) → 턱수염만
    v = value.get("beards")
    if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < COUNT["beards"] and beards_fix(v) != v:
        value["beards"] = beards_fix(v); value["beard"] = beard_of(value["beards"])
        changed = True
    # 고르는 칸에서 뺀 부품(눈 0 → 7·3 → 1, 11/10 79번 눈썹 1 아치 → 7 가는, 코 1 동그란 → 0 작은). 옮기기 전 기록도 범위 안이라 valid()
    for k, m in MOVED.items():
        v = value.get(k)
        if isinstance(v, int) and not isinstance(v, bool) and v in m:
            value[k] = m[v]
            changed = True
    return changed


def valid(value):
    """저장된 avatar가 온전한지(빠진 칸·범위 밖 없음)."""
    try:
        return isinstance(value, dict) and all(_int(value.get(k), COUNT[k]) is not None for k in KEYS)
    except Bad:
        return False


def clean_color(v):
    try:
        return _int(v, NCOLORS)
    except Bad:
        raise Bad(BAD_COLOR)


def catalog():
    """GET /api/presets 응답: 예전 프리셋 8 + 닮은 모습(pool·who_rows, 4칸 × 4줄 × 화면 6) + 부품 이름·고르는 칸 순서(pick) + 색 값 + 얼굴 그리기 규칙.
    vibe·want·sex 는 서버 안 메모라 보내지 않는다."""
    return {
        "presets": [{"id": p["id"], "label": p["label"], "sex": p["sex"], "color": p["color"], "avatar": dict(p["avatar"])}
                    for p in PRESETS],
        # 닮은 모습(83번): pool = 96명(WHO_ROWS 순서), who_rows = 줄 → 화면 → 칸 id(4칸, 남·여·남·여). 줄 이름은 없다
        "pool": [{"id": i, "age": _BY_ID[i]["age"], "color": _BY_ID[i]["color"], "avatar": dict(_BY_ID[i]["avatar"])} for i in WHO_IDS],
        "who_rows": [[list(g) for g in r] for r in WHO_ROWS],
        # 11/10 사장 '직접 고르기': 닮은 모습 첫 칸 [처음부터]가 여는 기본형(부품 기본값, 나이·성별 느낌 없는 짧은 머리·둥근 얼굴)
        "base": dict(BASE_AVATAR),
        "parts": {k: list(v) for k, v in PARTS},
        "pick": {k: list(v) for k, v in PICK.items()},   # 고르는 칸 순서(번호). wrinkle 은 따로 켜고 끄는 비트
        "one_of": {"beards": [BEARD_MUS | BEARD_LONG]},   # 켜고 끄는 칸 중 같이 안 되는 비트 묶음(하나를 켜면 묶음의 다른 비트는 꺼진다)
        "hairColors": [dict(name=n, hex=h, **({"salt": list(HAIR_SALT[i])} if i in HAIR_SALT else {})) for i, (n, h) in enumerate(HAIR_COLORS)],
        "skins": [{"name": n, "hex": h} for n, h in SKINS],
        "colors": [{"name": n, "hex": h} for n, h in COLORS],
        "glassesColors": [{"name": n, "hex": h} for n, h in GLASSES_COLORS],
        "pantsColors": [{"name": n, "hex": h} for n, h in PANTS_COLORS],
        "max_people": MAX_PEOPLE,
        "face_spec": FACE_SPEC,
    }
