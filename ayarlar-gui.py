#!/usr/bin/env python3
"""Mühür ayarları — damga görünümünü canlı önizlemeyle düzenler.

Kullanım: ayarlar-gui.py
"""

import base64
import subprocess
import sys
import tempfile
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

import pymupdf

import damga
import imza_core

ORNEK_TARIH = "01.01.2026 09.30.00"


class AyarPenceresi:
    def __init__(self, kok):
        self.kok = kok
        self.ayar = damga.ayarlar()
        self.foto = None
        kok.title("Mühür — Ayarlar")
        kok.resizable(False, False)

        # Sertifikadan ad/unvan al; kart yoksa temsilî değer kullan.
        self.ad, self.unvan = self._kimlik()

        govde = ttk.Frame(kok, padding=16)
        govde.pack(fill="both", expand=True)

        self._secenekler(govde)
        self._onizleme(govde)
        self._dugmeler(kok)

        self.yenile()

    # ------------------------------------------------------------- yardımcı

    def _kimlik(self):
        try:
            lib = imza_core.kutuphane_bul()
            token = imza_core.token_bul(lib)
            sertifika, _ = imza_core.imza_sertifikasi_bul(lib, token)
            konu = sertifika.subject.native
            return konu.get("common_name", ""), konu.get("title", "")
        except Exception:
            return "AD SOYAD", "AVUKAT"

    def _renk_dugmesi(self, ust, anahtar, etiket, satir):
        ttk.Label(ust, text=etiket).grid(row=satir, column=0, sticky="w", pady=4)

        satir_cerceve = ttk.Frame(ust)
        satir_cerceve.grid(row=satir, column=1, sticky="w", padx=(8, 0))

        kutu = tk.Canvas(satir_cerceve, width=34, height=20, highlightthickness=1,
                         highlightbackground="#888", cursor="hand2")
        kutu.pack(side="left")
        kutu.bind("<Button-1>", lambda e, a=anahtar: self.renk_sec(a))

        # Renk kutusu tek başına tıklanabilir göründüğünü anlatmıyor; yanına
        # açık bir düğme koyuyoruz.
        ttk.Button(satir_cerceve, text="Değiştir…", width=10,
                   command=lambda a=anahtar: self.renk_sec(a)).pack(
                       side="left", padx=(6, 0))

        setattr(self, f"kutu_{anahtar}", kutu)

    def _renk_kodu(self, anahtar):
        r, g, b = self.ayar[anahtar]
        return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))

    # -------------------------------------------------------------- arayüz

    def _secenekler(self, govde):
        sol = ttk.LabelFrame(govde, text="Görünüm", padding=12)
        sol.grid(row=0, column=0, sticky="nw")

        satir = 0
        ttk.Label(sol, text="Logo").grid(row=satir, column=0, sticky="w", pady=4)
        self.logolar = damga.logo_secenekleri()
        self.logo_kutu = ttk.Combobox(
            sol, state="readonly", width=24,
            values=[etiket for _, etiket in self.logolar],
        )
        mevcut = [i for i, (deger, _) in enumerate(self.logolar)
                  if deger == self.ayar["logo"]]
        self.logo_kutu.current(mevcut[0] if mevcut else 0)
        self.logo_kutu.grid(row=satir, column=1, sticky="w", padx=(8, 0))
        self.logo_kutu.bind("<<ComboboxSelected>>", lambda e: self.yenile())
        satir += 1

        ttk.Label(sol, text="Islak imza").grid(row=satir, column=0, sticky="w", pady=4)
        cerceve = ttk.Frame(sol)
        cerceve.grid(row=satir, column=1, sticky="w", padx=(8, 0))
        self.imza_etiket = ttk.Label(cerceve, text="", width=16)
        self.imza_etiket.pack(side="left")
        ttk.Button(cerceve, text="Seç…", width=6,
                   command=self.imza_sec).pack(side="left", padx=2)
        ttk.Button(cerceve, text="Kaldır", width=7,
                   command=self.imza_kaldir).pack(side="left")
        satir += 1

        self.kanun_var = tk.BooleanVar(value=self.ayar["kanun_metni"])
        ttk.Checkbutton(sol, text="5070 sayılı Kanun ibaresi görünsün",
                        variable=self.kanun_var,
                        command=self.yenile).grid(row=satir, column=0, columnspan=2,
                                                  sticky="w", pady=(8, 2))
        satir += 1

        self.cerceve_var = tk.BooleanVar(value=self.ayar["cerceve"])
        ttk.Checkbutton(sol, text="Çerçeve çizilsin", variable=self.cerceve_var,
                        command=self.yenile).grid(row=satir, column=0, columnspan=2,
                                                  sticky="w", pady=2)
        satir += 1

        ttk.Separator(sol, orient="horizontal").grid(
            row=satir, column=0, columnspan=2, sticky="ew", pady=10)
        satir += 1

        for anahtar, etiket in (("kanun_rengi", "Kanun metni rengi"),
                                ("metin_rengi", "Unvan/tarih rengi"),
                                ("logo_rengi", "Logo rengi"),
                                ("monogram_rengi", "Monogram rengi")):
            self._renk_dugmesi(sol, anahtar, etiket, satir)
            satir += 1

    def _onizleme(self, govde):
        sag = ttk.LabelFrame(govde, text="Önizleme", padding=12)
        sag.grid(row=0, column=1, sticky="n", padx=(16, 0))
        self.tuval = tk.Canvas(sag, width=460, height=170,
                               background="white", highlightthickness=1,
                               highlightbackground="#ccc")
        self.tuval.pack()
        self.olcu_etiket = ttk.Label(sag, text="", foreground="#666")
        self.olcu_etiket.pack(anchor="w", pady=(6, 0))

    def _dugmeler(self, kok):
        serit = ttk.Frame(kok, padding=(16, 0, 16, 14))
        serit.pack(fill="x")
        ttk.Button(serit, text="Kapat", command=kok.destroy).pack(side="right")
        ttk.Button(serit, text="Kaydet", command=self.kaydet).pack(
            side="right", padx=6)
        ttk.Button(serit, text="Logo klasörünü aç",
                   command=self.klasor_ac).pack(side="left")

    # -------------------------------------------------------------- eylemler

    def klasor_ac(self):
        damga.LOGO_KLASORU.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(damga.LOGO_KLASORU)], check=False)

    def renk_sec(self, anahtar):
        secim = colorchooser.askcolor(color=self._renk_kodu(anahtar),
                                      parent=self.kok)
        if secim and secim[0]:
            self.ayar[anahtar] = [round(k / 255, 3) for k in secim[0]]
            self.yenile()

    def imza_sec(self):
        yol = filedialog.askopenfilename(
            title="Islak imza görseli", filetypes=[("PNG", "*.png")])
        if yol:
            self.ayar["islak_imza"] = yol
            self.yenile()

    def imza_kaldir(self):
        self.ayar["islak_imza"] = ""
        self.yenile()

    def _topla(self):
        """Arayüzdeki seçimleri ayar sözlüğüne yazar."""
        self.ayar["logo"] = self.logolar[self.logo_kutu.current()][0]
        self.ayar["kanun_metni"] = bool(self.kanun_var.get())
        self.ayar["cerceve"] = bool(self.cerceve_var.get())
        return self.ayar

    def yenile(self):
        a = self._topla()

        for anahtar in ("kanun_rengi", "metin_rengi", "logo_rengi", "monogram_rengi"):
            getattr(self, f"kutu_{anahtar}").configure(
                background=self._renk_kodu(anahtar))

        imza = a["islak_imza"]
        self.imza_etiket.configure(
            text=Path(imza).name if imza else "yok")

        gecici = Path(tempfile.gettempdir()) / "muhur-onizleme.pdf"
        try:
            g, y = damga.ciz(gecici, self.ad, self.unvan, ORNEK_TARIH, a)
        except Exception as hata:
            self.olcu_etiket.configure(text=f"önizleme hatası: {hata}")
            return

        belge = pymupdf.open(gecici)
        olcek = min(440 / g, 150 / y, 3.0)
        pix = belge[0].get_pixmap(matrix=pymupdf.Matrix(olcek, olcek))
        belge.close()

        self.foto = tk.PhotoImage(data=base64.b64encode(pix.tobytes("png")))
        self.tuval.delete("all")
        self.tuval.create_image(230, 85, image=self.foto)
        self.olcu_etiket.configure(text=f"damga ölçüsü: {g} × {y} punto")

    def kaydet(self):
        damga.ayarlari_yaz(self._topla())
        messagebox.showinfo(
            "Mühür", "Ayarlar kaydedildi.\n\nBundan sonraki imzalarda "
            "bu görünüm kullanılacak.")


def main():
    kok = tk.Tk()
    AyarPenceresi(kok)
    kok.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
