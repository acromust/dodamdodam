package ai.simeodum.car

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.os.Handler
import android.os.Looper
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/** 광장 자리 한 칸에 앉은 사람(서버 /api/plaza). 누가 메시지를 보냈는지는 이 값에 없다(비밀 규칙). */
data class PlazaPerson(val slot: Int, val code: String, val name: String?, val color: Int, val avatar: IntArray) {
    val label get() = name?.let(::nim) ?: "새 초대 코드"
    override fun equals(other: Any?) = other is PlazaPerson && other.slot == slot && other.code == code && other.name == name && other.color == color && other.avatar.contentEquals(avatar)
    override fun hashCode() = code.hashCode() * 31 + slot
}

/** 광장 전체: 앉은 사람, 오늘 대기 개수, 다음 초대 자리(없으면 null = 5명 다 참), 최대 인원. */
data class PlazaData(val people: List<PlazaPerson>, val pending: Int, val nextSlot: Int?, val max: Int) {
    fun bySlot(s: Int) = people.firstOrNull { it.slot == s }
    fun byCode(c: String?) = c?.let { code -> people.firstOrNull { it.code == code } }
}

/**
 * 광장 자료(받기·저장)와 캐릭터 2D 그림(얼굴 텍스처·재생 패널 얼굴 칸).
 * 부품 번호·색·얼굴 그리기 규칙은 서버 server/avatar.py(= GET /api/presets)와 같다. 서버 값을 받으면 그걸 쓰고, 못 받으면 아래 같은 값.
 * 얼굴 그리기는 폰 웹 server/web/avatar3d.js drawFace 를 그대로 옮겼다(웹 canvas ↔ Android Canvas).
 */
object Plaza {
    /** avatar 칸 순서(서버 KEYS). 정수 배열 인덱스로 쓴다. */
    val KEYS = listOf("hair", "hairColor", "eyes", "brows", "nose", "mouth", "wrinkle", "blush", "beard", "glasses", "face", "skin", "height", "build", "beardColor", "acc", "scarfColor", "glassesColor", "pantsColor", "mark", "beards", "marks")
    const val HAIR = 0; const val HAIR_COLOR = 1; const val EYES = 2; const val BROWS = 3; const val NOSE = 4; const val MOUTH = 5
    const val WRINKLE = 6; const val BLUSH = 7; const val BEARD = 8; const val GLASSES = 9; const val FACE = 10; const val SKIN = 11
    const val HEIGHT = 12; const val BUILD = 13; const val BEARD_COLOR = 14   // 수염색(11/08 추가, 머리색 6가지와 같은 색)
    const val ACC = 15   // 소품(11/09 추가, 맨 뒤): 0 없음, 1 목도리(이어폰은 뺐다). PlazaView.dress 가 16번째 칸(인덱스 15)으로 읽는다
    const val SCARF_COLOR = 16   // 목도리 색(11/09 추가, 맨 뒤): 대표색 8가지와 같은 색. 기본 1 분홍(서버 avatar.SCARF_DEFAULT)
    const val GLASSES_COLOR = 17; const val PANTS_COLOR = 18   // 83번(11/10, 맨 뒤): 안경테 색 4·바지 색 5. 0 = 예전 테·바지 색
    // 수염 5(11/10, 뒤에만): 4 = 짧은 수염(얼굴 그림) + 콧수염(3D beard_mus)
    // 11/10 사장 '수염·점 여러 개': 비트 칸(맨 뒤). 얼굴·3D 는 이 둘만 본다. 예전 BEARD·MARK 한 칸 값은 서버가 맞춰 두고, 없으면 avatarOf 가 옮긴다
    const val BEARDS = 20   // 1 짧은 수염(얼굴 그림)·2 콧수염(beard_mus)·4 턱수염(beard_long, 예전 긴 수염)
    const val MARKS = 21    // 1·2 눈 밑 점 왼·오, 4·8 입가 점 왼·오, 16·32 볼 점 왼·오, 64 주근깨(왼쪽 = 화면에서 보는 쪽)
    private val BEARD_OLD = intArrayOf(0, 1, 2, 4, 3); private val MARK_OLD = intArrayOf(0, 1, 4, 16, 64)   // 서버 avatar.BEARD_OLD·MARK_OLD
    const val MARK = 19   // 점(11/10 83번 5절 (b), 맨 뒤): 0 없음·1 눈 밑 점·2 입가 점·3 볼 점·4 주근깨. FaceSheet 가 face_atlas.json groups.mark[값]을 그린다. 없던 때 = 0
    // 머리 17개(11/09): 옛 0~13 뜻 그대로 + 14 애즈펌·15 2:8 가르마·16 올백(서버 avatar.py 와 같게 뒤에만 붙임)
    // 머리 21개(11/10): 20 짧은 스포츠머리(뒤에만)
    // 머리 20개(11/10 83번): 17 투블럭·18 C컬 중단발·19 웨이브 커트(뒤에만). 10 일자 앞머리는 같은 번호에 다시 만든 가발
    // 주름 16개(11/10): 비트 합 1 눈가 + 2 이마 + 4 입가 + 8 눈 밑(0~3 뜻 그대로). FaceSheet 가 face_atlas.json groups.wrinkle[값]을 그린다
    // 머리색·수염색 8개(11/10): 6 희끗한 검정·7 희끗한 갈색을 뒤에 붙임. 차는 섞인 평균색으로 칠한다(웹 3D만 가닥 무늬)
    // 눈 14·눈썹 9·입 9(11/10 76번, 뒤에만 붙임). 눈 0·3은 웹 고르는 칸에서만 숨기고 서버가 읽을 때 7·1로 옮긴다(여기선 범위 안 값 그대로 그림)
    // 11/10 79번: 눈 17(14 무쌍·15 애교살·16 도도한), 눈썹 10(9 긴 꼬리). 숨긴 눈썹 1·코 1 은 서버가 7·0 으로 옮기고, 아틀라스도 같은 층을 담아 둠
    // 범위 밖 값은 avatarOf 가 DEFAULTS 칸 값으로 둔다
    // 83번: 머리색·수염색 12(8 애쉬 브라운·9 적갈색·10 와인·11 은발), 안경테 색 4, 바지 색 5
    // 83번: 얼굴형·체형 5(3·4 = 형태 중간값, PlazaView FACE_W·BUILD_W). 85번: 얼굴형 7(5 넓은 얼굴·6 넓고 각진)
    // 11/10 84번: 눈 25(17~24 Mii풍 새 눈). 숨긴 눈 2·6·9·10·15 는 서버가 7·21·23·16·1 로 옮기고, 아틀라스도 옮긴 눈 층을 담아 둠
    private val COUNT = intArrayOf(21, 12, 25, 10, 3, 9, 16, 2, 5, 4, 7, 7, 3, 5, 12, 2, 8, 4, 5, 5, 8, 128)

