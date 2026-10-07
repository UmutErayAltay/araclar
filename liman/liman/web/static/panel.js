/* liman paneli — davranis katmani (CSP uyumlu).
   Guvenlik: HTML dogrudan YAZILMAZ; DOM yalnizca `createElement` +
   `textContent` ile kurulur. Surec adi, komut, IP ve etiket metinleri
   guvenilmeyendir; hicbiri HTML olarak ayristirilmaz.
   CSP `script-src 'self'` oldugu icin bu dosya `static/`ten gelir; satir ici
   script YOKTUR. Panel yalnizca OKUR: hicbir yazma istegi yapmaz. */

(function () {
  "use strict";

  var YENILE_SN = 5;

  /* Metin rozeti: deger YALNIZCA `textContent` ile yazilir. */
  function rozet(metin, sinif) {
    var el = document.createElement("span");
    el.className = sinif;
    el.textContent = metin;
    return el;
  }

  function hucre(deger, sinif) {
    var td = document.createElement("td");
    if (sinif) { td.className = sinif; }
    td.textContent = deger === null || deger === undefined ? "-" : String(deger);
    return td;
  }

  function tabloKur(dinleyenler) {
    var govde = document.getElementById("tablo-govde");
    var bos = document.getElementById("tablo-bos");
    if (!govde || !bos) { return; }

    /* Eski satirlari tek seferde at, sonra yeniden kur. */
    govde.replaceChildren();
    for (var i = 0; i < dinleyenler.length; i++) {
      var s = dinleyenler[i];
      var tr = document.createElement("tr");
      /* Renk + "!" METNI birlikte: renk korlugunde de ayirt edilir. */
      var acik = s.kapsam === "disa_acik";
      if (acik) { tr.className = "disa-acik"; }

      tr.appendChild(hucre(acik ? "! " + s.port : s.port, "port"));
      tr.appendChild(hucre(s.proto));
      tr.appendChild(hucre(acik ? "dışa açık" : "yerel"));
      tr.appendChild(hucre(s.ip, "adres mono"));

      var surec = hucre(s.surec);
      if (s.uyari) {
        surec.appendChild(rozet(" (" + s.uyari + ")", "uyari-not"));
      }
      tr.appendChild(surec);

      tr.appendChild(hucre(s.pid, "sayi"));
      tr.appendChild(hucre(s.bagli, "sayi"));
      tr.appendChild(hucre(s.etiket));
      govde.appendChild(tr);
    }
    bos.hidden = dinleyenler.length > 0;
  }

  function bosPortlariKur(portlar) {
    var liste = document.getElementById("bos-liste");
    if (!liste) { return; }
    liste.replaceChildren();
    for (var i = 0; i < portlar.length; i++) {
      var li = document.createElement("li");
      li.className = "mono";
      li.textContent = String(portlar[i]);
      liste.appendChild(li);
    }
  }

  function ozetKur(ozet) {
    var sayaclar = { "ozet-toplam": ozet.toplam, "ozet-yerel": ozet.yerel, "ozet-disa": ozet.disa_acik };
    for (var id in sayaclar) {
      if (!Object.prototype.hasOwnProperty.call(sayaclar, id)) { continue; }
      var el = document.getElementById(id);
      /* YALNIZCA SAYI yazilir; metin olarak da guvenlidir. */
      if (el) { el.textContent = String(sayaclar[id]); }
    }
  }

  function baglantiNotu(kesik) {
    var not = document.getElementById("baglanti-not");
    if (not) { not.hidden = !kesik; }
  }

  function yenile() {
    fetch("/api/durum", { cache: "no-store" })
      .then(function (cevap) {
        if (!cevap.ok) { throw new Error("HTTP " + cevap.status); }
        return cevap.json();
      })
      .then(function (veri) {
        tabloKur(veri.dinleyenler);
        bosPortlariKur(veri.bos);
        ozetKur(veri.ozet);
        baglantiNotu(false);
      })
      .catch(function () {
        /* Sunucu erisilemiyor: eski veriyi BIRAK, yalnizca notu goster. */
        baglantiNotu(true);
      });
  }

  function baslat() {
    yenile();
    window.setInterval(yenile, YENILE_SN * 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", baslat);
  } else {
    baslat();
  }
})();
