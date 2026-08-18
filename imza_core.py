"""Nitelikli elektronik imza çekirdeği (TÜRKTRUST / AKİS).

AKİS kartına özgü dört uyumsuzluğu burada telafi ediyoruz:

1. Nesneler etiketle değil ID ile eşleştirilir. Etiket Türkçe karakter
   içerdiğinden Unicode normalizasyon farkı eşleşmeyi bozuyordu.
2. pyHanko'nun varsayılan CKA_SIGN filtresi kaldırılır; kart bu
   öznitelikle aramayı desteklemiyor.
3. Kart, RSA özel anahtarı için SIGN=False bildiriyor (açık anahtar
   yeteneklerini özel anahtara atamış). İmzalama yeteneği elle eklenir.
4. Kart birleşik SHA256_RSA_PKCS mekanizmasını tanımıyor, sadece ham
   RSA_PKCS var. Ham moda geçilir; özet yazılımda hesaplanır.

Ayrıca yazı tipi olarak birimi 1000 olan bir font seçilir: pyHanko
genişlik dizisini (/W) yazı tipinin kendi biriminde yazıyor, PDF ise
binde birim bekliyor. 2048 birimli fontlarda harfler 2,048 kat aralıklı
çıkıyor.
"""

import pkcs11
from pkcs11 import Attribute, ObjectClass
from pkcs11._pkcs11 import SignMixin
from pyhanko.pdf_utils.font.opentype import GlyphAccumulatorFactory
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.text import TextBoxStyle
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec, enumerate_sig_fields
from pyhanko.sign.pkcs11 import PKCS11Signer
from pyhanko.sign.signers.pdf_signer import PdfSigner
from pyhanko.stamp import TextStampStyle

# Bilinen PKCS#11 sürücüleri. Sırayla denenir, kart takılı olan ilki seçilir.
BILINEN_KUTUPHANELER = [
    "/usr/local/lib/libakisp11.dylib",  # AKİS — TÜBİTAK kartları (TÜRKTRUST, E-Güven, Kamu SM)
    "/usr/local/lib/libeTPkcs11.dylib",  # SafeNet eToken
    "/Library/Frameworks/eToken.framework/Versions/A/libeToken.dylib",
    "/usr/local/lib/libcvP11.dylib",  # Charismathics
    "/Library/OpenSC/lib/opensc-pkcs11.so",  # OpenSC
]


class KartYok(RuntimeError):
    """Takılı kart ya da uygun sürücü bulunamadı."""


def _surucu_tanisi(yollar):
    """Sürücü var ama kart okunamıyorsa sebebi anlaşılır biçimde açıklar.

    En sık sebep: sürücünün eski, yalnızca Intel derlenmiş sürümü. Apple
    Silicon'da çalışan Python böyle bir kütüphaneyi yükleyemiyor.
    """
    import platform
    import subprocess

    arm = platform.machine() == "arm64"
    for yol in yollar:
        try:
            mimari = subprocess.run(["lipo", "-archs", yol], capture_output=True,
                                    text=True, timeout=5).stdout.split()
        except Exception:
            mimari = []
        if arm and mimari and "arm64" not in mimari:
            return (
                "Kart sürücünüz eski: yalnızca Intel sürümü kurulu "
                f"({' '.join(mimari)}), bu Mac ise Apple Silicon.\n\n"
                "Sürücünün güncel sürümünü kart sağlayıcınızdan (TÜRKTRUST, "
                "E-Güven, Kamu SM, E-Tuğra) indirip kurun. Güncel AKİS "
                "sürümleri hem Intel hem Apple Silicon destekler.\n\n"
                f"Sürücü: {yol}"
            )

    return (
        "E-imza sürücüsü kurulu ama kart okunamadı.\n\n"
        "Sırayla bakın:\n"
        "  1. Token bu bilgisayara takılı mı?\n"
        "  2. Başka bir e-imza uygulaması açık mı (AKİA, UYAP, Adobe)? "
        "Kart aynı anda tek uygulamaya açılır.\n"
        "  3. Token'ı çıkarıp yeniden takmayı deneyin.\n\n"
        "Sürmezse kart-raporu.py çıktısını geliştiriciye iletin."
    )


