import axios from "axios";

export function toErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (detail && typeof detail === "object") {
      const message = typeof (detail as { message?: unknown }).message === "string"
        ? String((detail as { message: string }).message)
        : "";
      const errors = Array.isArray((detail as { errors?: unknown }).errors)
        ? ((detail as { errors: unknown[] }).errors.filter((value) => typeof value === "string") as string[])
        : [];
      if (errors.length > 0) {
        return [message || fallback, ...errors].join("\n");
      }
      if (message.trim()) return message;
      return fallback;
    }
    if (error.message) {
      return error.message;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
