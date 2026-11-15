package ai.simeodum.car

import android.animation.ValueAnimator
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.StateListDrawable
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.io.File
import java.time.LocalDate
import android.os.SystemClock
import java.util.concurrent.Executors

/**
 * 정차 중 화면(시안 C-01~05). 처음 켜기(켜기 → 권한 → 내 이름 → 핸들 가운데 버튼 연습 → 듣는 방식) → 주차 홈(숨겨진 개수·오늘 들은 메시지·숨길 수 있는 사람)
 * → 도착해서 이어 듣기 → 5초 답장. 주행 최적화를 선언하지 않았으므로 주행 중에는 시스템이 이 화면을 막는다.
 * Pleos 디자인 가이드 대조(10/29): 글자 단계·라이트/다크·가로 넓은 창 두 칸·누름 반응(95% + 배경)·대비 4.5:1·하위 화면 뒤로.
 */
class MainActivity : Activity() {

    /** 가이드 색 토큰(colors): 라이트·다크 두 벌. 회색 basic_00~900(#FFFFFF~#131417)은 다크에서 반전, 보조 글자는 불투명도 64%(63번 2장).
     *  파랑은 버튼·글자에 쓰지 않는다(Pleos 버튼에는 파랑이 없다). 빨강은 끊기·신고·버리기 팝업 버튼에만. */
    private class Palette(private val night: Boolean) {
        private fun c(light: String, dark: String) = Color.parseColor(if (night) dark else light)
        val PAGE = c("#FFFFFF", "#17171C")
        val CARD = c("#F3F3F3", "#1FFFFFFF")       // 회색 면: 카드·보조 버튼(다크: 흰색 12%)
        val CARD_DOWN = c("#E7E7E7", "#33FFFFFF")  // 눌렀을 때
        val LINE = c("#E0E1E6", "#3A3B40")         // 선 1px·막대 바탕
        val INK = c("#131417", "#FFFFFF")          // 글자: 본문·제목
        val SUB = c("#68696B", "#A3A3A5")          // 보조 글자: #131417의 64%(다크: 흰색 64%)
        val INK84 = c("#393A3C", "#D9D9D9")        // 84%: 대기 개수 윗줄 한 곳에만
        val LIST_BG = c("#F7F8FA", "#17171C")      // 들은 메시지 목록 바탕(흰 묶음 카드가 위에 놓인다)
        // 주 버튼: 진회색 + 흰 글자(Pleos 팝업 버튼). 다크에서 눌림은 밝게
        val PRIMARY = Color.parseColor("#44464E")
        val PRIMARY_DOWN = c("#313236", "#686A72")
        val ON_INK = Color.WHITE                   // 주 버튼 위 글자
        val SWITCH_ON = Color.parseColor("#02C265") // Pleos switch_on = informative_active
        val TRACK_OFF = c("#E0E1E6", "#4A4B50")    // 꺼진 스위치
        val CHECK = SWITCH_ON                      // 고른 칸 ✓(Pleos 선택 표시 값)
        // 되돌릴 수 없는 동작(끊기·신고·버리기) 팝업 버튼. 흰 글자 대비 5.0:1
        val RED = Color.parseColor("#D91F2E")
        val RED_DOWN = Color.parseColor("#B81926")
        val POPUP = c("#FFFFFF", "#313236")        // 가운데 팝업·광장 패널 면(밤: #313236)
        val DIM = c("#80000000", "#99000000")      // 팝업 뒤 어둡게
        val TOAST = Color.parseColor("#38393B")    // 아래 토스트: #38393B + 흰 글자
    }

    // 가이드 글자 단계(typography): Headline 60/56/48, Title 40/36/32, Body 30/28/26, Label 24/20
    // 쓰는 곳(63번 2장): 개수 60 · 머리줄 제목 36 · 본문·버튼 28 · 토스트 26 · 라벨 24. 굵기 700(개수 숫자·패널 이름·팝업 제목) / 600(제목 줄·버튼) / 400(목록·설명·시각·입구)
    private object T {
        const val HEAD_L = 60f; const val HEAD_M = 56f; const val HEAD_S = 48f
        const val TITLE_L = 40f; const val TITLE = 36f; const val TITLE_S = 32f
        const val BODY = 28f; const val BODY_S = 26f
        const val LABEL = 24f; const val LABEL_S = 24f
        const val W4 = 400; const val W6 = 600; const val W7 = 700
        /** Pleos 표의 줄 높이(크기 → 줄 높이). */
        val LINE = mapOf(60f to 80f, 56f to 72f, 48f to 64f, 40f to 52f, 36f to 44f, 32f to 40f, 30f to 38f, 28f to 36f, 26f to 34f, 24f to 28f, 20f to 24f)
    }

    private companion object {
        /** 화면을 다시 만들 때 넘겨줄 메시지(같은 프로세스 안에서만). 지난 메시지처럼 오늘 목록에 없는 것도 그 화면으로 돌아오게. */
        val held = mutableMapOf<String, Hidden>()
    }

    private lateinit var C: Palette
    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()
    private lateinit var body: LinearLayout
    private lateinit var headerBox: FrameLayout
    /** 한꺼번에 여러 번 바뀌어도(기록 여러 줄 등) 화면은 한 번만 다시 만든다(매번 화면 전체를 새로 만들어 광장 장이 밀리던 것). */
    private var renderQueued = false
    private val onChange: () -> Unit = { if (!renderQueued) { renderQueued = true; main.post { renderQueued = false; render() } } }
    private val answered = mutableMapOf<String, String>() // 메시지 id → 답장 상태
    private var onboardStep = 0      // 0: 켜기, 1: 권한 안내, 2: 내 이름, 3: 핸들 가운데 버튼 연습, 4: 듣는 방식 고르기
    private var settingsOpen = false
    /** 설정에서 연 하위 화면: 들은 메시지 · 듣는 방식 고르기 · 권한 · 웹 문서(개인정보 처리방침·이용약관). */
    private var heardOpen = false
    private var modeOpen = false
    private var permOpen = false
    private var webOpen: Pair<String, String>? = null   // (제목, 경로)
    /** '다음에도 들으시겠습니까?' 알림으로 열었으면 하나 고를 때마다 다음 반복 메시지로 넘어간다. */
    private var repeatFlow = false
    /** 들은 메시지 화면 맨 위에 띄운 '다음에도 들을지' 카드(화면을 떠나면 비운다). */
    private val askOnHeard = linkedSetOf<String>()
    /** 남긴 사람이 지운 메시지(답장이 '없는 메시지'로 거절됨). 답장·다시 듣기를 숨긴다. */
    private val goneIds = mutableSetOf<String>()
    /** 들은 메시지 화면의 지난 메시지 id(오늘 목록에 없어도 지워진 것으로 보지 않게). */
    private val pastIds = mutableSetOf<String>()
    /** 답장을 못 보냈을 때 확인 화면에 남기는 이유 한 줄. */
    private var sendError: String? = null
    /** 답장 녹음 전 3·2·1(첫마디가 잘리지 않게). 0이면 녹음 중. */
    private var replyPrep = 0
    /** 출발하면 하던 화면을 접어 두고, 몇 분 안에 다시 주차하면 되살린다. */
    private class Snap(val at: Long, val settings: Boolean, val heard: Boolean, val family: Boolean, val examples: Boolean, val mode: Boolean, val perm: Boolean, val after: Hidden?, val droppedReply: Boolean)
    private var snap: Snap? = null
    private var wasDriving = false
    private val RESTORE_MS = 10 * 60_000L
    private var devTaps = 0
    private var logOpen = false
    private var inviteOpen = false
    private var familyOpen = false
    /** '예시 메시지' 목록(주차 홈 버튼·설정에서). 뒤로 가면 연 곳으로 돌아간다. */
    private var examplesOpen = false
    private var afterOf: Hidden? = null       // 다 들은 뒤 답장 화면
    private var lastPlaying: Hidden? = null   // 방금까지 재생하던 목소리(끝나면 답장 화면으로)
    private var lastPlayingAt = 0L            // 재생 화면을 마지막으로 그린 때(오래전에 들은 것으로 답장 화면이 뜨지 않게)
    /** 열림 연출(1.4초)은 목소리마다 한 번만. 다시 그릴 땐 끝 장면으로. */
    private val openingShown = mutableSetOf<String>()
    private var replying: Hidden? = null
    /** 설정의 '지난 메시지': 보관 기간 안에서 오늘 전에 들은 것과 들은 날. 설정을 열 때 한 번 받는다. */
    private var past: List<Pair<Hidden, String>>? = null
    private var pastFailed = false
    private var pastLoading = false   // 받는 중이면 다시 그려도 또 요청하지 않는다
    /** 마이크 권한을 묻는 동안 답장하려던 메시지. 허용하면 바로 녹음을 시작한다. */
    private var replyAfterPermission: Hidden? = null
    /** 녹음을 마친 답장: 보내기 전에 들어 보고 보낼지 정한다(정차 중에만). */
    private var review: Hidden? = null
    private var reviewFile: File? = null
    private var preview: MediaPlayer? = null
    /** 이번에 고른 반복 듣기(서버 값이 오기 전에도 화면이 바로 바뀌게). true: 다음에도 듣기. */
    private val repeatKeep = mutableMapOf<String, Boolean>()
    /** 가운데 팝업(Pleos system-popup Medium): 되돌릴 수 없는 일만 묻는다. ok는 끝나면 done()을 불러 팝업을 닫는다. */
    private class Ask(val title: String, val body: String?, val ok: String, val danger: Boolean, val run: (done: () -> Unit) -> Unit)
    private var ask: Ask? = null
    /** 가운데 팝업 메뉴(사람 줄을 누르면): 제목 + 세로 버튼 + [닫기]. 고르면 메뉴를 닫고 그 일을 한다(되돌릴 수 없는 일은 다시 묻는다). */
    private class Menu(val title: String, val items: List<Pair<String, () -> Unit>>)
    private var menu: Menu? = null
    private var askBusy = false   // 팝업 버튼이 서버 답을 기다리는 중(로딩, 다시 누름 막기)
    private lateinit var overlay: FrameLayout
    private lateinit var toastView: TextView
    /** 결과 한 줄(아래 토스트, 3초). */
    private val hideToast = Runnable { toastView.visibility = View.GONE }
    /** 서버를 부르는 버튼의 로딩 상태(다시 누르면 같은 요청이 여러 번 가지 않게). */
    private var inviteBusy = false
    private var sending = false
    private var invitesLoading = false
    private var replyLeft = 5
    private var recorder: MediaRecorder? = null
    private var loudest = 0
    private val levels = ArrayDeque<Float>()
    // 재생·녹음 중에 다시 그리지 않고 갱신만 하는 뷰
    private var bar: Bar? = null
    private var previewBar: Bar? = null
    private var web: android.webkit.WebView? = null
    private var webFailed = false
    private var webHttpFail = false   // 인터넷은 되는데 문서가 없음(서버 오류)
    private var timeNow: TextView? = null
    private var timeAll: TextView? = null
    private var countView: TextView? = null
    private var wave: Wave? = null