def kutuphane_bul():
    """Kart takılı olan ilk PKCS#11 sürücüsünün yolunu döndürür."""
    import os

    denenen = []
    for yol in BILINEN_KUTUPHANELER:
        if not os.path.exists(yol):
            continue
        denenen.append(yol)
        try:
            if list(pkcs11.lib(yol).get_tokens()):
                return yol
        except Exception:
            continue
    if denenen:
        raise KartYok(_surucu_tanisi(denenen))
    raise KartYok(
        "E-imza sürücüsü bulunamadı.\n\n"
        "Kartınızın sürücüsünü (AKİS, SafeNet vb.) kurmanız gerekiyor."
    )


def token_bul(lib_yolu):
    """Takılı ilk kartın etiketini döndürür."""
    tokenlar = list(pkcs11.lib(lib_yolu).get_tokens())
    if not tokenlar:
        raise KartYok("Kart takılı değil.")
    return tokenlar[0].label


def imza_sertifikasi_bul(lib_yolu, token_etiketi):
    """Karttaki imzalama sertifikasını PIN'siz bulur.

    Bazı kartlarda iki sertifika olur: nitelikli imza ve kimlik doğrulama.
    İmzalama için olanı 'non_repudiation' anahtar kullanımından ayırt ederiz.

    (sertifika_nesnesi, CKA_ID) döndürür.
    """
    from asn1crypto import x509 as asn1_x509

    token = pkcs11.lib(lib_yolu).get_token(token_label=token_etiketi)
    adaylar = []
    with token.open() as oturum:  # login yok: sertifikalar açık nesnedir
        for nesne in oturum.get_objects(
            {Attribute.CLASS: ObjectClass.CERTIFICATE}
        ):
            try:
                ham = nesne[Attribute.VALUE]
                kimlik = nesne[Attribute.ID]
            except Exception:
                continue
            adaylar.append((asn1_x509.Certificate.load(ham), kimlik))

    if not adaylar:
        raise KartYok("Kartta sertifika bulunamadı.")

    def imzalama_mi(sertifika):
        try:
            kullanim = sertifika.key_usage_value
            return kullanim and "non_repudiation" in kullanim.native
        except Exception:
            return False

    for sertifika, kimlik in adaylar:
        if imzalama_mi(sertifika):
            return sertifika, kimlik
    return adaylar[0]  # ayırt edemezsek ilkini kullan

# unitsPerEm = 1000 olan bir yazı tipi şart (yukarıdaki nota bakınız).
FONT = "/System/Library/Fonts/Supplemental/STIXGeneral.otf"
PUNTO = 8

DAMGA_METNI = "NİTELİKLİ ELEKTRONİK İMZA\n%(ad)s · %(unvan)s\n%(ts)s"
ZAMAN_BICIMI = "%d.%m.%Y %H:%M:%S (UTC%z)"


class AkisSigner(PKCS11Signer):
    """AKİS kartının hatalı yetenek bayraklarını telafi eden imzalayıcı."""

    def _pull_signing_key_handle(self):
        handle = super()._pull_signing_key_handle()
        if not hasattr(handle, "sign"):
            cls = type(handle)
            handle.__class__ = type(cls.__name__, (cls, SignMixin), {})
        return handle


def _sayfa_kutusu(page):
    """MediaBox'ı miras zincirini takip ederek bulur."""
    node, adim = page, 0
    while node is not None and adim < 16:
        mb = node.get("/MediaBox")
        if mb is not None:
            return [float(x) for x in mb]
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
        adim += 1
    return [0.0, 0.0, 595.0, 842.0]


