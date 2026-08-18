"""İmza damgasını PDF olarak çizer.

pyHanko'nun hazır damga stili tüm metne tek renk ve tek yazı tipi uygular.
Satır satır renk/kalınlık, logo ve ıslak imza istediğimiz için damgayı
burada kendimiz çizip imzaya hazır görünüm olarak veriyoruz.

Görünüm ~/Muhur/ayarlar.json ile kişiselleştirilir.
"""

import json
from pathlib import Path

import pymupdf

EV = Path.home() / "Muhur"
AYAR_DOSYASI = EV / "ayarlar.json"
LOGO_KLASORU = EV / "logolar"

VARSAYILAN = {
    # "monogram" | "yok" | logolar/ içindeki dosya adı | tam PNG yolu
    "logo": "monogram",
    "islak_imza": "",            # PNG yolu; boş bırakılırsa çizilmez
    "kanun_metni": True,
    "dil": "tr",                        # "tr" | "en" | "tr+en"
    "kanun_rengi": [0.65, 0.10, 0.10],
    "metin_rengi": [0.20, 0.20, 0.20],
    "monogram_rengi": [0.13, 0.17, 0.30],
    "logo_rengi": [0.13, 0.17, 0.30],   # SVG simgeler bu renge boyanır
    "monogram_harf_sayisi": 2,          # 2 = ad+soyad (varsayılan), 3 = orta ad da dahil
    "cerceve": False,
    "cerceve_rengi": [0.55, 0.55, 0.55],
    # Damganın sayfadaki son konumu (sol-alt köşe, punto). Sürükleyince güncellenir.
    "son_konum": None,
    "son_sayfa": None,
}

YAZI = "/System/Library/Fonts/Supplemental/Arial.ttf"
YAZI_KALIN = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

KANUN_TR = ("Bu belge 5070 sayılı Kanun gereğince",
            "güvenli elektronik imza ile imzalanmıştır.")

# Yabancı taraflı belgeler için. "qualified electronic signature" eIDAS
# terminolojisiyle aynı; karşı taraf ne olduğunu anlıyor.
KANUN_EN = ("This document has been signed with a qualified",
            "electronic signature under Turkish Law No. 5070.")

KANUN = KANUN_TR          # geriye dönük uyumluluk


def kanun_satirlari(a=None):
    """Ayardaki dile göre ibare satırlarını verir."""
    a = a or ayarlar()
    dil = str(a.get("dil", "tr")).lower()
    if dil == "en":
        return KANUN_EN
    if dil in ("tr+en", "en+tr", "iki", "both"):
        return KANUN_TR + KANUN_EN
    return KANUN_TR

# Ölçüler (punto) — logo/yazı dengesi bu değerlerle kuruldu
LOGO_BOY = 46
BOSLUK = 10
KENAR = 5
P_KANUN, P_AD, P_ALT, SATIR = 6.6, 12.0, 7.6, 8.4
AD_BOSLUK = 9      # kanun metni ile ad arasındaki nefes payı
IMZA_YUKSEKLIK = 34


def ayarlar():
    veri = dict(VARSAYILAN)
    if AYAR_DOSYASI.is_file():
        try:
            veri.update(json.loads(AYAR_DOSYASI.read_text(encoding="utf-8")))
        except Exception:
            pass  # bozuk ayar dosyası varsayılanı bozmasın
    return veri


