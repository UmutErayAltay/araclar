/* atlas paneli — davranis katmani (CSP uyumlu).
   Guvenlik: hicbir noktada HTML dogrudan yazilmaz; DOM metinleri yalnizca
   `setAttribute`/`style` ile degistirilir. CSP `script-src 'self'` oldugu
   icin bu dosya `static/`ten gelir; satir ici script YOKTUR.

   1) Yogunluk cubuklarinin genisligini `data-genislik` niteliginden tasir
      (satir ici `style` yasak oldugu icin HTML'den tasinamaz).
   2) SUZGEC FORMU: CSP basligi `form-action 'none'` oldugu icin tarayiciya
      yerel form GONDERIMINI kalici olarak engeller (dogrulanmis: native submit
      hicbir sey yapmaz). Bu bir serbestlestirme DEGIL, CSP'nin baglayici
      kuralidir; bu yuzden form JS ile ele alinir:
        - `action`/`method` tanimli kalir (JS kapali olsa da sayfa anlamli);
        - `formaction` YOKTUR — bu CSP'yi acardi;
        - gonderim `location.assign()` ile YAPILIR. Bu bir FORM GONDERIMI
          degil, duz bir gezinmedir; `form-action` yalnizca form gonderimini
          kapsar, bu yuzden CSP'ye uygundur ve tam sayfa yuklemesi yapar.
      Sorgu dizesi YALNIZCA secim listelerinden (`select.name`/`option.value`,
      sunucunun bastirdigi degerler) kurulur; hicbir kullanici metni URL'ye
      girmez. Panel salt goruntulemedir; hicbir ag istegi yapmaz. */

(function () {
  "use strict";

  function cubuklariUygula() {
    var cubuklar = document.querySelectorAll(".cubuk[data-genislik]");
    for (var i = 0; i < cubuklar.length; i++) {
      var cubuk = cubuklar[i];
      var ham = parseFloat(cubuk.getAttribute("data-genislik"));
      if (isNaN(ham)) { continue; }
      // Yalniz SAYI yazilir; `data-genislik` HTML'den maskelenmis bir sayidir.
      var yuzde = Math.min(100, Math.max(0, ham));
      cubuk.style.width = yuzde + "%";
    }
  }

  function suzgecBagla() {
    var form = document.querySelector("form.suzgec");
    if (!form) { return; }
    form.addEventListener("submit", function (olay) {
      // Yerel gonderim CSP tarafindan engellenir; gezinme bizim isimiz.
      olay.preventDefault();
      var parcalar = [];
      var secimler = form.querySelectorAll("select[name], input[name]");
      for (var i = 0; i < secimler.length; i++) {
        var el = secimler[i];
        var ad = el.getAttribute("name");
        var deger = el.value;
        if (!ad || !deger) { continue; }
        // Yalnizca sunucunun bastirdigi secim degerleri kullanilir.
        parcalar.push(encodeURIComponent(ad) + "=" + encodeURIComponent(deger));
      }
      var yol = parcalar.length ? "?" + parcalar.join("&") : "";
      // `location.assign` duz GEZINME yapar (form gonderimi degil) → CSP uyumlu.
      window.location.assign(form.getAttribute("action") + yol);
    });
  }

  function baslat() {
    cubuklariUygula();
    suzgecBagla();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", baslat);
  } else {
    baslat();
  }
})();