/* yol paneli — davranis katmani (CSP uyumlu, satir ici script yok).
   Guvenlik: HTML hicbir zaman innerHTML ile yazilmaz; DOM yalnizca createElement +
   textContent ile kurulur. Yol, ad, deger ve komut metinleri guvenilmeyen veridir.
   Degisiklikler once TASLAKTA toplanir; yazma yalnizca Onizle'den sonra, acik
   "uygula" dugmesiyle yapilir. Sunucu her yazmada beklenen eski degeri kontrol eder. */

(function () {
  "use strict";

  var CSRF = "";
  var csrfMeta = document.querySelector('meta[name="yol-csrf"]');
  if (csrfMeta) { CSRF = csrfMeta.getAttribute("content") || ""; }

  var KAPSAM_ETIKET = { kullanici: "Kullanıcı", sistem: "Sistem", surec: "Süreç" };
  var KAPSAM_KISA = { kullanici: "kullanıcı", sistem: "sistem", surec: "süreç" };
  var KAYNAK_ETIKET = { windows: "Windows", dosya: "JSON dosyası", surec: "Süreç ortamı" };
  var BULGU = {
    "yok": { metin: "yok", sinif: "rozet-hata" },
    "bos": { metin: "boş", sinif: "rozet-hata" },
    "tekrar": { metin: "tekrar", sinif: "rozet-hata" },
    "sistemde-var": { metin: "sistemde var", sinif: "rozet-hata" },
    "goreli": { metin: "göreli", sinif: "rozet-uyari" }
  };
  var EYLEM = {
    "ekle": { metin: "yeni", sinif: "rozet-basari" },
    "degistir": { metin: "değişecek", sinif: "rozet-uyari" },
    "sil": { metin: "silinecek", sinif: "rozet-hata" }
  };
  var SORUNLU = ["yok", "bos", "tekrar", "sistemde-var"];
  var SEKMELER = ["path", "komut", "degisken", "yedek"];
  var MAKS_YOL = 4096;
  var MAKS_DEGER = 32767;

  var S = {
    durum: null,       // GET /api/durum
    degiskenler: [],   // GET /api/degiskenler (maskeli)
    yedekler: [],      // GET /api/yedekler
    satirlar: {},      // kapsam -> PATH satirlari (taslak hali)
    taslak: {},        // anahtar -> {kapsam, ad, tip, eski, yeni}
    acik: {},          // anahtar -> bu oturumda acikca istenen deger
    duzenle: null,     // acik degisken duzenleyicisi
    onizleme: null,    // son onizlemenin gonderilen govdesi
    yedekAcik: null    // acik yedek fark kimligi
  };

  /* ------------------------------------------------------------ yardimcilar */

  function $(id) { return document.getElementById(id); }

  function el(etiket, sinif, metin) {
    var e = document.createElement(etiket);
    if (sinif) { e.className = sinif; }
    if (metin !== undefined && metin !== null) { e.textContent = String(metin); }
    return e;
  }

  function dugme(metin, sinif, aciklama, tikla) {
    var b = el("button", "dugme " + (sinif || ""), metin);
    b.type = "button";
    if (aciklama) { b.setAttribute("aria-label", aciklama); }
    if (tikla) { b.addEventListener("click", tikla); }
    return b;
  }

  function rozet(metin, sinif) { return el("span", "rozet " + (sinif || ""), metin); }

  function bildir(metin, hata) {
    var b = $("bildirim");
    b.className = "bildirim" + (hata ? " hata-bildirim" : "");
    b.textContent = metin || "";
  }

  function hataGoster(err) {
    bildir((err && err.message) || "Beklenmeyen bir hata oluştu.", true);
  }

  function kisalt(metin, n) {
    var s = String(metin);
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  function gorunenDeger(v) {
    if (v === null || v === undefined) { return "(yok)"; }
    return v === "" ? "(boş)" : v;
  }

  function goreli(iso) {
    if (!iso) { return "bilinmiyor"; }
    var t = Date.parse(String(iso).replace(/(\.\d{3})\d+/, "$1"));
    if (isNaN(t)) { return String(iso); }
    var sn = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (sn < 60) { return "az önce"; }
    var dk = Math.round(sn / 60);
    if (dk < 60) { return dk + " dakika önce"; }
    var sa = Math.round(dk / 60);
    if (sa < 24) { return sa + " saat önce"; }
    var g = Math.round(sa / 24);
    if (g < 30) { return g + " gün önce"; }
    return new Date(t).toLocaleDateString("tr-TR");
  }

  /* Istek yardimcisi: GET govdesiz; POST'a CSRF basligi eklenir. Hata: Error(.kod, .veri). */
  function istek(yol, govde) {
    var secenek = { cache: "no-store", headers: { "Accept": "application/json" } };
    if (govde !== undefined) {
      secenek.method = "POST";
      secenek.headers["Content-Type"] = "application/json";
      secenek.headers["X-CSRF"] = CSRF;
      secenek.body = JSON.stringify(govde);
    }
    return fetch(yol, secenek).then(function (cevap) {
      return cevap.json().catch(function () { return {}; }).then(function (veri) {
        if (!cevap.ok) {
          var hata = new Error((veri && veri.hata) || ("İstek başarısız (HTTP " + cevap.status + ")."));
          hata.kod = cevap.status;
          hata.veri = veri;
          throw hata;
        }
        return veri;
      });
    }, function () {
      throw new Error("Sunucuya ulaşılamadı. Panel çalışıyor mu?");
    });
  }

  function kapsamBilgi(ad) {
    var liste = (S.durum && S.durum.platform.kapsamlar) || [];
    for (var i = 0; i < liste.length; i++) {
      if (liste[i].ad === ad) { return liste[i]; }
    }
    return null;
  }

  function yazilabilir(ad) {
    var k = kapsamBilgi(ad);
    return !!(k && k.yazilabilir);
  }

  function ayirici() { return S.durum.platform.ayirici; }
  function windowsMu() { return !!S.durum.platform.windows; }

  function anahtar(kapsam, ad) { return kapsam + "\u0001" + ad; }

  function esitDeger(a, b) {
    if (a === null || b === null) { return a === b; }
    return a.metin === b.metin && a.genisler === b.genisler;
  }

  /* ------------------------------------------------------------ taslak */

  function taslakSayi() { return Object.keys(S.taslak).length; }

  /* eski/yeni null olabilir: eski null = yeni olusturma, yeni null = silme.
     Eski ile yeni ayniysa kayit taslaktan kalkar (no-op degisiklik gonderilmez). */
  function taslakKoy(kapsam, ad, eski, yeni) {
    var k = anahtar(kapsam, ad);
    if (esitDeger(eski, yeni)) {
      delete S.taslak[k];
    } else {
      S.taslak[k] = {
        kapsam: kapsam,
        ad: ad,
        tip: ad.toLowerCase() === "path" ? "path" : "degisken",
        eski: eski,
        yeni: yeni
      };
    }
    taslakGuncelle();
  }

  function taslakGovde() {
    return {
      degisiklikler: Object.keys(S.taslak).map(function (k) {
        var t = S.taslak[k];
        return { kapsam: t.kapsam, ad: t.ad, eski: t.eski, yeni: t.yeni };
      })
    };
  }

  function onizlemeGizle() {
    S.onizleme = null;
    $("onizleme").hidden = true;
    $("onizleme-govde").replaceChildren();
  }

  function taslakGuncelle() {
    var n = taslakSayi();
    var sayi = $("taslak-sayi");
    sayi.textContent = n ? n + " değişiklik taslakta" : "Taslak boş";
    sayi.className = "taslak-sayi" + (n ? " bekliyor" : "");
    $("taslak-onizle").disabled = n === 0;
    $("taslak-temizle").disabled = n === 0;
    onizlemeGizle();
    yedekGeriAlGuncelle();
  }

  function taslakTemizle() {
    S.taslak = {};
    S.duzenle = null;
    satirlariKur();
    ciz();
    bildir("Taslak temizlendi.");
  }

  /* ------------------------------------------------------------ PATH satirlari */

  function satirlariKur() {
    S.satirlar = {};
    var liste = (S.durum && S.durum.platform.kapsamlar) || [];
    liste.forEach(function (k) { S.satirlar[k.ad] = []; });
    S.durum.path.girdiler.forEach(function (g) {
      if (!S.satirlar[g.kapsam]) { S.satirlar[g.kapsam] = []; }
      S.satirlar[g.kapsam].push({
        ham: g.ham,
        genis: g.genis,
        bulgular: g.bulgular.slice(),
        taslak: false
      });
    });
  }

  function pathAd(kapsam) {
    var k = S.durum.path.kayitlar[kapsam];
    if (k && k.var && k.ad) { return k.ad; }
    return windowsMu() ? "Path" : "PATH";
  }

  /* Satirlardan yeni PATH metnini kurar; eski ile farki taslaga yazar. */
  function pathTaslagiGuncelle(kapsam) {
    var k = S.durum.path.kayitlar[kapsam] || { var: false, metin: "", genisler: false };
    var satirlar = S.satirlar[kapsam] || [];
    var yeniMetin = satirlar.map(function (r) { return r.ham; }).join(ayirici());
    var eski = k.var ? { metin: k.metin, genisler: k.genisler } : null;
    var yeni;
    if (!k.var && satirlar.length === 0) {
      yeni = null;
    } else if (k.var && yeniMetin === k.metin) {
      yeni = eski;
    } else {
      var genisler = k.var ? k.genisler : false;
      if (windowsMu() && yeniMetin.indexOf("%") >= 0) { genisler = true; }
      yeni = { metin: yeniMetin, genisler: genisler };
    }
    taslakKoy(kapsam, pathAd(kapsam), eski, yeni);
  }

  function takas(liste, a, b) {
    var gecici = liste[a];
    liste[a] = liste[b];
    liste[b] = gecici;
  }

  function satirIslem(kapsam, i, islem) {
    var liste = S.satirlar[kapsam];
    if (islem === "yukari" && i > 0) {
      takas(liste, i, i - 1);
    } else if (islem === "asagi" && i < liste.length - 1) {
      takas(liste, i, i + 1);
    } else if (islem === "kaldir") {
      liste.splice(i, 1);
    } else {
      return;
    }
    pathTaslagiGuncelle(kapsam);
    pathCiz();
  }

  function sorunlu(satir) {
    return satir.bulgular.some(function (b) { return SORUNLU.indexOf(b) >= 0; });
  }

  function dizinAnahtari(metin) {
    var t = metin.trim().replace(/[\\\/]+$/, "");
    return windowsMu() ? t.replace(/\//g, "\\").toLowerCase() : t;
  }

  /* Dizin kullanici PATH'ine eklenir; ayni dizin varsa false doner. */
  function dizinEkle(metin, basa) {
    var liste = S.satirlar.kullanici || (S.satirlar.kullanici = []);
    var anahtarDeger = dizinAnahtari(metin);
    for (var i = 0; i < liste.length; i++) {
      if (liste[i].ham !== "" && dizinAnahtari(liste[i].ham) === anahtarDeger) { return false; }
    }
    var satir = { ham: metin, genis: null, bulgular: [], taslak: true };
    if (basa) { liste.unshift(satir); } else { liste.push(satir); }
    pathTaslagiGuncelle("kullanici");
    pathCiz();
    return true;
  }

  function onerileriUygula() {
    var liste = S.satirlar.kullanici || [];
    var kalan = liste.filter(function (r) { return !sorunlu(r); });
    var kaldirilan = liste.length - kalan.length;
    if (!kaldirilan) { return; }
    S.satirlar.kullanici = kalan;
    pathTaslagiGuncelle("kullanici");
    pathCiz();
    bildir(kaldirilan + " sorunlu girdi taslağa eklendi. Uygulamadan önce Önizle ile kontrol edin.");
  }

  function oneriGuncelle() {
    var yazilir = yazilabilir("kullanici");
    var n = (S.satirlar.kullanici || []).filter(sorunlu).length;
    $("oneri-dugme").disabled = !yazilir || n === 0;
    var not = !yazilir
      ? "Kullanıcı PATH'i bu kaynakta yazılabilir değil."
      : (n ? n + " sorunlu girdi (yok, boş, tekrar veya sistemde var) kaldırılacak."
           : "Kullanıcı PATH'inde temizlenecek sorunlu girdi yok.");
    $("oneri-not").textContent = not;
  }

  function satirEl(kapsam, i, satir, sira, yazilir) {
    var li = el("li", "yol-satir");
    li.appendChild(el("span", "yol-sira", sira + "."));

    var govde = el("div", "yol-govde");
    if (satir.ham === "") {
      govde.appendChild(el("span", "yol-bos", "(boş girdi)"));
    } else {
      govde.appendChild(el("code", "yol-ham", satir.ham));
    }
    if (satir.genis && satir.genis !== satir.ham) {
      govde.appendChild(el("span", "yol-genis", "çözümlenmiş: " + satir.genis));
    }

    var rozetler = el("div", "yol-rozetler");
    if (satir.taslak) { rozetler.appendChild(rozet("taslakta eklendi", "rozet-vurgu")); }
    satir.bulgular.forEach(function (b) {
      var m = BULGU[b];
      if (m) { rozetler.appendChild(rozet(m.metin, m.sinif)); }
    });
    if (!satir.bulgular.length && !satir.taslak) { rozetler.appendChild(rozet("sorun yok", "rozet-basari")); }
    govde.appendChild(rozetler);
    li.appendChild(govde);

    var ad = satir.ham === "" ? "boş girdi" : satir.ham;
    var eylem = el("div", "yol-eylem");
    var sonuncu = S.satirlar[kapsam].length - 1;
    eylem.appendChild(dugme("yukarı", "dugme-kucuk", ad + " girdisini yukarı taşı",
      function () { satirIslem(kapsam, i, "yukari"); }));
    eylem.lastChild.disabled = !yazilir || i === 0;
    eylem.appendChild(dugme("aşağı", "dugme-kucuk", ad + " girdisini aşağı taşı",
      function () { satirIslem(kapsam, i, "asagi"); }));
    eylem.lastChild.disabled = !yazilir || i === sonuncu;
    eylem.appendChild(dugme("kaldır", "dugme-kucuk", ad + " girdisini taslaktan kaldır",
      function () { satirIslem(kapsam, i, "kaldir"); }));
    eylem.lastChild.disabled = !yazilir;
    li.appendChild(eylem);
    return li;
  }

  function pathCiz() {
    var sirali = ["sistem", "kullanici", "surec"].filter(function (k) { return kapsamBilgi(k) !== null; });
    var sistemVar = sirali.indexOf("sistem") >= 0;
    var kullaniciKutusu = sirali.indexOf("kullanici") >= 0 ? "kullanici" : "surec";

    $("liste-sistem").hidden = !sistemVar;
    $("baslik-kullanici").textContent = KAPSAM_ETIKET[kullaniciKutusu];

    var sira = 0;
    var kapsamKutulari = { sistem: ["yol-sistem", "not-sistem"], kullanici: ["yol-kullanici", "not-kullanici"],
                           surec: ["yol-kullanici", "not-kullanici"] };
    sirali.forEach(function (kapsam) {
      var hedef = kapsamKutulari[kapsam];
      var ol = $(hedef[0]);
      var not = $(hedef[1]);
      var yazilir = yazilabilir(kapsam);
      var satirlar = S.satirlar[kapsam] || [];
      ol.replaceChildren();
      if (!yazilir) {
        not.textContent = "Salt okunur." + (kapsam === "sistem" ? " Yönetici olarak açın." : " Bu platformda yalnız okunur.");
      } else {
        not.textContent = satirlar.length ? satirlar.length + " girdi" : "Bu kapsamda PATH tanımlı değil.";
      }
      if (!satirlar.length) {
        ol.appendChild(el("li", "yol-bos", "Bu listede girdi yok."));
      }
      satirlar.forEach(function (satir, i) {
        sira += 1;
        ol.appendChild(satirEl(kapsam, i, satir, sira, yazilir));
      });
    });

    var uzun = S.durum.ozet.uzun;
    var uyari = $("path-kapsam-not");
    uyari.hidden = !uzun;
    uyari.textContent = uzun
      ? "Toplam PATH 2047 karakteri aşıyor; bazı araçlar PATH'in tamamını göremeyebilir."
      : "";

    var kullaniciYazilir = yazilabilir("kullanici");
    $("dizin-girdi").disabled = !kullaniciYazilir;
    $("dizin-ekle").disabled = !kullaniciYazilir;
    oneriGuncelle();
  }

  /* ------------------------------------------------------------ genel durum */

  function platformCiz() {
    var p = S.durum.platform;
    var parcalar = [KAYNAK_ETIKET[p.kaynak] || p.kaynak];
    var salt = [];
    p.kapsamlar.forEach(function (k) {
      var kisa = KAPSAM_KISA[k.ad] || k.ad;
      parcalar.push(kisa + ": " + (k.yazilabilir ? "yazılabilir" : "salt okunur"));
      if (!k.yazilabilir) { salt.push(kisa); }
    });
    $("platform-rozet").textContent = parcalar.join(" · ");

    var serit = $("salt-okunur-serit");
    if (p.kaynak === "surec") {
      serit.textContent = "Bu platformda ortam değişkenleri yalnız okunur (süreç ortamı). Değişiklik yapılamaz.";
      serit.hidden = false;
    } else if (salt.length) {
      var metin = "Salt okunur: " + salt.join(", ") + ".";
      if (p.kapsamlar.some(function (k) { return k.ad === "sistem" && !k.yazilabilir; })) {
        metin += " Sistem kapsamını yönetici olarak açarak düzenleyebilirsiniz.";
      }
      serit.textContent = metin;
      serit.hidden = false;
    } else {
      serit.textContent = "";
      serit.hidden = true;
    }
  }

  function ozetCiz() {
    var o = S.durum.ozet;
    var girdi = o.girdi || {};
    var toplam = Object.keys(girdi).reduce(function (t, k) { return t + girdi[k]; }, 0);
    $("ozet-girdi").textContent = String(toplam);
    $("ozet-girdi-alt").textContent = Object.keys(girdi).map(function (k) {
      return (KAPSAM_KISA[k] || k) + " " + girdi[k];
    }).join(" · ") || "girdi yok";
    $("ozet-sorunlu").textContent = String(o.sorunlu);
    $("ozet-golge").textContent = String(o.golgelenen);
    var son = S.durum.yedek.son;
    $("ozet-yedek").textContent = son ? goreli(son.zaman) : "yok";
    $("ozet-yedek-alt").textContent = son ? "toplam " + S.durum.yedek.sayi + " yedek" : "henüz yedek yok";
  }

  function kapsamSecenekleri() {
    var sel = $("yeni-kapsam");
    var onceki = sel.value;
    sel.replaceChildren();
    ["kullanici", "sistem"].forEach(function (k) {
      if (!yazilabilir(k)) { return; }
      var o = el("option", "", KAPSAM_ETIKET[k]);
      o.value = k;
      sel.appendChild(o);
    });
    if (onceki) { sel.value = onceki; }
    $("yeni-ekle").disabled = sel.options.length === 0;
  }

  /* ------------------------------------------------------------ komutlar */

  function komutCiz() {
    var govde = $("komut-govde");
    govde.replaceChildren();
    var ara = $("komut-ara").value.trim().toLowerCase();
    var liste = (S.durum.komutlar || []).filter(function (k) {
      return !ara || k.ad.toLowerCase().indexOf(ara) >= 0;
    });
    $("komut-bos").hidden = liste.length > 0;

    liste.forEach(function (k) {
      var tr = el("tr");
      tr.appendChild(el("td", "komut-ad", k.ad));

      var kazanan = el("td", "yol-hucre");
      if (k.kazanan) {
        kazanan.appendChild(el("code", "", k.kazanan));
      } else {
        kazanan.appendChild(el("span", "yol-bos", "bulunamadı"));
      }
      tr.appendChild(kazanan);

      var golge = el("td", "sayi");
      if (k.golgede && k.golgede.length) {
        var detay = el("details", "golge");
        detay.appendChild(el("summary", "", k.golgede.length + " gölgede"));
        var ul = el("ul");
        k.golgede.forEach(function (yol) { ul.appendChild(el("li", "", yol)); });
        detay.appendChild(ul);
        golge.appendChild(detay);
      } else {
        golge.textContent = "0";
      }
      tr.appendChild(golge);

      var bulgu = el("td");
      if (!k.kazanan) {
        bulgu.appendChild(rozet("yok", "rozet-hata"));
      } else if (k.bulgu === "store-taklidi") {
        bulgu.appendChild(rozet("store-taklidi", "rozet-uyari"));
        bulgu.appendChild(el("p", "kisa-not",
          "Microsoft Store kısayolu gerçek Python'u gölgeliyor. Ayarlar > Uygulama yürütme diğer adları'ndan kapatın."));
      } else {
        bulgu.textContent = "-";
      }
      tr.appendChild(bulgu);
      govde.appendChild(tr);
    });
  }

  /* ------------------------------------------------------------ degiskenler */

  function degerAl(kapsam, ad) {
    var yol = "/api/degiskenler?goster=1&kapsam=" + encodeURIComponent(kapsam) +
              "&ad=" + encodeURIComponent(ad);
    return istek(yol).then(function (veri) {
      var kayit = veri.degiskenler && veri.degiskenler[0];
      if (!kayit) { throw new Error("Değişken bulunamadı: " + ad); }
      return { metin: kayit.deger, genisler: !!kayit.genisler };
    });
  }

  function degerGoster(d, ac) {
    var k = anahtar(d.kapsam, d.ad);
    if (!ac) {
      delete S.acik[k];
      degiskenCiz();
      return;
    }
    degerAl(d.kapsam, d.ad).then(function (kayit) {
      S.acik[k] = kayit.metin;
      degiskenCiz();
    }).catch(hataGoster);
  }

  function duzenleAc(d) {
    degerAl(d.kapsam, d.ad).then(function (kayit) {
      S.duzenle = { kapsam: d.kapsam, ad: d.ad, eski: kayit, odak: true };
      degiskenCiz();
    }).catch(hataGoster);
  }

  function silTaslaga(d) {
    degerAl(d.kapsam, d.ad).then(function (kayit) {
      taslakKoy(d.kapsam, d.ad, kayit, null);
      if (S.duzenle && S.duzenle.kapsam === d.kapsam && S.duzenle.ad === d.ad) { S.duzenle = null; }
      degiskenCiz();
      bildir(d.ad + " taslakta silinecek olarak işaretlendi.");
    }).catch(hataGoster);
  }

  function duzenleyiciEl(d) {
    var eski = S.duzenle.eski;
    var tr = el("tr", "satir-duzenle");
    var td = el("td");
    td.colSpan = 5;

    var alan = el("div", "alan");
    var etiket = el("label", "", "Yeni değer");
    etiket.setAttribute("for", "duz-deger");
    var metin = el("textarea", "girdi girdi-cok");
    metin.id = "duz-deger";
    metin.rows = 2;
    metin.spellcheck = false;
    metin.value = eski.metin;
    alan.appendChild(etiket);
    alan.appendChild(metin);
    td.appendChild(alan);

    var kutu = el("label", "onay-kutusu");
    var genis = el("input");
    genis.type = "checkbox";
    genis.id = "duz-genisler";
    genis.checked = eski.genisler;
    kutu.appendChild(genis);
    kutu.appendChild(document.createTextNode(" genişleyen metin (REG_EXPAND_SZ)"));
    td.appendChild(kutu);

    var hata = el("p", "alan-hata");
    var grup = el("div", "eylem-satir");
    grup.appendChild(dugme("Taslağa ekle", "dugme-birincil", null, function () {
      if (metin.value.length > MAKS_DEGER || metin.value.indexOf("\u0000") >= 0) {
        hata.textContent = "Değer çok uzun ya da geçersiz karakter içeriyor.";
        return;
      }
      taslakKoy(d.kapsam, d.ad, eski, { metin: metin.value, genisler: genis.checked });
      S.duzenle = null;
      degiskenCiz();
      bildir(d.ad + " taslağa eklendi.");
    }));
    grup.appendChild(dugme("Vazgeç", "dugme-hayalet", null, function () {
      S.duzenle = null;
      degiskenCiz();
    }));
    td.appendChild(grup);
    td.appendChild(hata);
    tr.appendChild(td);
    return tr;
  }

  function degiskenCiz() {
    var govde = $("degisken-govde");
    govde.replaceChildren();
    var kapsam = $("degisken-kapsam").value;
    var ara = $("degisken-ara").value.trim().toLowerCase();

    /* Taslakta olusturulacak yeni degiskenler de listede gorunur (yazilmis degerle). */
    var goruntu = S.degiskenler.slice();
    Object.keys(S.taslak).forEach(function (k) {
      var t = S.taslak[k];
      if (t.tip === "degisken" && t.eski === null && t.yeni !== null) {
        goruntu.push({ kapsam: t.kapsam, ad: t.ad, deger: t.yeni.metin, gizli: false,
                       genisler: t.yeni.genisler, yeni: true });
      }
    });

    var liste = goruntu.filter(function (d) {
      if (kapsam && d.kapsam !== kapsam) { return false; }
      if (!ara) { return true; }
      var acik = S.acik[anahtar(d.kapsam, d.ad)];
      var metin = d.gizli ? (acik !== undefined ? acik : "") : d.deger;
      return d.ad.toLowerCase().indexOf(ara) >= 0 || String(metin).toLowerCase().indexOf(ara) >= 0;
    });
    $("degisken-bos").hidden = liste.length > 0;

    liste.forEach(function (d) {
      var k = anahtar(d.kapsam, d.ad);
      var acik = S.acik[k];
      var tr = el("tr");
      var adHucre = el("td");
      adHucre.appendChild(el("code", "", d.ad));
      tr.appendChild(adHucre);
      tr.appendChild(el("td", "", KAPSAM_ETIKET[d.kapsam] || d.kapsam));

      var dh = el("td", "deger");
      var gosterilen = acik !== undefined ? acik : d.deger;
      dh.appendChild(el("span", "deger-metni mono", kisalt(gorunenDeger(gosterilen), 120)));
      if (d.gizli) {
        dh.appendChild(rozet("gizli", "rozet-uyari"));
        dh.appendChild(dugme(acik !== undefined ? "gizle" : "göster", "dugme-kucuk",
          d.ad + " değerini " + (acik !== undefined ? "gizle" : "göster"),
          function () { degerGoster(d, acik === undefined); }));
      }
      var taslak = S.taslak[k];
      if (taslak) {
        if (taslak.yeni === null) {
          dh.appendChild(rozet("taslakta: silinecek", "rozet-hata"));
        } else if (taslak.eski === null) {
          dh.appendChild(rozet("taslakta: yeni", "rozet-basari"));
        } else {
          dh.appendChild(rozet("taslakta: değişecek", "rozet-vurgu"));
          dh.appendChild(el("p", "kisa-not", "taslak değeri: " +
            (d.gizli ? "maskeli" : kisalt(gorunenDeger(taslak.yeni.metin), 80))));
        }
      }
      tr.appendChild(dh);

      tr.appendChild(el("td", "", d.genisler ? "genişleyen (REG_EXPAND_SZ)" : "metin (REG_SZ)"));

      var islem = el("td");
      if (d.ad.toLowerCase() === "path") {
        islem.appendChild(el("span", "kisa-not", "PATH sekmesinde düzenlenir"));
      } else if (!d.yeni) {
        var yaz = yazilabilir(d.kapsam);
        var grup = el("div", "satir-islem");
        var duz = dugme("düzenle", "dugme-kucuk", d.ad + " değişkenini düzenle", function () { duzenleAc(d); });
        duz.disabled = !yaz;
        var sil = dugme("sil", "dugme-kucuk dugme-tehlike", d.ad + " değişkenini taslakta sil", function () { silTaslaga(d); });
        sil.disabled = !yaz;
        grup.appendChild(duz);
        grup.appendChild(sil);
        islem.appendChild(grup);
      } else {
        islem.appendChild(el("span", "kisa-not", "taslakta bekliyor"));
      }
      tr.appendChild(islem);
      govde.appendChild(tr);

      if (S.duzenle && S.duzenle.kapsam === d.kapsam && S.duzenle.ad === d.ad) {
        var editor = duzenleyiciEl(d);
        govde.appendChild(editor);
        if (S.duzenle.odak) {
          S.duzenle.odak = false;
          var metin = editor.querySelector("textarea");
          if (metin) { metin.focus(); }
        }
      }
    });
  }

  function yeniDegiskenEkle(e) {
    e.preventDefault();
    var hata = $("yeni-hata");
    hata.textContent = "";
    var kapsam = $("yeni-kapsam").value;
    var ad = $("yeni-ad").value.trim();
    var deger = $("yeni-deger").value;
    var genisler = $("yeni-genisler").checked;

    if (!ad || ad.length > 256 || ad.indexOf("=") >= 0 || ad.indexOf("\u0000") >= 0) {
      hata.textContent = "Ad boş olamaz; en fazla 256 karakter olmalı ve = içermemeli.";
      return;
    }
    if (ad.toLowerCase() === "path") {
      hata.textContent = "PATH için PATH sekmesini kullanın.";
      return;
    }
    if (!yazilabilir(kapsam)) {
      hata.textContent = "Seçilen kapsam yazılabilir değil.";
      return;
    }
    if (S.degiskenler.some(function (d) { return d.kapsam === kapsam && d.ad === ad; })) {
      hata.textContent = "Bu ad zaten var. Değiştirmek için listedeki düzenle düğmesini kullanın.";
      return;
    }
    if (deger.length > MAKS_DEGER || deger.indexOf("\u0000") >= 0) {
      hata.textContent = "Değer çok uzun ya da geçersiz karakter içeriyor.";
      return;
    }
    taslakKoy(kapsam, ad, null, { metin: deger, genisler: genisler });
    $("yeni-ad").value = "";
    $("yeni-deger").value = "";
    $("yeni-genisler").checked = false;
    degiskenCiz();
    bildir(ad + " taslağa eklendi.");
  }

  /* ------------------------------------------------------------ yedekler */

  function yedekFarkKapat() {
    S.yedekAcik = null;
    $("yedek-fark").hidden = true;
    $("yedek-fark-govde").replaceChildren();
  }

  function yedekGeriAlGuncelle() {
    $("yedek-geri-al").disabled = taslakSayi() > 0;
    $("yedek-taslak-not").hidden = taslakSayi() === 0;
  }

  function yedekCiz() {
    var govde = $("yedek-govde");
    govde.replaceChildren();
    $("yedek-bos").hidden = S.yedekler.length > 0;
    S.yedekler.forEach(function (y) {
      var tr = el("tr");
      var zaman = el("td");
      zaman.appendChild(el("span", "", goreli(y.zaman)));
      zaman.setAttribute("title", y.zaman || "");
      zaman.appendChild(el("p", "kisa-not", y.id));
      tr.appendChild(zaman);
      var kapsamlar = Object.keys(y.kapsamlar).map(function (k) {
        return (KAPSAM_ETIKET[k] || k) + ": " + y.kapsamlar[k];
      });
      tr.appendChild(el("td", "", kapsamlar.join(", ") || "-"));
      var islem = el("td");
      islem.appendChild(dugme("farkı gör", "dugme-kucuk", goreli(y.zaman) + " yedeğinin farkını gör",
        function () { yedekFarkGoster(y); }));
      tr.appendChild(islem);
      govde.appendChild(tr);
    });
  }

  function yedekFarkGoster(y) {
    istek("/api/yedek/" + encodeURIComponent(y.id) + "/fark").then(function (veri) {
      S.yedekAcik = y.id;
      var baslik = $("yedek-fark-baslik");
      baslik.textContent = goreli(y.zaman) + " yedeği: " + veri.fark.length + " değişiklik";
      var govdeEl = $("yedek-fark-govde");
      farkCiz(govdeEl, veri.fark);
      var geri = $("yedek-geri-al");
      geri.textContent = veri.fark.length ? veri.fark.length + " değişikliği geri al" : "geri alınacak fark yok";
      geri.hidden = veri.fark.length === 0;
      yedekGeriAlGuncelle();
      $("yedek-fark").hidden = false;
      baslik.focus();
    }).catch(hataGoster);
  }

  function yedekGeriAl() {
    var id = S.yedekAcik;
    if (!id || taslakSayi() > 0) { return; }
    istek("/api/geri-al/" + encodeURIComponent(id), {}).then(function (veri) {
      bildir(veri.yedek
        ? "Geri alındı. Yeni yedek: " + veri.yedek + ". Açık terminalleri yeniden başlatın."
        : "Geri alınacak fark yok.");
      yukle();
    }).catch(function (err) {
      hataGoster(err);
      if (err.kod === 409 || err.kod === 500) { yukle(); }
    });
  }

  /* ------------------------------------------------------------ fark (onizleme ve yedek) */

  function gorunenKapsamDeger(v, bosMetin) {
    return (v === null || v === undefined) ? bosMetin : gorunenDeger(v);
  }

  function farkCiz(govde, satirlar) {
    govde.replaceChildren();
    if (!satirlar.length) {
      govde.appendChild(el("p", "aciklama", "Değişiklik yok."));
      return;
    }
    satirlar.forEach(function (s) {
      var kutu = el("div", "fark-satir");
      var baslik = el("div", "fark-baslik");
      baslik.appendChild(el("code", "", s.kapsam + "/" + s.ad));
      var eylem = EYLEM[s.eylem] || { metin: s.eylem, sinif: "" };
      baslik.appendChild(rozet(eylem.metin, eylem.sinif));
      if (s.gizli) { baslik.appendChild(rozet("gizli: değer maskeli", "rozet-uyari")); }
      kutu.appendChild(baslik);

      if (s.path) {
        if (!s.eklenen.length && !s.cikan.length) {
          kutu.appendChild(el("p", "kisa-not", "Girdi sayısı " + s.eski_sayi + " → " + s.yeni_sayi +
            " (yinelenen ya da boş girdiler kaldırılıyor)."));
        }
        if (s.eklenen.length) {
          kutu.appendChild(el("p", "eklenen-etiket", "Eklenecek girdiler:"));
          var eklenen = el("ul");
          s.eklenen.forEach(function (g) { eklenen.appendChild(el("li", "", "+ " + g)); });
          kutu.appendChild(eklenen);
        }
        if (s.cikan.length) {
          kutu.appendChild(el("p", "cikan-etiket", "Çıkacak girdiler:"));
          var cikan = el("ul");
          s.cikan.forEach(function (g) { cikan.appendChild(el("li", "", "− " + g)); });
          kutu.appendChild(cikan);
        }
      } else {
        kutu.appendChild(el("p", "degisim",
          "Eski: " + gorunenKapsamDeger(s.eski, "(yok)") + "   →   Yeni: " + gorunenKapsamDeger(s.yeni, "(silinecek)")));
      }
      govde.appendChild(kutu);
    });
  }

  function onizle() {
    var govde = taslakGovde();
    istek("/api/onizle", govde).then(function (veri) {
      S.onizleme = govde;
      farkCiz($("onizleme-govde"), veri.fark);
      $("onizleme-uygula").textContent = veri.fark.length + " değişikliği uygula";
      $("onizleme").hidden = false;
      $("onizleme-baslik").focus();
      $("onizleme").scrollIntoView({ block: "start" });
      bildir("Önizleme hazır. Uygulamadan önce yedek alınır.");
    }).catch(function (err) {
      hataGoster(err);
      if (err.kod === 409) { yukle(); }
    });
  }

  function uygula() {
    var govde = S.onizleme;
    if (!govde) { return; }
    istek("/api/uygula", govde).then(function (veri) {
      bildir(veri.uygulanan + " değişiklik uygulandı. Yedek: " + veri.yedek +
             ". Yeni açılan terminaller değişikliği görür; açık olanları yeniden başlatın.");
      yukle();
    }).catch(function (err) {
      if (err.kod === 409) {
        bildir(err.message + " Taslak temizlendi; güncel değerlerle yeniden düzenleyin.", true);
        yukle();
      } else if (err.kod === 500) {
        bildir(err.message, true);
        yukle();
      } else {
        hataGoster(err);
      }
    });
  }

  /* ------------------------------------------------------------ yukleme ve cizim */

  function ciz() {
    platformCiz();
    ozetCiz();
    pathCiz();
    komutCiz();
    kapsamSecenekleri();
    degiskenCiz();
    yedekCiz();
    taslakGuncelle();
  }

  /* Her yazmadan sonra ve ilk acilista cagrilir: taslak sifirlanir, veriler tazelenir. */
  function yukle() {
    S.taslak = {};
    S.acik = {};
    S.duzenle = null;
    S.onizleme = null;
    yedekFarkKapat();
    return Promise.all([istek("/api/durum"), istek("/api/degiskenler"), istek("/api/yedekler")])
      .then(function (sonuc) {
        S.durum = sonuc[0];
        S.degiskenler = sonuc[1].degiskenler || [];
        S.yedekler = sonuc[2].yedekler || [];
        satirlariKur();
        ciz();
      })
      .catch(hataGoster);
  }

  /* ------------------------------------------------------------ sekmeler ve olaylar */

  function sekmeSec(ad, odakla) {
    SEKMELER.forEach(function (s) {
      var secili = s === ad;
      var sekme = $("sekme-" + s);
      sekme.setAttribute("aria-selected", secili ? "true" : "false");
      sekme.tabIndex = secili ? 0 : -1;
      $("panel-" + s).hidden = !secili;
    });
    if (odakla) { $("sekme-" + ad).focus(); }
  }

  function sekmeleriBagla() {
    var liste = document.querySelector('[role="tablist"]');
    liste.addEventListener("click", function (e) {
      var hedef = e.target.closest("[data-sekme]");
      if (hedef) { sekmeSec(hedef.getAttribute("data-sekme"), false); }
    });
    liste.addEventListener("keydown", function (e) {
      var mevcut = SEKMELER.indexOf(e.target.getAttribute("data-sekme"));
      if (mevcut < 0) { return; }
      var n = SEKMELER.length;
      var yeni = -1;
      if (e.key === "ArrowRight") { yeni = (mevcut + 1) % n; }
      else if (e.key === "ArrowLeft") { yeni = (mevcut - 1 + n) % n; }
      else if (e.key === "Home") { yeni = 0; }
      else if (e.key === "End") { yeni = n - 1; }
      if (yeni >= 0) {
        e.preventDefault();
        sekmeSec(SEKMELER[yeni], true);
      }
    });
  }

  function olaylariBagla() {
    sekmeleriBagla();

    $("taslak-onizle").addEventListener("click", onizle);
    $("taslak-temizle").addEventListener("click", taslakTemizle);
    $("onizleme-uygula").addEventListener("click", uygula);
    $("onizleme-kapat").addEventListener("click", onizlemeGizle);
    $("yedek-geri-al").addEventListener("click", yedekGeriAl);
    $("yedek-vazgec").addEventListener("click", yedekFarkKapat);
    $("oneri-dugme").addEventListener("click", onerileriUygula);

    $("komut-ara").addEventListener("input", komutCiz);
    $("degisken-kapsam").addEventListener("change", degiskenCiz);
    $("degisken-ara").addEventListener("input", degiskenCiz);
    $("degisken-formu").addEventListener("submit", yeniDegiskenEkle);

    $("dizin-formu").addEventListener("submit", function (e) {
      e.preventDefault();
      var hata = $("dizin-hata");
      var girdi = $("dizin-girdi");
      var metin = girdi.value.trim();
      hata.textContent = "";
      if (!yazilabilir("kullanici")) {
        hata.textContent = "Kullanıcı PATH'i bu kaynakta yazılabilir değil.";
        return;
      }
      if (!metin || metin.length > MAKS_YOL || metin.indexOf("\u0000") >= 0) {
        hata.textContent = "Geçerli bir dizin yolu yazın.";
        return;
      }
      istek("/api/dizin-var", { yol: metin }).then(function (varMi) {
        if (!varMi) {
          hata.textContent = "Dizin bulunamadı: " + metin;
          return;
        }
        if (!dizinEkle(metin, $("dizin-basa").checked)) {
          hata.textContent = "Bu dizin kullanıcı PATH'inde zaten var.";
          return;
        }
        girdi.value = "";
        bildir(metin + " taslağa eklendi. Uygulamadan önce Önizle ile kontrol edin.");
      }).catch(function (err) { hata.textContent = err.message; });
    });
  }

  function baslat() {
    olaylariBagla();
    yukle();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", baslat);
  } else {
    baslat();
  }
})();
