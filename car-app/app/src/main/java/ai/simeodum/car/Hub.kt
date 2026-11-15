package ai.simeodum.car

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.time.LocalDate
import java.util.Date
import java.util.Locale

/** 서비스와 화면이 같은 프로세스에서 나눠 쓰는 상태. */
object Hub {
    var service: CarService? = null
    var today: List<Hidden> = emptyList()
    /** 서비스가 목록을 한 번이라도 받았는지(서버·저장분·체험 중 하나로). 그전엔 메인 숫자를 비워 둔다. */
    var loaded = false
    /** 체험 메시지로 도는 중(서버에 못 닿음). 들음 기록·답장은 서버로 보내지 않는다. */
    var demo = false
    val opened = mutableSetOf<String>()
    var waiting: String? = null
    /** 주차했을 때 '다음에도 들을까요?'를 물을 반복 메시지(정차 중 화면에 카드로). */
    var askRepeat: List<Hidden> = emptyList()
    /** 지금 나오는 목소리(정차 중 화면이 재생 카드로 보여 준다). */
    var nowPlaying: Hidden? = null
    var paused = false
    /** 기어 P(서 있음). 답장 버튼·도착 연출은 이때만. */
    var parked = false
    var driving = false   // 기어를 안 뒤로 P가 아닌 상태
    /** 막 열려 '들을까요?'를 기다리는 목소리(버튼 듣기). 정차 중이면 화면이 도착 장면으로 보여 준다. */
    var offered: Hidden? = null
    /** 버튼 듣기 카드의 남은 시간 막대(11/09): 핸들 버튼을 받는 시간이 끝나는 때(elapsedRealtime). 0이면 안내 음성이 나오는 중(막대는 꽉 찬 채로 멈춤). */
    var askEndsAt = 0L
    var askWindowMs = 8_000L
    /** 이번 주차를 시작한 때(ms). '주차했을 때' 메시지가 주차 목록에서 온 시각. */
    var parkedAt = 0L
    /** 앱 화면이 보이는 중(정차 중이면 알림 카드 대신 화면의 도착 장면으로 충분). */
    var visible = false
    /** 도착해서 이어 듣는 중이면 남은 개수(재생 중인 것 포함), 아니면 0. */
    var arrivalLeft = 0
    /** 보낸 초대 링크(서버에서 받음). null이면 아직 모름(서버 없음·체험 중). */
    var invites: List<Invite>? = null
    /** 서버에 못 닿는 중(저장분으로 기다림). 정차 중 메인 아래에 작게 알린다. */
    @Volatile var offline = false
    /** 시연용 짧은 시간(주차로 볼 주행 15초 등). 맥 서버 개발 빌드는 켜진 채로, 그 밖에는 시연 도구에서 켠다. */
    @Volatile var shortTimes = false
    /** 차 홈 광장(자리별 사람). null이면 아직 모름(받기 전·서버 없음). Plaza.load 가 채운다. */
    @Volatile var plaza: PlazaData? = null
    /** 와이퍼가 켜져 있음(비 판정과 같은 신호). 광장에 유리 돔·빗줄기. */
    @Volatile var raining = false
    /** 전조등(하향등) 켜짐. null이면 신호를 못 받음(그땐 광장 가로등을 시스템 야간 모드로). */
    @Volatile var lowBeam: Boolean? = null
    // ---- 광장이 반응하는 차 신호(64번 27). 모두 가족 전원에게 똑같이 반응한다(대기 메시지와 무관) ----
    /** 운전석 등받이 각도(SDK 값 그대로)와 안전벨트. 젖히고 벨트를 풀면 광장 사람들이 쿠션에 기댄다. */
    @Volatile var backrest: Int? = null
    @Volatile var beltOn: Boolean? = null
    /** 운전석 문이 열린 때(elapsedRealtime). 0이면 없음. */
    @Volatile var doorOpenAt = 0L
    /** 충전구 열림·배터리 잔량(%). */
    @Volatile var chargePort = false
    @Volatile var soc: Int? = null
    /** 무드등 색(RGB)·밝기(SDK 값 그대로). */
    @Volatile var ambientColor: Int? = null
    @Volatile var ambientBright: Int? = null
    /** 공조 풍량 단계. */
    @Volatile var fan: Int? = null
    /** 직전 운행 시간(ms). 오래 달린 뒤 첫 정차엔 손 흔들기 대신 기지개. */
    @Volatile var lastTripMs = 0L
    /** 시연·시험용 날씨 덮어쓰기: rain · snow · clear · night · day (서비스 명령 weather). null이면 실제 신호대로. */
    @Volatile var weatherTest: String? = null
    /** 광장 시험: 다음 돌아가며 하는 행동을 이것으로(wave·stretch·yawn·drink·doze·read·stroll·visit·face2·lookup·lookat·turn·greet). 한 번 쓰면 비움. */
    @Volatile var plazaTest: String? = null
    /** 이번 주차에서 이어 들은 메시지(끝까지 들은 것만, 들은 순서). 이어 듣기가 끝난 뒤 '들은 뒤' 패널의 얼굴 줄에 쓴다(C5). */
    var parkHeard: List<Hidden> = emptyList()
    /** 답장 안 한 메시지 카드를 띄울 때(C7): 시동을 켜고 아직 P · 주행 중에 들은 메시지가 있는 채로 주차. 화면이 정차 중에만 보여 준다. */
    @Volatile var nudge = false
    /** 멈춘 뒤 화면 아래 토스트로 알릴 한 줄(화면이 한 번 보여 주고 지운다). */
    var stopNote: String? = null
    val logs = ArrayDeque<String>()
    private val listeners = mutableListOf<() -> Unit>()
    private val time = SimpleDateFormat("HH:mm:ss", Locale.KOREA)

