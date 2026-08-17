#!/bin/zsh
# Mühür — kurulum
#
# Kullanım: Terminal'de çalıştırın. Tek satırlık kurulum için bkz. README.
#
# Yaptıkları:
#   1. Homebrew ve Python 3.13'ü (yoksa) kurar
#   2. ~/Muhur klasörünü ve yalıtılmış Python ortamını oluşturur
#   3. Finder'a "Mühürle" hızlı eylemini ekler
#   4. E-imza kartınızı bulup kurulumu doğrular
#
# Sisteminizdeki hiçbir şeyi değiştirmez; her şey ~/Muhur içinde kalır.

set -e

KAYNAK="${0:A:h}"
HEDEF="$HOME/Muhur"
YESIL='\033[0;32m'; SARI='\033[0;33m'; KIRMIZI='\033[0;31m'; BITIR='\033[0m'

basari() { print "${YESIL}✓${BITIR} $1" }
uyari()  { print "${SARI}!${BITIR} $1" }
hata()   { print "${KIRMIZI}✗${BITIR} $1"; exit 1 }
baslik() { print "\n$1" }

print "Mühür kurulumu"
print "──────────────"

# ---------------------------------------------------------------- ön kontrol
[[ "$(uname)" == "Darwin" ]] || hata "Bu kurulum yalnızca macOS içindir."

baslik "Homebrew kontrol ediliyor…"
if ! command -v brew >/dev/null 2>&1; then
	uyari "Homebrew kurulu değil. Kuruluyor (parolanız istenebilir)…"
	/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
	for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
		[[ -x "$p" ]] && eval "$($p shellenv)"
	done
fi
command -v brew >/dev/null 2>&1 || hata "Homebrew kurulamadı."
basari "Homebrew hazır"

baslik "Python kuruluyor…"
brew list --formula 2>/dev/null | grep -qx "python@3.13" || brew install python@3.13
brew list --formula 2>/dev/null | grep -qx "python-tk@3.13" || brew install python-tk@3.13
PYTHON="$(brew --prefix)/bin/python3.13"
[[ -x "$PYTHON" ]] || hata "Python 3.13 bulunamadı."
basari "Python hazır ($($PYTHON --version))"

# --------------------------------------------------------------------- kopya
baslik "Dosyalar yerleştiriliyor…"
mkdir -p "$HEDEF"
for f in imza_core.py imzala.py imzala-hizli.py imzala-gui.py damga.py ayarlar-gui.py ornek-uret.py kart-raporu.py ikon-uret.py; do
	[[ -f "$KAYNAK/$f" ]] || hata "Kurulum dosyası eksik: $f"
	cp "$KAYNAK/$f" "$HEDEF/"
done
if [[ -d "$KAYNAK/logolar" ]]; then
	mkdir -p "$HEDEF/logolar"
	cp "$KAYNAK/logolar/"* "$HEDEF/logolar/" 2>/dev/null || true
fi
basari "Dosyalar $HEDEF içine kopyalandı"

baslik "Python ortamı hazırlanıyor (birkaç dakika sürebilir)…"
[[ -d "$HEDEF/venv" ]] || "$PYTHON" -m venv "$HEDEF/venv"
"$HEDEF/venv/bin/pip" install --quiet --upgrade pip
"$HEDEF/venv/bin/pip" install --quiet "pyHanko[pkcs11,opentype]" pyhanko-cli pymupdf
basari "Kütüphaneler kuruldu"

# ---------------------------------------------------------------- hızlı eylem
baslik "Mühür uygulaması oluşturuluyor…"
UYG="$HOME/Applications/Mühür.app"
mkdir -p "$HOME/Applications"
BETIK="$(mktemp -t muhur).applescript"
cat > "$BETIK" <<'APPLESCRIPT'
-- Birlikte Aç ile gelen PDF'ler: yer seçme penceresi.
on open theFiles
	repeat with f in theFiles
		set p to POSIX path of f
		do shell script "cd \"$HOME/Muhur\" || exit 1; ./venv/bin/python imzala-gui.py " & quoted form of p & " > /dev/null 2>&1 &"
	end repeat
