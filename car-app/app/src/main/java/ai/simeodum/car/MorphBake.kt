package ai.simeodum.car

import com.google.android.filament.Engine
import com.google.android.filament.IndexBuffer
import com.google.android.filament.RenderableManager
import com.google.android.filament.SurfaceOrientation
import com.google.android.filament.VertexBuffer
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sqrt

/**
 * 체형·얼굴형 모프를 Filament 대신 CPU에서 사람마다 한 번 섞어 그 사람 전용 꼭짓점 버퍼로 바꿔 낀다(11/10).
 *
 * 왜: Filament 모프는 위치는 잘 섞지만 법선이 망가진다. 모프 가중치가 0이 아니면 그 덩어리의 법선이 한 방향(앞쪽)으로 쏠려,
 * 체형 '듬직'처럼 머리 모양이 하나도 안 바뀌는 모프만 켜도 머리 명암이 평평해지고(에뮬레이터 실측: 가중치 0 → 둥근 명암·광택,
 * 0이 아닌 어떤 모프든 → 납작한 단색), glb 의 모프 법선을 빼거나(차이 0) 바꿔 넣어도 똑같았다 → 파일이 아니라 Filament 1.57.1 의 모프 법선 처리 문제로 본다.
 * 얼굴 조각(머리 뼈 자식)과 머리 살(몸, 뼈로 움직임)은 서로 다른 가중치 합(얼굴형만 / 체형 + 얼굴형)이라 쏠림이 달라
 * 각진·갸름 얼굴과 듬직·날씬 체형에서 턱 아래가 얼굴 조각과 다른 명암으로 갈라져 보였다('턱이 깨져 보임').
 *
 * (그 전엔 sparse 모프로 저장된 몸·가발·긴 수염이 GPU에서 위치도 덜 움직였을 수 있으나, 여기서는 sparse 도 직접 펼쳐 읽어 웹과 같은 모양이 된다.)
 * 그래서 모프가 있는 덩어리(몸·가발·수염·안경·목도리·얼굴 조각)는 사람을 만들 때 위치·법선을 직접 섞어(법선은 다시 정규화)
 * 새 VertexBuffer 로 바꿔 끼우고 Filament 모프 가중치는 0으로 둔다. 매 장 비용은 그대로(오히려 모프 계산이 빠짐), 사람마다 한 번만.
 * 뼈 번호·가중치·색·UV 는 glb 그대로라 동작·색칠은 예전과 같다.
 */
class MorphBake(buf: ByteBuffer) {
    private val bin: ByteBuffer

    /** glb 접근자·버퍼 조각에서 필요한 칸만(JSON 은 처음에 한 번 읽고 버린다: 사람 자산 JSON 객체만 몇 MB라). */
    private class Acc(val bv: Int, val off: Int, val count: Int, val ct: Int, val n: Int, val norm: Boolean,
                      val spCount: Int, val spIbv: Int, val spIoff: Int, val spIct: Int, val spVbv: Int, val spVoff: Int)
    private class PrimMeta(val pos: Int, val nrm: Int, val uv: Int, val color: Int, val joints: Int, val weights: Int, val indices: Int,
                           val targets: List<Pair<Int, Int>>)   // (위치, 법선 또는 -1)
    private class MeshMeta(val names: List<String>, val prims: List<PrimMeta>)
    private val accs: Array<Acc>
    private val bvOff: IntArray; private val bvStride: IntArray
    /** 노드 이름 → 모프가 있는 메시. 없는 노드는 목록에 없다. */
    private val meshOf = HashMap<String, MeshMeta>()

