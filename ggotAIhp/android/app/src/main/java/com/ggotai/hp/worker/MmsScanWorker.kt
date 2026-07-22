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

        /** 본문 저장을 기다리는 시간. 실측 1.5초에 여유를 뒀다. */
        const val SCAN_DELAY_MILLIS = 5_000L

        /**
         * 예외로 인한 재시도 상한. SecurityException(권한 미허용) 같은 영구 실패는
         * 재시도해도 계속 실패하므로, WorkManager 백오프로 무한히 돌지 않게 끊는다.
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
        return try {
            // 본문이 아직 안 내려온 메시지가 남았으면 WorkManager 백오프에 재시도를 맡긴다.
            // 이게 없으면 그 메시지를 다시 볼 트리거가 "다음 MMS 도착" 또는 "앱 재시작"뿐이라,
            // 조용한 폰에서는 영영 안 잡힌다. 6시간 상한이 무한 재시도를 자연히 끊는다.
            if (MmsScanner.scanOnce(applicationContext)) Result.retry() else Result.success()
        } catch (e: Exception) {
            // scanOnce 는 실패(커서·SQLite 오류 등)를 예외로 알린다. 이를 success 로
            // 삼키면 조용한 폰에서는 다음 MMS 가 올 때까지 재시도가 없어, 그 사이 도착한
            // 주문이 6시간 창이 지나며 그대로 유실된다. 다만 SecurityException 같은 영구
            // 실패는 재시도해도 계속 실패하므로 runAttemptCount 로 상한을 둔다.
            if (runAttemptCount < MAX_EXCEPTION_RETRIES) {
                Log.w(TAG, "MMS 스캔 실패 — 재시도 예약 (시도 ${runAttemptCount + 1}): ${e.message}")
                Result.retry()
            } else {
                Log.e(TAG, "MMS 스캔 반복 실패 — 재시도 포기 (시도 ${runAttemptCount + 1}): ${e.message}")
                Result.failure()
            }
        }
    }
}
