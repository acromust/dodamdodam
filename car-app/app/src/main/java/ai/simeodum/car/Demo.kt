package ai.simeodum.car

import android.content.Context

/** 예시 메시지인지(id가 demo-로 시작). 진짜가 아니라서 서버로 보내지 않고 답장·신고·다음에도 듣기도 없다. */
val Hidden.example get() = id.startsWith("demo-")

/**
 * 예시 메시지: 메인 장면처럼 운전자는 아빠, 남긴 사람은 딸 지윤·아내 수진(지어낸 이름).
 * 서버에 닿지 못하고 저장해 둔 메시지도 없을 때(심사용 APK를 처음 깔았을 때) 자동으로 쓰고, 정차 중 화면의 '예시 메시지'에서 언제든 골라 들을 수 있다.
 * 음성은 제미나이 TTS(gemini-2.5-flash-preview-tts, 목소리 Sulafat·Leda)로 만든 지윤·수진 예시로 앱 안(res/raw)에 들어 있어서 인터넷 없이도 바로 들린다. 서버에 닿으면 진짜 메시지로 바뀐다.
 */
object Demo {
    private class Item(val moment: String, val sender: String, val raw: Int, val line: String, val repeat: String = "once")

    private val items = listOf(
        Item("start", "수진", R.raw.demo_start, "오늘 3시 치과 예약 있는 거 잊지 마요."),
        Item("rain", "지윤", R.raw.demo_rain, "아빠, 비 오니까 천천히 와요. 엄마가 뒷자리 아래 우산 있대요!", repeat = "each"), // 반복 메시지: 주차하면 '다음에도 들을까요?'
        Item("home", "지윤", R.raw.demo_home, "아빠, 오는 길에 바나나 우유 하나만 사다 주시면 안 돼요?"),
        Item("long", "수진", R.raw.demo_long, "여보, 많이 달렸죠? 다음 휴게소에서 커피 한잔하고 좀 쉬었다 가요."),
        Item("battery", "수진", R.raw.demo_battery, "여보, 글로브박스 안에 포인트카드 있으니까 충전할 때 적립 꼭 해요."),
        Item("arrive", "지윤", R.raw.demo_arrive, "아빠, 오늘도 운전하느라 수고 많으셨어요!"),
    )

    private fun hidden(i: Item) = Hidden("demo-${i.moment}", i.sender, i.moment, "/demo/${i.moment}.m4a", false, false, i.repeat)

    /** 예시 메시지 목록(파일은 꺼내지 않는다). 목록 화면에 쓴다. */
    fun examples(): List<Hidden> = items.map(::hidden)

    /** 예시 메시지의 말(목록에 작은 글자로). */
    fun line(h: Hidden): String? = items.firstOrNull { "demo-${it.moment}" == h.id }?.line

    /** 예시 음성 파일을 재생 위치로 꺼내 둔다(백그라운드 스레드에서). 앱이 바뀌면 예시 음성도 바뀔 수 있으니 매번 새로 꺼낸다(몇십 KB). */
    fun prepare(c: Context, h: Hidden) {
        val i = items.firstOrNull { "demo-${it.moment}" == h.id } ?: return
        c.resources.openRawResource(i.raw).use { input -> Store.audioFile(c, h).outputStream().use { input.copyTo(it) } }
    }

    /** 예시 메시지 목록. 음성 파일까지 꺼내 둔다(백그라운드 스레드에서 불러도 된다). */
    fun messages(c: Context): List<Hidden> = examples().onEach { prepare(c, it) }
}