    init {
        val d = buf.duplicate().order(ByteOrder.LITTLE_ENDIAN)
        val jl = d.getInt(12)
        val bytes = ByteArray(jl); d.position(20); d.get(bytes)
        val json = JSONObject(String(bytes, Charsets.UTF_8))
        val bo = 20 + jl
        val bl = d.getInt(bo)
        d.position(bo + 8); d.limit(bo + 8 + bl)
        bin = d.slice().order(ByteOrder.LITTLE_ENDIAN)
        val bvs = json.getJSONArray("bufferViews")
        bvOff = IntArray(bvs.length()) { bvs.getJSONObject(it).optInt("byteOffset", 0) }
        bvStride = IntArray(bvs.length()) { bvs.getJSONObject(it).optInt("byteStride", 0) }
        val ja = json.getJSONArray("accessors")
        accs = Array(ja.length()) { i ->
            val o = ja.getJSONObject(i)
            val n = when (o.getString("type")) { "SCALAR" -> 1; "VEC2" -> 2; "VEC3" -> 3; "VEC4" -> 4; else -> 16 }
            val sp = o.optJSONObject("sparse"); val si = sp?.getJSONObject("indices"); val sv = sp?.getJSONObject("values")
            Acc(o.optInt("bufferView", -1), o.optInt("byteOffset", 0), o.getInt("count"), o.getInt("componentType"), n, o.optBoolean("normalized"),
                sp?.getInt("count") ?: 0, si?.getInt("bufferView") ?: -1, si?.optInt("byteOffset", 0) ?: 0, si?.getInt("componentType") ?: 0,
                sv?.getInt("bufferView") ?: -1, sv?.optInt("byteOffset", 0) ?: 0)
        }
        val meshes = json.getJSONArray("meshes"); val nodes = json.getJSONArray("nodes")
        for (i in 0 until nodes.length()) {
            val nd = nodes.getJSONObject(i); if (!nd.has("mesh")) continue
            val name = nd.optString("name"); if (name.isEmpty() || meshOf.containsKey(name)) continue
            val mesh = meshes.getJSONObject(nd.getInt("mesh"))
            val tn = mesh.optJSONObject("extras")?.optJSONArray("targetNames") ?: continue
            val ps = mesh.getJSONArray("primitives")
            if (!ps.getJSONObject(0).has("targets")) continue
            meshOf[name] = MeshMeta((0 until tn.length()).map { tn.getString(it) }, (0 until ps.length()).map { k ->
                val p = ps.getJSONObject(k); val at = p.getJSONObject("attributes"); val tg = p.optJSONArray("targets")
                PrimMeta(at.getInt("POSITION"), at.getInt("NORMAL"), at.optInt("TEXCOORD_0", -1), at.optInt("COLOR_0", -1),
                    at.optInt("JOINTS_0", -1), at.optInt("WEIGHTS_0", -1), p.getInt("indices"),
                    if (tg == null) emptyList() else (0 until tg.length()).map { t -> tg.getJSONObject(t).let { o -> o.getInt("POSITION") to o.optInt("NORMAL", -1) } })
            })
        }
    }

    /** 덩어리 하나(primitive): 바탕 데이터 + 모프(이름 → 위치·법선 차이). 쓸 때만 만들고 버린다. */
    private class Prim(
        val pos: FloatArray, val nrm: FloatArray, val uv: FloatArray?, val color: FloatArray?,
        val joints: ShortArray?, val weights: FloatArray?, val indices: IntArray,
        val targets: Map<String, Pair<FloatArray, FloatArray?>>,
    ) { val count get() = pos.size / 3 }

    /** 덩어리마다 인덱스 버퍼는 사람끼리 같이 쓴다. */
    private val ibs = HashMap<String, IndexBuffer>()

    fun hasMorphs(node: String): Boolean = meshOf.containsKey(node)

    private fun prims(node: String): List<Prim>? {
        val m = meshOf[node] ?: return null
        return m.prims.map { p ->
            val t = HashMap<String, Pair<FloatArray, FloatArray?>>()
            for ((i, tg) in p.targets.withIndex()) if (i < m.names.size) t[m.names[i]] = floats(tg.first) to (if (tg.second >= 0) floats(tg.second) else null)
            Prim(floats(p.pos), floats(p.nrm), if (p.uv >= 0) floats(p.uv) else null, if (p.color >= 0) floats(p.color) else null,
                if (p.joints >= 0) floats(p.joints).let { f -> ShortArray(f.size) { f[it].toInt().toShort() } } else null,
                if (p.weights >= 0) floats(p.weights) else null,
                floats(p.indices).let { f -> IntArray(f.size) { f[it].toInt() } }, t)
        }
    }

