package com.ggotai.hp.util

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities

/** 인터넷 전송이 실제 가능한 네트워크가 있는지 판단한다. */
object NetworkUtil {

    /**
     * 인터넷(검증된) 연결 여부.
     * 통화 직후 VoLTE(IMS) 망만 살아있는 순간 등에는 false → 업로드를 보류한다.
     */
    fun isOnline(context: Context): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return false
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }
}
