package com.ggotai.hp.mms

import android.content.ContentUris
import android.content.Context
import android.net.Uri
import android.provider.Telephony
import android.util.Log
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.MessageBuffer
import com.ggotai.hp.manager.DeviceStatus
import com.ggotai.hp.policy.MessageGroupDecider
import com.ggotai.hp.policy.OrderTextFilter
import com.ggotai.hp.receiver.SmsReceiver
import com.ggotai.hp.util.ContactLookup
import com.ggotai.hp.util.CustomerResolver
import com.ggotai.hp.util.PhoneNumberNormalizer
import com.ggotai.hp.worker.MessageFlushWorker

/**
 * 긴 문자(LMS) 수집.
 *
 * 70자를 넘는 문자는 SMS 가 아니라 MMS 로 도착해 SmsReceiver 에 아예 들어오지 않는다
 * (2026-07-22 실기기 확인 — 로그조차 남지 않아 조용히 유실됐다). 시스템이 저장해 둔
 * MMS 를 읽어 기존 문자와 같은 버퍼에 담는다.
 *
 * 버퍼에 담긴 뒤부터는 새 코드가 없다 — 디바운스·묶음·업로드는 문자·카톡과 같다.
 */
object MmsScanner {

    private const val TAG = "MmsScanner"
    private const val PREFS = "app_prefs"
    private const val KEY_WATERMARK = "MMS_WATERMARK"

    /** MMS 주소 테이블에서 발신자를 뜻하는 값. */
    private const val ADDR_TYPE_FROM = 137

    /**
     * @return 본문이 아직 안 내려온 메시지가 남았으면 true. 호출부가 재시도를 정한다 —
     *   여기서 워커를 부르면 스캐너와 스케줄링이 서로를 부르는 고리가 된다.
     */
    suspend fun scanOnce(context: Context): Boolean {
        if (DeviceStatus.isRevoked(context)) {
            Log.d(TAG, "기기 승인취소 — MMS 스캔 중단")
            return false
        }

        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val stored = prefs.getLong(KEY_WATERMARK, -1L)
        val watermark = if (stored < 0) null else stored
        val now = System.currentTimeMillis()
        val startAt = MmsScanWindow.startAt(watermark, now)

        if (watermark == null) {
            // 첫 설치 — 과거는 건드리지 않고 기준점만 세운다.
            prefs.edit().putLong(KEY_WATERMARK, now).apply()
            Log.d(TAG, "첫 스캔 — 기준점만 세우고 과거는 건너뜀")
            return false
        }

        val dao = AppDatabase.getDatabase(context).messageBufferDao()
        var earliestIncompleteAt: Long? = null
        var collected = 0

        try {
            for (message in queryInbox(context, startAt, now)) {
                val parts = queryParts(context, message.id)
                if (parts.isEmpty()) {
                    // 본문이 아직 안 내려왔다. 넘어가면 이 주문을 영영 못 본다.
                    earliestIncompleteAt = minOf(
                        earliestIncompleteAt ?: message.receivedAt, message.receivedAt
                    )
                    Log.d(TAG, "본문 미다운로드 — 워터마크 보류 id=${message.id}")
                    continue
                }

                val sender = PhoneNumberNormalizer.normalize(queryFrom(context, message.id))
                if (sender.isEmpty()) continue

                val active = dao.countRecentBySender(
                    SmsReceiver.CHANNEL_SMS, sender, MessageGroupDecider.stickySince(now)
                ) > 0

                val body = MmsBodyAssembler.assemble(parts, active) ?: continue
                if (!OrderTextFilter.shouldCollect(sender, body, active)) {
                    Log.d(TAG, "주문 후보 아님 — 폐기 (서버 전송 안 함)")
                    continue
                }
                if (dao.countDuplicate(
                        SmsReceiver.CHANNEL_SMS, sender, body, message.receivedAt
                    ) > 0
                ) {
                    Log.d(TAG, "중복 MMS — 스킵")
                    continue
                }

                dao.insert(
                    MessageBuffer(
                        channelOrder = SmsReceiver.CHANNEL_SMS,
                        senderKey = sender,
                        senderName = CustomerResolver.resolveName(
                            null, ContactLookup.nameFor(context, sender)
                        ),
                        phoneNumber = sender,
                        body = body,
                        receivedAt = message.receivedAt
                    )
                )
                collected++
                Log.d(TAG, "버퍼 적재(MMS) sender=$sender bodyLen=${body.length} active=$active")
            }
        } catch (e: Exception) {
            // 권한 미허용도 여기로 온다. 조용히 실패하면 통째로 놓치는 걸 알 방법이 없다.
            Log.e(TAG, "MMS 스캔 실패: ${e.message}")
            return false
        }

        prefs.edit()
            .putLong(KEY_WATERMARK, MmsScanWindow.nextWatermark(now, earliestIncompleteAt))
            .apply()

        if (collected > 0) MessageFlushWorker.schedule(context)
        return earliestIncompleteAt != null
    }

    private data class MmsRow(val id: Long, val receivedAt: Long)

    /** 받은 메시지함에서 조회 구간에 들어오는 MMS. date 는 초 단위다. */
    private fun queryInbox(context: Context, startAt: Long, endAt: Long): List<MmsRow> {
        val rows = mutableListOf<MmsRow>()
        context.contentResolver.query(
            Telephony.Mms.Inbox.CONTENT_URI,
            arrayOf(Telephony.Mms._ID, Telephony.Mms.DATE),
            "${Telephony.Mms.DATE} >= ? AND ${Telephony.Mms.DATE} <= ?",
            arrayOf((startAt / 1000).toString(), (endAt / 1000).toString()),
            "${Telephony.Mms.DATE} ASC"
        )?.use { cursor ->
            val idIndex = cursor.getColumnIndexOrThrow(Telephony.Mms._ID)
            val dateIndex = cursor.getColumnIndexOrThrow(Telephony.Mms.DATE)
            while (cursor.moveToNext()) {
                rows.add(MmsRow(cursor.getLong(idIndex), cursor.getLong(dateIndex) * 1000))
            }
        }
        return rows
    }

    private fun queryParts(context: Context, mmsId: Long): List<MmsPart> {
        val parts = mutableListOf<MmsPart>()
        context.contentResolver.query(
            Uri.parse("content://mms/part"),
            arrayOf("ct", "text"),
            "mid = ?",
            arrayOf(mmsId.toString()),
            null
        )?.use { cursor ->
            val typeIndex = cursor.getColumnIndexOrThrow("ct")
            val textIndex = cursor.getColumnIndexOrThrow("text")
            while (cursor.moveToNext()) {
                parts.add(
                    MmsPart(
                        contentType = cursor.getString(typeIndex).orEmpty(),
                        text = cursor.getString(textIndex)
                    )
                )
            }
        }
        return parts
    }

    private fun queryFrom(context: Context, mmsId: Long): String? {
        val uri = ContentUris.withAppendedId(Telephony.Mms.CONTENT_URI, mmsId)
            .buildUpon().appendPath("addr").build()
        context.contentResolver.query(
            uri,
            arrayOf(Telephony.Mms.Addr.ADDRESS),
            "${Telephony.Mms.Addr.TYPE} = ?",
            arrayOf(ADDR_TYPE_FROM.toString()),
            null
        )?.use { cursor ->
            if (cursor.moveToFirst()) {
                return cursor.getString(cursor.getColumnIndexOrThrow(Telephony.Mms.Addr.ADDRESS))
            }
        }
        return null
    }
}
