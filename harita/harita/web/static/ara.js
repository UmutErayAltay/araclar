// harita /ara — arama kutusu.
//
// CSP `form-action 'none'` yüzünden HTML formu gönderilemez; JS formu
// yakalar ve `location.assign` ile gezinir. Bu bir ağ isteği DEĞİLDİR:
// sayfa aynı sunucudan yeniden yüklenir (CSP gevşetilmez).
//
// DOM'a hiçbir zaman HTML yazılmaz; kullanıcı içeriği tarayıcıya yalnız
// gezinme adresi olarak gider. (Graf JS'inin aksine burada DOM'a metin bile
// yazılmaz: sonuçlar sunucu tarafında render edilir.)

(function () {
  "use strict";
  const form = document.getElementById("ara-form");
  const kutu = document.getElementById("ara-kutu");
  if (!form || !kutu) return;

  form.addEventListener("submit", function (olay) {
    olay.preventDefault();
    const deger = kutu.value.trim();
    // Boş sorgu: `?q=` bile göndermeyelim, ilk durumda kalalım.
    if (!deger) return;
    const adres = new URL(window.location.href);
    adres.search = "";
    adres.searchParams.set("q", deger);
    window.location.assign(adres.pathname + "?" + adres.searchParams.toString());
  });
})();
