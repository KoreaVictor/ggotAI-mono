package com.ggotai.hp.util

/** 통화 고객의 번호/이름을 결정하는 순수 로직. */
object CustomerResolver {
    const val UNKNOWN_NUMBER = "Unknown"
    const val DEFAULT_NAME = "신규"

    /** CallLog 번호가 비어있으면 "Unknown". */
    fun resolveNumber(callLogNumber: String?): String =
        callLogNumber?.takeIf { it.isNotBlank() } ?: UNKNOWN_NUMBER

    /** CallLog 캐시명 → (번호로 조회한) 주소록명 → "신규" 순. */
    fun resolveName(cachedName: String?, contactName: String?): String =
        cachedName?.takeIf { it.isNotBlank() }
            ?: contactName?.takeIf { it.isNotBlank() && it != DEFAULT_NAME }
            ?: DEFAULT_NAME
}
