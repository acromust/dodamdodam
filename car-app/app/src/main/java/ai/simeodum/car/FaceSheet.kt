package ai.simeodum.car

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import org.json.JSONObject

/**
 * 얼굴 그림(face.png)을 GPT가 그린 부품 그림 모음(assets/face_atlas.png + face_atlas.json)으로 합친다.
 * 아틀라스는 car-app/tools/char/face_atlas.py 가 만든다: 부품을 문서 56 정면 배치(512px = 머리 반지름)에 놓고,
 * plaza_char2.glb 얼굴 조각의 공 모양 펼침 UV에 맞춰 미리 휘어 둔 것 → 여기서는 칸(dst)에 붙이기만 한다.
 * 순서: 피부 바탕 → 짧은 수염 → 볼터치 → 주름 → 코 → 입 → 눈 → 눈썹. 눈썹은 머리색, 수염은 수염색을 곱한다.
 * 피부 맞춤(11/10): 주름·코는 피부보다 한 단 어두운 색(tint skin), 볼터치는 피부 밝기에 따라 분홍~장밋빛(tint pair),
 * 눈썹·짧은 수염은 피부와 밝기 차가 sep 보다 작으면 어둡게. 식은 face_atlas.py compose() · avatar3d.js paintOf 와 같다.
 * 주름 3(눈가+이마)은 json 에 두 층이 담겨 있어 따로 처리할 것이 없다.
 * 층의 unless_eyes(11/10 79번): 그 눈 번호면 이 층은 안 그린다(애교살 눈 15 + 눈 밑 선은 같은 자리).
 * 11/10: by_eyes(눈 번호 → 그림 칸, 눈가 주름은 눈마다 바깥 끝 옆), need({칸: 비트} 켜졌을 때만, 짧은 수염 위 주름·주근깨 자리 비우기),
 * shade(짧은 수염: 짙은 피부일수록 피부 그늘색 쪽으로). face_atlas.py compose() · avatar3d.js faceSheet 와 같다.
 * 아틀라스를 못 읽으면 null → Plaza.drawFace 가 예전 도형 그리기로 그린다.
 */
object FaceSheet {
    private class Layer(val src: Rect, val l: Float, val t: Float, val r: Float, val b: Float,
                        val mirror: Boolean, val alpha: Float, val alphaDark: Float, val tint: Int, val mean: Float,
                        val k0: Float, val k1: Float, val c0: Int, val c1: Int, val sep: Float, val unlessEyes: IntArray,
                        val byEyes: Array<Spr>?, val need: IntArray, val shade: FloatArray?)
    /** 그림 한 칸(아틀라스 src → 얼굴 dst). 눈가 주름은 눈마다 다른 칸(by_eyes) */
    private class Spr(val src: Rect, val l: Float, val t: Float, val r: Float, val b: Float)
    private class Sheet(val atlas: Bitmap, val groups: List<Pair<Int, List<List<Layer>>>>, val tLo: Float, val tHi: Float)

    private const val TINT_NONE = 0; private const val TINT_HAIR = 1; private const val TINT_BEARD = 2
    private const val TINT_SKIN = 3; private const val TINT_PAIR = 4
    private val KEY_INDEX = mapOf("eyes" to Plaza.EYES, "brows" to Plaza.BROWS, "nose" to Plaza.NOSE, "mouth" to Plaza.MOUTH,
        "wrinkle" to Plaza.WRINKLE, "blush" to Plaza.BLUSH, "beard" to Plaza.BEARD, "mark" to Plaza.MARK,
        "beards" to Plaza.BEARDS, "marks" to Plaza.MARKS)   // 11/10: draw_order 는 비트 칸(beards·marks)만 그린다(beard·mark 묶음은 예전 앱용으로 남김)

    @Volatile private var sheet: Sheet? = null
    @Volatile private var tried = false

    /** 한 번만 읽는다(약 2MB). Plaza.load 에서 부르고, 못 불렸으면 첫 draw 때 앱 Context 를 찾아 읽는다. */
    fun init(c: Context) {
        if (tried) return
        synchronized(this) {
            if (tried) return
            tried = true
            runCatching { sheet = read(c.applicationContext) }.onFailure { Hub.log("얼굴 부품 그림 못 읽음: ${it.message}") }
        }
    }

