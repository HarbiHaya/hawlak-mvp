import { ApiError, ContractError } from "./api";

/** Error raised when a photo is requested in offline fixture mode. */
export class OfflineMediaError extends Error {
  constructor() {
    super("offline_media");
    this.name = "OfflineMediaError";
  }
}

/**
 * Plain Arabic message for any error the dashboard can hit.
 * Never includes the bearer token or a full phone number.
 */
export function describeError(error: unknown, context: { conflict?: string } = {}): string {
  if (error instanceof ContractError) {
    const shown = error.issues.slice(0, 3).join(" · ");
    const more = error.issues.length > 3 ? ` (+${error.issues.length - 3})` : "";
    return `الاستجابة لا تطابق العقد (${error.where}): ${shown}${more}`;
  }
  if (error instanceof OfflineMediaError) {
    return "الصور متاحة فقط عند الاتصال بالخادم.";
  }
  if (error instanceof ApiError) {
    switch (error.status) {
      case 0:
        return "تعذّر الوصول إلى الخادم. تأكد أن الواجهة البرمجية تعمل وأن DASHBOARD_ORIGIN يطابق عنوان هذه اللوحة (http://localhost:5173).";
      case 401:
        return "رمز الدخول غير صحيح. اقفل اللوحة وأدخل الرمز من جديد.";
      case 400:
        return `طلب غير صالح (${error.code}).`;
      case 404:
        return `غير موجود (${error.code}).`;
      case 409:
        return context.conflict ?? `تعارض مع بيانات محفوظة (${error.code}).`;
      case 422:
        return "رفض الخادم البيانات المرسلة لأنها لا تطابق النموذج المتوقع.";
      case 502:
        return `تعذّر الإرسال عبر واتساب${error.serverMessage ? `: ${error.serverMessage}` : "."}`;
      case 503:
        return "التخزين غير متاح حاليًا. حاول بعد قليل.";
      default:
        return `خطأ من الخادم (${error.status} · ${error.code}).`;
    }
  }
  return "حدث خطأ غير متوقع.";
}
