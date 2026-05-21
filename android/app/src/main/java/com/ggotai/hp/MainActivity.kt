package com.ggotai.hp

import android.app.DatePickerDialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.DividerItemDecoration
import androidx.recyclerview.widget.LinearLayoutManager
import com.ggotai.hp.api.DeleteCallRequest
import com.ggotai.hp.api.RetrofitClient
import com.ggotai.hp.databinding.ActivityMainBinding
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.CallHistory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var adapter: CallHistoryAdapter
    private val selectedCalendar: Calendar = Calendar.getInstance()

    private val updateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == "com.ggotai.hp.ACTION_UPDATE_HISTORY") {
                // 통화 종료 및 데이터 업로드 완료 시 반드시 오늘 날짜로 셋팅
                resetToToday()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val shopName = intent.getStringExtra("SHOP_NAME") ?: "서울플라워"
        binding.tvShopName.text = shopName

        // 오늘 날짜로 세팅 및 표시 업데이트
        resetToToday()

        // 오늘 버튼 연동
        binding.btnToday.setOnClickListener {
            resetToToday()
        }

        // 날짜 클릭 시 DatePickerDialog 연동
        binding.tvSelectedDate.setOnClickListener {
            showDatePicker()
        }
        
        binding.btnSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        setupRecyclerView()
    }

    private fun setupRecyclerView() {
        adapter = CallHistoryAdapter(emptyList())
        adapter.setOnItemLongClickListener(object : CallHistoryAdapter.OnItemLongClickListener {
            override fun onItemLongClick(item: CallHistory) {
                showDeleteDialog(item)
            }
        })
        binding.recyclerView.layoutManager = LinearLayoutManager(this)
        binding.recyclerView.adapter = adapter
        binding.recyclerView.addItemDecoration(DividerItemDecoration(this, DividerItemDecoration.VERTICAL))
    }

    private fun showDeleteDialog(item: CallHistory) {
        AlertDialog.Builder(this)
            .setTitle("통화 내역 삭제")
            .setMessage("이 통화 내역을 삭제하시겠습니까?\n(서버에서도 함께 영구 삭제됩니다)")
            .setPositiveButton("삭제") { dialog, _ ->
                deleteCallHistory(item)
                dialog.dismiss()
            }
            .setNegativeButton("취소") { dialog, _ ->
                dialog.dismiss()
            }
            .show()
    }

    private fun deleteCallHistory(item: CallHistory) {
        lifecycleScope.launch {
            // 1단계: 로컬 DB(Room)에서 즉시 영구 삭제 수행
            val db = AppDatabase.getDatabase(applicationContext)
            withContext(Dispatchers.IO) {
                db.callHistoryDao().delete(item)
            }
            Toast.makeText(this@MainActivity, "로컬 내역이 삭제되었습니다.", Toast.LENGTH_SHORT).show()
            
            // 삭제 후 즉시 목록 새로고침
            loadCallHistory()

            // 2단계: 서버(Supabase Edge Function) 비동기 연쇄 삭제 요청 (음성 파일도 서버에서 영구 파쇄)
            if (item.audioFileName.isNotEmpty()) {
                withContext(Dispatchers.IO) {
                    try {
                        // 서버 DB 및 스토리지에 저장된 실제 파일명 규격으로 매칭 파일명 재구성
                        // 규칙: {user_phone}_{customer_phone}_{YYYYMMDD}_{HHmmss}.wav
                        val serverDateStr = item.callDate.replace("-", "")
                        val serverTimeStr = item.callTime.replace(":", "")
                        val serverAudioFileName = "${item.userPhoneNumber}_${item.phoneNumber}_${serverDateStr}_${serverTimeStr}.wav"

                        val response = RetrofitClient.instance.deleteCall(
                            DeleteCallRequest(
                                user_phone_number = item.userPhoneNumber,
                                audio_file_name = serverAudioFileName
                            )
                        )
                        withContext(Dispatchers.Main) {
                            if (response.isSuccessful && response.body()?.status == "success") {
                                val successMsg = response.body()?.message ?: "서버 보관 데이터도 완벽하게 삭제되었습니다."
                                Toast.makeText(this@MainActivity, successMsg, Toast.LENGTH_SHORT).show()
                            } else {
                                val errorMsg = response.body()?.message ?: "응답 실패 (코드: ${response.code()})"
                                Log.w("MainActivity", "서버 삭제 응답 실패: $errorMsg")
                                Toast.makeText(this@MainActivity, "서버 내역 삭제 실패: $errorMsg", Toast.LENGTH_LONG).show()
                            }
                        }
                    } catch (e: Exception) {
                        Log.e("MainActivity", "서버 삭제 요청 중 에러 발생", e)
                        withContext(Dispatchers.Main) {
                            Toast.makeText(this@MainActivity, "서버 삭제 요청 실패 (네트워크 연결을 확인하세요)", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            }
        }
    }

    private fun resetToToday() {
        selectedCalendar.timeInMillis = System.currentTimeMillis()
        updateDateDisplay()
        loadCallHistory()
    }

    private fun updateDateDisplay() {
        val displayFormat = SimpleDateFormat("yyyy.MM.dd", Locale.getDefault())
        binding.tvSelectedDate.text = displayFormat.format(selectedCalendar.time)
    }

    private fun showDatePicker() {
        val year = selectedCalendar.get(Calendar.YEAR)
        val month = selectedCalendar.get(Calendar.MONTH)
        val day = selectedCalendar.get(Calendar.DAY_OF_MONTH)

        DatePickerDialog(this, { _, selectedYear, selectedMonth, selectedDay ->
            selectedCalendar.set(Calendar.YEAR, selectedYear)
            selectedCalendar.set(Calendar.MONTH, selectedMonth)
            selectedCalendar.set(Calendar.DAY_OF_MONTH, selectedDay)
            updateDateDisplay()
            loadCallHistory()
        }, year, month, day).show()
    }

    private fun loadCallHistory() {
        lifecycleScope.launch {
            val db = AppDatabase.getDatabase(applicationContext)
            val dbFormat = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault())
            val dateQuery = dbFormat.format(selectedCalendar.time)
            
            val historyList = withContext(Dispatchers.IO) {
                db.callHistoryDao().getByDate(dateQuery)
            }
            adapter.updateData(historyList)
        }
    }

    override fun onResume() {
        super.onResume()
        // 앱이 다시 화면에 돌아올 때도 반드시 오늘 날짜로 셋팅하고 조회
        resetToToday()
        
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

