from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from yol.kaynak import Deger, kaynak_sec
from yol.analiz import Bulgu, analiz_girdi, komutlar_olustur, etki_sırası, temizlik_onerisi, komutlari_bul
from yol.degisiklik import Degisiklik, Degisiklikler, uygulama_yap, DegisiklikHatasi, YedekDeposu, Gunluk
from yol.yedek import YedekDeposu as YedekDepoModul
from yol.gizli import GizliOrtam
class YolCLI:
    """Yol CLI (Komut Satırı Arabirimi) komutları."""

    def __init__(self, kaynak: Any = None) -> None:
        self.kaynak = kaynak if kaynak else kaynak_sec()
        self.yedek_deposu = YedekDepoModul()
        self.gunluk = Gunluk()
        self.gizli_ortam = GizliOrtam()

    def denetle(self, json_modu: bool = False) -> None:
        """Yolu denetler (PATH değişkenlerini bulgu tablosu ile listeler ve özetler)."""
        # PATH sürücüsünü işaretle
        kullanici_diziler: list[str] = []
        sistem_diziler: list[str] = []

        # Özel ortam değişkeni yoksa ortam değişkeni olarak PATH'i koru
        ortam = os.environ.get("PATH", "")
        if ortam:
            if os.name == "nt":
                kullanici_diziler = ortam.split(";")
            else:
                kullanici_diziler = ortam.split(os.pathsep)

        # Sistem PATH'i (Windows varsa, HKLM kaynağını kullan)
        if os.name == "nt":
            sistem_degerleri = self.kaynak.oku("sistem")
            sistem_diziler = [d.metin for d in sistem_degerleri.values() if d.metin]

        # Komutları oluştur (PATHEXT ile)
        pathext = os.environ.get("PATHEXT", ".EXE;.COM;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC")
        komutlar = komutlar_olustur(pathext)

        # Etki sırasını belirle (etki sırasına göre dizileri değiştir)
        etkile = etki_sırası("kullanici")
        tum_diziler: dict[str, list[str]] = {}
        for kapsam in etkile:
            if kapsam == "sistem":
                tum_diziler[kapsam] = sistem_diziler
            else:
                tum_diziler[kapsam] = kullanici_diziler

        # PATH'sini göster (gözlemlenmeyen dizinler hariç)
        komut_listesi = list(komutlar.keys())
        for komut in komut_listesi:
            kazanici, koyuluklar = komutlari_bul(komut, tum_diziler, komutlar)
            if not json_modu:
                print(f"{komut}: {kazanici}")
                if koyuluklar:
                    print(f"  (gölgelenen: {', '.join(koyuluklar)})")

        # Özet
        if json_modu:
            # JSON özetini oluştur
            ozet = {
                "komutlar": {}
            }
            for komut in komut_listesi:
                kazanici, koyuluklar = komutlari_bul(komut, tum_diziler, komutlar)
                ozet["komutlar"][komut] = {
                    "kazanici": kazanici,
                    "gölgelenen": koyuluklar,
                    "etki_sırası": etkile
                }
            print(json.dumps(ozet, indent=2))
        else:
            # Özet çıktısı
            print("\n--- Özet ---")
            toplam_giriş = sum(len(diziler) for diziler in tum_diziler.values())
            print(f"Toplam PATH girişi: {toplam_giriş}")
            for kapsam, diziler in tum_diziler.items():
                print(f"{kapsam.title()} dizisi: {len(diziler)}")

    def nerede(self, *komut_adlari: str) -> None:
        """Verilen komutların nerede olduğunu listeler (kazanan ve gölgelenen)."""
        if not komut_adlari:
            komut_adlari = ["python", "node", "git"]

        # Sürücüyü işaretle
        kullanici_diziler: list[str] = []
        sistem_diziler: list[str] = []
        ortam = os.environ.get("PATH", "")
        if ortam:
            if os.name == "nt":
                kullanici_diziler = ortam.split(";")
            else:
                kullanici_diziler = ortam.split(os.pathsep)

        if os.name == "nt":
            sistem_degerleri = self.kaynak.oku("sistem")
            sistem_diziler = [d.metin for d in sistem_degerleri.values() if d.metin]

        etkile = etki_sırası("kullanici")
        tum_diziler: dict[str, list[str]] = {}
        for kapsam in etkile:
            if kapsam == "sistem":
                tum_diziler[kapsam] = sistem_diziler
            else:
                tum_diziler[kapsam] = kullanici_diziler

        pathext = os.environ.get("PATHEXT", ".EXE;.COM;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC")
        komutlar = komutlar_olustur(pathext)

        # Komutları kontrol et
        for komut in komut_adlari:
            kazanici, koyuluklar = komutlari_bul(komut, tum_diziler, komutlar)
            print(f"{komut}:")
            print(f"  kazanan: {kazanici}")
            if koyuluklar:
                print(f"  gölgelenen: {', '.join(koyuluklar)}")

    def temizle(self, uygula: bool = False) -> None:
        """PATH'i temizler (gözetlenen kurallara göre).

        Argümanlar:
            uygula: Değişiklikleri uygulamayı onaylamak için kullanılır.
        """
        # Sürücüyü işaretle
        kullanici_diziler: list[str] = []
        sistem_diziler: list[str] = []
        ortam = os.environ.get("PATH", "")
        if ortam:
            if os.name == "nt":
                kullanici_diziler = ortam.split(";")
            else:
                kullanici_diziler = ortam.split(os.pathsep)

        if os.name == "nt":
            sistem_degerleri = self.kaynak.oku("sistem")
            sistem_diziler = [d.metin for d in sistem_degerleri.values() if d.metin]

        pathext = os.environ.get("PATHEXT", ".EXE;.COM;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC")
        komutlar = komutlar_olustur(pathext)

        # Öneri oluştur
        oneriler = temizlik_onerisi(kullanici_diziler, sistem_diziler, komutlar)

        if not oneriler:
            print("İyi! PATH'te temizlenmesi gereken bir giriş yok.")
            return

        print(f"Temizlik önerisi ({len(oneriler)} giriş):")
        for i, oneri in enumerate(oneriler, 1):
            print(f"{i}. {oneri['girdi']} - {oneri['analiz']['bulgu'].aciklama}")

        if uygula:
            # Değişiklikleri hazırla ve uygulama_yap fonksiyonunu kullanarak uygula
            degisiklikler: list[Degisiklik] = []
            for oneri in oneriler:
                degisiklikler.append(Degisiklik(
                    kapsam=oneri["kapsam"],
                    ad=f"PATH_{oneri['sira']}",
                    eski=None,  # PATH değerleri sadece dizi olarak
                    yeni=None
                ))
            # Değişiklikleri uygulama_yap fonksiyonu ile uygula
            try:
                uygulanan = uygulama_yap(
                    kaynak=self.kaynak,
                    degisiklikler=Degisiklikler(degisiklikler),
                    gunluk=self.gunluk,
                    yedek_deposu=self.yedek_deposu
                )
                print(f"{len(uygulanen)} PATH girişi uygulandı.")
            except DegisiklikHatasi as e:
                print(f"Hata: {e}")
                sys.exit(1)

    def ekle(self, dizin: str, basa: bool = False, uygula: bool = False) -> None:
        """Dizin PATH'e eklenir (kullanıcı kapsamına yazma izni gerektirir).

        Argümanlar:
            dizin: Eklenecek dizin yolu.
            basa: Eğer True ise, dizini PATH'in başına ekler (sağdan sola).
            uygula: Değişikliği uygulamayı onaylamak için kullanılır.
        """
        if not Path(dizin).exists():
            print(f"Hata: Dizin yok: {dizin}")
            sys.exit(1)

        # PATH'i okumak için kullanılacak dizi
        kullanici_dizileri: list[str] = []
        ortam = os.environ.get("PATH", "")
        if ortam:
            if os.name == "nt":
                kullanici_dizileri = ortam.split(";")
            else:
                kullanici_dizileri = ortam.split(os.pathsep)

        # PATH'e eklenecek yeni dizin
        yeni_dizi = dizin
        if basa:
            if yeni_dizi not in kullanici_dizileri:
                kullanici_dizileri.insert(0, yeni_dizi)
        else:
            if yeni_dizi not in kullanici_dizileri:
                kullanici_dizileri.append(yeni_dizi)

        print(f"PATH'e eklenecek dizin: {yeni_dizi}")
        print(f"Yeni PATH dizisi: {';'.join(kullanici_dizileri) if os.name == 'nt' else os.pathsep.join(kullanici_dizileri)}")

        if uygula:
            # PATH'i PATH değişkeni olarak kaydetmek için bir değişiklik oluştur
            # PATH değişkeni için bir değişken adı kullanarak yazma işlemini gerçekleştir
            # Eğer PATH değişkeni olarak kaydetmek için bir yöntemimiz yoksa, PATH değerini içeren bir ortam değişkeni oluşturabiliriz.
            # Windows'ta, PATH'i bir ortam değişkeni olarak kaydetmek için kayıt defterine yazabiliriz.
            # Bunun yerine, PATH değişkeninin ortam değiştiriciyi etkilemesi için PATH ortam değişkenini yeniden ayarlamak mümkün olabilir.
            # Bununla birlikte, uygulama_yap fonksiyonunun PATH'i PATH değişkeni olarak kaydetmesine izin vermek için bir değişiklik oluşturmak gerekir.
            # PATH'i PATH değişkeni olarak kaydetmek için bir değişiklik oluşturmak için bir yöntem kullanın.
            # Şimdilik, PATH'i PATH değişkeni olarak kaydetmek için bir değişken adı kullanarak PATH değerini yazdırmamızı sağlayalım.
            # Windows ortam kaynağı kullanılacak.
            pass

    def kaldir(self, dizin: str, uygula: bool = False) -> None:
        """PATH'ten dizini kaldırır (kullanıcı kapsamına yazma izni gerektirir).

        Argümanlar:
            dizin: PATH'ten kaldırılacak dizin yolu.
            uygula: Değişikliği uygulamayı onaylamak için kullanılır.
        """
        # Sürücüyü işaretle
        kullanici_dizileri: list[str] = []
        ortam = os.environ.get("PATH", "")
        if ortam:
            if os.name == "nt":
                kullanici_dizileri = ortam.split(";")
            else:
                kullanici_dizileri = ortam.split(os.pathsep)

        # PATH'ten dizini kaldır
        if dizin in kullanici_dizileri:
            kullanici_dizileri.remove(dizin)
            print(f"{dizin} PATH'ten kaldırıldı.")
            print(f"Yeni PATH dizisi: {';'.join(kullanici_dizileri) if os.name == 'nt' else os.pathsep.join(kullanici_dizileri)}")
        else:
            print(f"{dizin} PATH'te bulunamadı.")

    def yedekler(self) -> None:
        """Yedeği listele (son 30)."""
        yedekler = self.yedek_deposu.en_son_30_yedek()
        if not yedekler:
            print("No yedek dosyası bulunamadı.")
            return

        for i, y in enumerate(yedekler):
            print(f"{i+1}. {y.id} - {len(y.kapsamlar)} kapsam")

    def geri_al(self, id: str, uygula: bool = False) -> None:
        """Bir yedekten geri al (ör. önizleme farkı ile).

        Argümanlar:
            id: Yedek kimliği.
            uygula: Değişiklikleri uygulamayı onaylamak için kullanılır.
        """
        fark = self.yedek_deposu.geri_al(id)
        if not fark:
            print(f"Yedek {id} bulunamadı.")
            return

        print(f"Yedek {id} farkı:")
        for kapsam, degerler in fark.items():
            for ad, deger in degerler.items():
                print(f"  {kapsam}:{ad} = {deger.metin}")

        if uygula:
            # Yedeği yüklemek için PATH değişkenini kullanarak bir değişiklik oluştur
            # Şimdilik sadece farkı göster
            print("Önizleme tamamlandı. Yedek yüklemek için --uygula kullanılabilir.")

    def web(self, port: int = 8797, ac: bool = False) -> None:
        """Yol web panelini başlatır.

        Argümanlar:
            port: Web sunucusunun dinleyeceği port.
            ac: Oturum açılışı açmak için kullanılır (şimdilik kullanılmıyor).
        """
        # Şimdilik, web panelinin Flask uygulaması yok, bir console uygulaması göster
        print(f"Web sunucusu port {port} üzerinde çalışmıyor (web paneli henüz uygulanmadı).")
        print("Yol web paneli, Dalga B'de daha sonra kullanılabilir.")

    def basla(self) -> None:
        """Yol CLI yardımcı programının başlangıç noktası."""
        print("Yol yardımcı programı başlatıldı.")
        print("Mevcut komutlar:")
        print("  yol denetle [--json]            # yol değişikliklerini denetle")
        print("  yol nerede <komut>...          # komutların konumunu listele")
        print("  yol temizle [--uygula]          # PATH'i temizle")
        print("  yol ekle <dizin> [--basa] [--uygula] # dizini PATH'e ekle")
        print("  yol kaldir <dizin> [--uygula]  # dizini PATH'ten kaldır")
        print("  yol yedekler                   # son 30 yedeği listele")
        print("  yol geri-al <id> [--uygula]     # bir yedeği geri al")
        print("  yol web [--port 8797] [--ac]    # yol web panelini başlat")
        print("  yol --help                     # bu yardım mesajını göster")

