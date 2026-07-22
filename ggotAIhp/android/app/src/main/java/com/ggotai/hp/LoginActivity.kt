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
import com.ggotai.hp.manager.DeviceStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private var isAuthenticating = false

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

    override fun onResume() {
        super.onResume()
        // 설정 화면에서 권한을 허용하고 돌아왔을 때 이어서 진행
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
            if (android.os.Environment.isExternalStorageManager()) {
                checkPermissions()
            }
        }
    }

    private fun checkPermissions() {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
            if (!android.os.Environment.isExternalStorageManager()) {
                Toast.makeText(this, "통화 녹음 파일을 가져오기 위해 모든 파일 접근 권한을 허용해주세요.", Toast.LENGTH_LONG).show()
                val intent = Intent(android.provider.Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                intent.data = android.net.Uri.parse("package:$packageName")
                startActivity(intent)
                return
            }
        }

        val requiredPermissions = mutableListOf(
            Manifest.permission.READ_PHONE_NUMBERS,
            Manifest.permission.READ_PHONE_STATE,
            Manifest.permission.READ_CALL_LOG,
            Manifest.permission.READ_EXTERNAL_STORAGE,
            Manifest.permission.READ_CONTACTS,
            // 문자 주문 수집 — 없으면 SmsReceiver 가 아예 호출되지 않는다.
            Manifest.permission.RECEIVE_SMS,
            // 긴 문자(LMS)는 MMS 로 온다. 같은 SMS 권한 그룹이라 보통 함께 부여되지만,
            // 자동 부여가 안 되는 기기를 대비해 명시적으로 요청한다.
            Manifest.permission.RECEIVE_MMS,
            // MmsScanner 가 MMS 수신함(content://mms)을 읽는 데 필요하다. MainActivity 는
            // 이미 RECEIVE_MMS 와 함께 이 권한을 요구하도록 고쳐졌는데, 여기(신규 설치
            // 경로)만 빠뜨리면 SMS 권한 그룹 동시 부여에만 기대게 된다 — MainActivity 를
            // 고친 이유가 바로 그 가정에 기대지 않기 위해서였다.
            Manifest.permission.READ_SMS
        )
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            requiredPermissions.add(Manifest.permission.POST_NOTIFICATIONS)
            requiredPermissions.add(Manifest.permission.READ_MEDIA_AUDIO)
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
        if (isAuthenticating) return
        isAuthenticating = true
        
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
                    DeviceStatus.clearRevoked(this@LoginActivity)
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
        isAuthenticating = false
        binding.progressBar.visibility = View.GONE
        binding.tvErrorMessage.visibility = View.VISIBLE
        binding.tvErrorMessage.text = message
        binding.btnConfirm.visibility = View.VISIBLE
    }
}