    /** 접근자 → float 배열(정규화 정수·sparse 포함, 성분 순서 그대로). */
    private fun floats(ai: Int): FloatArray {
        val a = accs[ai]; val n = a.n
        val out = FloatArray(a.count * n)
        if (a.bv >= 0) read(a.bv, a.off, a.count, a.ct, n, a.norm, out)
        if (a.spCount > 0) {
            val idx = FloatArray(a.spCount); read(a.spIbv, a.spIoff, a.spCount, a.spIct, 1, false, idx)
            val v = FloatArray(a.spCount * n); read(a.spVbv, a.spVoff, a.spCount, a.ct, n, a.norm, v)
            for (i in 0 until a.spCount) { val r = idx[i].toInt() * n; for (j in 0 until n) out[r + j] = v[i * n + j] }
        }
        return out
    }

    /** 버퍼 조각 bv 에서 c개 × k성분을 dst 에(박싱 없이). */
    private fun read(bv: Int, off: Int, c: Int, type: Int, k: Int, norm: Boolean, dst: FloatArray) {
        val size = when (type) { 5126, 5125 -> 4; 5123, 5122 -> 2; else -> 1 }
        val stride = bvStride[bv].takeIf { it > 0 } ?: (size * k)
        val base = bvOff[bv] + off
        for (i in 0 until c) for (j in 0 until k) {
            val o = base + i * stride + j * size
            dst[i * k + j] = when (type) {
                5126 -> bin.getFloat(o)
                5125 -> (bin.getInt(o).toLong() and 0xffffffffL).toFloat()
                5123 -> (bin.getShort(o).toInt() and 0xffff).let { if (norm) it / 65535f else it.toFloat() }
                5122 -> bin.getShort(o).toInt().let { if (norm) maxOf(it / 32767f, -1f) else it.toFloat() }
                5121 -> (bin.get(o).toInt() and 0xff).let { if (norm) it / 255f else it.toFloat() }
                else -> bin.get(o).toInt().let { if (norm) maxOf(it / 127f, -1f) else it.toFloat() }
            }
        }
    }

    private fun direct(n: Int) = ByteBuffer.allocateDirect(n).order(ByteOrder.nativeOrder())

