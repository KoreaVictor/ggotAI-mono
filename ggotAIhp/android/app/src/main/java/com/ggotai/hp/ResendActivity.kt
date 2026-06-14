package com.ggotai.hp

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.ggotai.hp.databinding.ActivityResendBinding
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.CallHistory
import com.ggotai.hp.manager.UploadManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class ResendActivity : AppCompatActivity() {

    private lateinit var binding: ActivityResendBinding
    private var historyId: Int = -1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityResendBinding.inflate(layoutInflater)
        setContentView(binding.root)

        historyId = intent.getIntExtra("HISTORY_ID", -1)
        if (historyId == -1) {
            Toast.makeText(this, "잘못된 접근입니다.", Toast.LENGTH_SHORT).show()
            finish()
            return
        }

        loadData()

        binding.btnResend.setOnClickListener {
            if (binding.btnResend.text == "성공") {
                finish()
                return@setOnClickListener
            }
            binding.btnResend.isEnabled = false
            binding.tvCurrentStatus.text = "현재 상태: 전송중"
            binding.tvCurrentStatus.setTextColor(android.graphics.Color.parseColor("#757575")) // Gray
            
            lifecycleScope.launch {
                // 수동 재전송: 영구실패(sync=2) 건도 다시 자동 재시도 대상이 되도록 리셋
                run {
                    val resetDb = AppDatabase.getDatabase(applicationContext)
                    withContext(Dispatchers.IO) {
                        val h = resetDb.callHistoryDao().getAll().find { it.id == historyId }
                        if (h != null) {
                            h.retryCount = 0
                            h.syncStatus = 0
                            resetDb.callHistoryDao().update(h)
                        }
                    }
                }

                UploadManager.uploadCallHistory(applicationContext, historyId)

                // 다시 로드하여 상태 확인
                val db = AppDatabase.getDatabase(applicationContext)
                val updatedHistory = withContext(Dispatchers.IO) {
                    db.callHistoryDao().getAll().find { it.id == historyId }
                }
                
                if (updatedHistory?.transferStatus == "성공") {
                    binding.tvCurrentStatus.text = "현재 상태: 성공"
                    binding.tvCurrentStatus.setTextColor(android.graphics.Color.parseColor("#212121")) // Black
                    binding.tvErrorLog.text = "에러 로그: -"
                    binding.btnResend.text = "성공"
                    binding.btnResend.isEnabled = true
                } else {
                    binding.btnResend.isEnabled = true
                    binding.tvCurrentStatus.text = "현재 상태: ${updatedHistory?.transferStatus ?: "전송실패"}"
                    binding.tvCurrentStatus.setTextColor(android.graphics.Color.parseColor("#D50000")) // Red
                    binding.tvErrorLog.text = "에러 로그: ${updatedHistory?.errorMessage ?: "알 수 없는 에러"}"
                }
            }
        }
    }

    private fun loadData() {
        lifecycleScope.launch {
            val db = AppDatabase.getDatabase(applicationContext)
            val history = withContext(Dispatchers.IO) {
                db.callHistoryDao().getAll().find { it.id == historyId }
            }

            if (history != null) {
                binding.tvTargetInfo.text = "고객: ${history.customerName} (${history.phoneNumber})"
                binding.tvCurrentStatus.text = "현재 상태: ${history.transferStatus}"
                
                if (history.transferStatus == "성공") {
                    binding.tvCurrentStatus.setTextColor(android.graphics.Color.parseColor("#212121")) // Black
                    binding.tvErrorLog.text = "에러 로그: -"
                    binding.btnResend.text = "성공"
                    binding.btnResend.isEnabled = true
                } else {
                    binding.tvCurrentStatus.setTextColor(android.graphics.Color.parseColor("#D50000")) // Red
                    binding.tvErrorLog.text = "에러 로그: ${history.errorCode ?: ""} - ${history.errorMessage ?: "없음"}"
                    binding.btnResend.text = "재전송"
                    binding.btnResend.isEnabled = true
                }
            } else {
                finish()
            }
        }
    }
}
