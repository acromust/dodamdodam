package ai.simeodum.car

import android.content.Context
import android.util.Base64
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/** 숨긴 메시지 하나. 내용(audio)은 열릴 때까지 운전자 화면에 안 나온다. */
data class Hidden(
    val id: String,
    val sender: String,
    val moment: String,   // start · arrive · home · rain · battery
    val audioPath: String,
    val played: Boolean,  // 이미 들음
    val done: Boolean,    // 들었거나 사라짐
    val repeat: String = "once", // once(그날 한 번) · each(그 순간마다, 하루 한 번)
    val pickedDate: String? = null, // 남긴 사람이 달력에서 고른 날짜(yyyy-MM-dd). 오늘·내일로 고르면 없음
    val place: Place? = null,       // moment가 place일 때 남긴 사람이 지도에서 고른 곳
    val stopped: Boolean = false,   // 반복 메시지를 운전자가 그만 들음(목록엔 남아 다시 켤 수 있다)
    // 들은 메시지 줄(시각·길이·답장). 서버가 주면 쓰고, 없으면 차에 남긴 기록을 쓴다
    val heardAt: Long? = null,      // 들은 시각(ms)
    val lenMs: Long? = null,        // 길이(ms)
    val replied: Boolean = false,   // 답장한 적 있음
    // 남긴 사람 사진: 초대 코드와 사진 판 번호(서버가 주면). 정차 중 화면에만 동그랗게 보인다(Store.photoFile)
    val invite: String? = null,
    val photo: String? = null,
    // 이 메시지가 어느 날 목록에서 왔는지(yyyy-MM-dd). 자정을 넘겨 들어도 들음을 그날로 남기려고
    val day: String? = null,
    // 운전자가 고른 반응 이모티콘(C4, REACTIONS 중 하나). 서버가 주면 쓴다. 안 골랐으면 null
    val reaction: String? = null,
)

/** 운전자가 고르는 반응 다섯(서버 REACTIONS와 같은 순서·같은 글자): ❤️ 👍 😂 😮 😢. 하나만 남고, 다른 걸 누르면 바뀐다. */
val REACTIONS = listOf("\u2764\uFE0F", "\uD83D\uDC4D", "\uD83D\uDE02", "\uD83D\uDE2E", "\uD83D\uDE22")

/** 남긴 사람을 부르는 말: 모든 화면·안내에서 '○○님'으로 통일한다(2026-11-03 사용자 결정, '엄마가'는 존중하지 않는 느낌). */
fun nim(name: String) = if (name.endsWith("님")) name else "${name}님"

/** 남긴 사람이 고른 장소. 차 위치가 아니라서 서버에 있어도 공유 원칙에 걸리지 않는다. */
data class Place(val lat: Double, val lon: Double, val name: String)

fun placeOf(o: JSONObject?) = o?.let { Place(it.getDouble("lat"), it.getDouble("lon"), it.getString("name")) }

/** 운전자가 보낸 초대 링크. name은 링크를 연 사람이 처음 숨길 때 정해진다(그전엔 null).
 *  claimed: 어떤 폰이 이 링크를 처음 열어 가졌는지(그 폰만 쓸 수 있다). photo: 사진 판 번호.
 *  reissued: 다시 연결로 만든 새 링크를 새 폰이 열기 전. */
data class Invite(val code: String, val name: String?, val claimed: Boolean = false, val photo: String? = null, val reissued: Boolean = false)

/** JSON 값이 비었거나 null이면 null(org.json의 optString은 null을 "null"로 준다). */
fun JSONObject.str(k: String) = optString(k).takeIf { it.isNotEmpty() && it != "null" }

/** 순간 이름(안내 문장·화면에 쓴다). */
val MOMENT_LABEL = mapOf("start" to "차 탈 때", "arrive" to "주차했을 때", "home" to "집 근처에 왔을 때", "rain" to "비 올 때", "long" to "오래 달렸을 때", "battery" to "배터리·기름이 부족할 때", "place" to "장소에 왔을 때")
/** 순간 이름(알림·화면 공통): 장소 메시지는 고른 장소 이름으로 '○○ 근처에 왔을 때'. */
fun momentLabel(h: Hidden) = h.place?.let { "${it.name} 근처에 왔을 때" } ?: MOMENT_LABEL[h.moment] ?: h.moment

/** 서버(기본: 맥 127.0.0.1:8090 → 에뮬레이터 10.0.2.2:8090, 클라우드 빌드: API_BASE). 모두 백그라운드 스레드에서 부른다. */
object Api {
    val BASE: String = BuildConfig.API_BASE
    /** 이 차의 번호. 처음 켤 때 한 번 만들어 둔다. 서버는 이 번호로 이 차의 초대 링크·메시지만 준다. */
    @Volatile var carId = ""
        private set

