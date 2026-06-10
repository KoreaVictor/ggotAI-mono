package com.ggotai.hp.util

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CallLog
import android.util.Log
import androidx.core.content.ContextCompat
import com.ggotai.hp.model.CallLogEntry

/** 통화 종료 직후 가장 최근 통화기록을 조회한다. */
object CallLogReader {
    private const val TAG = "CallLogReader"
    private const val MAX_AGE_MS = 10 * 60 * 1000L // 최근 10분 이내만 유효

    /**
     * 최근 통화 1건을 반환한다.
     * 권한 없음 / 기록 없음 / 10분 초과(오래된 통화) → null.
     */
    fun latestCall(context: Context): CallLogEntry? {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALL_LOG)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "READ_CALL_LOG 미승인 — CallLog 조회 생략")
            return null
        }

        val projection = arrayOf(
            CallLog.Calls.NUMBER,
            CallLog.Calls.CACHED_NAME,
            CallLog.Calls.TYPE,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION
        )

        return try {
            context.contentResolver.query(
                CallLog.Calls.CONTENT_URI,
                projection,
                null,
                null,
                "${CallLog.Calls.DATE} DESC"
            )?.use { cursor ->
                if (!cursor.moveToFirst()) return null
                val number = cursor.getString(cursor.getColumnIndexOrThrow(CallLog.Calls.NUMBER))
                val cachedName = cursor.getString(cursor.getColumnIndexOrThrow(CallLog.Calls.CACHED_NAME))
                val type = cursor.getInt(cursor.getColumnIndexOrThrow(CallLog.Calls.TYPE))
                val dateMillis = cursor.getLong(cursor.getColumnIndexOrThrow(CallLog.Calls.DATE))
                val durationSec = cursor.getInt(cursor.getColumnIndexOrThrow(CallLog.Calls.DURATION))

                if (System.currentTimeMillis() - dateMillis > MAX_AGE_MS) {
                    Log.w(TAG, "최근 통화가 10분 초과 — 매칭 생략")
                    null
                } else {
                    Log.d(TAG, "CallLog 최근통화: number=$number name=$cachedName type=$type dur=$durationSec")
                    CallLogEntry(number, cachedName, type, dateMillis, durationSec)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "CallLog 조회 실패", e)
            null
        }
    }
}