def belge_bilgisi(path):
    """(sayfa_sayısı, son sayfanın MediaBox'ı, mevcut imza alanı adları)."""
    with open(path, "rb") as f:
        reader = PdfFileReader(f)
        sayfa_sayisi = int(reader.root["/Pages"]["/Count"])
        page = reader.find_page_for_modification(sayfa_sayisi - 1)[0].get_object()
        kutu = _sayfa_kutusu(page)
        adlar = {name for name, _, _ in enumerate_sig_fields(reader)}
    return sayfa_sayisi, kutu, adlar


def mevcut_imzalar(path):
    """Belgedeki imzaları (alan adı, imzalayan, sertifika seri no) döndürür."""
    sonuc = []
    with open(path, "rb") as f:
        reader = PdfFileReader(f)
        for sig in reader.embedded_signatures:
            cert = sig.signer_cert
            sonuc.append(
                (
                    sig.field_name,
                    cert.subject.native.get("common_name", ""),
                    cert.serial_number,
                )
            )
    return sonuc


EK = "_imzalı"


def cikti_yolu(girdi):
    """belge.pdf -> belge_imzalı.pdf  (zaten ekliyse adı değiştirmez)."""
    from pathlib import Path

    girdi = Path(girdi)
    if girdi.stem.endswith(EK):
        return girdi
    return girdi.with_name(girdi.stem + EK + girdi.suffix)


def kendi_seri_no():
    """Karttaki imzalama sertifikasının seri numarası (PIN gerektirmez)."""
    lib = kutuphane_bul()
    token = token_bul(lib)
    sertifika, _ = imza_sertifikasi_bul(lib, token)
    return sertifika.serial_number


def sadece_ben_mi_imzaladim(path):
    """(imza_var_mi, hepsi_bana_mi_ait) döndürür."""
    imzalar = mevcut_imzalar(path)
    if not imzalar:
        return False, True
    try:
        benim = kendi_seri_no()
    except Exception:
        return True, False
    return True, all(seri == benim for _, _, seri in imzalar)


def imzasiz_haline_dondur(kaynak, hedef):
    """İmzalı PDF'ten imza öncesi hâli çıkarır.

    İmza, dosyanın sonuna eklenir; öncesi olduğu gibi durur. İlk %%EOF'a
    kadar keserek imzasız asla dönüyoruz. Sonucu doğrulamadan kabul etmiyoruz:
    açılabilmeli ve içinde hiç imza kalmamalı.
    """
    import re
    from pathlib import Path

    ham = Path(kaynak).read_bytes()
    yerler = [m.end() for m in re.finditer(rb"%%EOF", ham)]
    if len(yerler) < 2:
        raise ValueError("Bu dosyada imza öncesi sürüm bulunamadı.")

    aday = ham[: yerler[0]]
    Path(hedef).write_bytes(aday)

    with open(hedef, "rb") as f:
        okuyucu = PdfFileReader(f)
        if okuyucu.embedded_signatures:
            raise ValueError("İmzasız sürüm ayrıştırılamadı.")
        int(okuyucu.root["/Pages"]["/Count"])  # açılabildiğini doğrula
    return hedef


def imzala_yerine(girdi, pin, kutu=None, sayfa=0, onceki_imzayi_kaldir=False):
    """İmzalar ve imzasız orijinali sonuçla değiştirir.

    Önce gizli bir geçici dosyaya imzalar; ancak imzalama başarıyla
    biterse orijinali siler. Yarıda kalırsa orijinal olduğu gibi kalır.

    (ad, unvan, alan, hedef_yol) döndürür.
    """
    import os
    from pathlib import Path

    girdi = Path(girdi)
    hedef = cikti_yolu(girdi)
    gecici = girdi.with_name(f".{girdi.stem}.imzalaniyor.pdf")
    gecici_asil = girdi.with_name(f".{girdi.stem}.imzasiz.pdf")

    kaynak = girdi
    if onceki_imzayi_kaldir:
        imzasiz_haline_dondur(girdi, gecici_asil)
        kaynak = gecici_asil

    try:
        ad, unvan, alan = imzala(
            str(kaynak), str(gecici), pin, kutu=kutu, sayfa=sayfa
        )
        os.replace(gecici, hedef)
        if hedef != girdi and girdi.exists():
            girdi.unlink()
    finally:
        for artik in (gecici, gecici_asil):
            if artik.exists():
                artik.unlink()

    return ad, unvan, alan, hedef