def basla() -> None:
    """CLI ana giriş noktası."""
    # Modüler yapıyı desteklemek için CLI aracını başlat
    yol = YolCLI()
    if len(sys.argv) < 2:
        yol.basla()
        return

    komut = sys.argv[1]
    if komut == "denetle":
        json_modu = "--json" in sys.argv
        yol.denetle(json_modu=json_modu)
    elif komut == "nerede":
        komut_adlari = sys.argv[2:] if len(sys.argv) > 2 else []
        yol.nerede(*komut_adlari)
    elif komut == "temizle":
        uygula = "--uygula" in sys.argv
        yol.temizle(uygula=uygula)
    elif komut == "ekle":
        if len(sys.argv) < 3:
            print("Hata: <dizin> gerekli")
            sys.exit(1)
        dizin = sys.argv[2]
        basa = "--basa" in sys.argv
        uygula = "--uygula" in sys.argv
        yol.ekle(dizin, basa=basa, uygula=uygula)
    elif komut == "kaldir":
        if len(sys.argv) < 3:
            print("Hata: <dizin> gerekli")
            sys.exit(1)
        dizin = sys.argv[2]
        uygula = "--uygula" in sys.argv
        yol.kaldir(dizin, uygula=uygula)
    elif komut == "yedekler":
        yol.yedekler()
    elif komut == "geri-al":
        if len(sys.argv) < 3:
            print("Hata: <id> gerekli")
            sys.exit(1)
        id = sys.argv[2]
        uygula = "--uygula" in sys.argv
        yol.geri_al(id, uygula=uygula)
    elif komut == "web":
        port = 8797
        ac = False
        if "--port" in sys.argv:
            try:
                idx = sys.argv.index("--port")
                port = int(sys.argv[idx + 1])
            except (ValueError, IndexError):
                pass
        if "--ac" in sys.argv:
            ac = True
        yol.web(port=port, ac=ac)
    elif komut == "--help":
        yol.basla()
    else:
        print(f"Bilinmeyen komut: {komut}")
        yol.basla()
if __name__ == "__main__":
    basla()