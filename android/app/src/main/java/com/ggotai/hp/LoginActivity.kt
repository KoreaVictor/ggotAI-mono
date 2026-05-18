package com.ggotai.hp

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.telephony.TelephonyManager
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.ggotai.hp.api.RetrofitClient
import com.ggotai.hp.databinding.ActivityLoginBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.entries.all { it.value }
        if (allGranted) {
            extractPhoneNumberAndVerify()
        } else {
            showError("권한이 거부되어 앱을 사용할 수 없습니다.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.btnConfirm.setOnClickListener {
            finishAndRemoveTask()
        }

        checkPermissions()
    }

    private fun checkPermissions() {
        val requiredPermissions = mutableListOf(
            Manifest.permission.READ_PHONE_NUMBERS,
            Manifest.permission.READ_PHONE_STATE,
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.READ_CALL_LOG
        )
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            requiredPermissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }

        val allGranted = requiredPermissions.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }

        if (allGranted) {
            extractPhoneNumberAndVerify()
        } else {
            requestPermissionLauncher.launch(requiredPermissions.toTypedArray())
        }
    }

    private fun extractPhoneNumberAndVerify() {
        try {
            val telephonyManager = getSystemService(Context.TELEPHONY_SERVICE) as TelephonyManager
            var phoneNumber = ""
            
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_PHONE_NUMBERS) == PackageManager.PERMISSION_GRANTED) {
                phoneNumber = telephonyManager.line1Number ?: ""
            }

            if (phoneNumber.isEmpty()) {
                showError("기기에서 전화번호를 추출할 수 없습니다.\n유심이 장착되어 있는지 확인해주세요.")
                return
            }

            val cleanNumber = phoneNumber.replace(Regex("[^0-9]"), "")
            val formattedNumber = if (cleanNumber.startsWith("82")) {
                "0" + cleanNumber.substring(2)
            } else {
                cleanNumber
            }

            // Save user phone number to SharedPreferences
            val prefs = getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
            prefs.edit().putString("USER_PHONE_NUMBER", formattedNumber).apply()

            binding.tvPhoneNumber.text = "[핸드폰 번호: $formattedNumber]"
            
            verifyDeviceOnServer(formattedNumber)

        } catch (e: Exception) {
            showError("기기 정보를 읽는 중 오류가 발생했습니다.")
            e.printStackTrace()
        }
    }

    private fun verifyDeviceOnServer(phoneNumber: String) {
        lifecycleScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    com.ggotai.hp.api.RetrofitClient.instance.verifyDevice(phoneNumber)
                }
                
                if (response.isSuccessful && response.body()?.status == "success") {
                    val shopName = response.body()?.data?.shop_name ?: "꽃가게"
                    Toast.makeText(this@LoginActivity, "$shopName 님 환영합니다.", Toast.LENGTH_SHORT).show()
                    
                    val intent = Intent(this@LoginActivity, MainActivity::class.java)
                    intent.putExtra("SHOP_NAME", shopName)
                    startActivity(intent)
                    finish()
                } else {
                    val errorMsg = response.body()?.message ?: "이 핸드폰은 사용할 수 없습니다."
                    showError(errorMsg)
                }
            } catch (e: Exception) {
                showError("서버 접속에 실패했습니다.\n인터넷 연결을 확인하세요.")
            }
        }
    }

    private fun showError(message: String) {
        binding.progressBar.visibility = View.GONE
        binding.tvErrorMessage.visibility = View.VISIBLE
        binding.tvErrorMessage.text = message
        binding.btnConfirm.visibility = View.VISIBLE
    }
}
