#!/usr/bin/env python3
"""Kart uyumluluk raporu.

Mühür farklı bir e-imza kartında çalışmazsa bu betik çalıştırılır ve çıkan
rapor geliştiriciye gönderilir. PIN sormaz, imza atmaz, karta yazmaz —
yalnızca kartın kendini nasıl tanıttığını okur.

Rapor kişisel veri içermez: ad, TC ve sertifika seri numarası maskelenir.

Kullanım: kart-raporu.py
"""

import platform
import sys
from pathlib import Path

import pkcs11
from pkcs11 import Attribute, ObjectClass

import imza_core

CIKTI = Path.home() / "Desktop" / "muhur-kart-raporu.txt"


def maskele(metin):
    metin = str(metin or "")
    if len(metin) <= 4:
        return "***"
    return metin[:2] + "*" * (len(metin) - 4) + metin[-2:]


def rapor():
    satirlar = []
    yaz = satirlar.append

    yaz("MÜHÜR — KART UYUMLULUK RAPORU")
    yaz("=" * 46)
    yaz(f"macOS      : {platform.mac_ver()[0]}  ({platform.machine()})")
    yaz(f"Python     : {sys.version.split()[0]}")
    yaz("")

    # --- sürücü ---
    try:
        lib_yolu = imza_core.kutuphane_bul()
    except Exception as hata:
        yaz(f"SÜRÜCÜ BULUNAMADI: {hata}")
        yaz("")
        yaz("Denenen yollar:")
        for y in imza_core.BILINEN_KUTUPHANELER:
            yaz(f"   {'VAR' if Path(y).exists() else 'yok'}  {y}")
        return "\n".join(satirlar)

    yaz(f"Sürücü     : {lib_yolu}")

    lib = pkcs11.lib(lib_yolu)
    yaz(f"PKCS#11    : {lib.manufacturer_id} / {lib.library_description}")
    yaz("")

    # --- kart ---
    tokenlar = list(lib.get_tokens())
    yaz(f"Takılı kart sayısı: {len(tokenlar)}")
    for t in tokenlar:
        yaz("")
        yaz(f"  Etiket   : {t.label}")
        yaz(f"  Üretici  : {t.manufacturer_id}")
        yaz(f"  Model    : {t.model}")
        yaz(f"  Flags    : 0x{int(t.flags):x}")

    if not tokenlar:
        return "\n".join(satirlar)

    token = tokenlar[0]

    # --- mekanizmalar (imzalama yöntemi seçimi buna bağlı) ---
    yaz("")
    yaz("Desteklenen mekanizmalar:")
    try:
        slot = list(lib.get_slots(token_present=True))[0]
        for m in sorted(slot.get_mechanisms(), key=lambda x: int(x)):
            yaz(f"   0x{int(m):08x}  {getattr(m, 'name', repr(m))}")
    except Exception as hata:
        yaz(f"   okunamadı: {hata}")

    # --- nesneler (PIN gerektirmez) ---
    yaz("")
    yaz("Karttaki sertifikalar (PIN'siz okunabilenler):")
    try:
        with token.open() as oturum:
            bulundu = 0
            for nesne in oturum.get_objects(
                    {Attribute.CLASS: ObjectClass.CERTIFICATE}):
                bulundu += 1
                try:
                    kimlik = nesne[Attribute.ID].hex()
                except Exception:
                    kimlik = "(yok)"
                try:
                    etiket = nesne[Attribute.LABEL]
                except Exception:
                    etiket = "(yok)"
                yaz(f"   #{bulundu}  CKA_ID={maskele(kimlik)}  "
                    f"CKA_LABEL={maskele(etiket)}")
            if not bulundu:
                yaz("   (sertifika okunamadı — kart PIN'siz okumaya izin vermiyor olabilir)")
    except Exception as hata:
        yaz(f"   oturum açılamadı: {hata}")

    # --- Mühür'ün uyguladığı telafiler ---
    yaz("")
    yaz("MÜHÜR'ÜN VARSAYIMLARI (TÜRKTRUST/AKİS kartına göre yazıldı)")
    yaz("-" * 46)
    try:
        sertifika, kimlik = imza_core.imza_sertifikasi_bul(lib_yolu, token.label)
        konu = sertifika.subject.native
        yaz(f"  İmzalama sertifikası bulundu : EVET")
        yaz(f"     sahip  : {maskele(konu.get('common_name'))}")
        yaz(f"     unvan  : {konu.get('title') or '(yok)'}")
        try:
            yaz(f"     kullanım: {sorted(sertifika.key_usage_value.native)}")
        except Exception:
            yaz("     kullanım: okunamadı")
    except Exception as hata:
        yaz(f"  İmzalama sertifikası bulundu : HAYIR — {hata}")

    yaz("")
    yaz("Bu rapor PIN sormadı, imza atmadı, karta hiçbir şey yazmadı.")
    return "\n".join(satirlar)


def main():
    try:
        metin = rapor()
    except Exception as hata:
        metin = f"Rapor üretilemedi: {type(hata).__name__}: {hata}"

    CIKTI.write_text(metin, encoding="utf-8")
    print(metin)
    print()
    print(f"Rapor masaüstüne kaydedildi: {CIKTI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