    private val Int.dp get() = (this * resources.displayMetrics.density).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Api.init(this)
        // 야간(다크) 모드면 다크 색 세트. 모드가 바뀌면 시스템이 화면을 다시 만든다.
        C = Palette((resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES)
        window.decorView.setBackgroundColor(C.PAGE)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(C.PAGE) }
        headerBox = FrameLayout(this)
        root.addView(headerBox)
        body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32.dp, 28.dp, 32.dp, 40.dp) }
        // 본문 칸: 뒤에 광장(3D, 화면을 다시 그려도 그대로 두는 층) + 앞에 본문(광장 화면에서는 투명한 무대·띠·패널)
        val content = FrameLayout(this)
        plazaHost = FrameLayout(this).apply { visibility = View.GONE }
        content.addView(plazaHost, FrameLayout.LayoutParams(-1, -1))
        content.addView(ScrollView(this).apply { addView(body); isFillViewport = true }, FrameLayout.LayoutParams(-1, -1))
        root.addView(content, LinearLayout.LayoutParams(-1, 0, 1f))
        // 화면 위에 얹는 층: 가운데 팝업(뒤는 어둡게)과 아래 토스트
        val stack = FrameLayout(this)
        stack.addView(root, FrameLayout.LayoutParams(-1, -1))
        overlay = FrameLayout(this).apply { visibility = View.GONE }
        stack.addView(overlay, FrameLayout.LayoutParams(-1, -1))
        // 토스트(Pleos toast): 아래 가운데, 바깥 24 · 안쪽 좌우 40 위아래 24, 최대 폭 792, 2줄까지
        toastView = text("", T.BODY_S, Color.WHITE, center = true).apply {
            visibility = View.GONE; maxLines = 2; ellipsize = android.text.TextUtils.TruncateAt.END
            maxWidth = 792.dp; setPadding(40.dp, 24.dp, 40.dp, 24.dp); elevation = 20.dp.toFloat()
            background = GradientDrawable().apply { setColor(C.TOAST); cornerRadius = 16.dp.toFloat() }
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        stack.addView(toastView, FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply { setMargins(24.dp, 0, 24.dp, 24.dp) })
        setContentView(stack)
        restoreState(savedInstanceState)
        watchRestrictions()
        Hub.quiet = false   // 앱을 다시 열면 이번 운행도 다시 들려준다
        openHeard(intent)
        if (Hub.onboarded(this)) { Hub.setEnabled(this, true); startForegroundService(Intent(this, CarService::class.java)) }
        forwardTestCommand(intent)
    }

    /** 낮·밤 전환 등으로 화면이 다시 만들어져도(색을 만들 때 정하므로 다시 만드는 쪽을 둔다) 하던 단계·화면으로 돌아온다. */
    /** 창 크기·방향이 바뀌었다(Pleos 1:1 세로 ↔ 가로): 같은 화면에서 배치만 다시 그린다. 광장(3D)은 그대로 이어서 돈다. */
    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        Hub.log("창 크기 바뀜 → ${newConfig.screenWidthDp}×${newConfig.screenHeightDp}dp")
        render()
    }

    override fun onSaveInstanceState(out: Bundle) {
        super.onSaveInstanceState(out)
        out.putInt("onboardStep", onboardStep)
        out.putBooleanArray("open", booleanArrayOf(settingsOpen, heardOpen, familyOpen, examplesOpen, modeOpen, permOpen, inviteOpen, ownerEditing, inviteAfterName))
        ownerDraft?.let { out.putString("ownerDraft", it) }
        webOpen?.let { out.putStringArray("webOpen", arrayOf(it.first, it.second)) }
        afterOf?.let { held[it.id] = it; out.putString("afterOf", it.id) }
        lastPlaying?.let { held[it.id] = it; out.putString("lastPlaying", it.id); out.putLong("lastPlayingAt", lastPlayingAt) }
        review?.let { h -> held[h.id] = h; out.putString("review", h.id); reviewFile?.let { out.putString("reviewFile", it.path) } }
    }

    private fun restoreState(b: Bundle?) {
        b ?: return
        onboardStep = b.getInt("onboardStep", onboardStep)
        b.getBooleanArray("open")?.takeIf { it.size >= 9 }?.let { o ->
            settingsOpen = o[0]; heardOpen = o[1]; familyOpen = o[2]; examplesOpen = o[3]; modeOpen = o[4]; permOpen = o[5]; inviteOpen = o[6]; ownerEditing = o[7]; inviteAfterName = o[8]
        }
        ownerDraft = b.getString("ownerDraft")
        b.getStringArray("webOpen")?.takeIf { it.size == 2 }?.let { webOpen = it[0] to it[1] }
        afterOf = b.getString("afterOf")?.let(::findMsg)
        lastPlaying = b.getString("lastPlaying")?.let(::findMsg); lastPlayingAt = b.getLong("lastPlayingAt", 0L)
        // 녹음해 둔 답장(보내기 전)은 파일이 남아 있으면 그대로 다시 들어 보고 보낼 수 있게
        val rf = b.getString("reviewFile")?.let { File(it) }?.takeIf { it.exists() }
        val rv = b.getString("review")?.let(::findMsg)
        if (rv != null && rf != null) { review = rv; reviewFile = rf }
    }

    /** 다시 만들어진 화면이 메시지를 다시 찾는다: 오늘 목록·날이 바뀌어 빠진 들은 것·예시·직전 화면이 들고 있던 것. */
    private fun findMsg(id: String): Hidden? = Hub.today.firstOrNull { it.id == id } ?: Hub.retired.firstOrNull { it.id == id }
        ?: Demo.examples().firstOrNull { it.id == id } ?: held[id]

    override fun onDestroy() {
        // 다시 만들어질 때마다 차 연결·주행 규제 감시가 쌓이지 않게 푼다
        runCatching { uxm?.unregisterListener() }; uxm = null
        runCatching { carConn?.disconnect() }; carConn = null
        stopPractice(); practiceWheel?.close("화면 끝"); stopPreview()
        main.removeCallbacksAndMessages(null)
        web?.destroy(); web = null
        plaza?.destroy(); plaza = null
        super.onDestroy()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent); if (BuildConfig.DEBUG && intent.getStringExtra("cmd") != null) skipGreet = true   // 시험 명령으로 다시 열린 건 '다시 보임' 인사(모두 손 흔들기)를 건너뜀
        forwardTestCommand(intent)
        if (openHeard(intent)) render()
    }

    /** 주차 알림을 누르면 들은 메시지가 있는 화면으로 간다. 답장과 다음에도 듣기는 거기서 한다. */
    private fun openHeard(i: Intent?): Boolean {
        val open = i?.getStringExtra("open") ?: return false
        i.removeExtra("open")
        familyOpen = false; examplesOpen = false; settingsOpen = false; modeOpen = false; permOpen = false; webOpen = null
        // 주차 알림은 한 장(들은 메시지). 다음에도 들을지는 그 화면 맨 위 카드로 묻는다. 예전 '다음에도 듣기' 알림(open=repeat)도 같은 곳으로
        Hub.log("주차 알림($open) → 들은 메시지")
        heardOpen = true; afterOf = null; repeatFlow = false
        return true
    }

    /** 케이스 테스트 명령을 서비스로 넘긴다 (서비스는 외부에 열지 않는다). */
    private fun forwardTestCommand(i: Intent?) {
        // 맥 서버 개발 빌드, 또는 시연 도구를 켠 차에서만(클라우드 심사용 APK에 밖에서 명령이 들어오지 않게)
        if (!BuildConfig.DEBUG || i?.getStringExtra("cmd") == null || !(Api.BASE.contains("10.0.2.2") || devOn())) return
        startForegroundService(Intent(this, CarService::class.java).putExtras(i))
    }

    override fun onResume() {
        super.onResume(); Hub.rollDay(); Hub.visible = true; Hub.listen(onChange); Hub.service?.refresh(); loadInvites(); Plaza.load(this, force = true)
        // 앱 설정에서 속도·위치를 허용하고 돌아왔으면 대기 서비스가 구독을 다시 건다
        val missing = carPermsMissing()
        if (permsSeen != null && missing != permsSeen) Hub.service?.resubscribe()
        permsSeen = missing
        render(); main.post(ticker)
    }
    private var permsSeen: List<String>? = null

    private var newLink: String? = null   // 방금 만든 초대 링크(카드로 보여 줌)
    private var newLinkFor: String? = null   // 다시 연결로 만든 링크면 그 사람 이름
    private var scrollToLink = false         // 링크 카드를 막 띄웠으면 그 자리까지 내린다
    private var shownInvite: String? = null  // 사람 화면에서 다시 펼쳐 본 연결 전 링크
    private var inviteError = false
    private var invitesChecked = false    // 서버에 물어본 뒤에만 첫날 버튼을 판단한다(켤 때 깜빡임 방지)

    private fun loadInvites() {
        if (invitesLoading) return
        invitesLoading = true
        io.execute {
            val r = runCatching { Api.invites() }
            // 사람 화면·메시지 화면의 사진을 받아 두고, 목록에 없는 사진(지움·바꿈·끊음)은 차에서도 지운다
            r.getOrNull()?.let { list -> list.forEach { runCatching { Store.fetchPhoto(this, it.code, it.photo) } }; runCatching { Store.keepPhotos(this, list) }; runCatching { Store.syncBusts(this, list) } }
            main.post { Hub.invites = r.getOrNull(); invitesChecked = true; invitesLoading = false; if (r.isSuccess) Plaza.load(this, force = true); render() }
        }
    }

    /** 연결된 사람이 없는 첫날. 체험 중이면 예시뿐이라 아무도 없는 것. 서버를 모르면(invites == null) 오늘 메시지로 판단한다. */
    private fun noOneYet(): Boolean {
        val invites = Hub.invites
        return invitesChecked && (Hub.demo || if (invites != null) invites.isEmpty() else Hub.today.isEmpty())
    }

    /** 결과 한 줄을 화면 아래 토스트로 3초(Pleos toast). 주행 중에는 띄우지 않는다. */
    private fun toast(s: String) {
        if (driving()) return
        toastView.text = s; toastView.visibility = View.VISIBLE
        main.removeCallbacks(hideToast); main.postDelayed(hideToast, 3000)
    }

    /** 가운데 팝업으로 묻는다. */
    private fun confirm(title: String, body: String?, ok: String, danger: Boolean = true, run: (done: () -> Unit) -> Unit) {
        ask = Ask(title, body, ok, danger, run); askBusy = false; render()
    }
    private fun closeAsk() { ask = null; askBusy = false; render() }
    private fun closeMenu() { menu = null; render() }

    /** 첫날 버튼: 사람 화면을 연다. 초대장에 쓸 내 이름이 있으면 그 자리에서 링크까지 만들고, 없으면 이름부터 받는다. */
    private fun inviteFirst() {
        familyOpen = true; newLink = null; newLinkFor = null; inviteError = false
        if (ownerName().isEmpty()) { ownerEditing = true; inviteAfterName = true; ownerDraft = ""; inviteOpen = false; render(); return }
        inviteOpen = true; render()
        makeInvite()
    }

    /** 운전자 이름(예: 홍길동). 초대장에 '홍길동님 차'로 보인다(서버의 from). 관계 호칭(아빠·여보)은 받지 않는다. */
    private fun ownerName(): String = prefs().getString("ownerName", "") ?: ""
    private fun cleanName(s: String) = s.trim().removeSuffix("님").trim().take(10)
    private var ownerEditing = false
    private var inviteAfterName = false   // 이름을 정하면 바로 링크를 만든다([초대 링크 만들기]를 이름 없이 눌렀을 때)
    private var ownerDraft: String? = null   // 다시 그려도 쓰던 이름이 남게

    /** 사람 화면: 내 이름 한 줄(초대장에 '○○님 차'로 쓰인다. 누르면 그 자리에서 고친다). */
    private fun ownerRow(v: LinearLayout) {
        if (!ownerEditing) {
            v.addView(navRow("내 이름", ownerName().ifEmpty { "정하기" }) { ownerEditing = true; ownerDraft = ownerName(); render() }, full().apply { bottomMargin = 24.dp })
            return
        }
        v.addView(section("초대장에 쓸 내 이름", top = 12))
        val input = android.widget.EditText(this).apply {
            setText(ownerDraft ?: ownerName()); hint = "예: 홍길동"; setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, T.BODY); setTextColor(C.INK); setHintTextColor(C.SUB)
            filters = arrayOf(android.text.InputFilter.LengthFilter(10)); isSingleLine = true
            // 가로 화면에서 키보드가 화면 전체를 덮지 않게(쓰는 칸과 버튼이 그대로 보이게)
            imeOptions = android.view.inputmethod.EditorInfo.IME_ACTION_DONE or android.view.inputmethod.EditorInfo.IME_FLAG_NO_EXTRACT_UI or android.view.inputmethod.EditorInfo.IME_FLAG_NO_FULLSCREEN
            setOnEditorActionListener { _, a, _ -> if (a == android.view.inputmethod.EditorInfo.IME_ACTION_DONE) { saveOwner(); true } else false }
            setPadding(28.dp, 0, 28.dp, 0); minHeight = 96.dp; background = box(C.CARD, C.LINE)
            addTextChangedListener(object : android.text.TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun afterTextChanged(s: android.text.Editable?) { ownerDraft = s?.toString() ?: "" }
            })
        }
        v.addView(input, full().apply { bottomMargin = 16.dp })
        v.addView(btnRow(primary(if (inviteAfterName) "코드 만들기" else "저장") { saveOwner() },
            outline("닫기") { ownerEditing = false; inviteAfterName = false; ownerDraft = null; keyboard(input, false); render() }), full().apply { bottomMargin = 24.dp })
        // 다시 그려도 쓰던 칸에 그대로 이어 쓴다
        input.post { input.requestFocus(); input.setSelection(input.text.length); keyboard(input, true) }
    }

    private fun keyboard(v: View, show: Boolean) {
        val im = getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        if (show) im.showSoftInput(v, 0) else im.hideSoftInputFromWindow(v.windowToken, 0)
    }

    private fun saveOwner() {
        val n = cleanName(ownerDraft ?: "")
        if (n.isEmpty()) { toast("이름을 입력해 주세요"); return }
        prefs().edit().putString("ownerName", n).apply()
        currentFocus?.let { keyboard(it, false) }
        ownerEditing = false; ownerDraft = null
        val go = inviteAfterName; inviteAfterName = false
        render()
        if (go) makeInvite()
    }

    private fun makeInvite() {
        if (inviteBusy) return   // 답이 오기 전에 또 누르면 링크가 여러 개 생긴다
        inviteBusy = true; render()
        io.execute {
            val from = ownerName().ifEmpty { null }
            val r = runCatching { Api.createInvite(from) }
            main.post {
                inviteBusy = false; newLinkFor = null
                r.onSuccess { code -> newLink = Api.inviteLink(code); inviteError = false; scrollToLink = true; Hub.log("초대 링크 만듦: $code"); loadInvites() }
                 .onFailure { inviteError = true; newLink = null; Hub.log("초대 링크 못 만듦: ${it.message}") }
                inviteOpen = true; render()
            }
        }
    }

    private fun revoke(inv: Invite, done: () -> Unit) = io.execute {
        val r = runCatching { Api.revokeInvite(inv.code) }
        main.post {
            Hub.log(if (r.isSuccess) "초대 링크 끊음: ${inv.name ?: inv.code}" else "끊기 실패: ${r.exceptionOrNull()?.message}")
            // 방금 만든 링크를 끊었으면 링크 카드도 내린다
            if (r.isSuccess && newLink?.endsWith("=${inv.code}") == true) { newLink = null; inviteOpen = false }
            done()
            toast(if (r.isSuccess) (if (inv.name != null) "${nim(inv.name!!)} 연결을 끊었습니다" else "초대 코드를 끊었습니다") else "인터넷에 연결되지 않아 끊지 못했습니다")
            loadInvites()
        }
    }
    /** 폰을 바꾼 사람: 같은 사람으로 새 링크를 만든다(이름·사진·메시지·답장은 그대로, 쓰던 링크는 끊긴다). */
    private fun askReissue(inv: Invite) {
        val who = nim(inv.name ?: return)
        confirm("$who 새 폰으로 다시 연결", "쓰던 코드는 끊고 새 코드를 만듭니다", "새 코드 만들기", danger = false) { done -> reissue(inv, done) }
    }

    private fun reissue(inv: Invite, done: () -> Unit) = io.execute {
        val r = runCatching { Api.reissueInvite(inv.code, ownerName().ifEmpty { null }) }
        main.post {
            Hub.log(if (r.isSuccess) "다시 연결 링크 만듦: ${inv.name}" else "다시 연결 실패: ${r.exceptionOrNull()?.message}")
            r.onSuccess { code -> newLink = Api.inviteLink(code); newLinkFor = inv.name; inviteError = false; inviteOpen = true; shownInvite = null; scrollToLink = true }
            done()
            // 된 경우는 내려오는 '○○님 새 폰에 보낼 코드' 카드가 알려 준다
            if (!r.isSuccess) toast("인터넷에 연결되지 않아 만들지 못했습니다")
            loadInvites()
        }
    }

    override fun onPause() { if (replying != null) { Hub.log("답장 녹음 중 화면을 떠나 취소"); cancelReply() }; stopPreview(); stopPractice(); plaza?.setActive(false); plazaIdle = false; Hub.visible = false; Hub.unlisten(onChange); main.removeCallbacks(ticker); super.onPause() }

    /** 듣는 중 멈춤(화면 멈춤 버튼·뒤로). 처음 듣던 메시지는 홈으로, 다시 듣던 것은 그 메시지 화면으로 돌아간다. */
    private fun stopPlaying(why: String) {
        val h = Hub.nowPlaying
        Hub.service?.stopListening(why)
        if (h != null && h.id !in Hub.heard) lastPlaying = null
        if (h?.example == true) endDemoTour()   // 예시 가족 체험(C13) 중 멈추면 원래 화면으로
        render()
    }

    /** 뒤로(CCP Back 포함): 하위 화면이면 이전 화면으로, 홈이면 앱을 숨긴다. */
    @Deprecated("Activity 기본 뒤로 처리")
    override fun onBackPressed() {
        when {
            // 팝업이 떠 있으면 팝업만 닫는다(서버 답을 기다리는 중엔 그대로)
            ask != null -> if (!askBusy) closeAsk()
            menu != null -> closeMenu()
            replying != null -> cancelReply()
            review != null -> if (!sending) askDiscardReview()
            Hub.nowPlaying != null -> stopPlaying("뒤로")
            // 광장 도착 패널에는 [나중에]가 없다: 뒤로가 그 일을 한다(예전 도착 화면의 [나중에]와 같다)
            Hub.offered != null && !driving() && plaza != null -> Hub.service?.later()
            familyOpen -> { familyOpen = false; inviteOpen = false; ownerEditing = false; inviteAfterName = false; ownerDraft = null; render() }
            afterOf != null -> { afterOf = null; repeatFlow = false; render() }
            examplesOpen -> { examplesOpen = false; render() }
            webOpen != null -> { webOpen = null; web?.destroy(); web = null; render() }
            permOpen -> { permOpen = false; render() }
            modeOpen -> { modeOpen = false; render() }
            heardOpen -> { heardOpen = false; askOnHeard.clear(); if (!pastLoading) past = null; render() }
            orderOpen -> { if (!orderBusy) { orderOpen = false; orderDraft = null; render() } }
            settingsOpen -> { settingsOpen = false; logOpen = false; devTaps = 0; render() }
            inviteOpen -> { inviteOpen = false; render() }
            // 광장 위 카드·들은 뒤 패널(광장 화면에서만 보인다)
            demoPlaza != null -> { endDemoTour(); render() }
            plazaCard != 0 -> { plazaCard = 0; render() }
            plazaAfter != null -> { plazaAfter = null; render() }
            // 처음 켜기: 한 단계 앞으로(권한이 이미 다 있어 건너뛴 안내는 다시 보이지 않는다)
            !Hub.onboarded(this) && onboardStep > 0 -> {
                onboardStep = when (onboardStep) { 2 -> if (carPermsMissing().isEmpty() && !notifMissing()) 0 else 1; else -> onboardStep - 1 }
                currentFocus?.let { keyboard(it, false) }
                render()
            }
            else -> moveTaskToBack(true)
        }
    }

    // ---------- 화면 고르기 ----------

    /** 한 칸 폭(가로로 넓은 창이면 최대 840dp 기둥을 창 가운데에, 세로·1:1 창이면 꽉 차게. 11/15: 왼쪽에 붙이면 오른쪽 절반이 비어 미완성처럼 보여 가운데로. 칸 안 목록은 왼쪽 정렬 그대로). */
    /** span: 가로 창에서도 840 기둥으로 줄이지 않고 창 폭 전체(광장 화면: 왼쪽 광장 + 오른쪽 정보 기둥, C1). */
    private fun column(fill: Boolean = false, span: Boolean = false): LinearLayout {
        val w = resources.configuration.screenWidthDp
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val holder = LinearLayout(this).apply { gravity = Gravity.CENTER_HORIZONTAL }
        val narrowCol = w >= 1000 && !span
        holder.addView(col, LinearLayout.LayoutParams(if (narrowCol) 840.dp else -1, if (fill) -1 else -2))
        // fill: 창 높이를 꽉 채워 주인공(눈금)을 세로 가운데에, 입구 줄을 맨 아래에 둔다
        body.addView(holder, if (fill) LinearLayout.LayoutParams(-1, 0, 1f) else full())
        return col
    }

    private fun grow() = View(this).apply { layoutParams = LinearLayout.LayoutParams(1, 0, 1f) }

    /**
     * 화면을 쓸 수 있는지(정차) / 막는지(주행). 11/08 C3: 기어 P 대신 플랫폼 주행 규제 상태(CarUxRestrictions)를 따른다.
     * requiresDistractionOptimization == false 면 정차. 한국(북미 외)은 시속 5km 이하 + P·주차 브레이크·오토홀드면 플랫폼이 풀어 준다(Pleos 지역별 주행 규제 정책).
     * 플랫폼 값을 못 받으면(차 서비스 없음·예외) 예전처럼 기어 P로 대신한다. 소리를 낼지(순간·재생 판단)는 CarService가 여전히 기어로 정한다: 이건 화면만.
     */
    private var restricted = false
    private var uxKnown = false   // 플랫폼 값을 한 번이라도 받았는지
    private var carConn: android.car.Car? = null
    private var uxm: android.car.drivingstate.CarUxRestrictionsManager? = null
    private fun driving() = if (uxKnown) restricted else Hub.driving
    /** 정차 중에만 하는 일(답장 녹음·다음에도 듣기·신고·반응)을 열지. 플랫폼 값이 없으면 기어 P(기어를 모르면 닫음). */
    private fun stopped() = if (uxKnown) !restricted else Hub.parked
    private fun watchRestrictions() {
        runCatching {
            val c = android.car.Car.createCar(this).also { carConn = it }
            val um = c.getCarManager(android.car.Car.CAR_UX_RESTRICTION_SERVICE) as android.car.drivingstate.CarUxRestrictionsManager
            uxm = um
            restricted = um.currentCarUxRestrictions.isRequiresDistractionOptimization
            uxKnown = true
            um.registerListener { r -> main.post { val was = restricted; restricted = r.isRequiresDistractionOptimization; uxKnown = true; if (was != restricted) Hub.log("주행 규제 → ${if (restricted) "켜짐(주행)" else "풀림(정차)"}"); render() } }
            Hub.log("화면 기준: 플랫폼 주행 규제 상태(${if (restricted) "주행" else "정차"})")
        }.onFailure { uxKnown = false; Hub.log("주행 규제 상태를 못 받아 기어 P로 화면을 엶: $it") }
    }

    private fun render() {
        val d = driving()
        if (d != wasDriving) {
            wasDriving = d
            if (d) {
                Hub.service?.stopReplay()   // 기어 P가 아닌 정차(오토홀드 등)에서 시작한 다시 듣기도 주행이 되면 끝낸다(C3)
                endDemoTour()
                lastPlaying = null   // 새 운행: 지난번에 듣던 것으로 주차 때 답장 화면이 뜨지 않게
                // 출발: 열려 있던 화면을 접어 둔다(녹음하던 답장은 버리지만, 그 메시지 화면은 되살린다)
                val s = Snap(System.currentTimeMillis(), settingsOpen, heardOpen, familyOpen, examplesOpen, modeOpen, permOpen,
                    replying ?: review ?: afterOf, replying != null || review != null)
                snap = s.takeIf { it.settings || it.heard || it.family || it.examples || it.mode || it.perm || it.after != null }
            } else snap?.let { s ->
                snap = null
                // 몇 분 안에 다시 주차했으면 마지막 화면으로 돌려놓는다
                if (System.currentTimeMillis() - s.at <= RESTORE_MS && Hub.onboarded(this)) {
                    settingsOpen = s.settings; heardOpen = s.heard; familyOpen = s.family; examplesOpen = s.examples; modeOpen = s.mode; permOpen = s.perm
                    afterOf = s.after
                    if (s.droppedReply) main.post { toast("녹음하던 답장은 보내지 않았습니다") }
                }
            }
        }
        if (driving() && replying != null) { cancelReply(); return }
        if (driving() && review != null) { Hub.log("주행 중이라 녹음한 답장 버림"); discardReview(); return }
        if (driving()) {
            settingsOpen = false; familyOpen = false; examplesOpen = false; inviteOpen = false; afterOf = null
            heardOpen = false; modeOpen = false; permOpen = false; repeatFlow = false; askOnHeard.clear()
            orderOpen = false; orderDraft = null; plazaCard = 0; plazaAfter = null
            if (webOpen != null) { webOpen = null; web?.destroy(); web = null }
            // 묻던 팝업·결과 토스트도 닫는다(주행 중 화면은 듣기 하나만). 서버 답을 기다리던 것은 끝까지 가고 결과만 안 보인다
            if (ask != null) { ask = null; askBusy = false }
            menu = null
            main.removeCallbacks(hideToast); toastView.visibility = View.GONE
        }
        // 멈춘 뒤 결과 한 줄(핸들 버튼·알림 [멈추기]로 멈춰도 같은 토스트)
        Hub.stopNote?.let { n -> Hub.stopNote = null; main.post { toast(n) } }
        // 연습 화면을 떠나면(출발·다음 단계·뒤로) 핸들 버튼 받기와 예시 재생을 끝낸다
        if (driving() || Hub.onboarded(this) || onboardStep != 3) stopPractice()
        web?.let { (it.parent as? ViewGroup)?.removeView(it) }   // 웹 문서는 다시 그려도 새로 불러오지 않는다
        body.removeAllViews()
        bar = null; previewBar = null; timeNow = null; timeAll = null; countView = null; wave = null
        panelBars = null; panelNow = null; panelAll = null
        // 재생이 막 끝났으면(들음으로 기록됨) 그 자리에서 답장 화면. 머리줄보다 먼저 정해야 한 번이라도 '도담도담'이 안 뜬다(아래 when에서 앞 줄이 먼저 잡는 경우는 그대로 둔다)
        if (!driving() && Hub.onboarded(this) && replying == null && review == null && Hub.nowPlaying == null && Hub.offered == null &&
            lastPlaying != null && lastPlaying!!.id in Hub.heard && Hub.arrivalLeft == 0) {
            // 방금 화면에서 듣던 것만(오래전에 듣고 화면을 떠났으면 그냥 홈)
            // 광장에서 들었으면 광장 패널이 '들은 뒤'로 바뀐다. 들은 메시지 화면에서 다시 들은 것은 그 화면으로
            if (System.currentTimeMillis() - lastPlayingAt <= RESTORE_MS) { if (replayToAfter || !plazaOk()) afterOf = lastPlaying else plazaAfter = lastPlaying }
            lastPlaying = null; replayToAfter = false
        }
        popup()
        // 풍경 화면은 그림이 칸 끝까지(여백 없음), 나머지는 기본 여백
        val scene = Hub.onboarded(this) && replying == null && review == null && !settingsOpen && !familyOpen && !examplesOpen && !heardOpen && !modeOpen && !permOpen && !orderOpen && webOpen == null
        plazaOnScreen = false
        plazaGround = null
        if (scene) body.setPadding(0, 0, 0, 0) else body.setPadding(32.dp, 28.dp, 32.dp, 40.dp)
        body.setBackgroundColor(Color.TRANSPARENT)   // 들은 메시지 목록만 heardScreen 이 옅은 회색으로 칠한다
        when {
            // 처음 켜기 전 주행: 막힘 문장은 하나만 배우면 되게 확정 문구 그대로(63번 4장)
            driving() && !Hub.onboarded(this) -> column(fill = true).apply { gravity = Gravity.CENTER_VERTICAL }.let { blockedLines(it, C.INK, C.SUB, center = true) }
            driving() -> if (plazaOk()) plazaScreen(column(fill = true, span = true)) else driveScreen(column(fill = true))
            // 처음 켜기 첫 장에서 연 개인정보 처리방침(뒤로 가면 그 장으로)
            !Hub.onboarded(this) && webOpen != null -> webScreen(column(fill = true), webOpen!!.second)
            !Hub.onboarded(this) -> when (onboardStep) { 0 -> onboardOn(column()); 1 -> onboardPerm(column()); 2 -> onboardName(column()); 3 -> onboardPractice(column(fill = true)); else -> onboardMode(column()) }
            replying != null -> replyScreen(column(), replying!!)
            review != null -> reviewScreen(column(fill = true), review!!)
            // 듣는 중·도착: 광장(보낸 사람이 말 거는 자리에) + 아래 재생 패널. 광장을 못 띄우는 차는 예전 화면
            Hub.nowPlaying != null -> if (plazaOk()) plazaScreen(column(fill = true, span = true)) else playingScreen(column(fill = true), Hub.nowPlaying!!)
            // 정차 중에 막 열린 목소리: 액자 안에서 빛이 깨어나는 도착 장면
            Hub.offered != null -> if (plazaOk()) plazaScreen(column(fill = true, span = true)) else arrivalScreen(column(fill = true), Hub.offered!!)
            afterOf != null -> afterScreen(column(fill = true), afterOf!!)
            familyOpen -> family(column())
            examplesOpen -> examples(column())
            webOpen != null -> webScreen(column(fill = true), webOpen!!.second)
            permOpen -> permScreen(column())
            modeOpen -> modeTiles(column())
            heardOpen -> heardScreen(column())
            orderOpen -> orderScreen(column())
            settingsOpen -> settings(column())
            else -> if (plazaOk()) plazaScreen(column(fill = true, span = true)) else home()
        }
        // 광장을 안 쓰는 화면이면 3D 층을 숨기고 그리기를 멈춘다
        if (!plazaOnScreen) { plazaHost.visibility = View.GONE; plaza?.setActive(false); plazaIdle = false }
        // 머리줄은 화면을 다 고른 뒤에: 광장 화면이면 비·눈·밤 바탕과 글자색을 따라간다(63번 4장)
        headerBox.removeAllViews()
        headerBox.addView(header(plazaGround))
    }

    /** 주행 중 막힘 안내 두 줄: 확정 문구 32/600 + 도움말 줄 26/400 64%, 사이 8. 누를 것 없음. */
    private fun blockedLines(v: LinearLayout, ink: Int, sub: Int, center: Boolean = false) {
        v.addView(text("주행 중에는 화면을 사용할 수 없습니다", T.TITLE_S, ink, bold = true, center = center), full())
        v.addView(text("P, 파킹 브레이크, 오토홀드 상태에서 사용할 수 있습니다", T.BODY_S, sub, center = center).apply { setPadding(0, 8.dp, 0, 0) }, full())
    }

    // ---------- C-01 처음 켜기 ----------

    /** 가운데 팝업을 그린다(없으면 층을 숨긴다). 폭 760(세로 창에서 양옆 40), 제목 + 설명 + 버튼 둘(주 버튼 왼쪽), 뒤는 어둡게. */
    private fun popup() {
        overlay.removeAllViews()
        val m = menu
        val a = ask
        if (a == null && m == null) { overlay.visibility = View.GONE; return }
        overlay.visibility = View.VISIBLE
        overlay.setBackgroundColor(C.DIM)
        overlay.isClickable = true
        overlay.setOnClickListener { if (a == null) closeMenu() else if (!askBusy) closeAsk() }   // 바깥을 누르면 닫기
        val w = resources.configuration.screenWidthDp
        // 팝업 틀(63번 4장): 모서리 44, 여백 위 48·좌우 44·아래 44, 제목 36/700, 설명 28/400 64%, 버튼 96·모서리 30
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(44.dp, 48.dp, 44.dp, 44.dp); isClickable = true
            background = GradientDrawable().apply { setColor(C.POPUP); cornerRadius = 44.dp.toFloat() }
            elevation = 20.dp.toFloat()   // 그림자 3단계(떠 있는 팝업)
        }
        if (a == null && m != null) {
            // 메뉴: 제목 + 버튼을 세로로(누르는 칸 96, 사이 24). 되돌릴 수 없는 일은 고른 뒤 빨간 버튼 팝업으로 한 번 더 묻는다
            card.addView(text(m.title, T.TITLE, C.INK, center = true, w = T.W7), full().apply { bottomMargin = 16.dp })
            m.items.forEach { (label, run) ->
                card.addView(button(label, C.CARD, C.CARD_DOWN, C.INK, h = 96, r = 30) { menu = null; render(); run() }, full().apply { topMargin = 24.dp })
            }
            card.addView(button("닫기", C.CARD, C.CARD_DOWN, C.INK, h = 96, r = 30) { closeMenu() }, full().apply { topMargin = 24.dp })
            overlay.addView(card, FrameLayout.LayoutParams(minOf(760, w - 48).dp, -2, Gravity.CENTER))
            return
        }
        a!!
        card.addView(text(a.title, T.TITLE, C.INK, center = true, w = T.W7), full())
        a.body?.let { card.addView(text(it, T.BODY, C.SUB, center = true).apply { setPadding(0, 16.dp, 0, 0) }, full()) }
        val btns = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, 40.dp, 0, 0) }
        // 일반 확인은 진회색, 빨강은 끊기·신고·버리기에만
        val okBtn: View = if (askBusy) busy(if (a.danger) C.RED else C.PRIMARY, when (a.ok) { "끊기" -> "끊는 중"; "신고하기" -> "신고하는 중"; "새 코드 만들기" -> "코드를 만드는 중"; "버리기" -> "버리는 중"; else -> "기다리는 중" }, h = 96, r = 30)
            else button(a.ok, if (a.danger) C.RED else C.PRIMARY, if (a.danger) C.RED_DOWN else C.PRIMARY_DOWN, C.ON_INK, h = 96, r = 30) { askBusy = true; render(); a.run { closeAsk() } }
        btns.addView(okBtn, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = 24.dp })
        btns.addView(button("닫기", C.CARD, C.CARD_DOWN, C.INK, h = 96, r = 30) { if (!askBusy) closeAsk() }.apply { isEnabled = !askBusy; alpha = if (askBusy) 0.5f else 1f }, LinearLayout.LayoutParams(0, -2, 1f))
        card.addView(btns, full())
        overlay.addView(card, FrameLayout.LayoutParams(minOf(760, w - 48).dp, -2, Gravity.CENTER))
    }

    private fun onboardOn(v: LinearLayout) {
        v.gravity = Gravity.CENTER_HORIZONTAL
        v.addView(space(40))
        v.addView(logoTile(120), LinearLayout.LayoutParams(120.dp, 120.dp))   // 첫 화면 그림은 로고 타일(63번 4장)
        v.addView(space(36))
        v.addView(text("음성 메시지를\n보낸 분이 정한 순간에 들려드립니다", T.TITLE_L, C.INK, center = true, w = T.W7))
        v.addView(space(28))
        // 처음 켤 때 서버로 가는 것 고지(Pleos 개인정보 심사 '수집 항목 고지'). 권한 안내는 이미 허용돼 있으면 건너뛰므로 늘 보이는 첫 장에 둔다
        v.addView(text("보낸 분 이름과 음성 메시지, 내 이름과 답장 목소리는 도담도담 서버에 보관됩니다. 차 위치와 운전 정보는 차 밖으로 보내지 않습니다.", T.LABEL, C.SUB, center = true), LinearLayout.LayoutParams(minOf(720, resources.configuration.screenWidthDp - 64).dp, -2))
        v.addView(button("개인정보 처리방침", C.PAGE, C.CARD, C.INK, h = 80, r = 24) { openWeb("개인정보 처리방침", "/privacy") }, btnLp())
        v.addView(space(28))
        // 이미 다 허용돼 있으면 안내 한 장은 건너뛴다
        v.addView(primary("다음") { onboardStep = if (carPermsMissing().isEmpty() && !notifMissing()) 2 else 1; render() }, btnLp())
    }

    /** 시스템 권한 창 전에 왜 필요한지 한 장(티맵·카카오T 방식). 거절해도 다음으로 가고, 메인은 막지 않는다. */
    private fun onboardPerm(v: LinearLayout) {
        v.addView(text("속도와 위치를 허용해 주세요", T.TITLE, C.INK, bold = true))
        v.addView(space(32))
        val rows = mutableListOf(
            Triple("speed", "속도", "달리는 중에 들려드립니다"),
            Triple("location", "위치", "집이나 정한 곳 근처에서 들려드립니다"),
        )
        if (notifMissing()) rows += Triple("bell", "알림", "듣기 버튼을 띄웁니다")
        val list = listBox(v)
        rows.forEach { (ic, name, why) ->
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = 100.dp; setPadding(0, 20.dp, 0, 20.dp) }
            row.addView(Icon(this, ic, C.INK), LinearLayout.LayoutParams(48.dp, 48.dp).apply { marginEnd = 24.dp })
            val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            col.addView(text(name, T.BODY, C.INK))
            col.addView(text(why, T.LABEL, C.SUB))
            row.addView(col, LinearLayout.LayoutParams(0, -2, 1f))
            listAdd(list, row)
        }
        v.addView(space(40))
        v.addView(primary("허용하기") { askCarPermissions(); onboardStep = 2; render() }, btnLp())
    }

    /** 속도·위치는 사용자가 허용해야 들어온다. 없으면 주행 중 재생과 장소 순간이 멈춘다. */
    private val CAR_PERMS = arrayOf("android.car.permission.CAR_SPEED", "pleos.car.permission.FUSED_LOCATION")
    private fun granted(p: String) = checkSelfPermission(p) == android.content.pm.PackageManager.PERMISSION_GRANTED
    private fun carPermsMissing() = CAR_PERMS.filter { !granted(it) }
    /** 알림(Android 13부터 사용자가 허용해야 뜸): 버튼 듣기 카드·주차 뒤 알림이 여기에 달려 있다. 거절해도 메인은 막지 않는다. */
    private fun notifMissing() = android.os.Build.VERSION.SDK_INT >= 33 && !granted(android.Manifest.permission.POST_NOTIFICATIONS)
    private fun askCarPermissions() {
        val need = carPermsMissing() + if (notifMissing()) listOf(android.Manifest.permission.POST_NOTIFICATIONS) else emptyList()
        if (need.isNotEmpty()) { prefs().edit().putBoolean("carPermAsked", true).putBoolean("notifAsked", notifMissing()).apply(); requestPermissions(need.toTypedArray(), 2) }
    }

    /** [허용하기]: 한 번 거절한 뒤 Android가 더는 창을 띄우지 않으면(다시 묻지 않음) 앱 설정을 연다. */
    private fun allow(perms: List<String>, askedKey: String, ask: () -> Unit) {
        val blocked = prefs().getBoolean(askedKey, false) && perms.none { shouldShowRequestPermissionRationale(it) }
        if (!blocked) return ask()
        Hub.log("권한 창이 더 뜨지 않아 앱 설정 열기")
        runCatching { startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", packageName, null))) }
            .onFailure { Hub.log("앱 설정 못 엶: $it"); ask() }
    }

    /** 속도·위치를 거절했을 때 메인 맨 위 안내 줄. 속도가 없으면 주행 중 재생만, 위치가 없으면 집·정한 곳 순간만 멈춘다(나머지는 그대로). */
    private fun permNotice() = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
        setPadding(28.dp, 16.dp, 16.dp, 16.dp); background = box(C.CARD, C.CARD, radius = 24)
        val missing = carPermsMissing()
        val speed = "android.car.permission.CAR_SPEED" in missing
        val loc = "pleos.car.permission.FUSED_LOCATION" in missing
        val what = when { speed && loc -> "속도·위치"; speed -> "속도"; else -> "위치" }
        addView(text("$what 권한이 꺼져 있습니다", T.BODY, C.INK), LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = 16.dp })
        addView(button("허용하기", C.PRIMARY, C.PRIMARY_DOWN, C.ON_INK, h = 80, r = 24) { allow(carPermsMissing(), "carPermAsked") { askCarPermissions() } }, LinearLayout.LayoutParams(-2, -2))
    }

    /** 처음 켜기 3: 초대장에 쓸 내 이름 한 칸(사람 화면의 '내 이름'과 같은 값). 정해 두면 메인 [초대 링크 만들기]가 바로 링크를 만든다. */
    private fun onboardName(v: LinearLayout) {
        v.addView(section("초대장에 쓸 내 이름", top = 12))
        val input = android.widget.EditText(this).apply {
            setText(ownerDraft ?: ownerName()); hint = "예: 홍길동"; setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, T.BODY); setTextColor(C.INK); setHintTextColor(C.SUB)
            filters = arrayOf(android.text.InputFilter.LengthFilter(10)); isSingleLine = true
            imeOptions = android.view.inputmethod.EditorInfo.IME_ACTION_DONE or android.view.inputmethod.EditorInfo.IME_FLAG_NO_EXTRACT_UI or android.view.inputmethod.EditorInfo.IME_FLAG_NO_FULLSCREEN
            setOnEditorActionListener { _, a, _ -> if (a == android.view.inputmethod.EditorInfo.IME_ACTION_DONE) { onboardNameNext(); true } else false }
            setPadding(28.dp, 0, 28.dp, 0); minHeight = 96.dp; background = box(C.CARD, C.LINE)
            addTextChangedListener(object : android.text.TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun afterTextChanged(s: android.text.Editable?) { ownerDraft = s?.toString() ?: "" }
            })
        }
        v.addView(input, full().apply { bottomMargin = 32.dp })
        v.addView(primary("다음") { onboardNameNext() }, btnLp())
        input.post { input.requestFocus(); input.setSelection(input.text.length); keyboard(input, true) }
    }

    private fun onboardNameNext() {
        val n = cleanName(ownerDraft ?: ownerName())
        if (n.isEmpty()) { toast("이름을 입력해 주세요"); return }
        prefs().edit().putString("ownerName", n).apply()
        currentFocus?.let { keyboard(it, false) }
        ownerDraft = null; onboardStep = 3; render()
    }

    // ---------- 처음 켜기 4: 핸들 가운데 버튼 연습 ----------
    // 정차 중에 예시 메시지 하나가 띵동과 함께 온다. 실제 핸들 가운데 버튼(또는 화면 [듣기])을 누르면 재생, 다 들으면 듣는 방식으로.
    // 서비스는 처음 켜기를 마친 뒤에 켜지므로 버튼 받기(WheelWindow)와 재생을 이 화면이 직접 한다. 서버에는 아무것도 보내지 않는다.

    private val practiceMsg by lazy { Demo.examples().first { it.moment == "start" } }   // 수진님 · 차 탈 때(정차 중이라 맞는 순간)
    private var practiceWheel: WheelWindow? = null
    private var practicePlayer: MediaPlayer? = null
    private var practiceFocus: android.media.AudioFocusRequest? = null
    private var practiceArmed = false   // 띵동을 울리고 핸들 버튼을 받는 중

    private fun onboardPractice(v: LinearLayout) {
        val h = practiceMsg
        if (practicePlayer != null) {
            // 듣는 중: 실제 듣는 화면처럼 빛 + 이름 + 재생 막대
            val l = lit(v, senderTile(h, 40))
            l.mid.addView(text(whose(h), T.HEAD_S, C.INK, center = true, w = T.W7), full())
            l.mid.addView(space(32))
            bar = Bar(this).also { l.mid.addView(it, LinearLayout.LayoutParams(-1, 40.dp)) }
            l.foot.addView(outline("다음") { practiceNext() }, btnLp())
            tick()
            return
        }
        // 화면을 떠난 뒤 늦게 온 다시 그리기(사람 목록 받기 등)로는 띵동·버튼 받기를 다시 열지 않는다
        if (!practiceArmed && Hub.visible) armPractice()
        v.gravity = Gravity.CENTER_HORIZONTAL
        v.addView(grow())
        // 주행 중 메시지 알림 화면과 같은 말
        v.addView(text(whose(h), T.BODY, C.SUB, center = true), full())
        v.addView(space(16))
        v.addView(text("핸들 가운데 버튼으로\n듣기", T.HEAD_M, C.INK, center = true, w = T.W7), full())
        v.addView(space(32))
        // 누를 버튼이 핸들 어디 있는지. 가로 창: 왼쪽 전체 + 오른쪽 확대 / 세로 창: 확대 한 장 360×270(두 장이면 넘쳐 잘린다)
        if (wideWindow()) {
            val pics = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            pics.addView(wheelPic(R.drawable.wheel_full, "핸들 전체에서 누를 버튼 위치"), LinearLayout.LayoutParams(400.dp, 300.dp))
            pics.addView(wheelPic(R.drawable.wheel_play, "핸들 가운데 버튼 확대"), LinearLayout.LayoutParams(400.dp, 300.dp).apply { marginStart = 16.dp })
            v.addView(pics, LinearLayout.LayoutParams(-2, -2))
        } else v.addView(wheelPic(R.drawable.wheel_play, "핸들 가운데 버튼 확대"), LinearLayout.LayoutParams(360.dp, 270.dp))
        v.addView(grow())
        // 듣지 않고 넘어가면 [건너뛰기], 다 들은 뒤(듣는 중 화면)는 [다음]
        v.addView(btnRow(primary("듣기") { practicePlay() }, outline("건너뛰기") { practiceNext() }), LinearLayout.LayoutParams(-2, -2))
    }

    private fun armPractice() {
        practiceArmed = true
        val w = practiceWheel ?: WheelWindow(this).also { practiceWheel = it }
        w.open { key -> Hub.log("연습: 핸들 버튼($key) → 듣기"); practicePlay() }
        // 화면이 뜬 뒤 띵동(실제 메시지가 올 때와 같은 소리)
        main.postDelayed({ if (practiceArmed && practicePlayer == null) Chime.play() }, 400)
        Hub.log("연습: 예시 메시지 알림")
    }

    private fun practicePlay() {
        if (practicePlayer != null || driving() || onboardStep != 3) return
        val attrs = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()
        val am = getSystemService(android.media.AudioManager::class.java)
        // 목소리가 소리 권한을 먼저 잡은 뒤 버튼 받기를 닫는다(음악이 사이에 튀지 않게)
        practiceFocus = android.media.AudioFocusRequest.Builder(android.media.AudioManager.AUDIOFOCUS_GAIN_TRANSIENT).setAudioAttributes(attrs).build().also { am.requestAudioFocus(it) }
        val p = runCatching {
            MediaPlayer().apply {
                setAudioAttributes(attrs)
                resources.openRawResourceFd(R.raw.demo_start).use { setDataSource(it.fileDescriptor, it.startOffset, it.length) }
                setOnCompletionListener { Hub.log("연습: 예시 메시지 다 들음"); practiceNext() }
                setOnErrorListener { _, a, b -> Hub.log("연습 재생 오류 $a/$b"); practiceNext(); true }
                prepare(); start()
            }
        }.onFailure { Hub.log("연습 재생 실패: $it") }.getOrNull()
        practiceArmed = false
        practiceWheel?.close("연습 듣기")
        if (p == null) { practiceNext(); return }
        Hub.log("연습: ${practiceMsg.sender} 메시지 재생")
        practicePlayer = p
        render()
    }

    private fun practiceNext() { stopPractice(); onboardStep = 4; render() }

    /** 연습을 끝낸다(다음 단계·뒤로·출발·화면을 떠날 때). 다시 연습 화면이 그려지면 띵동부터 다시. */
    private fun stopPractice() {
        if (!practiceArmed && practicePlayer == null && practiceFocus == null) return
        practiceArmed = false
        practiceWheel?.close("연습 끝")
        practicePlayer?.let { runCatching { it.stop() }; it.release() }
        practicePlayer = null
        practiceFocus?.let { getSystemService(android.media.AudioManager::class.java).abandonAudioFocusRequest(it) }
        practiceFocus = null
    }

    /** 처음 켤 때 듣는 방식을 고른다(설정에서 바꿀 수 있다). 연습으로 한 번 들어 본 뒤에 고른다. */
    private fun onboardMode(v: LinearLayout) {
        // 머리줄이 '듣는 방식'이라 제목 없이 칸부터(설정의 듣는 방식 화면과 같은 자리)
        modeTiles(v)
        v.addView(space(24))
        v.addView(primary("시작") {
            Hub.setOnboarded(this); Hub.setEnabled(this, true)
            startForegroundService(Intent(this, CarService::class.java))
            render()
        }, btnLp())
    }

    /** 핸들 버튼 그림(ChatGPT 생성) 한 장, 모서리 둥글게. 연습 화면·주행 중 알림 화면에 쓴다. */
    private fun wheelPic(res: Int, what: String) = ImageView(this).apply {
        setImageResource(res); scaleType = ImageView.ScaleType.CENTER_CROP
        clipToOutline = true; outlineProvider = object : android.view.ViewOutlineProvider() { override fun getOutline(view: View, o: android.graphics.Outline) { o.setRoundRect(0, 0, view.width, view.height, 16.dp.toFloat()) } }
        contentDescription = what
    }

    private fun modeTiles(v: LinearLayout) {
        listOf(
            Triple("button", "버튼 눌러서 듣기", "핸들 가운데 버튼으로 듣기"),   // 11/10 사용자: 카드 안내와 같은 이름표형('바로' 뺌)
            Triple("auto", "버튼 없이 듣기", "알림 소리 뒤 자동으로 듣기"),   // 11/10 이름표형
            // 주행 집중 모드(11/08 C14, 예전 '주차하면 듣기'와 같은 동작): 주행 중에 순간이 와도 띵동·안내·알림 없이 두었다가 주차하면 이어 들려준다(CarService.enqueue·onPark)
            Triple("arrive", "주행 집중 모드", "운전 중 알림 끄기 · 주차 후 듣기"),   // 11/10 사용자: 이름표형으로(11/08 문구 대체)
        ).forEach { (key, title, desc) ->
            val on = Hub.listenMode(this) == key
            // 고른 칸: 회색 면 + ✓ / 안 고른 칸: 흰 면 + 1px 선(63번 4장)
            val tile = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(28.dp, 22.dp, 28.dp, 22.dp) }
            if (on) tile.background = box(C.CARD, C.CARD, radius = 24)
            else {
                pressable(tile, C.PAGE, C.CARD_DOWN, C.PAGE, radius = 24) { Hub.setListenMode(this, key); Hub.log("듣는 방식 → $title"); render() }
                tile.foreground = GradientDrawable().apply { cornerRadius = 24.dp.toFloat(); setStroke(1.dp, C.LINE); setColor(Color.TRANSPARENT) }
            }
            tile.addView(choiceTitle(title, on, tag = if (key == "button") "추천" else null))
            if (desc.isNotEmpty()) tile.addView(text(desc, T.BODY_S, C.SUB).apply { setPadding(0, 4.dp, 0, 0) })
            v.addView(tile, full().apply { bottomMargin = 24.dp })
        }
    }

    /** 고르는 칸의 제목 줄. 고른 칸은 색만이 아니라 체크 표시로도 알 수 있게(햇빛·색 구별이 어려운 사람). tag: 제목 오른쪽 작은 태그(추천). */
    private fun choiceTitle(title: String, on: Boolean, tag: String? = null) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
        addView(text(title, T.BODY, C.INK, bold = true), LinearLayout.LayoutParams(-2, -2))
        tag?.let { addView(tagView(it, if (on) C.PAGE else C.CARD), LinearLayout.LayoutParams(-2, -2).apply { marginStart = 16.dp }) }
        addView(View(this@MainActivity), LinearLayout.LayoutParams(0, 1, 1f))
        if (on) addView(Icon(this@MainActivity, "check", C.CHECK), LinearLayout.LayoutParams(40.dp, 40.dp))
        contentDescription = listOfNotNull(title, tag, if (on) "선택됨" else null).joinToString(", ")
    }

    /** 작은 태그(63번 4장 예시 표시 모양): 면, 모서리 12, 24/600 64%. */
    private fun tagView(s: String, face: Int = C.CARD) = text(s, T.LABEL, C.SUB, bold = true).apply {
        setPadding(14.dp, 4.dp, 14.dp, 4.dp); background = box(face, face, radius = 12)
    }

    // ---------- 주차 홈: 기다림 액자 ----------

    /** 열린 뒤에야 공개하는 '왜 열렸는지'(열리기 전엔 어디에도 안 보인다). */
    private val LEFT_WHEN = mapOf("start" to "차 탈 때", "arrive" to "주차했을 때", "home" to "집 근처에 왔을 때", "rain" to "비 올 때", "long" to "오래 달렸을 때", "battery" to "배터리·기름이 부족할 때")

    /** 반복 묻기 라벨(63번 4장): "다음에 비 올 때". */
    private val NEXT_LABEL = mapOf("start" to "다음에 차 탈 때", "arrive" to "다음에 주차할 때", "home" to "다음에 집 근처에 왔을 때", "rain" to "다음에 비 올 때", "long" to "다음에 오래 달렸을 때", "battery" to "다음에 배터리·기름이 부족할 때")

    // ---------- 메인 화면: 이 함수만 고치면 된다 ----------

    private fun home() {
        // 3D를 못 띄우는 차의 예비 홈: 광장의 띠와 같은 줄·버튼·입구(그림 없음, 63번 4장)
        val v = column(fill = true)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL; setPadding(40.dp, 32.dp, 40.dp, 32.dp) }
        v.addView(col, LinearLayout.LayoutParams(-1, 0, 1f))
        if (carPermsMissing().isNotEmpty()) col.addView(permNotice(), full())
        col.addView(grow())
        plazaBand(col, false, Ground(Color.TRANSPARENT), false)
        col.addView(grow())
    }

    /** 메인 입구 한 줄(63번 4장): 목록 줄 높이 100, 28/400 글자 + 꺾쇠 32 64%. 바탕 위에 면 없이(누르면 옅게). */
    private fun homeDoor(label: String, g: Ground? = null, onClick: () -> Unit) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = 100.dp; setPadding(16.dp, 0, 8.dp, 0)
        pressable(this, Color.TRANSPARENT, g?.doorDown ?: C.CARD, Color.TRANSPARENT, radius = 24, onClick = onClick)
        addView(text(label, T.BODY, g?.ink ?: C.INK), LinearLayout.LayoutParams(0, -2, 1f))
        addView(Icon(this@MainActivity, "next", g?.sub ?: C.SUB), LinearLayout.LayoutParams(32.dp, 32.dp).apply { marginStart = 8.dp })
        contentDescription = label
    }

    // ---------- 차 홈 광장(3D 더미) ----------
    // 상태(59번 0절): 주행 대기(그리기 멈춤·흐림·터치 0) / 주행 도착(결과 1장) / 재생 패널 / P 대기(쉬는 시간) / P 도착(걸어 나옴) / 들은 뒤 / 연결 0명.
    // 광장(PlazaView)은 화면을 다시 그려도 지우지 않는 층(plazaHost)에 한 번만 만들고, 본문에는 투명한 무대·아래 띠·패널만 그린다.

    private lateinit var plazaHost: FrameLayout
    private var plaza: PlazaView? = null
    private var plazaFailed = false
    private var plazaOnScreen = false
    /** 직전에 P 대기 장면이었는지(들어올 때 한 번 다 같이 손 흔들기). */
    private var plazaIdle = false
    private var skipGreet = false   // 시험 명령(adb·원격 화면)으로 앞으로 불려 온 경우 인사 한 번 건너뛰기
    /** 광장 패널의 '들은 뒤'(P): '○○님' + [답장][다시 듣기]. 빈 곳을 누르거나 뒤로 가면 닫는다. */
    private var plazaAfter: Hidden? = null
    /** 답장 안 한 메시지 카드(C7)에서 이모티콘을 보낸 메시지: 목록(Hub.unreplied)에서 빠져도 닫기·답장 전까지 그 카드를 그대로 둔다. */
    private var nudgeHold: Hidden? = null
    /** 누른 쿠션(사람) 자리: 아래 카드 '○○님' + [닫기]. 0이면 없음. */
    private var plazaCard = 0
    /** 들은 메시지 화면에서 다시 들었으면 끝난 뒤 그 메시지 화면으로(광장 패널이 아니라). */
    private var replayToAfter = false
    private var panelKey: String? = null
    private var panelBars: PanelBars? = null
    private var panelNow: TextView? = null
    private var panelAll: TextView? = null
    private val busts = mutableMapOf<PlazaPerson, Bitmap>()
    private var orderOpen = false
    private var orderDraft: MutableList<String?>? = null
    private var orderBusy = false

    /** 광장을 띄울 수 있는지. 처음 부를 때 만든다. 못 만들면(3D가 안 되는 차) 예전 홈·듣기 화면으로 돌아간다. */
    private fun plazaOk(): Boolean {
        if (plazaFailed) return false
        if (plaza == null) {
            plaza = runCatching { PlazaView(this) }
                .onFailure { plazaFailed = true; Hub.log("광장을 띄우지 못해 예전 홈으로: $it") }.getOrNull()
                ?.also { pv ->
                    plazaHost.addView(pv, FrameLayout.LayoutParams(1, 1))
                    // 날씨·밤이 4초에 걸쳐 바뀌는 동안 본문 칸 바탕도 같이. 글자색이 바뀌어야 하는 순간에만 화면을 다시 그린다
                    pv.onBackdrop = { c -> plazaHost.setBackgroundColor(c); if (plazaOnScreen && plazaGround?.ink != Ground(c).ink) render() }
                    pv.pageColor = C.PAGE
                    pv.lowSpec = Hub.lowSpec(this)
                }
        }
        return plaza != null
    }

    /** 광장 3D 칸을 무대(본문의 투명한 칸)와 같은 자리·크기로 맞춘다. 크기가 그대로면 건드리지 않는다(다시 그리지 않게). */
    private fun placePlaza(stage: View) {
        val pv = plaza ?: return
        if (stage.width <= 0 || stage.height <= 0) return
        val a = IntArray(2); val h = IntArray(2)
        stage.getLocationInWindow(a); plazaHost.getLocationInWindow(h)
        val lp = pv.layoutParams as FrameLayout.LayoutParams
        val x = a[0] - h[0]; val y = a[1] - h[1]
        if (lp.width == stage.width && lp.height == stage.height && lp.leftMargin == x && lp.topMargin == y) return
        lp.width = stage.width; lp.height = stage.height; lp.leftMargin = x; lp.topMargin = y; lp.gravity = Gravity.TOP or Gravity.START
        pv.post { pv.layoutParams = lp }
    }

    /** 낮밤: 시스템 야간 모드에 묶는다(63번 4장, 시각 규칙 없음). 시험 명령(weather night/day)이 있으면 그것. */
    private fun plazaNight(): Boolean = when (Hub.weatherTest) {
        "night" -> true
        "day" -> false
        else -> (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
    }
    /** 가로등: 전조등(하향등) 신호를 따른다. 신호가 없으면 야간 모드. 비가 오면 켠다. 시험 명령 night/day 면 그것. */
    private fun plazaLamp(): Boolean = when (Hub.weatherTest) {
        "night" -> true
        "day" -> false
        else -> (Hub.lowBeam ?: plazaNight()) || plazaWeather() == "rain"   // 비 오면 낮에도 켠다(사용자 11/08 밤)
    }
    /** 비(와이퍼 켜짐 = 기존 비 판정 신호) → 유리 돔. 눈은 아직 신호가 없어 시험 명령으로만. */
    private fun plazaWeather(): String = when (Hub.weatherTest) {
        "rain", "snow" -> Hub.weatherTest!!
        "clear" -> ""
        else -> if (Hub.raining) "rain" else ""
    }

    /** 메시지를 남긴 사람의 자리(광장에서 찾기). 이름을 숨길 때(동승자 + 프라이빗 모드)는 아무도 나오지 않는다.
     *  예시 메시지는 예시 가족 체험(C13) 중에만 그 예시 사람이 나온다. */
    private fun heroOf(h: Hidden?, d: PlazaData?): PlazaPerson? {
        if (h == null || d == null || namesHidden()) return null
        if (h.example || Hub.demo) return if (demoPlaza != null && d === demoPlaza) d.people.firstOrNull { it.name == h.sender } else null
        return d.byCode(h.invite) ?: d.people.firstOrNull { it.name != null && it.name == h.sender }
    }

    /** 가로로 넓은 창(폭/높이 > 1.15)이면 왼쪽 60% 광장, 오른쪽 40% 정보 기둥(11/08 C1). 세로 창(840×1184 등)은 예전 배치 그대로. */
    private fun wideWindow() = resources.configuration.let { it.screenWidthDp > it.screenHeightDp * 1.15f }

    /** 날씨·밤 바탕(창 전체, C2) 위에 바로 놓이는 글자 색. 카드·패널 안은 카드 바탕이라 원래 색을 쓴다. 바탕이 없으면(맑은 낮) 원래 색.
     *  비·눈 전용 글자색은 두지 않는다: 글자 #131417(밤은 흰색)과 그 64%·84%만(63번 2장). 비 바탕 #DCE3EB 위 64%는 약 5.0:1. */
    private inner class Ground(bd: Int) {
        val on = Color.alpha(bd) > 0
        val bg = bd
        private val dark = on && lum(bd) < 0.18   // 바탕 밝기 0.18에서 흰 글자로: 검정·흰 글자 둘 다 4.5:1 이상인 점(날씨·밤이 4초에 걸쳐 바뀌는 중에도, 회의 11/08)
        val ink = if (!on) C.INK else if (dark) Color.WHITE else Color.parseColor("#131417")
        val sub = if (!on) C.SUB else Color.argb(163, Color.red(ink), Color.green(ink), Color.blue(ink))     // 64%
        val ink84 = if (!on) C.INK84 else Color.argb(214, Color.red(ink), Color.green(ink), Color.blue(ink)) // 84%
        val line = if (!on) C.LINE else Color.argb(31, Color.red(ink), Color.green(ink), Color.blue(ink))
        val doorDown = if (!on) C.CARD else if (dark) 0x26FFFFFF else 0x1F000000
    }
    /** 이번에 그린 광장 화면의 바탕(머리줄이 따라간다). 광장이 아니면 null. */
    private var plazaGround: Ground? = null
    private fun lum(c: Int): Double {
        fun l(v: Int) = (v / 255.0).let { if (it <= 0.04045) it / 12.92 else Math.pow((it + 0.055) / 1.055, 2.4) }
        return 0.2126 * l(Color.red(c)) + 0.7152 * l(Color.green(c)) + 0.0722 * l(Color.blue(c))
    }

    private fun plazaScreen(v: LinearLayout) {
        val pv = plaza ?: return home()
        plazaOnScreen = true
        val d = driving()
        // 예시 가족 체험 중에 진짜 메시지가 오면 체험을 끝낸다
        if (demoPlaza != null && (Hub.offered != null || Hub.nowPlaying?.example == false)) endDemoTour()
        val demo = demoPlaza
        val data = demo ?: Hub.plaza ?: Plaza.cached(this)?.also { Hub.plaza = it }
        val playing = Hub.nowPlaying
        // 체험의 '도착' 장면은 예시 목소리가 실제로 나오기 시작할 때까지 그대로 둔다(준비하는 사이 띠가 깜빡이지 않게)
        val offered = Hub.offered ?: demoMsg.takeIf { demo != null && playing == null && (demoStep == "arrive" || demoStep == "play") }
        // 패널에 보일 상태: 재생 > 도착 > 들은 뒤(P) > 쿠션 카드(P) > 답장 안 한 메시지 카드(P, C7) > 없음
        val after = if (!d && playing == null && offered == null) plazaAfter else null
        val cardP = if (!d && plazaCard != 0) data?.bySlot(plazaCard) else null
        val calm = !d && playing == null && offered == null && after == null && cardP == null && demo == null
        if (d || !Hub.nudge) nudgeHold = null   // 이모티콘을 보내 붙잡아 둔 카드는 주행을 시작하거나 카드가 내려가면 놓는다
        // 주차 목록(순간이 온 재생 예정)이 있으면 답장 카드는 뒤로 미룬다: 주차 안내 녹음("도착한 음성 메시지가 있습니다.") 뒤에 카드가 목록을 가리지 않게(목록을 다 들으면 카드)
        val listFirst = nudgeHold == null && Hub.parked && Hub.service?.parkList()?.isNotEmpty() == true
        val nudge = if (calm && Hub.nudge && !namesHidden() && !listFirst) nudgeHold?.let { listOf(it) } ?: Hub.unreplied(this) else emptyList()
        if (calm && Hub.nudge && nudge.isEmpty() && !namesHidden() && !listFirst) Hub.nudge = false
        val mode = when { playing != null -> "play"; offered != null -> "arrive"; after != null -> "after"; cardP != null -> "card"; nudge.isNotEmpty() -> "nudge"; else -> null }
        val h = playing ?: offered ?: after
        val hero = if (mode == "nudge") heroOf(nudge.first(), data) else heroOf(h, data)
        if (mode == "play") { lastPlaying = playing; lastPlayingAt = System.currentTimeMillis() }

        // 3D 층 상태 맞추기
        plazaHost.visibility = View.VISIBLE
        pv.setActive(true)
        pv.setPeople(data)
        pv.setWeather(plazaWeather(), plazaNight(), plazaLamp())
        // 비·눈·밤 바탕색은 3D 칸이 아니라 헤더 아래 본문 칸 전체에(C2). 맑은 낮은 투명 = 원래 흰 화면
        plazaHost.setBackgroundColor(pv.backdrop)
        val g = Ground(pv.backdrop)
        plazaGround = g
        pv.setDriving(d)
        pv.setHold(!d && !Hub.parked)   // 오토홀드·파킹 브레이크(P 아님): 광장은 다 움직이되 걷기만 뺀다
        pv.setHero(if (mode == "card") 0 else hero?.slot ?: 0, walk = !d, tint = if (mode == "play") 0.4f else 0.2f)
        // 흐림은 쓰지 않는다(11/08 사용자). 주행 중엔 멈춘 선명한 장면 + 위쪽 '주차 시에 사용' 안내
        pv.setBlur(false)
        val idle = !d && (mode == null || mode == "card" || mode == "nudge")
        if (idle && !plazaIdle) { if (skipGreet) skipGreet = false else pv.greet() }
        plazaIdle = idle

        val wide = wideWindow()
        val wrap = FrameLayout(this).apply { clipChildren = false }
        v.addView(wrap, LinearLayout.LayoutParams(-1, 0, 1f))
        // 무대: 투명(뒤의 3D가 보인다). P에서만 누를 수 있다. 세로 창: 무대 + 아래 띠 / 가로 창: 왼쪽 무대 60% + 오른쪽 정보 기둥 40%
        val stage = FrameLayout(this)
        var inner: LinearLayout? = null
        var side: FrameLayout? = null
        if (wide) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; clipChildren = false }
            wrap.addView(row, FrameLayout.LayoutParams(-1, -1))
            row.addView(stage, LinearLayout.LayoutParams(0, -1, 0.6f))
            // 오른쪽 기둥(63번 4장): 왼쪽 정렬, 여백 왼 16·오른 48·위아래 48, 묶음은 세로 가운데
            side = FrameLayout(this).apply { clipChildren = false; clipToPadding = false; setPadding(16.dp, 48.dp, 48.dp, 48.dp) }
            row.addView(side, LinearLayout.LayoutParams(0, -1, 0.4f))
        } else {
            inner = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            wrap.addView(inner, FrameLayout.LayoutParams(-1, -1))
            inner.addView(stage, LinearLayout.LayoutParams(-1, 0, 1f))
        }
        stage.addOnLayoutChangeListener { s, _, _, _, _, _, _, _, _ -> placePlaza(s) }
        stage.post { placePlaza(stage) }
        if (!d) {
            var downX = 0f; var downY = 0f
            stage.setOnTouchListener { _, e ->
                when (e.actionMasked) {
                    MotionEvent.ACTION_DOWN -> { downX = e.x; downY = e.y }
                    MotionEvent.ACTION_UP -> if (Math.hypot((e.x - downX).toDouble(), (e.y - downY).toDouble()) < 24.dp) plazaTap(e.x, e.y, mode)
                }
                true
            }
            stage.contentDescription = data?.people?.joinToString(", ") { it.label } ?: ""
            if (carPermsMissing().isNotEmpty()) stage.addView(permNotice(), FrameLayout.LayoutParams(-1, -2, Gravity.TOP).apply { setMargins(24.dp, 16.dp, 24.dp, 0) })
            // 이어 들을 때 [다음 메시지]는 패널 안 재생 원 오른쪽 ⏭ 원으로 옮겼다(63번 4장)
        }
        // 띠(대기 개수·버튼·입구 / 주행 중엔 대기 개수 + 막힘 안내). 바탕은 투명(창 바탕색이 그대로).
        // 주행 중에도 떠 있는 카드 없이 P 홈과 같은 자리(세로: 광장 아래 / 가로: 오른쪽 기둥)에 갈아 끼운다(63번 4장).
        // 패널이 떠 있는 동안 글자는 숨긴다(자리는 그대로 둬서 광장 크기가 바뀌지 않게). 도착 중에는 막힘 안내도 같이 숨는다
        val band = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = if (wide) Gravity.START else Gravity.CENTER_HORIZONTAL; setPadding(if (wide) 0 else 40.dp, 24.dp, if (wide) 0 else 40.dp, 24.dp) }
        if (side != null) side.addView(band, FrameLayout.LayoutParams(-1, -2, Gravity.CENTER_VERTICAL)) else inner!!.addView(band, full())
        plazaBand(band, d, g, wide)
        if (mode != null) band.visibility = View.INVISIBLE

        // 재생 패널(53번 2절: 792×360, 바닥에서 12 위) 또는 쿠션 카드·답장 안 한 메시지 카드. 가로 창이면 오른쪽 기둥 가운데에 기둥 폭으로
        if (mode == null) { panelKey = null; return }
        val card = when (mode) {
            "card" -> cardView(cardP!!, wide)
            "nudge" -> nudgeView(nudge, hero, wide)
            else -> panelView(mode, h!!, hero, d, wide, if (mode == "after") groupFor(h, data) else null)
        }
        val holder = FrameLayout(this).apply { clipChildren = false }
        if (side != null) {
            side.addView(holder, FrameLayout.LayoutParams(-1, -2, Gravity.CENTER_VERTICAL))
            holder.addView(card, FrameLayout.LayoutParams(-1, -2))
        } else {
            wrap.addView(holder, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))
            holder.addView(card, FrameLayout.LayoutParams(840.dp, -2, Gravity.CENTER_HORIZONTAL))
            // 칸이 840보다 좁으면 패널을 같은 비율로 줄인다
            holder.post {
                val k = minOf(1f, holder.width / 840.dp.toFloat())
                card.pivotX = card.width / 2f; card.pivotY = card.height.toFloat(); card.scaleX = k; card.scaleY = k
            }
        }
        val key = "$mode:${h?.id ?: nudge.firstOrNull()?.id}:${if (mode == "card") plazaCard else 0}:$wide"
        if (key != panelKey && !d) {
            // P: 0.2초 동안 아래에서 24 올라온다. 주행 중엔 움직임 없이 한 번에
            card.alpha = 0f; card.translationY = 24.dp.toFloat()
            card.animate().alpha(1f).translationY(0f).setDuration(200).start()
        }
        panelKey = key
        tick()
    }

    /** 개수 띠(75번 A-2 정차 화면 계층, 11/10).
     *  정차(P): ① 도착한 음성 메시지 N개 + [모두 듣기] + 목록(지금 누를 것, 화면의 주인공) → ② 선 + '예약된 음성 메시지 M개' 한 줄(누를 것 없음)
     *  → ③ 들은 메시지 입구. 도착한 게 없으면 ② 자리가 큰 숫자(예약된 음성 메시지 / M개)로 올라간다. 큰 숫자는 화면에 하나만.
     *  주행 중: 예약된 숫자 하나 + 놓친 게 있을 때만 작은 줄 '도착한 메시지 N개 · 주차 후 듣기' + 1px 선 + 막힘 안내(누를 것 없음).
     *  g: 창 바탕(날씨·밤) 위 글자 색. narrow: 가로 창 오른쪽 기둥(왼쪽 정렬). */
    private fun plazaBand(col: LinearLayout, d: Boolean, g: Ground, narrow: Boolean) {
        val ready = Hub.loaded || Hub.today.isNotEmpty()
        val svc = Hub.service
        // 도착한 것(순간이 이미 온 것)은 정차 중에만 목록으로. 주행 중·P 아닌 정차(오토홀드 등)는 작은 줄 하나로
        val parkedNow = !d && ready && Hub.parked && Hub.nowPlaying == null && Hub.offered == null && Hub.arrivalLeft == 0
        val listNow = if (parkedNow) svc?.parkList() ?: emptyList() else emptyList()
        val reserved = svc?.reservedCount() ?: Hub.waitingCount(this, listNow.map { it.id }.toSet())
        val arrivedLater = if (parkedNow || !ready) 0 else svc?.arrivedLater() ?: 0
        val waiting = reserved + listNow.size + arrivedLater
        countLines(col, ready, listNow.size, reserved, d, g, narrow)
        if (listNow.isNotEmpty()) {
            parkRows(col, listNow, g, narrow)
            // 예약된 것은 숫자만 한 줄(무엇이 언제 올지는 보이지 않는다: 깜짝이 깨지지 않게, 11/08 결정)
            if (reserved > 0) {
                col.addView(View(this).apply { setBackgroundColor(g.line) }, LinearLayout.LayoutParams(-1, 1.dp).apply { topMargin = 24.dp; bottomMargin = 24.dp })
                col.addView(text("예약된 음성 메시지 ${reserved}개", T.BODY, g.ink, bold = true, center = !narrow), full())
            }
        }
        if (arrivedLater > 0) col.addView(text("도착한 메시지 ${arrivedLater}개 · 주차 후 듣기", T.BODY, g.sub, center = !narrow).apply { setPadding(0, 12.dp, 0, 0) }, full())
        if (d) {
            // 잠시 후 줄은 버튼을 누르고 기다릴 때(잠시 후 들려드립니다)와 주행 집중 모드로 미뤘을 때(주차하면 들려드립니다)만
            svc?.driveNote()?.let { col.addView(text(it, T.BODY, g.sub, center = !narrow).apply { setPadding(0, 8.dp, 0, 0) }, full()) }
            if (Hub.demo) col.addView(tagView("예시 메시지"), LinearLayout.LayoutParams(-2, -2).apply { topMargin = 12.dp })
            col.addView(View(this).apply { setBackgroundColor(g.line) }, LinearLayout.LayoutParams(-1, 1.dp).apply { topMargin = 40.dp; bottomMargin = 40.dp })
            blockedLines(col, g.ink, g.sub, center = !narrow)
            return
        }
        if (!ready) return
        val btns = mutableListOf<View>()
        if (noOneYet()) btns += primary("초대 코드 만들기") { inviteFirst() }
        if (!Hub.demo && Hub.today.isNotEmpty() && !prefs().getBoolean("gotReal", false)) prefs().edit().putBoolean("gotReal", true).apply()
        // 가족 0명이면 예시 가족이 잠깐 앉아 도착 → 재생 → 들은 뒤를 한 번 보여 준다(C13). 사람이 있으면 예시 목록
        if (!Hub.demo && waiting == 0 && !prefs().getBoolean("gotReal", false))
            btns += outline("예시 메시지 들어 보기") { if (noOneYet()) startDemoTour() else { examplesOpen = true; render() } }
        btns.forEachIndexed { i, b -> col.addView(b, LinearLayout.LayoutParams(-2, -2).apply { topMargin = if (i == 0) 32.dp else 16.dp }) }
        if (Hub.demo) col.addView(tagView("예시 메시지"), LinearLayout.LayoutParams(-2, -2).apply { topMargin = 16.dp })
        if (Hub.offline && !Hub.demo) col.addView(text("인터넷에 연결되지 않았습니다", T.LABEL, g.sub, center = !narrow).apply { setPadding(0, 16.dp, 0, 0) }, full())
        // 들은 메시지 입구 한 줄(개수 없음, 맨 아래 = 지난 것). 사람은 설정의 '사람·초대'로 들어간다
        col.addView(homeDoor("들은 메시지", g) { heardOpen = true; render() }, full().apply { topMargin = if (listNow.isNotEmpty()) 24.dp else 48.dp })
    }

    /** 큰 숫자 한 묶음(75번 A-2): 윗줄 32/400 84% 이름, 아랫줄 "N개" 60/700. 도착한 게 있으면 '도착한 음성 메시지', 없으면 '예약된 음성 메시지'.
     *  둘 다 0이면 "예약된 음성 메시지가 없습니다" 36/600 한 줄(도착한 0은 따로 말하지 않는다). 설명 줄 없음. 파랑 없음. */
    private fun countLines(col: LinearLayout, ready: Boolean, arrived: Int, reserved: Int, d: Boolean, g: Ground, narrow: Boolean) {
        if (!ready) { col.addView(text(" ", T.HEAD_L, g.ink), full()); return }   // 목록을 처음 받기 전엔 자리만(0개 → N개로 튀지 않게)
        // 가족 0명(C13): 대기 문구 대신 초대 쪽 확정 문구(문구 은행 #71)를 제목으로
        val empty = !d && noOneYet() && !Hub.demo && arrived + reserved == 0
        val big = { name: String, n: Int ->
            col.addView(text(name, T.TITLE_S, g.ink84, center = !narrow).apply { importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO }, full())
            col.addView(text("${n}개", T.HEAD_L, g.ink, center = !narrow, w = T.W7), full())
            col.getChildAt(col.childCount - 1).contentDescription = "$name ${n}개"
        }
        when {
            empty -> col.addView(text("연결된 사람이 없습니다", T.TITLE, g.ink, bold = true, center = !narrow), full())
            arrived > 0 -> big("도착한 음성 메시지", arrived)
            reserved > 0 -> big("예약된 음성 메시지", reserved)
            else -> col.addView(text("예약된 음성 메시지가 없습니다", T.TITLE, g.ink, bold = true, center = !narrow), full())
        }
    }

    /** 주차 목록(11/09): [모두 듣기](1개면 [듣기]) + 받은 차례 줄. 줄 = 들은 메시지 줄과 같은 꼴(높이 100, 얼굴 칸 64·모서리 16, 사이 1px 선).
     *  윗줄 "엄마님 · 비 올 때"(28/400), 아랫줄 받은 시각 "오후 3:12"(24/400 64%, 지난날 것은 '어제'). 세로 창은 2줄·가로 창 기둥은 3줄까지 보이고 나머지는 밀어서. */
    private fun parkRows(col: LinearLayout, list: List<Hidden>, g: Ground, narrow: Boolean) {
        col.addView(primary(if (list.size == 1) "듣기" else "모두 듣기") { if (Hub.service?.playMissed() != true) Hub.log("못 들은 메시지를 지금 틀 수 없음") },
            LinearLayout.LayoutParams(-2, -2).apply { topMargin = 24.dp })
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        list.forEachIndexed { i, h ->
            if (i > 0) box.addView(View(this).apply { setBackgroundColor(g.line) }, LinearLayout.LayoutParams(-1, 1.dp))
            box.addView(parkRow(h, g), full())
        }
        val max = if (narrow) 3 else 2
        if (list.size > max) {
            val sv = android.widget.ScrollView(this).apply { isVerticalScrollBarEnabled = true; overScrollMode = View.OVER_SCROLL_NEVER; addView(box, FrameLayout.LayoutParams(-1, -2)) }
            col.addView(sv, LinearLayout.LayoutParams(-1, (max * 100 + max - 1).dp).apply { topMargin = 16.dp })
        } else col.addView(box, full().apply { topMargin = 16.dp })
    }

    private fun parkRow(h: Hidden, g: Ground): View {
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = 100.dp; setPadding(8.dp, 16.dp, 8.dp, 16.dp) }
        row.addView(senderTile(h, 16), LinearLayout.LayoutParams(64.dp, 64.dp).apply { marginEnd = 20.dp })
        val c = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val top = "${who(h) ?: "음성 메시지"} · ${momentText(h)}"
        c.addView(text(top, T.BODY, g.ink).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END })
        val at = Hub.service?.receivedAt(h)?.let { whenText(it) }
        if (at != null) c.addView(text(at, T.LABEL, g.sub).apply { setPadding(0, 4.dp, 0, 0) })
        row.addView(c, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(Icon(this, "play", g.sub), LinearLayout.LayoutParams(32.dp, 32.dp).apply { marginStart = 12.dp })
        pressable(row, Color.TRANSPARENT, g.doorDown, Color.TRANSPARENT, radius = 24) { if (Hub.service?.playMissed(h.id) != true) Hub.log("이 메시지를 지금 틀 수 없음") }
        row.contentDescription = listOfNotNull(top, at?.let { "${it}에 받음" }).joinToString(", ")
        return row
    }

    /** 광장을 눌렀다(정차): 사람(걷는 중이어도 지금 자리) → 그 사람이 손을 들고 카드, 회색 '+' 쿠션 → 초대 코드 만들기, 빈 곳 → 카드·들은 뒤 패널 닫기. */
    private fun plazaTap(x: Float, y: Float, mode: String?) {
        if (driving()) return
        val hit = if (mode == null || mode == "card" || mode == "after" || mode == "nudge") plaza?.pick(x, y) else null
        when (hit?.kind) {
            PlazaView.Hit.PERSON -> { plaza?.react(hit.slot); plazaCard = hit.slot; plazaAfter = null; render() }
            PlazaView.Hit.INVITE -> { plazaCard = 0; inviteFirst() }
            null -> {
                if (demoPlaza != null && mode != "arrive" && mode != "play") { endDemoTour(); plazaCard = 0; render() }
                else if (plazaCard != 0 || plazaAfter != null) { plazaCard = 0; plazaAfter = null; render() }
            }
        }
    }

    private fun bustOf(p: PlazaPerson): Bitmap = busts.getOrPut(p) { Plaza.bust(p, 256) }
    /** 웹이 올린 3D 얼굴 그림(받아 둔 것). 없으면 null. */
    private fun shotOf(p: PlazaPerson): Bitmap? {
        val v = Hub.invites?.firstOrNull { it.code == p.code }?.bust ?: return null
        val f = Store.bustFile(this, v)
        if (!f.exists()) return null
        return bitmaps.getOrPut(f.path) { runCatching { BitmapFactory.decodeFile(f.path) }.getOrNull() }
    }

    /** 패널 공통 틀(63번 4장): 흰 면(밤 #313236) 모서리 32, 그림자 8, 안쪽 여백 40. 꼬리(40×20)는 패널 위 가운데에서 원판을 가리킨다. */
    private fun panelShell(h: Int, tail: Boolean): Pair<FrameLayout, FrameLayout> {
        val outer = FrameLayout(this).apply { clipChildren = false; clipToPadding = false }
        val face = C.POPUP
        if (tail) outer.addView(object : View(this) {
            private val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = face }
            override fun onDraw(c: Canvas) { c.drawPath(android.graphics.Path().apply { moveTo(0f, height.toFloat()); lineTo(width / 2f, 0f); lineTo(width.toFloat(), height.toFloat()); close() }, p) }
        }.apply { elevation = 8.dp.toFloat() }, FrameLayout.LayoutParams(40.dp, 21.dp, Gravity.TOP or Gravity.START).apply { leftMargin = 400.dp })
        val panel = FrameLayout(this).apply {
            background = GradientDrawable().apply { setColor(face); cornerRadius = 32.dp.toFloat() }
            elevation = 8.dp.toFloat(); isClickable = true
        }
        outer.addView(panel, FrameLayout.LayoutParams(792.dp, h.dp, Gravity.TOP or Gravity.START).apply { leftMargin = 24.dp; topMargin = if (tail) 20.dp else 0 })
        outer.setPadding(0, 0, 0, 12.dp)
        return outer to panel
    }

    /** 가로 창 오른쪽 기둥의 패널(C1): 기둥 폭을 꽉 채우고 위에서 아래로 쌓는다(높이는 내용대로). 꼬리 없음. */
    private fun stackShell(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; setPadding(40.dp, 40.dp, 40.dp, 40.dp); isClickable = true
        background = GradientDrawable().apply { setColor(C.POPUP); cornerRadius = 32.dp.toFloat() }
        elevation = 8.dp.toFloat()
    }

    /** 패널 안 한 칸을 (x, y) dp 자리에 둔다(패널 왼쪽 위 기준). */
    private fun at(panel: FrameLayout, v: View, x: Int, y: Int, w: Int, h: Int) =
        panel.addView(v, FrameLayout.LayoutParams(if (w < 0) w else w.dp, if (h < 0) h else h.dp, Gravity.TOP or Gravity.START).apply { leftMargin = x.dp; topMargin = y.dp })

    /** 보낸 사람 얼굴 칸(광장의 대표색 + 어깨 위 그림). 모를 때·이름을 숨길 때는 회색 칸 + 사람 아이콘 64%. */
    private fun faceTile(p: PlazaPerson?, radius: Int = 24): View = FrameLayout(this).apply {
        // 웹이 캐릭터와 같이 올린 3D 얼굴 그림이 있으면 웹 아이콘과 같게: 대표색 18% 바탕 + 그 그림. 없으면 예전 그림(대표색 바탕)
        val shot = p?.let { shotOf(it) }
        val base = p?.let { Plaza.color(it.color) } ?: C.LINE
        background = GradientDrawable().apply { setColor(if (shot != null) Color.argb(0x2E, Color.red(base), Color.green(base), Color.blue(base)) else base); cornerRadius = radius.dp.toFloat() }
        clipToOutline = true
        outlineProvider = object : android.view.ViewOutlineProvider() { override fun getOutline(view: View, o: android.graphics.Outline) { o.setRoundRect(0, 0, view.width, view.height, radius.dp.toFloat()) } }
        if (p != null) addView(ImageView(this@MainActivity).apply { setImageBitmap(shot ?: bustOf(p)); scaleType = ImageView.ScaleType.CENTER_CROP }, FrameLayout.LayoutParams(-1, -1))
        else addView(Icon(this@MainActivity, "person", C.SUB), FrameLayout.LayoutParams(-1, -1).apply { setMargins(radius.dp / 2 + 8.dp, radius.dp / 2 + 8.dp, radius.dp / 2 + 8.dp, radius.dp / 2 + 8.dp) })
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
    }

    /** 이름 줄: 4글자까지 48 한 줄, 더 길면 40으로 한 단계(말줄임 없음). 가로 창 패널(wrap)은 두 줄까지 줄을 바꾼다. 굵기 700(패널 이름). */
    private fun nameLine(s: String, size: Float, small: Float, room: Int = 560, wrap: Boolean = false): TextView {
        val t = text(s, size, C.INK, w = T.W7).apply { maxLines = if (wrap) 2 else 1 }
        if (t.paint.measureText(s) > room.dp) t.textSize = small
        return t
    }

    private val panelSub get() = Color.argb(163, Color.red(C.INK), Color.green(C.INK), Color.blue(C.INK))   // 64%

    /** 안내 줄(75번 B 세트 1, 라벨형): 핸들 버튼 아이콘 40 + "핸들 가운데 버튼으로 듣기"(재생 중엔 "…멈추기") 32/600 한 줄. */
    private fun wheelHint(verb: String = "듣기") = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
        addView(Icon(this@MainActivity, "wheel", C.INK), LinearLayout.LayoutParams(40.dp, 40.dp).apply { marginEnd = 16.dp })
        // 가로 창 기둥처럼 좁으면 어절 자리에서 두 줄로(안드로이드는 한글을 글자 단위로 끊는다)
        val t = text("핸들 가운데 버튼으로 $verb", T.TITLE_S, C.INK, bold = true).apply { maxLines = 2 }
        addView(t, LinearLayout.LayoutParams(0, -2, 1f))
        addOnLayoutChangeListener { _, l, _, r, _, _, _, _, _ ->
            val room = (r - l) - 56.dp
            val one = "핸들 가운데 버튼으로 $verb"
            val want = if (room > 0 && t.paint.measureText(one) > room) "핸들 가운데 버튼으로\n$verb" else one
            if (t.text.toString() != want) t.post { t.text = want }
        }
    }

    /** 주행 중 듣기 카드의 남은 시간 막대(11/09 사용자 요청). 핸들 버튼을 받는 8초가 지나는 만큼 왼쪽으로 줄어든다(한 번만, 깜빡임·숫자·색 바뀜 없음).
     *  안내 음성이 나오는 동안은 꽉 찬 채로 멈춰 있다(Hub.askEndsAt == 0). 색·두께는 재생 막대와 같은 값(바탕 #E0E1E6, 채움 #44464E, 6). */
    private inner class TimeBar(ctx: Context) : View(ctx) {
        private val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
        init { importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO }
        override fun onDraw(c: Canvas) {
            val end = Hub.askEndsAt
            val ratio = if (end == 0L) 1f else ((end - SystemClock.elapsedRealtime()).toFloat() / Hub.askWindowMs).coerceIn(0f, 1f)
            val y = height / 2f; val r = 3.dp.toFloat()
            p.strokeWidth = 6.dp.toFloat()
            p.color = C.LINE; c.drawLine(r, y, width - r, y, p)
            if (ratio > 0f) { p.color = C.PRIMARY; c.drawLine(r, y, r + (width - 2 * r) * ratio, y, p) }
            if (end != 0L && ratio > 0f) postInvalidateOnAnimation()
        }
    }
    // 막대 아래 줄('주차하면 들을 수 있습니다')은 11/10 사용자 결정으로 뺐다: 시간이 지나면 개수 아래 '도착한 메시지 N개 · 주차 후 듣기'가 같은 사실을 보여 준다

    /** 재생 패널 한 장: 도착 → 재생 → 들은 뒤가 같은 틀 안에서 바뀐다(53번 2절). 주행 중엔 누를 것이 없고, 재생 막대·시간 숫자도 숨긴다(P에서만).
     *  group: 주차해서 여러 사람 것을 이어 들은 뒤(C5)의 대표 메시지들(사람마다 하나, 2명 이상일 때만). wide: 가로 창 오른쪽 기둥. */
    private fun panelView(mode: String, h: Hidden, hero: PlazaPerson?, d: Boolean, wide: Boolean, group: List<Hidden>?): View {
        val sub = panelSub
        val momentLine = (if (h.example || Hub.demo) "예시 · " else "") + momentText(h)
        val title = when (mode) {
            "arrive" -> if (d) Hub.service?.whose(h) ?: "음성 메시지" else whose(h)   // "지윤님 메시지"(75번 B 세트 1)
            "play" -> whose(h)   // "○○님 메시지" + 아래 줄 순간(63번 4장)
            else -> who(h) ?: "음성 메시지"
        }
        val line = when (mode) {
            "arrive" -> ""
            "play" -> momentLine   // 이어 들을 때 남은 것은 ⏭ 원이 알려 준다
            else -> if (gone(h)) "남긴 사람이 지운 메시지입니다" else afterLine(h)   // 들은 뒤 아래 줄 '집 근처에 왔을 때 · 오후 11:40'(75번 B 세트 1)
        }
        val close = { plazaAfter = null }
        val shut = { if (demoPlaza != null) endDemoTour(); plazaAfter = null }   // ✕: 예시 가족 체험 중이면 체험도 끝낸다
        val skip = mode == "play" && !d && Hub.arrivalLeft > 1
        if (wide) {
            val p = stackShell()
            if (mode == "after" && group != null) p.addView(LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.TOP
                addView(groupRow(group, h, wide = true), LinearLayout.LayoutParams(0, -2, 1f))
                addView(closeX { shut() }, LinearLayout.LayoutParams(76.dp, 76.dp))
            }, full().apply { bottomMargin = 24.dp })
            else {
                val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                top.addView(faceTile(hero), LinearLayout.LayoutParams(112.dp, 112.dp))
                top.addView(grow0())
                if (mode == "after") top.addView(closeX { shut() }, LinearLayout.LayoutParams(76.dp, 76.dp))
                if (!d && mode != "after") top.addView(playCircle(mode, h), LinearLayout.LayoutParams(100.dp, 100.dp))
                if (skip) top.addView(skipCircle(), LinearLayout.LayoutParams(80.dp, 80.dp).apply { marginStart = 16.dp })
                p.addView(top, full().apply { bottomMargin = 20.dp })
            }
            p.addView(nameLine(title, if (mode == "arrive") T.TITLE_L else T.HEAD_S, T.TITLE_L, wrap = true).apply { maxWidth = Int.MAX_VALUE }, full())
            if (mode == "arrive") {
                p.addView(wheelHint(), full().apply { topMargin = 16.dp })
                // 주행 중: 남은 시간 막대만(아래 줄 없음, 11/10)
                if (d) p.addView(TimeBar(this), LinearLayout.LayoutParams(-1, 24.dp).apply { topMargin = 20.dp })
            }
            else {
                p.addView(text(line, T.BODY, sub).apply { maxLines = 2; ellipsize = android.text.TextUtils.TruncateAt.END; setPadding(0, 8.dp, 0, 0) }, full())
                if (mode == "play" && d) p.addView(wheelHint("멈추기"), full().apply { topMargin = 20.dp })
            }
            if (mode == "after") p.addView(stackAfter(h, close), full().apply { topMargin = 24.dp })
            else if (!d) stackBars(p, mode, h, hero)
            return p
        }
        val grouped = mode == "after" && group != null
        // 높이: 들은 뒤 = 이모티콘 줄·선·버튼 줄까지(484, 묶음 576, 지운 메시지 332·424) / 재생 360(주행 중 272: 막대·시간 없이 '…멈추기' 줄) / 도착 428(주행 중 320)
        val ph = when { grouped -> reactPanelH(h, 284); mode == "after" -> reactPanelH(h, 192); mode == "arrive" -> if (d) 320 else 428; mode == "play" && d -> 272; else -> 360 }
        val (outer, panel) = panelShell(ph, tail = true)
        if (grouped) {
            // 얼굴 줄(최대 5): 누르면 그 사람의 들은 뒤로. 아래 이름·줄·버튼은 고른 사람 것
            at(panel, groupRow(group!!, h, wide = false), 40, 32, 712, 104)
            at(panel, nameLine(title, T.HEAD_S, T.TITLE_L, room = 712), 40, 160, 712, 56)
            at(panel, text(line, T.BODY, sub).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END }, 40, 224, 712, 36)
            absAfter(panel, h, 284, close)
            at(panel, closeX { shut() }, 676, 40, 76, 76)
            return outer
        }
        at(panel, faceTile(hero), 40, 40, 128, 128)
        if (mode == "arrive") {
            at(panel, nameLine(title, T.TITLE_L, T.TITLE), 192, 80, 560, 52)
            at(panel, wheelHint(), 40, 192, 712, -2)   // 한 줄(40)
            // 주행 중: 남은 시간 막대만. 버튼은 없다(핸들 가운데 버튼이 주인공, 안 누르면 도착한 메시지로 남는다)
            if (d) at(panel, TimeBar(this), 40, 256, 712, 24)
        } else if (mode == "after") {
            at(panel, nameLine(title, T.HEAD_S, T.TITLE_L, room = 476), 192, 52, 476, 56)   // 오른쪽 위 ✕ 자리만큼 좁힌다
        } else {
            at(panel, nameLine(title, T.HEAD_S, T.TITLE_L), 192, 52, 560, 56)
            at(panel, text(line, T.BODY, sub).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END }, 192, 116, 560, 36)
            if (d) at(panel, wheelHint("멈추기"), 40, 192, 712, -2)   // 주행 중 재생: '핸들 가운데 버튼으로 멈추기'
        }
        if (mode == "after") { absAfter(panel, h, 192, close); at(panel, closeX { shut() }, 676, 40, 76, 76); return outer }
        if (d) return outer   // 주행 중: 재생 막대·시간 숫자·버튼 없음
        // 파장: 둥근 세로 막대 20개(높이 고정), 들은 만큼만 대표색. 시간은 양 끝. 이어 들을 때는 ⏭ 원 자리만큼 막대를 줄인다
        val y = if (mode == "arrive") 256 else 200   // 도착: 한 줄 안내(192~232) 아래
        val bw = if (skip) 486 else 586
        val bars = PanelBars(this, h.id, hero?.let { Plaza.barColor(it.color) } ?: C.PRIMARY)
        if (mode == "play") panelBars = bars
        at(panel, bars, 40, y, bw, 88)
        val total = if (mode == "play") "" else (Hub.lenMs(this, h.id) ?: h.lenMs)?.let { clock(fullLen(it.toInt())) } ?: ""
        val now = text("0:00", T.LABEL, sub)
        val all = text(total, T.LABEL, sub).apply { gravity = Gravity.END }
        at(panel, now, 40, y + 100, 200, 32)
        at(panel, all, 40 + bw - 200, y + 100, 200, 32)
        if (mode == "play") { panelNow = now; panelAll = all }
        // 멈춤 원(P에서만): 도착이면 ▶ 듣기, 재생 중이면 ‖ / 멈췄으면 ▶. 이어 들을 때는 오른쪽에 ⏭ 원
        if (skip) { at(panel, playCircle(mode, h), 568, y - 6, 100, 100); at(panel, skipCircle(), 688, y + 4, 80, 80) }
        else at(panel, playCircle(mode, h), 668, y - 6, 100, 100)
        return outer
    }

    private fun grow0() = View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 1, 1f) }

    /** 패널 오른쪽 위 닫기 ✕(63번·73번 4-6): Pleos 아이콘 버튼 Plain, 아이콘 40·누르는 칸 76. 누르면 닫고 다시 그린다. */
    private fun closeX(onClose: () -> Unit): View = FrameLayout(this).apply {
        contentDescription = "닫기"
        pressable(this, Color.TRANSPARENT, C.CARD_DOWN, Color.TRANSPARENT, oval = true) { onClose(); render() }
        addView(Icon(this@MainActivity, "close", C.INK), FrameLayout.LayoutParams(40.dp, 40.dp, Gravity.CENTER))
    }

    /** 멈춤 원: 도착이면 ▶ 듣기, 재생 중이면 ‖ / 멈췄으면 ▶. 예시 가족 체험(C13)의 도착이면 예시 목소리를 바로 튼다. */
    private fun playCircle(mode: String, h: Hidden): View {
        val playIcon = mode == "arrive" || Hub.paused
        val circle = FrameLayout(this).apply { contentDescription = if (mode == "arrive") "듣기" else if (Hub.paused) "이어 듣기" else "일시정지" }
        pressable(circle, C.CARD, C.CARD_DOWN, C.CARD, oval = true) {
            if (mode == "arrive") { if (h.example && demoPlaza != null) demoPlay() else Hub.service?.listenNow() } else Hub.service?.togglePause()
        }
        circle.addView(Icon(this, if (playIcon) "play" else "pause", C.INK), FrameLayout.LayoutParams(44.dp, 44.dp, Gravity.CENTER))
        return circle
    }

    /** 다음 메시지 원(63번 4장): 주차해서 이어 들을 때 재생 원 오른쪽, 80 · #F3F3F3 · 아이콘 36. 넘긴 것은 들은 메시지 화면에서 들을 수 있다. */
    private fun skipCircle(): View = FrameLayout(this).apply {
        contentDescription = "다음 메시지"
        pressable(this, C.CARD, C.CARD_DOWN, C.CARD, oval = true) { Hub.service?.skipToNext() }
        addView(Icon(this@MainActivity, "skip", C.INK), FrameLayout.LayoutParams(36.dp, 36.dp, Gravity.CENTER))
    }

    /** 가로 창 패널의 막대·시간(도착·재생, P에서만). */
    private fun stackBars(p: LinearLayout, mode: String, h: Hidden, hero: PlazaPerson?) {
        val bars = PanelBars(this, h.id, hero?.let { Plaza.barColor(it.color) } ?: C.PRIMARY)
        if (mode == "play") panelBars = bars
        p.addView(bars, LinearLayout.LayoutParams(-1, 72.dp).apply { topMargin = 24.dp })
        val times = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, 8.dp, 0, 0) }
        val total = if (mode == "play") "" else (Hub.lenMs(this, h.id) ?: h.lenMs)?.let { clock(fullLen(it.toInt())) } ?: ""
        val now = text("0:00", T.LABEL, panelSub)
        val all = text(total, T.LABEL, panelSub).apply { gravity = Gravity.END }
        times.addView(now, LinearLayout.LayoutParams(0, -2, 1f)); times.addView(all, LinearLayout.LayoutParams(0, -2, 1f))
        p.addView(times, full())
        if (mode == "play") { panelNow = now; panelAll = all }
    }

    // ---------- 들은 뒤: 이모티콘 줄(내용 쪽) · 1px 선 · [답장][다시 듣기](할 일) (C4·C5·C6·C7 같은 꼴) ----------
    // 11/08 사용자 확정: '잘 들었습니다' 버튼 대신 이모티콘 5개 중 하나(카톡 공감처럼). 답장과 '둘 중 하나'로 보이지 않게 자리를 나눈다:
    // 이모티콘은 메시지 정보 바로 아래, 답장·다시 듣기는 맨 아래 버튼 줄. 이모티콘을 보내도 [답장]은 그대로, 답장을 보낸 뒤에도 이모티콘은 다시 고를 수 있다

    private val EMOJI_NAME = listOf("하트", "좋아요", "웃음", "놀람", "슬픔")   // 읽어 주기용 이름(REACTIONS 순서)
    private val reacted = mutableMapOf<String, String>()   // 메시지 id → 이번에 고른 이모티콘(예시 메시지 포함)
    private var reacting: Pair<String, String>? = null     // 보내는 중(메시지 id, 이모티콘): 다시 누름 막기
    private fun replyDone(h: Hidden) = answered[h.id] == "답장 보냄" || answered[h.id] == DEMO_SENT || (!h.example && (h.id in repliedToday() || h.replied || Hub.repliedAt(this, h.id) != null))
    /** 이 메시지에 고른 이모티콘(없으면 null). 예시 메시지는 이번에 누른 것만. */
    private fun reactionOf(h: Hidden): String? = reacted[h.id] ?: if (h.example) null else Hub.reactionOf(this, h.id) ?: h.reaction
    private fun reactDone(h: Hidden) = reactionOf(h) != null

    private fun panelStatus(s: String) = text(s, T.BODY, panelSub, center = true).apply { maxLines = 2 }
    private fun replySlot(h: Hidden, close: () -> Unit): View =
        if (replyDone(h)) panelStatus(answered[h.id] ?: "답장 보냄")
        else panelButton("답장", true) { close(); if (h.example) endDemoTour(); startReply(h) }
    private fun replaySlot(h: Hidden, close: () -> Unit): View = panelButton("다시 듣기", false) {
        close()
        if (h.example && demoPlaza != null) demoPlay() else if (h.example) playExample(h) else replay(h)
    }

    /** 이모티콘 원 다섯 줄(room: 쓸 수 있는 폭 dp). 원 지름 72·이모티콘 40·사이 16·누르는 칸 76, 아래 '보냄' 자리 28(늘 비워 둬서 줄 높이가 안 바뀐다).
     *  고른 원만 #F3F3F3 면 + #131417 테두리 2, 나머지는 면 없음. 가로 창 기둥이 좁으면 같은 비율로 줄인다. 높이 = 칸 + 28. */
    private fun emojiRow(h: Hidden, room: Int = 712, onSent: () -> Unit = {}): LinearLayout {
        val gap = if (room >= 5 * 76 + 4 * 16) 16 else 8
        val cell = minOf(76, (room - gap * 4) / 5).coerceAtLeast(56)
        val dia = cell - 4
        val sending = reacting?.takeIf { it.first == h.id }?.second
        val chosen = sending ?: reactionOf(h)
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        REACTIONS.forEachIndexed { i, e ->
            val on = e == chosen
            val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL; clipChildren = false }
            val hit = FrameLayout(this).apply {
                contentDescription = EMOJI_NAME[i] + when { on && sending != null -> ", 보내는 중"; on -> ", 보낸 반응"; else -> "" }
                isClickable = true
                setOnTouchListener(pressShrink)
                setOnClickListener { it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY); pickReaction(h, e, onSent) }
            }
            val face = FrameLayout(this).apply {
                fun oval(fill: Int, ring: Boolean) = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(fill); if (ring) setStroke(2.dp, C.INK) }
                background = StateListDrawable().apply {
                    addState(intArrayOf(android.R.attr.state_pressed), oval(C.CARD_DOWN, on))
                    addState(intArrayOf(), oval(if (on) C.CARD else Color.TRANSPARENT, on))
                }
                isDuplicateParentStateEnabled = true
                addView(TextView(this@MainActivity).apply {
                    text = e; textSize = 40f * dia / 72f; gravity = Gravity.CENTER; includeFontPadding = false
                    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                }, FrameLayout.LayoutParams(-1, -1))
            }
            hit.addView(face, FrameLayout.LayoutParams(dia.dp, dia.dp, Gravity.CENTER))
            // 보내는 중이면 고른 원 안에 도는 표시. 원 아래 '보냄' 글자는 뺐다(11/09: 누를 때마다 하나씩 보내는 것처럼 읽혀서 → 줄 위 '보낸 반응' 한 줄)
            if (on && sending != null) hit.addView(android.widget.ProgressBar(this@MainActivity).apply { isIndeterminate = true; indeterminateTintList = android.content.res.ColorStateList.valueOf(C.SUB) },
                FrameLayout.LayoutParams(32.dp, 32.dp, Gravity.CENTER))
            col.addView(hit, LinearLayout.LayoutParams(cell.dp, cell.dp))
            row.addView(col, LinearLayout.LayoutParams(cell.dp, -2).apply { if (i > 0) marginStart = gap.dp })
        }
        return row
    }
    private fun emojiRowH(room: Int = 712) = minOf(76, (room - (if (room >= 5 * 76 + 4 * 16) 16 else 8) * 4) / 5).coerceAtLeast(56)

    /** 이모티콘 줄 위 상태 한 줄(73번 4-6): 고르기 전 '반응', 보낸 뒤 '보낸 반응'. 하나만 남고 바꿀 수 있다. */
    private fun reactLabel(h: Hidden, center: Boolean = false) = text(if (reactDone(h)) "보낸 반응" else "반응", T.LABEL, panelSub, center = center)

    /** 이모티콘 줄과 버튼 줄 사이 1px 선(#E0E1E6, 밤 #3A3B40). */
    private fun reactLine() = View(this).apply { setBackgroundColor(C.LINE); importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO }

    /** 맨 아래 버튼 줄: [답장](주 버튼 #44464E) [다시 듣기](보조). 답장 안 한 메시지 카드는 [다시 듣기] 대신 [닫기](third). */
    private fun actionRow(h: Hidden, close: () -> Unit, third: View? = null) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        addView(replySlot(h, close), LinearLayout.LayoutParams(0, 100.dp, 1f).apply { marginEnd = 16.dp })
        addView(third ?: replaySlot(h, close), LinearLayout.LayoutParams(0, 100.dp, 1f))
    }

    /** 세로 창 패널(792 폭, 안쪽 712)의 들은 뒤 아래쪽: y부터 이모티콘 줄 → 24 → 선 → 24 → 버튼 줄(100). 지운 메시지는 [닫기]만.
     *  패널 높이는 reactPanelH(y)로 맞춘다. third가 있으면(답장 안 한 메시지 카드) 지난날 메시지라 지운 메시지로 보지 않는다(예전과 같게). */
    private fun absAfter(panel: FrameLayout, h: Hidden, y: Int, close: () -> Unit, third: View? = null, onSent: () -> Unit = {}) {
        if (third == null && gone(h)) { at(panel, panelButton("닫기", false) { close(); render() }, 576, y, 176, 100); return }
        val eh = emojiRowH()
        at(panel, reactLabel(h), 40, y, 712, 28)
        at(panel, emojiRow(h, 712, onSent), 40, y + 40, 712, eh)
        at(panel, reactLine(), 40, y + 40 + eh + 24, 712, 1)
        at(panel, actionRow(h, close, third), 40, y + 40 + eh + 49, 712, 100)
    }
    /** absAfter를 y에 둔 패널 높이(아래 여백 40 포함). 지운 메시지는 [닫기] 한 줄. */
    private fun reactPanelH(h: Hidden, y: Int, nudge: Boolean = false) = if (!nudge && gone(h)) y + 100 + 40 else y + 40 + emojiRowH() + 49 + 100 + 40

    /** 가로 창 기둥 패널의 들은 뒤 아래쪽(위에서 아래로 쌓는다). 기둥이 좁으면 이모티콘 원을 줄인다. */
    private fun stackAfter(h: Hidden, close: () -> Unit, third: View? = null, onSent: () -> Unit = {}): View {
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        if (third == null && gone(h)) { col.addView(panelButton("닫기", false) { close(); render() }, LinearLayout.LayoutParams(-1, 100.dp)); return col }
        val room = (resources.configuration.screenWidthDp * 0.4f - 64 - 80).toInt()
        col.addView(reactLabel(h), full().apply { bottomMargin = 12.dp })
        col.addView(emojiRow(h, room, onSent), LinearLayout.LayoutParams(-2, -2))
        col.addView(reactLine(), LinearLayout.LayoutParams(-1, 1.dp).apply { topMargin = 24.dp; bottomMargin = 24.dp })
        col.addView(actionRow(h, close, third), full())
        return col
    }

    /** 이모티콘을 고르면 서버에 보낸다(차 인증은 다른 요청과 같다). 하나만: 다른 걸 고르면 바뀌고, 같은 걸 다시 누르면 그대로(취소 없음).
     *  못 보내면 전에 고른 상태로 돌아가 다시 누를 수 있다(답장 보내기와 같은 방식). 예시 메시지는 보내지 않는다. */
    private fun pickReaction(h: Hidden, emoji: String, onSent: () -> Unit = {}) {
        if (reacting != null || !stopped()) return
        if (reactionOf(h) == emoji) return
        // 보낸 이모티콘이 그 사람에게 날아가고 그 사람이 손을 흔든다(64번 28, 운전자가 누른 직후라 비밀 규칙과 무관). 못 보냈으면 날리지 않는다
        val fly = { (demoPlaza ?: Hub.plaza)?.let { d -> heroOf(h, d)?.let { plaza?.flyEmoji(it.slot, emoji) } }; Unit }
        if (Hub.demo || h.example) {
            // 예시 메시지는 서버로 보내지 않는다(답장 예시와 같은 규칙)
            reacted[h.id] = emoji
            Hub.log("체험 메시지라 반응은 보내지 않음"); render(); toast(DEMO_SENT); fly()
            return
        }
        val before = reactionOf(h)
        reacting = h.id to emoji; render()
        io.execute {
            val r = runCatching { Api.react(h.id, emoji) }
            main.post {
                reacting = null
                Hub.log(if (r.isSuccess) "${nim(h.sender)}에게 반응 보냄 $emoji" else "반응 실패: ${r.exceptionOrNull()?.message}")
                if (r.isSuccess) {
                    Hub.setReacted(this, h.id, emoji); reacted[h.id] = emoji
                    onSent(); render(); fly()
                    toast(if (before == null) "반응을 보냈습니다" else "반응을 바꿨습니다")
                } else {
                    render(); toast(if (r.exceptionOrNull() is java.io.IOException) "인터넷에 연결되지 않아 보내지 못했습니다" else "보내지 못했습니다")
                }
            }
        }
    }

    // ---------- 이어 들은 뒤 얼굴 줄(C5) ----------

    /** 이번 주차에서 이어 들은 메시지 중 사람마다 마지막 것(들은 순서, 최대 5). 지금 패널 메시지가 그 안에 있고 2명 이상일 때만. */
    private fun groupFor(h: Hidden, d: PlazaData?): List<Hidden>? {
        if (namesHidden() || h.example) return null
        val chain = Hub.parkHeard
        if (chain.none { it.id == h.id }) return null
        val order = chain.map { it.invite ?: it.sender }.distinct()
        if (order.size < 2) return null
        return order.take(5).map { k -> chain.last { (it.invite ?: it.sender) == k } }
    }

    /** 얼굴 칸 한 줄: 고른 사람은 테두리, 답장·반응을 보낸 사람은 체크 표시. 누르면 그 사람 [답장]·[다시 듣기]로. */
    private fun groupRow(group: List<Hidden>, picked: Hidden, wide: Boolean): View {
        val data = Hub.plaza
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val size = if (wide) minOf(104, ((resources.configuration.screenWidthDp * 0.4f - 40 - 64 - 12 * 4) / 5).toInt()).coerceAtLeast(56) else 104
        val gap = if (wide) 12 else 20
        group.forEachIndexed { i, m ->
            val p = heroOf(m, data)
            val on = m.id == picked.id
            val sent = replyDone(m) || reactDone(m)
            val cell = FrameLayout(this).apply {
                clipChildren = false
                setPadding(if (on) 6.dp else 0, if (on) 6.dp else 0, if (on) 6.dp else 0, if (on) 6.dp else 0)
                if (on) background = GradientDrawable().apply { cornerRadius = 30.dp.toFloat(); setStroke(3.dp, C.INK) }   // 고른 얼굴: #131417 테두리 3
                contentDescription = listOfNotNull(who(m) ?: "음성 메시지", if (on) "선택됨" else null, if (sent) (if (replyDone(m)) "답장 보냄" else "반응 보냄") else null).joinToString(", ")
                setOnTouchListener(pressShrink)
                setOnClickListener { it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY); if (!on) { plazaAfter = m; render() } }
            }
            cell.addView(faceTile(p), FrameLayout.LayoutParams(-1, -1))
            if (sent) cell.addView(FrameLayout(this).apply {
                background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(C.POPUP); setStroke(2.dp, C.LINE) }
                addView(Icon(this@MainActivity, "check", C.INK), FrameLayout.LayoutParams(26.dp, 26.dp, Gravity.CENTER))
            }, FrameLayout.LayoutParams(36.dp, 36.dp, Gravity.BOTTOM or Gravity.END))
            row.addView(cell, LinearLayout.LayoutParams(size.dp, size.dp).apply { if (i > 0) marginStart = gap.dp })
        }
        return row
    }

    // ---------- 쿠션 카드(C6) ----------

    /** 그 사람에게서 오늘 끝까지 들은 메시지 중 가장 최근 것. 안 들은 것(넘긴 것 포함)은 보여 주지 않는다(숨김 규칙). 이름을 숨길 때·체험 중엔 없음. */
    private fun lastHeardFrom(p: PlazaPerson): Hidden? {
        if (namesHidden() || demoPlaza != null) return null
        return Hub.heardListToday(this).firstOrNull { it.id in Hub.heard && !it.example && (it.invite == p.code || (it.invite == null && p.name != null && it.sender == p.name)) }
    }

    /** 사람 쿠션을 눌렀을 때: 그 사람에게서 최근 들은 메시지 1개(순간) + 이모티콘 줄 + [답장][다시 듣기].
     *  들은 게 없으면 이름 + "오늘 들은 메시지 없음"(닫기 없음, 빈 곳을 누르거나 뒤로 가면 닫힌다). */
    private fun cardView(p: PlazaPerson, wide: Boolean): View {
        val m = lastHeardFrom(p)
        val close = { plazaCard = 0 }
        val line = m?.let { msg -> afterLine(msg) } ?: "오늘 들은 메시지 없음"
        if (wide) {
            val c = stackShell()
            val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            top.addView(faceTile(p), LinearLayout.LayoutParams(112.dp, 112.dp))
            top.addView(grow0())
            top.addView(closeX { close() }, LinearLayout.LayoutParams(76.dp, 76.dp))
            c.addView(top, full().apply { bottomMargin = 20.dp })
            c.addView(nameLine(p.label, T.HEAD_S, T.TITLE_L, wrap = true), full())
            c.addView(text(if (m != null && gone(m)) "남긴 사람이 지운 메시지입니다" else line, T.BODY, panelSub).apply { maxLines = 2; setPadding(0, 8.dp, 0, 0) }, full())
            if (m != null) c.addView(stackAfter(m, close), full().apply { topMargin = 24.dp })
            return c
        }
        if (m == null) {
            val (outer, panel) = panelShell(208, tail = false)
            at(panel, faceTile(p), 40, 40, 128, 128)
            at(panel, nameLine(p.label, T.HEAD_S, T.TITLE_L, room = 476), 192, 52, 476, 56)
            at(panel, text(line, T.BODY, panelSub), 192, 116, 560, 36)
            at(panel, closeX { close() }, 676, 40, 76, 76)
            return outer
        }
        val (outer, panel) = panelShell(reactPanelH(m, 192), tail = false)
        at(panel, faceTile(p), 40, 40, 128, 128)
        at(panel, nameLine(p.label, T.HEAD_S, T.TITLE_L, room = 476), 192, 52, 476, 56)
        at(panel, text(if (gone(m)) "남긴 사람이 지운 메시지입니다" else line, T.BODY, panelSub).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END }, 192, 116, 560, 36)
        absAfter(panel, m, 192, close)
        at(panel, closeX { close() }, 676, 40, 76, 76)
        return outer
    }

    // ---------- 답장 안 한 메시지 카드(C7) ----------

    /** 시동을 켜고 아직 정차 중 · 주행 중에 들은 메시지가 있는 채로 주차했을 때 한 장. 가장 최근 것 하나 + 남은 개수.
     *  이모티콘 줄 + [답장][닫기]. 닫으면 그 메시지는 다시 띄우지 않는다. 답장·반응을 이미 한 것은 목록(Hub.unreplied)에 없다.
     *  이모티콘을 보내도 카드는 그대로 둔다(nudgeHold: '보냄'을 보고 답장도 할 수 있게). 닫기·답장으로 내린다. */
    private fun nudgeView(list: List<Hidden>, hero: PlazaPerson?, wide: Boolean): View {
        val m = list.first()
        pastIds += m.id   // 지난날 들은 메시지라 오늘 목록에 없어도 지운 메시지로 보지 않는다(버튼 줄이 [닫기]만 남지 않게)
        // 11/08 사용자 확정: '아직' 없이 '답장하지 않은 ○○님의 음성 메시지'
        val title = "답장하지 않은 ${nim(m.sender)}의 음성 메시지"
        // '외 N개'는 뺐다(닫으면 볼 길이 없어서, 63번 4장). 아래 줄은 들은 뒤 한 줄과 같은 꼴
        val line = afterLine(m)
        val finish = { Hub.nudge = false; nudgeHold = null }
        val hold = { nudgeHold = m }
        val onReply = { finish(); pastIds += m.id }   // 지난 메시지로 보고 답장 결과 화면에서 '지운 메시지'로 잘못 보지 않게
        // 닫기는 오른쪽 위 ✕로 옮기고 버튼 줄은 다른 들은 뒤 패널처럼 [답장][다시 듣기](73번 4-6). 닫으면 이 메시지는 다시 띄우지 않는다
        val shut = { Hub.closeNudge(this, m.id); finish(); Hub.log("답장 카드 닫음: ${m.sender}") }
        if (wide) {
            val c = stackShell()
            c.addView(LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                addView(faceTile(hero), LinearLayout.LayoutParams(112.dp, 112.dp)); addView(grow0()); addView(closeX { shut() }, LinearLayout.LayoutParams(76.dp, 76.dp))
            }, full().apply { bottomMargin = 20.dp })
            c.addView(text(title, T.TITLE, C.INK, w = T.W7).apply { maxLines = 3 }, full())
            c.addView(text(line, T.BODY, panelSub).apply { maxLines = 2; setPadding(0, 8.dp, 0, 0) }, full())
            c.addView(stackAfter(m, onReply, onSent = hold), full().apply { topMargin = 24.dp })
            return c
        }
        val (outer, panel) = panelShell(reactPanelH(m, 192, nudge = true), tail = false)
        at(panel, faceTile(hero), 40, 40, 128, 128)
        at(panel, text(title, T.TITLE_S, C.INK, w = T.W7).apply { maxLines = 2; ellipsize = android.text.TextUtils.TruncateAt.END }, 192, 40, 476, 84)
        at(panel, text(line, T.BODY, panelSub).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END }, 192, 132, 560, 36)
        absAfter(panel, m, 192, onReply, onSent = hold)
        at(panel, closeX { shut() }, 676, 40, 76, 76)
        return outer
    }

    /** 패널 버튼: 주 버튼 진회색 #44464E·흰 글자, 보조 #F3F3F3(밤 흰색 12%). 모서리 32, 28/600(63번 4장). */
    private fun panelButton(label: String, primary: Boolean, onClick: () -> Unit) = text(label, T.BODY, if (primary) C.ON_INK else C.INK, bold = true, center = true).apply {
        if (primary) pressable(this, C.PRIMARY, C.PRIMARY_DOWN, C.PRIMARY, radius = 32, onClick = onClick)
        else pressable(this, C.CARD, C.CARD_DOWN, C.CARD, radius = 32, onClick = onClick)
    }

    // ---------- 가족 0명: 예시 가족 체험(C13) ----------
    // '예시 메시지 들어 보기'를 누르면 예시 가족 3명이 잠깐 쿠션에 앉고, 한 명(지윤님 · 주차했을 때)이 말 거는 자리로 나와 도착 → 재생 → 들은 뒤를 한 번 보여 준다.
    // 서버에는 아무것도 보내지 않는다(예시 메시지 규칙 그대로). 빈 곳을 누르거나 뒤로 가면, 또는 들은 뒤 10초가 지나면 원래 0명 화면으로.

    private var demoPlaza: PlazaData? = null
    private var demoStep: String? = null   // arrive · play · after
    private val demoMsg by lazy { Demo.examples().first { it.moment == "arrive" } }
    private val demoGo = Runnable { demoPlay() }
    private val demoEnd = Runnable { if (demoStep == "after") { endDemoTour(); render() } }

    private fun startDemoTour() {
        if (driving() || !plazaOk() || Hub.service == null) { examplesOpen = true; render(); return }
        demoPlaza = Plaza.demoData(); demoStep = "arrive"; plazaCard = 0; plazaAfter = null
        Hub.log("예시 가족 체험 시작")
        render()
        main.removeCallbacks(demoGo); main.postDelayed(demoGo, 3000)   // 도착 장면을 3초 보여 준 뒤 저절로 듣기(▶를 누르면 바로)
    }

    private fun demoPlay() {
        main.removeCallbacks(demoGo); main.removeCallbacks(demoEnd)
        if (demoPlaza == null || driving()) return
        val h = demoMsg
        demoStep = "play"; plazaAfter = null; render()
        io.execute {
            val r = runCatching { Demo.prepare(this, h) }
            main.post {
                val ok = r.isSuccess && demoPlaza != null && !driving() && Hub.service?.replay(h, onFail = { endDemoTour(); render() }) {
                    if (demoPlaza != null && !driving()) { demoStep = "after"; plazaAfter = h; main.postDelayed(demoEnd, 10_000) }
                    render()
                } == true
                if (!ok) { Hub.log("예시 목소리를 틀지 못해 체험 끝"); endDemoTour() }
                render()
            }
        }
    }

    private fun endDemoTour() {
        if (demoPlaza == null && demoStep == null) return
        main.removeCallbacks(demoGo); main.removeCallbacks(demoEnd)
        if (plazaAfter?.example == true) plazaAfter = null
        demoPlaza = null; demoStep = null; plazaCard = 0
        Hub.log("예시 가족 체험 끝")
    }

    // ---------- 자리 바꾸기(설정 → 차 주인만, P에서만) ----------

    /** 자리 1~5를 위에서부터 한 줄씩. 위·아래 버튼으로 옆 자리와 맞바꾸고 [저장]으로 서버에 보낸다. */
    private fun orderScreen(v: LinearLayout) {
        val d = Hub.plaza
        if (d == null || d.people.isEmpty()) {
            v.addView(text("연결된 사람이 없습니다", T.BODY_S, C.SUB).apply { setPadding(4.dp, 0, 0, 24.dp) })
            return
        }
        val draft = orderDraft ?: MutableList<String?>(5) { i -> d.bySlot(i + 1)?.code }.also { orderDraft = it }
        // [확인 필요] 새 문구: 안내 한 줄
        for (i in 0 until 5) {
            val p = d.people.firstOrNull { it.code == draft[i] }
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = 112.dp; setPadding(24.dp, 8.dp, 16.dp, 8.dp); background = box(C.CARD, C.CARD) }
            row.addView(text("${i + 1}", T.TITLE_S, C.SUB, center = true), LinearLayout.LayoutParams(48.dp, -2).apply { marginEnd = 16.dp })
            row.addView(if (p != null) faceTile(p, 16) else View(this).apply { background = box(C.LINE, C.LINE, radius = 16) },
                LinearLayout.LayoutParams(64.dp, 64.dp).apply { marginEnd = 20.dp })
            // [확인 필요] 새 문구 '빈 자리'
            row.addView(text(p?.label ?: "빈 자리", T.BODY, if (p != null) C.INK else C.SUB), LinearLayout.LayoutParams(0, -2, 1f))
            fun arrow(up: Boolean) = FrameLayout(this).apply {
                val can = !orderBusy && (if (up) i > 0 else i < 4) && (p != null || draft[if (up) i - 1 else i + 1] != null)
                contentDescription = if (up) "위로" else "아래로"   // [확인 필요] 읽어 주기 문구
                pressable(this, C.PAGE, C.CARD_DOWN, C.PAGE) {
                    if (!can) return@pressable
                    val j = if (up) i - 1 else i + 1
                    val t = draft[i]; draft[i] = draft[j]; draft[j] = t
                    render()
                }
                alpha = if (can) 1f else 0.3f
                // 꺾쇠 아이콘을 세워서 위·아래로
                addView(Icon(this@MainActivity, if (up) "back" else "next", C.INK).apply { rotation = 90f }, FrameLayout.LayoutParams(40.dp, 40.dp, Gravity.CENTER))
            }
            row.addView(arrow(true), LinearLayout.LayoutParams(96.dp, 80.dp).apply { marginEnd = 12.dp })
            row.addView(arrow(false), LinearLayout.LayoutParams(96.dp, 80.dp))
            v.addView(row, rowGap())
        }
        v.addView(space(16))
        val changed = (0 until 5).any { d.bySlot(it + 1)?.code != draft[it] }
        v.addView(if (orderBusy) busy(C.PRIMARY, "저장하는 중") else primary("저장") { if (changed) saveOrder(draft.toList()) else { orderOpen = false; orderDraft = null; render() } }, btnLp())
    }

    private fun saveOrder(draft: List<String?>) {
        if (orderBusy) return
        orderBusy = true; render()
        val slots = draft.mapIndexedNotNull { i, c -> c?.let { it to i + 1 } }.toMap()
        io.execute {
            val r = runCatching { Plaza.order(this, slots) }
            main.post {
                orderBusy = false
                r.onSuccess { d ->
                    Hub.log("자리 바꿈: ${slots.entries.joinToString { "${it.value}" }}")
                    orderOpen = false; orderDraft = null
                    Plaza.update(d); render()
                    toast("자리를 바꿨습니다")   // [확인 필요] 새 문구
                }.onFailure {
                    Hub.log("자리 바꾸기 실패: ${it.message}")
                    render(); toast(if (it is java.io.IOException) "인터넷에 연결되지 않아 바꾸지 못했습니다" else "바꾸지 못했습니다")
                }
            }
        }
    }

    /** 재생 패널의 둥근 세로 막대 20개. 높이는 메시지마다 정해져 움직이지 않고, 들은 만큼만 왼쪽부터 칠한다(주행 중에도 같은 규칙). */
    private inner class PanelBars(ctx: Context, seed: String, private val on: Int) : View(ctx) {
        // 서버 파장 값(wave[20])이 아직 없어 메시지 id로 정한 높이(32~88, 최소 32라 점으로 보이지 않게). [확인 필요] 서버가 녹음 때 20구간 소리 크기를 주면 그 값으로
        private val heights = kotlin.random.Random(seed.hashCode().toLong()).let { r -> FloatArray(20) { 32f + r.nextFloat() * 56f } }
        var ratio = 0f
            set(v) { val n = v.coerceIn(0f, 1f); val redraw = (n * 20).toInt() != (field * 20).toInt(); field = n; if (redraw) invalidate() }
        private val p = Paint(Paint.ANTI_ALIAS_FLAG)
        override fun onDraw(c: Canvas) {
            val filled = (ratio * 20).toInt()
            val u = width / 586f   // 이 칸의 1dp(패널이 줄어도 같은 비율)
            val cy = height / 2f
            for (i in 0 until 20) {
                p.color = if (i < filled) on else C.LINE
                val x = 30f * i * u; val bh = heights[i] * u
                c.drawRoundRect(x, cy - bh / 2, x + 16f * u, cy + bh / 2, 8f * u, 8f * u, p)
            }
        }
    }

    private fun prefs() = getSharedPreferences("sim", Context.MODE_PRIVATE)

    /** 오늘 답장한 메시지. 앱이 다시 떠도 유지하고, 날이 바뀌면 비어서 바로가기도 사라진다. */
    private fun repliedToday(): Set<String> =
        if (prefs().getString("repliedDate", null) == LocalDate.now().toString()) prefs().getStringSet("replied", emptySet())!! else emptySet()

    private fun markReplied(id: String) {
        prefs().edit().putString("repliedDate", LocalDate.now().toString()).putStringSet("replied", repliedToday() + id).apply()
        Hub.setReplied(this, id)   // 들은 메시지 줄의 '답장 보냄'(지난 메시지에도 남는다)
    }

    /** 예시 표시(예시 메시지라는 걸 어디서나 알 수 있게). 태그 모양: 면 #F3F3F3, 모서리 12, 24/600 64%(63번 4장). */
    private fun demoTag(s: String = "예시 메시지") = tagView(s)

    /** 반복 메시지의 지금 상태: 이번에 고른 것 → 못 보낸 선택 → 서버 값. null이면 고른 적 없음. */
    private fun repeatState(h: Hidden): Boolean? {
        repeatKeep[h.id]?.let { return it }
        Hub.unsentRepeats(this).firstOrNull { it.startsWith("${h.id}:") }?.let { return it.endsWith(":true") }
        val stopped = Hub.today.firstOrNull { it.id == h.id }?.stopped ?: h.stopped
        return if (stopped) false else if (Hub.repeatAsked(this, h.id)) true else null
    }

    /** 반복 메시지는 들은 뒤 화면에서 언제든 다음에도 들을지 바꿀 수 있다(그만 들었다가 되돌리기 포함).
     *  63번 4장: 회색 면 #F3F3F3 위 왼쪽 라벨 "다음에 비 올 때" + 오른쪽 두 칸 [듣기 | 그만 듣기]. 문장은 없다. showWho: 들은 메시지 화면 맨 위(누구 것인지 한 줄 위에). */
    private fun repeatCard(h: Hidden, showWho: Boolean = false): View {
        val state = repeatState(h)
        val card = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(32.dp, 16.dp, 16.dp, 16.dp); background = box(C.CARD, C.CARD, radius = 24) }
        val left = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        if (showWho) left.addView(text(whose(h), T.LABEL, C.SUB))
        val label = h.place?.let { "다음에 ${it.name} 근처에 왔을 때" } ?: NEXT_LABEL[h.moment] ?: "다음에도"
        left.addView(text(label, T.BODY, C.INK, bold = true))
        card.addView(left, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = 16.dp })
        val seg = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(4.dp, 4.dp, 4.dp, 4.dp); background = box(C.LINE, C.LINE, radius = 24) }
        listOf(true to "듣기", false to "그만 듣기").forEachIndexed { i, (keep, name) ->
            val on = state == keep
            val b = text(name, T.BODY, C.INK, center = true, w = if (on) T.W6 else T.W4).apply { minHeight = 80.dp; minWidth = 160.dp; setPadding(24.dp, 0, 24.dp, 0) }
            if (on) { b.background = box(C.POPUP, C.POPUP, radius = 20); b.contentDescription = "$name 선택됨" }
            else pressable(b, Color.TRANSPARENT, C.CARD_DOWN, Color.TRANSPARENT, radius = 20) { decideRepeat(h, keep) }
            seg.addView(b, LinearLayout.LayoutParams(-2, -2).apply { if (i > 0) marginStart = 4.dp })
        }
        card.addView(seg, LinearLayout.LayoutParams(-2, -2))
        return card
    }

    // ---------- 가족: 초대 링크와 연결된 사람 ----------

    /** 초대 카드 안: 왼쪽 QR(도담도담 첫 화면 주소만 담는다), 오른쪽 본문 + 작은 줄(주소) + 코드. 찍든 주소를 치든 같은 첫 화면에서 코드를 넣는다. 긴 링크 글자는 보여 주지 않는다. */
    private fun codeLines(card: LinearLayout, code: String) {
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        qrBitmap(BuildConfig.SHARE_BASE.trimEnd('/') + "/")?.let { bmp ->
            val tile = ImageView(this).apply {
                setImageBitmap(bmp); scaleType = ImageView.ScaleType.FIT_CENTER
                setPadding(12.dp, 12.dp, 12.dp, 12.dp); background = box(Color.WHITE, Color.WHITE)
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            }
            row.addView(tile, LinearLayout.LayoutParams(184.dp, 184.dp).apply { rightMargin = 32.dp })
        }
        val words = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        words.addView(text("폰 카메라로 QR을 찍어 주세요", T.BODY, C.INK))
        words.addView(text("또는 ${Api.shareHost}에서 코드 입력", T.LABEL, C.SUB).apply { setPadding(0, 4.dp, 0, 0) })
        words.addView(text("코드 ${spaced(code)}", T.HEAD_S, C.INK, w = T.W7).apply { setPadding(0, 16.dp, 0, 0); letterSpacing = 0.04f; contentDescription = "코드 ${code.toList().joinToString(" ")}" })
        row.addView(words, LinearLayout.LayoutParams(0, -2, 1f))
        card.addView(row)
    }

    /** 초대 코드를 3자리씩 띄어 쓴다(123 456). */
    private fun spaced(code: String) = code.chunked(3).joinToString(" ")

    /** 링크를 QR 그림으로. 칸 하나를 정수 픽셀로 그려 흐림 없이 또렷하게. 실패하면 null(주소·코드만 보인다). */
    private fun qrBitmap(link: String): Bitmap? = runCatching {
        val m = com.google.zxing.qrcode.QRCodeWriter().encode(link, com.google.zxing.BarcodeFormat.QR_CODE, 0, 0,
            mapOf(com.google.zxing.EncodeHintType.MARGIN to 0, com.google.zxing.EncodeHintType.ERROR_CORRECTION to com.google.zxing.qrcode.decoder.ErrorCorrectionLevel.M))
        val cell = maxOf(1, 160.dp / m.width)
        Bitmap.createBitmap(m.width * cell, m.height * cell, Bitmap.Config.ARGB_8888).also { b ->
            val c = android.graphics.Canvas(b); c.drawColor(Color.WHITE)
            val p = android.graphics.Paint().apply { color = Color.BLACK }
            for (y in 0 until m.height) for (x in 0 until m.width) if (m.get(x, y))
                c.drawRect((x * cell).toFloat(), (y * cell).toFloat(), ((x + 1) * cell).toFloat(), ((y + 1) * cell).toFloat(), p)
        }
    }.getOrNull()

    private fun family(v: LinearLayout) {
        val invites = Hub.invites
        // 서버에 못 닿았으면 '연결됨'으로 지어내지 않고 못 불러왔다고 말한다
        if (invites == null && !Hub.demo && invitesChecked) {
            v.addView(text("인터넷에 연결되지 않아 불러오지 못했습니다", T.BODY_S, C.SUB).apply { setPadding(4.dp, 0, 0, 12.dp) })
            v.addView(if (invitesLoading) busy(C.CARD, "불러오는 중") else outline("다시 불러오기") { loadInvites(); render() }, btnLp())
            v.addView(space(24))
        }
        // 이름 없는 초대는 사람처럼 보이지 않게 코드로(63번 4장)
        val people: List<Pair<String, Invite?>> = invites?.map { (it.name?.let(::nim) ?: "코드 ${spaced(it.code)}") to it } ?: if (Hub.demo) Hub.today.map { it.sender }.distinct().map { nim(it) to null } else emptyList()
        // 방금 만든 링크는 아래 카드로 보여 주므로, 목록에서 다시 펼치는 건 그 밖의 연결 전 링크만
        val fresh = newLink?.substringAfterLast("invite=")
        if (people.isEmpty() && invites != null) v.addView(text("연결된 사람이 없습니다", T.BODY_S, C.SUB).apply { setPadding(4.dp, 0, 0, 24.dp) })
        val list = listBox(v)
        people.forEach { (name, inv) ->
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = 100.dp; setPadding(8.dp, 16.dp, 8.dp, 16.dp) }
            // 광장의 얼굴 칸 64·모서리 16. 광장에 없으면 사진, 그것도 없으면 회색 칸 + 사람 아이콘 64%
            val person = inv?.let { Hub.plaza?.byCode(it.code) }
            val pic = photoBitmap(inv?.photo)
            row.addView(if (person != null || pic == null) faceTile(person, 16) else roundPhoto(pic, 16), LinearLayout.LayoutParams(64.dp, 64.dp).apply { marginEnd = 20.dp })
            // 체험 중에는 예시 이름이라고 밝힌다(오른쪽 표시 하나만)
            val example = inv == null && Hub.demo
            row.addView(text(name, T.BODY, if (inv != null && inv.name == null) C.SUB else C.INK), LinearLayout.LayoutParams(0, -2, 1f))
            // 링크 보냄: 아무 폰도 안 염 · 링크 열어 봄: 한 폰이 열었지만 이름을 정하기 전 · 연결됨: 이름까지 정해짐 · 새 링크 보냄: 다시 연결 뒤 새 폰이 열기 전
            // 이름이 있는데 잠기지 않은 옛 링크(폰 잠금 전에 만든 것)는 연결됨으로 본다
            val linked = inv == null || (inv.name != null && !inv.reissued)
            if (example) row.addView(demoTag("예시"), LinearLayout.LayoutParams(-2, -2).apply { marginEnd = 16.dp })
            else row.addView(text(when { linked -> "연결됨"; inv!!.name != null -> "새 코드 만듦"; inv.claimed -> "초대장 열어 봄"; else -> "코드 만듦" }, T.LABEL, C.SUB).apply { setPadding(0, 0, 24.dp, 0) })
            // 연결 전 링크: 줄을 누르면 그 링크를 다시 보여 준다(잃어버린 사람에게 다시 보내게)
            val waiting = inv != null && !linked && inv.code != fresh
            if (waiting) {
                pressable(row, Color.TRANSPARENT, C.CARD, Color.TRANSPARENT) { shownInvite = if (shownInvite == inv!!.code) null else inv.code; render() }
                row.contentDescription = "$name, 코드 다시 보기"
            }
            // 끊기는 가운데 팝업으로 한 번 더 묻는다(되돌릴 수 없어서 빨간 버튼)
            val askRevoke = { i: Invite ->
                val who = i.name?.let(::nim)
                confirm(if (who != null) "$who 연결 끊기" else "초대 코드 끊기",
                    if (who != null) "메시지를 더 이상 받지 않습니다" else "이 코드로 오는 메시지를 더 이상 받지 않습니다", "끊기") { done -> revoke(i, done) }
            }
            if (inv != null && linked) {
                // 연결된 사람: 줄을 누르면 가운데 팝업 메뉴(새 폰으로 다시 연결 · 연결 끊기). 줄 끝 꺾쇠로 누를 수 있다는 것만
                row.addView(Icon(this, "next", C.SUB), LinearLayout.LayoutParams(32.dp, 32.dp))
                pressable(row, Color.TRANSPARENT, C.CARD, Color.TRANSPARENT) {
                    menu = Menu(name, listOf("새 폰으로 다시 연결" to { askReissue(inv) }, "연결 끊기" to { askRevoke(inv) })); render()
                }
                row.contentDescription = "$name, 연결됨"
            }
            // 연결 전 링크는 줄을 누르면 코드를 다시 펼치므로 끊기 버튼은 줄에 그대로 둔다(Medium)
            else if (inv != null) row.addView(button("끊기", C.CARD, C.CARD_DOWN, C.INK, h = 80, r = 24) { askRevoke(inv) }, LinearLayout.LayoutParams(-2, -2))
            listAdd(list, row)
            if (waiting && shownInvite == inv!!.code) {
                val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(28.dp, 20.dp, 28.dp, 24.dp); background = box(C.CARD, C.CARD, radius = 24) }
                codeLines(card, inv.code)
                list.addView(card, full().apply { bottomMargin = 16.dp })
            }
        }
        v.addView(space(24))
        ownerRow(v)
        // 이름을 받는 중이면 그 칸의 [링크 만들기]가 대신한다
        if (!(ownerEditing && inviteAfterName))
            v.addView(if (inviteBusy) busy(C.PRIMARY, "코드를 만드는 중") else primary("초대 코드 만들기") {
                if (ownerName().isEmpty()) { ownerEditing = true; inviteAfterName = true; ownerDraft = ""; render() }
                else { newLinkFor = null; makeInvite() }
            }, btnLp())
        if (inviteOpen) {
            val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(28.dp, 24.dp, 28.dp, 24.dp); background = box(C.CARD, C.CARD, radius = 24) }
            if (newLink != null) {
                // 다시 연결로 만든 것만 누구 것인지 한 줄 위에. 나머지는 주소와 코드만
                newLinkFor?.let { card.addView(text("${nim(it)} 새 폰에 보낼 코드", T.BODY, C.SUB).apply { setPadding(0, 0, 0, 12.dp) }) }
                codeLines(card, newLink!!.substringAfterLast("invite="))
            } else card.addView(text(if (inviteError) "인터넷에 연결되지 않아 만들지 못했습니다" else "코드를 만드는 중", T.BODY_S, C.SUB))
            v.addView(card, full().apply { topMargin = 24.dp })
            // 방금 띄운 링크 카드가 화면 밖이면 그 자리까지 내린다
            if (scrollToLink && newLink != null) { scrollToLink = false; card.post { card.requestRectangleOnScreen(android.graphics.Rect(0, 0, card.width, card.height), false) } }
        }
    }

    /** 목록 묶음(63번 2장): 줄 높이 100, 줄 사이 1px #E0E1E6. card: 흰 면·모서리 32·1px 테두리 카드 안에(들은 메시지). */
    private fun listBox(v: LinearLayout, card: Boolean = false): LinearLayout {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            if (card) { background = GradientDrawable().apply { setColor(C.POPUP); cornerRadius = 32.dp.toFloat(); setStroke(1.dp, C.LINE) }; setPadding(24.dp, 0, 24.dp, 0) }
        }
        v.addView(box, full())
        return box
    }
    private fun listAdd(box: LinearLayout, row: View) {
        if (box.childCount > 0) box.addView(listLine(), LinearLayout.LayoutParams(-1, 1.dp))
        box.addView(row, full())
    }
    private fun listLine() = View(this).apply { setBackgroundColor(C.LINE) }

    // ---------- 도착·듣기: 액자 안에서 빛이 깨어난다 ----------


    /** 도착 3장면 공통: 그림 + 가운데 글자 + 맨 아래 버튼 자리. pic: 보낸 사람 얼굴 칸 200·모서리 40(63번 4장). null이면 그림 자리만 비워 둔다. */
    private class Lit(val glow: View, val mid: LinearLayout, val foot: LinearLayout)
    private fun lit(v: LinearLayout, pic: View?): Lit {
        val stage = FrameLayout(this)
        v.addView(stage, LinearLayout.LayoutParams(-1, 0, 1f))
        val glow = pic ?: View(this).apply { visibility = View.INVISIBLE }
        val mid = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER; setPadding(40.dp, 32.dp, 40.dp, 240.dp) }
        stage.addView(mid, FrameLayout.LayoutParams(-1, -1))
        mid.addView(glow, LinearLayout.LayoutParams(200.dp, 200.dp))
        mid.addView(space(28))
        val foot = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL }
        stage.addView(foot, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM).apply { setMargins(40.dp, 0, 40.dp, 32.dp) })
        // 아래 버튼이 많아지면(반복 카드·답장) 가운데 글자가 가려지지 않게 그만큼 비운다
        foot.addOnLayoutChangeListener { _, _, top, _, bottom, _, _, _, _ ->
            val need = maxOf(240.dp, bottom - top + 56.dp)
            if (mid.paddingBottom != need) mid.post { mid.setPadding(40.dp, 32.dp, 40.dp, need) }
        }
        return Lit(glow, mid, foot)
    }

    /** 보낸 사람 얼굴 칸: 광장 사람 → 사진 → 회색 칸 + 사람 아이콘. 이름을 숨길 때는 회색 칸. 예시 메시지는 예시 가족 얼굴. */
    private fun senderTile(h: Hidden, radius: Int): View {
        if (namesHidden()) return faceTile(null, radius)
        val p = if (h.example || Hub.demo) Plaza.demoData().people.firstOrNull { it.name == h.sender }
            else (Hub.plaza ?: Plaza.cached(this))?.let { d -> d.byCode(h.invite) ?: d.people.firstOrNull { it.name != null && it.name == h.sender } }
        if (p != null) return faceTile(p, radius)
        return photoOf(h)?.let { roundPhoto(it, radius) } ?: faceTile(null, radius)
    }

    /** ② 정차 중 도착(3D를 못 띄우는 차): 보낸 사람 얼굴 칸이 커지며 나온다. 조건은 들은 뒤에. */
    private fun arrivalScreen(v: LinearLayout, h: Hidden) {
        val l = lit(v, senderTile(h, 40))
        if (h.id !in openingShown) {
            openingShown += h.id
            l.glow.apply { scaleX = 0.5f; scaleY = 0.5f; animate().scaleX(1f).scaleY(1f).setDuration(500).setInterpolator(android.view.animation.OvershootInterpolator(1.6f)).start() }
        }
        // 프라이빗 모드 + 동승자면 정차 화면에서도 이름을 숨긴다(안내 음성과 같은 판단)
        l.mid.addView(text(whose(h), T.HEAD_S, C.INK, center = true, w = T.W7), full())
        if (Hub.demo || h.example) l.mid.addView(demoTag(), LinearLayout.LayoutParams(-2, -2).apply { topMargin = 12.dp })
        // 주행 화면·알림 카드와 같은 버튼 이름
        l.foot.addView(btnRow(primary("듣기") { Hub.service?.listenNow() }, outline("나중에") { Hub.service?.later() }), LinearLayout.LayoutParams(-2, -2))
    }

    /** 이름을 숨길 때: 프라이빗 모드가 켜져 있고 동승자가 있을 때(서비스의 판단 하나만 쓴다). */
    private fun namesHidden() = Hub.service?.hideName() == true
    /** 화면에 쓰는 보낸 사람: 숨길 때는 null. */
    private fun who(h: Hidden) = if (namesHidden()) null else nim(h.sender)
    /** "○○님 메시지" / 숨길 때 "음성 메시지". */
    private fun whose(h: Hidden) = who(h)?.let { "$it 메시지" } ?: "음성 메시지"

    /** 받아 둔 사진(판 번호 → 그림). 파일이 없으면 null. */
    private val bitmaps = mutableMapOf<String, Bitmap?>()
    private fun photoBitmap(v: String?): Bitmap? {
        if (v == null) return null
        val f = Store.photoFile(this, v)
        if (!f.exists()) return null
        return bitmaps.getOrPut(f.path) { runCatching { BitmapFactory.decodeFile(f.path) }.getOrNull() }
    }
    /** 남긴 사람 사진(서버는 검수를 통과한 사진만 준다). 이름을 숨기면(동승자가 있는 프라이빗 모드) 사진도 숨긴다. 없으면 null. */
    private fun photoFor(h: Hidden): Bitmap? {
        if (namesHidden() || h.example || Hub.demo) return null
        // 사람 목록이 더 새 값이면(사진을 바꿨거나 지움) 그걸 따른다
        val inv = Hub.invites?.firstOrNull { it.code == h.invite }
        return photoBitmap(if (inv != null) inv.photo else h.photo)
    }
    /** 정차 중 화면의 사진(주행 중엔 null: 원래 그림). */
    private fun photoOf(h: Hidden): Bitmap? = if (driving()) null else photoFor(h)
    /** 사진: radius가 없으면 동그랗게, 있으면 둥근 네모(얼굴 칸과 같은 모서리). */
    private fun roundPhoto(b: Bitmap, radius: Int? = null) = ImageView(this).apply {
        setImageBitmap(b); scaleType = ImageView.ScaleType.CENTER_CROP; clipToOutline = true
        outlineProvider = object : android.view.ViewOutlineProvider() { override fun getOutline(view: View, o: android.graphics.Outline) { if (radius == null) o.setOval(0, 0, view.width, view.height) else o.setRoundRect(0, 0, view.width, view.height, radius.dp.toFloat()) } }
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO   // 이름 글자가 바로 옆에 있다
    }

    /** 주행 중 화면(3D를 못 띄우는 차): 누를 것 없음, 움직임 없음(63번 4장). 도착이면 핸들 사진 360×270만, 아니면 대기 개수 + 막힘 안내. */
    private fun driveScreen(v: LinearLayout) {
        val playing = Hub.nowPlaying
        val offered = Hub.offered
        if (playing != null) return playingScreen(v, playing)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL; setPadding(40.dp, 32.dp, 40.dp, 32.dp) }
        v.addView(col, LinearLayout.LayoutParams(-1, 0, 1f))
        col.addView(grow())
        if (offered != null) {
            val who = Hub.service?.whose(offered) ?: "음성 메시지"
            col.addView(text(who, T.BODY, C.SUB, center = true), full())
            if (Hub.demo || offered.example) col.addView(demoTag(), LinearLayout.LayoutParams(-2, -2).apply { topMargin = 8.dp })
            col.addView(space(24))
            // 화면 버튼이 아니라 핸들 가운데 버튼이 주인공: 누를 버튼 그림을 글보다 먼저
            col.addView(wheelPic(R.drawable.wheel_play, "핸들 가운데 버튼"), LinearLayout.LayoutParams(360.dp, 270.dp))
            col.addView(space(28))
            col.addView(text("핸들 가운데 버튼으로\n듣기", T.HEAD_M, C.INK, center = true, w = T.W7), full())
            col.addView(TimeBar(this), LinearLayout.LayoutParams(-1, 24.dp).apply { topMargin = 32.dp })
        } else plazaBand(col, true, Ground(Color.TRANSPARENT), false)
        col.addView(grow())
    }

    /** ④ 듣는 중(3D를 못 띄우는 차): 큰 이름. P에서는 얼굴 칸 + 재생 막대 + 멈춤 원(이어 들을 때 ⏭ 원), 주행 중엔 그림·막대·버튼 없이 이름만. */
    private fun playingScreen(v: LinearLayout, h: Hidden) {
        // 주행 중 듣는 동안에만: 사진이 있으면 이름 왼쪽에 작게
        val drivePic = if (driving()) photoFor(h) else null
        val l = lit(v, if (driving()) null else senderTile(h, 40))
        if (!driving()) ValueAnimator.ofFloat(1f, 1.04f).apply {
            duration = 700; repeatMode = ValueAnimator.REVERSE; repeatCount = ValueAnimator.INFINITE
            addUpdateListener { a -> val k = a.animatedValue as Float; l.glow.scaleX = k; l.glow.scaleY = k }
            l.glow.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
                override fun onViewAttachedToWindow(x: View) {}
                override fun onViewDetachedFromWindow(x: View) { cancel() }
            })
            start()
        }
        val name = if (driving()) Hub.service?.whose(h) ?: "음성 메시지" else whose(h)
        val nameView = text(name, T.HEAD_S, C.INK, center = true, w = T.W7)
        if (drivePic == null) l.mid.addView(nameView, full())
        else {
            // 앨범 아트처럼 멈춘 한 장(Pleos app-category, Android car quality IU-1 예외), 누구 목소리인지 확인용. 움직임·누름 없음
            nameView.measure(View.MeasureSpec.UNSPECIFIED, View.MeasureSpec.UNSPECIFIED)
            val lineH = nameView.measuredHeight
            val over = (lineH - 96.dp) / 2
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER; clipChildren = false }
            row.addView(roundPhoto(drivePic).apply { isClickable = false; isFocusable = false },
                LinearLayout.LayoutParams(96.dp, 96.dp).apply { marginEnd = 24.dp; topMargin = over; bottomMargin = over })
            row.addView(nameView, LinearLayout.LayoutParams(-2, -2))
            l.mid.clipChildren = false
            l.mid.addView(row, LinearLayout.LayoutParams(-1, lineH))
        }
        l.mid.addView(text(momentText(h), T.BODY, C.SUB, center = true).apply { setPadding(0, 8.dp, 0, 0) }, full())
        if (Hub.demo || h.example) l.mid.addView(demoTag(), LinearLayout.LayoutParams(-2, -2).apply { topMargin = 8.dp })
        if (driving()) l.mid.addView(text("핸들 가운데 버튼으로 멈추기", T.TITLE_S, C.INK, center = true, bold = true).apply { setPadding(0, 32.dp, 0, 0) }, full())
        if (!driving()) {
            l.mid.addView(space(32))
            bar = Bar(this).also { l.mid.addView(it, LinearLayout.LayoutParams(-1, 40.dp)) }
            val time = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER; setPadding(0, 8.dp, 0, 24.dp) }
            timeNow = text("0:00", T.BODY, C.INK).also { time.addView(it) }
            timeAll = text("", T.BODY, C.SUB).also { time.addView(it) }   // 길이는 준비된 뒤에(그전엔 비움)
            l.mid.addView(time, full())
            // 일시정지 대신 멈춤: 처음 듣던 메시지는 못 들은 것으로 남아 주차할 때 다시 들려준다
            val btns = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            val btn = FrameLayout(this).apply { contentDescription = "멈추기" }
            pressable(btn, C.CARD, C.CARD_DOWN, C.CARD, oval = true) { stopPlaying("화면 멈춤") }
            btn.addView(Icon(this, "stop", C.INK), FrameLayout.LayoutParams(40.dp, 40.dp, Gravity.CENTER))
            btns.addView(btn, LinearLayout.LayoutParams(100.dp, 100.dp))
            // 주차해서 여러 개를 이어 들을 때: 지금 것은 넘기고 다음으로(넘긴 것은 들은 메시지 화면에서 들을 수 있다)
            if (Hub.arrivalLeft > 1) btns.addView(skipCircle(), LinearLayout.LayoutParams(80.dp, 80.dp).apply { marginStart = 16.dp })
            l.mid.addView(btns, LinearLayout.LayoutParams(-2, -2))
        }
        lastPlaying = h; lastPlayingAt = System.currentTimeMillis()
        tick()
    }

    /** ⑤ 다 들은 뒤: 얼굴 칸 + 이름 + 언제 남긴 메시지인지 + 이모티콘 줄. 1px 선 아래 버튼은 [답장][다시 듣기]만(63번 4장, 닫기는 머리줄 뒤로, 신고는 머리줄 ⋯). 반복 메시지면 다음에도 들을지. */
    private fun afterScreen(v: LinearLayout, h: Hidden) {
        val l = lit(v, senderTile(h, 40))
        l.mid.addView(text(whose(h), T.HEAD_S, C.INK, center = true, w = T.W7), full())
        l.mid.addView(text(afterLine(h), T.BODY, C.SUB, center = true).apply { setPadding(0, 12.dp, 0, 0) }, full())
        if (Hub.demo || h.example) l.mid.addView(demoTag(), LinearLayout.LayoutParams(-2, -2).apply { topMargin = 12.dp })
        // 이모티콘 줄은 메시지 정보 바로 아래(내용 쪽). 정차 중에만
        if (!gone(h) && stopped()) {
            l.mid.addView(reactLabel(h, center = true), full().apply { topMargin = 32.dp; bottomMargin = 12.dp })
            l.mid.addView(emojiRow(h), LinearLayout.LayoutParams(-2, -2))
        }
        // 남긴 사람이 지운 메시지: 답장·다시 듣기·신고를 숨기고 이유만(닫기는 머리줄 뒤로)
        if (gone(h)) {
            l.foot.addView(text("남긴 사람이 지운 메시지입니다", T.BODY, C.SUB, center = true), full())
            return
        }
        // 반복 메시지는 들은 뒤 화면마다 다음에도 들을지 보여 준다(지난 메시지에서 열어도 같다). 예시 메시지는 진짜가 아니라 신고·다음에도 듣기가 없다
        if (stopped() && h.repeat == "each" && !h.example) l.foot.addView(repeatCard(h), full().apply { bottomMargin = 24.dp })
        // 마이크를 허용한 뒤 돌아오면 안내를 지운다
        if (answered[h.id] == MIC_NEED && granted(android.Manifest.permission.RECORD_AUDIO)) answered.remove(h.id)
        // 예시 메시지도 답장은 끝까지 해 볼 수 있다(녹음 → 들어 보기 → 보내기). 보내기만 서버로 가지 않는다
        val btns = mutableListOf<View>()
        var note: String? = null
        if (stopped()) {
            when {
                answered[h.id] == "답장 보냄" || answered[h.id] == DEMO_SENT || (!h.example && (h.id in repliedToday() || h.replied || Hub.repliedAt(this, h.id) != null)) -> note = answered[h.id] ?: "답장 보냄"
                answered[h.id] == MIC_NEED -> { note = MIC_NEED; btns += primary("허용하기") { allow(listOf(android.Manifest.permission.RECORD_AUDIO), "micAsked") { afterOf = null; startReply(h) } } }
                else -> { note = answered[h.id]; btns += primary(if (answered[h.id] != null) "다시 녹음" else "답장") { afterOf = null; startReply(h) } }
            }
        }
        btns += outline("다시 듣기") { afterOf = null; replayToAfter = true; if (h.example) playExample(h, backTo = h) else replay(h) }
        // 이모티콘 줄(위)과 할 일 버튼 줄(아래) 사이 1px 선
        if (stopped()) l.foot.addView(reactLine(), LinearLayout.LayoutParams(-1, 1.dp).apply { bottomMargin = 24.dp })
        note?.let { l.foot.addView(text(it, T.BODY, C.SUB, center = true), full().apply { bottomMargin = 24.dp }) }
        l.foot.addView(btnRow(*btns.toTypedArray()), LinearLayout.LayoutParams(-2, -2))
    }

    /** 들은 뒤 한 줄(75번 B 세트 1): "집 근처에 왔을 때 · 오후 11:40"(받은 시각 = 순간이 온 때, 모르면 들은 시각). 이름을 숨겨도 같은 줄. */
    private fun afterLine(h: Hidden): String {
        val at = Hub.service?.receivedAt(h) ?: Hub.receivedAtSaved(this, h.id) ?: Hub.heardAt(this, h.id)
        return listOfNotNull(momentText(h), at?.let { whenText(it) }).joinToString(" · ")
    }

    /** 받은 시각 글자: 오늘 "오후 3:12", 어제 "어제 오후 11:50", 그 전 "11월 8일 오후 3:12". 주차 목록 줄과 들은 뒤 줄이 같이 쓴다. */
    private fun whenText(ms: Long): String {
        val day = java.time.Instant.ofEpochMilli(ms).atZone(java.time.ZoneId.systemDefault()).toLocalDate()
        val today = LocalDate.now()
        return (if (day == today) "" else if (day == today.minusDays(1)) "어제 " else "${day.monthValue}월 ${day.dayOfMonth}일 ") + timeOf(ms)
    }

    /** 남긴 사람이 지운 메시지인지: 답장이 거절됐거나, 오늘 메시지인데 목록에서 빠졌다(지난 메시지는 원래 오늘 목록에 없다). */
    private fun gone(h: Hidden) = h.id in goneIds ||
        (!h.example && !Hub.demo && Hub.loaded && !Hub.offline && h.id !in pastIds && Hub.today.none { it.id == h.id } &&
            Hub.retired.none { it.id == h.id })   // 자정이 지나 목록에서 빠졌을 뿐인 들은 메시지는 지운 것이 아니다

    /** 순간 이름: 장소 메시지는 고른 장소 이름으로. */
    private fun momentText(h: Hidden) = h.place?.let { "${it.name} 근처에 왔을 때" } ?: LEFT_WHEN[h.moment] ?: MOMENT_LABEL[h.moment] ?: ""

    /** 정차 중 다시 듣기. 못 틀면(인터넷 없음 등) 그 메시지 화면에 남아 이유를 알려 준다. */
    private fun replay(h: Hidden) {
        val started = Hub.service?.replay(h, onFail = { if (!driving()) { afterOf = h; render(); toast("인터넷에 연결되지 않아 들을 수 없습니다") } }) {} ?: false
        // 다른 메시지가 나오는 중이면 겹쳐 틀지 않고 그 메시지 화면에 그대로 둔다
        if (!started && !driving()) { afterOf = h; render() }
    }

    /** 신고 확인(가운데 팝업): 그 사람의 초대 링크를 끊어 남은 메시지도 더는 안 나온다. 남긴 사람에게 신고했다고 알리지는 않는다. */
    private fun askReport(h: Hidden) {
        val who = who(h)
        confirm(if (who != null) "$who 신고하기" else "보낸 사람 신고하기",
            "신고하면 연결도 끊깁니다", "신고하기") { done ->
            io.execute {
                val r = runCatching { Api.report(h.id) }
                main.post {
                    Hub.log(if (r.isSuccess) "${nim(h.sender)} 신고함 → 연결 끊음" else "신고 실패: ${r.exceptionOrNull()?.message}")
                    // 됐으면 그 메시지 화면을 닫는다. 못 했으면 그 화면에 남아 다시 누를 수 있다
                    if (r.isSuccess && afterOf?.id == h.id) afterOf = null
                    done()
                    toast(if (r.isSuccess) (if (who != null) "${who}을 신고했습니다" else "신고했습니다") else "신고하지 못했습니다")
                    past = null; Hub.service?.refresh(); loadInvites()
                }
            }
        }
    }


    // ---------- C-05 답장 녹음 ----------

    private fun replyScreen(v: LinearLayout, h: Hidden) {
        v.gravity = Gravity.CENTER_HORIZONTAL
        v.addView(space(20))
        // 누구 메시지인지만(이름을 숨길 때는 '음성 메시지')
        v.addView(text("${whose(h)}에 답장", T.BODY, C.SUB, center = true))
        v.addView(space(28))
        // 녹음 원 200(63번 4장): 3·2·1 동안은 회색 + 마이크 64%(아직 녹음하지 않음), 녹음 중은 진회색 + 흰 마이크
        val prep = replyPrep > 0
        val circle = FrameLayout(this).apply { background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(if (prep) C.CARD else C.PRIMARY) } }
        circle.addView(Icon(this, "mic", if (prep) C.SUB else Color.WHITE), FrameLayout.LayoutParams(72.dp, 72.dp, Gravity.CENTER))
        v.addView(circle, LinearLayout.LayoutParams(200.dp, 200.dp))
        v.addView(space(20))
        countView = text(if (prep) "$replyPrep" else "$replyLeft", T.HEAD_M, if (prep) C.SUB else C.INK, center = true, w = T.W7).also { v.addView(it) }
        v.addView(text(if (prep) "곧 녹음을 시작합니다" else "녹음 중", T.BODY, C.INK, center = true))
        v.addView(space(16))
        // 소리 막대는 녹음이 시작된 뒤에만(3·2·1 동안은 같은 자리를 비워 둔다)
        if (prep) v.addView(space(56)) else wave = Wave(this).also { v.addView(it, LinearLayout.LayoutParams(400.dp, 56.dp)) }
        v.addView(space(32))
        // 다 말했으면 5초를 기다리지 않고 끝낼 수 있다(녹음이 시작된 뒤에만)
        v.addView(btnRow(primary("녹음 끝내기") { if (replyPrep == 0) finishReply() }.apply { if (prep) { alpha = 0.4f; isEnabled = false } },
            outline("버리기") { cancelReply() }), LinearLayout.LayoutParams(-2, -2))
    }

    /** 녹음한 답장 확인(정차 중에만): 들어 보고 보내거나 다시 녹음한다. 주행하면 버린다. */
    /** 녹음이 끝나면 한 번 저절로 들려준다(정차 중에만 오는 화면). 가운데: 재생 막대 + 작은 재생/멈춤 동그라미, 맨 아래: [보내기][다시 녹음].
     *  버리기는 머리줄 뒤로(가운데 팝업으로 묻는다). */
    private fun reviewScreen(v: LinearLayout, h: Hidden) {
        v.gravity = Gravity.CENTER_HORIZONTAL
        v.addView(grow())
        photoOf(h)?.let { v.addView(roundPhoto(it), LinearLayout.LayoutParams(120.dp, 120.dp)); v.addView(space(20)) }
        v.addView(text(who(h)?.let { "${it}에게 보낼 답장" } ?: "보낼 답장", T.TITLE_L, C.INK, center = true, w = T.W7), full())
        if (Hub.demo || h.example) v.addView(demoTag(), LinearLayout.LayoutParams(-2, -2).apply { topMargin = 12.dp })
        v.addView(space(40))
        // 듣는 화면과 같은 꼴: 막대 아래 동그란 버튼 하나(다시 들을 때만 누른다). 막대 채움은 보낸 사람 대표색(63번 4장)
        val tint = if (namesHidden()) null else (if (h.example || Hub.demo) Plaza.demoData().people.firstOrNull { it.name == h.sender } else heroOf(h, Hub.plaza))?.let { Plaza.barColor(it.color) }
        previewBar = Bar(this, tint ?: C.PRIMARY).also { v.addView(it, LinearLayout.LayoutParams(-1, 40.dp)) }
        v.addView(space(24))
        val play = FrameLayout(this).apply { contentDescription = if (preview != null) "멈추기" else "다시 들어 보기" }
        pressable(play, C.CARD, C.CARD_DOWN, C.CARD, oval = true) { if (!sending) { if (preview != null) { stopPreview(); render() } else playPreview() } }
        play.addView(Icon(this, if (preview != null) "stop" else "play", C.INK), FrameLayout.LayoutParams(40.dp, 40.dp, Gravity.CENTER))
        v.addView(play, LinearLayout.LayoutParams(96.dp, 96.dp))
        v.addView(grow())
        // 못 보냈으면 이유와 할 일을 버튼 위에 남긴다(토스트는 3초 뒤 사라지므로)
        sendError?.let { v.addView(text(it, T.BODY, C.INK, center = true).apply { setPadding(0, 0, 0, 24.dp) }, full()) }
        // 주 버튼 왼쪽(Pleos 가로 버튼 순서). 보내는 동안은 로딩(다시 누름 막기), 못 보내면 같은 녹음을 다시 보낼 수 있다
        val sendLabel = if (sendError != null) "다시 보내기" else "보내기"
        v.addView(btnRow(if (sending) busy(C.PRIMARY, "보내는 중") else primary(sendLabel) { stopPreview(); val f = reviewFile; if (f != null) sendReply(h, f) else discardReview() },
            outline("다시 녹음") { if (!sending) { stopPreview(); review = null; reviewFile = null; sendError = null; startReply(h) } }), LinearLayout.LayoutParams(-2, -2))
    }

    /** 녹음한 답장은 되돌릴 수 없으니 버리기 전에 한 번 묻는다(가운데 팝업). */
    private fun askDiscardReview() {
        stopPreview()
        confirm("녹음한 답장 버리기", null, "버리기") { done -> done(); discardReview() }
    }

    /** 녹음한 답장을 들어 본다(재생 소리와 같은 알림 용도). */
    private fun playPreview() {
        val f = reviewFile ?: return
        stopPreview()
        preview = runCatching {
            MediaPlayer().apply {
                setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                setDataSource(f.absolutePath)
                setOnCompletionListener { stopPreview(); render() }
                setOnErrorListener { _, what, extra -> Hub.log("답장 들어 보기 오류 $what/$extra"); stopPreview(); render(); true }
                prepare(); start()
            }
        }.onFailure { Hub.log("답장 들어 보기 실패: $it") }.getOrNull()
        render()
    }

    private fun stopPreview() {
        val p = preview ?: return
        preview = null
        runCatching { p.stop() }; runCatching { p.release() }
    }

    /** 녹음한 답장 버리기(취소·뒤로·주행 시작). 그 메시지 화면으로 돌아간다. */
    private fun discardReview() {
        val h = review
        review = null; reviewFile = null; sendError = null
        stopPreview()
        if (h != null && !driving()) afterOf = h
        render()
    }

    // ---------- 예시 메시지 ----------

    /** 체험용 예시 6개. 누르면 정차 중 다시 듣기처럼 들려주고, 끝나면 그 메시지의 들은 뒤 화면으로. 서버에는 아무것도 보내지 않는다. */
    private fun examples(v: LinearLayout) {
        val list = listBox(v)
        Demo.examples().forEach { h ->
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = 100.dp; setPadding(8.dp, 18.dp, 8.dp, 18.dp) }
            // 순간 3D 그림 대신 보낸 사람 얼굴 칸 64·모서리 16(63번 5장)
            row.addView(senderTile(h, 16), LinearLayout.LayoutParams(64.dp, 64.dp).apply { marginEnd = 20.dp })
            val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            col.addView(text("${nim(h.sender)} · ${MOMENT_LABEL[h.moment] ?: h.moment}", T.BODY, C.INK))
            Demo.line(h)?.let { col.addView(text(it, T.LABEL_S, C.SUB).apply { setPadding(0, 4.dp, 0, 0) }) }
            row.addView(col, LinearLayout.LayoutParams(0, -2, 1f))
            pressable(row, Color.TRANSPARENT, C.CARD, Color.TRANSPARENT) { playExample(h) }
            listAdd(list, row)
        }
    }

    /** 예시 음성을 꺼내 두고 다시 듣기처럼 들려준다. 다 들으면 들은 뒤 화면(뒤로 가면 예시 목록). */
    private fun playExample(h: Hidden, backTo: Hidden? = null) = io.execute {
        val r = runCatching { Demo.prepare(this, h) }
        main.post {
            r.onFailure { Hub.log("예시 메시지 준비 실패: $it") }
            val started = r.isSuccess && !driving() && Hub.service?.replay(h) { if (!driving()) afterOf = h; render() } == true
            // 못 틀었으면(다른 메시지가 나오는 중 등) 누른 화면으로 돌아간다
            if (!started && backTo != null && !driving()) { afterOf = backTo; render() }
        }
    }

    // ---------- 설정 ----------

    /** 설정: 메뉴 줄 목록(토스·카카오톡처럼). 들은 메시지는 따로 '들은 메시지' 화면에. */
    private fun settings(v: LinearLayout) {
        // 메뉴 줄 목록(63번 2장): 줄 높이 100, 줄 사이 1px 선
        val list = listBox(v)
        listAdd(list, navRow("들은 메시지") { heardOpen = true; render() })
        listAdd(list, navRow("듣는 방식", MODE_NAME[Hub.listenMode(this)]) { modeOpen = true; render() })
        listAdd(list, navRow("사람·초대") { familyOpen = true; render() })
        // 광장 자리 순서(차 주인만 = 이 차 화면, P에서만: 설정은 정차 중에만 열린다)
        if (Hub.plaza?.people?.isNotEmpty() == true) listAdd(list, navRow("자리 바꾸기") { orderOpen = true; orderDraft = null; render() })
        listAdd(list, navRow("예시 메시지") { examplesOpen = true; render() })
        // 마이크만 묻기 전이면 '모두 허용됨'이라고 하지 않고 값을 비운다
        listAdd(list, navRow("권한", if (permsOff().isNotEmpty()) "꺼짐 ${permsOff().size}개" else if (micUnasked()) null else "모두 허용됨") { permOpen = true; render() })
        listAdd(list, switchRow("저사양 모드", LOW_SPEC_DESC, Hub.lowSpec(this)) { on ->
            Hub.setLowSpec(this, on); plaza?.lowSpec = on; Hub.log("저사양 모드 → ${if (on) "켜기" else "끄기"}"); render()
        })
        listAdd(list, navRow("개인정보 처리방침") { openWeb("개인정보 처리방침", "/privacy") })
        listAdd(list, navRow("이용약관") { openWeb("이용약관", "/terms") })
        listAdd(list, navRow("위치정보 이용약관") { openWeb("위치정보 이용약관", "/location") })
        // 앱 정보를 일곱 번 누르면 시연 도구가 열린다(안드로이드 개발자 옵션 방식). 심사용 빌드에도 기본으로는 안 보인다
        listAdd(list, navRow("앱 정보", "버전 ${appVersion()}", arrow = false) {
            if (devOn()) return@navRow
            devTaps++
            if (devTaps >= 7) { devTaps = 0; prefs().edit().putBoolean("devTools", true).apply(); toast("시연 도구를 켰습니다"); render() }
        })
        if (devOn()) {
            v.addView(section("시연 도구"))
            v.addView(switchRow("시연용 짧은 시간", "주차 15초 · 오래 달림 30초 · 메시지 간격 20초", Hub.shortTimes) { on ->
                Hub.shortTimes = on; prefs().edit().putBoolean("shortTimes", on).apply(); Hub.log("시연용 짧은 시간 → ${if (on) "켜기" else "끄기"}"); render()
            }, rowGap())
            v.addView(btnRow(outline("새로고침") { Hub.service?.refresh() }, outline("오늘 첫 출발 다시") {
                Hub.setLastStart(this, null); Hub.opened.clear(); Hub.heard.clear(); Hub.skipped.clear(); answered.clear()
                prefs().edit().remove("replied").remove("skipIds").apply()
                Hub.clearRepeatAsked(this); Hub.askRepeat = emptyList()
                io.execute { runCatching { Api.demoReset() }; main.post { Hub.service?.refresh(); Hub.log("시연용 초기화") } }
            }), rowGap())
            v.addView(btnRow(outline(if (logOpen) "기록 숨기기" else "기록 보기") { logOpen = !logOpen; render() },
                outline("시연 도구 끄기") { prefs().edit().putBoolean("devTools", false).apply(); logOpen = false; render() }), full())
            if (logOpen) v.addView(text((listOfNotNull(Hub.waiting?.let { "기다리는 이유: $it" }) + Hub.logs).joinToString("\n"), T.LABEL, C.SUB).apply { setPadding(0, 16.dp, 0, 0) })
        }
    }

    /** 저사양 모드 아래 줄: 실제로 바뀌는 것만(PlazaView.lowSpec). */
    private val LOW_SPEC_DESC = "초당 30장으로 그립니다"
    private val MODE_NAME = mapOf("button" to "버튼 눌러서 듣기", "auto" to "버튼 없이 듣기", "arrive" to "주행 집중 모드")
    private fun devOn() = prefs().getBoolean("devTools", false)
    private fun appVersion() = runCatching { packageManager.getPackageInfo(packageName, 0).versionName }.getOrNull() ?: ""
    private fun rowGap() = full().apply { bottomMargin = 16.dp }

    /** 설정 메뉴 한 줄: 제목 + (지금 값) + 오른쪽 화살표. 줄 전체를 누른다. */
    private fun navRow(title: String, value: String? = null, arrow: Boolean = true, onClick: () -> Unit) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = 100.dp; setPadding(8.dp, 16.dp, 8.dp, 16.dp)
        pressable(this, Color.TRANSPARENT, C.CARD, Color.TRANSPARENT, onClick = onClick)
        addView(text(title, T.BODY, C.INK), LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = 16.dp })
        // 값이 길면(듣는 방식 이름 등) 줄임표 없이 오른쪽에서 줄을 바꾼다
        value?.let { addView(text(it, T.BODY, C.SUB).apply { gravity = Gravity.END or Gravity.CENTER_VERTICAL }, LinearLayout.LayoutParams(0, -2, 1f)) }
        if (arrow) addView(Icon(this@MainActivity, "next", C.SUB), LinearLayout.LayoutParams(32.dp, 32.dp).apply { marginStart = 12.dp })
        contentDescription = listOfNotNull(title, value).joinToString(", ")
    }

    /** 웹 문서(서버의 한 장)를 앱 안에서 연다. 차에 웹 보기가 없거나 못 불러오면 이유와 할 일을 보여 준다. */
    private fun openWeb(title: String, path: String) {
        web?.destroy(); web = null; webFailed = false
        webOpen = title to path; render()
    }

    private fun webScreen(v: LinearLayout, path: String) {
        if (webFailed) {
            v.addView(grow())
            v.addView(text(if (webHttpFail) "지금은 문서를 열 수 없습니다" else "인터넷에 연결되지 않아 열지 못했습니다", T.BODY, C.INK, center = true), full())
            v.addView(space(24))
            v.addView(outline("다시 불러오기") { web?.destroy(); web = null; webFailed = false; render() }, LinearLayout.LayoutParams(-2, -2).apply { gravity = Gravity.CENTER_HORIZONTAL })
            v.addView(grow())
            return
        }
        val w = web ?: runCatching {
            android.webkit.WebView(this).apply {
                setBackgroundColor(Color.WHITE)
                webViewClient = object : android.webkit.WebViewClient() {
                    override fun onReceivedError(view: android.webkit.WebView, req: android.webkit.WebResourceRequest, err: android.webkit.WebResourceError) {
                        if (req.isForMainFrame) main.post { webFailed = true; webHttpFail = false; render() }
                    }
                    override fun onReceivedHttpError(view: android.webkit.WebView, req: android.webkit.WebResourceRequest, res: android.webkit.WebResourceResponse) {
                        if (req.isForMainFrame) main.post { webFailed = true; webHttpFail = true; render() }
                    }
                    // 문서 안의 다른 주소는 열지 않는다(차 안 웹 보기는 이 문서만)
                    override fun shouldOverrideUrlLoading(view: android.webkit.WebView, req: android.webkit.WebResourceRequest) = true
                }
                loadUrl(Api.BASE + path)
            }
        }.onFailure { Hub.log("웹 보기 없음: $it") }.getOrNull()?.also { web = it }
        if (w == null) {
            v.addView(grow())
            v.addView(text("이 차에서는 문서를 열 수 없습니다", T.BODY, C.INK, center = true), full())
            v.addView(space(12))
            v.addView(text("폰에서 ${BuildConfig.SHARE_BASE}${path}를 열어 주세요", T.BODY_S, C.SUB, center = true), full())
            v.addView(grow())
            return
        }
        v.addView(w, LinearLayout.LayoutParams(-1, 0, 1f))
    }

    /** 꺼진 권한(속도·위치·알림·마이크). 마이크는 첫 답장 때 묻는 게 정상이라, 물어본 뒤 거절했을 때만 센다. */
    private fun micUnasked() = !granted(android.Manifest.permission.RECORD_AUDIO) && !prefs().getBoolean("micAsked", false)
    private fun permsOff(): List<String> = carPermsMissing() + (if (notifMissing()) listOf(android.Manifest.permission.POST_NOTIFICATIONS) else emptyList()) +
        (if (granted(android.Manifest.permission.RECORD_AUDIO) || micUnasked()) emptyList() else listOf(android.Manifest.permission.RECORD_AUDIO))

    /** 권한 화면: 무엇에 쓰는지 한 줄 + 허용됨 / [허용하기]. */
    private fun permScreen(v: LinearLayout) {
        // 아이콘: Material Symbols speed / location_on / notifications / mic, 48dp #131417(63번 4장)
        val rows = listOf(
            Triple("speed", "속도", "android.car.permission.CAR_SPEED") to "달리는 중에 들려드립니다",
            Triple("location", "위치", "pleos.car.permission.FUSED_LOCATION") to "집이나 정한 곳 근처에서 들려드립니다",
            Triple("bell", "알림", android.Manifest.permission.POST_NOTIFICATIONS) to "듣기 버튼을 띄웁니다",
            Triple("mic", "마이크", android.Manifest.permission.RECORD_AUDIO) to "답장을 녹음할 때 씁니다",
        )
        val list = listBox(v)
        rows.forEach { (r, why) ->
            val (ic, name, perm) = r
            val on = if (perm == android.Manifest.permission.POST_NOTIFICATIONS) !notifMissing() else granted(perm)
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = 100.dp; setPadding(8.dp, 20.dp, 8.dp, 20.dp) }
            row.addView(Icon(this, ic, C.INK), LinearLayout.LayoutParams(48.dp, 48.dp).apply { marginEnd = 24.dp })
            val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            col.addView(text(name, T.BODY, C.INK))
            col.addView(text(why, T.LABEL, C.SUB))
            row.addView(col, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = 16.dp })
            if (on) row.addView(text("허용됨", T.BODY, C.SUB).apply { setPadding(0, 0, 8.dp, 0) })
            else {
                val key = when (perm) { android.Manifest.permission.RECORD_AUDIO -> "micAsked"; android.Manifest.permission.POST_NOTIFICATIONS -> "notifAsked"; else -> "carPermAsked" }
                row.addView(button("허용하기", C.PRIMARY, C.PRIMARY_DOWN, C.ON_INK, h = 80, r = 24) {
                    allow(listOf(perm), key) { prefs().edit().putBoolean(key, true).apply(); requestPermissions(arrayOf(perm), 2) }
                }, LinearLayout.LayoutParams(-2, -2))
            }
            row.contentDescription = "$name ${if (on) "허용됨" else if (perm == android.Manifest.permission.RECORD_AUDIO && micUnasked()) "허용 전" else "꺼짐"}"
            listAdd(list, row)
        }
    }

    // ---------- 들은 메시지 ----------

    private val TIME_FMT = java.time.format.DateTimeFormatter.ofPattern("a h:mm", java.util.Locale.KOREAN)
    private fun timeOf(ms: Long) = java.time.Instant.ofEpochMilli(ms).atZone(java.time.ZoneId.systemDefault()).toLocalTime().format(TIME_FMT)

    /** 들은 메시지 한 줄: 위 "○○님 · 비 올 때", 아래 "오후 6:12에 들음 · 0:05 · 답장 보냄". */
    private fun heardRow(h: Hidden, day: LocalDate?, skipped: Boolean): View {
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = 100.dp; setPadding(8.dp, 16.dp, 8.dp, 16.dp) }
        // 보낸 사람 얼굴 칸 64·모서리 16(63번 5장). 이름을 숨길 때는 회색 칸 + 사람 아이콘
        row.addView(senderTile(h, 16), LinearLayout.LayoutParams(64.dp, 64.dp).apply { marginEnd = 20.dp })
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val top = "${who(h) ?: "음성 메시지"} · ${momentText(h)}"
        col.addView(text(top, T.BODY, C.INK))
        val at = Hub.heardAt(this, h.id) ?: h.heardAt
        val len = Hub.lenMs(this, h.id) ?: h.lenMs
        val replied = h.replied || Hub.repliedAt(this, h.id) != null || h.id in repliedToday() || answered[h.id] == "답장 보냄"
        // 화면: 날짜·'오늘'은 구역 제목이 이미 말하므로 '들음'만. 읽어 주기는 줄 하나만 읽혀 날짜를 남기고 길이는 'N초'로
        val parts = mutableListOf<String>()
        val spoken = mutableListOf<String>()
        when {
            skipped -> { parts += "넘김"; spoken += "넘김" }
            at != null -> { parts += "${timeOf(at)}에 들음"; spoken += "${timeOf(at)}에 들음" }
            day != null -> { parts += "들음"; spoken += "${day.monthValue}월 ${day.dayOfMonth}일에 들음" }
            else -> { parts += "들음"; spoken += "오늘 들음" }
        }
        len?.let { parts += clock(fullLen(it.toInt())); spoken += seconds(fullLen(it.toInt())) }
        if (replied) { parts += "답장 보냄"; spoken += "답장 보냄" }
        if (parts.isNotEmpty()) col.addView(text(parts.joinToString(" · "), T.LABEL, C.SUB).apply { setPadding(0, 4.dp, 0, 0) })
        row.addView(col, LinearLayout.LayoutParams(0, -2, 1f))
        if (skipped) row.addView(Icon(this, "play", C.SUB), LinearLayout.LayoutParams(32.dp, 32.dp).apply { marginStart = 12.dp })
        // 답장 바로가기: 들은 것 중 답장 전인 것만(답장했으면 아래 줄의 '답장 보냄', 지운 메시지는 그 화면에서 이유를 본다). 정차 중에만
        else if (!replied && !gone(h) && stopped() && answered[h.id] != DEMO_SENT)
            // 회색 줄 위라 흰 면 버튼(줄 전체 누름과 따로)
            // 흰 묶음 카드 위라 Medium 보조 버튼(80·모서리 24, 줄 전체 누름과 따로)
            row.addView(button("답장", C.CARD, C.CARD_DOWN, C.INK, h = 80, r = 24) { startReply(h) }.apply { minWidth = 140.dp; setPadding(28.dp, 0, 28.dp, 0); contentDescription = who(h)?.let { "${it}에게 답장" } ?: "답장" },
                LinearLayout.LayoutParams(-2, -2).apply { marginStart = 16.dp })
        // 넘긴 것은 눌러서 바로 듣고, 들은 것은 그 메시지 화면(다시 듣기·답장)으로
        pressable(row, Color.TRANSPARENT, C.CARD, Color.TRANSPARENT) { if (skipped) playSkipped(h) else { afterOf = h; render() } }
        row.contentDescription = (listOf(top) + spoken).joinToString(", ")
        return row
    }

    /** 넘긴 메시지를 정차 중에 듣는다. 끝까지 들으면 들은 것으로 치고 그 메시지 화면으로. */
    private fun playSkipped(h: Hidden) {
        if (driving()) return
        Hub.service?.replay(h, onFail = { if (!driving()) toast("인터넷에 연결되지 않아 들을 수 없습니다") }) {
            Hub.service?.heardNow(h)
            if (!driving()) afterOf = h
            render()
        }
    }

    /** 들은 메시지 화면: 오늘(최근 것부터) + 지난 30일(날짜별 묶음). 주차 알림 '오늘 들은 메시지 N개'도 여기로 온다. */
    private fun heardScreen(v: LinearLayout) {
        // 옅은 회색 바탕 위 흰 묶음 카드 하나(모서리 32, 테두리 1px) 안에 줄 100. 구역 이름 28/600, 구역 사이 1px 선(63번 4장)
        body.setBackgroundColor(C.LIST_BG)
        // 오늘 들은 반복 메시지 중 아직 안 정한 것: 맨 위 카드로 다음에도 들을지 묻는다(주차 알림은 들은 메시지 한 장만).
        // 이 화면에 있는 동안은 고른 뒤에도 카드가 남아 바로 바꿀 수 있다
        Hub.askRepeat.filter { !Hub.repeatAsked(this, it.id) }.forEach { askOnHeard += it.id }
        val asks = askOnHeard.mapNotNull { id -> Hub.today.firstOrNull { it.id == id } }.filter { it.repeat == "each" && !it.example }
        asks.forEach { h -> v.addView(repeatCard(h, showWho = true), full().apply { bottomMargin = 24.dp }) }
        val card = listBox(v, card = true)
        var first = true
        fun sect(name: String) {
            if (!first) card.addView(listLine(), LinearLayout.LayoutParams(-1, 1.dp).apply { topMargin = 16.dp })
            card.addView(text(name, T.BODY, C.INK, bold = true).apply { setPadding(8.dp, if (first) 32.dp else 40.dp, 0, 16.dp) }, full())
            first = false
        }
        fun note(s: String) = card.addView(text(s, T.LABEL, C.SUB).apply { setPadding(8.dp, 0, 0, 24.dp) }, full())
        fun rows(items: List<View>) = items.forEachIndexed { i, r -> if (i > 0) card.addView(listLine(), LinearLayout.LayoutParams(-1, 1.dp)); card.addView(r, full()) }
        sect("오늘")
        val heard = Hub.heardListToday(this)
        if (heard.isEmpty()) note("오늘 들은 메시지가 없습니다")
        rows(heard.map { h -> heardRow(h, null, h.id in Hub.skipped && h.id !in Hub.heard) })
        // 체험 중엔 받을 지난 메시지가 없다: 그리기 전에 정해 '불러오는 중'에 멈추지 않게
        // 자정 뒤에 들은 어제 목록 메시지는 '오늘'에 이미 있다: 지난 메시지에 한 번 더 보이지 않게
        val p = (past ?: if (Hub.demo) emptyList<Pair<Hidden, String>>().also { past = it } else null)?.filter { (h, _) -> heard.none { it.id == h.id } }
        if (p == null) {
            sect("지난 메시지")
            note("불러오는 중")
            // 받는 중이면 다시 그려도 새로 요청하지 않는다(기록 한 줄만 늘어도 화면을 다시 그린다)
            if (!pastLoading) {
                pastLoading = true
                io.execute { val r = runCatching { Api.heardBefore() }; r.getOrNull()?.forEach { runCatching { Store.fetchPhoto(this, it.first.invite, it.first.photo) } }; main.post { pastLoading = false; pastFailed = r.isFailure; past = r.getOrDefault(emptyList()); pastIds += past!!.map { it.first.id }; if (heardOpen) render() } }
            }
        } else if (pastFailed) {
            sect("지난 메시지")
            note("인터넷에 연결되지 않아 불러오지 못했습니다")
            card.addView(button("다시 불러오기", C.CARD, C.CARD_DOWN, C.INK, h = 80, r = 24) { past = null; pastFailed = false; render() }, LinearLayout.LayoutParams(-2, -2).apply { bottomMargin = 24.dp; marginStart = 8.dp })
        } else if (p.isEmpty()) {
            sect("지난 메시지")
            note("지난 30일 동안 들은 메시지가 없습니다")
        } else p.groupBy { it.second }.forEach { (day, items) ->
            val d = runCatching { LocalDate.parse(day) }.getOrNull()
            sect(when { d == null -> day; d == LocalDate.now().minusDays(1) -> "어제"; else -> "${d.monthValue}월 ${d.dayOfMonth}일" })
            rows(items.map { (h, _) -> heardRow(h, d, false) })
        }
        card.addView(space(16))
    }

    // ---------- 동작 ----------

    /** 반복 메시지 계속 듣기/그만 듣기. 그만 들어도 남긴 사람에겐 알리지 않고 화면도 바뀌지 않는다. */
    private fun decideRepeat(h: Hidden, keep: Boolean) {
        Hub.setRepeatAsked(this, h.id)
        Hub.askRepeat = Hub.askRepeat.filter { it.id != h.id }
        Hub.log("${nim(h.sender)} · ${MOMENT_LABEL[h.moment]} 반복 → ${if (keep) "다음에도 듣기" else "그만 듣기"}")
        repeatKeep[h.id] = keep
        // 되돌리면 오늘 안 들은 경우 다시 나올 수 있게, 그만 들으면 오늘도 틀지 않게
        if (keep) { if (h.id !in Hub.heard && h.id !in Hub.heardStored(this)) Hub.opened -= h.id }
        else Hub.opened += h.id
        if (!Hub.demo && !h.example) io.execute {
            runCatching { Api.setRepeat(h.id, keep) }
                .onSuccess { main.post { Hub.unsentRepeats(this).filter { it.startsWith("${h.id}:") }.forEach { Hub.clearUnsentRepeat(this, it) } } }
                .onFailure { main.post { Hub.log("반복 설정 실패 → 다음에 다시 보냄: ${it.message}"); Hub.queueRepeat(this, h.id, keep) } }
        }
        Hub.changed(); render()
        // 알림으로 연 반복 메시지 묻기: 고른 게 잠깐 보인 뒤 다음 것으로, 마지막이면 '모두 정했습니다'
        if (repeatFlow && afterOf?.id == h.id) {
            val next = Hub.askRepeat.firstOrNull { !Hub.repeatAsked(this, it.id) }
            if (next == null) repeatFlow = false   // '모두 정했습니다' 토스트는 뺐다(63번 4장)
            else main.postDelayed({ if (repeatFlow && afterOf?.id == h.id && !driving()) { afterOf = next; render() } }, 700)
        }
    }

    /** 정차 중 5초 답장. 마이크가 안 되면(에뮬레이터 오디오 꺼짐) 샘플 답장으로 흐름만 확인한다. */
    private fun startReply(h: Hidden) {
        // 실제 차에서는 처음 답장할 때 마이크 권한을 묻는다(설치 때 자동 허용 아님)
        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            // 권한 창이 떠도 그 메시지 화면에 머문다(예전엔 홈으로 돌아가 목록에서 다시 들어가야 했다)
            replyAfterPermission = h; afterOf = h; render()
            prefs().edit().putBoolean("micAsked", true).apply()
            requestPermissions(arrayOf(android.Manifest.permission.RECORD_AUDIO), 7); return
        }
        // 바로 녹음하지 않고 3·2·1 뒤에 시작한다(첫마디가 잘리지 않게)
        replying = h; replyPrep = 3; replyLeft = 5; levels.clear(); loudest = 0; recorder = null; sendError = null
        render()
    }

    /** 3·2·1이 끝나면 녹음을 시작한다. */
    private fun beginRecording() {
        if (replying == null) return
        val out = File(cacheDir, "reply.m4a")
        recorder = runCatching {
            MediaRecorder(this).apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setOutputFile(out.absolutePath)
                prepare(); start()
            }
        }.onFailure { Hub.log("마이크 녹음 실패: $it") }.getOrNull()
        replyLeft = 5; levels.clear(); loudest = 0
        render()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        // 속도·위치: 거절했으면 메인 화면이 막는 카드로 바뀐다
        // 허용했으면 대기 서비스가 속도·위치 구독을 다시 건다(처음 켤 때 권한 없이 걸다 실패했으므로)
        if (requestCode == 2) { Hub.log("속도·위치 권한 ${if (carPermsMissing().isEmpty()) "허용" else "거절"} · 알림 ${if (notifMissing()) "거절" else "허용"}"); Hub.service?.resubscribe(); permsSeen = carPermsMissing(); render(); return }
        if (requestCode != 7) return
        val h = replyAfterPermission ?: return
        replyAfterPermission = null
        if (grantResults.firstOrNull() == android.content.pm.PackageManager.PERMISSION_GRANTED && !driving()) {
            answered.remove(h.id); afterOf = null; startReply(h)
        } else {
            Hub.log("마이크 권한이 없어 답장 못 함"); answered[h.id] = MIC_NEED; afterOf = h; render()
        }
    }

    /** 녹음 취소(취소·뒤로·화면 떠남·출발). 정차 중이면 그 메시지 화면으로 돌아간다. */
    private fun cancelReply() {
        val h = replying
        recorder?.let { r -> runCatching { r.stop() }; runCatching { r.release() } }
        recorder = null; replying = null; replyPrep = 0
        if (h != null && !driving()) afterOf = h
        render()
    }

    private fun finishReply() {
        val h = replying ?: return
        val out = File(cacheDir, "reply.m4a")
        val ok = recorder?.let { r -> runCatching { r.stop(); r.release() }.isSuccess && out.length() > 1000 } ?: false
        recorder = null; replying = null
        afterOf = h   // 답장 결과는 그 메시지 화면에서 보여 준다
        // 녹음 중 가장 큰 소리가 너무 작으면(마이크 꺼짐) 녹음이 비었다고 본다. 샘플은 개발 빌드에서만.
        // 샘플 답장은 맥 시연 서버일 때만(클라우드에선 운전자가 하지 않은 답장이 가족 폰에 가면 안 된다)
        if (!(ok && loudest > 200) && !(BuildConfig.DEBUG && Api.BASE.contains("10.0.2.2"))) { answered[h.id] = "소리가 거의 들리지 않았습니다. 다시 녹음해 주세요."; render(); return }   // 문구 은행 #82
        val file = if (ok && loudest > 200) out else File(cacheDir, "reply_sample.m4a").also { f ->
            resources.openRawResource(R.raw.reply_sample).use { i -> f.outputStream().use { i.copyTo(it) } }
            Hub.log("마이크 소리가 없어(최대 $loudest) 샘플 답장으로 바꿈")
        }
        // 바로 보내지 않고 들어 본 뒤 보낸다(주행하면 버린다)
        if (driving()) { Hub.log("주행 중이라 녹음한 답장 버림"); render(); return }
        afterOf = null; review = h; reviewFile = file
        // 방금 녹음한 것을 한 번 저절로 들려준다(정차 중에만 답장하므로 갑작스럽지 않다). 다시 들으려면 동그라미를 누른다
        Hub.log("답장 녹음 끝 → 한 번 들려줌")
        playPreview()
    }

    /** 체험용 예시 답장의 결과(서버로 보내지 않음). */
    private val DEMO_SENT = "예시 메시지는 보내지 않습니다"

    /** [보내기]: 버튼을 로딩으로 두고 보낸다. 되면 그 메시지 화면 + 토스트, 못 하면 이 화면에 남아 같은 녹음을 다시 보낼 수 있다. */
    private fun sendReply(h: Hidden, file: File) {
        if (sending) return
        // 예시 메시지는 끝까지 해 보되 서버에는 보내지 않는다(id가 demo-라 서버에 없다)
        if (Hub.demo || h.example) {
            answered[h.id] = DEMO_SENT; Hub.log("체험 메시지라 답장은 보내지 않음")
            review = null; reviewFile = null; afterOf = h; render(); return  // 들은 뒤 화면 아래 줄에 같은 말이 남아서 토스트는 띄우지 않는다
        }
        sending = true; render()
        io.execute {
            val r = runCatching { Api.reply(h.id, file, "audio/mp4") }
            main.post {
                sending = false
                Hub.log(if (r.isSuccess) "${nim(h.sender)}에게 답장 보냄" else "답장 실패: ${r.exceptionOrNull()?.message}")
                if (r.isSuccess) {
                    sendError = null
                    answered[h.id] = "답장 보냄"; markReplied(h.id)
                    // 주행을 시작해 녹음이 버려졌어도 보낸 결과는 남긴다
                    if (review?.id == h.id) { review = null; reviewFile = null }
                    if (!driving()) afterOf = h
                    render(); toast(who(h)?.let { "${it}에게 답장을 보냈습니다" } ?: "답장을 보냈습니다")
                } else {
                    val e = r.exceptionOrNull()
                    val msg = e?.message ?: ""
                    if (msg.contains("답장할 메시지가 없") || msg.startsWith("서버 404") || msg.startsWith("서버 410")) {
                        // 남긴 사람이 지운 메시지: 다시 보내도 계속 실패하니 녹음을 버리고 그 메시지 화면에서 이유를 보여 준다
                        goneIds += h.id
                        if (review?.id == h.id) { review = null; reviewFile = null; sendError = null }
                        if (!driving()) afterOf = h
                        render(); return@post
                    }
                    sendError = when {
                        e is java.io.IOException -> "인터넷에 연결되지 않아 보내지 못했습니다"
                        msg.contains("짧아요") -> "조금 더 길게 말해 주세요"   // 문구 은행 #83
                        else -> "보내지 못했습니다"
                    }
                    render(); toast(sendError!!)
                }
            }
        }
    }

    /** 재생 막대·녹음 카운트다운을 0.2초마다 갱신한다(화면 전체를 다시 그리지 않음). */
    private val MIC_NEED = "마이크를 허용해야 답장할 수 있습니다"

    private val ticker = object : Runnable {
        private var last = 0L
        override fun run() {
            tick()
            if (replying != null && replyPrep > 0) {
                // 3·2·1: 숫자만 바꾸고, 0이 되면 녹음 시작
                val now = System.currentTimeMillis()
                if (last == 0L) last = now
                if (now - last >= 1000) {
                    last = now; replyPrep--
                    if (replyPrep <= 0) { last = 0L; replyPrep = 0; beginRecording() } else countView?.text = "$replyPrep"
                }
            } else if (replying != null) {
                recorder?.let { r -> runCatching { val a = r.maxAmplitude; loudest = maxOf(loudest, a); levels.addLast(a / 32767f) } }
                if (levels.size > 40) levels.removeFirst()
                wave?.invalidate()
                val now = System.currentTimeMillis()
                if (last == 0L) last = now
                if (now - last >= 1000) {
                    last = now; replyLeft--
                    countView?.text = "$replyLeft"
                    if (replyLeft <= 0) { last = 0L; finishReply() }
                }
            } else last = 0L
            main.postDelayed(this, 200)
        }
    }

    private fun tick() {
        preview?.let { p -> runCatching { if (p.duration > 0) previewBar?.ratio = p.currentPosition.toFloat() / p.duration } }
        practicePlayer?.let { p -> runCatching { if (p.duration > 0) bar?.ratio = p.currentPosition.toFloat() / p.duration }; return }
        val (now, all) = Hub.service?.progress() ?: return
        if (all <= 0) return
        // 광장 재생 패널: 막대는 들은 만큼만 칠한다(높이는 그대로)
        panelBars?.ratio = now.toFloat() / all
        panelNow?.text = clock(now)
        panelAll?.text = clock(fullLen(all))
        bar?.ratio = now.toFloat() / all
        timeNow?.text = clock(now)
        timeAll?.text = " / ${clock(fullLen(all))}"
    }

    private fun clock(ms: Int) = "%d:%02d".format(ms / 60000, (ms / 1000) % 60)
    /** 녹음 전체 길이: 반올림하고 최소 1초(0.9초짜리가 '0:00'으로 보이지 않게). 재생 중 지난 시간은 그대로 내림. */
    private fun fullLen(ms: Int) = maxOf(1, (ms + 500) / 1000) * 1000
    /** 읽어 주기용 길이: '0:03'은 시각처럼 읽혀서 '3초'·'1분 5초'로. */
    private fun seconds(ms: Int): String {
        val sec = maxOf(1, ms / 1000)
        return if (sec < 60) "${sec}초" else "${sec / 60}분" + if (sec % 60 > 0) " ${sec % 60}초" else ""
    }

    // ---------- 그리는 도구 ----------

    /** 앱 헤더(Page Navigation): 최상위는 로고+제목+톱니, 하위 화면은 ‹+제목(+⋯). 높이 100, 제목 36/600(63번 4장).
     *  g: 광장 화면이면 비·눈·밤 바탕과 글자색을 따라간다. 아래 1px 선은 하위 화면에만. */
    private fun header(g: Ground? = null): View {
        val sub = when {
            replying != null || review != null -> "답장"
            // 정차 중 듣는 화면도 뒤로(멈춤)가 보이게
            Hub.nowPlaying != null && !driving() -> "듣는 중"
            // 도착 장면은 다른 화면보다 먼저 그려지니(render) 머리줄도 늘 '도담도담'
            Hub.offered != null && !driving() && Hub.onboarded(this) -> null
            familyOpen -> "사람·초대"
            afterOf != null -> "들은 메시지"
            examplesOpen -> "예시 메시지"
            webOpen != null -> webOpen!!.first
            permOpen -> "권한"
            modeOpen -> "듣는 방식"
            heardOpen -> "들은 메시지"
            orderOpen -> "자리 바꾸기"
            settingsOpen -> "설정"
            // 처음 켜기 2단계부터는 화면에서 앞 단계로 돌아갈 수 있게
            !Hub.onboarded(this) && onboardStep == 1 && !driving() -> "권한"
            !Hub.onboarded(this) && onboardStep == 2 && !driving() -> ""   // 칸 라벨 '초대장에 쓸 내 이름'만 남기고 머리줄은 비운다
            !Hub.onboarded(this) && onboardStep == 3 && !driving() -> "예시 메시지"
            !Hub.onboarded(this) && onboardStep >= 4 && !driving() -> "듣는 방식"
            else -> null
        }
        val bg = if (g?.on == true) g.bg else C.PAGE
        val ink = g?.ink ?: C.INK
        val down = g?.doorDown ?: C.CARD
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            minimumHeight = 100.dp; setPadding(24.dp, 0, 20.dp, 0); setBackgroundColor(bg)
        }
        fun iconBtn(kind: String, what: String, onClick: () -> Unit) = FrameLayout(this).apply {
            contentDescription = what
            pressable(this, bg, down, bg, radius = 24, onClick = onClick)
            addView(Icon(this@MainActivity, kind, ink), FrameLayout.LayoutParams(44.dp, 44.dp, Gravity.CENTER))
        }
        if (sub != null) {
            // 뒤로: 글자 '‹' 대신 선 아이콘(다른 아이콘과 같은 굵기), 누르는 칸 76dp
            row.addView(iconBtn("back", "뒤로") { onBackPressed() }, LinearLayout.LayoutParams(76.dp, 76.dp).apply { marginEnd = 12.dp })
            row.addView(text(sub, T.TITLE, ink, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
            // 들은 메시지 한 장: 신고는 머리줄 ⋯ 메뉴로(63번 4장). 정차 중·진짜 메시지·지우지 않은 것만
            val h = afterOf
            if (h != null && sub == "들은 메시지" && stopped() && !Hub.demo && !h.example && !gone(h))
                row.addView(iconBtn("more", "더 보기") { menu = Menu(who(h) ?: "음성 메시지", listOf("신고하기" to { askReport(h) })); render() }, LinearLayout.LayoutParams(76.dp, 76.dp))
        } else {
            row.addView(logoTile(62), LinearLayout.LayoutParams(62.dp, 62.dp).apply { marginEnd = 20.dp })   // 로고 62(Pleos 실측)
            row.addView(text("도담도담", T.TITLE, ink, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
            // 톱니 = 설정(Material Symbols Rounded settings 근사, 44dp)
            if (Hub.onboarded(this) && !driving()) row.addView(iconBtn("settings", "설정") { settingsOpen = true; render() }, LinearLayout.LayoutParams(76.dp, 76.dp))
        }
        if (sub == null) return row
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        box.addView(row, full())
        box.addView(View(this).apply { setBackgroundColor(g?.line ?: C.LINE) }, LinearLayout.LayoutParams(-1, 1.dp))
        return box
    }

    /** 머리줄 앱 표시: 런처 아이콘의 보이는 부분(하늘·도로 + 말풍선)을 둥근 네모로. 다크에서도 그대로(브랜드 표시). */
    private fun logoTile(size: Int) = ImageView(this).apply {
        setImageResource(R.drawable.logo_tile); scaleType = ImageView.ScaleType.CENTER_CROP
        outlineProvider = object : android.view.ViewOutlineProvider() {
            override fun getOutline(v: View, o: android.graphics.Outline) { o.setRoundRect(0, 0, v.width, v.height, (size / 5).dp.toFloat()) }
        }
        clipToOutline = true
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
    }

    private fun box(fill: Int, stroke: Int, oval: Boolean = false, radius: Int = 20) = GradientDrawable().apply {
        setColor(fill)
        if (oval) shape = GradientDrawable.OVAL else cornerRadius = radius.dp.toFloat()
    }

    /** 누르는 동안 95%로 작아진다(150ms). */
    private val pressShrink = View.OnTouchListener { view, e ->
        when (e.action) {
            MotionEvent.ACTION_DOWN -> view.animate().scaleX(0.95f).scaleY(0.95f).setDuration(150).start()
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> view.animate().scaleX(1f).scaleY(1f).setDuration(150).start()
        }
        false
    }

    /** 누름 반응(interaction): 95%로 작아지고 배경이 바뀐다(150ms) + 진동 피드백. */
    private fun pressable(v: View, fill: Int, down: Int, stroke: Int, oval: Boolean = false, radius: Int = 20, onClick: () -> Unit) {
        v.background = StateListDrawable().apply {
            addState(intArrayOf(android.R.attr.state_pressed), box(down, stroke, oval, radius))
            addState(intArrayOf(), box(fill, stroke, oval, radius))
        }
        v.isClickable = true
        v.setOnTouchListener(pressShrink)
        v.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            onClick()
        }
    }

    /** 켜고 끄는 줄. 차에서는 작은 스위치만 누르기 어려워서 줄 전체를 눌러도 바뀐다.
     *  스위치(63번 4장): 켜짐 초록 #02C265(Pleos switch_on), 80×48, 손잡이 둥근 네모 36, 꺼짐 #E0E1E6. */
    private fun switchRow(title: String, desc: String, on: Boolean, onChange: (Boolean) -> Unit) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = 100.dp; setPadding(8.dp, 20.dp, 8.dp, 20.dp)
        pressable(this, Color.TRANSPARENT, C.CARD, Color.TRANSPARENT) { onChange(!on) }
        val col = LinearLayout(this@MainActivity).apply { orientation = LinearLayout.VERTICAL }
        col.addView(text(title, T.BODY, C.INK))
        col.addView(text(desc, T.LABEL, C.SUB))
        addView(col, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = 24.dp })
        val track = FrameLayout(this@MainActivity).apply { background = GradientDrawable().apply { cornerRadius = 14.dp.toFloat(); setColor(if (on) C.SWITCH_ON else C.TRACK_OFF) } }
        track.addView(View(this@MainActivity).apply { background = GradientDrawable().apply { cornerRadius = 10.dp.toFloat(); setColor(Color.WHITE) } },
            FrameLayout.LayoutParams(36.dp, 36.dp, (if (on) Gravity.END else Gravity.START) or Gravity.CENTER_VERTICAL).apply { setMargins(6.dp, 0, 6.dp, 0) })
        addView(track, LinearLayout.LayoutParams(80.dp, 48.dp))
        contentDescription = "$title ${if (on) "켜짐" else "꺼짐"}"
    }

    /** 섹션 제목(63번 4장): 28/600 #131417, 위 40·아래 16. */
    private fun section(s: String, top: Int = 40) = text(s, T.BODY, C.INK, bold = true).apply { setPadding(4.dp, top.dp, 0, 16.dp) }

    private fun space(h: Int) = View(this).apply { layoutParams = LinearLayout.LayoutParams(1, h.dp) }

    private fun full() = LinearLayout.LayoutParams(-1, -2)

    /** 글자 한 줄. bold = 600(제목 줄·버튼), w로 700·400을 직접 고른다(63번 2장 굵기). */
    private fun text(s: String, size: Float, color: Int, bold: Boolean = false, center: Boolean = false, w: Int = if (bold) T.W6 else T.W4) = TextView(this).apply {
        text = s; textSize = size; setTextColor(color)
        typeface = Typeface.create(Typeface.DEFAULT, w, false)
        if (center) gravity = Gravity.CENTER
        val lh = T.LINE[size]
        if (lh != null) lineHeight = android.util.TypedValue.applyDimension(android.util.TypedValue.COMPLEX_UNIT_SP, lh, resources.displayMetrics).toInt()
        else setLineSpacing(0f, 1.2f)
    }

    /** 버튼 한 개(63번 2장): Large 높이 100·모서리 32 / Medium 80·24 / 팝업 96·30, 글자 28/600. 폭은 글자에 맞추고 최소 240. */
    private fun button(label: String, fill: Int, down: Int, ink: Int, h: Int = 100, r: Int = 32, onClick: () -> Unit) = text(label, T.BODY, ink, bold = true, center = true).apply {
        minHeight = h.dp; minWidth = 240.dp; setPadding(40.dp, 0, 40.dp, 0)
        pressable(this, fill, down, fill, radius = r, onClick = onClick)
    }

    /** 주 버튼(Large): 진회색 #44464E + 흰 글자. */
    private fun primary(label: String, onClick: () -> Unit) = button(label, C.PRIMARY, C.PRIMARY_DOWN, C.ON_INK, onClick = onClick)

    /** 보조 버튼(Large): 회색 #F3F3F3 + #131417 글자. */
    private fun outline(label: String, onClick: () -> Unit) = button(label, C.CARD, C.CARD_DOWN, C.INK, onClick = onClick)

    /** 버튼 여럿을 가로로(글자 폭, 사이 24, 왼쪽부터). 840 전체 폭 버튼 대신. */
    private fun btnRow(vararg b: View) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        b.forEachIndexed { i, v -> addView(v, LinearLayout.LayoutParams(-2, -2).apply { if (i > 0) marginStart = 24.dp }) }
    }
    /** 버튼 한 개 자리(글자 폭). */
    private fun btnLp() = LinearLayout.LayoutParams(-2, -2)

    /** 서버 답을 기다리는 버튼(Pleos 버튼 '로딩' 상태): 같은 자리·크기에 도는 표시만, 누를 수 없음. */
    private fun busy(fill: Int, doing: String, h: Int = 100, r: Int = 32) = FrameLayout(this).apply {
        minimumHeight = h.dp; minimumWidth = 240.dp
        background = box(fill, fill, radius = r)
        contentDescription = doing   // 읽어 주기: '보내는 중'처럼 버튼마다 하는 일
        val tint = if (fill == C.CARD) C.INK else C.ON_INK
        addView(android.widget.ProgressBar(this@MainActivity).apply {
            isIndeterminate = true; indeterminateTintList = android.content.res.ColorStateList.valueOf(tint)
        }, FrameLayout.LayoutParams(48.dp, 48.dp, Gravity.CENTER))
    }

    /** 재생 막대: 채움은 진회색(답장 들어 보기는 보낸 사람 대표색), 바탕 #E0E1E6, 끝은 둥글게. */
    private inner class Bar(ctx: Context, private val tint: Int = C.PRIMARY) : View(ctx) {
        var ratio = 0f; set(v) { field = v.coerceIn(0f, 1f); invalidate() }
        private val p = Paint(Paint.ANTI_ALIAS_FLAG)
        override fun onDraw(c: Canvas) {
            val y = height / 2f; val r = 12.dp.toFloat(); val x = r + (width - 2 * r) * ratio
            p.style = Paint.Style.STROKE; p.strokeWidth = 6.dp.toFloat(); p.strokeCap = Paint.Cap.ROUND
            p.color = C.LINE; c.drawLine(r, y, width - r, y, p)
            if (ratio > 0f) { p.color = tint; c.drawLine(r, y, x, y, p) }
        }
    }

    /** 녹음 중 소리 크기 막대. */
    private inner class Wave(ctx: Context) : View(ctx) {
        private val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeCap = Paint.Cap.ROUND }
        override fun onDraw(c: Canvas) {
            p.color = C.PRIMARY   // 소리 막대 #44464E
            val n = 40; val gap = width / n.toFloat(); p.strokeWidth = gap * 0.45f
            val list = levels.toList()
            for (i in 0 until n) {
                val v = list.getOrNull(i - (n - list.size)) ?: 0f
                val h = (0.15f + 0.85f * minOf(1f, v * 4f)) * height / 2
                val x = gap * (i + 0.5f)
                c.drawLine(x, height / 2f - h, x, height / 2f + h, p)
            }
        }
    }
}
