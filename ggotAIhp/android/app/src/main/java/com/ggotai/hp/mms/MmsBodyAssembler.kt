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
     * MIME 타입 문자열에서 파라미터(;charset=... 등)를 떼어낸 순수 타입만 남긴다.
     * 아이폰발 MMS 는 "text/plain; charset=utf-8" 처럼 파라미터를 흔히 붙이는데,
     * 이를 떼지 않으면 상수와 정확히 일치하지 않아 글이 미디어로 오분류되고
     * 주문 본문이 통째로 사라진다.
     */
    private fun bareContentType(contentType: String): String =
        contentType.substringBefore(';').trim()

    /**
     * RFC 2047 인코딩 단어(`=?charset?B/Q?...?=`) 형태 — 인코딩된 제목의 겉모습이다.
     * 이전 라운드에서 디코딩을 일부러 생략하기로 했으니, 이 형태로 온 값은 사람이 읽을
     * 문장이 아니라 쓰레기다. 그대로 두면 사진 자리표시(PHOTO_PLACEHOLDER)를 밀어내고
     * 그 자리를 인코딩된 원문이 차지해 AI 추출 대상 텍스트를 오염시킨다.
     */
    private val ENCODED_WORD_SUBJECT = Regex("^=\\?.+\\?=$")

    /**
     * 본문으로 쓸 수 있는 제목만 남긴다. 공백뿐이거나 RFC 2047 인코딩 단어면 없는 것으로
     * 본다 — 통신사·삼성 단말이 sub 에 파일명, "MMS", 인코딩된 값을 흔히 넣어 보낸다.
     */
    private fun usableSubject(subject: String?): String {
        val trimmed = subject?.trim().orEmpty()
        if (trimmed.isEmpty() || ENCODED_WORD_SUBJECT.matches(trimmed)) return ""
        return trimmed
    }

    /**
     * @param subject MMS 의 sub 컬럼(제목). 삼성 메시지 등 일부 발신자(주로 LMS·피처폰)는
     *   본문을 파트가 아니라 이 제목에 담아 보낸다 — 파트만 보면 글이 하나도 없어 사진뿐인
     *   메시지로 오분류되거나 그대로 버려진다. RFC 2047 인코딩 단어가 아닌 한 별도 디코딩
     *   없이 있는 그대로 쓴다 — 의존성을 늘리느니 원문 그대로 두는 편이 안전하다.
     * @return 버퍼에 담을 본문. 담을 것이 없으면 null.
     *   파트가 아예 없으면(본문 미다운로드) 역시 null 이다 — 호출부가 이 경우를
     *   워터마크 전진 중단으로 따로 다룬다.
     */
    fun assemble(parts: List<MmsPart>, hasActiveConversation: Boolean, subject: String? = null): String? {
        val partsText = parts
            .filter { bareContentType(it.contentType).equals(TEXT_TYPE, ignoreCase = true) }
            .mapNotNull { it.text?.trim()?.takeIf { line -> line.isNotEmpty() } }
            .joinToString("\n")

        val subjectText = usableSubject(subject)

        if (partsText.isNotEmpty()) {
            // 글 파트가 있으면 그것만이 본문이다. 제목은 버린다 — 국내 LMS 는 본문 앞부분을
            // 잘라 제목에 그대로 넣는 경우가 대부분이라, 붙이면 첫 줄이 중복된다.
            // (실측 2026-07-22: 제목="사장님 안녕하세요 내일", 본문 첫 줄이 같은 문장으로 시작)
            // 제목이 쓸모 있는 경우는 글 파트가 아예 없을 때뿐이고, 그건 아래에서 다룬다.
            return partsText
        }

        // 여기부터는 글 파트가 없다. 미디어가 있는데 제목을 본문 대신 그대로 돌려주면,
        // "사진을 보냈습니다."가 나와야 할 자리를 파일명·"MMS"·인코딩된 쓰레기 제목이
        // 차지해 버린다 — 미디어 유무를 글보다 먼저 확인해야 한다.
        val hasMedia = parts.any {
            val bare = bareContentType(it.contentType)
            !bare.equals(TEXT_TYPE, ignoreCase = true) &&
                !bare.equals(LAYOUT_TYPE, ignoreCase = true)
        }
        if (hasMedia) {
            if (!hasActiveConversation) return null
            // 쓸만한 제목이 있으면 자리표시 위에 얹는다 — 자리표시를 대체하지 않는다.
            return if (subjectText.isEmpty()) PHOTO_PLACEHOLDER else "$subjectText\n$PHOTO_PLACEHOLDER"
        }

        // 미디어도 글도 없다 — 제목만으로 본문을 삼는다(LMS·피처폰 대체 경로).
        return subjectText.ifEmpty { null }
    }
}
