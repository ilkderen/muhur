#!/usr/bin/env python3
"""Mühür.app için uygulama simgesi (.icns) üretir.

Simgeyi paketin içinde hazır taşımak yerine kurulumda SVG'den üretiyoruz;
böylece dağıtım dosyası şişmiyor.

Kullanım: ikon-uret.py [hedef.icns]
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

KAYNAK_SIMGE = Path.home() / "Muhur" / "logolar" / "stamp.svg"
ZEMIN = (0.055, 0.078, 0.145)   # gece laciverti
BOYUTLAR = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
            (256, 1), (256, 2), (512, 1), (512, 2)]


def _simge_pdf(gecici):
    ham = KAYNAK_SIMGE.read_text(encoding="utf-8").replace("currentColor", "#ffffff")
    svg = gecici / "simge.svg"
    svg.write_text(ham, encoding="utf-8")
    belge = pymupdf.open(str(svg))
    pdf = belge.convert_to_pdf()
    belge.close()
    hedef = gecici / "simge.pdf"
    hedef.write_bytes(pdf)
    return hedef


def _kare(simge_pdf, boy=512):
    belge = pymupdf.open()
    sayfa = belge.new_page(width=boy, height=boy)
    pay = boy * 0.085                       # macOS ikonları kenardan içeride durur
    sayfa.draw_rect(pymupdf.Rect(pay, pay, boy - pay, boy - pay),
                    color=None, fill=ZEMIN, width=0, radius=0.225)
    src = pymupdf.open(str(simge_pdf))
    ic = boy * 0.30
    sayfa.show_pdf_page(pymupdf.Rect(ic, ic, boy - ic, boy - ic), src, 0)
    src.close()
    return belge, sayfa


def uret(hedef_icns):
    if not KAYNAK_SIMGE.is_file():
        raise FileNotFoundError(f"Simge bulunamadı: {KAYNAK_SIMGE}")

    with tempfile.TemporaryDirectory() as gecici_ad:
        gecici = Path(gecici_ad)
        simge = _simge_pdf(gecici)
        kume = gecici / "Muhur.iconset"
        kume.mkdir()

        for temel, kat in BOYUTLAR:
            boy = temel * kat
            belge, sayfa = _kare(simge)
            pix = sayfa.get_pixmap(matrix=pymupdf.Matrix(boy / 512, boy / 512),
                                   alpha=True)
            ad = f"icon_{temel}x{temel}{'@2x' if kat == 2 else ''}.png"
            pix.save(str(kume / ad))
            belge.close()

        subprocess.run(["iconutil", "-c", "icns", str(kume), "-o", str(hedef_icns)],
                       check=True)
    return hedef_icns


if __name__ == "__main__":
    hedef = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path.home() / "Applications" / "Mühür.app" / "Contents" / "Resources" / "applet.icns")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    print("üretildi:", uret(hedef))
