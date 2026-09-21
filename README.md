# Wi-Fi Monitor Suite v2

نرم‌افزار گرافیکی (PySide6) برای مانیتورینگ خودکار وای‌فای: مانیتور مود،
channel hopping، کپچر با tshark، و نمایش زنده‌ی بسته‌ها/SSIDها روی
یک داشبورد با تم تیره. روی هر سه پلتفرم (لینوکس/ویندوز/مک) اجرا می‌شود؛
سطح واقعی پشتیبانی هر کدام متفاوت است.

## ساختار پروژه

```
wireless-sniffer-toolkit/
├── main_gui.py              # رابط گرافیکی (PySide6)
├── __main__.py              # python -m از ریشه پروژه
├── requirements.txt
├── requirements-build.txt   # PyInstaller برای ساخت exe
├── scripts/
│   ├── build_exe.bat        # ساخت exe با دابل‌کلیک (ویندوز)
│   ├── build_exe.ps1        # اسکریپت اصلی بیلد
│   └── clean.bat            # پاک‌سازی build/dist
├── README.md
├── LICENSE
├── tests/
└── core/
    ...
```

## ساخت فایل اجرایی (ویندوز)

```bat
scripts\build_exe.bat
```

یا در PowerShell:

```powershell
.\scripts\build_exe.ps1
.\scripts\build_exe.ps1 -Clean
```

خروجی:
`dist\WiFi-Monitor-Suite.exe`

برای مانیتور مود، exe را با Run as Administrator اجرا کنید.

## نصب

```bash
pip install -r requirements.txt
```

ابزارهای سیستمی:

**لینوکس** (کامل):
```bash
sudo apt install aircrack-ng tshark wireless-tools iw
```

**ویندوز** (جزئی):
- Wireshark (شامل tshark)
- Npcap با **"Support raw 802.11 traffic (and monitor mode)"**
- اجرا با **Run as Administrator**

**مک** (تجربی):
- `airport` روی مک‌های قدیمی؛ روی Apple Silicon معمولاً نیست
- `mergecap` از Wireshark برای ترکیب کپچرها

## اجرا

```bash
# لینوکس/مک
sudo python3 main_gui.py
# یا
sudo python3 -m .

# ویندوز (Administrator)
python main_gui.py
```

## تست

```bash
python -m unittest discover -s tests -v
```

تست‌ها بدون سخت‌افزار مانیتور مود اجرا می‌شوند (پارس، کانال، CSV، دود GUI).

## قابلیت‌ها

- جدول زنده: SSID / BSSID / کانال / سیگنال / تعداد بسته
- فیلتر زنده روی جدول + خروجی CSV
- تایمر مدت سشن + هشدار قطع شدن فرآیند کپچر
- thread-safe start/stop با Signalهای Qt
- readiness در استارت (sudo/Npcap/tshark/…)
- لینوکس: `iw`/`airmon-ng` + مدیریت موقت NetworkManager
- ویندوز: `WlanHelper` + اولویت اینترفیس‌های وای‌فای از `tshark -D`
- مک: hopping شبیه‌سازی‌شده با `airport` + `mergecap`

## محدودیت‌ها

مانیتور مود سطح درایور است:
- لینوکس: وابسته به chipset
- ویندوز: وابسته به Npcap + درایور
- مک: عملاً سخت‌افزار قدیمی یا آداپتور USB

## نکته حقوقی

فقط روی شبکه‌ی خودتان یا با مجوز رسمی استفاده کنید.
