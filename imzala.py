#!/usr/bin/env python3
"""Komut satırından PDF imzalama.

Kart, sertifika ve sürücü otomatik bulunur — hiçbir şey elle tanımlanmaz.

Kullanım:
    imzala.py belge.pdf              # damgayı boş alana koyar
    imzala.py belge.pdf --gorunmez   # damgasız (görünmez imza)
"""

import argparse
import getpass
import sys
from pathlib import Path

import imza_core


def main() -> int:
    ap = argparse.ArgumentParser(description="PDF'i e-imza ile imzalar.")
    ap.add_argument("belge", help="imzalanacak PDF")
    ap.add_argument(
        "--gorunmez",
        action="store_true",
        help="damga koymadan imzala (görünmez imza)",
    )
    args = ap.parse_args()

    girdi = Path(args.belge).expanduser()
    if not girdi.is_file():
        print(f"Dosya bulunamadı: {girdi}")
        return 1

    try:
        lib = imza_core.kutuphane_bul()
        token = imza_core.token_bul(lib)
        sertifika, _ = imza_core.imza_sertifikasi_bul(lib, token)
    except imza_core.KartYok as hata:
        print(hata)
        return 1

    konu = sertifika.subject.native
    print(f"Kart      : {token}")
    print(f"Sertifika : {konu.get('common_name')} ({konu.get('title')})")

    pin = getpass.getpass("PIN: ")

    if args.gorunmez:
        kutu, sayfa = None, 0
    else:
        sayfa, kutu = imza_core.konum_bul(girdi)

    try:
        ad, unvan, alan, cikti = imza_core.imzala_yerine(
            girdi, pin, kutu=kutu, sayfa=sayfa
        )
    except Exception as hata:
        print(f"\nİmzalama başarısız: {type(hata).__name__}: {hata}")
        return 1

    print(f"\nİmza alanı: {alan}")
    print(f"İmzalandı : {cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
