package com.ggotai.hp

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import androidx.appcompat.app.AppCompatActivity
import com.ggotai.hp.databinding.ActivitySettingsBinding
import com.ggotai.hp.service.KakaoMessageListenerService

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.title = "환경설정"
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        binding.toolbar.setNavigationOnClickListener { finish() }

        val prefs = getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        // 기본값은 true (기능 자동화 켜짐)
        val isAutoSyncEnabled = prefs.getBoolean("AUTO_SYNC_ENABLED", true)

        binding.switchAutoSync.isChecked = isAutoSyncEnabled

        binding.switchAutoSync.setOnCheckedChangeListener { _, isChecked ->
            prefs.edit().putBoolean("AUTO_SYNC_ENABLED", isChecked).apply()
        }

        binding.buttonKakaoAccess.setOnClickListener {
            // 알림 접근은 앱이 요청할 수 없고 사용자가 시스템 설정에서 직접 켜야 한다.
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }
    }

    override fun onResume() {
        super.onResume()
        // 설정 화면에서 켜고 돌아왔을 수 있으므로 매번 다시 확인한다.
        val enabled = KakaoMessageListenerService.isEnabled(this)
        binding.textKakaoStatus.text = if (enabled) {
            "정상 — 카톡 주문을 수집하고 있습니다."
        } else {
            "꺼짐 — 알림 접근을 허용해야 카톡 주문이 수집됩니다."
        }
        binding.textKakaoStatus.setTextColor(
            if (enabled) 0xFF2E7D32.toInt() else 0xFFC62828.toInt()
        )
        binding.buttonKakaoAccess.text = if (enabled) "설정 열기" else "권한 설정"
    }
}