    /**
     * 렌더러블 ri(노드 node)의 덩어리마다 모프를 w(이름 → 가중치)로 섞은 새 꼭짓점 버퍼를 끼운다. 만든 버퍼를 돌려준다(사람을 지울 때 엔진에서 지움).
     * 모프가 없는 노드면 빈 목록. Filament 모프 가중치는 0으로 둔다.
     */
    fun apply(engine: Engine, rm: RenderableManager, ri: Int, node: String, w: Map<String, Float>): List<VertexBuffer> {
        val ps = prims(node) ?: return emptyList()
        val made = ArrayList<VertexBuffer>()
        val primCount = rm.getPrimitiveCount(ri)
        for ((k, p) in ps.withIndex()) {
            if (k >= primCount) break
            val n = p.count
            val pos = p.pos.copyOf(); val nrm = p.nrm.copyOf()
            for ((name, d) in p.targets) {
                val wt = w[name] ?: 0f
                if (wt == 0f) continue
                val dp = d.first; for (i in pos.indices) pos[i] += wt * dp[i]
                d.second?.let { dn -> for (i in nrm.indices) nrm[i] += wt * dn[i] }
            }
            for (i in 0 until n) {
                val x = nrm[i * 3]; val y = nrm[i * 3 + 1]; val z = nrm[i * 3 + 2]
                val l = sqrt(x * x + y * y + z * z).takeIf { it > 1e-8f } ?: 1f
                nrm[i * 3] = x / l; nrm[i * 3 + 1] = y / l; nrm[i * 3 + 2] = z / l
            }
            // 법선 → 접선 틀 사원수(gltfio 와 같은 short4 정규화)
            val nb = direct(n * 12).also { b -> b.asFloatBuffer().put(nrm) }
            val so = SurfaceOrientation.Builder().vertexCount(n).normals(nb).build()
            val quats = direct(n * 8); so.getQuatsAsShort(quats); so.destroy()
            var slot = 0
            val b = VertexBuffer.Builder().vertexCount(n)
            val bufs = ArrayList<ByteBuffer>()
            fun add(attr: VertexBuffer.VertexAttribute, type: VertexBuffer.AttributeType, stride: Int, data: ByteBuffer, normalized: Boolean = false) {
                b.attribute(attr, slot, type, 0, stride); if (normalized) b.normalized(attr)
                bufs.add(data); slot++
            }
            add(VertexBuffer.VertexAttribute.POSITION, VertexBuffer.AttributeType.FLOAT3, 12, direct(n * 12).also { it.asFloatBuffer().put(pos) })
            add(VertexBuffer.VertexAttribute.TANGENTS, VertexBuffer.AttributeType.SHORT4, 8, quats, normalized = true)
            p.uv?.let { uv -> add(VertexBuffer.VertexAttribute.UV0, VertexBuffer.AttributeType.FLOAT2, 8, direct(n * 8).also { it.asFloatBuffer().put(uv) }) }
            // 꼭짓점 색(명암): gltfio 재질은 색 칸을 늘 곱하므로, 파일에 없으면 흰색을 채운다(빠지면 0으로 읽혀 검게 나옴). 바이트 4개로(메모리 1/4)
            val cb = direct(n * 4)
            val comps = p.color?.let { it.size / n } ?: 0
            for (i in 0 until n) for (c in 0..3) {
                val v = if (c < comps) p.color!![i * comps + c] else 1f
                cb.put((v.coerceIn(0f, 1f) * 255f + 0.5f).toInt().toByte())
            }
            add(VertexBuffer.VertexAttribute.COLOR, VertexBuffer.AttributeType.UBYTE4, 4, cb, normalized = true)
            p.joints?.let { j -> add(VertexBuffer.VertexAttribute.BONE_INDICES, VertexBuffer.AttributeType.USHORT4, 8, direct(n * 8).also { it.asShortBuffer().put(j) }) }
            p.weights?.let { wv -> add(VertexBuffer.VertexAttribute.BONE_WEIGHTS, VertexBuffer.AttributeType.FLOAT4, 16, direct(n * 16).also { it.asFloatBuffer().put(wv) }) }
            val vb = b.bufferCount(slot).build(engine)
            for ((i, data) in bufs.withIndex()) { data.rewind(); vb.setBufferAt(engine, i, data) }
            val ib = ibs.getOrPut("$node#$k") {
                val big = n > 65535
                val ib = IndexBuffer.Builder().indexCount(p.indices.size)
                    .bufferType(if (big) IndexBuffer.Builder.IndexType.UINT else IndexBuffer.Builder.IndexType.USHORT).build(engine)
                val data = if (big) direct(p.indices.size * 4).also { it.asIntBuffer().put(p.indices) }
                else direct(p.indices.size * 2).also { bb -> val sb = bb.asShortBuffer(); for (x in p.indices) sb.put(x.toShort()) }
                ib.setBuffer(engine, data); ib
            }
            rm.setGeometryAt(ri, k, RenderableManager.PrimitiveType.TRIANGLES, vb, ib, 0, p.indices.size)
            made.add(vb)
        }
        val mc = rm.getMorphTargetCount(ri)
        if (mc > 0) rm.setMorphWeights(ri, FloatArray(mc), 0)
        return made
    }

    fun destroy(engine: Engine) { ibs.values.forEach { engine.destroyIndexBuffer(it) }; ibs.clear() }
}
