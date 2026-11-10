package ai.simeodum.car

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RenderEffect
import android.graphics.Shader
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Choreographer
import android.view.Surface
import android.view.SurfaceView
import android.view.View
import android.widget.FrameLayout
import com.google.android.filament.Camera
import com.google.android.filament.ColorGrading
import com.google.android.filament.Colors
import com.google.android.filament.Engine
import com.google.android.filament.EntityManager
import com.google.android.filament.Filament
import com.google.android.filament.IndirectLight
import com.google.android.filament.LightManager
import com.google.android.filament.MaterialInstance
import com.google.android.filament.Renderer
import com.google.android.filament.SwapChain
import com.google.android.filament.SwapChainFlags
import com.google.android.filament.Texture
import com.google.android.filament.TextureSampler
import com.google.android.filament.ToneMapper
import com.google.android.filament.Viewport
import com.google.android.filament.android.DisplayHelper
import com.google.android.filament.android.UiHelper
import com.google.android.filament.gltfio.AssetLoader
import com.google.android.filament.gltfio.FilamentAsset
import com.google.android.filament.gltfio.FilamentInstance
import com.google.android.filament.android.TextureHelper
import com.google.android.filament.gltfio.ResourceLoader
import com.google.android.filament.gltfio.UbershaderProvider
import com.google.android.filament.utils.Utils
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.math.tan
import kotlin.random.Random

/**
 * 차 홈 광장(3D 더미, Filament). 흰 받침판 위 나무 아래 빈백 쿠션 5자리에 연결된 사람이 앉아 쉰다.
 *
 * 그리기 규칙(Pleos RAM·CPU 규정, 57·59·64번):
 * - 주행 중: 그리지 않는다. 바뀐 게 있을 때(사람·날씨·도착) 결과 1장만 그린다. 출발하면 모두 자기 쿠션에 앉은 자세로 굳는다.
 * - 정차 중(P·파킹 브레이크·오토홀드): 무슨 일이 있어도 멈추지 않는다(사용자 11/08). 카드·설정이 떠 있어도 돈다.
 *   쉬는 건 화면이 안 보일 때(setActive false)뿐. 기본은 화면 갱신(60Hz)마다 초당 60장, 설정의 저사양 모드면 초당 30장(11/09 사용자 결정).
 *   Pleos 정차 CPU 상한 25%는 코드 최적화로 맞춘다: 행렬 재사용(할당 0), 숨긴 부품은 장면에서 빼기.
 * - 늘 도는 것: 숨쉬기(4초, 모두 같은 폭), 고개 돌리기(6~9초마다 ±8°), 나뭇잎·풀 흔들림, 비·눈 내림, 가로등 켜짐(3초).
 * - 돌아가며 하는 행동: 6~10초마다 한 명(섞은 주머니라 모두 같은 횟수). 손 흔들기·일어섰다 앉기·몸 돌리기·올려다보기·기지개·옆 사람 보기,
 *   걷는 것은 둘러보기·옆 사람에게 가기·둘이 마주 보기. 쿠션을 떠나는 사람은 동시에 2명까지(사용자 11/08), 정차 뒤 5초와 오토홀드 중엔 걷지 않는다.
 *   말 거는 자리(원판 둘레)는 메시지 주인공만 들어간다. 메시지 주인공이 나오면 다른 사람은 큰 동작을 쉬고 쿠션으로 돌아간다.
 * - 행동 고르는 코드는 대기 목록·보낸 사람을 받지 않는다. 섞는 씨앗은 사람 코드와 날짜뿐(비밀 규칙).
 * - 사람(11/09): plaza_char2.glb 한 자산의 인스턴스 5개(텍스처 같이 씀). 동작은 glb 클립(뼈) + 0.35초 교차 전환, 위치·방향·높이는 뿌리 노드만.
 *   클립에는 크기·(Hips 빼고)이동 채널이 없어 키(뿌리 균일 크기)가 풀리지 않는다. 체형·얼굴형은 모프 가중치. 얼굴 그림은 사람마다 따로 만든 텍스처.
 * - 비밀 규칙: 기다리는 장면에서는 모두 같은 자세·크기 규칙. 누가 보냈는지는 도착·재생·들은 뒤에만(hero).
 */
