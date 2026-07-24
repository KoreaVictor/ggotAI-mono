package com.ggotai.hp.mms

/**
 * MMS 제목(sub)의 깨진 인코딩을 되살린다.
 *
 * 실측(SM-N971N, 2026-07-22): `sub_cs=106`(UTF-8)인데 프로바이더가 UTF-8 바이트를 Latin-1 로
 * 읽어 돌려줬다 — "사장님 안녕하세요 내일"이 "ì¬ì¥ë ìëíì¸ì ë´ì¼"로 나왔다.
 * 이 문자열이 그대로 주문 원문에 실려 서버로 올라갔다.
 *
 * 되돌리는 방법은 간단하다: 글자들을 Latin-1 바이트로 되돌린 뒤 UTF-8 로 다시 읽는다.
 * 다만 제대로 디코딩해 주는 기기에서 이걸 하면 멀쩡한 한글이 망가지므로, **깨진 모양일
 * 때만** 손댄다.
 */
object MmsSubjectDecoder {

    /** IANA MIBenum. 106 = UTF-8. */
    const val CHARSET_UTF8 = 106

    /**
     * 깨진 UTF-8 의 겉모습: 모든 글자가 Latin-1 범위(≤0xFF) 안에 있으면서 그중 상위
     * 영역(0x80~0xFF)을 쓰고 있다.
     *
     * 한글이 제대로 디코딩됐다면 코드포인트가 0xFF 를 넘으므로 여기 걸리지 않는다 —
     * 멀쩡한 제목을 건드리지 않기 위한 조건이다.
     */
    private fun looksMisdecoded(text: String): Boolean =
        text.any { it.code in 0x80..0xFF } && text.all { it.code <= 0xFF }

    /**
     * @param raw 프로바이더가 준 제목 그대로.
     * @param charset `sub_cs` 컬럼 값. UTF-8(106)이 아니면 손대지 않는다.
     */
    fun decode(raw: String?, charset: Int): String? {
        if (raw.isNullOrEmpty()) return raw
        if (charset != CHARSET_UTF8) return raw
        if (!looksMisdecoded(raw)) return raw

        return try {
            val restored = String(raw.toByteArray(Charsets.ISO_8859_1), Charsets.UTF_8)
            // 되돌리기에 실패하면 대체문자(U+FFFD)가 섞인다 — 그럴 바엔 원본을 둔다.
            if (restored.contains('�')) raw else restored
        } catch (e: Exception) {
            raw
        }
    }
}