    /** 실제로 들은 메시지(사라진 건 빼고). 정차 중 화면에서 다시 듣기·답장. */
    val heard = mutableSetOf<String>()

    /** 앱이 켜진 채 날짜가 바뀌면 오늘 기록을 비운다(반복 메시지가 다음 날 다시 나오게). 메인 스레드에서 부른다. */
    private var day = LocalDate.now().toString()
    fun rollDay() {
        val now = LocalDate.now().toString()
        if (now == day) return
        day = now; opened.clear(); heard.clear(); skipped.clear(); askRepeat = emptyList(); retired = emptyList()
        // 자정이 지난 뒤(이 기록을 비우기 전에) 이미 들은 것은 오늘 들은 것이라 그대로 둔다
        service?.let { c -> heardStored(c).let { opened += it; heard += it }; skippedStored(c).let { opened += it; skipped += it } }
    }
    /** 날이 바뀌어 목록에서 빠진 메시지 중 오늘(자정 뒤) 들은 것. 지운 메시지가 아니라서 들은 메시지 화면에 남긴다. */
    var retired: List<Hidden> = emptyList()
    /** 주차해서 이어 듣다 [다음]으로 넘긴 메시지(오늘). 다시 틀지 않고 들은 메시지 화면에서 골라 듣는다. */
    val skipped = mutableSetOf<String>()
    fun skippedStored(c: Context): Set<String> =
        if (prefs(c).getString("skipDate", null) == LocalDate.now().toString()) prefs(c).getStringSet("skipIds", emptySet())!! else emptySet()
    fun markSkipped(c: Context, h: Hidden) {
        skipped += h.id
        forgetOccurred(c, h.id)
        prefs(c).edit().putString("skipDate", LocalDate.now().toString()).putStringSet("skipIds", skippedStored(c) + h.id).apply()
        putMeta(c, h.id, "skip", System.currentTimeMillis())
    }
    /** 들은 메시지 화면에 보이는 오늘 것: 끝까지 들은 것 + 넘긴 것. 최근 것부터. */
    fun heardListToday(c: Context) = (today + retired.filter { r -> today.none { it.id == r.id } }).filter { it.id in heard || it.id in skipped }
        .sortedByDescending { heardAt(c, it.id) ?: meta(c).optJSONObject(it.id)?.optLong("skip") ?: 0L }

