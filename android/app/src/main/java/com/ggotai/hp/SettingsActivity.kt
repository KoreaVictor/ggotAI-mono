package com.ggotai.hp

import android.content.Context
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.ggotai.hp.databinding.ActivitySettingsBinding

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
    }
}