def ayarlari_yaz(veri):
    AYAR_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    AYAR_DOSYASI.write_text(
        json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def konumu_hatirla(kutu, sayfa):
    """Sürükleyip bıraktığın yeri bir dahaki sefere hatırlar."""
    veri = ayarlar()
    veri["son_konum"] = [round(float(v), 1) for v in kutu]
    veri["son_sayfa"] = int(sayfa)
    ayarlari_yaz(veri)


def _logo_yolu(deger):
    """Ayardaki logo değerini gerçek dosya yoluna çevirir."""
    if not deger or deger in ("yok", "monogram"):
        return None
    yol = Path(deger).expanduser()
    if yol.is_file():
        return yol
    aday = LOGO_KLASORU / deger
    return aday if aday.is_file() else None


def logo_secenekleri():
    """Ayar arayüzünde gösterilecek liste."""
    secenekler = [("monogram", "Monogram (addan otomatik)"), ("yok", "Logosuz")]
    if LOGO_KLASORU.is_dir():
        dosyalar = sorted(LOGO_KLASORU.glob("*.png")) + sorted(LOGO_KLASORU.glob("*.svg"))
        for f in dosyalar:
            etiket = f.stem.replace("-", " ").replace("_", " ").capitalize()
            secenekler.append((f.name, etiket))
    return secenekler


def _svg_pdf(yol, renk):
    """SVG simgeyi verilen renge boyayıp PDF'e çevirir.

    Phosphor simgeleri fill="currentColor" kullanıyor; bağlam olmadığında
    siyaha düşüyor. Rengi doğrudan oraya yazıyoruz.
    """
    import tempfile

    r, g, b = [int(k * 255) for k in renk]
    ham = Path(yol).read_text(encoding="utf-8")
    ham = ham.replace("currentColor", f"#{r:02x}{g:02x}{b:02x}")
    gecici = Path(tempfile.gettempdir()) / "muhur-simge.svg"
    gecici.write_text(ham, encoding="utf-8")
    belge = pymupdf.open(str(gecici))
    pdf = belge.convert_to_pdf()
    belge.close()
    hedef = Path(tempfile.gettempdir()) / "muhur-simge.pdf"
    hedef.write_bytes(pdf)
    return hedef


def _bas_harfler(ad, azami=3):
    """Addaki her kelimenin baş harfi (en çok `azami` tane).

    "İlkderen Şevki Oker" -> "İŞO".  Tek kelimeyse ilk iki harf alınır.
    """
    parcalar = [k for k in ad.split() if k]
    if not parcalar:
        return "?"
    if len(parcalar) == 1:
        return parcalar[0][:2].upper()
    harfler = [k[0] for k in parcalar]
    if len(harfler) > azami:                    # ortadakileri kırp, ilk ve son kalsın
        harfler = harfler[:azami - 1] + [harfler[-1]]
    return "".join(harfler).upper()


def _metin_genisligi(ad="", unvan="", tarih="", a=None):
    """En uzun satırın gerçek genişliğini ölçer — damga içeriği kadar geniş olur."""
    a = a or ayarlar()
    duz = pymupdf.Font(fontfile=YAZI)
    kalin = pymupdf.Font(fontfile=YAZI_KALIN)

    genislikler = []
    if a["kanun_metni"]:
        genislikler += [duz.text_length(s, P_KANUN) for s in kanun_satirlari(a)]
    if ad:
        genislikler.append(kalin.text_length(ad, P_AD))
    if unvan or tarih:
        genislikler.append(duz.text_length(f"{unvan} · {tarih}", P_ALT))
    return max(genislikler) if genislikler else 180


def olcu(a=None, ad="", unvan="", tarih=""):
    """Damganın (genişlik, yükseklik) ölçüsünü içeriğe göre hesaplar."""
    a = a or ayarlar()
    # Ölçüyü önceden bilmek gerektiğinde (yer seçimi) temsilî metin kullanılır.
    metin_genislik = _metin_genisligi(
        ad or "ORNEK AD SOYAD",
        unvan or "AVUKAT",
        tarih or "01.01.2026 00:00:00 (UTC+0300)",
        a,
    )
    G = KENAR * 2 + (0 if a["logo"] == "yok" else LOGO_BOY + BOSLUK) + metin_genislik
    satir_sayisi = (len(kanun_satirlari(a)) if a["kanun_metni"] else 0) + 2
    metin_yuk = satir_sayisi * SATIR + P_AD + 6 + (AD_BOSLUK if a["kanun_metni"] else 0)
    imza = IMZA_YUKSEKLIK + 4 if _logo_yolu(a["islak_imza"]) else 0
    Y = max(LOGO_BOY + 12, metin_yuk + 12) + imza
    return round(G), round(Y)


def ciz(hedef_pdf, ad, unvan, tarih, a=None):
    """Damgayı tek sayfalık PDF olarak çizer; (genişlik, yükseklik) döndürür."""
    a = a or ayarlar()
    G, Y = olcu(a, ad, unvan, tarih)

    belge = pymupdf.open()
    sf = belge.new_page(width=G, height=Y)
    sf.insert_font(fontname="duz", fontfile=YAZI)
    sf.insert_font(fontname="kalin", fontfile=YAZI_KALIN)

    if a["cerceve"]:
        sf.draw_rect(pymupdf.Rect(0.5, 0.5, G - 0.5, Y - 0.5),
                     color=tuple(a["cerceve_rengi"]), width=0.7)

    imza_yolu = _logo_yolu(a["islak_imza"])
    imza_alani = IMZA_YUKSEKLIK + 4 if imza_yolu else 0

    # --- sol sütun: logo ya da monogram ---
    x_metin = KENAR
    if a["logo"] != "yok":
        ust = imza_alani + (Y - imza_alani - LOGO_BOY) / 2
        kutu = pymupdf.Rect(KENAR, ust, KENAR + LOGO_BOY, ust + LOGO_BOY)
        yol = _logo_yolu(a["logo"])
        if yol:
            try:
                if str(yol).lower().endswith(".svg"):
                    simge = pymupdf.open(str(_svg_pdf(yol, a["logo_rengi"])))
                    sf.show_pdf_page(kutu, simge, 0)
                    simge.close()
                else:
                    sf.insert_image(kutu, filename=str(yol), keep_proportion=True)
            except Exception:
                pass  # bozuk görsel damgayı engellemesin
        else:  # monogram
            renk = tuple(a["monogram_rengi"])
            m = kutu.width / 2
            sf.draw_circle((kutu.x0 + m, kutu.y0 + m), m - 1.5, color=renk, width=1.3)
            harf = _bas_harfler(ad, a.get("monogram_harf_sayisi", 3))
            # Harf sayısına göre puntoyu küçült, sonra ölçerek tam ortala.
            punto = {1: 17.0, 2: 15.0, 3: 12.0}.get(len(harf), 10.0)
            olcer = pymupdf.Font(fontfile=YAZI_KALIN)
            genislik = olcer.text_length(harf, punto)
            sf.insert_text((kutu.x0 + m - genislik / 2,
                            kutu.y0 + m + punto * 0.36),
                           harf, fontname="kalin", fontsize=punto, color=renk)
        x_metin = KENAR + LOGO_BOY + BOSLUK

    # --- ıslak imza (varsa üstte) ---
    if imza_yolu:
        try:
            sf.insert_image(
                pymupdf.Rect(x_metin, 3, x_metin + 165, 3 + IMZA_YUKSEKLIK),
                filename=str(imza_yolu), keep_proportion=True,
            )
        except Exception:
            pass

    # --- metin ---
    icerik_yuk = ((len(kanun_satirlari(a)) if a["kanun_metni"] else 0) * SATIR
                  + P_AD + SATIR + 6
                  + (AD_BOSLUK if a["kanun_metni"] else 0))
    y = imza_alani + ((Y - imza_alani) - icerik_yuk) / 2 + P_KANUN
    if a["kanun_metni"]:
        for satir in kanun_satirlari(a):
            sf.insert_text((x_metin, y), satir, fontname="duz",
                           fontsize=P_KANUN, color=tuple(a["kanun_rengi"]))
            y += SATIR
        y += AD_BOSLUK
    sf.insert_text((x_metin, y), ad, fontname="kalin", fontsize=P_AD, color=(0, 0, 0))
    y += P_AD + 4
    sf.insert_text((x_metin, y), f"{unvan} · {tarih}", fontname="duz",
                   fontsize=P_ALT, color=tuple(a["metin_rengi"]))

    # Yazı tiplerinin tamamını gömmek damgayı ~1,5 MB yapıyor; kullanılan
    # karakterlere indirince ~60 KB'a düşüyor. Her imzada tekrarlandığı için
    # dosya boyutunda büyük fark yaratıyor.
    try:
        belge.subset_fonts()
    except Exception:
        pass
    belge.save(str(hedef_pdf), garbage=4, deflate=True, clean=True)
    belge.close()
    return G, Y