    /** 들은 메시지 줄에 쓰는 기록(차에만): 들은 시각·길이·답장 시각. 31일 지나면 지운다. */
    private fun meta(c: Context): JSONObject = runCatching { JSONObject(prefs(c).getString("meta", "{}")!!) }.getOrDefault(JSONObject())
    private fun putMeta(c: Context, id: String, key: String, v: Any) {
        val m = meta(c)
        val o = m.optJSONObject(id) ?: JSONObject()
        o.put(key, v).put("t", System.currentTimeMillis()); m.put(id, o)
        val cut = System.currentTimeMillis() - 31L * 86_400_000L
        m.keys().asSequence().toList().forEach { k -> if ((m.optJSONObject(k)?.optLong("t") ?: 0L) < cut) m.remove(k) }
        prefs(c).edit().putString("meta", m.toString()).apply()
    }
    private fun metaOf(c: Context, id: String, key: String) = meta(c).optJSONObject(id)?.optLong(key, 0L)?.takeIf { it > 0 }
    fun heardAt(c: Context, id: String) = metaOf(c, id, "at")
    /** 들은 메시지를 받은 시각(순간이 온 때). 들을 때 옮겨 둔 값. */
    fun receivedAtSaved(c: Context, id: String) = metaOf(c, id, "rcv")
    fun lenMs(c: Context, id: String) = metaOf(c, id, "len")
    fun repliedAt(c: Context, id: String) = metaOf(c, id, "rep")
    fun setLen(c: Context, id: String, ms: Int) { if (ms > 0 && lenMs(c, id) == null) putMeta(c, id, "len", ms.toLong()) }
    fun setReplied(c: Context, id: String) = putMeta(c, id, "rep", System.currentTimeMillis())
    /** 녹음 없이 고르는 반응(C4)을 마지막으로 보낸 시각. */
    fun reactedAt(c: Context, id: String) = metaOf(c, id, "rct")
    /** 이 메시지에 보낸 반응 이모티콘. 예전 '잘 들었습니다'(시각만 남음)는 ❤️로 읽는다(서버와 같게). 안 보냈으면 null. */
    fun reactionOf(c: Context, id: String): String? {
        val o = meta(c).optJSONObject(id) ?: return null
        return o.str("emo")?.takeIf { it in REACTIONS } ?: if (o.optLong("rct", 0L) > 0) REACTIONS[0] else null
    }
    fun setReacted(c: Context, id: String, emoji: String) {
        putMeta(c, id, "rct", System.currentTimeMillis())
        putMeta(c, id, "emo", emoji)
    }