def imza_blogu_bul(path, ad, genislik, yukseklik, kenar=24):
    """Belgede imzalayanın adını arayıp damgayı onun altına yerleştirir.

    Dilekçeler 'MÜŞTEKİ VEKİLİ / AV. AD SOYAD' gibi bir blokla biter; ıslak
    imza oraya atılır. Damgayı da oraya koymak hem alışkanlığa uyar hem de
    EKLER bölümü olan belgelerde eklerin arkasında kalmasını önler.

    Bulursa (sayfa, kutu), bulamazsa None döner.
    """
    import pymupdf

    aranan = " ".join(ad.split()).upper()
    belge = pymupdf.open(path)
    try:
        for dizin in range(len(belge) - 1, -1, -1):  # sondan başa
            sayfa = belge[dizin]
            Y = sayfa.rect.height
            bulgular = sayfa.search_for(aranan) or sayfa.search_for(aranan.title())
            if not bulgular:
                continue
            hedef = max(bulgular, key=lambda r: r.y1)  # en alttaki geçiş

            dolu = [pymupdf.Rect(b[:4]) for b in sayfa.get_text("blocks")]
            dolu += [pymupdf.Rect(c["rect"]) for c in sayfa.get_drawings()]

            x = min(max(hedef.x0 - 6, kenar), sayfa.rect.width - genislik - kenar)
            for bosluk in (8, 14, 20, 28):
                aday = pymupdf.Rect(x, hedef.y1 + bosluk,
                                    x + genislik, hedef.y1 + bosluk + yukseklik)
                if aday.y1 > Y - 12:
                    break
                if not any(aday.intersects(d) for d in dolu):
                    return dizin, (aday.x0, Y - aday.y1, aday.x1, Y - aday.y0)
    finally:
        belge.close()
    return None


def bos_alan_bul(path, genislik=None, yukseklik=None, kenar=30):
    """Damga için içeriğe çarpmayan bir yer bulur.

    Son sayfanın altından yukarı doğru, önce sağ sonra sol sütunu tarar.
    Dönen değer (sayfa_dizini, (x1, y1, x2, y2)) — PDF puntosu, sol-alt orijinli.
    Hiç boş yer yoksa sayfa sonuna yeni bir şerit açmak yerine sağ alta koyar.
    """
    import pymupdf

    if genislik is None or yukseklik is None:
        import damga

        g, y = damga.olcu()
        genislik = genislik or g
        yukseklik = yukseklik or y

    belge = pymupdf.open(path)
    dizin = len(belge) - 1
    sayfa = belge[dizin]
    G, Y = sayfa.rect.width, sayfa.rect.height

    # Sayfadaki dolu alanlar: metin blokları + çizimler + mevcut açıklamalar
    dolu = [pymupdf.Rect(b[:4]) for b in sayfa.get_text("blocks")]
    dolu += [pymupdf.Rect(c["rect"]) for c in sayfa.get_drawings()]

    def bos_mu(r):
        return not any(r.intersects(d) for d in dolu)

    # MuPDF koordinatı yukarıdan aşağı; alttan başlayıp yukarı tarıyoruz.
    ust_sinir = kenar
    y = Y - kenar - yukseklik
    while y >= ust_sinir:
        for x in (G - kenar - genislik, kenar):
            aday = pymupdf.Rect(x, y, x + genislik, y + yukseklik)
            if bos_mu(aday):
                belge.close()
                return dizin, (aday.x0, Y - aday.y1, aday.x1, Y - aday.y0)
        y -= 8

    belge.close()
    x = G - kenar - genislik
    return dizin, (x, kenar, x + genislik, kenar + yukseklik)