class PlazaView(ctx: Context) : FrameLayout(ctx) {
    companion object {
        init { Filament.init(); Utils.init() }
        private const val SEAT_TOP = 0.47f        // 빈백 앉는 면 높이(pr_cushion 실측 0.43~0.45, 살짝 파묻히게)
        private const val TARGET_Z = 6.0f          // 앉은 사람이 바라보는 점(카메라 쪽)
        private val HEIGHT = floatArrayOf(.86f, 1f, 1.12f)   // 키는 뿌리 균일 크기(불균일이면 가발이 찌그러짐). 체형·얼굴형은 모프
        private const val FACE_PX = 256
        // ── 캐릭터 plaza_char2.glb(tools/char/build_char.py): 뼈 38개 + 동작 19개, 사람 5명 = 한 자산의 인스턴스 5개 ──
        private const val POOL = 5
        private const val FADE_MS = 350f                         // 동작 사이 교차 전환
        // 동작 이름(glb 애니메이션 이름 그대로)
        private const val C_SIT = "Chair_Sit_Idle_F"; private const val C_SIT_WAVE = "Sit_Wave"; private const val C_SIT_YAWN = "Sit_Yawn"
        private const val C_SIT_STRETCH = "Sit_Stretch"; private const val C_DRINK = "Sit_and_Drink"; private const val C_DOZE = "Sit_and_Doze_Off"
        private const val C_CROSS = "Sit_Cross_Legged"; private const val C_RISE = "Sit_to_Stand_Transition_M"; private const val C_SITDOWN = "Stand_to_Sit_Transition_M"
        private const val C_WALK = "Walking"; private const val C_IDLE = "Short_Breathe_and_Look_Around"; private const val C_LOOK = "Long_Breathe_and_Look_Around"
        private const val C_CHAT = "Stand_and_Chat"; private const val C_WAVE1 = "Wave_One_Hand"; private const val C_STRETCH = "Stretch"
        // root_motion.json에서 옮긴 값(glTF 좌표: +Z 앞, 키 1 기준 미터). 모든 동작은 0초에 Hips 수평 위치가 원점
        private const val CLIP_WALK = 0.739f                     // Walking 디딤발 속도(m/s) → 걷는 빠르기에 맞춰 재생 속도를 바꿈(발 미끄럼 없게)
        private const val RISE_END_X = -0.0003f; private const val RISE_END_Z = 0.1293f   // 앉→서 끝 Hips 위치(앞으로 13cm)
        private const val SIT_END_X = 0.0038f; private const val SIT_END_Z = -0.0648f     // 서→앉 끝(뒤로 6.5cm)
        private const val CHAT_YAW0 = -0.7016f                   // Stand_and_Chat 첫 몸 방향(-40.2°) → 뿌리를 그만큼 되돌려 원하는 쪽을 보게
        private const val READ_TO = 3.0f                         // 책 읽기 = Sit_and_Drink 0~3초(두 손을 무릎 앞에 모은 자세)를 왕복 재생
        // ── 빈백에 앉기(11/09 실측: pr_cushion 윗면 높이 지도 × 앉은 동작 몸 점, 몸통·다리·발이 쿠션 속 1cm 넘게 안 들어가게) ──
        // 쿠션은 가운데가 0.41로 파인 그릇(폭 ±0.12), 옆 팔걸이 0.6~0.7, 등받이 z -0.15 뒤 1.05, 앞 끝 z 0.58.
        // 동작의 다리(정강이 수직)는 어디 둬도 쿠션 속이라, 앉은 동안 다리는 앞으로 뻗어 쿠션 위에 얹는다(허벅지 앞·정강이 약간 아래·발끝 위).
        // 값은 키(작음·보통·큼)마다: SEAT_D 쿠션 가운데에서 앞으로 뿌리까지(m), Y_* 뿌리 높이(m, 바닥 0). 표 = 서→앉·앉→서 진행 0, .1 … 1 의 뿌리 높이
        private val SEAT_D = floatArrayOf(0.15f, 0.09f, 0.12f)
        private val Y_CHAIR = floatArrayOf(0.225f, 0.193f, 0.171f)      // Chair_Sit_Idle_F·Sit_Wave·Sit_Yawn·Sit_Stretch
        private val Y_DRINK = floatArrayOf(0.303f, 0.286f, 0.264f)      // Sit_and_Drink(책 읽기도)
        private val Y_DOZE = floatArrayOf(0.275f, 0.254f, 0.245f)       // Sit_and_Doze_Off
        private val SIT_Y = arrayOf(floatArrayOf(0f, 0f, .059f, .276f, .362f, .395f, .413f, .386f, .302f, .250f, .246f),
                                    floatArrayOf(0f, 0f, .035f, .308f, .375f, .404f, .420f, .393f, .296f, .226f, .217f),
                                    floatArrayOf(0f, 0f, .006f, .284f, .361f, .394f, .411f, .361f, .228f, .170f, .174f))
        private val RISE_Y = arrayOf(floatArrayOf(.245f, .249f, .293f, .365f, .408f, .399f, .360f, .282f, .036f, .003f, .003f),
                                     floatArrayOf(.222f, .229f, .282f, .372f, .416f, .407f, .375f, .316f, .173f, .006f, .005f),
                                     floatArrayOf(.192f, .177f, .219f, .332f, .404f, .397f, .362f, .295f, .139f, .007f, .006f))
        private const val Z_FRONT = 0.74f                                // 쿠션 앞에 서는 점(앞 끝 0.58 + 발). 서→앉은 여기서 SEAT_D까지 뒤로 털썩
        // 빈백 다리 방향(몸 기준: +X 왼쪽, +Y 위, +Z 앞. 오른쪽 다리는 X 반대). tools/char 시뮬(legsim)과 같은 값
        private val LEG_THIGH = floatArrayOf(0.12f, -0.05f, 1f); private val LEG_SHIN = floatArrayOf(0.10f, -0.30f, 1f); private val LEG_FOOT = floatArrayOf(0.05f, 0.75f, 0.66f)
        // 옛 머리 번호(서버 avatar.py hair) → 새 노드. 14~16은 새로 뒤에 붙인 것. null = 민머리
        private val HAIR_NODES = arrayOf("hair_m_dandy", "hair_m_gareu", "hair_m_spiky", "hair_m_bald", null, "hair_w_long", "hair_w_pony", "hair_w_pigtail",
            "hair_w_wave", "hair_w_bun", "hair_m_bowl", "hair_w_bob", "hair_w_grancut", "hair_w_perm", "hair_m_ez", "hair_m_man50", "hair_m_allback",
            "hair_m_twoblock", "hair_w_ccurl", "hair_w_wavecut", "hair_m_buzz")   // 11/10 17 투블럭·18 C컬 중단발·19 웨이브 커트
        private val GLASSES = arrayOf(null, "glasses_round", "glasses_square", "glasses_half")
        // 체형 [build_slim, build_chubby]: 0 날씬·1 보통·2 듬직·3 조금 날씬·4 조금 듬직. 얼굴형 [face_slim, face_square, face_full]: 0 둥근·1 갸름·2 각진·3 조금 갸름·4 조금 각진
        // · 5 넓은 얼굴·6 넓고 각진(85번, 뒤에만)
        private val BUILD_W = arrayOf(floatArrayOf(1f, 0f), floatArrayOf(0f, 0f), floatArrayOf(0f, 1f), floatArrayOf(.5f, 0f), floatArrayOf(0f, .5f))
        private val FACE_W = arrayOf(floatArrayOf(0f, 0f, 0f), floatArrayOf(1f, 0f, 0f), floatArrayOf(0f, 1f, 0f), floatArrayOf(.5f, 0f, 0f), floatArrayOf(0f, .5f, 0f),
            floatArrayOf(0f, 0f, 1f), floatArrayOf(0f, .7f, 1f))
        // 11/10 콧수염(beard_mus) 줄여 올리기(사장: 넓고 각진 + 짧은 수염 + 콧수염이면 입이 거의 안 보임). 콧수염 아래 끝이 입꼬리·웃는 선 윗부분을 덮던 것 →
        // 윗가운데(코 밑, 메시 좌표 MUS_PIVOT)를 기준으로 가로·세로·앞뒤를 줄여 아래 끝을 입꼬리 높이까지. 넓은 얼굴(5·6)은 가로를 조금 더. 웹 avatar3d.js MUS_* 와 같은 값
        private val MUS_PIVOT = floatArrayOf(0f, 1.21f, 0.30f); private val MUS_S = floatArrayOf(0.92f, 0.72f, 0.8f); private const val MUS_WIDE = 0.96f
        private val PROPS_IN_HAND = arrayOf("prop_cup", "prop_book", "prop_phone")
        // 재생 방식
        private const val ONCE = 0; private const val LOOP = 1; private const val PING = 2
        // 카메라(받침판이 칸 폭에 들어오게)
        private val EYE = floatArrayOf(0f, 5.4f, 11.2f)
        private val LOOK = floatArrayOf(0f, 0.9f, 0.2f)
        private const val WALK_SPEED = 0.62f      // 1초에 걷는 거리. 동물의숲 주민처럼 느긋하게(11/08 밤 사용자)
        private const val MAX_AWAY = 3            // 쿠션을 떠나 돌아다니는 사람은 동시에 3명까지(사용자 11/08 밤)
        private const val HERO_MAX_MS = 2500L     // 메시지 주인공이 말 거는 자리까지 오는 최대 시간
        private const val LAMP_MS = 3000L         // 가로등이 서서히 켜지는 시간(사용자 11/08)
        private const val ENV_MS = 4000L          // 날씨·밤·시간대가 바뀌는 데 걸리는 시간(사용자 11/08 밤: 3~5초)
        // 가로등 빛(11/10 자연스러운 밤·비): 사람에게 고르게 닿는 따뜻한 둘레빛 몫, 유리 둘레 빛 번짐·바닥 빛 웅덩이·젖은 바닥 반사 진하기.
        // 실제 점광원·스포트는 쓰지 않는다: 에뮬레이터에서 켜기만 해도 앱 CPU +3~4%p(11/10 실측, 범위·거리를 줄여도 +3%p)라 바닥 빛은 흐림 텍스처로 그린다
        private const val LAMP_AMB = 0.1f; private const val HALO_A = 0.55f; private const val POOL_A = 0.5f; private const val WET_A = 0.42f
        private const val ENV_N = 32
        /** 앞 채움빛이 오는 쪽(앞 왼쪽 위, 카메라 쪽). 방향광은 하나만 쓰여서(위 '빛' 설명) 둘레빛에 '반 램버트'로 넣는다 */
        private val FILL_DIR = floatArrayOf(-0.6f, 0.4f, 0.7f).let { v -> val l = sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]); floatArrayOf(v[0] / l, v[1] / l, v[2] / l) }
        private const val FOREVER = Long.MAX_VALUE
        // 구간 종류
        private const val SEAT = 0; private const val RISE = 1; private const val WALK = 2; private const val STAND = 3; private const val SIT = 4
        // 몸짓
        private const val G_WAVE = 1; private const val G_LIFT = 2; private const val G_TURN = 3; private const val G_LOOKUP = 4
        private const val G_STRETCH = 5; private const val G_LOOKAT = 6
        // 돌아가며 하는 행동(섞은 주머니 칸)
        private const val A_WAVE = 1; private const val A_LIFT = 2; private const val A_TURN = 3; private const val A_LOOKUP = 4
        private const val A_STRETCH = 5; private const val A_LOOKAT = 6; private const val A_STROLL = 7; private const val A_VISIT = 8; private const val A_FACE2 = 9
        private val WALKERS = setOf(A_STROLL, A_VISIT, A_FACE2)
        private const val G_HELLO = 7; private const val G_CATCH = 8   // 문 열림 인사(살짝 일어나 손), 눈 받기(두 손 앞으로)
        private const val G_READ = 9; private const val G_LOOKAROUND = 10; private const val G_HUM = 11; private const val G_TALK = 12   // 책 읽기, 둘러보기, 흥얼거리기(몸 살랑), 이야기
        private const val G_DOZE = 13; private const val G_DRINK = 14; private const val G_YAWN = 15   // 졸기, 마시기(컵), 하품(11/09 Meshy 동작)
        private const val A_READ = 10
        private const val A_DOZE = 11; private const val A_DRINK = 12; private const val A_YAWN = 13
        // 소품 자리(tools/make_plaza_glb.py 와 같게): 걷는 사람이 피한다(x, z, 반지름). 화분·눈사람·충전 기둥·벤치
        // ── 걷는 길 장애물(11/09): plaza_scene.glb 메시의 바닥 발자국 볼록 껍질(x, z 차례, 장면 좌표). 몸이 닿는 높이까지만 잼 ──
        // 나무 줄기 y<0.5(뿌리 퍼짐), 가로등 받침 y<0.8, 벤치 y<0.9(앉는 판·등받이), 화분·충전 기둥·눈사람 전체. 쿠션은 메시 좌표(쿠션 기준) + 앉은 다리(앞 0.72)
        private val OB_TREE = floatArrayOf(-0.41f, -3.40f, -0.11f, -3.57f, 0.18f, -3.52f, 0.34f, -3.39f, 0.40f, -3.26f, 0.42f, -3.09f, 0.31f, -2.84f, 0.19f, -2.74f, 0.06f, -2.69f, -0.24f, -2.72f, -0.35f, -2.79f, -0.50f, -3.08f)
        private val OB_LAMP = floatArrayOf(-2.92f, -2.59f, -2.80f, -2.69f, -2.72f, -2.71f, -2.54f, -2.67f, -2.46f, -2.58f, -2.42f, -2.48f, -2.48f, -2.27f, -2.55f, -2.21f, -2.66f, -2.17f, -2.75f, -2.18f, -2.89f, -2.26f, -2.94f, -2.34f)
        private val OB_BENCH = floatArrayOf(2.12f, -2.56f, 2.17f, -2.62f, 2.46f, -2.90f, 2.62f, -2.90f, 3.24f, -2.30f, 3.26f, -2.26f, 3.27f, -2.11f, 2.99f, -1.82f, 2.95f, -1.78f, 2.91f, -1.77f, 2.84f, -1.78f, 2.15f, -2.47f)
        private val OB_POT = floatArrayOf(2.34f, 1.54f, 2.45f, 1.31f, 2.55f, 1.26f, 2.65f, 1.24f, 2.76f, 1.24f, 2.85f, 1.30f, 2.96f, 1.55f, 2.93f, 1.69f, 2.83f, 1.80f, 2.72f, 1.85f, 2.46f, 1.82f, 2.38f, 1.70f)
        private val OB_CHARGER = floatArrayOf(1.81f, 2.20f, 1.88f, 2.08f, 1.99f, 2.03f, 2.12f, 2.05f, 2.21f, 2.12f, 2.24f, 2.18f, 2.25f, 2.24f, 2.20f, 2.39f, 2.14f, 2.46f, 1.97f, 2.52f, 1.88f, 2.54f, 1.80f, 2.28f)
        private val OB_SNOWMAN = floatArrayOf(-3.05f, 1.79f, -3.03f, 1.68f, -2.98f, 1.60f, -2.91f, 1.52f, -2.77f, 1.46f, -2.57f, 1.48f, -2.27f, 1.59f, -2.37f, 1.92f, -2.50f, 2.08f, -2.61f, 2.14f, -2.70f, 2.15f, -3.05f, 2.12f)
        private val OB_CUSHION = floatArrayOf(-0.61f, -0.22f, -0.42f, -0.46f, -0.03f, -0.58f, 0.22f, -0.55f, 0.39f, -0.48f, 0.54f, -0.34f, 0.64f, 0.03f, 0.61f, 0.20f,
            0.42f, 0.45f, 0.30f, 0.72f, -0.30f, 0.72f, -0.50f, 0.37f, -0.62f, 0.14f)   // 쿠션 기준(x 옆, z 앞). 앞 0.72 = 앉은 사람 발끝
        private const val NAV_C = 0.05f; private const val NAV_O = -3.6f; private const val NAV_N = 144   // 5cm 칸, -3.6~3.6
        private const val NAV_INFL = 0.37f    // 몸 반지름 0.22 + 여유 0.15
        private const val NAV_RIM = 3.5f      // 받침판 안쪽 걷는 한계(뿌리)
        private const val B_FRONT0 = 5; private const val B_TREE = 10; private const val B_LAMP = 11; private const val B_BENCH = 12
        private const val B_POT = 13; private const val B_CHARGER = 14; private const val B_SNOWMAN = 15; private const val B_RIM = 16
        private const val TURN_RATE = 4.5f    // 걸을 때 몸 돌리는 빠르기(라디안/초)
        private val BIRD_TREE = floatArrayOf(1.31f, 1.70f, -2.14f)   // 나무 오른쪽 앞 맨가지 끝 윗면(make_plaza_glb.py BIRD_PERCH)
        private val BIRD_LAMP = floatArrayOf(-2.69f, 2.87f, -2.44f)  // 가로등 유리 꼭대기
        private const val FLY_MS = 1600L
        private const val TAKEOFF_MS = 600L; private const val LAND_MS = 600L   // 새 동작 takeoff·land 길이(0.6초)
        private const val BIRD_SCALE = 1.5f   // 2초 안에 새로 읽히게 1.5배
        private const val FX_H = 11f   // 비·눈 덩어리 높이(tools/make_plaza_glb.py FX_H)
        private const val RECLINE_AT = 40   // 운전석 등받이 값이 이 이상이면 젖힌 것으로 본다(가상 콘솔 실측 후 조정)
        private const val FRAME_60 = 16_666_667L; private const val FRAME_30 = 33_333_333L
        // 꾸밈 효과 이름(저사양 모드·시험 명령 dbg:off:이름)
        private const val FX_RAIN = "rain"      // 빗줄기·눈송이 덩어리
        private const val FX_SWAY = "sway"      // 나뭇잎·풀·꽃 흔들림
        private const val FX_LEAF = "leaf"      // 낙엽
        private const val FX_FLY = "fly"        // 새 날기(앉아 숨쉬기는 그대로)
        private const val FX_BIRDIDLE = "birdidle"   // 새 고개 돌리기·쪼기·콩콩
        private const val FX_BIRD = "bird"      // 새 뼈 동작 전체(시험용: 숨쉬기까지 멈춤)
        private const val FX_POOL = "pool"      // 가로등 바닥 빛 웅덩이(+ 비 올 때 젖은 바닥 반사)
        private const val FX_SHADOW = "shadow"  // 서 있는 사람 발밑 그림자
        private const val FX_AA = "aa"          // 계단 줄이기(FXAA, sRGB 면을 못 쓰는 기기)
        private const val FX_FADE = "fade"      // 날씨·밤 4초 전환
        /** 저사양 모드가 끄는 꾸밈 효과. 11/09 실측으로 CPU 차이가 있는 게 없어 비어 있다(위 저사양 모드 설명). */
        private val LOW_OFF = emptyList<String>()
    }

    // ---------- 바깥에서 쓰는 상태 ----------
    enum class Hit { PERSON, INVITE }
    class Pick(val kind: Hit, val slot: Int)

    /** 3D를 그리는 면. TextureView 는 매 장 창 전체를 다시 합성해서(RenderThread 20~28%) SurfaceView 로 바꿨다(11/08 밤 최적화).
     *  SurfaceView 는 창 아래에 따로 합성되므로 바탕색은 3D가 지우는 색(clearColor)으로 칠하고, 화면이 칠하는 바탕과 같은 색을 쓴다. */
    private val tv = SurfaceView(ctx)
    /** 비·눈(3D 장면 안 덩어리). mode 는 지금 보이는 것, level 은 진하기 0~1(날씨가 바뀔 때 서서히). */
    private var fxMode = ""; private var fxLevel = 0f; private var fxTinted = -1f
    private val veil = View(ctx).apply { setBackgroundColor(Color.argb(150, 255, 255, 255)); visibility = GONE }

    private val engine: Engine = Engine.create()
    private val srgbOut = runCatching { SwapChain.isSRGBSwapChainSupported(engine) }.getOrDefault(false)
    private val renderer: Renderer = engine.createRenderer()
    private val scene = engine.createScene()
    private val view = engine.createView()
    private val camEntity = EntityManager.get().create()
    private val camera: Camera = engine.createCamera(camEntity)
    private val ui = UiHelper(UiHelper.ContextErrorPolicy.DONT_CHECK)
    private val display = DisplayHelper(ctx)
    private var swap: SwapChain? = null
    private val provider = UbershaderProvider(engine)
    private val loader = AssetLoader(engine, provider, EntityManager.get())
    private val res = ResourceLoader(engine)
    private val charBuf: ByteBuffer? = readAsset("plaza_char2.glb")
    /** 사람 자산에서 뼈로 움직이는 덩어리(노드 이름 → 피부 번호, glb 안 JSON에서 읽음). gltfio 는 updateBoneMatrices 때 피부에 붙은 덩어리마다
     *  뼈 행렬을 GPU에 따로 올리므로(숨겨서 장면에서 뺀 머리·수염·목도리도), 숨긴 덩어리는 피부에서 떼어 둔다(11/09 CPU 최적화). */
    private val skinOf: Map<String, Int> = charBuf?.let { skinnedNodes(it) } ?: emptyMap()
    /** 사람 자산(인스턴스 5개를 한 번에 만들고 텍스처는 같이 씀). 읽는 동안 charLoading, 다 읽으면 charReady. */
    private var charAsset: FilamentAsset? = null
    private val pool = ArrayList<FilamentInstance>()
    private var charLoading = false; private var charReady = false
    private val clipIx = HashMap<String, Int>()
    private val clipLen = HashMap<Int, Float>()
    private var riseMs = 1170L; private var sitMs = 1000L    // 앉→서·서→앉 동작 길이(읽은 뒤 실제 값으로)
    private val faceBuf: ByteBuffer? = readAsset("plaza_face2.glb")
    /** 체형·얼굴형 모프를 CPU에서 섞어 끼우는 도구(MorphBake 설명: Filament 모프는 법선을 망가뜨려 턱이 갈라져 보였음, 11/10). */
    private val bakeChar: MorphBake? = charBuf?.let { b -> runCatching { MorphBake(b) }.onFailure { Hub.log("광장 모프 읽기 실패(사람): $it") }.getOrNull() }
    private val bakeFace: MorphBake? = faceBuf?.let { b -> runCatching { MorphBake(b) }.onFailure { Hub.log("광장 모프 읽기 실패(얼굴): $it") }.getOrNull() }
    /** 덩어리(엔티티)마다 지금 끼워 둔 CPU 모프 꼭짓점 버퍼. 다시 끼우거나 덩어리가 없어질 때 엔진에서 지운다. */
    private val bakedVb = HashMap<Int, List<com.google.android.filament.VertexBuffer>>()
    /** 덩어리마다 끼운 모프 값(같으면 다시 안 섞음). */
    private val bakedKey = HashMap<Int, String>()
    private val shadowBuf: ByteBuffer? = readAsset("plaza_shadow.glb")   // 서 있거나 걷는 사람 발밑 흐린 원판(앉은 사람은 쿠션 그림자 위)   // 얼굴 조각(사람마다 따로 읽어 face.png 자리에 그 사람 그림)
    private var headFwd = floatArrayOf(0f, 0f, 1f)                   // Head 뼈 기준 얼굴 앞 방향(쉬는 자세에서 잼)
    private val tmBuf4 = FloatArray(16)
    private val tmBuf = FloatArray(16); private val tmBuf2 = FloatArray(16); private val tmBuf3 = FloatArray(16)
    private val sceneBuf: ByteBuffer? = readAsset("plaza_scene.glb")
    private val birdBuf: ByteBuffer? = readAsset("plaza_bird.glb")
    private var stage: FilamentAsset? = null
    private val sampler = TextureSampler(TextureSampler.MinFilter.LINEAR, TextureSampler.MagFilter.LINEAR, TextureSampler.WrapMode.CLAMP_TO_EDGE)
    private val sun = EntityManager.get().create()
    /** 받침판 가운데(사람 가슴 높이)에서 가로등 쪽 방향(둘레빛의 따뜻한 몫이 오는 쪽). 사람은 가로등과의 거리와 상관없이
     *  같은 세기로 받는다(사람끼리 밝기 차이 10% 안쪽). 바닥은 빛 웅덩이(lamp_pool)가 발치에서 둥글게 옅어진다. */
    private var lampDir = floatArrayOf(-0.62f, 0.33f, -0.71f)
    private var ambAt = 0L
    private var ibl: IndirectLight? = null
    private var grading: ColorGrading? = null
    private var destroyed = false
    private var vw = 1; private var vh = 1

    // 날씨·밤 전환 값(아래 applyWeather 설명). init 에서 쓰므로 init 보다 위에 둔다
    private val envCur = FloatArray(ENV_N); private var envFrom = FloatArray(ENV_N); private var envTo = FloatArray(ENV_N)
    private var envAt = 0L; private var envInit = false
    /** 바탕색이 바뀔 때마다(전환 중 매 장) 화면이 본문 칸을 칠한다. */
    var onBackdrop: ((Int) -> Unit)? = null
    /** 장면에서 뺀(숨긴) 부품. init 에서 쓰므로 init 보다 위에. */
    private val hidden = HashSet<Int>()
    private val sway = LinkedHashMap<Int, FloatArray>()
    private var crownE = 0
    private var chargeSegs: List<Int> = emptyList()
    /** 움직이는 소품(새·낙엽·충전 기둥·눈사람): 이름 → (엔티티, 처음 변환). */
    private val props = HashMap<String, Pair<Int, FloatArray>>()
    // 새: 0 나무에 앉음, 1 가로등으로 나는 중, 2 가로등에 앉음, 3 나무로 나는 중
    private var birdState = 0; private var birdAt = 0L; private var birdNext = 0L
    /** 새(plaza_bird.glb, 뼈 + 동작 7개). 지금 동작 번호·시작 시각·되풀이 여부, 다음 앉은 동작 시각. */
    private var bird: FilamentAsset? = null
    private var birdAnim: com.google.android.filament.gltfio.Animator? = null
    private val birdClips = HashMap<String, Int>()
    private var birdPlay = -1; private var birdPlayAt = 0L; private var birdLoop = true; private var birdIdleNext = 0L
    private var birdShown = true
    // 낙엽 1장
    private var leafAt = 0L; private var leafNext = 0L; private var leafX = 0f; private var leafZ = 0f
    // 충전 기둥 올라옴(0~1), 눈사람(눈 오는 정차 시작 때), 등받이 기댐(0~1), 문 열림 본 때, 시간대
    private var chargeK = 0f; private var snowSince = 0L; private var snowStage = -1; private var reclineK = 0f
    private var doorSeen = 0L; private var phase = -1; private var phaseCheck = 0L
    private var lastSoc = -1; private var lastAmb: Int? = null
    /** 자리(1~5)마다 쿠션 위치(x, z)와 바라보는 방향. 장면 파일의 노드 위치에서 읽는다. */
    private val seats = HashMap<Int, FloatArray>()
    private var talk = floatArrayOf(0f, 0.12f, 2.3f)

    private val musOrig = HashMap<Int, FloatArray>()   // 콧수염 엔티티 → 원래 자리(머리 뼈 기준)

    private inner class Person(val p: PlazaPerson, val inst: FilamentInstance) {
        val ents: IntArray = inst.entities
        private val byName = HashMap<String, Int>().also { m -> val a = inst.asset; for (e in ents) a.getName(e)?.let { n -> if (!m.containsKey(n)) m[n] = e } }
        fun e(name: String) = byName[name] ?: 0
        /** 뼈로 움직이는 덩어리 엔티티 → 피부 번호(보일 때만 피부에 붙임). */
        val skinIx = HashMap<Int, Int>().also { m -> for ((n, si) in skinOf) byName[n]?.let { m[it] = si } }
        val root = inst.root
        val hips = e("mixamorig:Hips"); val head = e("mixamorig:Head"); val spine = e("mixamorig:Spine")
        val anim = inst.animator
        val h = HEIGHT[(if (dbgHeight >= 0) dbgHeight else p.avatar[Plaza.HEIGHT]).coerceIn(0, 2)]
        val hi = (if (dbgHeight >= 0) dbgHeight else p.avatar[Plaza.HEIGHT]).coerceIn(0, 2)
        var faceAsset: FilamentAsset? = null
        var shadow: FilamentAsset? = null; var shadowK = -1f
        val upLeg = intArrayOf(e("mixamorig:LeftUpLeg"), e("mixamorig:RightUpLeg")); val lowLeg = intArrayOf(e("mixamorig:LeftLeg"), e("mixamorig:RightLeg"))
        val foot = intArrayOf(e("mixamorig:LeftFoot"), e("mixamorig:RightFoot")); val toe = intArrayOf(e("mixamorig:LeftToeBase"), e("mixamorig:RightToeBase"))
        var legW = 0f; var curLeg = 0f; var prvLeg = 0f; var headLimit = 0.2f
        /** 해야 할 구간들(앞에서부터). 비어 있으면 자기 쿠션에 앉아 쉰다. */
        val segs = ArrayDeque<Seg>()
        var segAt = 0L
        // 지금 자세(다음 계획의 출발점·누르기 판정)
        var cx = 0f; var cz = 0f; var cyaw = 0f; var cstand = 0f
        // 고개(늘 도는 작은 생활): 6~9초마다 ±8° 안에서 새 방향
        var headFrom = 0f; var headTo = 0f; var headAt = 0L; var headNext = 0L
        /** 이 사람 몫 행동 주머니. 씨앗은 사람 코드 + 날짜만(대기·보낸 사람과 무관). */
        val rnd = Random(p.code.hashCode() * 31 + dayIndex())
        val bag = ArrayList<Int>(); var last = 0
        // ── 동작 재생: 지금 동작(clip)과 섞여 사라지는 이전 동작(prev) ──
        var clip = -1; var clipAt = 0L; var clipFrom = 0f; var clipTo = 0f; var clipMode = LOOP; var clipRate = 1f; var clipKey: Any? = null
        var prev = -1; var prevT = 0f; var fadeAt = 0L
        // 동작마다 따로 붙는 뿌리 값(높이·방향 보정·Hips 수평 되돌림). 지금 몫과 이전 몫을 섞는다
        var curY = 0f; var curYaw = 0f; var curCx = 0f; var curCz = 0f
        var prvY = 0f; var prvYaw = 0f; var prvCx = 0f; var prvCz = 0f
        // 이번 장에 뼈에 얹을 값(pose → animate)
        var rootYaw = 0f; var animT = 0f; var alpha = 1f; var compX = 0f; var compZ = 0f; var headYaw = 0f; var headPitch = 0f; var lean = 0f
        var propShown: String? = null
        // 걷기: 지금 구간(바뀐 때를 알려고), 구간 시작 때 몸 방향, 걷는 몸 방향(부드럽게 돎), 비켜 기다린 시간
        var segRef: Seg? = null; var segYaw0 = 0f; var walkYaw = 0f; var waitMs = 0f; var waiting = false; var holdAcc = 0f; var replans = 0
        fun busy() = segs.isNotEmpty()
        fun away() = segs.any { it.kind != SEAT }
    }
    /** 한 구간: a → b 로 ms 동안(STAND는 a에 서서 yawA → yawB). 몸짓 gest(바라볼 점 gx, gz). */
    private class Seg(val kind: Int, val ms: Long, val ax: Float, val az: Float, val bx: Float, val bz: Float,
                      val yawA: Float, val yawB: Float, val gest: Int = 0, val gx: Float = 0f, val gz: Float = 0f,
                      val path: FloatArray? = null, val cum: FloatArray? = null, val allow: Int = 0, val planned: Boolean = true)   // WALK: 길(점 x,z…)·누적 길이·지나도 되는 장애물 칸
    private val people = HashMap<Int, Person>()   // slot → 사람
    private var data: PlazaData? = null

    // 도착한 사람(말 거는 자리로 나온 사람)
    private var heroSlot = 0

    private var driving = false
    /** 오토홀드·파킹 브레이크로 서 있음(P 아님): 다 움직이되 걷기만 뺀다(사용자 11/08). */
    private var hold = false
    private var wakeAt = 0L          // 정차한 때(첫 5초는 걷지 않는다)
    private var nextAct = 0L         // 다음 돌아가며 하는 행동
    private val order = ArrayList<Int>()   // 다음 차례 자리(섞은 주머니)
    private var lampOn = false; private var lampK = 0f; private var lastLiveAt = 0L
    private var active = false
    private var weather = ""
    private var night = false
    /** 지금 날씨·밤의 바탕색(맑은 낮은 투명). 화면이 헤더 아래 본문 칸 전체를 이 색으로 칠한다. */
    var backdrop: Int = Color.TRANSPARENT
        private set
    private var talkTint = 0f; private var talkColor = Color.WHITE

    // ---------- 그리기 고리 ----------
    private val choreo = Choreographer.getInstance()
    private val main = Handler(Looper.getMainLooper())
    private var posted = false
    private var pending = 0
    private var drawn = 0; private var workNs = 0L
    private var frameDt = 16f   // 지난 장과의 간격(ms)
    private var lastTest: String? = null
    private var cpuAt = 0L; private var cpuMs = 0L
    /** 정차 중 그리기 목표 시각(vsync 나노초). 30장: 매번 33.33ms씩 더해 가며 그 시각이 된 vsync 에서만 그린다(고르게, 밀림 없이). */
    private var nextFrameNs = 0L
    /** 정차 중 한 장 간격(나노초). 기본 60장(11/09 사용자 결정), 저사양 모드면 30장. 시험 명령 dbg:fps60 / dbg:fps30 으로도 바꾼다. */
    private var frameIntervalNs = FRAME_60
    /** 고르기 점검(시험 빌드 로그): 그린 장 사이 가장 긴 간격, 한 장 간격의 1.35배(60장 22.5ms·30장 45ms)를 넘은(한 장 밀린) 횟수. */
    private var lastDrawNs = 0L; private var gapMaxNs = 0L; private var gapLate = 0
    private val frame = object : Choreographer.FrameCallback {
        override fun doFrame(t: Long) {
            posted = false
            if (destroyed || !active) return
            val now = SystemClock.uptimeMillis()
            if (!driving) {
                // 정차 중: 기본 초당 60장 = 화면 갱신(60Hz)마다 그린다. 저사양 모드는 30장: vsync 시각 t 기준으로 목표 시각을 33.33ms씩 쌓아 가며,
                // 아직이면 이번 vsync 는 건너뜀(고르게). 화면이 60Hz보다 빠르면 60장도 같은 방식으로 건너뛴다.
                // 움직임은 실제 경과 시간(uptime)으로 계산하므로 장수가 바뀌어도 빠르기는 같다
                val everyVsync = frameIntervalNs <= vsyncNs() * 1.05
                if (!everyVsync) {
                    if (nextFrameNs == 0L || t - nextFrameNs > 100_000_000L) nextFrameNs = t   // 처음·오래 멈췄다 다시: 지금부터
                    if (t < nextFrameNs - 3_000_000L) { post(); return }                          // 3ms 여유(vsync 흔들림)
                    nextFrameNs += frameIntervalNs
                }
                val t0 = System.nanoTime()
                update(now)
                draw(t); pending = 0; drawn++
                if (lastDrawNs != 0L) { val g = t - lastDrawNs; if (g > gapMaxNs) gapMaxNs = g; if (g > frameIntervalNs * 135 / 100) gapLate++ }
                lastDrawNs = t
                workNs += System.nanoTime() - t0
                watchCpu(now)
                if (everyVsync) { post(); return }   // 60장: 다음 vsync 에 바로
                // 30장: 사이 vsync(그리지 않을 장)에는 깨어나지 않는다. 다음 그릴 vsync 12ms 전에 vsync 를 청해 그 vsync 에 바로 그린다.
                // (예전엔 매 vsync 마다 깨어나 절반은 그냥 돌아감 → 메인 스레드·vsync 요청이 두 배)
                val wakeMs = (nextFrameNs - 12_000_000L - System.nanoTime()) / 1_000_000L
                if (wakeMs > 0 && !posted && !destroyed && !dbgVsyncAll) { posted = true; choreo.postFrameCallbackDelayed(this, wakeMs) } else post()
                return
            }
            if (pending > 0) { update(now); if (draw(t)) pending = max(0, pending - 1) }
            if (charLoading) { stepCharLoad(); post() }   // 주행 중에도 사람 자산은 끝까지 읽는다
            if (pending > 0) post()
        }
    }
    private fun post() { if (!posted && !destroyed) { posted = true; choreo.postFrameCallback(frame) } }
    /** 화면 한 번 갱신 간격(나노초). 모르면 60Hz. */
    private fun vsyncNs(): Long = (1e9 / (tv.display?.refreshRate?.takeIf { it > 1f } ?: 60f)).toLong()

    // ---------- 저사양 모드(설정, 11/09) ----------
    // 켜면 초당 30장. 사람·얼굴·걷기·앉기·인사·말 거는 자리·쿠션·초대 '+'는 그대로.
    // 꾸밈 효과(비·눈 줄기, 나무·풀 흔들림, 낙엽, 새 날기·몸짓, 가로등 빛 웅덩이, 발밑 그림자, FXAA, 날씨 4초 전환)는 11/09 에뮬레이터에서
    // 하나씩 끄고 재 봤으나 앱 CPU 차이가 재는 흔들림(±1~2%) 안이라 끄지 않는다(LOW_OFF 비어 있음). 줄어드는 몫은 거의 다 60→30장에서 나온다
    // (맑음 약 32~38% → 17~18%, 한 코어 기준). 에뮬레이터 GPU는 맥이 그려 재지 못했으므로, 실제 차에서 GPU가 모자라면 LOW_OFF에 FX_RAIN 등을 넣는다.
    // 효과별 끄기는 시험 명령(dbg:off:이름 / dbg:on:이름)으로 따로 재 볼 수 있다.
    private val off = HashSet<String>()
    private fun on(fx: String) = fx !in off
    /** 저사양 모드. 바로 적용(광장을 다시 만들지 않음). */
    var lowSpec = false
        set(v) {
            if (field == v) return
            field = v
            frameIntervalNs = if (v) FRAME_30 else FRAME_60; nextFrameNs = 0L; lastDrawNs = 0L
            for (fx in LOW_OFF) setFx(fx, !v)
            if (posted && !driving) { choreo.removeFrameCallback(frame); posted = false }
            kick()
        }
    /** 꾸밈 효과 하나 켜고 끄기. 끌 때 남은 모습을 제자리로 돌린다. */
    private fun setFx(fx: String, enabled: Boolean) {
        if (enabled == on(fx)) return
        if (enabled) off.remove(fx) else off.add(fx)
        val tm = engine.transformManager
        when (fx) {
            FX_SWAY -> if (!enabled) for ((e, m) in sway) set(tm, e, m)
            FX_LEAF -> if (!enabled) { props["leaf_fall"]?.let { (e, _) -> showE(e, false) }; leafAt = 0L; leafNext = 0L }
            FX_POOL -> applyLamp()
            FX_AA -> if (!srgbOut) view.setAntiAliasing(if (enabled) com.google.android.filament.View.AntiAliasing.FXAA else com.google.android.filament.View.AntiAliasing.NONE)
            FX_SHADOW -> if (!enabled) for (x in people.values) { x.shadow?.entities?.forEach { showE(it, false) }; x.shadowK = -1f } else for (x in people.values) x.shadowK = -1f
        }
    }
    /** 바뀐 게 있으니 한 장 그린다(첫 몇 장은 GPU가 건너뛸 수 있어 3장까지 시도). 정차 중엔 어차피 계속 그린다. */
    fun kick() { pending = max(pending, 3); post() }

    /** 5초마다 앱 CPU(한 코어 기준)·초당 장수·한 장에 메인 스레드가 쓴 시간을 잰다(시험 빌드만 기록). 장수를 낮추는 장치는 두지 않는다. */
    private fun watchCpu(now: Long) {
        if (cpuAt == 0L) { cpuAt = now; cpuMs = android.os.Process.getElapsedCpuTime(); return }
        if (now - cpuAt < 5000L) return
        val c = android.os.Process.getElapsedCpuTime()
        val frac = (c - cpuMs).toFloat() / (now - cpuAt)
        cpuAt = now; cpuMs = c
        if (BuildConfig.DEBUG) Hub.log("광장 물체 ${scene.renderableCount}개 · sRGB면 ${srgbOut} · 초당 ${drawn / 5}장(최대 간격 ${gapMaxNs / 1_000_000}ms, 밀림 ${gapLate}) · 한 장 ${"%.1f".format(if (drawn > 0) workNs / 1e6 / drawn else 0.0)}ms · 걷는 사람 ${people.values.count { it.away() }} · CPU ${(frac * 100).toInt()}% · 길 ${navPlans}번(실패 $navFails) · 장애물 침범 ${navObsHits}장 · 사람 겹침 ${navPeopleHits}장", quiet = true)
        drawn = 0; workNs = 0L; gapMaxNs = 0L; gapLate = 0
    }

    private fun dayIndex() = (System.currentTimeMillis() / 86_400_000L).toInt()
    private val rnd = Random(dayIndex() * 7919L)

    init {
        // 빗줄기·눈송이는 3D 장면 안에(돔 밖·뒤쪽에만 있어 얼굴 위로 안 내린다, 회의 11/08)
        addView(tv, LayoutParams(-1, -1))
        addView(veil, LayoutParams(-1, -1))
        view.setScene(scene); view.setCamera(camera)
        // 후처리(색 보정표·FXAA 패스)를 끄고 화면 면이 직접 sRGB 로 내보내게(지원하면). 그리기 단계가 줄고 색이 정확해진다(흰색 255 그대로).
        // 계단 현상은 MSAA 4배로 대신한다. sRGB 면을 못 쓰는 기기에선 예전처럼 후처리로.
        if (srgbOut) {
            view.isPostProcessingEnabled = false
            view.multiSampleAntiAliasingOptions = com.google.android.filament.View.MultiSampleAntiAliasingOptions().apply { enabled = true; sampleCount = 4 }
        } else view.setAntiAliasing(com.google.android.filament.View.AntiAliasing.FXAA)
        view.setShadowingEnabled(false)
        // 색은 정한 값 그대로 보이게(필름 톤 없이). 노출 1 = 빛 세기를 화면 값으로
        grading = ColorGrading.Builder().toneMapper(ToneMapper.Linear()).build(engine).also { view.setColorGrading(it) }
        camera.setExposure(1f)
        // 빛(11/10): Filament 는 방향광을 장면에 하나만 쓴다(여럿이면 가장 센 것 하나). 그래서 방향광은 해·달 하나(앞 위에서, 얼굴이 보이게)이고,
        // 하늘·땅에서 오는 부드러운 빛은 둘레빛(위가 밝은 2단 구면 조화), 가로등은 둘레빛의 따뜻한 몫 + 바닥 빛 웅덩이 + 유리 둘레 빛 번짐이다
        LightManager.Builder(LightManager.Type.DIRECTIONAL).direction(-0.35f, -1f, -0.55f).intensity(2.3f).castShadows(false).build(engine, sun)
        scene.addEntity(sun)
        envCur[4] = 0.32f; envCur[5] = 1f; envCur[6] = 1f; envCur[7] = 1f; ambient(true)
        sceneBuf?.let { b ->
            runCatching {
                val a = loader.createAsset(b) ?: error("장면 파일을 읽지 못함")
                res.loadResources(a)
                scene.addEntities(a.entities)
                stage = a
                val tm = engine.transformManager
                a.getFirstEntityByName("lamp_head").takeIf { it != 0 }?.let { e ->
                    val m = tm.getTransform(tm.getInstance(e), FloatArray(16))
                    lampDir = norm(floatArrayOf(m[12], m[13] - 0.9f, m[14]))
                }
                for (s in 1..5) {
                    val e = a.getFirstEntityByName("cushion$s")
                    if (e == 0) continue
                    val m = tm.getTransform(tm.getInstance(e), FloatArray(16))
                    val x = m[12]; val z = m[14]
                    seats[s] = floatArrayOf(x, z, atan2(0f - x, TARGET_Z - z))
                }
                a.getFirstEntityByName("talk").takeIf { it != 0 }?.let { e ->
                    val m = tm.getTransform(tm.getInstance(e), FloatArray(16)); talk = floatArrayOf(m[12], 0.12f, m[14])   // 높이 0.12 돌판
                }
                // 흔들리는 것(나뭇잎·풀): 처음 자리를 기억해 두고 그 위에 작은 회전만 얹는다
                crownE = a.getFirstEntityByName("tree_crown")
                for (n in listOf("leaf_fall", "charger", "snowman1", "snowman2", "snow_tree", "snow_branch", "snow_rim", "snow_lamp", "snow_pot", "rain_a", "rain_b", "snowfx_a", "snowfx_b")) {
                    val e = a.getFirstEntityByName(n); if (e != 0) props[n] = e to tm.getTransform(tm.getInstance(e), FloatArray(16))
                }
                // 충전 기둥은 땅 속에, 눈사람은 숨겨 두고 시작
                props["charger"]?.let { (e, m) -> tm.setTransform(tm.getInstance(e), M.mul(M.t(0f, -0.8f, 0f), m)) }
                for (n in listOf("snowman1", "snowman2", "rain_a", "rain_b", "snowfx_a", "snowfx_b")) show(a, n, false)
                runCatching { mi(a, "snowfx_a")?.setParameter("emissiveFactor", 0.85f, 0.87f, 0.9f) }   // 눈송이는 빛을 덜 받아도 하얗게
                props["leaf_fall"]?.let { (e, _) -> showE(e, false) }   // 떨어질 때까지 장면에서 뺌
                chargeSegs = (1..5).map { a.getFirstEntityByName("charge_seg$it") }
                props["charger"]?.let { (e, _) -> showE(e, false) }; chargeSegs.forEach { showE(it, false) }   // 충전구 열기 전엔 장면에서 뺌
                for (n in listOf("tree_crown", "pot_flowers") + (1..7).map { "grass$it" }) {
                    val e = a.getFirstEntityByName(n); if (e != 0) sway[e] = tm.getTransform(tm.getInstance(e), FloatArray(16))
                }
            }.onFailure { Hub.log("광장 장면 못 읽음: $it") }
        }
        // 새: 뼈 동작이 있어 따로 읽는다. 나무 가지 끝에 앉혀 숨쉬기 첫 장으로
        birdBuf?.let { b ->
            runCatching {
                val a = loader.createAsset(b) ?: error("새 파일을 읽지 못함")
                res.loadResources(a)
                scene.addEntities(a.entities)
                val an = a.instance.animator
                for (i in 0 until an.animationCount) birdClips[an.getAnimationName(i)] = i
                bird = a; birdAnim = an
                placeBird(engine.transformManager, BIRD_TREE, camYaw(BIRD_TREE[0], BIRD_TREE[2]) - 0.5f)
                birdClip("idle_breathe", 0L, true); stepBird(0L)
            }.onFailure { Hub.log("광장 새 못 읽음: $it") }
        }
        // 사람: 인스턴스 5개짜리 자산 하나. 텍스처(가발 16장 등)는 한 번만 읽어 5명이 같이 쓰고, 재질 인스턴스·뼈·동작은 사람마다 따로.
        // 텍스처 풀기는 뒤에서(asyncBeginLoad) → 매 장 asyncUpdateLoad, 다 되면 charReady(그 전에 받은 사람은 그때 나타남)
        charBuf?.let { b ->
            runCatching {
                val inst = arrayOfNulls<FilamentInstance>(POOL)
                val a = loader.createInstancedAsset(b, inst) ?: error("캐릭터 파일을 읽지 못함")
                res.addResourceData("face.png", pngOf(solidBitmap(Color.parseColor("#F2C9AC"))))   // 파일 속 얼굴 자리(사람마다 아래 faceTexture 로 바꿔 끼움)
                if (!res.asyncBeginLoad(a)) error("캐릭터 텍스처 읽기 시작 실패")
                charAsset = a; pool.addAll(inst.filterNotNull()); charLoading = true
                Hub.log("광장 사람 자산: 인스턴스 ${pool.size}개, 동작 ${pool.firstOrNull()?.animator?.animationCount ?: 0}개 읽는 중")
            }.onFailure { Hub.log("광장 사람 자산 못 읽음: $it") }
        }
        // 불투명 면: 바탕은 clearColor(=화면이 칠하는 바탕과 같은 색)로 지운다. clearColor 는 선형 값이라 sRGB 를 선형으로 바꿔 넣는다.
        // 예전 흰색이 249·247·247로 나온 건 디더링 탓이라 디더링은 끈다(11/08 밤)
        view.dithering = com.google.android.filament.View.Dithering.NONE
        ui.renderCallback = object : UiHelper.RendererCallback {
            override fun onNativeWindowChanged(surface: Surface) {
                swap?.let { engine.destroySwapChain(it) }
                swap = engine.createSwapChain(surface, ui.swapChainFlags or (if (srgbOut) SwapChainFlags.CONFIG_SRGB_COLORSPACE else 0L))
                tv.display?.let { display.attach(renderer, it) }
                applyClear()
                kick()
            }
            override fun onDetachedFromSurface() {
                display.detach()
                swap?.let { engine.destroySwapChain(it); engine.flushAndWait() }
                swap = null
            }
            override fun onResized(width: Int, height: Int) {
                vw = max(1, width); vh = max(1, height)
                view.setViewport(Viewport(0, 0, vw, vh))
                project()
                kick()
            }
        }
        ui.attachTo(tv)
        applyWeather()
        stageColors()   // 사람을 받기 전에는 쿠션을 숨겨 둔다(받침판·나무만)
    }

    /** glb 의 JSON 덩어리에서 skin 을 가진 메시 노드 이름 → 피부 번호. */
    private fun skinnedNodes(b: ByteBuffer): Map<String, Int> = runCatching {
        val d = b.duplicate().order(ByteOrder.LITTLE_ENDIAN)
        val len = d.getInt(12)
        val bytes = ByteArray(len); d.position(20); d.get(bytes)
        val nodes = org.json.JSONObject(String(bytes, Charsets.UTF_8)).optJSONArray("nodes") ?: return@runCatching emptyMap<String, Int>()
        val m = HashMap<String, Int>()
        for (i in 0 until nodes.length()) { val n = nodes.getJSONObject(i); if (n.has("skin") && n.has("mesh")) m[n.optString("name")] = n.getInt("skin") }
        m as Map<String, Int>
    }.onFailure { Hub.log("광장 사람 피부 목록 못 읽음: $it") }.getOrDefault(emptyMap())

    private fun readAsset(name: String): ByteBuffer? = runCatching {
        val bytes = context.assets.open(name).use { it.readBytes() }
        ByteBuffer.allocateDirect(bytes.size).order(ByteOrder.nativeOrder()).put(bytes).apply { rewind() }
    }.onFailure { Hub.log("광장 파일 없음: $name") }.getOrNull()

    /** 둘레빛(구면 조화 2단): 받는 빛 = 고른 몫(A) + 위쪽 몫(U·n.y, 하늘이 땅보다 밝게) + 가로등 쪽 따뜻한 몫(n·가로등 방향, 켜짐 정도만큼).
     *  흐린 날·밤엔 위쪽 몫이 있어 납작한 회색이 아니라 위가 밝고 아래가 차분한 부드러운 빛이 된다. 새로 만들어야 해서 0.1초마다만(final 이면 바로). */
    private fun ambient(final: Boolean) {
        val now = SystemClock.uptimeMillis()
        if (!final && now - ambAt < 100L) return
        ambAt = now
        val e = envCur
        val w = LAMP_AMB * lampK * e[22]
        val warm = lampColor()
        val sh = FloatArray(12)
        for (c in 0..2) {
            // 가로등 몫은 고른 60% + 가로등 쪽 40%(가로등을 등진 얼굴도 어두워지지 않게, 바닥에서 되비친 따뜻한 빛)
            // 앞 채움빛(31): 받는 빛 = 세기 × (0.5 + 0.5 × n·앞쪽) — 턱 아래·볼 아래처럼 해를 못 받는 얼굴 아래쪽도 앞에서 밝혀 준다(음수 없음)
            val f = e[31] * e[5 + c] * 0.5f
            sh[c] = e[4] * e[5 + c] + w * warm[c] * 0.6f + f
            sh[3 + c] = e[8] * e[9 + c] + w * warm[c] * 0.4f * lampDir[1] + f * FILL_DIR[1]   // n.y
            sh[6 + c] = w * warm[c] * 0.4f * lampDir[2] + f * FILL_DIR[2]                       // n.z
            sh[9 + c] = w * warm[c] * 0.4f * lampDir[0] + f * FILL_DIR[0]                       // n.x
        }
        val old = ibl
        val next = IndirectLight.Builder().irradiance(2, sh).intensity(1f).build(engine)
        scene.setIndirectLight(next)
        ibl = next
        old?.let { engine.destroyIndirectLight(it) }
    }

    // ---------- 카메라·화면 좌표 ----------
    private val fovV get() = if (vw.toFloat() / vh >= 1f) 36.0 else 2 * Math.toDegrees(Math.atan(tan(Math.toRadians(22.0)) / (vw.toDouble() / vh)))

    private fun project() {
        camera.lookAt(EYE[0].toDouble(), EYE[1].toDouble(), EYE[2].toDouble(), LOOK[0].toDouble(), LOOK[1].toDouble(), LOOK[2].toDouble(), 0.0, 1.0, 0.0)
        camera.setProjection(fovV, vw.toDouble() / vh, 0.1, 60.0, Camera.Fov.VERTICAL)
    }

    /** 장면 점 → 화면 픽셀(x, y). 카메라 뒤면 null. */
    private fun toScreen(x: Float, y: Float, z: Float): FloatArray? {
        val f = norm(floatArrayOf(LOOK[0] - EYE[0], LOOK[1] - EYE[1], LOOK[2] - EYE[2]))
        val r = norm(cross(f, floatArrayOf(0f, 1f, 0f)))
        val u = cross(r, f)
        val d = floatArrayOf(x - EYE[0], y - EYE[1], z - EYE[2])
        val zc = dot(d, f); if (zc <= 0.01f) return null
        val t = tan(Math.toRadians(fovV / 2)).toFloat()
        val aspect = vw.toFloat() / vh
        val nx = dot(d, r) / zc / (t * aspect); val ny = dot(d, u) / zc / t
        return floatArrayOf((nx + 1f) / 2f * vw, (1f - ny) / 2f * vh)
    }
    private fun norm(v: FloatArray): FloatArray { val l = sqrt(dot(v, v)); return floatArrayOf(v[0] / l, v[1] / l, v[2] / l) }
    private fun dot(a: FloatArray, b: FloatArray) = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    private fun cross(a: FloatArray, b: FloatArray) = floatArrayOf(a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

    /** 누른 곳(이 뷰 좌표)의 사람·쿠션: 사람(지금 서 있는 자리 기준, 걷는 중이어도) → PERSON, 회색 '+' 쿠션 → INVITE, 빈 곳 → null. */
    fun pick(px: Float, py: Float): Pick? {
        val d = data ?: return null
        var best: Pick? = null; var bestD = Float.MAX_VALUE
        val reach = 0.09f * min(vw, vh) + 24f
        fun near(kind: Hit, s: Int, x: Float, z: Float, ys: FloatArray) {
            for (yy in ys) {
                val sp = toScreen(x, yy, z) ?: continue
                val dist = hypot(sp[0] - px, sp[1] - py)
                if (dist < reach && dist < bestD) { bestD = dist; best = Pick(kind, s) }
            }
        }
        for ((s, x) in people) if (s != heroSlot && d.bySlot(s) != null) near(Hit.PERSON, s, x.cx, x.cz, floatArrayOf(0.6f + x.cstand * 0.2f, 1.1f + x.cstand * 0.25f))
        d.nextSlot?.let { s -> seats[s]?.let { near(Hit.INVITE, s, it[0], it[1], floatArrayOf(0.45f, 1.1f)) } }
        return best
    }

    // ---------- 바깥에서 부르는 것 ----------

    /** 화면에 보이는 동안만 그린다(숨기면 멈춤). 정차 중 그리기를 쉬는 건 이때뿐이다. */
    fun setActive(on: Boolean) {
        if (active == on) return
        active = on; lastDrawNs = 0L
        if (on) kick() else if (posted) { choreo.removeFrameCallback(frame); posted = false }
    }

    /** 주행 중이면 모두 자기 쿠션 기본 자세로 굳히고 그리기를 멈춘다(바뀔 때 1장만). 정차하면 다시 늘 그린다. */
    fun setDriving(d: Boolean) {
        if (driving == d) return
        driving = d; lastDrawNs = 0L
        val now = SystemClock.uptimeMillis()
        if (d) {
            for (x in people.values) { x.segs.clear(); if (x.p.slot == heroSlot) heroStatic(x) }
            lampK = if (lampOn) 1f else 0f; applyLamp()
            // 바뀌던 날씨·밤은 끝 값으로 한 장에(주행 중엔 서서히 바꾸지 않는다)
            if (envAt != 0L) { envTo.copyInto(envCur); envAt = 0L; applyEnv(true) }
            fxMode = weather; fxLevel = if (weather == "rain" || weather == "snow") 1f else 0f
        } else { wakeAt = now; nextAct = now + 4000L }
        kick()
    }

    /** 오토홀드·파킹 브레이크로 서 있는 중(P 아님): 걷기만 뺀다. */
    fun setHold(h: Boolean) { hold = h }

    /** 흐림(쓰지 않음, 11/08). 예전 호출과 맞추려고 남겨 둔다. */
    fun setBlur(on: Boolean) {
        if (Build.VERSION.SDK_INT >= 31) setRenderEffect(if (on) RenderEffect.createBlurEffect(22f, 22f, Shader.TileMode.CLAMP) else null)
        else veil.visibility = if (on) VISIBLE else GONE
    }

    /** P(정차)로 들어왔다: 다 같이 손 흔들기(오래 달린 뒤엔 기지개), 그 뒤 생활로 흩어진다. 첫 5초는 걷지 않는다. */
    fun greet() {
        if (driving || destroyed) return
        val now = SystemClock.uptimeMillis()
        for (x in people.values) {
            if (x.p.slot == heroSlot || x.away()) continue
            x.segs.clear(); x.segAt = now
            // 30분 넘게 달렸으면(시험은 1분) 손 흔들기 대신 기지개(64번 27)
            val long = Hub.lastTripMs >= if (Hub.shortTimes) 60_000L else 1_800_000L
            x.segs.add(if (long) seatGest(x, G_STRETCH, clipMs(C_SIT_STRETCH, 2970L)) else seatGest(x, G_WAVE, clipMs(C_SIT_WAVE, 2100L)))
        }
        wakeAt = now; nextAct = now + 4500L
        post()
    }

    /** 사람을 눌렀다: 그 사람이 바로 이쪽을 보며 손을 든다(앉아 쉬는 중일 때). */
    fun react(slot: Int) {
        val x = people[slot] ?: return
        if (driving || x.away() || slot == heroSlot) return
        x.segs.clear(); x.segAt = SystemClock.uptimeMillis(); x.segs.add(seatGest(x, G_WAVE, clipMs(C_SIT_WAVE, 2100L)))
        post()
    }

    /** 앉은 사람을 서버 값으로 맞춘다(바뀐 사람만 다시 만든다). */
    fun setPeople(d: PlazaData?) {
        if (destroyed || d == data) return
        data = d
        val want = d?.people?.associateBy { it.slot } ?: emptyMap()
        // 빠졌거나 바뀐 사람은 지운다
        people.keys.toList().forEach { s -> if (want[s] != people[s]!!.p) remove(s) }
        want.forEach { (s, p) -> if (people[s] == null && seats.containsKey(s)) add(p) }
        if (heroSlot != 0 && people[heroSlot] == null) heroSlot = 0
        stageColors()
        kick()
    }

    /** 사람 자산 읽기 한 걸음(매 장). 다 읽으면 동작 번호를 기억하고 기다리던 사람을 만든다. */
    private fun stepCharLoad() {
        if (!charLoading) return
        res.asyncUpdateLoad()
        if (res.asyncGetLoadProgress() < 1f) return
        charLoading = false; res.evictResourceData()
        val an = pool.firstOrNull()?.animator ?: return
        for (i in 0 until an.animationCount) { clipIx[an.getAnimationName(i)] = i; clipLen[i] = an.getAnimationDuration(i) }
        clipIx[C_RISE]?.let { riseMs = (clipLen[it]!! * 1000f).toLong() }
        clipIx[C_SITDOWN]?.let { sitMs = (clipLen[it]!! * 1000f).toLong() }
        // 얼굴 앞 방향(Head 뼈 기준): 새 인스턴스는 쉬는 자세 = 몸 앞 +Z
        pool.firstOrNull()?.let { i -> val a = i.asset; i.entities.firstOrNull { a.getName(it) == "mixamorig:Head" }?.let { he ->
            val tm = engine.transformManager; val w = tm.getWorldTransform(tm.getInstance(he), tmBuf)
            val l = sqrt(w[2] * w[2] + w[6] * w[6] + w[10] * w[10]); headFwd = floatArrayOf(w[2] / l, w[6] / l, w[10] / l) } }
        charReady = true
        buildNav()   // 걷는 길 칸(init 에서 부르면 아래쪽 필드 초기값이 덮어써서 여기서)
        // 자기 점검(로그): 인스턴스마다 재질 인스턴스가 따로인지(같으면 색·얼굴이 5명 모두 같이 바뀜 → 사람마다 createAsset 으로 되돌려야 함)
        runCatching {
            val rm = engine.renderableManager
            fun faceMi(i: FilamentInstance): Long { val a = i.asset; val e = i.entities.firstOrNull { a.getName(it) == "face" } ?: return 0L
                return rm.getMaterialInstanceAt(rm.getInstance(e), 0).nativeObject }
            if (pool.size >= 2) Hub.log("광장 사람 재질 인스턴스 따로: ${faceMi(pool[0]) != faceMi(pool[1])}")
        }
        val miss = listOf(C_SIT, C_SIT_WAVE, C_SIT_YAWN, C_SIT_STRETCH, C_DRINK, C_DOZE, C_RISE, C_SITDOWN, C_WALK, C_IDLE, C_LOOK, C_CHAT, C_WAVE1, C_STRETCH).filter { it !in clipIx }
        Hub.log("광장 사람 자산 준비: 동작 ${clipIx.size}개${if (miss.isNotEmpty()) " · 없는 동작 $miss" else ""}")
        data?.let { d -> d.people.forEach { p -> if (people[p.slot] == null && seats.containsKey(p.slot)) add(p) } }
        kick()
    }

    private fun solidBitmap(c: Int) = android.graphics.Bitmap.createBitmap(4, 4, android.graphics.Bitmap.Config.ARGB_8888).apply { eraseColor(c) }
    private fun pngOf(bmp: android.graphics.Bitmap): ByteBuffer {
        val png = java.io.ByteArrayOutputStream().also { bmp.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }.toByteArray()
        return ByteBuffer.allocateDirect(png.size).put(png).also { it.rewind() }
    }
    private fun add(p: PlazaPerson) {
        if (!charReady) return   // 읽는 중이면 다 읽은 뒤 stepCharLoad 가 만든다
        val inst = pool.removeLastOrNull() ?: run { Hub.log("광장 사람 자리 없음(${p.slot})"); return }
        runCatching {
            val x = Person(p, inst)
            for ((e, si) in x.skinIx) inst.attachSkin(si, e)   // 앞 사람이 떼어 둔 덩어리도 다시 붙이고, dress 가 숨기는 것만 뗀다
            sitSpot(p.slot, x.hi).let { x.cx = it[0]; x.cz = it[1] }; x.cyaw = seats[p.slot]!![2]
            scene.addEntities(inst.entities)   // 먼저 다 넣고, dress 가 안 쓰는 머리·안경·수염·소품을 장면에서 뺀다
            // 얼굴: 따로 된 작은 자산(plaza_face2.glb)을 사람마다 읽으며 face.png 자리에 그 사람 그림을 넣고 Head 뼈에 붙인다.
            // (인스턴스 5개는 텍스처를 같이 쓰고, gltfio 재질에 baseColorMap 을 다시 꽂으면 무시됨 — 11/09 에뮬레이터에서 빨간 텍스처로 확인)
            val bmp = Plaza.drawFace(FACE_PX, p.avatar, Plaza.skin(p.avatar))
            showE(x.e("face"), false)   // 인스턴스 쪽 얼굴 조각은 안 씀
            faceBuf?.let { fb ->
                fb.rewind()
                val fa = loader.createAsset(fb) ?: error("얼굴 파일을 읽지 못함")
                res.addResourceData("face.png", pngOf(bmp)); res.loadResources(fa); res.evictResourceData()
                val tm = engine.transformManager
                tm.setParent(tm.getInstance(fa.root), tm.getInstance(x.head))
                scene.addEntities(fa.entities); x.faceAsset = fa
            } ?: Hub.log("광장 얼굴 파일 없음")
            shadowBuf?.let { sb -> sb.rewind(); loader.createAsset(sb)?.let { sa -> res.loadResources(sa); x.shadow = sa; sa.entities.forEach { showE(it, false) }; scene.addEntities(sa.entities); sa.entities.forEach { e -> hidden.add(e); scene.removeEntity(e) } } }
            // 뼈로 움직이는 몸은 쉬는 자세 상자로 가려 잘릴 수 있어 가림 판정을 끈다(문서 68)
            engine.renderableManager.let { rm -> rm.getInstance(x.e("body")).takeIf { it != 0 }?.let { rm.setCulling(it, false) } }
            dress(x)
            if (BuildConfig.DEBUG) Hub.log("광장 사람 ${p.slot}: 뼈 덩어리 ${x.skinIx.size}개 중 붙인 것 ${x.skinIx.keys.count { it !in hidden }}개", quiet = true)
            people[p.slot] = x
        }.onFailure { pool.add(inst); scene.removeEntities(inst.entities); Hub.log("광장 사람 못 만듦(${p.slot}): $it") }
    }

    private fun remove(s: Int) {
        val x = people.remove(s) ?: return
        scene.removeEntities(x.ents)
        x.ents.forEach { hidden.remove(it) }
        x.faceAsset?.let { fa -> scene.removeEntities(fa.entities); val es = fa.entities; loader.destroyAsset(fa); es.forEach { e -> bakedKey.remove(e); bakedVb.remove(e)?.forEach { engine.destroyVertexBuffer(it) } } }; x.faceAsset = null
        x.shadow?.let { sa -> scene.removeEntities(sa.entities); sa.entities.forEach { hidden.remove(it) }; loader.destroyAsset(sa) }; x.shadow = null
        pool.add(x.inst)
    }

    /** 사람 x의 노드 재질(첫 덩어리). 인스턴스마다 재질 인스턴스가 따로라 색이 사람마다 다르다. */
    private fun mi(x: Person, node: String): MaterialInstance? {
        val e = x.e(node); if (e == 0) return null
        val rm = engine.renderableManager
        val i = rm.getInstance(e); if (i == 0) return null
        return rm.getMaterialInstanceAt(i, 0)
    }
    private fun mi(a: FilamentAsset, node: String): MaterialInstance? {
        val e = a.getFirstEntityByName(node); if (e == 0) return null
        val rm = engine.renderableManager
        val i = rm.getInstance(e); if (i == 0) return null
        return rm.getMaterialInstanceAt(i, 0)
    }
    private fun tint(m: MaterialInstance?, c: Int, alpha: Float = 1f) =
        m?.setParameter("baseColorFactor", Colors.RgbaType.SRGB, Color.red(c) / 255f, Color.green(c) / 255f, Color.blue(c) / 255f, alpha)
    /** 숨긴 부품은 장면에서 아예 뺀다(가림 처리·그리기 목록에 안 들어가 매 장 비용이 준다). 다시 보이면 넣는다. */
    private fun show(a: FilamentAsset, node: String, on: Boolean) { showE(a.getFirstEntityByName(node), on) }
    private fun showE(e: Int, on: Boolean) {
        if (e == 0) return
        if (on) { if (hidden.remove(e)) scene.addEntity(e) } else if (hidden.add(e)) scene.removeEntity(e)
    }

    /** 사람 부품 보이기: 장면에 넣고 빼기 + 뼈로 움직이는 덩어리면 피부에 붙이고 떼기(뗀 덩어리는 매 장 뼈 행렬을 GPU에 올리지 않는다).
     *  다시 붙이면 같은 장의 animate(updateBoneMatrices)가 그리기 전에 뼈를 채운다. */
    private fun showPart(x: Person, e: Int, on: Boolean) {
        if (e == 0) return
        showE(e, on)
        x.skinIx[e]?.let { si -> if (on) x.inst.attachSkin(si, e) else x.inst.detachSkin(si, e) }
    }

    /** 사람마다 부품 보이기·색·모프: 대표색 윗옷, 피부색 몸(손·목), 머리색 가발, 수염색 수염, 체형·얼굴형 모프. 손 소품은 기본 숨김. */
    private fun dress(x: Person) {
        val a = x.p.avatar
        val hair = HAIR_NODES.getOrNull(a[Plaza.HAIR])
        for (n in HAIR_NODES) if (n != null) showPart(x, x.e(n), n == hair)
        val bd = a.getOrElse(Plaza.BEARDS) { 0 }   // 11/10 수염 비트: 1 짧은 수염(얼굴 그림)·2 콧수염·4 턱수염
        showPart(x, x.e("beard_mus"), bd and 2 != 0 && bd and 4 == 0)    // 콧수염(턱수염과 둘 중 하나: 턱수염 3D 에 콧수염이 붙어 있다)
        showPart(x, x.e("beard_long"), bd and 4 != 0)   // 턱수염(예전 긴 수염)
        x.e("beard_mus").takeIf { it != 0 }?.let { me ->   // 콧수염 줄여 올리기(MUS_S): 머리 뼈 기준 원래 자리 × 기준점 둘레 크기. 인스턴스를 돌려 쓰므로 원래 자리는 처음 한 번만 읽는다
            val tm = engine.transformManager; val ti = tm.getInstance(me)
            if (ti != 0) {
                val o = musOrig.getOrPut(me) { tm.getTransform(ti, FloatArray(16)) }
                val fw = if (a[Plaza.FACE] == 5 || a[Plaza.FACE] == 6) MUS_WIDE else 1f
                val (px, py, pz) = MUS_PIVOT
                tm.setTransform(ti, M.mul(o, M.mul(M.t(px, py, pz), M.mul(M.s(MUS_S[0] * fw, MUS_S[1], MUS_S[2]), M.t(-px, -py, -pz)))))
            }
        }
        for (n in GLASSES) if (n != null) showPart(x, x.e(n), n == GLASSES.getOrNull(a[Plaza.GLASSES]))
        GLASSES.getOrNull(a[Plaza.GLASSES])?.let { tint(mi(x, it), Plaza.glassesColor(a)) }   // 안경테 색(83번, 재질 glasses)
        // 꾸밈 칸(acc, 16번째 칸): 0 없음, 1 목도리. 이어폰은 뺐다(11/09 사용자) → 노드가 남아 있어도 늘 숨김(없으면 e()가 0이라 그냥 넘어감)
        val acc = a.getOrElse(15) { 0 }
        showPart(x, x.e("earbud"), false); showPart(x, x.e("scarf"), acc == 1)
        if (acc == 1) tint(mi(x, "scarf"), Plaza.scarfColor(a))   // 목도리 색(17번째 칸, 대표색 8가지): 회색 무늬 × 색
        for (n in PROPS_IN_HAND) showPart(x, x.e(n), false); x.propShown = null
        // 색: 몸은 덩어리 4개(skin·top·pants·shoes) 재질 이름으로. 바지는 83번 바지 색, 신발은 파일 기본색
        val rm = engine.renderableManager
        val skin = Plaza.skin(a); val cloth = Plaza.color(x.p.color); val pants = Plaza.pantsColor(a)
        rm.getInstance(x.e("body")).takeIf { it != 0 }?.let { ri ->
            for (k in 0 until rm.getPrimitiveCount(ri)) {
                val m = rm.getMaterialInstanceAt(ri, k)
                when (m.name) { "skin" -> tint(m, skin); "top" -> tint(m, cloth); "pants" -> tint(m, pants) }
            }
        }
        val hc = Plaza.hairColor(a)
        for (n in HAIR_NODES) if (n != null) tint(mi(x, n), hc)
        val bc = Plaza.beardColor(a)
        tint(mi(x, "beard_mus"), bc); tint(mi(x, "beard_long"), bc)
        // 모프: 체형(0 날씬 → build_slim, 2 듬직 → build_chubby), 얼굴형(1 갸름 → face_slim, 2 각진 → face_square). 같은 이름의 모프가 있는 덩어리 모두(몸·얼굴·가발·수염·안경·목도리)
        // 83번: 3·4 는 형태 중간값 0.5(조금 날씬·조금 듬직, 조금 갸름·조금 각진). 웹 avatar3d.js BUILD_W·FACE_W 와 같다
        val w = HashMap<String, Float>()
        val bw = BUILD_W.getOrElse(a[Plaza.BUILD]) { BUILD_W[1] }; val fw = FACE_W.getOrElse(a[Plaza.FACE]) { FACE_W[0] }
        w["build_slim"] = bw[0]; w["build_chubby"] = bw[1]
        w["face_slim"] = fw[0]; w["face_square"] = fw[1]; w["face_full"] = fw[2]
        // Filament 모프 대신 CPU에서 섞어 끼운다(MorphBake). 보이는 덩어리만(숨긴 가발 등은 나중에 보일 때 그 사람 모양으로 다시)
        // 이미 같은 값으로 끼웠으면 건너뛰고, 한 번도 안 끼운 덩어리는 모프가 모두 0이면 파일 그대로 둔다(메모리·시간 아끼기)
        val key = w.toSortedMap().entries.joinToString { "${it.key}=${it.value}" }
        val zero = w.values.all { it == 0f }
        fun bake(tool: MorphBake?, asset: FilamentAsset, e: Int) {
            if (tool == null || e in hidden) return
            if (bakedKey[e] == key || (zero && e !in bakedKey)) return
            val name = asset.getName(e) ?: return
            val ri = rm.getInstance(e); if (ri == 0 || rm.getMorphTargetCount(ri) <= 0 || !tool.hasMorphs(name)) return
            val made = runCatching { tool.apply(engine, rm, ri, name, w) }.onFailure { Hub.log("광장 모프 섞기 실패($name): $it") }.getOrNull() ?: return
            bakedVb.put(e, made)?.forEach { engine.destroyVertexBuffer(it) }
            bakedKey[e] = key
        }
        for (e in x.ents) bake(bakeChar, x.inst.asset, e)
        x.faceAsset?.let { fa -> for (e in fa.entities) bake(bakeFace, fa, e) }
    }
    /** 손 소품 하나만 보이기(null이면 모두 숨김). 바뀔 때만 장면을 고친다. */
    private fun holdProp(x: Person, name: String?) {
        if (x.propShown == name) return
        x.propShown?.let { showPart(x, x.e(it), false) }
        name?.let { showPart(x, x.e(it), true) }
        x.propShown = name
    }

    /** 쿠션 색과 '+': 앉은 사람은 대표색, 다음 초대 자리 하나만 회색 + '+', 그 뒤 빈자리는 안 보인다. */
    private fun stageColors() {
        val a = stage ?: return
        val d = data
        for (s in 1..5) {
            val p = d?.bySlot(s)
            val invite = d != null && d.nextSlot == s
            show(a, "cushion$s", p != null || invite)
            show(a, "plus$s", invite)
            tint(mi(a, "cushion$s"), if (p != null) Plaza.color(p.color) else Color.parseColor("#B9BCC2"))
        }
        val beige = Color.parseColor("#EBDCC6")
        val c = if (talkTint > 0f) mix(beige, talkColor, talkTint) else beige
        tint(mi(a, "talk"), c)
    }
    private fun mix(a: Int, b: Int, k: Float) = Color.rgb((Color.red(a) * (1 - k) + Color.red(b) * k).toInt(), (Color.green(a) * (1 - k) + Color.green(b) * k).toInt(), (Color.blue(a) * (1 - k) + Color.blue(b) * k).toInt())

    /**
     * 말 거는 자리에 나온 사람. slot 0이면 아무도 없음(나와 있던 사람은 쿠션으로).
     * walk: 정차 중이면 지금 있는 자리(쿠션·걷던 곳)에서 바로 걸어 나온다(최대 2.5초). 돌아갈 때도 걸어 가서 앉고 손을 흔든다.
     * 주행 중이면 결과 자세로 바로. 주인공이 나와 있는 동안 다른 사람은 큰 동작을 쉰다.
     * tint: 원판 윗면 대표색 비율(도착 0.2, 재생 0.4).
     */
    fun setHero(slot: Int, walk: Boolean, tint: Float) {
        val s = if (slot != 0 && people[slot] != null) slot else 0
        val now = SystemClock.uptimeMillis()
        val w = walk && !driving
        if (s != heroSlot) {
            people[heroSlot]?.let { old -> if (w) { goHome(old, now); old.segs.add(seatGest(old, G_WAVE, clipMs(C_SIT_WAVE, 2100L))) } else old.segs.clear() }
            heroSlot = s
            people[s]?.let { x ->
                if (w) {
                    // 다른 사람: 걷던 사람은 쿠션으로, 앉은 몸짓은 그만
                    for (o in people.values) if (o !== x) { if (o.away()) goHome(o, now) else o.segs.clear() }
                    goTalk(x, now)
                } else heroStatic(x)
            }
        }
        val newTint = if (s != 0) tint else 0f
        val newColor = people[s]?.p?.color?.let { Plaza.color(it) } ?: Color.WHITE
        if (newTint != talkTint || newColor != talkColor) { talkTint = newTint; talkColor = newColor; stageColors() }
        kick()
    }

    /**
     * 날씨: rain(유리 돔 + 빗줄기) · snow(돔 + 눈 캡 + 눈송이) · 그 밖은 맑음. night면 바탕을 어둡게.
     * lamp: 가로등(전조등 신호, 없으면 야간 모드). 정차 중엔 3초에 걸쳐 켜지고 꺼진다. 주행 중엔 바로.
     */
    fun setWeather(w: String, isNight: Boolean, lamp: Boolean = isNight) {
        if (lamp != lampOn) { lampOn = lamp; if (driving) { lampK = if (lamp) 1f else 0f; applyLamp() }; kick() }
        if (w == weather && isNight == night) return
        weather = w; night = isNight
        applyWeather(); kick()
    }

    /** 가로등 빛 색: 따뜻한 호박색. 무드등이 있으면 색은 30%만 섞는다(넘으면 게임처럼 보임). */
    private fun lampColor(): FloatArray {
        val amb = Hub.ambientColor
        val r0 = 1f; val g0 = 0.8f; val b0 = 0.56f
        return if (amb != null) floatArrayOf(lerp(r0, Color.red(amb) / 255f, .3f), lerp(g0, Color.green(amb) / 255f, .3f), lerp(b0, Color.blue(amb) / 255f, .3f))
        else floatArrayOf(r0, g0, b0)
    }

    /** 가로등 켜짐 정도(0~1): 유리가 호박색으로 빛나고 둘레로 빛이 번지며, 발치 바닥에 따뜻한 빛 웅덩이가 둥글게 옅어진다(비 오면 젖은 바닥에 길게 비침).
     *  사람에게는 가로등 쪽 따뜻한 둘레빛이 모두 같은 세기로 닿는다. 밝은 낮의 비에선 envCur[22]만큼 약하게. 깜빡이지 않는다. */
    private fun applyLamp(amb: Boolean = true) {
        val a = stage ?: return
        val k = lampK
        val s = envCur[22]   // 주변이 어두운 정도(밤 1, 비 오는 낮 0.35)
        val glass = mix(Color.parseColor("#F3EDE2"), Color.parseColor("#FFD9A0"), k)
        val g = mi(a, "lamp_glass") ?: mi(a, "lamp_head")
        tint(mi(a, "lamp_head"), glass)
        runCatching { g?.setParameter("emissiveFactor", 1.0f * k, 0.78f * k, 0.48f * k) }
        val c = lampColor()
        val warm = Color.rgb((c[0] * 255).toInt(), (c[1] * 255).toInt(), (c[2] * 255).toInt())
        // 무드등 밝기에 맞춰 바닥 빛 70~100%
        val br = Hub.ambientBright?.let { v -> 0.7f + 0.3f * (if (v <= 10) v / 10f else v / 100f).coerceIn(0f, 1f) } ?: 1f
        tint(mi(a, "lamp_pool"), mix(warm, Color.WHITE, 0.45f), POOL_A * k * s * br)   // 바닥에 닿은 빛은 유리보다 옅은 크림색(주황 얼룩이 되지 않게)
        show(a, "lamp_pool", k * s > 0.01f && on(FX_POOL))
        // 젖은 바닥에 길게 비친 가로등(비 올 때, 물웅덩이 진하기 = 젖은 정도)
        val wet = (envCur[16] / 0.7f).coerceIn(0f, 1f)
        tint(mi(a, "lamp_wet"), warm, WET_A * k * s * wet * br)
        show(a, "lamp_wet", k * s * wet > 0.01f && on(FX_POOL))
        tint(mi(a, "lamp_halo"), Color.parseColor("#FFD9A0"), HALO_A * k * (0.35f + 0.65f * s))
        show(a, "lamp_halo", k > 0.01f)
        if (amb) ambient(k <= 0f || k >= 1f)
    }

    // ---------- 날씨·밤·시간대 전환(11/08 밤: 바로 바뀌지 않고 4초에 걸쳐 자연스럽게) ----------
    // 환경 값 묶음: 0 해·달 세기, 1~3 해·달 색, 4 둘레빛 고른 몫, 5~7 그 색, 8 둘레빛 위쪽 몫(하늘이 밝게), 9~11 그 색, 12~14 받침판 색,
    // 15 유리 돔 투명도, 16 물웅덩이 투명도, 17 눈 쌓임(0~1), 18~21 바탕(알파·빨·초·파), 22 가로등이 보이는 정도(주변 어두움, 밤 1),
    // 23 받침판 거칠기(젖으면 낮아져 가로등·하늘이 은은히 비침), 24 바탕 흐린 빛 진하기, 25~27 그 색, 28~30 물웅덩이 색, 31 앞 채움빛(맑은 날)
    //
    // 자연스러운 빛(11/10, 사용자 "비 오거나 밤일 때 조명이 부자연스럽다"):
    // - 비(흐림): 해는 약하고 서늘하게, 대신 하늘 둘레빛이 위에서 고르게(그림자·명암이 부드럽고 낮은 대비). 받침판은 젖어 살짝 어둡고 매끈하게.
    // - 밤: 푸른 달빛(약하게, 앞 위에서라 얼굴이 보임) + 위가 조금 밝은 남색 둘레빛 + 가로등(발치 빛 웅덩이, 사람에겐 고른 따뜻한 둘레빛).
    //   받침판은 64번 14(약 25% 차분하게)보다 더 낮춘 서늘한 회색: 달빛 아래 땅이 얼굴보다 밝지 않게, 테두리는 남색 바탕과 구분되게 남긴다.
    // - 눈: 밝고 서늘한 흩어진 빛. 바탕 흐린 빛은 바탕색보다 조금 밝게 받침판 뒤에서 퍼진다.

    private fun applyWeather() {
        phase = dayPhase()
        val wet = weather == "rain" || weather == "snow"
        val t = FloatArray(ENV_N)
        fun put(i: Int, vararg v: Float) { for (k in v.indices) t[i + k] = v[k] }
        fun hex(i: Int, c: String) = Color.parseColor(c).let { t[i] = Color.red(it) / 255f; t[i + 1] = Color.green(it) / 255f; t[i + 2] = Color.blue(it) / 255f }
        var bg = Color.TRANSPARENT
        t[23] = 0.9f
        when {
            night -> {
                // 달빛: 푸르고 약하게. 둘레빛: 위(밤하늘)가 조금 밝은 남색. 가로등이 주인공
                when (weather) {
                    "rain" -> { put(0, 0.35f, 0.66f, 0.75f, 1f); put(4, 0.27f, 0.64f, 0.73f, 1f); put(8, 0.04f, 0.62f, 0.72f, 1f); t[23] = 0.42f }
                    "snow" -> { put(0, 0.55f, 0.74f, 0.82f, 1f); put(4, 0.3f, 0.72f, 0.8f, 1f); put(8, 0.05f, 0.7f, 0.78f, 1f) }
                    else -> { put(0, 0.45f, 0.66f, 0.75f, 1f); put(4, 0.26f, 0.62f, 0.72f, 1f); put(8, 0.05f, 0.6f, 0.7f, 1f) }
                }
                bg = if (wet) Color.parseColor("#2A3346") else Color.parseColor("#1E2433")
                t[22] = 1f
                put(24, 0.8f); hex(25, if (wet) "#3A4762" else "#2F3A58")
                hex(28, "#3A465E")
            }
            weather == "snow" -> {
                // 눈: 밝고 서늘하게 흩어진 빛(해는 낮추고 하늘 둘레빛을 올림 → 부드러운 명암)
                put(0, 1.25f, 0.95f, 0.97f, 1f); put(4, 0.42f, 0.94f, 0.96f, 1f); put(8, 0.08f, 0.94f, 0.97f, 1f)
                bg = Color.parseColor("#E6ECF5")   // 63번 4장
                put(24, 0.6f); hex(25, "#F3F6FA")
            }
            weather == "rain" -> {
                // 비(흐림): 해는 약하고 서늘하게, 하늘 둘레빛이 위에서 고르게. 가로등은 켜지되 낮이라 은은하게(0.35)
                put(0, 0.55f, 0.88f, 0.92f, 1f); put(4, 0.4f, 0.9f, 0.94f, 1f); put(8, 0.1f, 0.9f, 0.94f, 1f)
                bg = Color.parseColor("#DCE3EB")   // 63번 4장: 64% 글자 대비 약 5.0:1
                t[22] = 0.35f; t[23] = 0.42f
                put(24, 0.6f); hex(25, "#EDF1F5")
                hex(28, "#E4EAF1")
            }
            // 맑은 날(11/10 턱 그늘): 예전 채움빛(방향광 0.9)은 Filament 가 방향광을 하나만 써서 한 번도 안 켜졌고, 위에서 오는 해(2.3)만 세서
            // 숙인 얼굴의 아래쪽(눈 밑·입가·턱)이 이마보다 36% 어두운 탁한 갈색이 됐다(주름·안경테와 겹쳐 '입 주변이 지저분'). 해를 낮추고 앞 채움빛(31)을
            // 둘레빛에 넣어 얼굴 아래쪽을 밝힌다. 받침판 밝기는 그대로(236 → 235), 이마 219 → 236, 입가 141 → 176(에뮬레이터 실측)
            phase == 2 -> { put(0, 1.35f, 1f, 0.88f, 0.76f); put(4, 0.19f, 1f, 0.96f, 0.93f); t[31] = 0.5f }   // 노을: 받침판과 사람에만 연주황 빛
            phase == 0 -> { put(0, 1.35f, 1f, 0.97f, 0.92f); put(4, 0.21f, 0.95f, 0.98f, 1f); t[31] = 0.5f }   // 아침: 맑고 서늘한 빛
            else -> { put(0, 1.4f, 1f, 0.98f, 0.95f); put(4, 0.2f, 1f, 1f, 1f); t[31] = 0.5f }   // 바탕은 화면 흰색이 비치게(투명)
        }
        if (t[24] == 0f) { t[25] = envCur[25]; t[26] = envCur[26]; t[27] = envCur[27] }   // 흐린 빛이 사라질 땐 색은 그대로 옅어지기만
        if (weather != "rain") { t[28] = envCur[28]; t[29] = envCur[29]; t[30] = envCur[30] }
        // 밤 받침판은 서늘한 회색(가장 밝은 덩어리가 받침판이 되지 않게, 64번 14), 가로등 빛 웅덩이 자리만 따뜻하게 밝아진다. 비엔 젖어서 조금 어둡게
        hex(12, if (night) (if (weather == "snow") "#BFC3CA" else "#8F939B") else if (weather == "rain") "#DADCDC" else "#F4F4F2")
        t[15] = if (weather == "snow") 0.07f else if (wet) 0.06f else 0f; t[16] = if (weather == "rain") 0.7f else 0f; t[17] = if (weather == "snow") 1f else 0f
        t[18] = Color.alpha(bg) / 255f; t[19] = Color.red(bg) / 255f; t[20] = Color.green(bg) / 255f; t[21] = Color.blue(bg) / 255f
        if (bg == Color.TRANSPARENT) { t[19] = envCur[19]; t[20] = envCur[20]; t[21] = envCur[21] }   // 투명으로 갈 땐 색은 그대로 두고 옅어지기만
        fxTinted = -1f   // 빗줄기 색이 밤낮을 따라가게
        if (!envInit || driving || !active || !on(FX_FADE)) {
            // 처음·주행 중·안 보일 때: 바로 그 값으로(주행 중엔 한 장으로만 바꾼다)
            envInit = true; t.copyInto(envCur); envAt = 0L; applyEnv(true)
            fxMode = weather; fxLevel = if (wet) 1f else 0f
        } else {
            if (envCur[18] == 0f) { envCur[19] = t[19]; envCur[20] = t[20]; envCur[21] = t[21] }   // 투명에서 시작하면 색은 목표 색으로
            if (envCur[24] == 0f) { envCur[25] = t[25]; envCur[26] = t[26]; envCur[27] = t[27] }
            if (envCur[16] == 0f) { envCur[28] = t[28]; envCur[29] = t[29]; envCur[30] = t[30] }
            envFrom = envCur.copyOf(); envTo = t; envAt = SystemClock.uptimeMillis()
        }
        applyClear()
    }

    /** 비·눈 덩어리: 보이기·진하기, 정차 중엔 아래로 흘린다(같은 덩어리 둘을 위아래로 이어 FX_H 마다 돌림). */
    private fun stepFx(now: Long, live: Boolean) {
        val a = stage ?: return
        val rainOn = fxMode == "rain" && fxLevel > 0.01f && on(FX_RAIN); val snowOn = fxMode == "snow" && fxLevel > 0.01f && on(FX_RAIN)
        val r1 = props["rain_a"]?.first ?: 0; val r2 = props["rain_b"]?.first ?: 0
        val s1 = props["snowfx_a"]?.first ?: 0; val s2 = props["snowfx_b"]?.first ?: 0
        showE(r1, rainOn); showE(r2, rainOn); showE(s1, snowOn); showE(s2, snowOn)
        if (fxLevel != fxTinted) {
            fxTinted = fxLevel
            // 빗줄기: 낮엔 하늘보다 조금 짙은 회청색, 밤엔 바탕보다 밝은 옅은 줄(어둠 속에서 빛을 받은 빗방울처럼). 회색 막이 되지 않게 옅게
            if (night) tint(mi(a, "rain_a"), Color.parseColor("#A7B4C8"), 0.38f * fxLevel) else tint(mi(a, "rain_a"), Color.parseColor("#8797AB"), 0.5f * fxLevel)
            tint(mi(a, "snowfx_a"), Color.WHITE, 0.9f * fxLevel)
        }
        if (!live || (!rainOn && !snowOn)) return
        val t = now / 1000f
        val tm = engine.transformManager
        if (rainOn) { val off = (t * 7f) % FX_H; set(tm, r1, M.t(0f, -off, 0f)); set(tm, r2, M.t(0f, FX_H - off, 0f)) }
        if (snowOn) {
            val off = (t * 0.55f) % FX_H; val sx = 0.15f * sin(t * 0.6f)
            set(tm, s1, M.t(sx, -off, 0f)); set(tm, s2, M.t(-sx, FX_H - off, 0f))
        }
    }

    /** 전환 한 걸음(정차 중 매 장). 4초에 걸쳐 빛·바탕·돔·눈이 바뀌고, 빗줄기·눈송이는 옛것이 1.5초에 옅어진 뒤 새것이 3초에 짙어진다. */
    private fun stepEnv(now: Long, dt: Float) {
        if (envAt != 0L) {
            val k = ease(clamp((now - envAt) / ENV_MS.toFloat()))
            for (i in envCur.indices) envCur[i] = lerp(envFrom[i], envTo[i], k)
            applyEnv(k >= 1f)
            if (k >= 1f) envAt = 0L
        }
        if (fxMode != weather) { fxLevel = max(0f, fxLevel - dt / 1500f); if (fxLevel <= 0f) fxMode = weather }
        else if (weather == "rain" || weather == "snow") fxLevel = min(1f, fxLevel + dt / 3000f)
    }

    /** 화면 바탕(맑은 낮은 흰 화면, 밤 모드는 #17171C). 화면이 알려 준다. */
    var pageColor: Int = Color.WHITE
        set(v) { if (field != v) { field = v; applyClear(); kick() } }
    /** 3D 면을 지우는 색 = 화면 바탕 위에 지금 바탕색(반투명이면 섞어서)을 얹은 색. 화면이 칠하는 바탕과 같아야 칸 경계가 안 보인다. */
    private fun applyClear() {
        val b = backdrop; val a = Color.alpha(b) / 255f
        fun ch(p: Int, q: Int): Float {
            val v = (p * (1f - a) + q * a) / 255f
            if (BuildConfig.DEBUG && v > 0.99f) Hub.weatherTest?.takeIf { it.startsWith("w") }?.drop(1)?.toFloatOrNull()?.let { return it }   // 시험: 흰색 지우는 값 바꿔 보기
            if (v > 0.99f) return 1.2f   // 순백: 1.0 을 넣으면 색 보정을 거쳐 249·247·248 로 나온다. 1.15 이상이면 255(11/08 실측)
            return if (v <= 0.04045f) v / 12.92f else Math.pow(((v + 0.055f) / 1.055f).toDouble(), 2.4).toFloat()
        }
        val p = pageColor
        renderer.clearOptions = Renderer.ClearOptions().apply {
            clear = true
            clearColor = floatArrayOf(ch(Color.red(p), Color.red(b)), ch(Color.green(p), Color.green(b)), ch(Color.blue(p), Color.blue(b)), 1f)
        }
    }

    private fun applyEnv(final: Boolean) {
        val e = envCur
        val lm = engine.lightManager
        val sunI = lm.getInstance(sun)
        lm.setIntensity(sunI, e[0]); lm.setColor(sunI, e[1], e[2], e[3])
        val now = SystemClock.uptimeMillis()
        ambient(final)
        val a = stage
        if (a != null) {
            val plate = mi(a, "plate")
            tint(plate, Color.rgb((e[12] * 255).toInt(), (e[13] * 255).toInt(), (e[14] * 255).toInt()))
            plate?.setParameter("roughnessFactor", e[23])
            mi(a, "talk")?.setParameter("roughnessFactor", 0.9f - (0.9f - e[23]) * 0.6f)
            // 유리 돔: 아주 옅게(회색 막이 되지 않게), 해·달 반사는 작은 흰 점이 아니라 넓고 부드럽게(거칠기 0.35)
            mi(a, "dome")?.let { m -> tint(m, Color.parseColor("#EAF4FF"), e[15]); m.setParameter("roughnessFactor", 0.35f) }; show(a, "dome", e[15] > 0.004f)
            // 물웅덩이: 하늘이 비친 색(빛을 덜 타게 스스로 조금 빛남). 낮엔 젖은 바닥보다 밝은 하늘색, 밤엔 어두운 남색
            mi(a, "puddles")?.let { m ->
                tint(m, Color.rgb((e[28] * 255).toInt(), (e[29] * 255).toInt(), (e[30] * 255).toInt()), e[16])
                runCatching { m.setParameter("emissiveFactor", e[28] * 0.2f, e[29] * 0.2f, e[30] * 0.2f) }
                m.setParameter("roughnessFactor", 0.45f)
            }
            show(a, "puddles", e[16] > 0.004f)
            tint(mi(a, "haze"), Color.rgb((e[25] * 255).toInt(), (e[26] * 255).toInt(), (e[27] * 255).toInt()), e[24]); show(a, "haze", e[24] > 0.004f)
            if (lampK > 0f) applyLamp(false)   // 주변 어두움(22)이 바뀌면 가로등 세기도(둘레빛은 위에서 이미)
            // 눈은 위에서부터 소복이 쌓이듯(높이만 0 → 1)
            val tm = engine.transformManager
            for (n in listOf("snow_tree", "snow_branch", "snow_rim", "snow_lamp", "snow_pot")) {
                show(a, n, e[17] > 0.01f)
                props[n]?.let { (en, m) -> tm.setTransform(tm.getInstance(en), M.mul(m, M.s(1f, max(0.01f, e[17]), 1f))) }
            }
            val birdOk = e[15] < 0.03f   // 비·눈이 반쯤 오면 새는 숨는다(돔 투명도 최대 0.06~0.07)
            if (birdOk != birdShown) { birdShown = birdOk; bird?.renderableEntities?.forEach { showE(it, birdOk) } }
            if (!birdOk) {
                // 숨는 동안은 나무 자리로 돌려 두고, 다시 나오면 날기 시각을 새로 잡는다
                if (birdState != 0) { birdState = 0; placeBird(tm, BIRD_TREE, camYaw(BIRD_TREE[0], BIRD_TREE[2]) - 0.5f); birdClip("idle_breathe", now, true) }
                birdNext = 0L
            }
        }
        val bg = Color.argb((e[18] * 255).toInt(), (e[19] * 255).toInt(), (e[20] * 255).toInt(), (e[21] * 255).toInt())
        if (bg != backdrop) { backdrop = bg; onBackdrop?.invoke(bg); applyClear() }
    }

    // ---------- 자리 계산 ----------
    private fun fwd(s: Int): FloatArray { val y = seats[s]?.get(2) ?: 0f; return floatArrayOf(sin(y), cos(y)) }
    /** 쿠션에 앉는 점. */
    private fun sitSpot(s: Int, hi: Int = people[s]?.hi ?: 1): FloatArray { val seat = seats[s]!!; val f = fwd(s); val d = SEAT_D[hi]; return floatArrayOf(seat[0] + f[0] * d, seat[1] + f[1] * d) }
    /** 쿠션 앞에 서는 점(앉→서 끝·서→앉 시작). 쿠션 앞 끝 밖. */
    private fun frontSpot(s: Int): FloatArray { val seat = seats[s]!!; val f = fwd(s); return floatArrayOf(seat[0] + f[0] * Z_FRONT, seat[1] + f[1] * Z_FRONT) }
    /** 쿠션 앞 길목(산책 길을 고를 때 출발·도착점). */
    private fun standSpot(s: Int): FloatArray { val seat = seats[s]!!; val f = fwd(s); return floatArrayOf(seat[0] + f[0] * 0.85f, seat[1] + f[1] * 0.85f) }
    /** 동작 끝 Hips 이동(키 1 기준, 앞 +Z)을 쿠션 방향으로 돌려 키만큼 늘린 장면 이동. */
    private fun turned(yaw: Float, ex: Float, ez: Float, h: Float) = floatArrayOf((cos(yaw) * ex + sin(yaw) * ez) * h, (-sin(yaw) * ex + cos(yaw) * ez) * h)
    /** 앉→서 동작이 끝난 자리(쿠션 바로 앞). */
    private fun riseSpot(x: Person): FloatArray = frontSpot(x.p.slot)
    /** 서→앉 동작을 시작할 자리(끝나면 엉덩이가 앉는 점에 오도록). */
    private fun sitFrom(x: Person): FloatArray = frontSpot(x.p.slot)
    private fun camYaw(x: Float, z: Float) = atan2(0f - x, TARGET_Z - z)
    private fun dirYaw(ax: Float, az: Float, bx: Float, bz: Float) = atan2(bx - ax, bz - az)
    private fun walkMs(ax: Float, az: Float, bx: Float, bz: Float) = (hypot(bx - ax, bz - az) / WALK_SPEED * 1000f).toLong().coerceAtLeast(300L)
    // ---------- 걷는 길(11/09): 장애물을 5cm 칸에 몸 반지름+여유만큼 부풀려 칠해 두고, 걸을 때마다 A* → 줄 당기기로 몇 토막 길 ----------
    // 칸마다 비트: 쿠션 몸체 0~4, 쿠션 앞(다가가는 자리) 5~9, 나무·가로등·벤치·화분·충전 기둥·눈사람 10~15, 받침판 밖 16.
    // 보이지 않는 쿠션·안 나온 눈사람·충전 기둥은 그때그때 '지나가도 됨'으로(allow). 자기 쿠션 앞자리는 출발·도착 때만 허용.
    private var nav: IntArray? = null
    private var navG = FloatArray(0); private var navCame = IntArray(0); private var navStamp = IntArray(0); private var navClosed = IntArray(0); private var navRun = 0
    var navObsHits = 0; var navPeopleHits = 0; private var navPlans = 0; private var navFails = 0; private var navHitLog = 0

    private fun polyDist(px: Float, pz: Float, p: FloatArray): Float {
        var inside = true; var best = Float.MAX_VALUE; val n = p.size / 2
        var sign = 0
        for (i in 0 until n) {
            val ax = p[2 * i]; val az = p[2 * i + 1]; val bx = p[(2 * i + 2) % p.size]; val bz = p[(2 * i + 3) % p.size]
            val cr = (bx - ax) * (pz - az) - (bz - az) * (px - ax)
            val sg = if (cr > 0) 1 else if (cr < 0) -1 else 0
            if (sg != 0) { if (sign == 0) sign = sg else if (sg != sign) inside = false }
            best = min(best, segDist(px, pz, ax, az, bx, bz))
        }
        return if (inside) 0f else best
    }
    private fun buildNav() {
        val n = NAV_N; val m = IntArray(n * n)
        val statics = listOf(B_TREE to OB_TREE, B_LAMP to OB_LAMP, B_BENCH to OB_BENCH, B_POT to OB_POT, B_CHARGER to OB_CHARGER, B_SNOWMAN to OB_SNOWMAN)
        fun bbox(p: FloatArray): FloatArray { var a = 1e9f; var b = 1e9f; var c = -1e9f; var d = -1e9f; for (i in 0 until p.size / 2) { a = min(a, p[2 * i]); b = min(b, p[2 * i + 1]); c = max(c, p[2 * i]); d = max(d, p[2 * i + 1]) }; return floatArrayOf(a - NAV_INFL, b - NAV_INFL, c + NAV_INFL, d + NAV_INFL) }
        val boxes = statics.map { bbox(it.second) }
        for (j in 0 until n) for (i in 0 until n) {
            val cx = NAV_O + (i + .5f) * NAV_C; val cz = NAV_O + (j + .5f) * NAV_C; var bits = 0
            if (hypot(cx, cz) > NAV_RIM) bits = bits or (1 shl B_RIM)
            for ((k, sp) in statics.withIndex()) { val b = boxes[k]; if (cx < b[0] || cz < b[1] || cx > b[2] || cz > b[3]) continue
                if (polyDist(cx, cz, sp.second) <= NAV_INFL) bits = bits or (1 shl sp.first) }
            for ((s, seat) in seats) {
                val dx = cx - seat[0]; val dz = cz - seat[1]; if (dx * dx + dz * dz > 1.6f * 1.6f) continue
                val y = seat[2]; val lz = dx * sin(y) + dz * cos(y); val lx = dx * cos(y) - dz * sin(y)
                if (polyDist(lx, lz, OB_CUSHION) <= NAV_INFL) bits = bits or (1 shl (if (lz > 0.58f && abs(lx) < 0.5f) B_FRONT0 + s - 1 else s - 1))
            }
            m[j * n + i] = bits
        }
        nav = m; navG = FloatArray(n * n); navCame = IntArray(n * n); navStamp = IntArray(n * n); navClosed = IntArray(n * n)
        if (BuildConfig.DEBUG) Hub.log("광장 길 칸: ${n}×$n, 막힌 칸 ${m.count { it != 0 }}")
    }
    private fun cellOf(x: Float, z: Float): Int {
        val i = ((x - NAV_O) / NAV_C).toInt(); val j = ((z - NAV_O) / NAV_C).toInt()
        return if (i < 0 || j < 0 || i >= NAV_N || j >= NAV_N || x < NAV_O || z < NAV_O) -1 else j * NAV_N + i
    }
    /** 지금 지나가도 되는 장애물 비트: 안 보이는 쿠션(사람도 초대도 없음), 안 나온 눈사람, 안 올라온 충전 기둥. */
    private fun baseAllow(): Int {
        var a = 0
        for (s in 1..5) { val shown = people[s] != null || data?.nextSlot == s; if (!shown) a = a or (1 shl (s - 1)) or (1 shl (B_FRONT0 + s - 1)) }
        if (snowStage < 1) a = a or (1 shl B_SNOWMAN)
        if (chargeK <= 0f) a = a or (1 shl B_CHARGER)
        return a
    }
    private fun frontBit(s: Int) = 1 shl (B_FRONT0 + s - 1)
    /** 다른 사람이 서 있는 곳·서 있을 곳(원 x, z, 반지름). 걷는 중인 사람은 걸으며 비킨다. */
    private fun peopleCircles(me: Person, withWalkers: Boolean): FloatArray {
        val out = ArrayList<Float>()
        for (o in people.values) {
            if (o === me) continue
            val os = o.segs.firstOrNull(); val walking = os?.kind == WALK
            if ((o.cstand > 0.5f && !walking) || (walking && withWalkers)) { out.add(o.cx); out.add(o.cz); out.add(0.5f) }
            for (q in o.segs) if (q.kind == STAND) { out.add(q.ax); out.add(q.az); out.add(0.5f) }
        }
        return out.toFloatArray()
    }
    private fun cellBlocked(c: Int, allow: Int, circ: FloatArray, sx: Float, sz: Float): Boolean {
        val m = nav ?: return false
        if (m[c] and allow.inv() != 0) return true
        if (circ.isEmpty()) return false
        val cx = NAV_O + (c % NAV_N + .5f) * NAV_C; val cz = NAV_O + (c / NAV_N + .5f) * NAV_C
        if (hypot(cx - sx, cz - sz) < 0.2f) return false   // 출발점 둘레는 비켜서 나갈 수 있게
        var i = 0
        while (i < circ.size) { if (hypot(cx - circ[i], cz - circ[i + 1]) < circ[i + 2]) return true; i += 3 }
        return false
    }
    /** 곧은 선이 지나는 칸을 빠짐없이(격자 따라가기, 꼭짓점을 지나면 양옆 칸도) 보며 막힌 칸이 없는지. 출발·도착 칸은 비어 있다고 본다. */
    private fun los(ax: Float, az: Float, bx: Float, bz: Float, allow: Int, circ: FloatArray, sc: Int, gc: Int, sx: Float, sz: Float): Boolean {
        val n = NAV_N
        var i = ((ax - NAV_O) / NAV_C).toInt(); var j = ((az - NAV_O) / NAV_C).toInt()
        val ei = ((bx - NAV_O) / NAV_C).toInt(); val ej = ((bz - NAV_O) / NAV_C).toInt()
        if (i < 0 || j < 0 || i >= n || j >= n || ei < 0 || ej < 0 || ei >= n || ej >= n) return false
        val dx = bx - ax; val dz = bz - az
        val si = if (dx > 0) 1 else -1; val sj = if (dz > 0) 1 else -1
        val tdx = if (abs(dx) < 1e-9f) Float.MAX_VALUE else NAV_C / abs(dx); val tdz = if (abs(dz) < 1e-9f) Float.MAX_VALUE else NAV_C / abs(dz)
        var tmx = if (abs(dx) < 1e-9f) Float.MAX_VALUE else ((NAV_O + (i + (if (dx > 0) 1 else 0)) * NAV_C) - ax) / dx
        var tmz = if (abs(dz) < 1e-9f) Float.MAX_VALUE else ((NAV_O + (j + (if (dz > 0) 1 else 0)) * NAV_C) - az) / dz
        fun bad(ci: Int, cj: Int): Boolean { if (ci < 0 || cj < 0 || ci >= n || cj >= n) return true; val c = cj * n + ci; return c != sc && c != gc && cellBlocked(c, allow, circ, sx, sz) }
        var guard = 0
        while (true) {
            if (bad(i, j)) return false
            if ((i == ei && j == ej) || guard++ > 4 * n) return true
            if (abs(tmx - tmz) < 1e-6f) { if (bad(i + si, j) || bad(i, j + sj)) return false; i += si; j += sj; tmx += tdx; tmz += tdz }   // 꼭짓점: 양옆 칸도
            else if (tmx < tmz) { i += si; tmx += tdx } else { j += sj; tmz += tdz }
        }
    }
    /** A*(8방향, 모서리 자르기 없음) → 줄 당기기. 실패하면 null. */
    private fun planPath(ax: Float, az: Float, bx: Float, bz: Float, allow: Int, circ: FloatArray): FloatArray? {
        val m = nav ?: return floatArrayOf(ax, az, bx, bz)
        val sc = cellOf(ax, az); val gc = cellOf(bx, bz); if (sc < 0 || gc < 0) return null
        if (m[gc] and allow.inv() != 0) return null
        navPlans++
        if (los(ax, az, bx, bz, allow, circ, sc, gc, ax, az)) return floatArrayOf(ax, az, bx, bz)
        navRun++; val run = navRun; val n = NAV_N
        val gi = gc % n; val gj = gc / n
        fun hh(c: Int): Float { val di = abs(c % n - gi); val dj = abs(c / n - gj); return (max(di, dj) + 0.4142f * min(di, dj)) * NAV_C }
        val open = java.util.PriorityQueue<Long>()
        fun push(c: Int, f: Float) { open.add((java.lang.Float.floatToIntBits(f).toLong() shl 32) or c.toLong()) }
        navStamp[sc] = run; navG[sc] = 0f; navCame[sc] = -1; push(sc, hh(sc))
        var found = false; var expanded = 0
        while (open.isNotEmpty()) {
            val c = (open.poll()!! and 0xffffffffL).toInt()
            if (navClosed[c] == run) continue
            navClosed[c] = run; expanded++
            if (c == gc) { found = true; break }
            if (expanded > 12000) break
            val ci = c % n; val cj = c / n
            for (dj in -1..1) for (di in -1..1) {
                if (di == 0 && dj == 0) continue
                val ni = ci + di; val nj = cj + dj; if (ni < 0 || nj < 0 || ni >= n || nj >= n) continue
                val nc = nj * n + ni
                if (navClosed[nc] == run) continue
                if (nc != gc && cellBlocked(nc, allow, circ, ax, az)) continue
                if (di != 0 && dj != 0 && (cellBlocked(cj * n + ni, allow, circ, ax, az) || cellBlocked(nj * n + ci, allow, circ, ax, az))) continue
                val ng = navG[c] + if (di != 0 && dj != 0) 1.4142f * NAV_C else NAV_C
                if (navStamp[nc] != run || ng < navG[nc]) { navStamp[nc] = run; navG[nc] = ng; navCame[nc] = c; push(nc, ng + hh(nc)) }
            }
        }
        if (!found) { navFails++; return null }
        val cells = ArrayList<Int>(); var c = gc
        while (c != -1) { cells.add(c); c = navCame[c] }
        cells.reverse()
        val pts = ArrayList<Float>(); pts.add(ax); pts.add(az)
        fun cx(k: Int) = if (k == cells.size - 1) bx else NAV_O + (cells[k] % n + .5f) * NAV_C
        fun cz(k: Int) = if (k == cells.size - 1) bz else NAV_O + (cells[k] / n + .5f) * NAV_C
        // 줄 당기기: 지금 점에서 곧게 보이는 가장 먼 칸까지 한 토막
        var curX = ax; var curZ = az; var k = 0
        while (k < cells.size - 1) {
            var far = -1
            for (q in cells.size - 1 downTo k + 1) if (los(curX, curZ, cx(q), cz(q), allow, circ, sc, gc, ax, az)) { far = q; break }
            if (far < 0) {
                // 곧게 보이는 칸이 없으면(출발점이 칸 가운데가 아님) 먼저 지금 칸 가운데로 가서 칸을 따라간다(모서리를 스치지 않게)
                val mx = NAV_O + (cells[k] % n + .5f) * NAV_C; val mz = NAV_O + (cells[k] / n + .5f) * NAV_C
                if (hypot(mx - curX, mz - curZ) > 1e-4f) { curX = mx; curZ = mz; pts.add(curX); pts.add(curZ); continue }
                far = k + 1
            }
            curX = cx(far); curZ = cz(far); pts.add(curX); pts.add(curZ); k = far
        }
        return pts.toFloatArray()
    }
    /** 걷는 구간 하나(장애물·사람을 피한 길). 길을 못 찾으면 곧은 길로 만들되 planned=false(고르는 쪽이 그만둘 수 있게). */
    private fun makeWalk(x: Person, ax: Float, az: Float, bx: Float, bz: Float, yaw0: Float, speedUp: Float = 1f, withWalkers: Boolean = false): Seg {
        val allow = baseAllow() or frontBit(x.p.slot)
        val circ = peopleCircles(x, withWalkers)
        val got = planPath(ax, az, bx, bz, allow, circ) ?: planPath(ax, az, bx, bz, allow, FloatArray(0))
        val pts = got ?: floatArrayOf(ax, az, bx, bz)
        val cum = FloatArray(pts.size / 2); for (i in 1 until cum.size) cum[i] = cum[i - 1] + hypot(pts[2 * i] - pts[2 * i - 2], pts[2 * i + 1] - pts[2 * i - 1])
        val len = max(0.01f, cum.last())
        val ms = (len / WALK_SPEED * 1000f / speedUp).toLong().coerceAtLeast(300L)
        val endYaw = if (pts.size >= 4) dirYaw(pts[pts.size - 4], pts[pts.size - 3], pts[pts.size - 2], pts[pts.size - 1]) else yaw0
        return Seg(WALK, ms, ax, az, bx, bz, yaw0, endYaw, path = pts, cum = cum, allow = allow, planned = got != null)
    }
    /** 길 위 거리 d의 점과 그 토막 방향 → out(x, z, yaw). */
    private fun pathAt(s: Seg, d: Float, out: FloatArray) {
        val p = s.path!!; val c = s.cum!!
        var i = 0; while (i < c.size - 2 && c[i + 1] < d) i++
        val l = c[i + 1] - c[i]; val t = if (l > 1e-5f) ((d - c[i]) / l).coerceIn(0f, 1f) else 1f
        out[0] = lerp(p[2 * i], p[2 * i + 2], t); out[1] = lerp(p[2 * i + 1], p[2 * i + 3], t); out[2] = dirYaw(p[2 * i], p[2 * i + 1], p[2 * i + 2], p[2 * i + 3])
    }
    private val pathOut = FloatArray(3)
    /** 걷는 사람 앞을 다른 사람이 막는지. 둘 다 걸으면 번호 작은 사람이 먼저 가고, 서 있거나 기다리는 사람은 피해 간다(막히면 기다렸다 다시 길 찾기). */
    private fun blockedAhead(x: Person, px: Float, pz: Float, hd: Float): Boolean {
        val hx = sin(hd); val hz = cos(hd)
        for (o in people.values) {
            if (o === x) continue
            val os = o.segs.firstOrNull(); val oWalk = os?.kind == WALK
            if (!oWalk && o.cstand < 0.5f) continue   // 앉은 사람은 쿠션 칸이 막는다
            val dx = o.cx - px; val dz = o.cz - pz; val d = hypot(dx, dz)
            if (d > 0.7f) continue
            if ((dx * hx + dz * hz) / max(d, 1e-3f) < 0.15f) continue   // 옆·뒤 사람은 상관없음
            if (oWalk && !o.waiting) { if (o.p.slot < x.p.slot || d < 0.45f) return true }
            else if (d < 0.6f) return true
        }
        return false
    }

    /** 멈춰 설 자리: 말 거는 자리 둘레(원판 + 반 칸)는 메시지 주인공만, 장애물 칸(부풀린 것)·다른 사람 서 있을 자리 밖. */
    private fun okSpot(x: Float, z: Float, me: Int): Boolean {
        if (hypot(x - talk[0], z - talk[2]) < 1.6f) return false
        val c = cellOf(x, z); if (c < 0) return false
        nav?.let { if (it[c] and baseAllow().inv() != 0) return false } ?: run { if (hypot(x, z) > NAV_RIM) return false }
        for (o in people.values) if (o.p.slot != me) {
            if (o.cstand > 0.5f && hypot(x - o.cx, z - o.cz) < 0.8f) return false
            for (q in o.segs) if (q.kind == STAND && hypot(x - q.ax, z - q.az) < 0.8f) return false
        }
        return true
    }

    /** 한 번 재생하는 앉은 몸짓은 그 동작 길이만큼(끝나면 앉아 쉬기로 0.35초에 넘어감). */
    private fun clipMs(name: String, fallback: Long) = clipIx[name]?.let { (clipLen[it]!! * 1000f).toLong() } ?: fallback
    private fun seatGest(x: Person, g: Int, ms: Long, gx: Float = 0f, gz: Float = 0f): Seg {
        val sp = sitSpot(x.p.slot); val y = seats[x.p.slot]!![2]
        return Seg(SEAT, ms, sp[0], sp[1], sp[0], sp[1], y, y, g, gx, gz)
    }
    /** 지금 자세에서 (tx, tz)까지: 앉아 있으면 쿠션 앞으로 일어선 뒤 걷는다. 걸린 시간을 돌려준다. */
    private fun walkTo(x: Person, tx: Float, tz: Float, out: MutableList<Seg>, speedUp: Float = 1f): Long {
        var ax = x.cx; var az = x.cz; var yaw = x.cyaw; var total = 0L
        if (x.cstand < 0.5f) {
            // 앉→서 동작(제자리에서 일어나 쿠션 앞 13cm에 선다). 빨리 감기는 하지 않는다(동작이 1.2초뿐)
            val sp = sitSpot(x.p.slot); val st = riseSpot(x); val y0 = seats[x.p.slot]!![2]
            out.add(Seg(RISE, riseMs, sp[0], sp[1], st[0], st[1], y0, y0)); total += riseMs
            ax = st[0]; az = st[1]; yaw = y0
        }
        var ok = true
        if (hypot(tx - ax, tz - az) > 0.05f) {
            val w = makeWalk(x, ax, az, tx, tz, yaw, speedUp)
            out.add(w); total += w.ms; ok = w.planned
        }
        return if (ok) total else -1L   // -1: 장애물을 피하는 길을 못 찾음(곧은 길로 넣어 두긴 함)
    }
    /** 쿠션으로 돌아가 앉는다(지금 자리에서). */
    private fun goHome(x: Person, now: Long) {
        val out = ArrayList<Seg>()
        if (x.cstand >= 0.5f) sitDown(x, x.cx, x.cz, x.cyaw, out)
        else if (x.cstand > 0.02f) { val sp = sitSpot(x.p.slot); out.add(Seg(SIT, 300L, x.cx, x.cz, sp[0], sp[1], x.cyaw, seats[x.p.slot]!![2])) }
        x.segs.clear(); x.segs.addAll(out); x.segAt = now
    }
    /** (fx, fz)에 서 있는 사람이 쿠션으로: 앉기 전 자리까지 걷고, 돌아서며 서→앉 동작(1초). */
    private fun sitDown(x: Person, fx: Float, fz: Float, fyaw: Float, out: MutableList<Seg>): Boolean {
        val sf = sitFrom(x); val sp = sitSpot(x.p.slot); val y0 = seats[x.p.slot]!![2]
        var yy = fyaw; var ok = true
        if (hypot(sf[0] - fx, sf[1] - fz) > 0.05f) { val w = makeWalk(x, fx, fz, sf[0], sf[1], fyaw); out.add(w); yy = w.yawB; ok = w.planned }
        out.add(Seg(SIT, sitMs, sf[0], sf[1], sp[0], sp[1], yy, y0))
        return ok
    }
    /** 메시지 주인공: 지금 있는 자리에서 말 거는 자리로(최대 2.5초) 걸어 나와 카메라 쪽을 보고 선다. */
    private fun goTalk(x: Person, now: Long) {
        val out = ArrayList<Seg>()
        var t = walkTo(x, talk[0], talk[2], out)
        if (t < 0) t = out.sumOf { it.ms }
        if (t > HERO_MAX_MS) { out.clear(); walkTo(x, talk[0], talk[2], out, t.toFloat() / HERO_MAX_MS) }
        val yy = out.lastOrNull()?.yawB ?: x.cyaw
        out.add(Seg(STAND, FOREVER, talk[0], talk[2], talk[0], talk[2], yy, 0f))
        x.segs.clear(); x.segs.addAll(out); x.segAt = now
    }
    /** 주행 중 결과 자세: 말 거는 자리에 서 있다. */
    private fun heroStatic(x: Person) {
        x.segs.clear(); x.segs.add(Seg(STAND, FOREVER, talk[0], talk[2], talk[0], talk[2], 0f, 0f)); x.segAt = 0L
    }

    // ---------- 돌아가며 하는 행동(64번 4·5·6, 11/08 밤: 동물의숲 주민처럼 느긋하게) ----------
    // 동시에 3명까지 쿠션을 떠나 산책한다. 산책은 멈춰 서서 책 읽기·둘러보기·흥얼거리기를 하며 두 군데 들렀다 온다.
    // 길은 다른 사람이 갈 길·서 있을 자리와 0.75 이상 떨어지게 고르고, 카메라를 등지고 걷는 구간이 짧은 길을 고른다.
    private fun offCount() = people.values.count { it.away() || it.p.slot == heroSlot }

    private fun nextActor(): Person? {
        repeat(2) {
            if (order.isEmpty()) { order.addAll(people.keys.sorted()); order.shuffle(rnd) }
            while (order.isNotEmpty()) {
                val x = people[order.removeAt(0)] ?: continue
                if (!x.busy() && x.p.slot != heroSlot) return x
            }
        }
        return null
    }

    /** 시험 명령(adb ... --es cmd plaza --es value doze 등)으로 고른 다음 행동. 0이면 주머니대로. */
    private var forceAct = 0
    /** 시험용 끄기: norot(고개·기댐 얹기 끔), noanim(뼈 동작 끔), 그 밖은 정상. */
    private var dbg = ""
    /** 시험: 예전처럼 매 vsync 깨어나기(dbg:vsyncall, dbg:vsynchalf 로 되돌림). */
    private var dbgVsyncAll = false
    /** 시험: 모든 사람 키를 이 값(0 작음·1 보통·2 큼)으로(dbg:h0·h1·h2, dbg:hoff 해제). -1이면 아바타대로. */
    private var dbgHeight = -1
    /** 시험(CPU 재기): 0 보통, 1 아무도 안 걷기(dbg:nowalk), 2 걸을 수 있으면 늘 산책(dbg:allwalk). dbg:walk 로 보통. */
    private var dbgWalk = 0
    private fun drawAction(x: Person, walkOk: Boolean): Int {
        if (forceAct != 0) { val f = forceAct; forceAct = 0; return f }
        if (x.bag.isEmpty()) {
            // 산책이 가장 잦게(3칸), 나머지는 한 칸씩
            x.bag.addAll(listOf(A_STROLL, A_STROLL, A_STROLL, A_VISIT, A_FACE2, A_READ, A_LOOKAT, A_STRETCH, A_WAVE, A_LOOKUP, A_TURN, A_DOZE, A_DRINK, A_YAWN))
            if (weather == "rain" || weather == "snow") x.bag.add(A_LOOKUP)   // 비·눈 오면 돔을 올려다보기 한 번 더
            x.bag.shuffle(x.rnd)
        }
        val i = x.bag.indices.firstOrNull { val a = x.bag[it]; a != x.last && (walkOk || a !in WALKERS) } ?: return 0
        return x.bag.removeAt(i).also { x.last = it }
    }

    private fun neighbors(s: Int): List<Person> {
        val ks = people.keys.sorted(); val i = ks.indexOf(s)
        return listOfNotNull(ks.getOrNull(i - 1), ks.getOrNull(i + 1)).mapNotNull { people[it] }.filter { !it.busy() && it.p.slot != heroSlot }
    }

    /** 점 p와 선분 ab 사이 거리. */
    private fun segDist(px: Float, pz: Float, ax: Float, az: Float, bx: Float, bz: Float): Float {
        val dx = bx - ax; val dz = bz - az; val l2 = dx * dx + dz * dz
        val t = if (l2 < 1e-6f) 0f else (((px - ax) * dx + (pz - az) * dz) / l2).coerceIn(0f, 1f)
        return hypot(px - (ax + dx * t), pz - (az + dz * t))
    }
    private fun segSeg(a: FloatArray, b: FloatArray, c: FloatArray, d: FloatArray): Float =
        minOf(minOf(segDist(a[0], a[1], c[0], c[1], d[0], d[1]), segDist(b[0], b[1], c[0], c[1], d[0], d[1])),
              minOf(segDist(c[0], c[1], a[0], a[1], b[0], b[1]), segDist(d[0], d[1], a[0], a[1], b[0], b[1])))
    /** 다른 사람이 지금 있거나 앞으로 갈 길(남은 구간들). */
    private fun othersPaths(me: Person): List<Pair<FloatArray, FloatArray>> {
        val out = ArrayList<Pair<FloatArray, FloatArray>>()
        for (o in people.values) {
            if (o === me) continue
            val c = floatArrayOf(o.cx, o.cz); out.add(c to c)
            for (s in o.segs) if (s.kind != SEAT) {
                val pth = s.path
                if (pth != null) for (i in 0 until pth.size / 2 - 1) out.add(floatArrayOf(pth[2 * i], pth[2 * i + 1]) to floatArrayOf(pth[2 * i + 2], pth[2 * i + 3]))
                else out.add(floatArrayOf(s.ax, s.az) to floatArrayOf(s.bx, s.bz))
            }
        }
        return out
    }
    /** 이 길(점들을 차례로 잇는)이 다른 사람 길과 0.75 넘게 떨어져 있는지. */
    private fun routeClear(me: Person, pts: List<FloatArray>, extra: List<Pair<FloatArray, FloatArray>> = emptyList()): Boolean {
        val others = othersPaths(me) + extra
        for (i in 0 until pts.size - 1) for ((c, d) in others) if (segSeg(pts[i], pts[i + 1], c, d) < 0.75f) return false
        return true
    }
    /** 카메라를 등지고 걷는 거리(등이 보이는 구간). */
    private fun backLen(pts: List<FloatArray>): Float {
        var b = 0f
        for (i in 0 until pts.size - 1) {
            val a = pts[i]; val c = pts[i + 1]; val len = hypot(c[0] - a[0], c[1] - a[1]); if (len < 0.05f) continue
            if (cos(angDiff(dirYaw(a[0], a[1], c[0], c[1]), camYaw(a[0], a[1]))) < -0.25f) b += len
        }
        return b
    }
    /** 산책 중 멈춰서 하는 일: 책 읽기·둘러보기·흥얼거리기·기지개·올려다보기. 얼굴은 카메라 쪽(±35°). */
    private fun stopGest(x: Person) = listOf(G_READ, G_READ, G_LOOKAROUND, G_HUM, G_STRETCH, G_LOOKUP)[x.rnd.nextInt(6)]

    private fun routine(now: Long) {
        Hub.plazaTest?.let { t ->
            Hub.plazaTest = null
            if (t == "greet") { greet(); return }
            if (t.startsWith("dbg:")) {
                dbg = t.drop(4); Hub.log("[테스트] 광장 디버그 → $dbg")
                if (dbg.startsWith("off:") || dbg.startsWith("on:")) { setFx(dbg.substringAfter(':'), dbg.startsWith("on:")); Hub.log("광장 꺼 둔 효과: $off"); return }
                if (dbg.startsWith("h")) {
                    dbgHeight = dbg.drop(1).toIntOrNull() ?: -1
                    val ps = people.values.map { it.p }; people.keys.toList().forEach { remove(it) }; ps.forEach { add(it) }   // 키를 바꿔 다시 만듦
                    return
                }
                // 시험(재기만, 11/09 CPU 최적화 비교용)
                when (dbg) {
                    "vsyncall" -> dbgVsyncAll = true      // 예전처럼 매 vsync 깨어나기 / 되돌리기
                    "vsynchalf" -> dbgVsyncAll = false
                    "fps60" -> { frameIntervalNs = FRAME_60; nextFrameNs = 0L }   // 비교용
                    "fps30" -> { frameIntervalNs = FRAME_30; nextFrameNs = 0L }
                    "nowalk" -> dbgWalk = 1
                    "allwalk" -> dbgWalk = 2
                    "walk" -> dbgWalk = 0
                    "low" -> lowSpec = true          // 저사양 모드 켜기·끄기(설정과 같은 것, 재기용)
                    "normal" -> lowSpec = false
                    // 예전처럼 숨긴 덩어리도 모두 피부에 붙이기 / 보이는 것만
                    "skinall" -> for (x in people.values) for ((e, si) in x.skinIx) x.inst.attachSkin(si, e)
                    "skinvis" -> for (x in people.values) for ((e, si) in x.skinIx) if (e in hidden) x.inst.detachSkin(si, e)
                }
                for (x in people.values) {
                    when (dbg) {
                        "facehide" -> x.faceAsset?.let { fa -> fa.entities.forEach { showE(it, false) } }
                    }
                }
                return
            }
            forceAct = mapOf("wave" to A_WAVE, "turn" to A_TURN, "lookup" to A_LOOKUP, "stretch" to A_STRETCH, "read" to A_READ, "lookat" to A_LOOKAT,
                "stroll" to A_STROLL, "visit" to A_VISIT, "face2" to A_FACE2, "doze" to A_DOZE, "drink" to A_DRINK, "yawn" to A_YAWN)[t] ?: 0
            Hub.log("[테스트] 광장 다음 행동 → $t${if (forceAct == 0 && t != "greet") " (모르는 이름)" else ""}")
            nextAct = 0L
        }
        if (now < nextAct) return
        nextAct = now + 2500L + rnd.nextLong(1500L)
        if (heroSlot != 0 || people.isEmpty()) return   // 메시지 주인공이 나와 있으면 다른 사람은 큰 동작을 쉰다
        val x = nextActor() ?: return
        val walkOk = !hold && now - wakeAt >= 5000L && offCount() < MAX_AWAY && dbgWalk != 1
        val act = if (dbgWalk == 2 && walkOk) A_STROLL else drawAction(x, walkOk)
        val s = x.p.slot
        val sp = sitSpot(s); val st = standSpot(s); val y0 = seats[s]!![2]
        fun stay() = 4500L + x.rnd.nextLong(3500L)
        fun seated(g: Int, ms: Long, gx: Float = 0f, gz: Float = 0f) { x.segAt = now; x.segs.add(seatGest(x, g, ms, gx, gz)) }
        when (act) {
            A_WAVE -> seated(G_WAVE, clipMs(C_SIT_WAVE, 2100L))
            A_TURN -> seated(G_TURN, 3600L)
            A_LOOKUP -> if (weather == "snow" && x.rnd.nextBoolean()) seated(G_CATCH, 4200L) else seated(G_LOOKUP, 3800L)   // 눈 오면 손 내밀어 눈 받기
            A_STRETCH -> seated(G_STRETCH, clipMs(C_SIT_STRETCH, 2970L))
            A_YAWN -> seated(G_YAWN, clipMs(C_SIT_YAWN, 2970L))
            A_DRINK -> seated(G_DRINK, clipMs(C_DRINK, 11170L))          // 컵을 들고 한 번 마시기(11초)
            A_DOZE -> seated(G_DOZE, 9000L + x.rnd.nextLong(5000L))       // 꾸벅꾸벅(17초 동작의 앞부분부터)
            A_READ -> seated(G_READ, 7000L + x.rnd.nextLong(3000L))   // 앉아서 책 읽기
            A_LOOKAT -> { val o = neighbors(s).firstOrNull(); if (o != null) seated(G_LOOKAT, 4000L, o.cx, o.cz) else seated(G_HUM, 4000L) }
            A_STROLL -> {
                // 두 군데 들렀다 오는 산책. 후보를 여럿 뽑아 '안 겹치고 등이 덜 보이는' 길을 고른다
                var best: List<FloatArray>? = null; var bestScore = Float.MAX_VALUE
                repeat(28) {
                    val a1 = x.rnd.nextFloat() * 2f * PI.toFloat(); val r1 = 0.9f + x.rnd.nextFloat() * 1.2f
                    val p1 = floatArrayOf(st[0] + sin(a1) * r1, st[1] + cos(a1) * r1)
                    val a2 = x.rnd.nextFloat() * 2f * PI.toFloat(); val r2 = 0.8f + x.rnd.nextFloat() * 1.1f
                    val p2 = floatArrayOf(p1[0] + sin(a2) * r2, p1[1] + cos(a2) * r2)
                    if (!okSpot(p1[0], p1[1], s) || !okSpot(p2[0], p2[1], s)) return@repeat
                    if (hypot(p2[0] - st[0], p2[1] - st[1]) > 2.2f) return@repeat
                    val pts = listOf(st, p1, p2, st)
                    if (!routeClear(x, pts)) return@repeat
                    val score = backLen(pts) * 3f + x.rnd.nextFloat() * 0.3f
                    if (score < bestScore) { bestScore = score; best = pts }
                }
                val r = best
                if (r == null || bestScore > 2.4f) { seated(G_READ, 7000L); return }
                val out = ArrayList<Seg>()
                if (walkTo(x, r[1][0], r[1][1], out) < 0) { seated(G_READ, 7000L); return }
                var yaw = out.last().yawB
                for (i in 1..2) {
                    val p = r[i]
                    val face = camYaw(p[0], p[1]) + (x.rnd.nextFloat() - .5f) * 1.2f
                    out.add(Seg(STAND, stay(), p[0], p[1], p[0], p[1], yaw, face, stopGest(x)))
                    val n = r[i + 1]
                    val wy = dirYaw(p[0], p[1], n[0], n[1])
                    if (i < 2) { val w = makeWalk(x, p[0], p[1], n[0], n[1], face); if (!w.planned) { seated(G_READ, 7000L); return }; out.add(w); yaw = w.yawB }
                    else if (!sitDown(x, p[0], p[1], face, out)) { seated(G_READ, 7000L); return }   // 마지막 들른 곳에서 바로 쿠션으로
                }
                x.segAt = now; x.segs.addAll(out)
            }
            A_VISIT, A_FACE2 -> {
                val o = neighbors(s).firstOrNull()
                if (o == null) { seated(G_HUM, 4000L); return }
                val os = o.p.slot; val ost = standSpot(os)
                if (act == A_FACE2 && offCount() + 2 <= MAX_AWAY) {
                    // 둘이 나와서 이야기하기: 가운데로 반걸음씩, 서로 보되 얼굴이 보이게 카메라 쪽으로 반쯤
                    val mx = (st[0] + ost[0]) / 2f; val mz = (st[1] + ost[1]) / 2f + 0.35f
                    val k = 0.45f / max(0.01f, hypot(st[0] - mx, st[1] - mz)); val ko = 0.45f / max(0.01f, hypot(ost[0] - mx, ost[1] - mz))
                    val dv = avgFwd(s, os)
                    val a = freeNear(floatArrayOf(mx + (st[0] - mx) * k, mz + (st[1] - mz) * k), dv, s) ?: run { seated(G_LOOKAT, 4000L, o.cx, o.cz); return }
                    val b = freeNear(floatArrayOf(mx + (ost[0] - mx) * ko, mz + (ost[1] - mz) * ko), dv, os) ?: run { seated(G_LOOKAT, 4000L, o.cx, o.cz); return }
                    val ra = listOf(st, a, st); val rb = listOf(ost, b, ost)
                    if (!okSpot(a[0], a[1], s) || !okSpot(b[0], b[1], os) || !routeClear(x, ra) || !routeClear(o, rb)) { seated(G_LOOKAT, 4000L, o.cx, o.cz); return }
                    val holdMs = 6000L + x.rnd.nextLong(3000L)
                    val plans = ArrayList<Pair<Person, ArrayList<Seg>>>()
                    for ((p, me, other, home, seatP) in listOf(Quint(x, a, b, st, sp), Quint(o, b, a, ost, sitSpot(os)))) {
                        val out = ArrayList<Seg>()
                        if (walkTo(p, me[0], me[1], out) < 0) { seated(G_LOOKAT, 4000L, o.cx, o.cz); return }
                        val wy = out.last().yawB
                        val face = angLerp(dirYaw(me[0], me[1], other[0], other[1]), camYaw(me[0], me[1]), 0.45f)
                        out.add(Seg(STAND, holdMs, me[0], me[1], me[0], me[1], wy, face, G_TALK))
                        if (!sitDown(p, me[0], me[1], face, out)) { seated(G_LOOKAT, 4000L, o.cx, o.cz); return }
                        plans.add(p to out)
                    }
                    for ((p, out) in plans) { p.segs.clear(); p.segs.addAll(out); p.segAt = now }   // 둘 다 길이 있을 때만 나선다
                    return
                }
                // 옆 사람에게 가서 이야기: 두 쿠션 사이 앞에 서고, 그 사람은 앉은 채 이쪽을 보며 끄덕인다
                val mx = (st[0] + ost[0]) / 2f; val mz = (st[1] + ost[1]) / 2f
                val t = freeNear(floatArrayOf(mx + (ost[0] - mx) * 0.3f, mz + (ost[1] - mz) * 0.3f + 0.25f), avgFwd(s, os), s) ?: run { seated(G_LOOKAT, 4000L, o.cx, o.cz); return }
                if (!okSpot(t[0], t[1], s) || !routeClear(x, listOf(st, t, st))) { seated(G_LOOKAT, 4000L, o.cx, o.cz); return }
                val out = ArrayList<Seg>()
                val go = walkTo(x, t[0], t[1], out)
                if (go < 0) { seated(G_LOOKAT, 4000L, o.cx, o.cz); return }
                val wy = out.last().yawB
                val stayMs = 5500L + x.rnd.nextLong(2500L)
                val face = angLerp(dirYaw(t[0], t[1], seats[os]!![0], seats[os]!![1]), camYaw(t[0], t[1]), 0.55f)
                out.add(Seg(STAND, stayMs, t[0], t[1], t[0], t[1], wy, face, G_TALK))
                if (!sitDown(x, t[0], t[1], face, out)) { seated(G_LOOKAT, 4000L, o.cx, o.cz); return }
                x.segAt = now; x.segs.addAll(out)
                o.segs.clear(); o.segAt = now
                o.segs.add(seatGest(o, 0, go)); o.segs.add(seatGest(o, G_LOOKAT, stayMs, t[0], t[1]))
            }
            else -> seated(G_HUM, 4000L)
        }
    }
    /** 두 쿠션 앞 방향의 평균(이야기 자리를 쿠션·앉은 다리 밖으로 밀 때). */
    private fun avgFwd(a: Int, b: Int): FloatArray { val fa = fwd(a); val fb = fwd(b); val l = max(1e-3f, hypot(fa[0] + fb[0], fa[1] + fb[1])); return floatArrayOf((fa[0] + fb[0]) / l, (fa[1] + fb[1]) / l) }
    /** p에서 dir 쪽으로 10cm씩(최대 70cm) 밀며 처음 비어 있는 설 자리. */
    private fun freeNear(p: FloatArray, dir: FloatArray, me: Int): FloatArray? {
        for (k in 0..7) { val q = floatArrayOf(p[0] + dir[0] * 0.1f * k, p[1] + dir[1] * 0.1f * k); if (okSpot(q[0], q[1], me)) return q }
        return null
    }
    private data class Quint(val p: Person, val me: FloatArray, val other: FloatArray, val home: FloatArray, val seat: FloatArray)

    // ---------- 자세 ----------
    private fun update(now: Long) {
        val live = !driving
        if (live) {
            routine(now)
            // 가로등 3초에 걸쳐 켜짐·꺼짐
            val dt = if (lastLiveAt == 0L) 0L else min(200L, now - lastLiveAt)
            // 가로등은 날씨·밤 전환이 60% 지난 뒤(바탕이 어두워진 다음) 켜지기 시작한다(회의 11/08)
            val envK = if (envAt == 0L) 1f else clamp((now - envAt) / ENV_MS.toFloat())
            val target = if (lampOn && envK >= 0.6f) 1f else if (lampOn) lampK else 0f
            if (lampK != target) { lampK = if (target > lampK) min(1f, lampK + dt.toFloat() / LAMP_MS) else max(0f, lampK - dt.toFloat() / LAMP_MS); applyLamp() }
            lastLiveAt = now
            frameDt = dt.toFloat()
            stepEnv(now, dt.toFloat())
            if (BuildConfig.DEBUG && Hub.weatherTest != lastTest) { lastTest = Hub.weatherTest; applyClear() }
            stepFx(now, true)
        } else { lastLiveAt = 0L; stepFx(now, false) }   // 주행 중: 바뀐 날씨를 멈춘 한 장으로
        stepCharLoad()
        val tm = engine.transformManager
        tm.openLocalTransformTransaction()
        for (x in people.values) pose(x, now, live)
        if (BuildConfig.DEBUG && live) {   // 서 있거나 걷는 두 사람의 뿌리가 0.4m 안이면 센다(목표 0)
            val ps = people.values.filter { it.cstand > 0.5f }
            for (i in ps.indices) for (j in i + 1 until ps.size) if (hypot(ps[i].cx - ps[j].cx, ps[i].cz - ps[j].cz) < 0.4f) navPeopleHits++
        }
        if (live) {
            // 나뭇잎 ±1.2° 6.5초(풍량을 올리면 0.5~3°까지), 풀·꽃 ±4° 3~4초(모두에게 같은 규칙)
            val leafAmp = Hub.fan?.let { 0.009f + (it.coerceIn(0, 8) / 8f) * 0.043f } ?: 0.021f
            if (on(FX_SWAY)) for ((e, m) in sway) {
                val tree = e == crownE
                val ph = (e % 7) * 0.9f
                val a = if (tree) leafAmp * sin(now / 6500f * 2f * PI.toFloat()) else 0.07f * sin(now / (3200f + (e % 3) * 350f) * 2f * PI.toFloat() + ph)
                set(tm, e, M.mul(m, M.mul(M.rz(a), M.rx(a * 0.5f))))
            }
            life(tm, now)
        }
        tm.commitLocalTransformTransaction()
        for (x in people.values) animate(x)   // 사람 뼈: 뿌리 변환을 확정한 뒤 동작(+교차 전환) → 고개·기댐 얹기 → 뼈 행렬
        if (live) stepBird(now)   // 새 뼈: 변환을 확정한 뒤 동작 → 뼈 행렬
    }

    /** 소품과 차 신호(정차 중 매 장): 새·낙엽·충전 기둥·눈사람·문 열림 인사·등받이 기댐·시간대 확인. */
    private fun life(tm: com.google.android.filament.TransformManager, now: Long) {
        val dt = frameDt
        val wet = weather == "rain" || weather == "snow"
        // 운전석 문이 열리면(5초 안의 일만) 모두 살짝 일어나 1.5초 손 인사. 메시지 주인공이 나와 있으면 건너뛴다
        val door = Hub.doorOpenAt
        if (door != doorSeen) {
            doorSeen = door
            if (heroSlot == 0 && SystemClock.elapsedRealtime() - door < 5000L)
                for (x in people.values) if (!x.away()) { x.segs.clear(); x.segAt = now; x.segs.add(seatGest(x, G_HELLO, clipMs(C_SIT_WAVE, 2100L))) }
        }
        // 등받이를 젖히고(시작 값보다 15 넘게) 벨트를 풀면 모두 쿠션에 기댄다
        val rec = if (Hub.beltOn == false && (Hub.backrest ?: 0) >= RECLINE_AT) 1f else 0f
        reclineK = if (rec > reclineK) min(rec, reclineK + dt / 900f) else max(rec, reclineK - dt / 900f)
        // 시간대(30초마다): 바뀌면 빛을 다시
        if (now - phaseCheck > 30_000L) { phaseCheck = now; if (dayPhase() != phase) applyWeather() }
        if (Hub.ambientColor != lastAmb) { lastAmb = Hub.ambientColor; applyLamp() }
        // 새(뼈 동작): 나무 가지 끝에서 숨쉬고, 9~17초마다 고개 돌리기·쪼기·콩콩 중 하나.
        // 60~90초마다(시험 모드 15~25초) 가로등까지 날아갔다 온다: 이륙 0.6초 → 날갯짓하며 1.6초 → 착지 0.6초. 비·눈엔 숨는다
        if (bird != null && birdShown) {
            fun gap() = if (Hub.shortTimes) 15_000L + rnd.nextLong(10_000L) else 60_000L + rnd.nextLong(30_000L)
            if (birdNext == 0L) birdNext = now + gap()
            if (birdIdleNext == 0L) birdIdleNext = now + 9000L + rnd.nextLong(8000L)
            when (birdState) {
                0 -> if (now >= birdNext && !wet && on(FX_FLY)) { birdState = 1; birdAt = now }
                2 -> if (now >= birdNext) { birdState = 3; birdAt = now }   // 가로등에 앉아 있으면 저사양이어도 나무로 돌아온다
            }
            var pos = if (birdState >= 2) BIRD_LAMP else BIRD_TREE
            var yaw = camYaw(pos[0], pos[2]) + if (birdState >= 2) 0.5f else -0.5f
            if (birdState == 1 || birdState == 3) {
                val from = if (birdState == 1) BIRD_TREE else BIRD_LAMP; val to = if (birdState == 1) BIRD_LAMP else BIRD_TREE
                val fromYaw = camYaw(from[0], from[2]) + if (birdState == 1) -0.5f else 0.5f
                val toYaw = camYaw(to[0], to[2]) + if (birdState == 1) 0.5f else -0.5f
                val flyYaw = dirYaw(from[0], from[2], to[0], to[2])
                val el = now - birdAt
                when {
                    el < TAKEOFF_MS -> { pos = from; yaw = angLerp(fromYaw, flyYaw, ease(el / TAKEOFF_MS.toFloat())); birdClip("takeoff", now, false) }
                    el < TAKEOFF_MS + FLY_MS -> {
                        val k = (el - TAKEOFF_MS).toFloat() / FLY_MS; val e = ease(k)
                        pos = floatArrayOf(lerp(from[0], to[0], e), lerp(from[1], to[1], e) + 0.9f * sin(k * PI.toFloat()), lerp(from[2], to[2], e))
                        yaw = flyYaw; birdClip("flap", now, true)
                    }
                    el < TAKEOFF_MS + FLY_MS + LAND_MS -> { pos = to; yaw = angLerp(flyYaw, toYaw, ease((el - TAKEOFF_MS - FLY_MS) / LAND_MS.toFloat())); birdClip("land", now, false) }
                    else -> {
                        birdState = if (birdState == 1) 2 else 0; birdAt = now
                        birdNext = now + if (birdState == 2) 8000L + rnd.nextLong(6000L) else gap()
                        pos = to; yaw = toYaw; birdClip("idle_breathe", now, true); birdIdleNext = now + 9000L + rnd.nextLong(8000L)
                    }
                }
            } else {
                // 앉아 있을 때: 한 번짜리 동작이 끝나면 다시 숨쉬기, 때가 되면 한 동작
                if (!birdLoop && birdDone(now)) birdClip("idle_breathe", now, true)
                if (birdLoop && now >= birdIdleNext && on(FX_BIRDIDLE)) {
                    birdClip(listOf("head_turn", "head_turn", "peck", "hop")[rnd.nextInt(4)], now, false)
                    birdIdleNext = now + 9000L + rnd.nextLong(8000L)
                }
            }
            placeBird(tm, pos, yaw)
        }
        // 낙엽: 20~40초마다 1장이 4초에 걸쳐 흔들리며 떨어지고 3초 뒤 사라진다
        if (on(FX_LEAF)) props["leaf_fall"]?.let { (e, _) ->
            if (leafNext == 0L) leafNext = now + 20_000L + rnd.nextLong(20_000L)
            if (leafAt == 0L && now >= leafNext) { leafAt = now; leafX = 0.3f + (rnd.nextFloat() - 0.5f) * 1.8f; leafZ = -2.75f + rnd.nextFloat() * 0.5f }
            if (leafAt != 0L) {
                val k = (now - leafAt) / 4000f
                if (k >= 1.75f) { leafAt = 0L; leafNext = now + 20_000L + rnd.nextLong(20_000L); showE(e, false) }
                else {
                    showE(e, true)
                    val f = clamp(k)
                    set(tm, e, M.mul(M.t(leafX + 0.25f * sin(f * 3f * PI.toFloat()), lerp(2.0f, 0.03f, f), leafZ + 0.3f * f), M.mul(M.ry(f * 4f), M.rz(0.8f * sin(f * 5f * PI.toFloat()) * (1f - f)))))
                }
            }
        }
        // 충전구를 열면 충전 기둥이 1.2초에 걸쳐 올라오고, 배터리 5칸 고리가 잔량만큼 찬다(숫자 없음)
        props["charger"]?.let { (e, m) ->
            val target = if (Hub.chargePort) 1f else 0f
            if (chargeK != target) {
                chargeK = if (target > chargeK) min(1f, chargeK + dt / 1200f) else max(0f, chargeK - dt / 1200f)
                set(tm, e, M.mul(M.t(0f, -0.8f * (1f - ease(chargeK)), 0f), m))
                val on = chargeK > 0f; showE(e, on); chargeSegs.forEach { showE(it, on) }
            }
            val soc = Hub.soc ?: -1
            if (soc != lastSoc) {
                lastSoc = soc
                val filled = if (soc < 0) 0 else (soc + 19) / 20
                stage?.let { a -> for (k in 1..5) tint(mi(a, "charge_seg$k"), Color.parseColor(if (k <= filled) "#9CC48A" else "#E4DED4")) }
            }
        }
        // 눈사람: 눈 오는 날 정차 5·10·15분마다 자란다(시험 모드 5초 단위). 눈이 그치면 없어진다
        val st = if (weather == "snow") {
            if (snowSince == 0L) snowSince = now
            min(3L, (now - snowSince) / if (Hub.shortTimes) 5000L else 300_000L).toInt()
        } else { snowSince = 0L; 0 }
        if (st != snowStage) {
            snowStage = st
            val a = stage
            if (a != null) { show(a, "snowman1", st >= 1); show(a, "snowman2", st >= 2) }   // 눈·코는 머리 텍스처에
            props["snowman1"]?.let { (e, m) -> set(tm, e, M.mul(m, M.s(if (st == 1) .6f else 1f, if (st == 1) .6f else 1f, if (st == 1) .6f else 1f))) }
            props["snowman2"]?.let { (e, m) -> set(tm, e, M.mul(m, M.s(if (st == 2) .6f else 1f, if (st == 2) .6f else 1f, if (st == 2) .6f else 1f))) }
        }
    }

    /** 새 위치·방향(뿌리 엔티티, 1.5배). 동작 채널은 뼈에만 있어 부딪히지 않는다. */
    private fun placeBird(tm: com.google.android.filament.TransformManager, p: FloatArray, yaw: Float) {
        val b = bird ?: return
        set(tm, b.root, M.mul(M.mul(M.t(p[0], p[1], p[2]), M.ry(yaw)), M.s(BIRD_SCALE, BIRD_SCALE, BIRD_SCALE)))
    }
    /** 새 동작 바꾸기(같은 동작이면 그대로 이어서). */
    private fun birdClip(name: String, now: Long, loop: Boolean) {
        val i = birdClips[name] ?: return
        if (i == birdPlay && loop == birdLoop) return
        birdPlay = i; birdPlayAt = now; birdLoop = loop
    }
    private fun birdDone(now: Long): Boolean {
        val an = birdAnim ?: return true
        return birdPlay < 0 || (now - birdPlayAt) / 1000f >= an.getAnimationDuration(birdPlay)
    }
    /** 지금 동작의 한 장을 뼈에 얹고 뼈 행렬을 갱신한다(숨었으면 건너뜀). */
    private fun stepBird(now: Long) {
        val an = birdAnim ?: return
        if (birdPlay < 0 || !birdShown || !on(FX_BIRD)) return
        val dur = an.getAnimationDuration(birdPlay)
        val t = (now - birdPlayAt) / 1000f
        an.applyAnimation(birdPlay, if (birdLoop && dur > 0f) t % dur else min(t, dur))
        an.updateBoneMatrices()
    }

    /** 시간대: 0 아침(6~9시), 1 낮, 2 노을(16시 30분~18시 30분), 시험 명령 morning/dusk 가 있으면 그것. 밤은 야간 모드가 정한다. */
    private fun dayPhase(): Int = when (Hub.weatherTest) {
        "morning" -> 0
        "dusk" -> 2
        else -> {
            val c = java.util.Calendar.getInstance(); val m = c.get(java.util.Calendar.HOUR_OF_DAY) * 60 + c.get(java.util.Calendar.MINUTE)
            when (m) { in 360 until 540 -> 0; in 990 until 1110 -> 2; else -> 1 }
        }
    }

    // ---------- 이모티콘 날아가기(64번 28) ----------
    private var flying = 0
    /** 운전자가 이모티콘을 누른 직후: 이모티콘이 1초 동안 그 사람에게 날아가고, 그 사람이 손을 흔든다. */
    fun flyEmoji(slot: Int, emoji: String) {
        val x = people[slot] ?: return
        if (driving || vw < 10) return
        val to = toScreen(x.cx, 1.75f + x.cstand * 0.2f, x.cz) ?: return
        val tv = android.widget.TextView(context).apply { text = emoji; textSize = 34f; includeFontPadding = false }
        addView(tv, LayoutParams(-2, -2))
        tv.measure(0, 0)
        val w = tv.measuredWidth; val h = tv.measuredHeight
        val sx = vw * 0.92f; val sy = vh * 0.62f
        flying++; post()
        android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 1000L
            interpolator = android.view.animation.DecelerateInterpolator(1.4f)
            addUpdateListener { va ->
                val k = va.animatedValue as Float
                // 위로 둥글게 넘어가는 길
                tv.translationX = lerp(sx, to[0], k) - w / 2f
                tv.translationY = lerp(sy, to[1], k) - h / 2f - sin(k * PI.toFloat()) * vh * 0.18f
                val sc = 0.8f + 0.5f * sin(k * PI.toFloat() * 0.5f)
                tv.scaleX = sc; tv.scaleY = sc
            }
            addListener(object : android.animation.AnimatorListenerAdapter() {
                override fun onAnimationEnd(a: android.animation.Animator) {
                    if (!x.busy() && x.p.slot != heroSlot && !driving) { x.segAt = SystemClock.uptimeMillis(); x.segs.add(seatGest(x, G_WAVE, clipMs(C_SIT_WAVE, 2100L))); post() }
                    tv.animate().alpha(0f).scaleX(1.6f).scaleY(1.6f).setDuration(300L).withEndAction { removeView(tv); flying = max(0, flying - 1) }.start()
                }
            })
            start()
        }
    }

    private fun clamp(v: Float) = v.coerceIn(0f, 1f)
    private fun ease(t: Float) = t * t * (3 - 2 * t)
    private fun lerp(a: Float, b: Float, t: Float) = a + (b - a) * t
    private fun angLerp(a: Float, b: Float, t: Float): Float { var d = b - a; while (d > PI) d -= (2 * PI).toFloat(); while (d < -PI) d += (2 * PI).toFloat(); return a + d * t }
    private fun angDiff(a: Float, b: Float): Float { var d = b - a; while (d > PI) d -= (2 * PI).toFloat(); while (d < -PI) d += (2 * PI).toFloat(); return d }

    /**
     * 사람 한 명의 이번 장(변환 거래 안): 구간 → 뿌리 위치·방향·높이, 고를 동작과 재생 시각, 뼈에 얹을 고개·기댐 값.
     * 뼈 자체는 animate 에서(뿌리 변환을 확정한 뒤 applyAnimation → applyCrossFade → updateBoneMatrices).
     * 동작↔구간: 앉아 쉬기 Chair_Sit_Idle_F, 일어서기 Sit_to_Stand, 걷기 Walking(걷는 빠르기에 맞춘 재생 속도), 서 있기 Short_Breathe,
     * 앉기 Stand_to_Sit(돌아서며), 몸짓은 Sit_Wave·Sit_Stretch·Sit_Yawn·Sit_and_Drink(컵)·Sit_and_Doze_Off·Sit_Cross_Legged·Stand_and_Chat 등.
     */
    private fun pose(x: Person, now: Long, live: Boolean) {
        val seat = seats[x.p.slot] ?: return
        val h = x.h
        // 끝난 구간은 넘긴다(시간이 이어지게)
        while (x.segs.isNotEmpty()) {
            val s = x.segs.first()
            if (s.ms == FOREVER || now - x.segAt < s.ms) break
            x.segs.removeFirst(); x.segAt += s.ms
            if (x.segAt > now) x.segAt = now
        }
        val sp = sitSpot(x.p.slot)
        val s0 = x.segs.firstOrNull()
        if (s0 !== x.segRef) { x.segRef = s0; x.segYaw0 = x.cyaw; x.walkYaw = x.cyaw; x.waitMs = 0f; x.waiting = false; x.holdAcc = 0f; x.replans = 0 }
        var px = sp[0]; var pz = sp[1]; var yaw = seat[2]; var stand = 0f
        var gest = 0; var gk = 0f; var gx = 0f; var gz = 0f; var gEl = 0L; var gMs = 1L
        var want = C_SIT; var mode = LOOP; var from = 0f; var to = -1f; var rate = 1f; var key: Any? = null
        var tp = -1f; var rising = false; var endX = 0f; var endZ = 0f   // 앉→서·서→앉 진행(0~1)과 그 동작이 Hips를 옮기는 양
        val s = x.segs.firstOrNull()
        if (s != null) {
            val el = if (x.segAt == 0L) Long.MAX_VALUE / 4 else now - x.segAt
            gEl = el; gMs = s.ms
            val k = if (s.ms == FOREVER) 0f else clamp(el.toFloat() / s.ms)
            when (s.kind) {
                SEAT -> { gest = s.gest; gk = k; gx = s.gx; gz = s.gz }
                RISE -> { px = lerp(s.ax, s.bx, k); pz = lerp(s.az, s.bz, k); yaw = s.yawB; stand = k; want = C_RISE; mode = ONCE; key = s; tp = k; rising = true; endX = RISE_END_X; endZ = RISE_END_Z }
                WALK -> {
                    stand = 1f
                    val len = s.cum?.last() ?: hypot(s.bx - s.ax, s.bz - s.az)
                    if (s.path != null) { pathAt(s, k * len, pathOut); px = pathOut[0]; pz = pathOut[1] } else { px = lerp(s.ax, s.bx, k); pz = lerp(s.az, s.bz, k); pathOut[2] = dirYaw(s.ax, s.az, s.bx, s.bz) }
                    val hd = pathOut[2]
                    // 몸은 길 방향으로 부드럽게 돈다(초당 4.5라디안). 남은 각이 크면 제자리에서 돌고 나서 걷는다
                    val err = angDiff(x.walkYaw, hd)
                    if (live) x.walkYaw += err.coerceIn(-TURN_RATE * frameDt / 1000f, TURN_RATE * frameDt / 1000f)
                    yaw = x.walkYaw
                    var hold = live && abs(err) > 0.9f
                    // 사람 비키기: 앞을 막으면 기다리고(서 있기 동작), 1.2초 넘게 막히면 사람을 피해 길을 다시 찾는다
                    val blocked = live && !hold && blockedAhead(x, px, pz, hd)
                    x.waiting = blocked
                    if (blocked) {
                        hold = true; x.waitMs += frameDt
                        if (x.waitMs > 1200f && x.replans < 3) {
                            x.replans++; x.waitMs = 0f
                            val nw = makeWalk(x, px, pz, s.bx, s.bz, x.walkYaw, withWalkers = true)
                            if (nw.planned) { x.segs[0] = nw; x.segRef = nw; x.segAt = now; x.waiting = false }
                        } else if (x.waitMs > 6000f) x.waiting = false   // 오래 막히면(드묾) 그냥 지나감
                    } else x.waitMs = 0f
                    if (hold) { x.holdAcc += frameDt; val add = x.holdAcc.toLong(); x.segAt += add; x.holdAcc -= add }   // 기다리는 동안 구간 시계를 멈춤
                    // 발이 미끄러지지 않게 재생 속도를 이 구간의 걷는 빠르기에 맞춤(주인공이 서둘러 나올 때는 빨리)
                    val v = if (s.ms in 1 until FOREVER) len / (s.ms / 1000f) else WALK_SPEED
                    want = if (x.waiting) C_IDLE else C_WALK; rate = if (x.waiting) 1f else (v / (CLIP_WALK * h)).coerceIn(0.5f, 2.2f)
                    // 시험 빌드 점검: 걷는 사람 뿌리가 부풀린 장애물 칸 안이면 센다(목표 0)
                    if (BuildConfig.DEBUG && live && !hold) { val c = cellOf(px, pz); val m = nav
                        if (m != null && c >= 0 && (m[c] and (s.allow or baseAllow()).inv()) != 0) { navObsHits++; if (navHitLog++ < 8) Hub.log("광장 길 점검: ${x.p.slot}번이 장애물 칸 안(${"%.2f".format(px)}, ${"%.2f".format(pz)}) 비트 ${Integer.toBinaryString(m[c])} 허용 ${Integer.toBinaryString(s.allow)} 구간 (${"%.2f".format(s.ax)},${"%.2f".format(s.az)})→(${"%.2f".format(s.bx)},${"%.2f".format(s.bz)}) 길찾음 ${s.planned} 점 ${s.path?.size?.div(2)} k ${"%.2f".format(k)}") } }
                }
                STAND -> { px = s.ax; pz = s.az; stand = 1f; yaw = angLerp(x.segYaw0, s.yawB, ease(clamp(el / 800f))); gest = s.gest; gk = k; gx = s.gx; gz = s.gz; want = C_IDLE }
                SIT -> { px = lerp(s.ax, s.bx, k); pz = lerp(s.az, s.bz, k); stand = 1f - k; yaw = angLerp(x.segYaw0, s.yawB, ease(clamp(k / 0.45f))); want = C_SITDOWN; mode = ONCE; key = s; tp = k; endX = SIT_END_X; endZ = SIT_END_Z }
            }
        }
        // 몸짓 → 동작(앉은 몸짓은 앉은 동작, 선 몸짓은 선 동작). 고개·몸 돌리기는 뼈에 얹는 값
        val isSeat = s == null || s.kind == SEAT
        var turn = 0f; var hYaw = 0f; var hPitch = 0f; var yawOff = 0f; var prop: String? = null
        val env = if (gest != 0) (if (gMs == FOREVER) 1f else min(1f, min(gEl / 800f, (gMs - gEl) / 800f))).coerceIn(0f, 1f) else 0f
        when (gest) {
            G_WAVE, G_HELLO -> { want = if (isSeat) C_SIT_WAVE else C_WAVE1; mode = ONCE; key = s }
            G_STRETCH -> { want = if (isSeat) C_SIT_STRETCH else C_STRETCH; mode = ONCE; key = s }
            G_YAWN -> { want = C_SIT_YAWN; mode = ONCE; key = s }
            G_DRINK -> { want = C_DRINK; mode = ONCE; key = s; prop = "prop_cup" }
            G_DOZE -> want = C_DOZE
            G_READ -> if (isSeat) { want = C_DRINK; mode = PING; from = 0f; to = READ_TO; prop = "prop_book"; hPitch = 0.25f * env } else want = C_LOOK
            G_HUM -> want = C_IDLE.takeIf { !isSeat } ?: C_SIT   // 앉아 흥얼거리기: 앉아 쉬기 + 고개 살랑(책상다리 동작은 빈백 위에 못 얹어 뺌)
            G_LOOKAROUND -> want = C_LOOK
            G_TALK -> { want = C_CHAT; yawOff = -CHAT_YAW0 }   // 이 동작은 40° 돌아서 시작 → 뿌리를 되돌려 상대 쪽을 보게
            G_TURN -> turn = 0.35f * sin(gk * PI.toFloat() * 2f)
            G_LOOKUP, G_CATCH -> hPitch = -0.38f * env
            G_LOOKAT -> { val d = angDiff(yaw, atan2(gx - px, gz - pz)).coerceIn(-1.1f, 1.1f); turn = 0.45f * d * env; hYaw = 0.5f * d * env }
        }
        // 주행 중: 모두 같은 한 장(앉은 사람은 앉아 쉬기 첫 장, 주인공은 서 있기 첫 장)
        if (!live) { if (isSeat) { want = C_SIT; prop = null }; mode = ONCE; key = null; from = 0f; to = -1f; turn = 0f; hYaw = 0f; hPitch = 0f }
        val ci = clipIx[want] ?: clipIx[C_SIT] ?: return
        if (to < 0f) to = clipLen[ci] ?: 1f
        if (ci != x.clip || key !== x.clipKey || mode != x.clipMode || from != x.clipFrom) {
            if (x.clip >= 0 && live) {
                // 지금 동작을 그 시각에 멈춰 '이전 동작'으로 두고 0.35초 동안 새 동작과 섞는다(뿌리 높이·방향·Hips 되돌림도 같이 섞음)
                x.prev = x.clip; x.prevT = clipTime(x, now); x.fadeAt = now
                x.prvY = x.curY; x.prvYaw = x.curYaw; x.prvCx = x.curCx; x.prvCz = x.curCz; x.prvLeg = x.curLeg
            } else x.prev = -1
            x.clip = ci; x.clipAt = now; x.clipFrom = from; x.clipTo = to; x.clipMode = mode; x.clipKey = key
            if (want == C_SIT && mode == LOOP) x.clipAt = now - x.p.slot * 1700L   // 앉아 쉬기는 사람마다 시작점을 달리
        }
        x.clipRate = rate
        // 뿌리 높이: 앉은 동작은 빈백 실측 표(키별), 선 동작은 바닥(말 거는 돌판 위면 돌판 높이), 앉→서·서→앉은 진행별 표(쿠션 위로 털썩·내려섬)
        val ground = talk[1] * clamp((0.95f - hypot(px - talk[0], pz - talk[2])) / 0.2f)
        val hi = x.hi
        val seatedClip = want == C_SIT || want == C_SIT_WAVE || want == C_SIT_YAWN || want == C_SIT_STRETCH || want == C_DRINK || want == C_DOZE
        val cy = when {
            tp >= 0f -> table(if (rising) RISE_Y[hi] else SIT_Y[hi], tp)
            want == C_DRINK -> Y_DRINK[hi]
            want == C_DOZE -> Y_DOZE[hi]
            seatedClip -> Y_CHAIR[hi]
            else -> ground
        }
        // 빈백 다리(앞으로 뻗어 쿠션 위에): 앉은 동작 1, 서→앉은 끝 45%에서 들어오고, 앉→서는 처음 45%에서 빠짐
        x.curLeg = when { tp >= 0f && rising -> 1f - ease(clamp(tp / 0.45f)); tp >= 0f -> ease(clamp((tp - 0.55f) / 0.45f)); seatedClip -> 1f; else -> 0f }
        // 고개 숙임 한도(라디안): 앉은 사람은 거의 정면을 보게. 졸기는 0.35였는데 카메라가 위에서 내려다봐서 큰 머리가 그만큼 숙이면
        // 입이 턱 밑으로 넘어가 안 보였다(11/10 사장 '분홍 빈백 사람 입이 없음', 에뮬레이터: 0.35 → 입 없음, 0.2 → 입 보임). 0.2 로
        x.headLimit = when { want == C_DOZE -> 0.2f; seatedClip -> 0.12f; else -> 0.25f }
        x.curY = cy; x.curYaw = yawOff
        val tk = max(0f, tp); x.curCx = endX * tk; x.curCz = endZ * tk   // 앉→서·서→앉: 뿌리를 옮긴 만큼 Hips를 되돌려 몸이 제자리에 있게
        var alpha = 1f
        if (x.prev >= 0) { alpha = clamp((now - x.fadeAt) / FADE_MS); if (alpha >= 1f) x.prev = -1 }
        x.alpha = alpha
        val ry = lerp(x.prvY, cy, alpha); val ryaw = lerp(x.prvYaw, yawOff, alpha)
        x.compX = lerp(x.prvCx, x.curCx, alpha); x.compZ = lerp(x.prvCz, x.curCz, alpha)
        x.legW = if (live) lerp(x.prvLeg, x.curLeg, alpha) else x.curLeg
        x.animT = if (live) clipTime(x, now) else 0f
        // 늘 도는 작은 생활: 고개(6~9초마다 ±8°). 걷거나 일어서는 중엔 동작 그대로
        if (live && now >= x.headNext) {
            x.headFrom = headNow(x, now); x.headTo = (x.rnd.nextFloat() * 2f - 1f) * 0.14f; x.headAt = now
            x.headNext = now + 6000L + x.rnd.nextLong(3000L)
        }
        val calm = live && (isSeat || s?.kind == STAND) && gest != G_DOZE
        x.headYaw = (if (calm) headNow(x, now) else 0f) + hYaw
        x.headPitch = hPitch
        x.lean = if (isSeat && live) -0.3f * reclineK else 0f   // 운전석을 젖히고 벨트를 풀면 앉은 사람 모두 뒤로 기댐(64번 27)
        holdProp(x, prop ?: (if (alpha < 1f) x.propShown else null))   // 컵·책은 그 동작 동안만(섞여 사라지는 동안은 남김)
        val tm = engine.transformManager
        x.rootYaw = yaw + turn + ryaw
        set(tm, x.root, M.mul(M.mul(M.t(px, ry, pz), M.ry(x.rootYaw)), M.s(h, h, h)))
        // 발밑 그림자: 서 있거나 걸을 때만, 쿠션 위로 올라가면(앉기·일어서기) 옅어짐. 앉은 사람은 쿠션 그림자가 대신
        if (on(FX_SHADOW)) x.shadow?.let { sa ->
            val k = (stand * clamp(1f - (ry - ground) / 0.3f) * 10f).roundToInt() / 10f
            if (k != x.shadowK) {
                x.shadowK = k
                sa.entities.forEach { showE(it, k > 0.05f) }
                val rm = engine.renderableManager
                sa.renderableEntities.forEach { e -> rm.getInstance(e).takeIf { it != 0 }?.let { tint(rm.getMaterialInstanceAt(it, 0), Color.BLACK, 0.12f * k) } }
            }
            if (k > 0.05f) set(tm, sa.root, M.mul(M.t(px, ground + 0.012f, pz), M.s(0.85f * h, 1f, 0.85f * h)))
        }
        x.cx = px; x.cz = pz; x.cyaw = yaw; x.cstand = stand
    }

    private fun clipTime(x: Person, now: Long): Float {
        val len = max(1e-3f, x.clipTo - x.clipFrom)
        val el = max(0f, (now - x.clipAt) / 1000f * x.clipRate)
        return when (x.clipMode) {
            ONCE -> x.clipFrom + min(el, len)
            LOOP -> x.clipFrom + el % len
            else -> { val k = el % (2f * len); x.clipFrom + if (k < len) k else 2f * len - k }   // PING: 앞으로 갔다 뒤로(이음매 튐 없음)
        }
    }

    /** 뼈: 지금 동작 한 장 → (전환 중이면) 이전 동작과 섞기 → Hips 되돌림 → 기댐·고개 얹기 → 뼈 행렬. 변환 거래를 확정한 뒤에 부른다. */
    private fun animate(x: Person) {
        if (x.clip < 0 || dbg == "noanim") return
        val an = x.anim
        an.applyAnimation(x.clip, x.animT)
        if (x.prev >= 0 && x.alpha < 1f) an.applyCrossFade(x.prev, x.prevT, x.alpha)   // alpha 0 = 이전 동작, 1 = 지금 동작
        val tm = engine.transformManager
        if (x.hips != 0 && (x.compX != 0f || x.compZ != 0f)) {
            val i = tm.getInstance(x.hips); tm.getTransform(i, tmBuf)
            tmBuf[12] -= x.compX; tmBuf[14] -= x.compZ; tm.setTransform(i, tmBuf)
        }
        if (dbg == "norot") { an.updateBoneMatrices(); return }
        if (x.legW > 0.002f) for (k in 0..1) {   // 빈백 다리: 허벅지 → 정강이 → 발 순서로 몸 기준 방향을 겨눔
            val sx = if (k == 0) 1f else -1f
            aimBone(x, x.upLeg[k], x.lowLeg[k], LEG_THIGH[0] * sx, LEG_THIGH[1], LEG_THIGH[2], x.legW)
            aimBone(x, x.lowLeg[k], x.foot[k], LEG_SHIN[0] * sx, LEG_SHIN[1], LEG_SHIN[2], x.legW)
            aimBone(x, x.foot[k], x.toe[k], LEG_FOOT[0] * sx, LEG_FOOT[1], LEG_FOOT[2], x.legW)
        }
        if (x.lean != 0f) worldRot(x, x.spine, 0f, x.lean)
        if (x.headYaw != 0f || x.headPitch != 0f) worldRot(x, x.head, x.headYaw, x.headPitch)
        // 고개 숙임 한도: 큰 머리가 숙이면 얼굴이 안 보여서(마시기·책·졸기 동작은 무릎을 봄) 그 넘는 만큼 들어 올림
        if (x.head != 0) {
            val tm2 = engine.transformManager; val w = tm2.getWorldTransform(tm2.getInstance(x.head), tmBuf)
            val f = headFwd
            val fx = w[0] * f[0] + w[4] * f[1] + w[8] * f[2]; val fy = w[1] * f[0] + w[5] * f[1] + w[9] * f[2]; val fz = w[2] * f[0] + w[6] * f[1] + w[10] * f[2]
            val down = atan2(-fy, hypot(fx, fz))
            if (down > x.headLimit) worldRot(x, x.head, 0f, -(down - x.headLimit))
        }
        an.updateBoneMatrices()
    }

    /** 표(진행 0, .1 … 1)에서 k의 값(선형). */
    private fun table(t: FloatArray, k: Float): Float { val f = clamp(k) * (t.size - 1); val i = min(t.size - 2, f.toInt()); return lerp(t[i], t[i + 1], f - i) }

    /** 뼈 bone 을 제자리에서 돌려 자식 관절 쪽 방향이 몸 기준 (dx, dy, dz)를 향하게(w 만큼). 앱과 tools 시뮬(legsim)이 같은 방식. */
    private fun aimBone(x: Person, bone: Int, child: Int, dx: Float, dy: Float, dz: Float, w: Float) {
        if (bone == 0 || child == 0) return
        val tm = engine.transformManager
        val bi = tm.getInstance(bone); val ci = tm.getInstance(child); if (bi == 0 || ci == 0) return
        val pi = tm.getInstance(tm.getParent(bi)); if (pi == 0) return
        val W = tm.getWorldTransform(bi, tmBuf); val C = tm.getWorldTransform(ci, tmBuf2)
        var ax = C[12] - W[12]; var ay = C[13] - W[13]; var az = C[14] - W[14]
        var l = sqrt(ax * ax + ay * ay + az * az); if (l < 1e-6f) return; ax /= l; ay /= l; az /= l
        val c = cos(x.rootYaw); val s = sin(x.rootYaw)
        l = sqrt(dx * dx + dy * dy + dz * dz)
        val tx = (c * dx + s * dz) / l; val ty = dy / l; val tz = (-s * dx + c * dz) / l
        var kx = ay * tz - az * ty; var ky = az * tx - ax * tz; var kz = ax * ty - ay * tx
        val sn = sqrt(kx * kx + ky * ky + kz * kz); val cs = ax * tx + ay * ty + az * tz
        if (sn < 1e-5f) return
        kx /= sn; ky /= sn; kz /= sn
        val ang = atan2(sn, cs) * w; val co = cos(ang); val si = sin(ang); val t = 1f - co
        val r = M.id()
        r[0] = t * kx * kx + co; r[1] = t * kx * ky + si * kz; r[2] = t * kx * kz - si * ky
        r[4] = t * kx * ky - si * kz; r[5] = t * ky * ky + co; r[6] = t * ky * kz + si * kx
        r[8] = t * kx * kz + si * ky; r[9] = t * ky * kz - si * kx; r[10] = t * kz * kz + co
        val nw = M.mul(r, W); nw[12] = W[12]; nw[13] = W[13]; nw[14] = W[14]
        android.opengl.Matrix.invertM(tmBuf4, 0, tm.getWorldTransform(pi, tmBuf3), 0)
        tm.setTransform(bi, M.mul(tmBuf4, nw))
    }

    /** 뼈 e를 제자리에서 돌린다(장면 기준): 몸 오른쪽 축으로 pitch(+ = 앞으로 숙임) 다음 위 축으로 yaw. 동작이 다음 장에 회전을 다시 쓰므로 쌓이지 않는다. */
    private fun worldRot(x: Person, e: Int, yawA: Float, pitchA: Float) {
        if (e == 0) return
        val tm = engine.transformManager
        val i = tm.getInstance(e); if (i == 0) return
        val pi = tm.getInstance(tm.getParent(i)); if (pi == 0) return
        val w = tm.getWorldTransform(i, tmBuf); val pw = tm.getWorldTransform(pi, tmBuf2)
        val r = M.mul(M.ry(yawA), M.mul(M.ry(x.rootYaw), M.mul(M.rx(pitchA), M.ry(-x.rootYaw))))
        val nw = M.mul(r, w); nw[12] = w[12]; nw[13] = w[13]; nw[14] = w[14]
        android.opengl.Matrix.invertM(tmBuf3, 0, pw, 0)
        tm.setTransform(i, M.mul(tmBuf3, nw))
    }
    private fun headNow(x: Person, now: Long) = lerp(x.headFrom, x.headTo, ease(clamp((now - x.headAt) / 1800f)))

    private fun set(tm: com.google.android.filament.TransformManager, e: Int, m: FloatArray) {
        if (e == 0) return
        val i = tm.getInstance(e); if (i != 0) tm.setTransform(i, m)
    }

    private fun draw(t: Long): Boolean {
        val s = swap ?: return false
        if (!ui.isReadyToRender) return false
        if (!renderer.beginFrame(s, t)) return false
        renderer.render(view)
        renderer.endFrame()
        return true
    }

    /** 화면을 닫을 때 한 번. 이후에는 아무것도 그리지 않는다. */
    fun destroy() {
        if (destroyed) return
        destroyed = true
        main.removeCallbacksAndMessages(null)
        if (posted) choreo.removeFrameCallback(frame)
        runCatching {
            ui.detach()
            people.keys.toList().forEach { remove(it) }
            if (charLoading) runCatching { res.asyncCancelLoad() }
            charAsset?.let { loader.destroyAsset(it) }; charAsset = null; pool.clear()

            stage?.let { scene.removeEntities(it.entities); loader.destroyAsset(it) }
            bird?.let { scene.removeEntities(it.entities); loader.destroyAsset(it) }; bird = null; birdAnim = null
            res.destroy(); loader.destroy(); provider.destroyMaterials(); provider.destroy()
            bakedVb.values.forEach { l -> l.forEach { engine.destroyVertexBuffer(it) } }; bakedVb.clear()
            bakeChar?.destroy(engine); bakeFace?.destroy(engine)
            ibl?.let { engine.destroyIndirectLight(it) }
            grading?.let { engine.destroyColorGrading(it) }
            listOf(sun).forEach { engine.destroyEntity(it); EntityManager.get().destroy(it) }
            swap?.let { engine.destroySwapChain(it) }
            engine.destroyRenderer(renderer); engine.destroyView(view); engine.destroyScene(scene)
            engine.destroyCameraComponent(camEntity); EntityManager.get().destroy(camEntity)
            engine.destroy()
        }.onFailure { Hub.log("광장 정리 오류: $it") }
    }

    /** 4×4 행렬(열 우선, Filament 방식). */
    /** 4×4 행렬. 매 장 수백 개를 만들므로 새로 할당하지 않고 4096칸 고리에서 돌려 쓴다(setTransform 이 바로 복사하므로 안전, GC 끊김 방지). */
    private object M {
        private val pool = Array(4096) { FloatArray(16) }
        private var at = 0
        private fun next(): FloatArray { val a = pool[at]; at = (at + 1) and 4095; return a }
        fun id() = next().also { java.util.Arrays.fill(it, 0f); it[0] = 1f; it[5] = 1f; it[10] = 1f; it[15] = 1f }
        fun t(x: Float, y: Float, z: Float) = id().also { it[12] = x; it[13] = y; it[14] = z }
        fun s(x: Float, y: Float, z: Float) = id().also { it[0] = x; it[5] = y; it[10] = z }
        fun rx(a: Float) = id().also { val c = cos(a); val s = sin(a); it[5] = c; it[6] = s; it[9] = -s; it[10] = c }
        fun ry(a: Float) = id().also { val c = cos(a); val s = sin(a); it[0] = c; it[2] = -s; it[8] = s; it[10] = c }
        fun rz(a: Float) = id().also { val c = cos(a); val s = sin(a); it[0] = c; it[1] = s; it[4] = -s; it[5] = c }
        fun mul(a: FloatArray, b: FloatArray): FloatArray {
            val o = next()
            for (c in 0 until 4) for (r in 0 until 4) {
                var v = 0f
                for (k in 0 until 4) v += a[k * 4 + r] * b[c * 4 + k]
                o[c * 4 + r] = v
            }
            return o
        }
    }
}
