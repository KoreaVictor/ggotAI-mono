package com.ggotai.hp

import android.app.DatePickerDialog
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
import com.ggotai.hp.databinding.ActivitySearchBinding
import com.ggotai.hp.db.AppDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

class SearchActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySearchBinding
    private lateinit var adapter: CallHistoryAdapter
    private var selectedDate: String? = null

    private val updateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == "com.ggotai.hp.ACTION_UPDATE_HISTORY") {
                performSearch()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySearchBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupToolbar()
        setupRecyclerView()
        setupFilters()

        // 기본 검색 (오늘 날짜, 전체)
        selectedDate = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
        binding.tvDate.text = selectedDate
    }

    override fun onResume() {
        super.onResume()
        performSearch() // 화면에 돌아올 때 자동으로 최신 검색 실행
        
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

    private fun setupToolbar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        binding.toolbar.setNavigationOnClickListener { finish() }
    }

    private fun setupRecyclerView() {
        adapter = CallHistoryAdapter(emptyList())
        binding.rvSearch.layoutManager = LinearLayoutManager(this)
        binding.rvSearch.adapter = adapter
        binding.rvSearch.addItemDecoration(DividerItemDecoration(this, DividerItemDecoration.VERTICAL))
    }

    private fun setupFilters() {
        binding.tvDate.setOnClickListener {
            val calendar = Calendar.getInstance()
            DatePickerDialog(this, { _, year, month, dayOfMonth ->
                selectedDate = String.format("%04d-%02d-%02d", year, month + 1, dayOfMonth)
                binding.tvDate.text = selectedDate
            }, calendar.get(Calendar.YEAR), calendar.get(Calendar.MONTH), calendar.get(Calendar.DAY_OF_MONTH)).show()
        }

        binding.btnSearchSubmit.setOnClickListener {
            performSearch()
        }
    }

    private fun performSearch() {
        val statusFilter = when {
            binding.rbSuccess.isChecked -> "성공"
            binding.rbFail.isChecked -> "실패"
            else -> "전체"
        }
        val dateFilter = selectedDate

        lifecycleScope.launch {
            val db = AppDatabase.getDatabase(applicationContext)
            val historyList = withContext(Dispatchers.IO) {
                var list = db.callHistoryDao().getAll()
                
                if (dateFilter != null) {
                    list = list.filter { it.callDate == dateFilter }
                }
                
                if (statusFilter != "전체") {
                    list = list.filter { it.transferStatus == statusFilter }
                }
                list
            }
            adapter.updateData(historyList)
        }
    }
}
