"""راهنمای سخت‌افزار و آداپتورهای پیشنهادی برای مانیتور مود."""

from __future__ import annotations

RECOMMENDED_ADAPTERS = [
    "Alfa AWUS036ACH / AWUS036ACM (chipset Realtek/MediaTek — معمولاً خوب روی لینوکس)",
    "Alfa AWUS036NHA (Atheros AR9271 — کلاسیک برای مانیتور مود لینوکس)",
    "TP-Link TL-WN722N v1 فقط (Atheros؛ نسخه‌های جدیدتر اغلب کار نمی‌کنند)",
    "Panda PAU09 / PAU06 (روی بعضی درایورهای لینوکس)",
]

WINDOWS_HINT = (
    "اکثر کارت‌های وای‌فای داخلی لپ‌تاپ روی ویندوز OID مانیتور مود را پشتیبانی نمی‌کنند. "
    "Npcap + WlanHelper لازم است و حتی با آن هم موفقیت تضمینی نیست. "
    "برای نتیجهٔ قابل‌اعتماد یک آداپتور USB سازگار بخرید یا از لینوکس استفاده کنید."
)


def recommended_adapters_text() -> str:
    lines = [WINDOWS_HINT, "", "آداپتورهای پیشنهادی:"]
    lines.extend(f"• {a}" for a in RECOMMENDED_ADAPTERS)
    return "\n".join(lines)


def monitor_mode_failure_message(detail: str = "") -> str:
    base = (
        "فعال‌سازی مانیتور مود ناموفق بود.\n\n"
        f"{WINDOWS_HINT}\n\n"
        "آداپتورهای پیشنهادی:\n"
        + "\n".join(f"• {a}" for a in RECOMMENDED_ADAPTERS)
    )
    if detail:
        base += f"\n\nجزئیات فنی: {detail[:400]}"
    return base