    // 59번 명세 1절 색 값(서버 avatar.py 와 같다). 8번은 회색 #A3A7AE → 남색(빈 쿠션 회색 #B9BCC2와 구분, 11/08 C12. 서버도 같은 값으로 바꿈)
    private val COLORS_HEX = listOf("#5AA9F0", "#F08AAE", "#F5C842", "#7CC36B", "#A98BE8", "#F49A4A", "#5FD0B5", "#3F5BA9")
    private val HAIR_HEX = listOf("#2B2522", "#4A3226", "#8A5A3C", "#A9A6A2", "#EDEBE7", "#E2B85A", "#5E5A58", "#7A6F68",
        "#6E6259", "#7B3A24", "#6A2639", "#C5CCD6")
    // 83번: 안경테(검정·갈색 뿔테·금테·은테), 바지(청바지 파랑·베이지·검정·회색·카키). 서버 GLASSES_COLORS·PANTS_COLORS 와 같다
    private val GLASSES_HEX = listOf("#2B2523", "#6B3F22", "#C9A04A", "#B8BEC6")
    private val PANTS_HEX = listOf("#50637F", "#CDB89A", "#2E3036", "#8A8E95", "#6E6B4A")
    // 피부 7(11/10 81번, 서버 SKINS 와 같다): 0 밝은·1 보통·2 따뜻한·3 구릿빛·4 짙은·5 화사한·6 건강한(5·6은 뒤에 붙임, 0~4는 가까운 새 색)
    private val SKIN_HEX = listOf("#FFE0CC", "#F9C9AA", "#F4C49E", "#B8774F", "#85503A", "#FFD5C0", "#DA9E74")
    // 캐릭터가 없는 예전 사람: 서버 default_avatar 와 같은 순서(young_f, young_m, middle_f, middle_m, child_f). 얼굴형(FACE)은 모두 0 둥근형(11/09)
    // 11/10 서버 프리셋을 새 눈·눈썹·입·주름으로 다시 맞춘 값 그대로(79번: 중년 여성 아치 → 가는 눈썹, 중년 남성 동그란 → 넓은 코)
    private val DEFAULTS = listOf(
        intArrayOf(6, 2, 12, 7, 0, 7, 0, 1, 0, 0, 0, 0, 1, 0, 2, 0, 1, 0, 0, 0, 0, 0), intArrayOf(1, 1, 7, 5, 0, 0, 0, 0, 0, 0, 0, 1, 2, 1, 1, 0, 1, 0, 0, 0, 0, 0),
        intArrayOf(8, 7, 23, 7, 0, 4, 5, 1, 0, 3, 0, 1, 1, 1, 7, 0, 1, 0, 0, 0, 0, 0), intArrayOf(15, 6, 8, 3, 2, 6, 12, 0, 1, 2, 0, 1, 2, 2, 6, 0, 1, 0, 0, 0, 1, 0),
        intArrayOf(7, 1, 1, 0, 0, 3, 0, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0))

