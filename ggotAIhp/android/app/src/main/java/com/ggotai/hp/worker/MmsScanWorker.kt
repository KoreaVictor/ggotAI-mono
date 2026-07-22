package com.ggotai.hp.worker

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.ggotai.hp.mms.MmsScanner
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CancellationException

/**
 * MMS 스캔을 지연 실행한다.
 *
 * MMS 는 도착 방송이 먼저 오고 본문이 뒤에 저장된다(실측 1.5초). 방송 직후에 읽으면
 * 빈 파트를 보게 되므로 조금 기다렸다 읽는다. 방송 안에서 잠들 수는 없어 워커로 뺀다.
 */
class MmsScanWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "MmsScanWorker"
        private const val WORK_NAME = "mms-scan"
        private const val PREFS = "app_prefs"

        /**
         * 연속 예외 횟수를 세는 카운터 키. runAttemptCount 를 그대로 쓰면 안 되는 이유:
         * runAttemptCount 는 이 워크(mms-scan)의 모든 재시도를 센다 — "본문이 아직 안
         * 내려온 메시지가 남았다"는 이유의 Result.retry() (scanOnce 가 예외 없이 정상
         * 반환하는 경우) 까지 함께 세어 버린다. 자동 다운로드가 꺼져 있거나 addr 행이
         * 없는 MMS 하나가 워터마크를 6시간 내내 붙잡고 있는 동안, 이 재시도는 15분
         * 안에도 상한을 넘길 만큼 자주 돈다. 그 상태에서 첫 일시적 SQLite/커서 예외가
         * 나면 runAttemptCount 가 이미 상한을 넘겨 있어 예외 재시도가 0번 — 예외
         * 재시도를 만든 이유(조용한 폰에서 재트리거가 없다) 그대로 재현된다. 그래서
         * "예외가 난 횟수"만 따로 이 SharedPreferences 카운터로 센다.
         */
        private const val KEY_CONSECUTIVE_EXCEPTIONS = "MMS_SCAN_CONSECUTIVE_EXCEPTIONS"

        /** 본문 저장을 기다리는 시간. 실측 1.5초에 여유를 뒀다. */
        const val SCAN_DELAY_MILLIS = 5_000L

        /**
         * 예외로 인한 재시도 상한. SecurityException(권한 미허용) 같은 영구 실패는
         * 재시도해도 계속 실패하므로, 무한히 돌지 않게 끊는다. runAttemptCount 대신
         * [KEY_CONSECUTIVE_EXCEPTIONS] 로 센 "연속 예외" 횟수를 이 값과 비교한다.
         */
        private const val MAX_EXCEPTION_RETRIES = 5

        fun schedule(context: Context, delayMillis: Long = SCAN_DELAY_MILLIS) {
            val request = OneTimeWorkRequestBuilder<MmsScanWorker>()
                .setInitialDelay(delayMillis, TimeUnit.MILLISECONDS)
                .build()
            // 연달아 온 MMS 는 한 번의 스캔이 모두 처리한다(워터마크 기반이라 안전).
            // REPLACE 라 앱 시작 스캔(지연 0)이 리시버가 잡아둔 5초 스캔을 밀어낼 수 있다.
            // 그 경우 본문이 덜 내려온 채로 읽지만, doWork 의 재시도가 이어받는다.
            WorkManager.getInstance(context).enqueueUniqueWork(
                WORK_NAME, ExistingWorkPolicy.REPLACE, request
            )
        }
    }

    override suspend fun doWork(): Result {
        val prefs = applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return try {
            // 본문이 아직 안 내려온 메시지가 남았으면 WorkManager 백오프에 재시도를 맡긴다.
            // 이게 없으면 그 메시지를 다시 볼 트리거가 "다음 MMS 도착" 또는 "앱 재시작"뿐이라,
            // 조용한 폰에서는 영영 안 잡힌다. 6시간 상한이 무한 재시도를 자연히 끊는다.
            val hasIncomplete = MmsScanner.scanOnce(applicationContext)
            // 예외 없이 끝났다 — 연속 예외 카운터를 초기화한다. "본문 미다운로드" 재시도가
            // 아무리 반복돼도 여기서는 매번 리셋되므로 예외 재시도 상한을 갉아먹지 않는다.
            prefs.edit().putInt(KEY_CONSECUTIVE_EXCEPTIONS, 0).apply()
            if (hasIncomplete) Result.retry() else Result.success()
        } catch (e: CancellationException) {
            // SmsReceiver/MainActivity 모두 ExistingWorkPolicy.REPLACE 로 이 워크를 다시
            // 예약한다 — 스캔 도중 취소되는 건 새 MMS/재실행이 뒤이어 온 정상 상황이다.
            // 아래 일반 Exception 처리로 떨어지면 Log.e("MMS 스캔 실패")로 남아 나중에
            // 이 로그를 보는 사람을 오도하고, 연속 예외 카운터까지 불필요하게 올라간다.
            throw e
        } catch (e: Exception) {
            // scanOnce 는 실패(커서·SQLite 오류 등)를 예외로 알린다. 이를 success 로
            // 삼키면 조용한 폰에서는 다음 MMS 가 올 때까지 재시도가 없어, 그 사이 도착한
            // 주문이 6시간 창이 지나며 그대로 유실된다. 다만 SecurityException 같은 영구
            // 실패는 재시도해도 계속 실패하므로 "연속 예외" 횟수로 상한을 둔다.
            val consecutive = prefs.getInt(KEY_CONSECUTIVE_EXCEPTIONS, 0) + 1
            prefs.edit().putInt(KEY_CONSECUTIVE_EXCEPTIONS, consecutive).apply()
            if (consecutive < MAX_EXCEPTION_RETRIES) {
                Log.w(TAG, "MMS 스캔 실패 — 재시도 예약 (연속 $consecutive 회): ${e.message}")
                Result.retry()
            } else {
                Log.e(TAG, "MMS 스캔 반복 실패 — 재시도 포기 (연속 $consecutive 회): ${e.message}")
                Result.failure()
            }
        }
    }
}