end open

-- Uygulamaya çift tıklanırsa: ayarlar penceresi.
on run
	do shell script "cd \"$HOME/Muhur\" || exit 1; ./venv/bin/python ayarlar-gui.py > /dev/null 2>&1 &"
end run
APPLESCRIPT
rm -rf "$UYG"
osacompile -o "$UYG" "$BETIK" >/dev/null 2>&1
rm -f "$BETIK"
P="$UYG/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Delete :CFBundleDocumentTypes" "$P" >/dev/null 2>&1
/usr/libexec/PlistBuddy -c "Set :CFBundleName Mühür" "$P" >/dev/null 2>&1
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string Mühür" "$P" >/dev/null 2>&1
for c in \
	"Add :CFBundleDocumentTypes array" \
	"Add :CFBundleDocumentTypes:0 dict" \
	"Add :CFBundleDocumentTypes:0:CFBundleTypeName string 'PDF belgesi'" \
	"Add :CFBundleDocumentTypes:0:CFBundleTypeRole string Editor" \
	"Add :CFBundleDocumentTypes:0:LSHandlerRank string Alternate" \
	"Add :CFBundleDocumentTypes:0:LSItemContentTypes array" \
	"Add :CFBundleDocumentTypes:0:LSItemContentTypes: string com.adobe.pdf"; do
	/usr/libexec/PlistBuddy -c "$c" "$P" >/dev/null 2>&1
done
# osacompile "on open" bölümü yüzünden uygulamayı droplet olarak üretiyor
# ve droplet.icns kullanıyor; her ikisini de kendi simgemizle değiştiriyoruz.
"$HEDEF/venv/bin/python" "$HEDEF/ikon-uret.py" \
	"$UYG/Contents/Resources/applet.icns" >/dev/null 2>&1 || true
[[ -f "$UYG/Contents/Resources/applet.icns" ]] && \
	cp "$UYG/Contents/Resources/applet.icns" "$UYG/Contents/Resources/droplet.icns" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile applet" "$P" >/dev/null 2>&1 || \
	/usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string applet" "$P" >/dev/null 2>&1
codesign -f -s - "$UYG" >/dev/null 2>&1
basari "Mühür.app oluşturuldu (çift tıklayınca ayarlar açılır)"

baslik "Finder hızlı eylemi ekleniyor…"
"$HEDEF/venv/bin/python" "$KAYNAK/hizli_eylem_kur.py" >/dev/null
killall -u "$USER" pbs 2>/dev/null || true
basari "Sağ tık menüsüne \"Mühürle\" eklendi"

# ----------------------------------------------------------------- doğrulama
baslik "E-imza kartınız aranıyor…"
if "$HEDEF/venv/bin/python" - <<'PY'
import sys
sys.path.insert(0, __import__("os").path.expanduser("~/Muhur"))
import imza_core
try:
    lib = imza_core.kutuphane_bul()
    token = imza_core.token_bul(lib)
    sertifika, _ = imza_core.imza_sertifikasi_bul(lib, token)
    konu = sertifika.subject.native
    print(f"    Sürücü    : {lib}")
    print(f"    Kart      : {token}")
    print(f"    Sertifika : {konu.get('common_name')} ({konu.get('title')})")
    print(f"    Geçerlilik: {sertifika['tbs_certificate']['validity']['not_after'].native:%d.%m.%Y}")
except imza_core.KartYok as e:
    print(f"    {e}")
    sys.exit(1)
PY
then
	basari "Kart okundu"
	print "\nKurulum tamamlandı."
	print "Bir PDF'e sağ tıklayıp \"Mühürle\" seçin."
else
	uyari "Kart okunamadı — kurulum yine de tamamlandı."
	print "\nToken takılı değilse takıp şunu çalıştırın:"
	print "    ~/Muhur/venv/bin/python ~/Muhur/imzala.py --help"
	print "\nSürücü kurulu değilse kart sağlayıcınızın (TÜRKTRUST, E-Güven,"
	print "Kamu SM, E-Tuğra) macOS sürücüsünü kurmanız gerekir."
fi
