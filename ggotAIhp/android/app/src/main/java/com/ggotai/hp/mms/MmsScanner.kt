package com.ggotai.hp.mms

import android.content.ContentUris
import android.content.Context
import android.content.SharedPreferences
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
import kotlinx.coroutines.CancellationException

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
    private const val KEY_HANDLED_IDS = "MMS_HANDLED_IDS"

    /**
     * 처리 완료 id를 기억해 둘 개수 상한. MMS _ID는 단조증가이므로 가장 큰 N개만
     * 남겨도 충분하다 — 사장님 폰이 6시간 창 안에 MMS 200통을 받을 일은 없다.
     */
    private const val MAX_HANDLED_IDS = 200

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

        // 본문 미다운로드로 워터마크가 보류되면, 그 뒤 메시지들은 (본문이 이미 내려왔어도)
        // 워터마크가 다시 전진할 때까지 매 스캔 재조회된다. countDuplicate 는 버퍼에 아직
        // 남아 있는 동안만 재삽입을 막아 주는데, MessageFlushWorker 가 업로드 뒤 몇 분 안에
        // 그 행을 지워 버리면 다음 재조회 때 이미 업로드된 주문이 그대로 다시 삽입돼
        // "동일 주문 이중 삽화(중복 배송)"로 이어진다. 그래서 한 번 처리(적재 또는 확정
        // 폐기)한 id는 워터마크와 별개로 따로 기억해 재조회되더라도 다시 처리하지 않는다.
        val handledIds = loadHandledIds(prefs)
        val newlyHandled = mutableSetOf<Long>()
        // 이번 조회 구간에 실제로 잡힌 id들. handled 목록을 가지치기할 때, 이 구간 밖으로
        // 나간 이전 id는 다시 조회될 수 없으니 굳이 남겨 두지 않는다(MmsHandledIds 참고).
        // null 은 "조회 자체가 실패해 이번 스캔이 창을 전혀 보지 못했다"는 뜻이다 — 이
        // 경우 무엇이 빠졌는지 알 수 없으니, 뒤에서 이전 handledIds 전체를 그대로
        // 보존하는 쪽(가지치기 생략)으로 대체해 안전하게 간다.
        var seenNow: Set<Long>? = null

        try {
            val queriedRows = queryInbox(context, startAt, now)
            seenNow = queriedRows.map { it.id }.toSet()
            for (message in queriedRows) {
                if (message.id in handledIds) continue

                val parts = queryParts(context, message.id)
                if (parts.isEmpty()) {
                    // 본문이 아직 안 내려왔다. 넘어가면 이 주문을 영영 못 본다.
                    // handled 표시하지 않는다 — 본문이 내려온 뒤 다시 봐야 한다.
                    earliestIncompleteAt = minOf(
                        earliestIncompleteAt ?: message.receivedAt, message.receivedAt
                    )
                    Log.d(TAG, "본문 미다운로드 — 워터마크 보류 id=${message.id}")
                    continue
                }

                val sender = PhoneNumberNormalizer.normalize(queryFrom(context, message.id))
                if (sender.isEmpty()) {
                    // addr 행이 part 행보다 한 박자 늦게 들어오는 경우가 실기기에서 확인됐다.
                    // 예전에는 여기서 그냥 넘어가 워터마크가 이 메시지를 지나쳐 버렸다 —
                    // 로그도 없이 통째로 유실되는, 이 기능이 없애려던 바로 그 실패다. 본문
                    // 미다운로드와 같은 취급으로 워터마크를 보류해 다음 스캔이 재시도하게 한다.
                    Log.w(TAG, "발신자 확인 불가 — 워터마크 보류 id=${message.id}")
                    earliestIncompleteAt = minOf(
                        earliestIncompleteAt ?: message.receivedAt, message.receivedAt
                    )
                    continue
                }

                // 밀린 메시지를 몰아서 처리할 때(휴대폰이 꺼져 있었거나 앱이 한참 뒤에
                // 재시작된 경우, 최대 6시간 전까지) now 는 이 메시지가 실제 도착한 시각보다
                // 훨씬 뒤다. now 기준으로 스티키를 판정하면 실제로는 직전 주문 문자의
                // 10분 스티키 창 안에 도착한 메시지도 "진행 중 아님"으로 잘못 판정되어,
                // 키워드 없는 후속 문자(가격·주소·받는분)와 사진 전용 후속 메시지(키워드
                // 대체 규칙이 없어 무조건 폐기됨)가 유실된다. 메시지 자신의 도착 시각을 써야 한다.
                val active = dao.countRecentBySender(
                    SmsReceiver.CHANNEL_SMS, sender, MessageGroupDecider.stickySince(message.receivedAt)
                ) > 0

                val body = MmsBodyAssembler.assemble(parts, active, message.subject)
                if (body == null) {
                    // 파트는 다 내려왔는데 담을 내용이 없다(주문과 무관한 사진뿐 등) —
                    // 확정 폐기이므로 handled 로 표시해 재조회 때 다시 안 본다.
                    newlyHandled.add(message.id)
                    continue
                }
                if (!OrderTextFilter.shouldCollect(sender, body, active)) {
                    Log.d(TAG, "주문 후보 아님 — 폐기 (서버 전송 안 함)")
                    newlyHandled.add(message.id)
                    continue
                }
                if (dao.countDuplicate(
                        SmsReceiver.CHANNEL_SMS, sender, body, message.receivedAt
                    ) > 0
                ) {
                    Log.d(TAG, "중복 MMS — 스킵")
                    newlyHandled.add(message.id)
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
                newlyHandled.add(message.id)
                collected++
                Log.d(TAG, "버퍼 적재(MMS) sender=$sender bodyLen=${body.length} active=$active")
            }
        } catch (e: CancellationException) {
            // SmsReceiver/MainActivity 모두 ExistingWorkPolicy.REPLACE 로 스캔을 예약한다 —
            // 스캔 도중 취소되는 건 새 MMS/재실행이 뒤이어 온 정상 상황이다. 아래 일반
            // Exception 처리로 떨어지면 진짜 오류(권한·커서 등)처럼 Log.e 로 남아 나중에
            // 이 로그를 보는 사람을 오도한다 — 그대로 다시 던져 정상 취소로 흘러가게 한다.
            throw e
        } catch (e: Exception) {
            // 권한 미허용도 여기로 온다. 조용히 실패하면 통째로 놓치는 걸 알 방법이 없다.
            Log.e(TAG, "MMS 스캔 실패: ${e.message}")
            // 예외가 나기 전까지 이미 버퍼에 넣거나 확정 폐기한 메시지가 있을 수 있다
            // (일부 단말은 content://mms 의 특정 행에서만 예외를 던진다). 그 처리 결과는
            // handled 로 남겨 둬야, 워터마크가 이 구간을 다시 읽을 때(아래에서 워터마크는
            // 그대로 두므로 다음 스캔이 이 구간을 다시 읽는다) 이미 업로드된 메시지가
            // 재조회 시점에 버퍼에서 이미 지워져 있어도 다시 삽입되지 않는다.
            saveHandledIds(
                prefs,
                MmsHandledIds.pruneHandledIds(handledIds, seenNow ?: handledIds, newlyHandled, MAX_HANDLED_IDS)
            )
            // 이미 적재된 메시지는 flush 를 예약해 두지 않으면 다음 스캔에서 중복으로
            // 걸러져 collected 가 0이 되고 영영 업로드되지 않는다.
            if (collected > 0) MessageFlushWorker.schedule(context)
            // 예외였음을 호출부(MmsScanWorker)가 구분해 재시도하게 한다 — false 를 돌려주면
            // 정상 종료와 구분이 안 돼, 일시적 오류(커서·SQLite 등)에도 재시도 없이 그대로
            // 6시간 창이 지나가 버린다.
            throw e
        }

        // 여기 도달했다는 것 자체가 try 블록이 예외 없이 끝났다는 뜻이라 seenNow 는
        // 항상 채워져 있다(두 catch 모두 rethrow 로 끝나 예외 시엔 아래로 내려오지 않는다).
        saveHandledIds(
            prefs,
            MmsHandledIds.pruneHandledIds(handledIds, seenNow, newlyHandled, MAX_HANDLED_IDS)
        )
        prefs.edit()
            .putLong(KEY_WATERMARK, MmsScanWindow.nextWatermark(now, earliestIncompleteAt))
            .apply()

        if (collected > 0) MessageFlushWorker.schedule(context)
        return earliestIncompleteAt != null
    }

    /** 처리 완료로 기억해 둔 MMS id 집합을 불러온다. */
    private fun loadHandledIds(prefs: SharedPreferences): Set<Long> =
        prefs.getStringSet(KEY_HANDLED_IDS, emptySet())
            ?.mapNotNull { it.toLongOrNull() }
            ?.toSet() ?: emptySet()

    /** 처리 완료 id 집합을 저장한다. 무엇을 남길지는 [MmsHandledIds.pruneHandledIds] 가 정한다. */
    private fun saveHandledIds(prefs: SharedPreferences, ids: Set<Long>) {
        prefs.edit()
            .putStringSet(KEY_HANDLED_IDS, ids.map { it.toString() }.toSet())
            .apply()
    }

    private data class MmsRow(val id: Long, val receivedAt: Long, val subject: String?)

    /** 받은 메시지함에서 조회 구간에 들어오는 MMS. date 는 초 단위다. */
    private fun queryInbox(context: Context, startAt: Long, endAt: Long): List<MmsRow> {
        val rows = mutableListOf<MmsRow>()
        context.contentResolver.query(
            Telephony.Mms.Inbox.CONTENT_URI,
            arrayOf(
                Telephony.Mms._ID, Telephony.Mms.DATE,
                Telephony.Mms.SUBJECT, Telephony.Mms.SUBJECT_CHARSET
            ),
            "${Telephony.Mms.DATE} >= ? AND ${Telephony.Mms.DATE} <= ?",
            arrayOf((startAt / 1000).toString(), (endAt / 1000).toString()),
            "${Telephony.Mms.DATE} ASC"
        )?.use { cursor ->
            val idIndex = cursor.getColumnIndexOrThrow(Telephony.Mms._ID)
            val dateIndex = cursor.getColumnIndexOrThrow(Telephony.Mms.DATE)
            val subjectIndex = cursor.getColumnIndexOrThrow(Telephony.Mms.SUBJECT)
            val charsetIndex = cursor.getColumnIndexOrThrow(Telephony.Mms.SUBJECT_CHARSET)
            while (cursor.moveToNext()) {
                rows.add(
                    MmsRow(
                        cursor.getLong(idIndex),
                        cursor.getLong(dateIndex) * 1000,
                        // 프로바이더가 UTF-8 제목을 Latin-1 로 읽어 주는 기기가 있다(실측).
                        MmsSubjectDecoder.decode(
                            cursor.getString(subjectIndex), cursor.getInt(charsetIndex)
                        )
                    )
                )
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