    fun init(ctx: Context) {
        if (carId.isNotEmpty()) return
        val p = ctx.getSharedPreferences("car", Context.MODE_PRIVATE)
        carId = p.getString("id", null) ?: java.util.UUID.randomUUID().toString().also { p.edit().putString("id", it).apply() }
    }

    /** day: 받을 날(차의 오늘). waitMs: 처음 깐 차는 무료 서버가 깨어나는 동안(최대 50초쯤) 기다린다. */
    fun today(day: String = java.time.LocalDate.now().toString(), waitMs: Int = 8000): List<Hidden> {
        // 서버가 다른 시간대(예: UTC 클라우드)에 있어도 차의 오늘 날짜로 받는다
        val json = JSONObject(get("/api/messages?date=$day", readMs = waitMs, connectMs = if (waitMs > 8000) 15_000 else 4000))
        val arr = json.getJSONArray("messages")
        return (0 until arr.length()).map { hiddenOf(arr.getJSONObject(it)).copy(day = day) }
    }

    private fun hiddenOf(it: JSONObject) = Hidden(it.getString("id"), it.getString("sender"), it.getString("moment"), it.getString("audio"), it.has("played"), it.has("played") || it.has("expired"), it.optString("repeat", "once"), if (it.optBoolean("picked")) it.optString("date") else null, placeOf(it.optJSONObject("place")), it.has("stopped") && it.opt("stopped") != false,
        it.optLong("heard_at", 0L).takeIf { t -> t > 0 }?.times(1000), it.optDouble("sec", 0.0).takeIf { d -> d > 0 }?.let { d -> (d * 1000).toLong() }, it.optBoolean("replied"),
        it.str("invite"), it.str("photo"), reaction = reactionOf(it))

    /** 서버의 reaction {emoji, at}. 예전 서버가 시각 숫자만 주면 ❤️(서버와 같은 호환 규칙). */
    private fun reactionOf(o: JSONObject): String? = when (val r = o.opt("reaction")) {
        is JSONObject -> r.str("emoji")?.takeIf { it in REACTIONS }
        is Number -> REACTIONS[0]
        else -> null
    }

    /** 보관 기간 안에서 오늘 전에 들은 메시지와 들은 날(yyyy-MM-dd). 최근 것부터. */
    fun heardBefore(): List<Pair<Hidden, String>> {
        val arr = JSONObject(get("/api/heard?date=${java.time.LocalDate.now()}")).getJSONArray("messages")
        return (0 until arr.length()).map { arr.getJSONObject(it) }.map { hiddenOf(it.put("played", true)) to it.getString("heard_day") }
    }

    /** 이 메시지를 남긴 사람을 신고한다. 서버가 그 사람의 초대 링크를 끊는다. */
    fun report(messageId: String) = post("/api/reports", JSONObject().put("message_id", real(messageId)))

    // 반복 메시지는 날짜별로 기록되므로 차의 오늘 날짜를 같이 보낸다
    private fun dayBody() = JSONObject().put("date", java.time.LocalDate.now().toString())
    /** 예시 메시지(demo-)는 서버에 없으니 절대 보내지 않는다. 화면에서 걸러도 한 번 더 막는다. */
    private fun real(id: String) = id.also { require(!it.startsWith("demo-")) { "예시 메시지는 서버로 보내지 않음" } }
    /** day: 그 메시지가 속한 날. 자정 넘어 들은 어제 목록 메시지를 오늘로 보내면 서버의 오늘·지난 목록 어디에도 안 보인다. */
    fun markPlayed(id: String, day: String? = null) = post("/api/messages/${real(id)}/played", day?.let { JSONObject().put("date", it) } ?: dayBody())
    /** 운전자가 반복 메시지를 그만 듣기(stop) / 다시 듣기(resume). 남긴 사람 화면은 바뀌지 않는다. */
    fun setRepeat(id: String, keep: Boolean) = post("/api/messages/${real(id)}/${if (keep) "resume" else "stop"}", dayBody())
    fun demoReset() = post("/api/demo/reset", JSONObject())

    fun reply(messageId: String, file: File, mime: String) = post("/api/replies", JSONObject()
        .put("message_id", real(messageId))
        .put("mime", mime)
        .put("audio", Base64.encodeToString(file.readBytes(), Base64.NO_WRAP)))

    /** 녹음 없이 고르는 반응(C4): 이모티콘 하나(REACTIONS). 다른 걸 보내면 바뀐다. 서버가 처음·바뀔 때만 남긴 사람 폰에 알린다. */
    fun react(messageId: String, emoji: String) = post("/api/reactions", JSONObject().put("message_id", real(messageId))
        .put("emoji", emoji.also { require(it in REACTIONS) { "고를 수 없는 반응" } }))

