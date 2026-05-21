package com.ggotai.hp.api

import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Query

data class VerifyDeviceResponse(
    val status: String,
    val data: ShopData?,
    val error_code: String?,
    val message: String?
)

data class ShopData(
    val shop_name: String,
    val representative_name: String,
    val is_approved: String
)

data class UploadCallResponse(
    val status: String,
    val message: String?,
    val error_code: String?
)

data class DeleteCallRequest(
    val user_phone_number: String,
    val audio_file_name: String
)

data class DeleteCallResponse(
    val status: String,
    val message: String?,
    val error_code: String?
)

interface ApiService {
    @GET("verify-device")
    suspend fun verifyDevice(@Query("phone") phone: String): Response<VerifyDeviceResponse>

    @retrofit2.http.Multipart
    @retrofit2.http.POST("upload-call")
    suspend fun uploadCall(
        @retrofit2.http.Part("user_phone_number") userPhoneNumber: okhttp3.RequestBody,
        @retrofit2.http.Part("phone_number") phoneNumber: okhttp3.RequestBody,
        @retrofit2.http.Part("customer_name") customerName: okhttp3.RequestBody,
        @retrofit2.http.Part("call_date") callDate: okhttp3.RequestBody,
        @retrofit2.http.Part("call_time") callTime: okhttp3.RequestBody,
        @retrofit2.http.Part("duration_seconds") durationSeconds: okhttp3.RequestBody,
        @retrofit2.http.Part audioFile: okhttp3.MultipartBody.Part
    ): Response<UploadCallResponse>

    @retrofit2.http.POST("delete-call")
    suspend fun deleteCall(
        @retrofit2.http.Body request: DeleteCallRequest
    ): Response<DeleteCallResponse>
}
