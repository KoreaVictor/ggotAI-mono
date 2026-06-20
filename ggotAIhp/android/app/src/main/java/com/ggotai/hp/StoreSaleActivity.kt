package com.ggotai.hp

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.ggotai.hp.databinding.ActivityStoreSaleBinding
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.CallHistory
import com.ggotai.hp.manager.UploadManager
import com.ggotai.hp.recorder.RecordingStopDecider
import com.ggotai.hp.recorder.StoreSaleRecorder
import com.ggotai.hp.recorder.StopReason
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** 매장판매: 사장님 음성 주문을 인앱 녹음 → 가게음성 채널로 업로드. */
class StoreSaleActivity : AppCompatActivity() {

    private lateinit var binding: ActivityStoreSaleBinding
    private val recorder by lazy { StoreSaleRecorder(applicationContext) }
    private val handler = Handler(Looper.getMainLooper())
    private var startedAt = 0L
    private var finished = false

    private val permLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) beginRecording() else denyAndExit() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityStoreSaleBinding.inflate(layoutInflater)
        setContentView(binding.root)
        UploadManager.initTts(applicationContext)

        binding.btnStop.setOnClickListener { finishRecording(StopReason.MANUAL) }
        binding.btnCancel.setOnClickListener { recorder.cancel(); finish() }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            == PackageManager.PERMISSION_GRANTED) {
            beginRecording()
        } else {
            permLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun denyAndExit() {
        Toast.makeText(this, "마이크 권한이 필요합니다.", Toast.LENGTH_LONG).show()
        finish()
    }

    private fun beginRecording() {
        val ok = recorder.start { reason -> runOnUiThread { finishRecording(reason) } }
        if (!ok) { Toast.makeText(this, "녹음을 시작하지 못했습니다.", Toast.LENGTH_LONG).show(); finish(); return }
        startedAt = SystemClock.elapsedRealtime()
        handler.post(tick)
    }

    private val tick = object : Runnable {
        override fun run() {
            val s = (SystemClock.elapsedRealtime() - startedAt) / 1000
            binding.tvTimer.text = String.format(Locale.getDefault(), "%02d:%02d", s / 60, s % 60)
            handler.postDelayed(this, 500)
        }
    }

    private fun finishRecording(reason: StopReason) {
        if (finished) return
        finished = true
        handler.removeCallbacks(tick)
        val result = recorder.stop()
        if (result == null) { Toast.makeText(this, "녹음 저장에 실패했습니다.", Toast.LENGTH_LONG).show(); finish(); return }

        if (!RecordingStopDecider.isSendable(result.elapsedMs, result.hadSpeech)) {
            UploadManager.speak("녹음이 짧아 취소되었습니다.")
            Toast.makeText(this, "녹음이 짧아 취소되었습니다.", Toast.LENGTH_SHORT).show()
            result.file.delete()
            finish(); return
        }

        val prefs = getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        val userPhone = prefs.getString("USER_PHONE_NUMBER", "Unknown") ?: "Unknown"
        val now = Date()
        val history = CallHistory(
            userPhoneNumber = userPhone,
            callDate = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(now),
            callTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(now),
            phoneNumber = "",
            customerName = "매장판매",
            transferStatus = "전송중",
            audioFileName = result.file.name,
            audioFilePath = result.file.absolutePath,
            durationSeconds = (result.elapsedMs / 1000).toInt(),
            callType = null,
            channelOrder = "가게음성",
            syncStatus = 0
        )
        Toast.makeText(this, "매장판매 주문을 전송합니다.", Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val id = withContext(Dispatchers.IO) {
                AppDatabase.getDatabase(applicationContext).callHistoryDao().insert(history).toInt()
            }
            UploadManager.uploadCallHistory(applicationContext, id, successMessage = "매장판매 주문이 접수되었습니다.")
            finish()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacks(tick)
    }
}
