export function otpMessage(reason: string | undefined): string {
  switch (reason) {
    case 'not_found':     return '인증번호를 먼저 요청해주세요';
    case 'expired':       return '인증번호가 만료되었습니다. 다시 요청해주세요';
    case 'mismatch':      return '인증번호가 일치하지 않습니다';
    case 'too_many':      return '시도 횟수를 초과했습니다. 다시 요청해주세요';
    case 'invalid_token': return '인증이 만료되었습니다. 다시 인증해주세요';
    case 'rate_limit':    return '잠시 후 다시 시도해주세요';
    case 'send_failed':   return '인증번호 발송에 실패했습니다';
    default:              return '오류가 발생했습니다. 다시 시도해주세요';
  }
}
