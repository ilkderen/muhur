#!/usr/bin/env python3
"""Damga denemeleri için örnek dilekçe üretir.

Kullanım: ornek-uret.py [dosya.pdf]
Varsayılan çıktı: ~/e-imza/deneme-dilekce.pdf
"""

import sys
from pathlib import Path

import pymupdf

import damga

GOVDE = [
    "DOSYA NO : 2026/000 E.",
    "KONU     : Beyanlarımızın sunulmasıdır.",
    "",
    "Yukarıda esas numarası yazılı dosyada, müvekkil adına beyanlarımızı",
    "sunmak üzere işbu dilekçeyi ibraz ediyoruz.",
    "",
    "Bu belge, Mühür uygulamasının damga yerleşimini denemek için",
    "üretilmiş örnek bir metindir. Hukuki bir değeri yoktur.",
    "",
    "SONUÇ VE İSTEM : Yukarıda arz ve izah olunan nedenlerle talebimizin",
    "kabulüne karar verilmesini saygıyla talep ederiz.",
]


def uret(hedef, ad="AV. AD SOYAD"):
    belge = pymupdf.open()
    sayfa = belge.new_page(width=595, height=842)
    sayfa.insert_font(fontname="duz", fontfile=damga.YAZI)
    sayfa.insert_font(fontname="kalin", fontfile=damga.YAZI_KALIN)

    sayfa.insert_text((60, 90), "ANKARA 5. ASLİYE HUKUK MAHKEMESİ'NE",
                      fontname="kalin", fontsize=12)
    y = 140
    for satir in GOVDE:
        sayfa.insert_text((60, y), satir, fontname="duz", fontsize=11)
        y += 22

    sayfa.insert_text((380, y + 40), "MÜŞTEKİ VEKİLİ", fontname="duz", fontsize=11)
    sayfa.insert_text((330, y + 60), ad, fontname="kalin", fontsize=11)
    sayfa.insert_text((60, y + 130), "EKLER:", fontname="kalin", fontsize=11)
    sayfa.insert_text((60, y + 150), "1- Vekaletname", fontname="duz", fontsize=11)

    try:
        belge.subset_fonts()
    except Exception:
        pass
    belge.save(str(hedef), garbage=4, deflate=True, clean=True)
    belge.close()
    return hedef


if __name__ == "__main__":
    hedef = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "e-imza" / "deneme-dilekce.pdf"
    print("üretildi:", uret(hedef))
