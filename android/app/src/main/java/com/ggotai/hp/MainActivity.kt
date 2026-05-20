package com.ggotai.hp

import android.graphics.Color
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.DividerItemDecoration
import androidx.recyclerview.widget.LinearLayoutManager
import com.ggotai.hp.databinding.ActivityMainBinding
import com.ggotai.hp.db.AppDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var adapter: CallHistoryAdapter

    private val updateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == "com.ggotai.hp.ACTION_UPDATE_HISTORY") {
                loadCallHistory()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val shopName = intent.getStringExtra("SHOP_NAME") ?: "서울플라워"
        binding.tvShopName.text = shopName
        
        val currentDate = java.text.SimpleDateFormat("yyyy.MM.dd", java.util.Locale.getDefault()).format(java.util.Date())
        binding.tvDateHeader.text = "$currentDate 전화 수신 현황"

        binding.btnSearch.setOnClickListener {
            startActivity(Intent(this, SearchActivity::class.java))
        }
        
        binding.btnSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        setupRecyclerView()
        loadCallHistory()
    }

    private fun setupRecyclerView() {
        adapter = CallHistoryAdapter(emptyList())
        binding.recyclerView.layoutManager = LinearLayoutManager(this)
        binding.recyclerView.adapter = adapter
        binding.recyclerView.addItemDecoration(DividerItemDecoration(this, DividerItemDecoration.VERTICAL))
    }

    private fun loadCallHistory() {
        lifecycleScope.launch {
            val db = AppDatabase.getDatabase(applicationContext)
            val currentDateDb = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.getDefault()).format(java.util.Date())
            val historyList = withContext(Dispatchers.IO) {
                db.callHistoryDao().getByDate(currentDateDb)
            }
            adapter.updateData(historyList)
        }
    }

    override fun onResume() {
        super.onResume()
        loadCallHistory() // 화면에 돌아올 때도 무조건 새로고침
        
        val filter = IntentFilter("com.ggotai.hp.ACTION_UPDATE_HISTORY")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(updateReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(updateReceiver, filter)
        }
    }

    override fun onPause() {
        super.onPause()
        unregisterReceiver(updateReceiver)
    }
}

