/* orkestra paneli — küçük davranış katmanı.
   Güvenlik: hiçbir noktada `innerHTML` YOK; metinler `textContent` ile yazılır.
   CSP `script-src 'self'` olduğu için bu dosya `static/`ten gelir, satır içi
   script yoktur. Tek iş: ilerleme çubuklarının genişliğini `data-genislik`
   niteliğinden taşımak (satır içi `style` yasak olduğu için HTML'den
   taşınamıyor). Başka hiçbir şey yapılmaz — panel salt görüntülemedir. */

(function () {
  "use strict";

  function ilerlemeCubuklariniUygula() {
    var cubuklar = document.querySelectorAll(".ilerleme i[data-genislik]");
    for (var i = 0; i < cubuklar.length; i++) {
      var cubuk = cubuklar[i];
      var ham = parseFloat(cubuk.getAttribute("data-genislik"));
      if (isNaN(ham)) { continue; }
      // Yalnız sayı yazılır; `data-genislik` HTML'den maskelenmiş bir sayıdır.
      var yuzde = Math.min(100, Math.max(0, ham));
      cubuk.style.width = yuzde + "%";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ilerlemeCubuklariniUygula);
  } else {
    ilerlemeCubuklariniUygula();
  }
})();