def onceki_damga_konumu(path):
    """Belgedeki mevcut imza damgasının yerini döndürür.

    Yeniden imzalarken damgayı aynı yere koymak için kullanılır; yoksa her
    seferinde bir öncekinin altına kayardı.
    """
    import pymupdf

    belge = pymupdf.open(path)
    try:
        for dizin in range(len(belge) - 1, -1, -1):
            sayfa = belge[dizin]
            Y = sayfa.rect.height
            for alan in sayfa.widgets():
                if alan.field_type != pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                    continue
                r = alan.rect
                if r.width < 5 or r.height < 5:   # görünmez imza alanı
                    continue
                return dizin, (r.x0, Y - r.y1, r.x1, Y - r.y0)
    finally:
        belge.close()
    return None


def konum_bul(path, ad=None, onceki_yeri_kullan=False):
    """Damga için en uygun yeri seçer.

    Sıra: (1) yeniden imzalıyorsak önceki damganın yeri, (2) ayarlardaki
    son konum, (3) belgedeki imza bloğu, (4) sayfadaki boş alan.

    ad verilmezse karttan okunur (PIN gerektirmez).
    """
    import damga

    a = damga.ayarlar()
    genislik, yukseklik = damga.olcu(a)

    if onceki_yeri_kullan:
        # Aynı imzayı tazeliyoruz: damga yerinden oynamasın.
        onceki = onceki_damga_konumu(path)
        if onceki:
            return onceki

    if a.get("son_konum") and a.get("son_sayfa") is not None:
        return int(a["son_sayfa"]), tuple(a["son_konum"])

    if ad is None:
        try:
            lib = kutuphane_bul()
            token = token_bul(lib)
            sertifika, _ = imza_sertifikasi_bul(lib, token)
            ad = sertifika.subject.native.get("common_name", "")
        except Exception:
            ad = ""

    if ad:
        sonuc = imza_blogu_bul(path, ad, genislik, yukseklik)
        if sonuc:
            return sonuc

    return bos_alan_bul(path, genislik, yukseklik)


def _alan_adi_sec(mevcut):
    n = 1
    while f"Imza{n}" in mevcut:
        n += 1
    return f"Imza{n}"


def imzala(infile, outfile, pin, kutu=None, sayfa=0):
    """PDF'i imzalar.

    kutu: (x1, y1, x2, y2) PDF punto cinsinden, sol-alt orijinli.
          None verilirse görünmez imza atılır.
    sayfa: 0 tabanlı sayfa dizini (görünür imza için).

    Sertifikanın sahibini (ad, unvan) döndürür.
    """
    _, _, mevcut_alanlar = belge_bilgisi(infile)
    alan = _alan_adi_sec(mevcut_alanlar)

    # Sürücü, kart ve sertifika karttan bulunur; hiçbiri sabit değildir.
    lib_yolu = kutuphane_bul()
    token_etiketi = token_bul(lib_yolu)
    _, obj_id = imza_sertifikasi_bul(lib_yolu, token_etiketi)

    token = pkcs11.lib(lib_yolu).get_token(token_label=token_etiketi)

    with token.open(user_pin=pin) as session:
        signer = AkisSigner(
            session, key_id=obj_id, cert_id=obj_id, use_raw_mechanism=True
        )
        signer.default_key_query_params = {
            Attribute.CLASS: ObjectClass.PRIVATE_KEY,
        }

        subject = signer.signing_cert.subject.native
        ad = subject.get("common_name", "")
        unvan = subject.get("title", "")

        meta = signers.PdfSignatureMetadata(field_name=alan)

        kwargs = {}
        gecici_damga = None
        if kutu is not None:
            from datetime import datetime
            import tempfile

            import damga
            from pyhanko.stamp import StaticStampStyle

            tarih = datetime.now().astimezone().strftime(
                "%d.%m.%Y %H:%M:%S (UTC%z)"
            )
            gecici_damga = tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False
            ).name
            damga.ciz(gecici_damga, ad, unvan, tarih)

            kwargs["new_field_spec"] = SigFieldSpec(
                sig_field_name=alan, on_page=sayfa, box=tuple(kutu)
            )
            # border_width varsayılanı 3'tür; damgayı kendimiz çizdiğimiz için
            # pyHanko'nun ayrıca çerçeve çizmesini istemiyoruz.
            kwargs["stamp_style"] = StaticStampStyle.from_pdf_file(
                gecici_damga, border_width=0
            )

        with open(infile, "rb") as inf:
            writer = IncrementalPdfFileWriter(inf)
            with open(outfile, "wb") as outf:
                PdfSigner(meta, signer=signer, **kwargs).sign_pdf(
                    writer,
                    output=outf,
                    appearance_text_params={"ad": ad, "unvan": unvan},
                )

    return ad, unvan, alan


