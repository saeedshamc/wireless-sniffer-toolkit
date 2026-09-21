# Wi-Fi Monitor Suite v2

نرم‌افزار گرافیکی (PySide6) برای مانیتورینگ وای‌فای: مانیتور مود، channel hopping
یا قفل کانال، کپچر tshark، جدول زنده AP/Client، نمودار سیگنال و heatmap کانال.

## قابلیت‌های کلیدی

- حالت **Hopping** یا **قفل کانال**
- جدول Networks با Encryption / Vendor / Channel Width
- تب **Clients** و تب **Channels** (heatmap)
- فیلتر: متن، Hidden، حداقل dBm، نوع رمز
- هشدار **Evil Twin** (SSID مشترک با چند BSSID)
- ذخیره تنظیمات در `settings.json`
- لاگ فایل سشن، نمایش حجم فایل کپچر، راهنمای سخت‌افزار
- CLI بدون GUI: `python cli.py`
- Auto-elevate روی ویندوز (UAC)

## نصب

```bash
pip install -r requirements.txt
```

**لینوکس:** `sudo apt install aircrack-ng tshark iw`  
**ویندوز:** Wireshark + Npcap (raw 802.11) + Run as Administrator  
**مک:** فقط با `airport` روی سخت‌افزار قدیمی؛ در غیر این صورت unsupported

## اجرا

```bash
# GUI
sudo python3 main_gui.py          # لینوکس/مک
python main_gui.py                # ویندوز (Admin)

# CLI
python cli.py --list-ifaces
python cli.py --iface wlan0 --band 2.4 --output capture.pcapng --duration 60
python cli.py --iface wlan0 --channel-mode fixed --channel 6 --csv-networks nets.csv
```

## ساخت exe (ویندوز)

```bat
scripts\build_exe.bat
```

پیش‌فرض **onedir** (استارت سریع‌تر). برای تک‌فایل:

```powershell
.\scripts\build_exe.ps1 -OneFile -Clean
```

## تست

```bash
python -m unittest discover -s tests -v
```

## سخت‌افزار پیشنهادی

اکثر کارت‌های داخلی لپ‌تاپ روی ویندوز مانیتور مود ندارند. آداپتورهای USB مثل
Alfa AWUS036ACH / AWUS036NHA یا TP-Link TL-WN722N v1 معمولاً گزینهٔ بهتری‌اند.

## نکته حقوقی

فقط روی شبکهٔ خودتان یا با مجوز رسمی استفاده کنید.