    /** 프리셋 캐릭터(서버 default_avatar 순서). 가족 0명 화면의 예시 가족에 쓴다. */
    fun preset(i: Int): IntArray = DEFAULTS[i.coerceAtLeast(0) % DEFAULTS.size].copyOf()

    /** 가족 0명일 때 '예시 메시지 들어 보기'로 잠깐 앉는 예시 가족(서버에 없는 값, 코드는 demo-로 시작). 이름은 예시 메시지(Demo)와 같다. */
    fun demoData(): PlazaData = PlazaData(listOf(
        PlazaPerson(1, "demo-p1", "수진", 1, preset(2)),
        PlazaPerson(2, "demo-p2", "지윤", 0, preset(4)),
        PlazaPerson(3, "demo-p3", "민준", 3, preset(1)),   // [확인 필요] 예시 이름(예시 메시지에는 없는 세 번째 사람)
    ), 0, null, 5)

    fun color(i: Int) = Color.parseColor(COLORS_HEX[i.coerceIn(0, COLORS_HEX.size - 1)])
    /** 목도리 색: 대표색 8가지 중 하나(윗옷 대표색과 따로 고른다). 예전 9칸·16칸 배열이면 기본 분홍 */
    fun scarfColor(a: IntArray) = color(a.getOrElse(SCARF_COLOR) { 1 })
    fun hairColor(a: IntArray) = Color.parseColor(catalogHex("hairColors", a[HAIR_COLOR]) ?: HAIR_HEX[a[HAIR_COLOR].coerceIn(0, HAIR_HEX.size - 1)])
    fun beardColor(a: IntArray) = Color.parseColor(catalogHex("hairColors", a[BEARD_COLOR]) ?: HAIR_HEX[a[BEARD_COLOR].coerceIn(0, HAIR_HEX.size - 1)])
    fun skin(a: IntArray) = Color.parseColor(catalogHex("skins", a[SKIN]) ?: SKIN_HEX[a[SKIN].coerceIn(0, SKIN_HEX.size - 1)])
    /** 83번: 안경테·바지 색. 예전 17칸 배열이면 0(예전 테·바지 색) */
    fun glassesColor(a: IntArray) = a.getOrElse(GLASSES_COLOR) { 0 }.let { Color.parseColor(catalogHex("glassesColors", it) ?: GLASSES_HEX[it.coerceIn(0, GLASSES_HEX.size - 1)]) }
    fun pantsColor(a: IntArray) = a.getOrElse(PANTS_COLOR) { 0 }.let { Color.parseColor(catalogHex("pantsColors", it) ?: PANTS_HEX[it.coerceIn(0, PANTS_HEX.size - 1)]) }
    /** 흰 바탕 위 막대에 쓸 대표색: 옅은 색(노랑·민트·회색 등)은 한 단 진하게(대비 3:1 맞추기, 53번 2절). */
    fun barColor(i: Int): Int {
        val c = color(i)
        val lum = (0.2126 * lin(Color.red(c)) + 0.7152 * lin(Color.green(c)) + 0.0722 * lin(Color.blue(c)))
        return if ((1.05 / (lum + 0.05)) >= 3.0) c else darker(c, 0.72f)
    }
    private fun lin(v: Int) = (v / 255.0).let { if (it <= 0.04045) it / 12.92 else Math.pow((it + 0.055) / 1.055, 2.4) }
    fun darker(c: Int, k: Float) = Color.rgb((Color.red(c) * k).toInt(), (Color.green(c) * k).toInt(), (Color.blue(c) * k).toInt())

