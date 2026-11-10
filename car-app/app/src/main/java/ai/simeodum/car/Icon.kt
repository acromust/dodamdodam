package ai.simeodum.car

import android.content.Context
import android.graphics.Canvas
import android.graphics.CornerPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.View

/**
 * 선 아이콘(Pleos 실제 UI처럼 평면). 24칸 격자에 선 굵기 2.0 하나로 그려서 크기에 맞춰 늘린다(63번 2장).
 * 채움: play · pause · stop · mic(몸통) · more(⋯) · person · skip. 선: back · next · check · settings · speed · location · bell · wheel.
 * settings·speed·location·bell·mic 은 Material Symbols Rounded(Apache 2.0) settings·speed·location_on·notifications·mic 모양을 이 격자에 옮겨 그린 근사(파일을 내려받지 않음).
 * kind: person · mic · pause · play · stop · skip(⏭) · more · back · next · check · close(✕) · settings · speed · location · bell · wheel(핸들 가운데 버튼)
 */
class Icon(ctx: Context, var kind: String, var color: Int) : View(ctx) {
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }

    override fun onDraw(c: Canvas) {
        val s = minOf(width, height) / 24f
        c.save()
        c.translate((width - 24 * s) / 2, (height - 24 * s) / 2)
        c.scale(s, s)
        line.color = color; fill.color = color
        line.strokeWidth = 2f
        line.pathEffect = null; fill.pathEffect = null
        when (kind) {
            "person" -> {
                c.drawCircle(12f, 8f, 3.6f, fill)
                c.drawPath(Path().apply { moveTo(4.5f, 20f); cubicTo(4.5f, 13.5f, 19.5f, 13.5f, 19.5f, 20f); close() }, fill)
            }
            "mic" -> { // 몸통은 채움, 받침 곡선·기둥은 선
                c.drawRoundRect(RectF(8.8f, 2.5f, 15.2f, 14.2f), 3.2f, 3.2f, fill)
                c.drawPath(Path().apply { moveTo(5.5f, 11f); cubicTo(5.5f, 19f, 18.5f, 19f, 18.5f, 11f) }, line)
                c.drawLine(12f, 17.2f, 12f, 21f, line)
            }
            "pause" -> { c.drawRoundRect(RectF(6.5f, 5f, 10f, 19f), 1.2f, 1.2f, fill); c.drawRoundRect(RectF(14f, 5f, 17.5f, 19f), 1.2f, 1.2f, fill) }
            "stop" -> c.drawRoundRect(RectF(6f, 6f, 18f, 18f), 2f, 2f, fill)
            // 무게중심을 칸 가운데로 맞춘 삼각형(63번 5장), 꼭짓점은 둥글게
            "play" -> { fill.pathEffect = CornerPathEffect(1.6f); c.drawPath(Path().apply { moveTo(9.3f, 5.5f); lineTo(19.8f, 12f); lineTo(9.3f, 18.5f); close() }, fill) }
            "skip" -> { // ⏭ 다음 메시지
                fill.pathEffect = CornerPathEffect(1.4f)
                c.drawPath(Path().apply { moveTo(6f, 6f); lineTo(15f, 12f); lineTo(6f, 18f); close() }, fill)
                fill.pathEffect = null
                c.drawRoundRect(RectF(15.8f, 6f, 18.2f, 18f), 1.2f, 1.2f, fill)
            }
            "more" -> { c.drawCircle(5f, 12f, 1.9f, fill); c.drawCircle(12f, 12f, 1.9f, fill); c.drawCircle(19f, 12f, 1.9f, fill) }
            "back" -> c.drawPath(Path().apply { moveTo(15f, 4.5f); lineTo(7.5f, 12f); lineTo(15f, 19.5f) }, line) // 머리줄 뒤로
            "next" -> c.drawPath(Path().apply { moveTo(9f, 4.5f); lineTo(16.5f, 12f); lineTo(9f, 19.5f) }, line) // 줄 끝 들어가기 꺾쇠
            "close" -> { c.drawLine(6f, 6f, 18f, 18f, line); c.drawLine(18f, 6f, 6f, 18f, line) } // 패널 닫기 ✕
            "check" -> c.drawPath(Path().apply { moveTo(4.5f, 12.5f); lineTo(9.5f, 17.5f); lineTo(19.5f, 6.5f) }, line) // 고른 칸 표시
            "settings" -> { // 톱니(Material Symbols Rounded settings 근사): 이 6개 + 가운데 구멍, 모서리는 둥글게
                line.pathEffect = CornerPathEffect(1.1f)
                c.drawPath(gear(), line)
                line.pathEffect = null
                c.drawCircle(12f, 12f, 3.1f, line)
            }
            "speed" -> { // 속도계(speed): 위가 열린 눈금 호 + 바늘
                c.drawArc(RectF(3f, 4.5f, 21f, 22.5f), 150f, 240f, false, line)
                c.drawLine(12f, 13.5f, 16.6f, 8.9f, line)
                c.drawCircle(12f, 13.5f, 1.7f, fill)
            }
            "location" -> { // 위치 핀(location_on)
                c.drawPath(Path().apply {
                    moveTo(12f, 21.5f)
                    cubicTo(12f, 21.5f, 5f, 14.9f, 5f, 9.6f)
                    arcTo(RectF(5f, 2.6f, 19f, 16.6f), 180f, 180f, false)
                    cubicTo(19f, 14.9f, 12f, 21.5f, 12f, 21.5f)
                    close()
                }, line)
                c.drawCircle(12f, 9.6f, 2.4f, line)
            }
            "bell" -> { // 알림(notifications)
                c.drawPath(Path().apply {
                    moveTo(4.5f, 17.5f); lineTo(19.5f, 17.5f)
                    moveTo(6.5f, 17.5f); lineTo(6.5f, 10.6f)
                    cubicTo(6.5f, 7.2f, 8.9f, 4.8f, 12f, 4.8f)
                    cubicTo(15.1f, 4.8f, 17.5f, 7.2f, 17.5f, 10.6f)
                    lineTo(17.5f, 17.5f)
                }, line)
                c.drawLine(10.2f, 20.6f, 13.8f, 20.6f, line)
                c.drawLine(12f, 2.6f, 12f, 4.8f, line)
            }
            "wheel" -> { // 핸들 가운데 버튼: 둥근 네모 선 안에 가운데 원
                c.drawRoundRect(RectF(3f, 3f, 21f, 21f), 5.5f, 5.5f, line)
                c.drawCircle(12f, 12f, 3.8f, fill)
            }
        }
        c.restore()
    }

    /** 톱니 바깥선: 이 6개(위·아래·대각 4개), 이 끝 반지름 9.6, 몸통 반지름 7.3. */
    private fun gear() = Path().apply {
        val r0 = 7.3f; val r1 = 9.6f
        fun pt(r: Float, deg: Double) = Pair(12f + r * Math.cos(Math.toRadians(deg)).toFloat(), 12f + r * Math.sin(Math.toRadians(deg)).toFloat())
        for (i in 0 until 6) {
            val a = -90.0 + i * 60.0
            val (bx, by) = pt(r0, a - 17)
            if (i == 0) moveTo(bx, by) else lineTo(bx, by)
            pt(r1, a - 11).let { (x, y) -> lineTo(x, y) }
            pt(r1, a + 11).let { (x, y) -> lineTo(x, y) }
            pt(r0, a + 17).let { (x, y) -> lineTo(x, y) }
            // 이 사이는 몸통 원을 따라
            arcTo(RectF(12f - r0, 12f - r0, 12f + r0, 12f + r0), (a + 17).toFloat(), 26f, false)
        }
        close()
    }
}