    // ---------- 답장 안 한 메시지 카드(C7) ----------
    // 들은 메시지를 차에 짧게 적어 둔다(다음 날 시동을 켜도 카드를 띄우려고: 오늘 목록은 날이 바뀌면 비므로). 답장·반응·닫기 한 것은 빼고, 7일 지나면 지운다.
    private const val NUDGE_KEEP_MS = 7L * 86_400_000L   // [확인 필요] 며칠 전 것까지 카드로 띄울지
    private fun rememberHeard(c: Context, h: Hidden) {
        if (h.example || demo || h.id == "test") return
        val arr = runCatching { org.json.JSONArray(prefs(c).getString("heardKeep", "[]")) }.getOrDefault(org.json.JSONArray())
        val out = org.json.JSONArray()
        val cut = System.currentTimeMillis() - NUDGE_KEEP_MS
        for (i in 0 until arr.length()) arr.optJSONObject(i)?.takeIf { it.optString("id") != h.id && it.optLong("at") >= cut }?.let { out.put(it) }
        out.put(JSONObject().put("id", h.id).put("sender", h.sender).put("moment", h.moment).put("audio", h.audioPath).put("at", System.currentTimeMillis())
            .put("invite", h.invite ?: JSONObject.NULL).put("photo", h.photo ?: JSONObject.NULL).put("day", h.day ?: JSONObject.NULL).put("repeat", h.repeat)
            .put("place", h.place?.let { JSONObject().put("lat", it.lat).put("lon", it.lon).put("name", it.name) } ?: JSONObject.NULL))
        while (out.length() > 30) out.remove(0)
        prefs(c).edit().putString("heardKeep", out.toString()).apply()
    }
    /** 카드에 띄울 메시지: 들었고, 답장도 반응도 안 했고, 닫지 않은 것. 최근 들은 것부터. */
    fun unreplied(c: Context): List<Hidden> {
        val arr = runCatching { org.json.JSONArray(prefs(c).getString("heardKeep", "[]")) }.getOrDefault(org.json.JSONArray())
        val cut = System.currentTimeMillis() - NUDGE_KEEP_MS
        val closed = prefs(c).getStringSet("nudgeClosed", emptySet())!!
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }.filter { it.optLong("at") >= cut }.mapNotNull { o ->
            val id = o.optString("id")
            val known = today.firstOrNull { it.id == id }
            if (id in closed || repliedAt(c, id) != null || reactedAt(c, id) != null || known?.replied == true || known?.reaction != null) return@mapNotNull null
            known ?: Hidden(id, o.optString("sender"), o.optString("moment"), o.optString("audio"), true, true, o.optString("repeat", "once"),
                place = placeOf(o.optJSONObject("place")), invite = o.str("invite"), photo = o.str("photo"), day = o.str("day"))
        }.reversed()
    }
    /** 카드를 닫았다: 이 메시지는 다시 띄우지 않는다. */
    fun closeNudge(c: Context, id: String) = prefs(c).edit().putStringSet("nudgeClosed", (prefs(c).getStringSet("nudgeClosed", emptySet())!! + id).toList().takeLast(60).toSet()).apply()
    fun heardToday() = today.filter { it.id in heard }
    /** 끝까지 들었다. 반복 메시지는 다음 날에도 알 수 있게 따로 남긴다(서버는 그날 들음만 알려 준다). */
    /** now: 지금 차에서 끝까지 들었다(들은 시각을 남긴다). 서버가 '들음'이라고 알려 준 것은 시각을 모르니 남기지 않는다. */
    fun markHeard(c: Context, h: Hidden, now: Boolean = true) {
        heard += h.id
        skipped -= h.id
        // 받은 시각(순간이 온 때)은 들은 뒤 한 줄 '집 근처에 왔을 때 · 오후 11:40'에 쓴다: 주차 목록 기록을 지우기 전에 옮겨 둔다
        (occurredAt(c, h.id) ?: parkedAt.takeIf { h.moment == "arrive" && it > 0 })?.let { putMeta(c, h.id, "rcv", it) }
        forgetOccurred(c, h.id)   // 다 들었으니 주차 목록에서 뺀다
        if (now && heardAt(c, h.id) == null) putMeta(c, h.id, "at", System.currentTimeMillis())
        if (now) rememberHeard(c, h)
        // 서버에 알리지 못한 채 앱이 다시 떠도 같은 날 또 재생하지 않게 차에도 남긴다
        prefs(c).edit().putString("heardDate", LocalDate.now().toString()).putStringSet("heardIds", heardStored(c) + h.id).apply()
        if (h.repeat == "each") prefs(c).edit().putStringSet("repeatHeard", prefs(c).getStringSet("repeatHeard", emptySet())!! + h.id).apply()
    }

    /** 오늘 차에서 끝까지 들은 메시지(날짜가 바뀌면 빈다). */
    fun heardStored(c: Context): Set<String> =
        if (prefs(c).getString("heardDate", null) == LocalDate.now().toString()) prefs(c).getStringSet("heardIds", emptySet())!! else emptySet()

    /** 화면·첫 출발 안내의 '대기 중인 메시지' 수: 이번 운행 기준, 오늘 나올 수 있는 것만 센다. 들어 본 반복 메시지(그만 듣기 포함)는 세지 않는다. 재생은 그대로 된다. */
    fun waitingCount(c: Context, except: Set<String> = emptySet()): Int {
        val repeatHeard = prefs(c).getStringSet("repeatHeard", emptySet())!!
        val repeatAsked = prefs(c).getStringSet("repeatAsked", emptySet())!! // 그만 듣기를 고른 메시지는 물어본 메시지에 들어 있다
        return today.count { it.id !in opened && it.id !in heard && it.id !in except && !(it.repeat == "each" && (it.id in repeatHeard || it.id in repeatAsked)) }
    }

    /** quiet: 기록만 하고 화면을 다시 그리지 않는다(5초마다 도는 광장 CPU 기록처럼 화면 상태와 상관없는 줄. 화면 전체를 다시 만들면 광장 장이 밀린다). */
    fun log(msg: String, quiet: Boolean = false) {
        // 줄에 보낸 분 이름이 들어 있다: release에서는 시스템 로그로 내보내지 않는다(화면 안 기록은 시연 도구에서만 보임, 메모리 80줄)
        if (BuildConfig.DEBUG) Log.i("SIM", msg)
        logs.addFirst("${time.format(Date())}  $msg")
        while (logs.size > 80) logs.removeLast()
        if (!quiet) changed()
    }

    fun changed() = listeners.toList().forEach { it() }
    fun listen(l: () -> Unit) { listeners += l }
    fun unlisten(l: () -> Unit) { listeners -= l }

    private fun prefs(c: Context) = c.getSharedPreferences("sim", Context.MODE_PRIVATE)
    /** 앱을 닫아서 이번 운행은 조용히 있는 중. 다음 시동이나 앱을 다시 열면 풀린다. */
    @Volatile var quiet = false
    fun enabled(c: Context) = prefs(c).getBoolean("enabled", false) && !quiet
    fun setEnabled(c: Context, on: Boolean) = prefs(c).edit().putBoolean("enabled", on).apply()
    /** 저사양 모드: 광장을 초당 30장으로, 꾸밈 효과 몇 가지를 끈다(기본 꺼짐 = 60장). */
    fun lowSpec(c: Context) = prefs(c).getBoolean("lowSpec", false)
    fun setLowSpec(c: Context, on: Boolean) = prefs(c).edit().putBoolean("lowSpec", on).apply()
    /** 처음 안내(듣는 방식 고르기)를 끝냈는지. */
    fun onboarded(c: Context) = prefs(c).getBoolean("enabled", false) || prefs(c).getBoolean("onboarded", false)
    fun setOnboarded(c: Context) = prefs(c).edit().putBoolean("onboarded", true).apply()
    fun lastStart(c: Context) = prefs(c).getString("lastStart", null)
    fun setLastStart(c: Context, d: String?) {
        val e = prefs(c).edit().putString("lastStart", d)
        if (d == null) e.remove("occurred").remove("occAt").remove("heardIds") // 첫 출발 상태로 되돌리면 오늘 왔던 순간·들은 기록도 없던 일로
        e.apply()
    }

    // ---------- 순간이 온 메시지(주차 목록 · '못 들은 메시지') ----------
    // 차에만 남긴다: id → {at: 온 시각(ms), d: 온 날, park: 날이 바뀐 뒤 첫 주차를 지났는지, m: 메시지}.
    // 끝까지 듣거나 넘기면 지운다. 날이 바뀌어도 다음 날 첫 주차까지는 남긴다(11/09 결정: 자정에 사라지지 않게). 그 주차가 끝나고 출발하면 지운다.
    private fun occ(c: Context): JSONObject = runCatching { JSONObject(prefs(c).getString("occAt", "{}")!!) }.getOrDefault(JSONObject())
    private fun saveOcc(c: Context, o: JSONObject) = prefs(c).edit().putString("occAt", o.toString()).apply()
    /** 순간이 왔는데 아직 끝까지 못 들은 메시지인가(오늘 것 + 날이 바뀌어 남겨 둔 것). */
    fun occurred(c: Context, id: String) = occ(c).has(id)
    /** 순간이 온 시각(ms). 주차 목록 줄의 '오후 3:12'. */
    fun occurredAt(c: Context, id: String): Long? = occ(c).optJSONObject(id)?.optLong("at", 0L)?.takeIf { it > 0 }
    /** 이번 운행에서 순간이 왔던 메시지(주차할 때 새로 생긴 게 있는지 본다). */
    val occurredThisTrip = mutableSetOf<String>()
    fun markOccurred(c: Context, ids: List<String>) {
        if (ids.isEmpty()) return
        occurredThisTrip += ids
        val o = occ(c); val day = LocalDate.now().toString()
        ids.forEach { id ->
            val e = o.optJSONObject(id)
            // 처음 왔거나, 지난날 왔던 것이 오늘 다시 왔으면 오늘 시각으로(같은 날 두 번째는 처음 시각 그대로)
            if (e == null || e.optString("d") != day) {
                val h = today.firstOrNull { it.id == id }
                o.put(id, JSONObject().put("at", System.currentTimeMillis()).put("d", day).put("m", h?.let { msgJson(it) } ?: e?.opt("m") ?: JSONObject.NULL))
            }
        }
        saveOcc(c, o)
    }
    fun forgetOccurred(c: Context, id: String) { val o = occ(c); if (o.has(id)) { o.remove(id); saveOcc(c, o) } }
    /** 주차했다: 날이 바뀐 뒤 처음 주차한 것으로 표시(지난날 온 것). */
    fun markParkSeen(c: Context) {
        val o = occ(c); val day = LocalDate.now().toString(); var ch = false
        o.keys().asSequence().toList().forEach { k -> o.optJSONObject(k)?.let { e -> if (e.optString("d") < day && !e.optBoolean("park")) { e.put("park", true); ch = true } } }
        if (ch) saveOcc(c, o)
    }
    /** 출발했다: 새 날 첫 주차를 지난 지난날 것과 사흘 넘은 것은 지운다. 지운 id를 돌려준다. */
    fun dropParkSeen(c: Context): List<String> {
        val o = occ(c); val cut = LocalDate.now().minusDays(2).toString()
        val drop = o.keys().asSequence().toList().filter { k -> o.optJSONObject(k)?.let { it.optBoolean("park") || it.optString("d") < cut } ?: true }
        if (drop.isNotEmpty()) { drop.forEach { o.remove(it) }; saveOcc(c, o) }
        return drop
    }
    /** 날이 바뀌어 오늘 목록에 없지만 아직 남겨 둘 메시지(지난날 목록에서 온 것). */
    fun carried(c: Context, day: String): List<Hidden> {
        val o = occ(c)
        return o.keys().asSequence().toList().mapNotNull { k -> o.optJSONObject(k)?.optJSONObject("m")?.let { msgOf(it) } }.filter { (it.day ?: day) < day }
    }
    /** 오늘 목록에서 남긴 사람이 지운 것(같은 날 목록에서 빠짐)은 기록에서도 지운다. */
    fun pruneOccurred(c: Context, day: String, ids: Set<String>) {
        val o = occ(c)
        val drop = o.keys().asSequence().toList().filter { k -> val m = o.optJSONObject(k)?.optJSONObject("m"); m != null && m.optString("day") == day && k !in ids }
        if (drop.isNotEmpty()) { drop.forEach { o.remove(it) }; saveOcc(c, o) }
    }
    fun clearOccurred(c: Context) = prefs(c).edit().remove("occAt").apply()

    private fun msgJson(h: Hidden): JSONObject = JSONObject().put("id", h.id).put("sender", h.sender).put("moment", h.moment).put("audio", h.audioPath)
        .put("invite", h.invite ?: JSONObject.NULL).put("photo", h.photo ?: JSONObject.NULL).put("day", h.day ?: JSONObject.NULL).put("repeat", h.repeat)
        .put("date", h.pickedDate ?: JSONObject.NULL).put("example", h.example)
        .put("place", h.place?.let { JSONObject().put("lat", it.lat).put("lon", it.lon).put("name", it.name) } ?: JSONObject.NULL)
    private fun msgOf(o: JSONObject): Hidden? = runCatching {
        if (o.optBoolean("example")) return null
        Hidden(o.getString("id"), o.optString("sender"), o.optString("moment"), o.optString("audio"), false, false, o.optString("repeat", "once"), o.str("date"),
            placeOf(o.optJSONObject("place")), invite = o.str("invite"), photo = o.str("photo"), day = o.str("day"))
    }.getOrNull()

    /** 듣는 방식: button(버튼 눌러서 듣기, 기본) · auto(버튼 없이 듣기) · arrive(주행 집중 모드: 주행 중엔 알리지 않고 주차하면). 처음 켤 때 고르고 정차 중 바꾼다. */
    fun listenMode(c: Context) = prefs(c).getString("listenMode", "button")!!
    fun setListenMode(c: Context, m: String) = prefs(c).edit().putString("listenMode", m).apply()

    /** 서버에 못 보낸 '다음에도 듣기/그만 듣기'. 다음에 목록을 받을 때 다시 보낸다. 값은 "id:keep". */
    fun queueRepeat(c: Context, id: String, keep: Boolean) =
        prefs(c).edit().putStringSet("repeatUnsent", unsentRepeats(c).filter { !it.startsWith("$id:") }.toSet() + "$id:$keep").apply()
    fun unsentRepeats(c: Context): Set<String> = prefs(c).getStringSet("repeatUnsent", emptySet())!!
    fun clearUnsentRepeat(c: Context, entry: String) =
        prefs(c).edit().putStringSet("repeatUnsent", unsentRepeats(c) - entry).apply()

    /** 반복 메시지를 주차 때 이미 물어봤는지(처음 한 번만 묻는다). */
    fun repeatAsked(c: Context, id: String) = prefs(c).getStringSet("repeatAsked", emptySet())!!.contains(id)
    fun clearRepeatAsked(c: Context) = prefs(c).edit().remove("repeatAsked").remove("repeatHeard").apply() // 시연용 초기화: 들어 본 기록도 함께
    fun setRepeatAsked(c: Context, id: String) = prefs(c).edit().putStringSet("repeatAsked", prefs(c).getStringSet("repeatAsked", emptySet())!! + id).apply()
}
