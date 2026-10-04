const MESSAGES = Object.freeze({
    chat_review_required: ["This message cannot be sent yet. Please rephrase it.", "ข้อความนี้ยังส่งไม่ได้ กรุณาปรับข้อความแล้วลองอีกครั้ง"],
    chat_invalid_message: ["Check the message length and characters, then try again.", "กรุณาตรวจสอบความยาวและอักขระของข้อความแล้วลองอีกครั้ง"],
    chat_rate_limited: ["You're sending messages too quickly. Please wait a moment.", "ส่งข้อความเร็วเกินไป กรุณารอสักครู่"],
    chat_duplicate: ["This repeats a recent message. Please wait or rephrase it.", "ข้อความนี้ซ้ำกับข้อความล่าสุด กรุณารอสักครู่หรือปรับข้อความก่อนส่ง"],
    chat_unavailable: ["Chat is temporarily unavailable. Please try again.", "ระบบแชทยังไม่พร้อม กรุณาลองอีกครั้ง"],
});

/** Known server reason keys only; never display raw rejected chat or unknown parameters. */
export function chatModerationText(key, language) {
    if (typeof key !== "string" || !Object.hasOwn(MESSAGES, key)) return null;
    return MESSAGES[key][language === "th" ? 1 : 0];
}
