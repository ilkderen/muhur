#!/usr/bin/env python3
"""Belgelendirme için örnek dilekçe ve damga görüntüsü üretir.

Gerçek müvekkil belgesi ya da gerçek imza kullanılmaz: metin lorem ipsum,
ad uydurma. Üretilen damga görüntüsü yalnızca **görünümü** anlatır, gerçek
bir elektronik imza içermez.

Kullanım:
    ornek-belge-uret.py            # ~/muhur/ornek altına üretir
    ornek-belge-uret.py <klasör>
"""

import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path.home() / "Muhur"))
import damga  # noqa: E402

AD = "AV. AYŞE YILMAZ"
DAMGA_AD = "AYŞE YILMAZ"
UNVAN = "AVUKAT"
TARIH = "18.08.2026 10:15:42 (UTC+0300)"

GOVDE = [
    "DOSYA NO : 2026/1234 E.",
    "KONU     : Beyanlarımızın sunulmasıdır.",
    "",
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Vestibulum",
    "auctor, nisl eget ultricies tincidunt, nisi nisl aliquam nunc, vitae",
    "aliquam nisl nunc vel nisi. Praesent commodo cursus magna, vel",
    "scelerisque nisl consectetur et.",
    "",
    "Curabitur blandit tempus porttitor. Nullam quis risus eget urna mollis",
    "ornare vel eu leo. Donec ullamcorper nulla non metus auctor fringilla.",
    "Maecenas sed diam eget risus varius blandit sit amet non magna.",
    "",
    "Integer posuere erat a ante venenatis dapibus posuere velit aliquet.",
    "Aenean lacinia bibendum nulla sed consectetur. Nulla vitae elit libero,",
    "a pharetra augue.",
    "",
    "SONUÇ VE İSTEM : Yukarıda arz ve izah olunan nedenlerle talebimizin",
    "kabulüne karar verilmesini saygıyla talep ederiz.",
]


def dilekce(hedef, damgali=False):
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

    sayfa.insert_text((380, y + 40), "DAVACI VEKİLİ", fontname="duz", fontsize=11)
    sayfa.insert_text((355, y + 60), AD, fontname="kalin", fontsize=11)
    sayfa.insert_text((60, y + 130), "EKLER:", fontname="kalin", fontsize=11)
    sayfa.insert_text((60, y + 150), "1- Vekaletname", fontname="duz", fontsize=11)

    if damgali:
        # Yalnızca görünüm: gerçek imza değil, damganın nasıl durduğunu gösterir.
        gecici = hedef.with_name("._damga.pdf")
        g, yy = damga.ciz(gecici, DAMGA_AD, UNVAN, TARIH)
        src = pymupdf.open(str(gecici))
        ust = y + 78
        sayfa.show_pdf_page(
            pymupdf.Rect(595 - 24 - g, ust, 595 - 24, ust + yy), src, 0)
        src.close()
        gecici.unlink(missing_ok=True)

    try:
        belge.subset_fonts()
    except Exception:
        pass
    belge.save(str(hedef), garbage=4, deflate=True, clean=True)
    belge.close()
    return hedef


def main():
    klasor = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "muhur" / "ornek"
    klasor.mkdir(parents=True, exist_ok=True)

    imzasiz = dilekce(klasor / "dilekce-ornegi.pdf", damgali=False)
    damgali = dilekce(klasor / "dilekce-ornegi-damgali.pdf", damgali=True)

    # README için damga yakın çekimi
    belge = pymupdf.open(damgali)
    sayfa = belge[0]
    kirp = pymupdf.Rect(240, 545, 585, 700)
    sayfa.get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=kirp).save(
        str(klasor.parent / "ekran" / "07-damga.png"))
    belge.close()

    print("üretildi:", imzasiz)
    print("üretildi:", damgali)
    print("üretildi:", klasor.parent / "ekran" / "07-damga.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