    fun audioUrl(path: String) = BASE + path

    /** 서버에 바뀐 게 생길 때까지 붙어 기다렸다가 새 번호를 받는다(서버가 최대 25초 붙잡는다). */
    fun waitChange(since: Long): Long = JSONObject(get("/api/changes?since=$since", readMs = 35_000)).getLong("version")

    fun invites(): List<Invite> {
        val arr = JSONObject(get("/api/invites")).getJSONArray("invites")
        return (0 until arr.length()).map { arr.getJSONObject(it) }.map { Invite(it.getString("code"), it.str("name"), it.optBoolean("claimed"), it.str("photo"), it.optBoolean("reissued")) }
    }
    /** 새 초대 링크 코드. from: 운전자 이름(예: 홍길동, '님' 없이). 웹 초대장에 '홍길동님 차'로 보인다. 없으면 null. */
    fun createInvite(from: String?): String = JSONObject(post("/api/invites", JSONObject().put("from", from ?: JSONObject.NULL))).getString("code")
    fun revokeInvite(code: String) = post("/api/invites/$code/revoke", JSONObject())
    /** 폰을 바꾼 사람에게 새 링크(같은 사람으로 이어진다: 이름·사진·메시지·답장). 예전 링크는 끊긴다. 새 코드를 돌려준다. */
    fun reissueInvite(code: String, from: String?): String = JSONObject(post("/api/invites/$code/reissue", JSONObject().put("from", from ?: JSONObject.NULL))).getString("code")
    /** 남긴 사람 사진(JPEG). 이 차가 만든 초대 링크의 것만 받는다. 없으면 오류. */
    fun photo(invite: String, v: String): ByteArray {
        val c = URL("$BASE/api/car/photo?invite=${java.net.URLEncoder.encode(invite, "UTF-8")}&v=${java.net.URLEncoder.encode(v, "UTF-8")}").openConnection() as HttpURLConnection
        c.connectTimeout = 4000; c.readTimeout = 8000
        carKey(c)
        try {
            if (c.responseCode != 200) error("사진 없음 ${c.responseCode}")
            return c.inputStream.use { it.readBytes() }
        } finally { c.disconnect() }
    }
    /** 차 홈 광장: 자리별 사람(캐릭터·대표색)·대기 개수·다음 초대 자리(JSON 그대로, Plaza.parse). 누가 보냈는지는 없다. */
    fun plaza(): String = get("/api/plaza")
    /** 자리 바꾸기(차 주인, P에서만): {코드: 자리}. 응답은 바뀐 광장(plaza 와 같은 꼴 + ok). */
    fun plazaOrder(slots: Map<String, Int>): String = post("/api/plaza/order", JSONObject().put("slots", JSONObject(slots as Map<*, *>)))
    /** 캐릭터 부품·색·얼굴 그리기 규칙(face_spec). 폰 웹과 같은 값. */
    fun presets(): String = get("/api/presets")

    /** 숨기는 사람이 여는 주소(시연: 노트북 서버). */
    fun inviteLink(code: String) = "${BuildConfig.SHARE_BASE}/?invite=$code"
    /** 차 화면에 크게 보여 줄 주소(https:// 없이, 예: dodamdodam.onrender.com). 가족이 이 주소를 열고 코드를 넣는다. */
    val shareHost: String = BuildConfig.SHARE_BASE.substringAfter("://").trimEnd('/')

    private fun carKey(c: HttpURLConnection) {
        if (BuildConfig.CAR_KEY.isNotEmpty()) c.setRequestProperty("X-Car-Key", BuildConfig.CAR_KEY)
        if (carId.isNotEmpty()) c.setRequestProperty("X-Car-Id", carId)
    }

    private fun get(path: String, readMs: Int = 8000, connectMs: Int = 4000): String {
        val c = URL(BASE + path).openConnection() as HttpURLConnection
        c.connectTimeout = connectMs; c.readTimeout = readMs
        carKey(c)
        return c.inputStream.bufferedReader().use { it.readText() }.also { c.disconnect() }
    }

    private fun post(path: String, body: JSONObject): String {
        val c = URL(BASE + path).openConnection() as HttpURLConnection
        c.connectTimeout = 4000; c.readTimeout = 15000
        c.requestMethod = "POST"; c.doOutput = true
        carKey(c)
        c.setRequestProperty("Content-Type", "application/json")
        c.outputStream.use { it.write(body.toString().toByteArray()) }
        val code = c.responseCode
        val text = (if (code < 400) c.inputStream else c.errorStream).bufferedReader().use { it.readText() }
        c.disconnect()
        if (code >= 400) error("서버 $code: $text")
        return text
    }
}