    private fun read(c: Context): Sheet {
        val j = JSONObject(c.assets.open("face_atlas.json").bufferedReader().use { it.readText() })
        val atlas = c.assets.open("face_atlas.png").use {
            BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inPreferredConfig = Bitmap.Config.ARGB_8888; inScaled = false })
        } ?: error("decode")
        val spr = j.getJSONArray("sprites")
        val groups = j.getJSONObject("groups")
        val order = j.getJSONArray("draw_order")
        val out = ArrayList<Pair<Int, List<List<Layer>>>>()
        for (k in 0 until order.length()) {
            val key = order.getString(k); val idx = KEY_INDEX[key] ?: continue
            val opts = groups.optJSONArray(key) ?: continue
            out += idx to (0 until opts.length()).map { o ->
                val ls = opts.getJSONArray(o)
                (0 until ls.length()).map { n ->
                    val L = ls.getJSONObject(n); val s = spr.getJSONObject(L.getInt("sprite"))
                    val src = s.getJSONArray("src"); val dst = s.getJSONArray("dst")
                    val x = src.getInt(0); val y = src.getInt(1)
                    fun sprOf(i: Int): Spr { val o = spr.getJSONObject(i); val r = o.getJSONArray("src"); val d = o.getJSONArray("dst")
                        return Spr(Rect(r.getInt(0), r.getInt(1), r.getInt(0) + r.getInt(2), r.getInt(1) + r.getInt(3)),
                            d.getDouble(0).toFloat(), d.getDouble(1).toFloat(), d.getDouble(2).toFloat(), d.getDouble(3).toFloat()) }
                    // 11/10 need: {칸 이름: 비트} 모두 켜졌을 때만 그림(짧은 수염 위 주름·주근깨 자리 비우기). [칸 번호, 비트, ...]
                    val nd = L.optJSONObject("need"); val need = ArrayList<Int>()
                    nd?.keys()?.forEach { kk -> KEY_INDEX[kk]?.let { need += it; need += nd.getInt(kk) } }
                    val al = L.optDouble("alpha", 1.0).toFloat()
                    val k = L.optJSONArray("k"); val c = L.optJSONArray("c")
                    Layer(Rect(x, y, x + src.getInt(2), y + src.getInt(3)),
                        dst.getDouble(0).toFloat(), dst.getDouble(1).toFloat(), dst.getDouble(2).toFloat(), dst.getDouble(3).toFloat(),
                        L.optBoolean("mirror"), al, L.optDouble("alpha_dark", al.toDouble()).toFloat(),
                        when (L.optString("tint")) { "hair" -> TINT_HAIR; "beard" -> TINT_BEARD; "skin" -> TINT_SKIN; "pair" -> TINT_PAIR; else -> TINT_NONE },
                        L.optDouble("mean", 1.0).toFloat(),
                        k?.optDouble(0, 1.0)?.toFloat() ?: 1f, k?.optDouble(1, 1.0)?.toFloat() ?: 1f,
                        c?.optString(0)?.let(::parseHex) ?: Color.WHITE, c?.optString(1)?.let(::parseHex) ?: Color.WHITE,
                        L.optDouble("sep", -1.0).toFloat(),
                        L.optJSONArray("unless_eyes")?.let { u -> IntArray(u.length()) { u.optInt(it, -1) } } ?: IntArray(0),
                        L.optJSONArray("by_eyes")?.let { u -> Array(u.length()) { sprOf(u.getInt(it)) } },
                        need.toIntArray(),
                        L.optJSONArray("shade")?.let { u -> FloatArray(3) { u.optDouble(it, 0.0).toFloat() } })
                }
            }
        }
        val st = j.optJSONArray("skin_t")
        return Sheet(atlas, out, st?.optDouble(0, 0.40)?.toFloat() ?: 0.40f, st?.optDouble(1, 0.89)?.toFloat() ?: 0.89f)
    }

    private fun parseHex(h: String): Int = runCatching { Color.parseColor(h) }.getOrDefault(Color.WHITE)

    /** 밝기(Rec.601 luma, 0~1). face_atlas.py _luma · avatar3d.js luma 와 같은 식 */
    private fun luma(c: Int) = (0.299f * Color.red(c) + 0.587f * Color.green(c) + 0.114f * Color.blue(c)) / 255f
    private fun rnd(v: Float) = Math.floor(v + 0.5).toInt().coerceIn(0, 255)
    private fun scale(c: Int, k: Float) = Color.rgb(rnd(Color.red(c) * k), rnd(Color.green(c) * k), rnd(Color.blue(c) * k))

    /** 층 하나에 곱할 색(없으면 null)과 alpha(0~1). skin = 이 사람 피부색, t = 0(짙은 피부)~1(밝은 피부) */
    private fun paintOf(L: Layer, a: IntArray, skin: Int, t: Float): Pair<Int?, Float> {
        val al = (L.alphaDark + (L.alpha - L.alphaDark) * t).coerceIn(0f, 1f)
        val col: Int? = when (L.tint) {
            TINT_HAIR, TINT_BEARD -> {
                val c = if (L.tint == TINT_HAIR) Plaza.hairColor(a) else Plaza.beardColor(a)
                val lc = luma(c); val ls = luma(skin)
                // 피부와 밝기가 너무 비슷하면(금발·흰머리 눈썹 × 밝은 피부 등) 피부 밝기 - sep 까지 어둡게
                val c2 = if (L.sep > 0f && Math.abs(lc - ls) < L.sep) scale(c, maxOf(ls - L.sep, 0.04f) / maxOf(lc, 1e-3f)) else c
                // 11/10 짧은 수염: 짙은 피부일수록 피부 그늘색(피부 × shade[2]) 쪽으로 섞기(w = shade[0] 밝은 ~ shade[1] 짙은)
                L.shade?.let { sd -> val w = sd[1] + (sd[0] - sd[1]) * t
                    Color.rgb(rnd(Color.red(c2) * (1 - w) + Color.red(skin) * sd[2] * w), rnd(Color.green(c2) * (1 - w) + Color.green(skin) * sd[2] * w),
                        rnd(Color.blue(c2) * (1 - w) + Color.blue(skin) * sd[2] * w)) } ?: c2
            }
            TINT_SKIN -> scale(skin, L.k1 + (L.k0 - L.k1) * t)   // 주름·코 그림자: 피부보다 한 단 어둡게
            TINT_PAIR -> Color.rgb(rnd(Color.red(L.c1) + (Color.red(L.c0) - Color.red(L.c1)) * t),
                rnd(Color.green(L.c1) + (Color.green(L.c0) - Color.green(L.c1)) * t), rnd(Color.blue(L.c1) + (Color.blue(L.c0) - Color.blue(L.c1)) * t))
            else -> null
        }
        return col to al
    }

    private fun appContext(): Context? = runCatching {
        Class.forName("android.app.ActivityThread").getMethod("currentApplication").invoke(null) as? Context
    }.getOrNull()

    /** 회색 명암 × 색 / 기준 밝기(face_atlas.py 와 같은 식). ColorMatrix 는 알파를 곱하기 전 색에 적용된다. */
    private fun tintFilter(c: Int, mean: Float): ColorMatrixColorFilter {
        val m = 1f / (255f * mean.coerceAtLeast(0.05f))
        return ColorMatrixColorFilter(ColorMatrix(floatArrayOf(
            Color.red(c) * m, 0f, 0f, 0f, 0f,
            0f, Color.green(c) * m, 0f, 0f, 0f,
            0f, 0f, Color.blue(c) * m, 0f, 0f,
            0f, 0f, 0f, 1f, 0f)))
    }

    /** 얼굴 텍스처 한 장(size×size, Plaza.drawFace 와 같은 칸). 아틀라스가 없으면 null. */
    fun draw(size: Int, a: IntArray, bg: Int?): Bitmap? {
        if (!tried) appContext()?.let(::init)
        val sh = sheet ?: return null
        val bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val g = Canvas(bmp)
        val S = size.toFloat()
        if (bg != null) g.drawColor(bg)
        val paint = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG)
        val skin = Plaza.skin(a)   // 바탕(bg)이 없어도 부품 색은 이 사람 피부에 맞춘다
        val t = ((luma(skin) - sh.tLo) / (sh.tHi - sh.tLo)).coerceIn(0f, 1f)
        val dst = RectF()
        for ((idx, opts) in sh.groups) {
            val layers = opts.getOrNull(a.getOrElse(idx) { 0 }) ?: continue
            for (L in layers) {
                if (L.unlessEyes.isNotEmpty() && a.getOrElse(Plaza.EYES) { 0 } in L.unlessEyes) continue
                var ok = true; var q = 0
                while (q < L.need.size) { if (a.getOrElse(L.need[q]) { 0 } and L.need[q + 1] == 0) { ok = false; break }; q += 2 }
                if (!ok) continue
                val sp = L.byEyes?.getOrNull(a.getOrElse(Plaza.EYES) { 0 })   // 눈가 주름: 그 눈 바깥 끝 옆 칸
                val (col, al) = paintOf(L, a, skin, t)
                paint.alpha = (al * 255).toInt()
                paint.colorFilter = col?.let { tintFilter(it, L.mean) }
                val src = sp?.src ?: L.src
                if (sp != null) dst.set(sp.l * S, sp.t * S, sp.r * S, sp.b * S) else dst.set(L.l * S, L.t * S, L.r * S, L.b * S)
                g.drawBitmap(sh.atlas, src, dst, paint)
                if (L.mirror) {   // 왼쪽만 담긴 부품: u 0.5 기준으로 뒤집어 오른쪽에 한 번 더
                    g.save(); g.scale(-1f, 1f, S / 2f, 0f); g.drawBitmap(sh.atlas, src, dst, paint); g.restore()
                }
            }
        }
        return bmp
    }
}