    private fun catalogHex(key: String, i: Int): String? = catalog?.optJSONArray(key)?.optJSONObject(i)?.optString("hex")?.takeIf { it.startsWith("#") }

    /** GET /api/presets 응답(face_spec 포함). 받기 전이면 null → 내장 FACE_SPEC. */
    @Volatile private var catalog: JSONObject? = null
    val spec: JSONObject get() = catalog?.optJSONObject("face_spec") ?: builtInSpec

    // server/avatar.py FACE_SPEC v0 그대로(못 받았을 때)
    private val builtInSpec: JSONObject by lazy { JSONObject("""
    {"version":0,"size":512,"ink":"#2B2522","blushColor":"#F2969A66","stubble":"#4A322633","mouthIn":"#E0605E",
     "eyes":{"y":0.50,"dx":0.15,"options":[{"shape":"dot","w":0.070,"h":0.070,"shine":0.020},{"shape":"dot","w":0.090,"h":0.100,"shine":0.030},
       {"shape":"dot","w":0.050,"h":0.050,"shine":0.014},{"shape":"dot","w":0.060,"h":0.100,"shine":0.018},{"shape":"line","w":0.090,"stroke":0.016},
       {"shape":"arc_up","w":0.100,"h":0.040,"stroke":0.018},{"shape":"droop","w":0.080,"h":0.070,"tilt":-12}]},
     "brows":{"y":0.39,"dx":0.16,"options":[{"shape":"short","w":0.070,"stroke":0.022},{"shape":"arch","w":0.110,"stroke":0.012},
       {"shape":"flat","w":0.110,"stroke":0.030},{"shape":"droop","w":0.120,"stroke":0.034,"tilt":-14}]},
     "nose":{"y":0.60,"options":[{"shape":"dot","w":0.030,"h":0.022},{"shape":"button","w":0.060,"h":0.045},{"shape":"wide","w":0.100,"h":0.055}]},
     "mouth":{"y":0.71,"options":[{"shape":"smile","w":0.120,"h":0.040,"stroke":0.016},{"shape":"open_smile","w":0.140,"h":0.080},
       {"shape":"line","w":0.090,"stroke":0.014},{"shape":"o","w":0.040,"h":0.050}]},
     "wrinkle":{"options":[null,{"shape":"eye_corner","y":0.50,"dx":0.25,"w":0.040,"lines":2,"stroke":0.008},
       {"shape":"forehead_smile","y":0.24,"w":0.220,"lines":3,"fold_y":0.66,"fold_dx":0.15,"stroke":0.008},{"shape":"both","of":[1,2]}]},
     "blush":{"y":0.63,"dx":0.25,"r":0.065},
     "beard":{"stubble":{"y":0.80,"w":0.46,"h":0.22}}}
    """.trimIndent()) }

    // ---------- 받기·저장 ----------

    private val io = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var loading = false
    private var lastLoad = 0L

    private fun prefs(c: Context) = c.getSharedPreferences("sim", Context.MODE_PRIVATE)

    /** 저장해 둔 마지막 광장(인터넷이 없어도 앉은 사람은 보이게). */
    fun cached(c: Context): PlazaData? = runCatching { prefs(c).getString("plaza", null)?.let(::parse) }.getOrNull()

    /** 서버에서 광장을 받아 Hub.plaza 에 넣는다(뒤 스레드). force가 아니면 5초 안에 다시 부르지 않는다. */
    fun load(c: Context, force: Boolean = false) {
        val app = c.applicationContext
        FaceSheet.init(app)   // 얼굴 부품 그림 한 번 읽기
        if (Hub.plaza == null) cached(app)?.let { Hub.plaza = it }
        val now = System.currentTimeMillis()
        if (loading || (!force && now - lastLoad < 5000)) return
        loading = true; lastLoad = now
        io.execute {
            if (catalog == null) runCatching { JSONObject(Api.presets()) }.onSuccess { catalog = it; prefs(app).edit().putString("presets", it.toString()).apply() }
                .onFailure { runCatching { prefs(app).getString("presets", null)?.let { catalog = JSONObject(it) } } }
            val r = runCatching { Api.plaza() }
            main.post {
                loading = false
                r.onSuccess { raw -> runCatching { parse(raw) }.onSuccess { d -> prefs(app).edit().putString("plaza", raw).apply(); update(d) } }
                 .onFailure { Hub.log("광장 못 받음: ${it.message}") }
            }
        }
    }

