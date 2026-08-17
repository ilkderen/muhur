#!/usr/bin/env python3
"""Mühür — belgeyi göster, imza yerini seç, imzala.

Kullanım:
    imzala-gui.py belge.pdf
    imzala-gui.py            (dosya seçme penceresi açılır)
"""

import base64
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pymupdf

import damga
import imza_core

# Sayfanın ekrandaki genişliği (nokta). Yakınlaştırma bunu ölçekler.
TEMEL_GENISLIK = 760
YAKINLASTIRMALAR = (0.75, 1.0, 1.25, 1.5, 2.0)

# Kaydırma hızı — büyütünce trackpad daha çok kaydırır
KAYDIRMA_HIZI = 1
TEKERLEK_ADIMI = 60

# İmza kutusu için makul alt sınır (punto)
MIN_GENISLIK = 110
MIN_YUKSEKLIK = 34


class ImzaPenceresi:
    def __init__(self, kok, pdf_yolu):
        self.kok = kok
        self.pdf_yolu = Path(pdf_yolu)
        self.belge = pymupdf.open(self.pdf_yolu)
        self.sayfa_no = 0
        self.olcek = 1.0
        self.yakin = 1
        self.foto = None
        self.secim = None
        self.secim_kutu = None
        self.baslangic = None

        kok.title(f"Mühür — {self.pdf_yolu.name}")

        self._ust_serit()
        self._tuval()
        self._alt_serit()

        self.sayfayi_ciz()
        self._imza_uyarisi()

    # ---------------------------------------------------------------- arayüz

    def _ust_serit(self):
        serit = ttk.Frame(self.kok, padding=(10, 8))
        serit.pack(fill="x")

        self.geri = ttk.Button(serit, text="‹", width=3, command=self.onceki)
        self.geri.pack(side="left")
        self.sayfa_etiketi = ttk.Label(serit, text="", width=12, anchor="center")
        self.sayfa_etiketi.pack(side="left", padx=4)
        self.ileri = ttk.Button(serit, text="›", width=3, command=self.sonraki)
        self.ileri.pack(side="left")

        ttk.Separator(serit, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Button(serit, text="−", width=3,
                   command=lambda: self.yakinlastir(-1)).pack(side="left")
        self.yakin_etiketi = ttk.Label(serit, text="", width=6, anchor="center")
        self.yakin_etiketi.pack(side="left")
        ttk.Button(serit, text="+", width=3,
                   command=lambda: self.yakinlastir(1)).pack(side="left")

        self.imzala_dugmesi = ttk.Button(
            serit, text="İmzala", command=self.imzala, state="disabled")
        self.imzala_dugmesi.pack(side="right")
        self.temizle_dugmesi = ttk.Button(
            serit, text="Seçimi temizle", command=self.secimi_temizle,
            state="disabled")
        self.temizle_dugmesi.pack(side="right", padx=6)
        ttk.Button(serit, text="Ayarlar…", command=self.ayarlari_ac).pack(
            side="right", padx=(0, 12))

    def _tuval(self):
        cerceve = ttk.Frame(self.kok)
        cerceve.pack(fill="both", expand=True, padx=10)

        self.tuval = tk.Canvas(cerceve, background="#3a3a3a",
                               highlightthickness=0, cursor="crosshair")
        self.kaydirma = ttk.Scrollbar(cerceve, orient="vertical",
                                      command=self.tuval.yview)
        self.tuval.configure(yscrollcommand=self.kaydirma.set)
        self.kaydirma.pack(side="right", fill="y")
        self.tuval.pack(side="left")

        self.tuval.bind("<Button-1>", self.fare_bas)
        self.tuval.bind("<B1-Motion>", self.fare_surukle)
        self.tuval.bind("<ButtonRelease-1>", self.fare_birak)
        # Kaydırma. İki ayrı olay var:
        #   <MouseWheel>     : gerçek fare tekerleği
        #   <TouchpadScroll> : trackpad'de iki parmak (Tk 9 ile geldi;
        #                      trackpad MouseWheel üretmiyor)
        # macOS'ta olay imlecin altındaki değil odaktaki pencereye gittiği
        # için tuvale değil pencerenin tamamına bağlıyoruz.
        self.tuval.configure(yscrollincrement=1)   # "units" = 1 piksel
        self.kok.bind_all("<MouseWheel>", self.tekerlek)
        try:
            self.kok.bind_all("<TouchpadScroll>", self.dokunmatik)
        except tk.TclError:
            pass  # eski Tk sürümlerinde bu olay yok
        self.tuval.focus_set()
        self.kok.bind("<Prior>", lambda e: self.onceki())
        self.kok.bind("<Next>", lambda e: self.sonraki())
        self.kok.bind("<Down>", lambda e: self.tuval.yview_scroll(3, "units"))
        self.kok.bind("<Up>", lambda e: self.tuval.yview_scroll(-3, "units"))

    def _alt_serit(self):
        serit = ttk.Frame(self.kok, padding=(10, 8))
        serit.pack(fill="x")
        self.durum = ttk.Label(
            serit, text="Dikdörtgen çizin; bırakınca PIN sorulur.")
        self.durum.pack(side="left")

    # ------------------------------------------------------------- sayfalama

    def _azami_yukseklik(self):
        return max(360, self.kok.winfo_screenheight() - 280)

    def sayfayi_ciz(self, kaydirma_ust=True):
        sayfa = self.belge[self.sayfa_no]
        hedef = TEMEL_GENISLIK * YAKINLASTIRMALAR[self.yakin]
        self.olcek = hedef / sayfa.rect.width
        pix = sayfa.get_pixmap(matrix=pymupdf.Matrix(self.olcek, self.olcek))
        self.foto = tk.PhotoImage(data=base64.b64encode(pix.tobytes("png")))

        self.tuval.delete("all")
        self.secim = None
        self.tuval.create_image(0, 0, anchor="nw", image=self.foto)
        self.tuval.configure(scrollregion=(0, 0, pix.width, pix.height))
        # Tuvali görüntüye tam oturt — sağda gri boşluk kalmasın.
        self.tuval.configure(width=pix.width,
                             height=min(pix.height, self._azami_yukseklik()))
        if kaydirma_ust:
            self.tuval.yview_moveto(0)

        self.sayfa_etiketi.configure(
            text=f"{self.sayfa_no + 1} / {len(self.belge)}")
        self.yakin_etiketi.configure(
            text=f"%{round(YAKINLASTIRMALAR[self.yakin] * 100)}")
        self.geri.configure(state="normal" if self.sayfa_no > 0 else "disabled")
        self.ileri.configure(
            state="normal" if self.sayfa_no < len(self.belge) - 1 else "disabled")
        self.secimi_temizle()

    def yakinlastir(self, yon):
        yeni = min(max(self.yakin + yon, 0), len(YAKINLASTIRMALAR) - 1)
        if yeni != self.yakin:
            self.yakin = yeni
            self.sayfayi_ciz(kaydirma_ust=False)

    def onceki(self):
        if self.sayfa_no > 0:
            self.sayfa_no -= 1
            self.sayfayi_ciz()
            self.tuval.yview_moveto(1)   # önceki sayfanın altından devam et

    def sonraki(self):
        if self.sayfa_no < len(self.belge) - 1:
            self.sayfa_no += 1
            self.sayfayi_ciz()

    def _kaydir(self, piksel):
        """Dikey kaydırma; sayfa sınırına gelince sayfa değiştirir."""
        if not piksel:
            return "break"
        ust, alt = self.tuval.yview()

        if piksel > 0 and alt >= 0.999:
            if self.sayfa_no < len(self.belge) - 1:
                self.sonraki()
            return "break"
        if piksel < 0 and ust <= 0.001:
            if self.sayfa_no > 0:
                self.onceki()
            return "break"

        self.tuval.yview_scroll(int(piksel), "units")
        return "break"

    def tekerlek(self, olay):
        """Gerçek fare tekerleği."""
        return self._kaydir(TEKERLEK_ADIMI if olay.delta > 0 else -TEKERLEK_ADIMI)

    def dokunmatik(self, olay):
        """Trackpad kaydırması.

        delta 32 bitlik bir değer: DÜŞÜK 16 bit dikey, yüksek 16 bit yatay
        (ikisi de işaretli). Ölçerek doğrulandı: aşağı kaydırma pozitif,
        yukarı negatif dikey değer üretiyor.
        """
        ham = int(olay.delta)
        dy = ham & 0xFFFF
        if dy >= 0x8000:
            dy -= 0x10000
        return self._kaydir(dy * KAYDIRMA_HIZI)

    def ayarlari_ac(self):
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().with_name("ayarlar-gui.py"))],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ------------------------------------------------------------ kutu çizme

    def fare_bas(self, olay):
        self.baslangic = (self.tuval.canvasx(olay.x), self.tuval.canvasy(olay.y))
        if self.secim:
            self.tuval.delete(self.secim)
        self.secim = self.tuval.create_rectangle(
            *self.baslangic, *self.baslangic,
            outline="#0a84ff", width=2)   # dolgusuz: altındaki metin kapanmasın

    def fare_surukle(self, olay):
        if not self.baslangic:
            return
        x, y = self.tuval.canvasx(olay.x), self.tuval.canvasy(olay.y)
        self.tuval.coords(self.secim, *self.baslangic, x, y)

    def fare_birak(self, olay):
        if not self.baslangic:
            return
        x1, y1 = self.baslangic
        x2, y2 = self.tuval.canvasx(olay.x), self.tuval.canvasy(olay.y)
        self.baslangic = None
        kutu = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

        gen = (kutu[2] - kutu[0]) / self.olcek
        yuk = (kutu[3] - kutu[1]) / self.olcek
        if gen < MIN_GENISLIK or yuk < MIN_YUKSEKLIK:
            self.durum.configure(
                text=f"Kutu çok küçük ({gen:.0f}×{yuk:.0f} punto). "
                     f"En az {MIN_GENISLIK}×{MIN_YUKSEKLIK} olmalı.")
            self.tuval.delete(self.secim)
            self.secim = self.secim_kutu = None
            self.imzala_dugmesi.configure(state="disabled")
            self.temizle_dugmesi.configure(state="disabled")
            return

        self.secim_kutu = kutu
        self.tuval.coords(self.secim, *kutu)
        self.durum.configure(
            text=f"İmza kutusu: {gen:.0f}×{yuk:.0f} punto, sayfa {self.sayfa_no + 1}.")
        self.imzala_dugmesi.configure(state="normal")
        self.temizle_dugmesi.configure(state="normal")

        # Kutuyu bırakır bırakmaz imzalamaya geç; PIN penceresi zaten onay yerine
        # geçiyor, ayrıca düğmeye basmaya gerek yok. (Vazgeçilirse kutu durur,
        # "İmzala" düğmesiyle yeniden denenebilir.)
        self.kok.after(60, self.imzala)

    def secimi_temizle(self):
        if self.secim:
            self.tuval.delete(self.secim)
        self.secim = self.secim_kutu = None
        self.imzala_dugmesi.configure(state="disabled")
        self.temizle_dugmesi.configure(state="disabled")

    def pdf_kutusu(self):
        cx1, cy1, cx2, cy2 = self.secim_kutu
        yukseklik = self.belge[self.sayfa_no].rect.height
        return (cx1 / self.olcek, yukseklik - cy2 / self.olcek,
                cx2 / self.olcek, yukseklik - cy1 / self.olcek)

    # ---------------------------------------------------------------- imzalama

    def _imza_uyarisi(self):
        try:
            imzalar = imza_core.mevcut_imzalar(self.pdf_yolu)
        except Exception:
            return
        if imzalar:
            kim = ", ".join(f"{ad} ({alan})" for alan, ad, _ in imzalar)
            self.durum.configure(text=f"Bu belgede zaten imza var: {kim}")

    def pin_sor(self):
        pencere = tk.Toplevel(self.kok)
        pencere.title("PIN")
        pencere.transient(self.kok)
        pencere.resizable(False, False)
        pencere.grab_set()

        cerceve = ttk.Frame(pencere, padding=20)
        cerceve.pack()
        ttk.Label(cerceve, text="E-imza PIN kodunuz:").pack(anchor="w")

        deger = tk.StringVar()
        giris = ttk.Entry(cerceve, show="•", textvariable=deger, width=24)
        giris.pack(pady=(8, 4))
        giris.focus_set()

        ttk.Label(cerceve, text="Kartta sınırlı deneme hakkı vardır.",
                  foreground="#a00").pack(anchor="w", pady=(0, 10))

        sonuc = {"pin": None}

        def tamam():
            sonuc["pin"] = deger.get()
            pencere.destroy()

        dugmeler = ttk.Frame(cerceve)
        dugmeler.pack(fill="x")
        ttk.Button(dugmeler, text="İptal", command=pencere.destroy).pack(
            side="right", padx=(6, 0))
        ttk.Button(dugmeler, text="İmzala", command=tamam).pack(side="right")
        giris.bind("<Return>", lambda e: tamam())

        self.kok.wait_window(pencere)
        return sonuc["pin"]

    def imzala(self):
        if not self.secim_kutu:
            return
        kutu = self.pdf_kutusu()
        pin = self.pin_sor()
        if not pin:
            return

        self.durum.configure(text="İmzalanıyor, karta erişiliyor…")
        self.imzala_dugmesi.configure(state="disabled")
        self.kok.update_idletasks()

        try:
            ad, unvan, alan, cikti = imza_core.imzala_yerine(
                self.pdf_yolu, pin, kutu=kutu, sayfa=self.sayfa_no)
        except Exception as hata:
            self.durum.configure(text="İmzalama başarısız.")
            self.imzala_dugmesi.configure(state="normal")
            messagebox.showerror(
                "Mühür",
                f"{type(hata).__name__}\n\n{hata}\n\n"
                "PIN yanlışsa kartta deneme hakkı azalır. Başka bir e-imza "
                "uygulaması açıksa kartı meşgul ediyor olabilir.")
            return

        damga.konumu_hatirla(kutu, self.sayfa_no)
        self.pdf_yolu = cikti
        self.kok.title(f"Mühür — {cikti.name}")
        self.durum.configure(text=f"İmzalandı: {cikti.name}")
        if messagebox.askyesno(
                "Mühür",
                f"{ad} ({unvan}) adına imzalandı.\n\n"
                f"Alan: {alan}\nDosya: {cikti.name}\n\nFinder'da göstereyim mi?"):
            subprocess.run(["open", "-R", str(cikti)], check=False)


def main():
    if len(sys.argv) > 1:
        yol = sys.argv[1]
    else:
        kok = tk.Tk()
        kok.withdraw()
        yol = filedialog.askopenfilename(
            title="İmzalanacak PDF", filetypes=[("PDF", "*.pdf")])
        kok.destroy()
        if not yol:
            return 0

    kok = tk.Tk()
    try:
        ImzaPenceresi(kok, yol)
    except Exception as hata:
        messagebox.showerror("Mühür", f"{type(hata).__name__}: {hata}")
        return 1
    kok.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
