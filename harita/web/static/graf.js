/* harita — sıfır bağımlılıklı kuvvet-yönlendirmeli graf (Dalga B + B.1).
 *
 * GÜVENLİK: DOM'a hiçbir kullanıcı metni HTML olarak basılmaz. Başlık, yol,
 * etiket ve özet değerlerinin TAMAMI `textContent` ile yazılır; DOM'a
 * doğrudan öğe (createElement/createElementNS) eklenir.
 *
 * YERLEŞİM (B.1): sabit tur sayılı kuvvet algoritması.
 *   * Başlangıç konumları not id'sinden TÜRETİLEN tohumlu sözde-rastgele
 *     (aynı vault → aynı görüntü; ekran görüntüleri tekrarlanabilir).
 *   * Çekim YAY: kuvvet ∝ (d − L), L = 70.
 *   * İtme Coulomb tipi, ızgara hücresinden TOPLU hesaplanır (O(n)).
 *   * Yerleşim sonunda bağlı bileşenler ayrı ayrı PAKETLENİR (üst üste
 *     binmezler); bağlantısız TEK düğümler (yetimler) alt kenarda düzenli
 *     sıralara dizilir.
 *
 * ETİKET (B.1): ekran puntosu `PUNTO / olcek` ile telafi edilir, yani
 * yakınlaştırma ölçeğinden BAĞIMSIZ sabit ≥11 px olur. Görünürlük derece
 * sırasıyla greedy seçimle belirlenir: kutuları kesişen etiket gizlenir.
 */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";

  // Renk körü-güvenli palet (Okabe-Ito). Sıra sabittir.
  var PALET = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#999999"];
  var DIGER_RENK = "#999999";

  var BOY_MIN = 4;
  var BOY_MAKS = 20;

  var ETIKET_ZUM = 1.15;   // bu ölçeğin üstünde etiket adayları genişler
  var ETIKET_ADET_UZAK = 30;   // uzak görünümde en fazla etiket adayı
  var ETIKET_ADET_YAKIN = 140; // yakın görünümde en fazla etiket adayı
  var PUNTO = 12;          // EKRAN puntosu (px) — telafiden sonra sabit

  var KENAR = 70;          // ideal kenar uzunluğu L (yerleşim uzayı)
  var SIYGAR = 40;         // sığdırma kenar boşluğu (px)
  var OLCEK_MIN = 0.25;
  var OLCEK_MAX = 3;

  var svg = document.getElementById("graf");
  var sahne = document.getElementById("sahne");
  var panel = document.getElementById("panel");
  var panelIcerik = document.getElementById("panel-icerik");
  var panelKapat = document.getElementById("panel-kapat");
  var lejant = document.getElementById("lejant");
  var sigdirDugme = document.getElementById("sigdir");
  var bosDurum = document.getElementById("bos-durum");
  var yukleniyor = document.getElementById("yukleniyor");

  var dugumler = [];
  var kenarlar = [];
  // Katmanlar başlangıçta OLUŞTURULUR; klavye dinleyicisi `dugumG`ye bağlanır
  // ve `hazirla()` içinde bu katman SVG'ye eklenir.
  var dugumG = svgEl("g", "dugum-katmani");
  var kenarG = svgEl("g", "kenar-katmani");
  var kokG = svgEl("g", "kok");
  var indeks = new Map();     // not id -> dugum sırası
  var svgDugum = [];          // <g> düğüm başına
  var svgKenar = [];          // <line> kenar başına
  var svgEtiket = [];         // <text> düğüm başına
  var dugumYaricapi = [];

  var konumX = null, konumY = null;
  var bas = null, hedefDizi = null;
  var kayX = 0, kayY = 0, olcek = 1;
  var secili = -1;
  var sonPunto = 0;
  var etiketSirasi = null;
  var etiketBekleyen = false;

  // --------------------------------------------------------------- yardımcı

  function el(etiket, sinif, metin) {
    var dugum = document.createElement(etiket);
    if (sinif) dugum.className = sinif;
    if (metin !== undefined && metin !== null) dugum.textContent = metin;
    return dugum;
  }

  /* SVG `transform`/`x1` nitelikleri ÜSSEK GÖSTERİMİ kabul etmez:
     `7.2e-7` yazmak Chromium'da "Expected number" hatası verir. Bu yüzden
     her koordinat 2 ondalığa yuvarlanıp sabit nokta biçimine çevrilir. */
  function n(x) {
    return (Math.round(x * 100) / 100).toFixed(2);
  }

  function svgEl(etiket, sinif) {
    var dugum = document.createElementNS(SVG_NS, etiket);
    if (sinif) dugum.setAttribute("class", sinif);
    return dugum;
  }

  /* Not id'sinden TÜRETİLEN tohumlu sözde-rastgele (mulberry32).
     Aynı id → aynı konum: yerleşim her çalıştırmada birebir aynıdır. */
  function tohumla(seed) {
    var a = (seed >>> 0) || 1;
    return function () {
      a = (a + 0x6d2b79f5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ---------------------------------------------------------------- renkler

  function renkleri_hazirla() {
    var sayac = new Map();
    var i;
    for (i = 0; i < dugumler.length; i++) {
      sayac.set(dugumler[i].klasor, (sayac.get(dugumler[i].klasor) || 0) + 1);
    }
    // En yoğun 8 klasör palete girer, kalanlar "diğer".
    var sirali = Array.from(sayac.keys()).sort(function (a, b) {
      var f = sayac.get(b) - sayac.get(a);
      return f !== 0 ? f : (a < b ? -1 : a > b ? 1 : 0);
    });

    var renk = new Map();
    var lejantSatirlari = [];
    for (i = 0; i < sirali.length; i++) {
      if (i < PALET.length) {
        renk.set(sirali[i], PALET[i]);
        lejantSatirlari.push({ ad: sirali[i], renk: PALET[i] });
      } else {
        renk.set(sirali[i], DIGER_RENK);
      }
    }
    var digerSayisi = sirali.length - PALET.length;
    if (digerSayisi > 0) {
      lejantSatirlari.push({ ad: "diğer (" + digerSayisi + ")", renk: DIGER_RENK });
    }
    return { renk: renk, lejant: lejantSatirlari };
  }

  function lejant_ciz(girdiler) {
    while (lejant.firstChild) lejant.removeChild(lejant.firstChild);
    if (!girdiler.length) return;
    lejant.appendChild(el("div", "lejant-ust", "Klasör"));
    for (var i = 0; i < girdiler.length; i++) {
      var satir = el("div", "lejant-satir");
      var kutu = el("span", "lejant-kutu");
      kutu.style.background = girdiler[i].renk;
      satir.appendChild(kutu);
      satir.appendChild(el("span", "lejant-ad", girdiler[i].ad));
      lejant.appendChild(satir);
    }
  }

  // ----------------------------------------------------------------- ölçek

  function govde_kutusu() {
    var r = sahne.getBoundingClientRect();
    return { g: Math.max(r.width, 1), y: Math.max(r.height, 1) };
  }

  /* Panelin KAPLAMADIĞI görünür sahne parçası (SVG yerel koordinatı).
     Masaüstünde panel sağdan, mobilde alttadır; hangisi daha çok yer kaplıyorsa
     o eksen kırpılır. Sığdırma ve seçimde bu alan kullanılır. */
  function gorunur_kutu() {
    var s = sahne.getBoundingClientRect();
    var kutu = { sol: 0, ust: 0, g: Math.max(s.width, 1), y: Math.max(s.height, 1) };
    if (panel.hidden) return kutu;
    var p = panel.getBoundingClientRect();
    var yatay = Math.max(0, Math.min(s.right, p.right) - Math.max(s.left, p.left));
    var dikey = Math.max(0, Math.min(s.bottom, p.bottom) - Math.max(s.top, p.top));
    if (dikey > yatay) kutu.y = Math.max(40, p.top - s.top);
    else kutu.g = Math.max(40, p.left - s.left);
    return kutu;
  }

  function cizim_guncelle() {
    if (!kokG) return;
    kokG.setAttribute("transform", "translate(" + n(kayX) + "," + n(kayY) + ") scale(" + n(olcek) + ")");
    // Yakınlaştıkça etiket adayları genişler, uzaklaştıkça daralır.
    dugumG.setAttribute("data-etiket", olcek >= ETIKET_ZUM ? "hepsi" : "derece");
    // Telafi: ekran puntosu `PUNTO` sabit olsun. Büyük değişimde tüm
    // etiketlerin `font-size` niteliği güncellenir (küçük değişimler atlanır).
    var punto = PUNTO / olcek;
    if (!sonPunto || Math.abs(punto - sonPunto) / sonPunto > 0.02) {
      for (var i = 0; i < svgEtiket.length; i++) {
        svgEtiket[i].setAttribute("font-size", n(punto));
      }
      sonPunto = punto;
    }
    etiketleri_istek();
  }

  function sinirlar() {
    var sol = Infinity, sag = -Infinity, ust = Infinity, alt = -Infinity;
    for (var i = 0; i < dugumler.length; i++) {
      var r = dugumYaricapi[i] || 0;
      if (konumX[i] - r < sol) sol = konumX[i] - r;
      if (konumX[i] + r > sag) sag = konumX[i] + r;
      if (konumY[i] - r < ust) ust = konumY[i] - r;
      if (konumY[i] + r > alt) alt = konumY[i] + r;
    }
    return { sol: sol, sag: sag, ust: ust, alt: alt };
  }

  /* Yerleşim bittiğinde ve pencere yeniden boyutlanınca düğüm sınır kutusu
     görünür sahneye SIYGAR boşlukla sığdırılır (ölçek kelepçeli).
     Kullanıcı kaydırıp yakınlaştırdıktan sonra otomatik sığdırma TEKRAR
     ÇALIŞMAZ; yalnız "Sığdır" düğmesi veya pencere yeniden boyutlanması. */
  function cerceveyi_sigdir() {
    if (!konumX || !dugumler.length) return;
    var g = gorunur_kutu();
    var s = sinirlar();
    var en = Math.max(s.sag - s.sol, 1);
    var boy = Math.max(s.alt - s.ust, 1);
    var yeni = Math.min((g.g - 2 * SIYGAR) / en, (g.y - 2 * SIYGAR) / boy);
    if (!isFinite(yeni) || yeni <= 0) yeni = 1;
    olcek = Math.max(OLCEK_MIN, Math.min(OLCEK_MAX, yeni));
    kayX = g.g / 2 - ((s.sol + s.sag) / 2) * olcek;
    kayY = g.y / 2 - ((s.ust + s.alt) / 2) * olcek;
    cizim_guncelle();
    etiketleri_duzenle();
  }

  // -------------------------------------------------------------- yerleşim

  function ilk_konumlar(n) {
    var xs = new Float64Array(n);
    var ys = new Float64Array(n);
    var ALTIN = Math.PI * (3 - Math.sqrt(5));
    for (var i = 0; i < n; i++) {
      // Tohum KENDİ not id'sinden: aynı vault → aynı başlangıç → aynı görüntü.
      var rnd = tohumla(Math.imul(dugumler[i].id, 2654435761) >>> 0);
      var r = KENAR * 1.7 * Math.sqrt(i + 0.5) * (0.72 + 0.56 * rnd());
      var a = i * ALTIN + (rnd() - 0.5) * 0.7;
      xs[i] = Math.cos(a) * r;
      ys[i] = Math.sin(a) * r;
    }
    return { x: xs, y: ys };
  }

  function hucreAnahtari(gx, gy) {
    return (gx + 32768) * 65536 + (gy + 32768);
  }

  /* Bir tur. İtme kuvveti 3x3 komşu ızgara hücresinden, çekim kuvveti kenarlardan.
   *
   * İki kararlılık kuralı:
   *   1) Kendi hücresi KENDİSİNİN katkısı çıkarılarak hesaplanır; aksi halde
   *      hücrede tek başına duran bir düğüm kendi kendine `1/d²` itme alır ve
   *      yerleşim PATLAR (düğümler milyonlarca birime savrulur).
   *   2) Tur başına yer değiştirme hücre boyutunun yarısıyla sınırlıdır.
   */
  function tur(xs, ys, n, hucre, yagut, cekimKenar, cekimMerkez) {
    var kafes = new Map();
    var i, ox, oy, kutu;

    for (i = 0; i < n; i++) {
      var hucreNo = hucreAnahtari(Math.floor(xs[i] / hucre), Math.floor(ys[i] / hucre));
      kutu = kafes.get(hucreNo);
      if (!kutu) { kutu = { sx: 0, sy: 0, adet: 0 }; kafes.set(hucreNo, kutu); }
      kutu.sx += xs[i];
      kutu.sy += ys[i];
      kutu.adet += 1;
    }

    var enFazla = hucre * 0.5;
    for (i = 0; i < n; i++) {
      var x = xs[i], y = ys[i];
      var gx = Math.floor(x / hucre), gy = Math.floor(y / hucre);
      var kendi = hucreAnahtari(gx, gy);
      var fx = 0, fy = 0;

      for (ox = -1; ox <= 1; ox++) {
        for (oy = -1; oy <= 1; oy++) {
          var anahtar = hucreAnahtari(gx + ox, gy + oy);
          var toplu = kafes.get(anahtar);
          if (!toplu) continue;
          var adet = toplu.adet, mx, my;
          if (anahtar === kendi) {
            adet -= 1;
            if (adet === 0) continue;               // hücrede tek başına: itme yok
            mx = (toplu.sx - x) / adet;
            my = (toplu.sy - y) / adet;
          } else {
            mx = toplu.sx / adet;
            my = toplu.sy / adet;
          }
          var dx = x - mx, dy = y - my;
          var d2 = dx * dx + dy * dy;
          if (d2 < 4) {
            // Neredeyse tam üst üste: sabit, deterministik ayrıştırma.
            dx = ((i % 7) - 3) * 0.5 + 0.7;
            dy = ((i % 5) - 2) * 0.5 + 0.7;
            d2 = dx * dx + dy * dy;
          }
          // Coulomb tipi: kuvvet büyüklüğü ∝ 1/d (çoklu sayım sınırlanır).
          var guc = yagut * adet / d2;
          var sinir = yagut * 6;
          if (guc > sinir) guc = sinir;
          fx += dx * guc;
          fy += dy * guc;
        }
      }

      // Yay: kuvvet ∝ (d − L). Kısa kenarlar uzar, uzun kenarlar kısalır.
      for (var k = bas[i]; k < bas[i + 1]; k++) {
        var diger = hedefDizi[k];
        var ex = xs[diger] - x, ey = ys[diger] - y;
        var uz = Math.sqrt(ex * ex + ey * ey) || 0.01;
        var cek = ((uz - KENAR) / uz) * cekimKenar;
        fx += ex * cek;
        fy += ey * cek;
      }

      fx -= x * cekimMerkez;                       // zayıf merkez çekimi
      fy -= y * cekimMerkez;

      var uzunluk = Math.sqrt(fx * fx + fy * fy);
      if (uzunluk > enFazla) {
        fx = fx / uzunluk * enFazla;
        fy = fy / uzunluk * enFazla;
      }
      xs[i] = x + fx;
      ys[i] = y + fy;
    }
  }

  function komsulari_kur() {
    var n = dugumler.length;
    var sayac = new Int32Array(n);
    var e, a, b, i;
    var gecici = [];
    for (e = 0; e < kenarlar.length; e++) {
      a = indeks.get(kenarlar[e].kaynak);
      b = indeks.get(kenarlar[e].hedef);
      if (a === undefined || b === undefined) continue;
      gecici.push([a, b]);
      sayac[a] += 1;
    }
    bas = new Int32Array(n + 1);
    var toplam = 0;
    for (i = 0; i < n; i++) { bas[i] = toplam; toplam += sayac[i]; }
    bas[n] = toplam;

    hedefDizi = new Int32Array(toplam);
    var doldur = bas.slice(0, n);
    for (e = 0; e < gecici.length; e++) {
      hedefDizi[doldur[gecici[e][0]]++] = gecici[e][1];
    }
  }

  /* Bağlı bileşenler (union-find) — O(n + m). Bileşenler sonra paketlenir. */
  function bilesenleri_kur(n) {
    var ebeveyn = new Int32Array(n);
    var i;
    for (i = 0; i < n; i++) ebeveyn[i] = i;
    for (i = 0; i < n; i++) {
      while (ebeveyn[i] !== i) { ebeveyn[i] = ebeveyn[ebeveyn[i]]; i = ebeveyn[i]; }
    }
    function kok(i) {
      var kok = i;
      while (ebeveyn[kok] !== kok) kok = ebeveyn[kok];
      while (ebeveyn[i] !== kok) { var sonraki = ebeveyn[i]; ebeveyn[i] = kok; i = sonraki; }
      return kok;
    }
    for (i = 0; i < kenarlar.length; i++) {
      var a = indeks.get(kenarlar[i].kaynak);
      var b = indeks.get(kenarlar[i].hedef);
      if (a === undefined || b === undefined) continue;
      var ra = kok(a), rb = kok(b);
      if (ra !== rb) ebeveyn[rb] = ra;
    }
    var koku = new Int32Array(n);
    var siraliKok = new Map();
    for (i = 0; i < n; i++) {
      var r = kok(i);
      if (!siraliKok.has(r)) siraliKok.set(r, siraliKok.size);
      koku[i] = siraliKok.get(r);
    }
    return koku;
  }

  /* Yerleşim sonunda: her bileşen katı bir cisim olarak taşınır.
     Bileşenin SARAN ÇEMBERİ komşusununkine değecek kadar ayrılır, yani
     merkezler arası mesafe > iki yarıçap toplamı (üst üste binme yok). */
  function bilesenleri_paketle(bilesen) {
    var n = dugumler.length;
    var sayi = 0, i;
    var uyeler = [];
    for (i = 0; i < n; i++) {
      if (!uyeler[bilesen[i]]) uyeler[bilesen[i]] = [];
      uyeler[bilesen[i]].push(i);
    }
    sayi = uyeler.length;

    var merkezX = new Float64Array(sayi), merkezY = new Float64Array(sayi), yaricap = new Float64Array(sayi);
    var ana = [], yetimler = [];
    for (var b = 0; b < sayi; b++) {
      var liste = uyeler[b];
      var cx = 0, cy = 0, t;
      for (t = 0; t < liste.length; t++) { cx += konumX[liste[t]]; cy += konumY[liste[t]]; }
      cx /= liste.length; cy /= liste.length;
      var r = 0;
      for (t = 0; t < liste.length; t++) {
        var dx = konumX[liste[t]] - cx, dy = konumY[liste[t]] - cy;
        var d = Math.sqrt(dx * dx + dy * dy) + (dugumYaricapi[liste[t]] || 0);
        if (d > r) r = d;
      }
      merkezX[b] = cx; merkezY[b] = cy; yaricap[b] = r;
      if (liste.length === 1) yetimler.push(b); else ana.push(b);
    }

    var bosluk = KENAR * 0.6;
    // Hedef satır genişliği toplam alandan karekökle bulunur, sonra GÖRÜNÜR
    // SAHNENİN EN/BOY ORANINA göre düzeltilir. Aksi hâlde geniş bir masaüstü
    // penceresinde yerleşim ince-yüksek kalır ve graf ekranın %23'ünü
    // kullanır; oran düzeltmesi grafı hem yatay hem dikeyde doldurur.
    var alan = 0;
    for (b = 0; b < sayi; b++) alan += (2 * yaricap[b]) * (2 * yaricap[b]);
    var gorunur = gorunur_kutu();
    var enBoy = gorunur.g / gorunur.y;
    var hedefG = Math.sqrt(alan) * 1.2;
    if (enBoy > 1.2) hedefG *= Math.min(enBoy, 2.2);
    hedefG = Math.max(KENAR * 3, hedefG);

    // Büyük bileşen önce: raf (shelf) yerleşimi, satırlar ortalanır.
    ana.sort(function (p, q) { return (uyeler[q].length - uyeler[p].length) || (p - q); });
    var hedef = new Array(sayi);
    var satirlar = [], suan = [], suanG = 0, suanY = 0, sonY = 0;
    function satir_kapat() {
      if (!suan.length) return;
      satirlar.push({ liste: suan, g: suanG, y: suanY });
      sonY += suanY + bosluk;
      suan = []; suanG = 0; suanY = 0;
    }
    for (i = 0; i < ana.length; i++) {
      b = ana[i];
      var genislik = 2 * yaricap[b];
      if (suan.length && suanG + genislik > hedefG) satir_kapat();
      suan.push(b);
      suanG += genislik + bosluk;
      if (genislik > suanY) suanY = genislik;
    }
    satir_kapat();

    var toplamG = 0, s;
    for (s = 0; s < satirlar.length; s++) toplamG = Math.max(toplamG, satirlar[s].g);
    toplamG = Math.max(toplamG - bosluk, KENAR);
    var toplamY = Math.max(sonY - bosluk, KENAR);
    var ust = -toplamY / 2;
    for (s = 0; s < satirlar.length; s++) {
      var satir = satirlar[s];
      var x = -toplamG / 2 + (toplamG - satir.g) / 2;
      for (i = 0; i < satir.liste.length; i++) {
        b = satir.liste[i];
        hedef[b] = { x: x + yaricap[b], y: ust + yaricap[b] };
        x += 2 * yaricap[b] + bosluk;
      }
      ust += satir.y + bosluk;
    }

    // Bağlantısız TEK düğümler: ana bloğun ALTINDA düzenli sıralar hâlinde
    // (grafın ortasında dağınık kalmazlar).
    var aralik = KENAR * 1.35;
    var satirda = Math.max(1, Math.min(20, Math.round(toplamG / aralik)));
    var yUst = toplamY / 2 + aralik;
    for (i = 0; i < yetimler.length; i++) {
      b = yetimler[i];
      var sutun = i % satirda;
      var sira = Math.floor(i / satirda);
      var satirGenislik = Math.min(satirda, yetimler.length - sira * satirda);
      hedef[b] = {
        x: -toplamG / 2 + aralik * (sutun + 0.5) - aralik / 2 + (toplamG - satirGenislik * aralik) / 2,
        y: yUst + sira * aralik * 1.25
      };
    }

    for (b = 0; b < sayi; b++) {
      if (!hedef[b]) { hedef[b] = { x: 0, y: 0 }; }
      var dd = hedef[b].x - merkezX[b];
      var ee = hedef[b].y - merkezY[b];
      var liste = uyeler[b];
      for (var j = 0; j < liste.length; j++) {
        konumX[liste[j]] += dd;
        konumY[liste[j]] += ee;
      }
    }
  }

  /* Yerleşim: her karede birkaç tur, arada nefes. */
  function yerlestir(tamamlaninca) {
    var n = dugumler.length;
    komsulari_kur();
    var bilesen = bilesenleri_kur(n);
    var ilk = ilk_konumlar(n);
    konumX = ilk.x;
    konumY = ilk.y;

    var TURLER = n > 1500 ? 140 : n > 600 ? 190 : 240;
    var KARE_TUR = 10;
    var turNo = 0;
    var baslangic = performance.now();

    function adim() {
      var kalan = TURLER - turNo;
      var bu = Math.min(KARE_TUR, kalan);
      for (var t = 0; t < bu; t++) {
        var soguma = 1 - turNo / TURLER;
        tur(konumX, konumY, n,
            KENAR * (0.95 + 0.75 * soguma),                  // ızgara hücre boyutu
            KENAR * KENAR * 0.0032 * (1 + 1.6 * soguma),     // itme
            0.06, 0.0016,                                    // kenar çekimi, merkez çekimi
            );
        turNo += 1;
      }
      pozisyonlari_ciz();
      if (turNo < TURLER) {
        requestAnimationFrame(adim);
      } else {
        bilesenleri_paketle(bilesen);
        pozisyonlari_ciz();
        cerceveyi_sigdir();
        tamamlaninca(performance.now() - baslangic);
      }
    }
    requestAnimationFrame(adim);
  }

  function pozisyonlari_ciz() {
    var i, e, a, b, cizgi;
    for (i = 0; i < dugumler.length; i++) {
      svgDugum[i].setAttribute("transform", "translate(" + n(konumX[i]) + "," + n(konumY[i]) + ")");
    }
    for (e = 0; e < kenarlar.length; e++) {
      a = indeks.get(kenarlar[e].kaynak);
      b = indeks.get(kenarlar[e].hedef);
      if (a === undefined || b === undefined) continue;
      cizgi = svgKenar[e];
      cizgi.setAttribute("x1", n(konumX[a]));
      cizgi.setAttribute("y1", n(konumY[a]));
      cizgi.setAttribute("x2", n(konumX[b]));
      cizgi.setAttribute("y2", n(konumY[b]));
    }
  }

  // ---------------------------------------------------------------- çizim

  function dugumleri_ciz(renkler) {
    var maxDerece = 1;
    var i;
    for (i = 0; i < dugumler.length; i++) {
      if (dugumler[i].derece > maxDerece) maxDerece = dugumler[i].derece;
    }
    etiketSirasi = [];
    for (i = 0; i < dugumler.length; i++) {
      var d = dugumler[i];
      var oran = Math.sqrt(Math.min(d.derece, maxDerece) / maxDerece);
      var yaricap = BOY_MIN + (BOY_MAKS - BOY_MIN) * oran;
      dugumYaricapi[i] = yaricap;

      var grup = svgEl("g", "dugum");
      grup.setAttribute("tabindex", "0");
      grup.setAttribute("role", "button");
      grup.setAttribute("data-id", String(d.id));
      grup.setAttribute("data-derece", String(d.derece));
      grup.setAttribute("aria-label", d.baslik + " — " + d.derece + " bağlantı");
      grup.setAttribute("transform", "translate(0,0)");

      var halka = svgEl("circle", "dugum-halka");
      halka.setAttribute("r", n(yaricap + 4));
      grup.appendChild(halka);

      var daire = svgEl("circle", "dugum-daire");
      daire.setAttribute("r", n(yaricap));
      daire.setAttribute("fill", renkler.get(d.klasor) || DIGER_RENK);
      grup.appendChild(daire);

      var etiket = svgEl("text", "dugum-etiket");
      etiket.setAttribute("x", n(yaricap + 6));
      etiket.setAttribute("y", "4");
      // Görünürlük JS tarafından greedy çakışma önlemeyle YAZILIR; başlangıçta
      // gizli. `data-etiket` özniteliği artık GEREKMEZ (CSS seçicisi kalktı).
      etiket.setAttribute("opacity", "0");
      etiket.textContent = d.baslik;   // textContent: HTML kaçışı YOK
      grup.appendChild(etiket);

      dugumG.appendChild(grup);
      svgDugum.push(grup);
      svgEtiket.push(etiket);
      etiketSirasi.push(i);
    }
    // Derece AZALAN, eşitlikte id artan — etiket öncelik sırası (kararlı).
    etiketSirasi.sort(function (p, q) {
      return (dugumler[q].derece - dugumler[p].derece) || (dugumler[p].id - dugumler[q].id);
    });
  }

  function kenarlari_ciz() {
    for (var e = 0; e < kenarlar.length; e++) {
      var cizgi = svgEl("line", "kenar");
      kenarG.appendChild(cizgi);
      svgKenar.push(cizgi);
    }
  }

  // ------------------------------------------------------------- etiketler

  /* Görünürlük, derece sırasıyla GREEDY seçimle belirlenir:
     kutuları daha önce yerleştirilmiş bir etiketle KESİŞEN etiket gizlenir.
     Yakınlaştıkça kutular ekrana yayılır, çakışma azalır, daha fazlası görünür.
     Seçili düğümün etiketi HER ZAMAN görünür (ilk sırada yerleştirilir). */
  function etiketleri_duzenle() {
    if (!konumX || !etiketSirasi || !etiketSirasi.length) return;
    // Uzak görünümde aday sayısı SINIRLANIR: az sayıda etiket, geniş kutular.
    // Sınır küçük grafı tamamen susturmamalı, büyük grafta da maliyeti
    // sınırlı kalmalı: iki sınırın ORTASI alınır.
    var hepsi = dugumG.getAttribute("data-etiket") === "hepsi";
    var sinir = hepsi ? ETIKET_ADET_YAKIN : ETIKET_ADET_UZAK;
    sinir = Math.max(sinir, Math.round((etiketSirasi.length + 1) / 2));
    var aday = [];
    var i;
    for (i = 0; i < etiketSirasi.length && aday.length < sinir; i++) {
      aday.push(etiketSirasi[i]);
    }

    // Seçili düğüm her zaman adayların başında.
    if (secili >= 0) {
      var yer = aday.indexOf(secili);
      if (yer > 0) { aday.splice(yer, 1); aday.unshift(secili); }
      else if (yer < 0) aday.unshift(secili);
    }

    // ÖNCE hepsini ölç (tek düzen), SONRA yaz: ölçüm/yazma iç içe geçmez.
    var kutular = new Array(aday.length);
    for (i = 0; i < aday.length; i++) kutular[i] = svgEtiket[aday[i]].getBoundingClientRect();

    var sahneKutu = sahne.getBoundingClientRect();
    var yerlesmis = [];
    var goster = new Array(dugumler.length);
    for (i = 0; i < goster.length; i++) goster[i] = null;

    for (i = 0; i < aday.length; i++) {
      var sira2 = aday[i];
      var k = kutular[i];
      // Sahne dışındaysa gösterme (kaydırılmış etiketler ekranı kirletmesin).
      if (k.width === 0 || k.right < sahneKutu.left || k.left > sahneKutu.right
          || k.bottom < sahneKutu.top || k.top > sahneKutu.bottom) {
        continue;
      }
      var cakisiyor = false;
      for (var j = 0; j < yerlesmis.length; j++) {
        var o = yerlesmis[j];
        if (k.left < o.right && o.left < k.right && k.top < o.bottom && o.top < k.bottom) {
          cakisiyor = true;
          break;
        }
      }
      if (cakisiyor) continue;
      yerlesmis.push(k);
      goster[sira2] = 1;
    }

    for (i = 0; i < svgEtiket.length; i++) {
      var gorunur = goster[i] === 1;
      svgEtiket[i].setAttribute("opacity", gorunur ? "1" : "0");
    }
  }

  function etiketleri_istek() {
    if (etiketBekleyen) return;
    etiketBekleyen = true;
    requestAnimationFrame(function () {
      etiketBekleyen = false;
      etiketleri_duzenle();
    });
  }

  // ----------------------------------------------------------- etkileşim

  function ekran_noktasi(olay) {
    var kutu = svg.getBoundingClientRect();
    return { x: olay.clientX - kutu.left, y: olay.clientY - kutu.top };
  }

  function yerlestirici_ara(x, y) {
    var gx = (x - kayX) / olcek;
    var gy = (y - kayY) / olcek;
    var en = Infinity, bulunan = -1, i;
    for (i = 0; i < dugumler.length; i++) {
      var dx = konumX[i] - gx, dy = konumY[i] - gy;
      var d2 = dx * dx + dy * dy;
      var esik = dugumYaricapi[i] + 8 / olcek;
      if (d2 < esik * esik && d2 < en) { en = d2; bulunan = i; }
    }
    return bulunan;
  }

  function uzaklastir(carpan, nokta) {
    var yeni = Math.max(OLCEK_MIN, Math.min(OLCEK_MAX, olcek * carpan));
    var gercek = yeni / olcek;
    kayX = nokta.x - (nokta.x - kayX) * gercek;
    kayY = nokta.y - (nokta.y - kayY) * gercek;
    olcek = yeni;
    cizim_guncelle();
  }

  var parmaklar = new Map();   // pointerId -> {x, y} (pinch için)
  var suruklenen = -1;
  var tik = null;
  var kaydirma = null;
  var sonParmakMesafe = 0;

  svg.addEventListener("pointerdown", function (olay) {
    if (!kokG) return;
    parmaklar.set(olay.pointerId, ekran_noktasi(olay));
    if (olay.pointerType === "touch") {
      if (parmaklar.size === 2) {
        suruklenen = -1; kaydirma = null; tik = null;
        sonParmakMesafe = parmak_mesafesi();
        return;
      }
      if (parmaklar.size > 2) return;
    }
    var nokta = ekran_noktasi(olay);
    // `setPointerCapture` yalnız GERÇEK etkin pointer için çalışır; sentetik
    // olaylarda (ve bazı tarayıcılarda) "No active pointer" fırlatır.
    try {
      svg.setPointerCapture(olay.pointerId);
    } catch (hata) { /* yakalama yok: sürükleme yine de çalışır */ }
    var n = nokta;
    var sira = yerlestirici_ara(n.x, n.y);
    if (sira >= 0) {
      suruklenen = sira;
      tik = { x: olay.clientX, y: olay.clientY, hareket: 0 };
    } else {
      kaydirma = { x: n.x, y: n.y, kayX: kayX, kayY: kayY };
    }
  });

  function parmak_mesafesi() {
    var noktalar = Array.from(parmaklar.values());
    if (noktalar.length < 2) return 0;
    return Math.hypot(noktalar[0].x - noktalar[1].x, noktalar[0].y - noktalar[1].y);
  }

  function parmak_ortasi() {
    var noktalar = Array.from(parmaklar.values());
    if (noktalar.length < 2) return null;
    return { x: (noktalar[0].x + noktalar[1].x) / 2, y: (noktalar[0].y + noktalar[1].y) / 2 };
  }

  svg.addEventListener("pointermove", function (olay) {
    if (!kokG) return;
    if (parmaklar.has(olay.pointerId)) parmaklar.set(olay.pointerId, ekran_noktasi(olay));

    if (parmaklar.size >= 2) {
      var mesafe = parmak_mesafesi();
      var orta = parmak_ortasi();
      if (sonParmakMesafe > 0 && mesafe > 0 && orta) {
        uzaklastir(mesafe / sonParmakMesafe, orta);
      }
      sonParmakMesafe = mesafe;
      return;
    }

    if (suruklenen >= 0) {
      var p = ekran_noktasi(olay);
      konumX[suruklenen] = (p.x - kayX) / olcek;
      konumY[suruklenen] = (p.y - kayY) / olcek;
      tik.hareket += Math.abs(olay.clientX - tik.x) + Math.abs(olay.clientY - tik.y);
      svgDugum[suruklenen].setAttribute(
        "transform", "translate(" + n(konumX[suruklenen]) + "," + n(konumY[suruklenen]) + ")");
      kenarlari_guncelle();
      etiketleri_istek();
    } else if (kaydirma) {
      var k = ekran_noktasi(olay);
      kayX = kaydirma.kayX + (k.x - kaydirma.x);
      kayY = kaydirma.kayY + (k.y - kaydirma.y);
      cizim_guncelle();
    }
  });

  function birmak_bit(olay) {
    parmaklar.delete(olay.pointerId);
    if (parmaklar.size < 2) sonParmakMesafe = 0;

    if (suruklenen >= 0) {
      if (tik && tik.hareket < 6) dugum_sec(suruklenen);
      suruklenen = -1;
      tik = null;
    } else {
      kaydirma = null;
    }
  }

  svg.addEventListener("pointerup", birmak_bit);
  svg.addEventListener("pointercancel", function (olay) {
    parmaklar.delete(olay.pointerId);
    suruklenen = -1; tik = null; kaydirma = null; sonParmakMesafe = 0;
  });

  // Boş alana tıklayınca panel kapanır (düğüm seçili değilse).
  svg.addEventListener("click", function (olay) {
    if (!kokG) return;
    var n = ekran_noktasi(olay);
    if (yerlestirici_ara(n.x, n.y) < 0 && !panel.hidden) panel_kapat();
  });

  svg.addEventListener("wheel", function (olay) {
    if (!kokG) return;
    olay.preventDefault();
    uzaklastir(olay.deltaY < 0 ? 1.12 : 1 / 1.12, ekran_noktasi(olay));
  }, { passive: false });

  // Klavye olayları `<g class="dugum">` çocuklarında oluşur; dinleyici
  // doğrudan dugumG'ye bağlanır (bu katman `hazirla()` içinde oluşturulur).
  dugumG.addEventListener("keydown", function (olay) {
    if (olay.key !== "Enter" && olay.key !== " ") return;
    // `data-id` ODAKLANAN düğümün üzerindedir, dinleyicinin bağlandığı
    // katmanın değil: `currentTarget` katmandır (kimlik taşımaz).
    var dugum = olay.target && olay.target.closest ? olay.target.closest(".dugum") : null;
    if (!dugum) return;
    olay.preventDefault();
    dugum_sec(indeks.get(parseInt(dugum.getAttribute("data-id"), 10)));
  });

  document.addEventListener("keydown", function (olay) {
    if (olay.key === "Escape" && !panel.hidden) panel_kapat();
  });

  panelKapat.addEventListener("click", function () { panel_kapat(); });

  /* "Sığdır": kullanıcı kaydırıp yakınlaştırdıktan sonra otomatik sığdırma
     tekrarlanmaz; bu düğme klavyeyle erişilebilir (gerçek `<button>`). */
  sigdirDugme.addEventListener("click", function () { cerceveyi_sigdir(); });

  // ---------------------------------------------------------------- panel

  function dugumu_gorunur_alana_getir(sira) {
    if (sira < 0) return;
    var g = gorunur_kutu();
    olcek = Math.max(olcek, 0.9);
    if (olcek > OLCEK_MAX) olcek = OLCEK_MAX;
    kayX = g.g / 2 - konumX[sira] * olcek;
    kayY = g.y / 2 - konumY[sira] * olcek;
    cizim_guncelle();
  }

  function dugum_sec(sira) {
    if (sira === undefined || sira === null || sira < 0 || sira >= dugumler.length) return;
    for (var i = 0; i < svgDugum.length; i++) {
      if (i === sira) svgDugum[i].classList.add("dugum-secili");
      else svgDugum[i].classList.remove("dugum-secili");
    }
    secili = sira;

    dugumu_gorunur_alana_getir(sira);

    panel_ac(dugumler[sira].id);
  }

  function panel_ac(notId) {
    fetch("/api/not/" + encodeURIComponent(notId), { credentials: "omit" })
      .then(function (c) { return c.ok ? c.json() : null; })
      .then(function (veri) {
        if (!veri) return;
        panel_ici(veri);
        panel.hidden = false;
        // Panel İÇİ kaydırma en üstte başlar (B.1: içerik başlık çubuğunun
        // altında kalmasın). Panel açılınca görünür alan daraldığı için
        // seçili düğüm yeniden ortalanır — panelin ARKASINA düşmez.
        panel.scrollTop = 0;
        dugumu_gorunur_alana_getir(secili);
        etiketleri_istek();
        panelKapat.focus();
      })
      .catch(function () { /* ağ hatası: panel açılmaz, graf çalışır */ });
  }

  function panel_kapat() {
    panel.hidden = true;
    while (panelIcerik.firstChild) panelIcerik.removeChild(panelIcerik.firstChild);
    if (secili >= 0 && svgDugum[secili]) {
      svgDugum[secili].classList.remove("dugum-secili");
      svgDugum[secili].focus();
    }
    secili = -1;
    etiketleri_istek();
  }

  function baglanti_listesi(baslik, ogeler, bosMetin) {
    var bolum = el("section", "panel-bolum");
    bolum.appendChild(el("h3", null, baslik));
    var liste = el("ul", "panel-listesi");
    if (!ogeler || !ogeler.length) {
      liste.appendChild(el("li", "bos", bosMetin));
    } else {
      for (var i = 0; i < ogeler.length; i++) {
        var li = el("li");
        var dugum = indeks.get(ogeler[i].id);
        if (dugum === undefined) {
          li.appendChild(el("span", "bos", ogeler[i].baslik));
        } else {
          var dugumAd = dugumler[dugum];
          var dugumEl = el("button", "panel-bag", dugumAd.baslik);
          dugumEl.type = "button";
          dugumEl.setAttribute("data-hedef-id", String(dugumAd.id));
          dugumEl.addEventListener("click", function () {
            dugum_sec(indeks.get(parseInt(this.getAttribute("data-hedef-id"), 10)));
          });
          li.appendChild(dugumEl);
        }
        liste.appendChild(li);
      }
    }
    bolum.appendChild(liste);
    return bolum;
  }

  function panel_ici(veri) {
    while (panelIcerik.firstChild) panelIcerik.removeChild(panelIcerik.firstChild);

    panelIcerik.appendChild(el("h2", null, veri.baslik));
    panelIcerik.appendChild(el("span", "yol", veri.yol));

    if (veri.etiketler && veri.etiketler.length) {
      var etiketler = el("div", "panel-etiketler");
      for (var t = 0; t < veri.etiketler.length; t++) {
        etiketler.appendChild(el("span", "etiket", "#" + veri.etiketler[t]));
      }
      panelIcerik.appendChild(etiketler);
    }

    panelIcerik.appendChild(el("p", "panel-ozet", veri.ozet || "(bu notta gövde yok)"));
    // Karar Q4: özet kesildiyse devamı olduğu AÇIKÇA yazılır.
    if (veri.ozet_kesildi) {
      panelIcerik.appendChild(el("p", "ozet-devam", "… (devamı notta)"));
    }
    panelIcerik.appendChild(baglanti_listesi("Giden linkler", veri.giden, "çözülen giden link yok"));
    panelIcerik.appendChild(baglanti_listesi("Gelen linkler", veri.gelen, "bu nota link veren yok"));

    if (veri.kirik && veri.kirik.length) {
      var kirikBolum = el("section", "panel-bolum");
      kirikBolum.appendChild(el("h3", null, "Kırık linkler"));
      var liste = el("ul", "panel-listesi");
      for (var k = 0; k < veri.kirik.length; k++) {
        var li = el("li");
        li.appendChild(el("span", "panel-kirik", "[[" + veri.kirik[k] + "]]"));
        liste.appendChild(li);
      }
      kirikBolum.appendChild(liste);
      panelIcerik.appendChild(kirikBolum);
    }
  }

  // -------------------------------------------------------------- başlatma

  function hazirla(baslangic) {
    if (!dugumler.length) {
      yukleniyor.hidden = true;
      bosDurum.hidden = false;
      sigdirDugme.hidden = true;
      hazir_bildir(0, 0, 0);
      return;
    }
    sigdirDugme.hidden = false;
    var renkler = renkleri_hazirla();
    lejant_ciz(renkler.lejant);
    dugumleri_ciz(renkler.renk);
    kenarlari_ciz();

    var dugumBitti = performance.now();
    yerlestir(function (sure) {
      yukleniyor.hidden = true;
      bosDurum.hidden = true;
      var acik = document.body.getAttribute("data-acik-not") || "";
      if (/^[0-9]+$/.test(acik)) {
        var sira = indeks.get(parseInt(acik, 10));
        if (sira !== undefined) dugum_sec(sira);
      }
      hazir_bildir(dugumBitti - baslangic, sure, dugumler.length);
    });
  }

  function hazir_bildir(node_ms, layout_ms, adet) {
    // E2E testleri ve performans ölçümü bu işareti bekler.
    window.__harita = {
      tamam: true,
      dugum: adet,
      kenar: kenarlar.length,
      dugumMs: Math.round(node_ms),
      yerlesimMs: Math.round(layout_ms),
      ilkCizimMs: Math.round(node_ms + layout_ms)
    };
    document.body.setAttribute("data-hazir", "1");
  }

  window.addEventListener("resize", function () {
    if (dugumler.length && konumX) cerceveyi_sigdir();
  });

  var baslangic = performance.now();
  fetch("/api/graf", { credentials: "omit" })
    .then(function (c) { return c.json(); })
    .then(function (veri) {
      dugumler = veri.dugumler || [];
      kenarlar = veri.kenarlar || [];
      var i;
      for (i = 0; i < dugumler.length; i++) indeks.set(dugumler[i].id, i);
      dugumYaricapi = new Float64Array(dugumler.length);

      kokG.appendChild(kenarG);
      kokG.appendChild(dugumG);
      svg.appendChild(kokG);
      hazirla(baslangic);
    })
    .catch(function () {
      yukleniyor.hidden = true;
      bosDurum.hidden = false;
      sigdirDugme.hidden = true;
      var baslik = bosDurum.querySelector("h2");
      if (baslik) baslik.textContent = "Graf yüklenemedi";
      document.body.setAttribute("data-hazir", "hata");
    });
})();