    /** 자리 바꾸기 결과 등 새 광장 값을 바로 반영한다(메인 스레드). */
    fun update(d: PlazaData) {
        if (Hub.plaza == d) return
        Hub.plaza = d; Hub.changed()
    }

    /** POST /api/plaza/order 응답을 광장으로(뒤 스레드에서 부른다). */
    fun order(c: Context, slots: Map<String, Int>): PlazaData {
        val raw = Api.plazaOrder(slots)
        val d = parse(raw)
        prefs(c.applicationContext).edit().putString("plaza", raw).apply()
        return d
    }

    fun parse(raw: String): PlazaData {
        val o = JSONObject(raw)
        val arr = o.optJSONArray("people") ?: JSONArray()
        val people = (0 until arr.length()).map { arr.getJSONObject(it) }.mapNotNull { p ->
            val slot = p.optInt("slot", 0).takeIf { it in 1..5 } ?: return@mapNotNull null
            PlazaPerson(slot, p.getString("code"), p.str("name"), p.optInt("color", (slot - 1) % 8).coerceIn(0, 7), avatarOf(p.optJSONObject("avatar"), slot))
        }.sortedBy { it.slot }
        val next = if (o.isNull("next_slot")) null else o.optInt("next_slot", 0).takeIf { it in 1..5 }
        return PlazaData(people, o.optInt("pending", 0), next, o.optInt("max", 5))
    }

    private fun avatarOf(o: JSONObject?, slot: Int): IntArray {
        val base = DEFAULTS[(slot - 1).coerceAtLeast(0) % DEFAULTS.size].copyOf()
        if (o == null) return base
        KEYS.forEachIndexed { i, k -> if (o.has(k)) o.optInt(k, base[i]).let { v -> if (v in 0 until COUNT[i]) base[i] = v } }
        // 수염색이 없던 때 저장된 캐릭터: 긴 수염은 흰색, 나머지는 머리색(서버 avatar.upgrade와 같다)
        if (!o.has("beardColor")) base[BEARD_COLOR] = if (base[BEARD] == 3) 4 else base[HAIR_COLOR]
        // 수염·점 비트 칸이 없던 기록: 예전 한 칸 값을 같은 모습의 비트로(서버 avatar.upgrade 와 같다)
        if (!o.has("beards")) base[BEARDS] = BEARD_OLD.getOrElse(base[BEARD]) { 0 }
        // 콧수염(2)·턱수염(4)은 둘 중 하나(턱수염 3D 에 콧수염이 붙어 있다): 둘 다 켜진 값은 턱수염만(서버 avatar.beards_fix 와 같다)
        if (base[BEARDS] and 6 == 6) base[BEARDS] = base[BEARDS] and 2.inv()
        if (!o.has("marks")) base[MARKS] = MARK_OLD.getOrElse(base[MARK]) { 0 }
        // 소품이 없던 때 저장된 캐릭터: DEFAULTS 의 0(없음) 그대로(서버 avatar.upgrade 와 같다)
        // 목도리 색이 없던 때 저장된 캐릭터: DEFAULTS 의 1(분홍) 그대로(서버 avatar.upgrade 와 같다)
        return base
    }

    // ---------- 얼굴 그림(2D): FACE_SPEC 좌표 그대로. 한 변 = 1.0 기준 ----------

    private fun hex(s: String?, fallback: Int = Color.BLACK): Int {
        if (s == null) return fallback
        val h = s.removePrefix("#")
        return runCatching {
            when (h.length) {
                6 -> Color.parseColor("#$h")
                8 -> Color.parseColor("#" + h.substring(6, 8) + h.substring(0, 6))   // #RRGGBBAA → #AARRGGBB
                else -> fallback
            }
        }.getOrDefault(fallback)
    }
    private fun alpha(c: Int, a: Float) = Color.argb((a.coerceIn(0f, 1f) * 255).toInt(), Color.red(c), Color.green(c), Color.blue(c))
    private fun rot(tilt: Double, s: Int) = (-(tilt) * s).toFloat()   // 도(degree) 단위 회전(Canvas.rotate)