# Kartı meşgul edebilecek bilinen uygulamalar (süreç adı, görünen ad)
KART_UYGULAMALARI = [
    ("Akia", "AKİA"),
    ("UHAPImza", "UHAPImza"),
    ("Adalet Eimza", "Adalet E-imza"),
    ("EDevletEImza", "E-Devlet E-İmza"),
    ("PTTKEPEImza", "PTT KEP E-İmza"),
    ("AdobeAcrobat", "Adobe Acrobat"),
    ("ekatip", "e-Katip"),
    ("UYAP", "UYAP"),
]


def karti_mesgul_edenler():
    """Şu anda açık olan ve kartı meşgul edebilecek uygulamaların adları."""
    import subprocess

    try:
        cikti = subprocess.run(["ps", "-Ao", "comm"], capture_output=True,
                               text=True, timeout=5).stdout
    except Exception:
        return []
    return [gorunen for surec, gorunen in KART_UYGULAMALARI if surec in cikti]


def hata_aciklamasi(hata):
    """Ham istisnayı kullanıcının anlayacağı bir açıklamaya çevirir.

    (başlık, öneri) döndürür. Öneri yalnızca gerçekten geçerliyse dolu olur —
    her hatada "başka uygulama açık olabilir" demek yanıltıcı oluyordu.
    """
    ad = type(hata).__name__
    metin = str(hata)
    dusuk = metin.lower()

    if "pinincorrect" in dusuk or "pin_incorrect" in dusuk:
        return ("PIN yanlış.",
                "Kartta sınırlı deneme hakkı vardır; dikkatli girin. "
                "Hak biterse PUK kodu gerekir.")

    if "pinlocked" in dusuk or "pin_locked" in dusuk:
        return ("Kart kilitli.",
                "PIN deneme hakkı tükenmiş. Kart sağlayıcınızın aracıyla "
                "PUK kodunu kullanarak açmanız gerekiyor.")

    if isinstance(hata, KartYok) or "kart" in dusuk and "bulunamadı" in dusuk:
        return (metin, "")

    if "mechanism" in dusuk:
        return ("Kart bu imzalama yöntemini desteklemiyor.",
                "Kartınız Mühür'ün geliştirildiği karttan farklı olabilir. "
                "kart-raporu.py çıktısını geliştiriciye iletin.")

    if "could not find private key" in dusuk or "certificate" in dusuk:
        return ("Kartta imzalama sertifikası bulunamadı.",
                "kart-raporu.py çıktısını geliştiriciye iletin.")

    acik = karti_mesgul_edenler()
    if acik:
        return (f"{ad}: {metin}",
                "Şu uygulamalar açık ve kartı meşgul ediyor olabilir: "
                + ", ".join(acik) + ". Kapatıp tekrar deneyin.")

    return (f"{ad}: {metin}", "")
