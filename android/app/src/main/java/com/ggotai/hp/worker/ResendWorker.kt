package com.ggotai.hp.worker

import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.manager.UploadManager
import com.ggotai.hp.policy.ResendPolicy
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File

/**
 * 15분 주기로 실행되어 업로드 실패 건(sync_status=0, transfer_status='실패')을
 * 1건당 1회씩 재업로드한다. 상한(ResendPolicy.MAX_RETRY) 도달 시 영구실패(sync_status=2).
 */
class ResendWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "ResendWorker"
        const val UNIQUE_NAME = "auto-resend"

        // 주기 워커와 재연결 일회성 워커가 동시에 떠도 같은 건을 중복 업로드하지 않도록
        // 프로세스 내 재전송을 직렬화한다. (서버 중복방지는 비원자적 pre-check라 경쟁에 취약)
        private val resendMutex = Mutex()
    }

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        resendMutex.withLock { resend() }
    }

    private suspend fun resend(): Result {
        val prefs = applicationContext.getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        if (!prefs.getBoolean("AUTO_SYNC_ENABLED", true)) {
            Log.d(TAG, "자동 연동 OFF — 재전송 워커 건너뜀")
            return Result.success()
        }

        // 영구실패 음성 안내를 위해 TTS 미리 초기화(엔진 연결은 비동기 → 업로드 진행 중 준비됨).
        UploadManager.initTts(applicationContext)

        val dao = AppDatabase.getDatabase(applicationContext).callHistoryDao()
        val items = dao.getRetryable(ResendPolicy.MAX_RETRY)
        Log.d(TAG, "재시도 대상 ${items.size}건")

        var changed = false
        var newPermanentFailures = 0
        for (item in items) {
            val file = File(item.audioFilePath)
            if (item.audioFilePath.isEmpty() || !file.exists()) {
                // 녹음파일 없음 → 영구실패로 제외
                item.syncStatus = 2
                dao.update(item)
                changed = true
                newPermanentFailures++
                Log.d(TAG, "녹음파일 없음 → 영구실패 처리 id=${item.id}")
                continue
            }

            val ok = UploadManager.uploadOnce(applicationContext, item.id)
            if (ok) {
                changed = true
                Log.d(TAG, "재전송 성공 id=${item.id}")
            } else {
                val fresh = dao.getAll().find { it.id == item.id } ?: continue
                val (newCount, newSync) = ResendPolicy.afterFailure(fresh.retryCount)
                fresh.retryCount = newCount
                fresh.syncStatus = newSync
                dao.update(fresh)
                changed = true
                if (newSync == 2) newPermanentFailures++
                Log.d(TAG, "재전송 실패 id=${item.id} retry=$newCount sync=$newSync")
            }
        }

        if (changed) {
            applicationContext.sendBroadcast(Intent("com.ggotai.hp.ACTION_UPDATE_HISTORY"))
        }
        if (newPermanentFailures > 0) {
            Log.d(TAG, "영구실패 ${newPermanentFailures}건 → 음성 안내")
            UploadManager.playTtsPermanentFailure(applicationContext, newPermanentFailures)
        }
        return Result.success()
    }
}
