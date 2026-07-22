package com.ggotai.hp.mms

/** MMS 파트 하나. ContentResolver 를 정책에 들이지 않기 위한 값 객체. */
data class MmsPart(val contentType: String, val text: String?)

/**
 * MMS 파트들에서 버퍼에 담을 본문을 만든다.
 *
 * 사진은 읽을 수 없다(한계). 다만 주문 대화 중이라면 "사진이 하나 왔었다"는 사실
 * 자체가 사장님에게 단서가 되므로 한 줄을 남긴다 — 손님이 "이런 걸로 해주세요" 하고
 * 사진을 붙이는 경우가 있다. 주문과 무관한 사람의 사진은 남기지 않는다.
 */
object MmsBodyAssembler {

    const val PHOTO_PLACEHOLDER = "사진을 보냈습니다."

    private const val TEXT_TYPE = "text/plain"
    /** 모든 MMS 에 붙는 배치 정보. 내용이 아니므로 사진으로 치지 않는다. */
    private const val LAYOUT_TYPE = "application/smil"

    /**
     * @return 버퍼에 담을 본문. 담을 것이 없으면 null.
     *   파트가 아예 없으면(본문 미다운로드) 역시 null 이다 — 호출부가 이 경우를
     *   워터마크 전진 중단으로 따로 다룬다.
     */
    fun assemble(parts: List<MmsPart>, hasActiveConversation: Boolean): String? {
        val text = parts
            .filter { it.contentType.equals(TEXT_TYPE, ignoreCase = true) }
            .mapNotNull { it.text?.trim()?.takeIf { line -> line.isNotEmpty() } }
            .joinToString("\n")
        if (text.isNotEmpty()) return text

        val hasMedia = parts.any {
            !it.contentType.equals(TEXT_TYPE, ignoreCase = true) &&
                !it.contentType.equals(LAYOUT_TYPE, ignoreCase = true)
        }
        return if (hasMedia && hasActiveConversation) PHOTO_PLACEHOLDER else null
    }
}