    /** 얼굴 텍스처 한 장(size×size). bg: 바탕색(피부). avatar3d.js drawFace 와 같은 순서로 그린다. */
    fun drawFace(size: Int, a: IntArray, bg: Int?): Bitmap {
        FaceSheet.draw(size, a, bg)?.let { return it }   // GPT 부품 그림(assets/face_atlas). 못 읽으면 아래 도형 그리기
        val bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val g = Canvas(bmp)
        val S = size.toFloat()
        val F = spec
        val ink = hex(F.optString("ink", "#2B2522"))
        val hair = hairColor(a)
        if (bg != null) g.drawColor(bg)
        fun X(v: Double) = (v * S).toFloat()
        val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
        val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
        val sides = intArrayOf(-1, 1)

        // 짧은 수염(수염 1): 입보다 먼저
        val stub = F.optJSONObject("beard")?.optJSONObject("stubble")
        if (a.getOrElse(BEARDS) { 0 } and 1 != 0 && stub != null) {
            val bc = beardColor(a); val c = Color.argb(Color.alpha(hex(F.optString("stubble", "#4A322633"))), Color.red(bc), Color.green(bc), Color.blue(bc))   // 색은 수염색, 옅기는 명세 값
            val bw = stub.optDouble("w"); val bh = stub.optDouble("h")
            g.save(); g.translate(X(.5), X(stub.optDouble("y"))); g.scale(1f, (bh / bw).toFloat())
            val r = X(bw / 2)
            fill.shader = RadialGradient(0f, 0f, r, intArrayOf(c, c, alpha(c, 0f)), floatArrayOf(0f, .55f, 1f), Shader.TileMode.CLAMP)
            g.drawCircle(0f, 0f, r, fill); fill.shader = null; g.restore()
            fill.color = alpha(c, min(1f, Color.alpha(c) / 255f * 1.6f))
            var seed = 7L
            fun rnd(): Double { seed = (seed * 16807) % 2147483647; return seed / 2147483647.0 }
            repeat(70) {
                val t = rnd() * PI * 2; val d = sqrt(rnd()) * .85
                g.drawCircle(X(.5 + cos(t) * d * bw / 2), X(stub.optDouble("y") + sin(t) * d * bh / 2), X(.004), fill)
            }
        }
        // 볼터치
        if (a[BLUSH] != 0) {
            val b = F.optJSONObject("blush")
            if (b != null) {
                val c = hex(F.optString("blushColor", "#F2969A66").takeIf { it.startsWith("#") } ?: "#F2969A66")
                for (s in sides) {
                    val x = X(.5 + s * b.optDouble("dx")); val y = X(b.optDouble("y")); val r = X(b.optDouble("r"))
                    fill.shader = RadialGradient(x, y, r, c, alpha(c, 0f), Shader.TileMode.CLAMP)
                    g.drawCircle(x, y, r, fill)
                }
                fill.shader = null
            }
        }
        // 주름(잉크를 옅게). 3 눈가+이마는 "of" 의 두 모양을 다 그린다
        val wOpts = F.optJSONObject("wrinkle")?.optJSONArray("options")
        val w0 = wOpts?.optJSONObject(a[WRINKLE])
        val wList = w0?.optJSONArray("of")?.let { of -> (0 until of.length()).mapNotNull { wOpts.optJSONObject(of.optInt(it)) } } ?: listOfNotNull(w0)
        for (w in wList) {
            line.color = alpha(ink, .38f); line.strokeWidth = X(w.optDouble("stroke"))
            val lines = w.optInt("lines", 2)
            when (w.optString("shape")) {
                "eye_corner" -> for (s in sides) for (i in 0 until lines) {
                    val x = X(.5 + s * w.optDouble("dx")); val y = X(w.optDouble("y")); val ang = (i - (lines - 1) / 2.0) * .55
                    g.drawLine(x, y, x + s * (cos(ang) * X(w.optDouble("w"))).toFloat(), y + (sin(ang) * X(w.optDouble("w"))).toFloat(), line)
                }
                "forehead_smile" -> {
                    for (i in 0 until lines) {
                        val y = X(w.optDouble("y") + i * .035); val hw = X(w.optDouble("w") / 2) * (1 - i * .12f)
                        g.drawPath(Path().apply { moveTo(X(.5) - hw, y + X(.01)); quadTo(X(.5), y - X(.018), X(.5) + hw, y + X(.01)) }, line)
                    }
                    for (s in sides) {
                        val x = X(.5 + s * w.optDouble("fold_dx")); val y = X(w.optDouble("fold_y"))
                        g.drawPath(Path().apply { moveTo(x - s * X(.01), y - X(.045)); quadTo(x + s * X(.02), y, x + s * X(.005), y + X(.06)) }, line)
                    }
                }
            }
        }
        // 코: 작은 점은 잉크, 나머지는 선 없이 그림자 + 빛
        val nose = F.optJSONObject("nose")
        val n = nose?.optJSONArray("options")?.optJSONObject(a[NOSE])
        if (nose != null && n != null) {
            val ny = X(nose.optDouble("y"))
            if (n.optString("shape") == "dot") {
                fill.color = alpha(ink, .85f)
                g.drawOval(RectF(X(.5) - X(n.optDouble("w") / 2), ny - X(n.optDouble("h") / 2), X(.5) + X(n.optDouble("w") / 2), ny + X(n.optDouble("h") / 2)), fill)
            } else {
                g.save(); g.translate(X(.5), ny); g.scale(1f, (n.optDouble("h") / n.optDouble("w")).toFloat())
                val r = X(n.optDouble("w") / 2) * 1.25f
                fill.shader = RadialGradient(0f, r * .25f, r, Color.argb(87, 176, 96, 66), Color.argb(0, 176, 96, 66), Shader.TileMode.CLAMP)
                g.drawCircle(0f, 0f, r * 1.2f, fill); fill.shader = null
                fill.color = Color.argb(97, 255, 255, 255); g.drawCircle(-r * .22f, -r * .3f, r * .28f, fill)
                g.restore()
            }
        }
        // 입
        val mouth = F.optJSONObject("mouth")
        val m = mouth?.optJSONArray("options")?.optJSONObject(a[MOUTH])
        if (mouth != null && m != null) {
            val my = X(mouth.optDouble("y"))
            line.color = ink; fill.color = ink
            when (m.optString("shape")) {
                "smile" -> {
                    line.strokeWidth = X(m.optDouble("stroke"))
                    val cy = my - X(m.optDouble("h") / 2); val rx = X(m.optDouble("w") / 2); val ry = X(m.optDouble("h"))
                    g.drawArc(RectF(X(.5) - rx, cy - ry, X(.5) + rx, cy + ry), 18f, 144f, false, line)   // 0.1π~0.9π
                }
                "open_smile" -> {
                    val top = my - X(m.optDouble("h") / 2); val hw = X(m.optDouble("w") / 2); val dh = X(m.optDouble("h"))
                    fun shape(k: Float): Path {
                        val y0 = top + (1 - k) * dh * .2f
                        return Path().apply {
                            moveTo(X(.5) - hw * k, y0); lineTo(X(.5) + hw * k, y0)
                            arcTo(RectF(X(.5) - hw * k, y0 - dh * k, X(.5) + hw * k, y0 + dh * k), 0f, 180f, false); close()
                        }
                    }
                    g.drawPath(shape(1f), fill)
                    fill.color = hex(F.optString("mouthIn", "#E0605E")); g.drawPath(shape(.78f), fill)
                }
                "line" -> { line.strokeWidth = X(m.optDouble("stroke")); g.drawLine(X(.5 - m.optDouble("w") / 2), my, X(.5 + m.optDouble("w") / 2), my, line) }
                else -> g.drawOval(RectF(X(.5) - X(m.optDouble("w") / 2), my - X(m.optDouble("h") / 2), X(.5) + X(m.optDouble("w") / 2), my + X(m.optDouble("h") / 2)), fill)
            }
        }
        // 눈: 흰자 없는 점 + 작은 반사광
        val eyes = F.optJSONObject("eyes")
        val e = eyes?.optJSONArray("options")?.optJSONObject(a[EYES])
        if (eyes != null && e != null) {
            val ey = X(eyes.optDouble("y"))
            for (s in sides) {
                val x = X(.5 + s * eyes.optDouble("dx"))
                g.save(); g.translate(x, ey); fill.color = ink; line.color = ink
                when (val shape = e.optString("shape")) {
                    "dot", "droop" -> {
                        val rx = X(e.optDouble("w") / 2); val ry = X(e.optDouble("h") / 2)
                        if (shape == "droop") {   // 위 눈꺼풀이 바깥으로 처진 반쯤 감은 눈
                            g.rotate(rot(e.optDouble("tilt"), s))
                            g.save(); g.clipRect(-rx * 2, -ry * .25f, rx * 2, -ry * .25f + ry * 3)
                            g.drawOval(RectF(-rx, -ry, rx, ry), fill); g.restore()
                            line.strokeWidth = X(.012); g.drawLine(-rx * 1.15f, -ry * .25f, rx * 1.15f, -ry * .25f, line)
                        } else g.drawOval(RectF(-rx, -ry, rx, ry), fill)
                        val sh = if (e.has("shine")) X(e.optDouble("shine") / 2) else rx * .3f
                        fill.color = Color.WHITE
                        g.drawCircle(rx * .32f, -ry * (if (shape == "droop") .02f else .38f), sh, fill)
                    }
                    "line" -> { line.strokeWidth = X(e.optDouble("stroke")); g.drawLine(-X(e.optDouble("w") / 2), 0f, X(e.optDouble("w") / 2), 0f, line) }
                    "arc_up" -> {
                        line.strokeWidth = X(e.optDouble("stroke"))
                        val cy = X(e.optDouble("h") / 2); val rx = X(e.optDouble("w") / 2); val ry = X(e.optDouble("h"))
                        g.drawArc(RectF(-rx, cy - ry, rx, cy + ry), 194.4f, 151.2f, false, line)   // 1.08π~1.92π
                    }
                }
                g.restore()
            }
        }
        // 눈썹(머리색)
        val brows = F.optJSONObject("brows")
        val b = brows?.optJSONArray("options")?.optJSONObject(a[BROWS])
        if (brows != null && b != null) {
            line.color = hair; line.strokeWidth = X(b.optDouble("stroke"))
            val by = X(brows.optDouble("y"))
            for (s in sides) {
                val x = X(.5 + s * brows.optDouble("dx")); val hw = X(b.optDouble("w") / 2)
                g.save(); g.translate(x, by)
                val p = Path()
                when (b.optString("shape")) {
                    "short" -> { p.moveTo(-hw, X(.006)); p.quadTo(0f, -X(.012), hw, X(.006)) }
                    "arch" -> { p.moveTo(-hw, X(.012)); p.quadTo(0f, -X(.03), hw, X(.012)) }
                    "flat" -> { p.moveTo(-hw, 0f); p.lineTo(hw, 0f) }
                    else -> { g.rotate(rot(b.optDouble("tilt"), s)); p.moveTo(-hw, 0f); p.quadTo(0f, -X(.014), hw, 0f) }
                }
                g.drawPath(p, line); g.restore()
            }
        }
        return bmp
    }

