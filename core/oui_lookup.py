"""جستجوی Vendor از OUI (سه اکتت اول MAC) — دیتابیس فشردهٔ رایج."""

from __future__ import annotations

# پیشوندهای رایج (بدون جداکننده، حروف کوچک)
_OUI_MAP = {
    "000c29": "VMware",
    "00155d": "Microsoft Hyper-V",
    "001a11": "Google",
    "001b63": "Apple",
    "001cc0": "Cisco",
    "001e58": "D-Link",
    "001f3b": "Intel",
    "00219b": "Dell",
    "00226b": "Cisco-Linksys",
    "0024d7": "Intel",
    "0026b9": "Dell",
    "0050f2": "Microsoft",
    "00d0c9": "Intel",
    "0418d6": "Ubiquiti",
    "046273": "Cisco",
    "04d4c4": "ASUSTek",
    "085700": "TP-Link",
    "0c8bfd": "Intel",
    "1002b5": "Intel",
    "14cc20": "TP-Link",
    "18d6c7": "TP-Link",
    "1c697a": "EliteGroup",
    "2059a0": "Xiaomi",
    "246511": "AVM",
    "28c2dd": "AzureWave",
    "2c56dc": "ASUSTek",
    "30b49e": "TP-Link",
    "34ce00": "Xiaomi",
    "3c5ab4": "Google",
    "44d9e7": "Ubiquiti",
    "50c7bf": "TP-Link",
    "525400": "QEMU/KVM",
    "60e327": "TP-Link",
    "649abe": "Apple",
    "70b3d5": "IEEE Registered",
    "744d28": "Routerboard",
    "788a20": "Ubiquiti",
    "7c2f80": "Gigaset",
    "840d8e": "Espressif",
    "8863df": "Apple",
    "8c8590": "Apple",
    "90f652": "TP-Link",
    "9844ce": "Huawei",
    "9c5c8e": "ASUSTek",
    "a0f3c1": "TP-Link",
    "ac84c6": "TP-Link",
    "b0fc36": "Huawei",
    "b4fbe4": "Ubiquiti",
    "bc5ff6": "Mercury",
    "c83a35": "Tenda",
    "cc46d6": "Cisco",
    "d8eb97": "Trendnet",
    "e4f89c": "Intel",
    "e8de27": "TP-Link",
    "f0b429": "Xiaomi",
    "f4f26d": "TP-Link",
    "fc9947": "Cisco",
}


def normalize_mac(mac: str) -> str:
    return "".join(c for c in (mac or "").lower() if c in "0123456789abcdef")


def vendor_from_bssid(bssid: str) -> str:
    hexmac = normalize_mac(bssid)
    if len(hexmac) < 6:
        return "Unknown"
    oui = hexmac[:6]
    return _OUI_MAP.get(oui, "Unknown")
