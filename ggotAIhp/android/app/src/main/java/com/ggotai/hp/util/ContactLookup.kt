package com.ggotai.hp.util

import android.content.Context
import android.net.Uri
import android.provider.ContactsContract
import android.util.Log

/**
 * 전화번호로 주소록 이름을 찾는다.
 *
 * 통화와 문자가 고객명을 같은 규칙으로 붙이도록 여기 모았다 — 문자는 발신번호만 오므로
 * 주소록을 안 보면 고객명 자리에 번호가 그대로 들어간다.
 *
 * 이름 선택(주소록에 없을 때 무엇으로 채울지)은 [CustomerResolver.resolveName] 이 정한다.
 * 여기서는 "찾았나 못 찾았나"만 답한다.
 */
object ContactLookup {

    private const val TAG = "ContactLookup"

    /** 주소록에 등록된 이름. 없거나 조회할 수 없으면 null. */
    fun nameFor(context: Context, phoneNumber: String?): String? {
        if (phoneNumber.isNullOrBlank()) return null

        val uri = Uri.withAppendedPath(
            ContactsContract.PhoneLookup.CONTENT_FILTER_URI,
            Uri.encode(phoneNumber)
        )
        return try {
            context.contentResolver.query(
                uri,
                arrayOf(ContactsContract.PhoneLookup.DISPLAY_NAME),
                null, null, null
            )?.use { cursor ->
                if (!cursor.moveToFirst()) return@use null
                val index = cursor.getColumnIndex(ContactsContract.PhoneLookup.DISPLAY_NAME)
                if (index < 0) null else cursor.getString(index)?.takeIf { it.isNotBlank() }
            }
        } catch (e: Exception) {
            // 권한 미허용도 여기로 온다 — 조용히 실패하면 원인을 못 찾는다.
            Log.e(TAG, "주소록 조회 실패(권한 없음 또는 오류): ${e.message}")
            null
        }
    }
}