    /** 재생 패널·누름 카드의 얼굴 칸: 대표색 바탕 위 어깨 위 정지 그림(avatar3d.js snap2d 와 같은 꼴). */
    fun bust(p: PlazaPerson, size: Int): Bitmap {
        val bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val g = Canvas(bmp)
        val S = size.toFloat()
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        g.drawColor(color(p.color))
        paint.color = darker(color(p.color), .85f)
        g.drawOval(RectF(S * .14f, S * .8f, S * .86f, S * 1.24f), paint)   // 어깨(옷)
        if (p.avatar[HAIR] != 4) { paint.color = hairColor(p.avatar); g.drawCircle(S / 2, S * .44f, S * .36f, paint) }
        val face = drawFace(256, p.avatar, skin(p.avatar))
        g.save()
        g.clipPath(Path().apply { addCircle(S / 2, S * .48f, S * .31f, Path.Direction.CW) })
        g.drawBitmap(face, android.graphics.Rect((256 * .14f).toInt(), (256 * .2f).toInt(), (256 * .86f).toInt(), (256 * .92f).toInt()),
            RectF(S * .19f, S * .17f, S * .81f, S * .79f), Paint(Paint.FILTER_BITMAP_FLAG))
        g.restore()
        face.recycle()
        return bmp
    }
}
