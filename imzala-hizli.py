#!/usr/bin/env python3
"""Arayüzsüz imzalama: PIN sor, damgayı boş alana koy, imzala.

Belgeyi göstermez — okumayı Preview'da yaparsın. Sadece macOS'un kendi
parola penceresi çıkar.

Kullanım: imzala-hizli.py belge.pdf
"""

import subprocess
import sys
from pathlib import Path

import imza_core

UYGULAMA = "Mühür"

# Uygulamanın kendi simgesi; bulunamazsa macOS'un genel simgesine düşülür.
_SIMGE_YOLU = Path.home() / "Applications" / "Mühür.app" / "Contents" / "Resources" / "applet.icns"


def _simge(varsayilan="note"):
    if _SIMGE_YOLU.is_file():
        return f'POSIX file "{_SIMGE_YOLU}"'
    return varsayilan


def _osascript(satir):
    return subprocess.run(
        ["osascript", "-e", satir], capture_output=True, text=True
    )


def pin_sor(dosya_adi):
    """macOS parola penceresiyle PIN ister. İptal edilirse None döner.

    PIN yalnızca bu sürecin belleğinde kalır: komut satırına da,
    kabuk değişkenine de yazılmaz.
    """
    betik = (
        f'display dialog "{dosya_adi} belgesi elektronik imza ile '
        f'imzalanacak.\n\nE-imza PIN kodunuz:" '
        'default answer "" with hidden answer '
        f'with title "{UYGULAMA}" '
        'buttons {"İptal", "İmzala"} default button "İmzala" '
        f'with icon {_simge()}'
    )
    sonuc = _osascript(betik)
    if sonuc.returncode != 0:
        return None
    isaret = "text returned:"
    cikti = sonuc.stdout.strip()
    yer = cikti.find(isaret)
    return cikti[yer + len(isaret):] if yer >= 0 else None


def bildir(baslik, mesaj, hata=False):
    simge = "stop" if hata else _simge()
    _osascript(
        f'display dialog "{mesaj}" with title "{baslik}" '
        f'buttons {{"Tamam"}} default button "Tamam" with icon {simge}'
    )


def main():
    if len(sys.argv) < 2:
        bildir(UYGULAMA, "İmzalanacak PDF belirtilmedi.", hata=True)
        return 1

    girdi = Path(sys.argv[1]).expanduser()
    if not girdi.is_file():
        bildir(UYGULAMA, f"Dosya bulunamadı:\n{girdi}", hata=True)
        return 1

    # Belge zaten imzalıysa uyar
    try:
        onceki = imza_core.mevcut_imzalar(girdi)
    except Exception:
        onceki = []
    kaldir = False
    if onceki:
        kim = ", ".join(ad for _, ad, _ in onceki)
        try:
            _, hepsi_benim = imza_core.sadece_ben_mi_imzaladim(girdi)
        except Exception:
            hepsi_benim = False

        if hepsi_benim:
            # Kendi imzam: ikinci bir imza biriktirmek yerine tazelemeyi öner.
            sonuc = _osascript(
                f'display dialog "Bu belgede zaten sizin imzanız var.\n\n'
                'Önceki imzayı kaldırıp yeniden mi imzalayalım, yoksa '
                'ikinci imza olarak mı eklensin?" '
                f'with title "{UYGULAMA}" '
                'buttons {"Vazgeç", "İkinci imza ekle", "Yeniden imzala"} '
                f'default button "Yeniden imzala" with icon {_simge()}'
            )
            if sonuc.returncode != 0 or "Vazgeç" in sonuc.stdout:
                return 0
            kaldir = "Yeniden" in sonuc.stdout
        else:
            # Başkasının imzası var: geri almak onu da siler, o yüzden sadece ekleyebiliriz.
            sonuc = _osascript(
                f'display dialog "Bu belgede başkasının imzası var:\n{kim}\n\n'
                'Önceki imza korunacak, sizinki ikinci imza olarak eklenecek." '
                f'with title "{UYGULAMA}" buttons {{"Vazgeç", "Devam"}} '
                f'default button "Devam" with icon {_simge("caution")}'
            )
            if sonuc.returncode != 0 or "Devam" not in sonuc.stdout:
                return 0

    pin = pin_sor(girdi.name)
    if not pin:
        return 0

    try:
        sayfa, kutu = imza_core.konum_bul(girdi, onceki_yeri_kullan=kaldir)
        ad, unvan, alan, cikti = imza_core.imzala_yerine(
            girdi, pin, kutu=kutu, sayfa=sayfa, onceki_imzayi_kaldir=kaldir
        )
    except Exception as hata:
        baslik, oneri = imza_core.hata_aciklamasi(hata)
        mesaj = f"İmzalanamadı.\n\n{baslik}"
        if oneri:
            mesaj += f"\n\n{oneri}"
        bildir(UYGULAMA, mesaj, hata=True)
        return 1

    sonuc = _osascript(
        f'display dialog "{ad} ({unvan}) adına imzalandı.\n\n'
        f'Dosya: {cikti.name}\nSayfa: {sayfa + 1}" '
        f'with title "{UYGULAMA}" buttons {{"Tamam", "Finder\'da Göster"}} '
        f'default button "Tamam" with icon {_simge()}'
    )
    if "Finder" in sonuc.stdout:
        subprocess.run(["open", "-R", str(cikti)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
