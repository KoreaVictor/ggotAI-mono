package com.ggotai.hp.model

/** CallLog.Calls 한 행의 필요한 필드. */
data class CallLogEntry(
    val number: String?,
    val cachedName: String?,
    val type: Int,
    val dateMillis: Long,
    val durationSec: Int
)
