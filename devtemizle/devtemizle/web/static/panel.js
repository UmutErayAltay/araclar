/* devtemizle paneli - davranis katmani (CSP uyumlu, vanilla JS).
   Guvenlik: DOM YALNIZCA createElement + textContent ile kurulur; innerHTML
   YOKTUR. Yol, repo ve tur adlari guvenilmeyen metindir.
   Silme iki adimlidir: once onizleme (onay paneli), sonra acik onay dugmesi.
   Istemci yalnizca sunucunun verdigi kimlikleri (id) gonderir; yol gondermez. */

(function () {
  "use strict";

  var ANKET_MS = 700;
  var SVG_NS = "http://www.w3.org/2000/svg";
  var GRUP_ADI = { js: "JavaScript", python: "Python", rust: "Rust", jvm: "JVM", genel: "Genel" };
  var ATLAMA_NEDEN = {
    "baglanti": "bağlantı, izlenmez",
    "pyvenv-yok": "sanal ortam değil (pyvenv.cfg yok)",
    "kanit-yok": "kanıt dosyası yok"
  };

  var secili = new Map();      /* kimlik -> secim kaydi (yalnizca kimlik + gosterim) */
  var raporVeri = null;        /* son /api/rapor cevabi */
  var acikRepolar = {};        /* yeniden cizimde acik kalacak repo yollari */
  var anketKimlik = null;
  var anketAktif = false;      /* bu sayfa bir is baslatti/izliyor */
  var siliniyor = false;

  /* ----------------------------------------------------------- yardimcilar */

  function byId(kimlik) { return document.getElementById(kimlik); }

  function el(etiket, sinif, metin) {
    var e = document.createElement(etiket);
    if (sinif) { e.className = sinif; }
    if (metin !== undefined && metin !== null) { e.textContent = String(metin); }
    return e;
  }

  function csrfJetonu() {
    var meta = document.querySelector('meta[name="csrf"]');
    return meta ? meta.getAttribute("content") || "" : "";
  }

  /* 1024 tabanli; 1 ondalik; Turkce ondalik virgul. Ornek: 1,4 GB. */
  function boyutYaz(bayt) {
    var n = Number(bayt) || 0;
    if (n < 1024) { return Math.round(n) + " B"; }
    var birimler = ["KB", "MB", "GB"];
    var v = n / 1024;
    var i = 0;
    while (v >= 1024 && i < birimler.length - 1) { v /= 1024; i += 1; }
    return v.toFixed(1).replace(".", ",") + " " + birimler[i];
  }

  /* Gun farkindan goreli yas: bugun, 3 gun once, 2 ay once, 1 yil once. */
  function goreli(gun) {
    if (gun === null || gun === undefined || isNaN(gun)) { return "bilinmiyor"; }
    var g = Math.floor(gun);
    if (g < 1) { return "bugün"; }
    if (g < 30) { return g + " gün önce"; }
    if (g < 365) { return Math.floor(g / 30) + " ay önce"; }
    return Math.floor(g / 365) + " yıl önce";
  }

  function unixGun(saniye) {
    return (Date.now() / 1000 - saniye) / 86400;
  }

  function tamZaman(saniye) {
    try { return new Date(saniye * 1000).toISOString(); } catch (e) { return ""; }
  }

  function repoAdi(yol) {
    var parcalar = String(yol || "").split(/[\\/]/).filter(function (p) { return p.length > 0; });
    return parcalar.length ? parcalar[parcalar.length - 1] : String(yol || "");
  }

  /* Repo koku altindaki gorece yol; kok disi ise tam yol. */
  function gorelYol(yol, repo) {
    if (repo && yol.indexOf(repo) === 0) {
      var r = yol.slice(repo.length).replace(/^[\\/]+/, "");
      return r || ".";
    }
    return yol;
  }

  function kisalt(yol) {
    var s = String(yol || "");
    return s.length > 48 ? "…" + s.slice(s.length - 46) : s;
  }

  function riskRozeti(risk, atlandi) {
    if (atlandi) { return el("span", "rozet bilgi", "atlandı"); }
    if (risk === "guvenli") { return el("span", "rozet guvenli", "güvenli"); }
    if (risk === "dikkat") { return el("span", "rozet dikkat", "dikkat"); }
    return el("span", "rozet bilgi", risk || "bilinmiyor");
  }

  function segSinifi(grup) {
    var g = String(grup || "genel");
    if (/-onbellek$/.test(g)) { return "seg-onbellek"; }
    return ["js", "python", "rust", "jvm", "genel"].indexOf(g) >= 0 ? "seg-" + g : "seg-genel";
  }

  function segEtiketi(grup) {
    var g = String(grup || "genel");
    if (/-onbellek$/.test(g)) {
      var taban = g.replace(/-onbellek$/, "");
      return "Önbellek (" + (GRUP_ADI[taban] || taban) + ")";
    }
    return GRUP_ADI[g] || g;
  }

  /* ------------------------------------------------------------- ag */

  function apiOku(yol) {
    return fetch(yol, { cache: "no-store" }).then(function (cevap) {
      if (!cevap.ok) { throw new Error("HTTP " + cevap.status); }
      return cevap.json();
    });
  }

  function apiGonder(yol, govde) {
    return fetch(yol, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-CSRF": csrfJetonu() },
      body: JSON.stringify(govde || {})
    }).then(function (cevap) {
      return cevap.json().catch(function () { return {}; }).then(function (veri) {
        if (!cevap.ok) { throw new Error(veri.hata || ("HTTP " + cevap.status)); }
        return veri;
      });
    });
  }

  /* ------------------------------------------------- ilerleme ve durum */

  function durumYaz(metin) { byId("durum").textContent = metin || ""; }

  function adimMetni(d) {
    if (d.is === "silme") { return d.n + " öğe siliniyor…"; }
    switch (d.adim) {
      case "kesif": return "Repolar aranıyor…";
      case "repo": return d.i + " / " + d.n + " repo taranıyor…";
      case "meta": return "Git bilgileri okunuyor…";
      case "onbellek": return "Önbellekler ölçülüyor…";
      case "rapor": return "Rapor yazılıyor…";
      default: return "Taranıyor…";
    }
  }

  function ilerlemeKur(d) {
    var satir = byId("ilerleme-satir");
    var pr = byId("ilerleme");
    if (d.is === "bos") { satir.hidden = true; return; }
    satir.hidden = false;
    byId("ilerleme-metin").textContent = adimMetni(d);
    if (d.is === "tarama" && d.n > 0) {
      pr.max = d.n;
      pr.value = d.i;
    } else {
      pr.removeAttribute("value");  /* belirsiz (indeterminate) */
    }
  }

  function anketBaslat() {
    if (anketKimlik !== null) { return; }
    anketKimlik = window.setInterval(anketAdim, ANKET_MS);
  }

  function anketDurdur() {
    if (anketKimlik !== null) {
      window.clearInterval(anketKimlik);
      anketKimlik = null;
    }
  }

  function anketAdim() {
    apiOku("/api/durum").then(function (d) {
      ilerlemeKur(d);
      if (d.is !== "bos") { return; }
      anketDurdur();
      if (anketAktif) {
        anketAktif = false;
        isBitti(d);
      }
    }).catch(function () {
      durumYaz("Sunucuyla bağlantı kurulamadı; yeniden deneniyor…");
    });
  }

  function silmeOzeti(s) {
    var silinen = (s.silindi || []).length;
    var silinemedi = s.silinemedi || [];
    var atlanan = (s.atlanan || []).length;
    var metin = silinen + " öğe silindi (" + boyutYaz(s.bosalan_bayt) + " boşaldı), " +
      silinemedi.length + " silinemedi, " + atlanan + " atlandı.";
    if (silinemedi.length) {
      metin += " İlk neden: " + (silinemedi[0].neden || "bilinmiyor") + ".";
    }
    durumYaz(metin);
  }

  function isBitti(d) {
    siliniyor = false;
    if (d.hata) {
      durumYaz("İşlem başarısız: " + d.hata);
    } else if (d.son_tur === "tara") {
      var t = d.son_sonuc || {};
      durumYaz("Tarama tamamlandı: " + (t.repo_sayisi || 0) + " repo tarandı, " +
        (t.aday_sayisi || 0) + " aday bulundu.");
    } else if (d.son_tur === "sil") {
      silmeOzeti(d.son_sonuc || {});
    }
    if (d.son_tur === "sil") {
      secili.clear();
      onayKapat();
    }
    raporYukle();
  }

  /* ----------------------------------------------------------- rapor */

  function raporYukle() {
    return apiOku("/api/rapor").then(function (veri) {
      raporVeri = veri;
      tumunuCiz();
    }).catch(function () {
      durumYaz("Rapor okunamadı. Sayfayı yenileyin.");
    });
  }

  function raporKaydi() { return (raporVeri && raporVeri.rapor) || null; }

  function kartYaz(kimlik, deger, alt) {
    var kart = byId(kimlik);
    kart.querySelector(".kart-sayi").textContent = deger;
    if (alt !== undefined) { kart.querySelector(".kart-alt").textContent = alt; }
  }

  function ozetKur() {
    var rapor = raporKaydi();
    var ozet = (raporVeri && raporVeri.ozet) || null;
    if (!rapor || !ozet) {
      kartYaz("kart-geri", "–");
      kartYaz("kart-dikkat", "–");
      kartYaz("kart-repo", "–");
      kartYaz("kart-temizlenen", boyutYaz((raporVeri && raporVeri.temizlenen_toplam) || 0));
      return;
    }
    kartYaz("kart-geri", boyutYaz(ozet.geri_kazanilabilir));
    kartYaz("kart-dikkat", boyutYaz(ozet.dikkat_gerektiren));
    kartYaz("kart-repo", String(ozet.taranan_repo || 0), (ozet.aday_sayisi || 0) + " aday");
    kartYaz("kart-temizlenen", boyutYaz(ozet.simdiye_kadar_temizlenen));
  }

  function dagilimKur() {
    var svg = byId("dagilim");
    var lejant = byId("lejant");
    var liste = (raporVeri && raporVeri.dagilim) || [];
    while (svg.firstChild) { svg.removeChild(svg.firstChild); }
    lejant.replaceChildren();

    var toplam = 0;
    liste.forEach(function (g) { toplam += g.boyut || 0; });
    if (!toplam) {
      lejant.appendChild(el("li", "ikincil", "Gösterilecek boyut yok."));
      return;
    }

    var x = 0;
    liste.forEach(function (g) {
      var oran = (g.boyut || 0) / toplam;
      if (oran <= 0) { return; }
      var genislik = oran * 1000;
      var dikdortgen = document.createElementNS(SVG_NS, "rect");
      dikdortgen.setAttribute("x", x.toFixed(2));
      dikdortgen.setAttribute("y", "0");
      dikdortgen.setAttribute("width", genislik.toFixed(2));
      dikdortgen.setAttribute("height", "24");
      dikdortgen.setAttribute("class", segSinifi(g.grup));
      var baslik = document.createElementNS(SVG_NS, "title");
      baslik.textContent = segEtiketi(g.grup) + ": " + boyutYaz(g.boyut);
      dikdortgen.appendChild(baslik);
      svg.appendChild(dikdortgen);
      x += genislik;

      var li = el("li");
      li.appendChild(el("span", "swatch " + segSinifi(g.grup)));
      li.appendChild(el("span", "", segEtiketi(g.grup)));
      li.appendChild(el("span", "sayi", boyutYaz(g.boyut)));
      lejant.appendChild(li);
    });
  }

  function dockerKur() {
    var dl = byId("docker-liste");
    var bos = byId("docker-bos");
    var rapor = raporKaydi();
    var d = rapor && rapor.docker;
    dl.replaceChildren();
    if (!rapor || !d || !d.var) {
      bos.hidden = !rapor;
      return;
    }
    bos.hidden = true;
    var satirlar = [
      ["İmajlar", d.imaj],
      ["Konteynerler", d.konteyner],
      ["Volume'lar", d.volume],
      ["Build önbelleği", d.build_cache]
    ];
    satirlar.forEach(function (s) {
      dl.appendChild(el("dt", "", s[0]));
      dl.appendChild(el("dd", "", boyutYaz(s[1])));
    });
  }

  /* -------------------------------------------------- filtre ve secim */

  function filtreAl() {
    var yas = parseInt(byId("filtre-yas").value, 10);
    if (isNaN(yas) || yas < 0) { yas = 0; }
    return {
      grup: byId("filtre-grup").value,
      yas: yas,
      ara: byId("filtre-ara").value.trim().toLowerCase(),
      guvenli: byId("filtre-guvenli").checked
    };
  }

  function adayGorunur(a, f) {
    if (f.grup && a.grup !== f.grup) { return false; }
    if ((a.yas_gun || 0) < f.yas) { return false; }
    if (f.guvenli && a.risk !== "guvenli") { return false; }
    return true;
  }

  function adaylar() {
    var rapor = raporKaydi();
    return rapor ? (rapor.adaylar || []) : [];
  }

  function adayKaydi(a) {
    var repo = a.repo || "";
    return {
      id: a.id,
      baslik: a.tur,
      boyut: a.boyut || 0,
      risk: a.risk || "dikkat",
      gosterim: repoAdi(repo) + "/" + gorelYol(a.yol, repo),
      dikkat: a.risk === "dikkat"
    };
  }

  function onbellekKaydi(o) {
    return {
      id: o.id,
      baslik: o.ad + " önbelleği",
      boyut: o.boyut || 0,
      risk: o.risk || "dikkat",
      gosterim: o.yol || "genel önbellek",
      dikkat: o.risk === "dikkat"
    };
  }

  function secimDegistir(kayit, kutu) {
    if (kutu.checked) { secili.set(kayit.id, kayit); } else { secili.delete(kayit.id); }
    secimGuncelle();
  }

  function raporKimlikleri() {
    var kumeler = new Set();
    adaylar().forEach(function (a) { kumeler.add(a.id); });
    var rapor = raporKaydi();
    ((rapor && rapor.onbellekler) || []).forEach(function (o) { kumeler.add(o.id); });
    return kumeler;
  }

  function secimGuncelle() {
    var bilinen = raporKimlikleri();
    secili.forEach(function (v, k) { if (!bilinen.has(k)) { secili.delete(k); } });

    var toplam = 0;
    secili.forEach(function (v) { toplam += v.boyut || 0; });
    var n = secili.size;

    byId("secim-cubugu").hidden = n === 0;
    byId("secim-ozet").textContent = n + " öğe seçildi · " + boyutYaz(toplam);
    if (n === 0) { onayKapat(); return; }
    if (!byId("onay").hidden) { onayKur(); }
  }

  function hizliSec() {
    var eklenen = 0;
    adaylar().forEach(function (a) {
      if (a.atlandi || a.risk !== "guvenli" || (a.yas_gun || 0) < 30) { return; }
      if (secili.has(a.id)) { return; }
      secili.set(a.id, adayKaydi(a));
      eklenen += 1;
    });
    yenidenCiz();
    durumYaz(eklenen ? eklenen + " güvenli aday seçildi (30 günden eski)."
      : "30 günden eski seçilebilecek güvenli aday yok.");
  }

  /* ---------------------------------------------------------- repolar */

  function repolariTopla(f) {
    var rapor = raporKaydi();
    var harita = {};
    ((rapor && rapor.repolar) || []).forEach(function (r) {
      harita[r.yol] = { yol: r.yol, son_commit: r.son_commit, kirli: !!r.kirli, adaylar: [] };
    });
    adaylar().forEach(function (a) {
      if (!harita[a.repo]) { harita[a.repo] = { yol: a.repo, son_commit: null, kirli: false, adaylar: [] }; }
      harita[a.repo].adaylar.push(a);
    });
    return Object.keys(harita).map(function (k) { return harita[k]; });
  }

  function adayTablosu(liste, repo) {
    var sarayici = el("div", "tablo-sarayici");
    var tablo = el("table", "tablo aday-tablo");
    tablo.appendChild(el("caption", "gizli", "Aday klasörler: " + repoAdi(repo)));

    var thead = el("thead");
    var basliklar = [
      ["onay-hucre", "Seç"], ["", "Tür ve geri getirme"], ["", "Yol"],
      ["sayi", "Boyut"], ["", "Yaş"], ["", "Risk"]
    ];
    var tr = el("tr");
    basliklar.forEach(function (b) {
      var th = el("th", b[0], b[1]);
      th.setAttribute("scope", "col");
      if (b[0] === "onay-hucre") { th.className = "onay-hucre"; th.textContent = ""; th.appendChild(el("span", "gizli", "Seç")); }
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    tablo.appendChild(thead);

    var govde = el("tbody");
    liste.forEach(function (a) {
      var satir = el("tr", a.atlandi ? "atlandi" : "");
      var hucre = el("td", "onay-hucre");
      if (!a.atlandi) {
        var kutu = el("input");
        kutu.type = "checkbox";
        kutu.checked = secili.has(a.id);
        kutu.setAttribute("aria-label", a.tur + " seç: " + gorelYol(a.yol, a.repo));
        kutu.addEventListener("change", function () { secimDegistir(adayKaydi(a), kutu); });
        hucre.appendChild(kutu);
      }
      satir.appendChild(hucre);

      var tur = el("td", "tur-hucre");
      tur.appendChild(el("code", "", a.tur));
      if (a.atlandi) {
        tur.appendChild(el("span", "geri-getirme", "atlandı: " + (ATLAMA_NEDEN[a.atlandi] || a.atlandi)));
      } else if (a.yeniden) {
        var gg = el("span", "geri-getirme", "geri getirme: ");
        gg.appendChild(el("code", "", a.yeniden));
        tur.appendChild(gg);
      }
      satir.appendChild(tur);

      var yol = el("td", "yol", gorelYol(a.yol, a.repo));
      yol.title = a.yol;
      satir.appendChild(yol);

      satir.appendChild(el("td", "sayi", a.atlandi ? "-" : boyutYaz(a.boyut)));

      var yas = el("td", "", goreli(a.yas_gun));
      if (a.son_erisim) { yas.title = a.son_erisim; }
      satir.appendChild(yas);

      var risk = el("td");
      risk.appendChild(riskRozeti(a.risk, a.atlandi));
      satir.appendChild(risk);
      govde.appendChild(satir);
    });
    tablo.appendChild(govde);
    sarayici.appendChild(tablo);
    return sarayici;
  }

  function repoKutusu(r, gorunur, f) {
    var kutu = el("details", "repo");
    if (acikRepolar[r.yol]) { kutu.open = true; }
    kutu.addEventListener("toggle", function () {
      if (kutu.open) { acikRepolar[r.yol] = true; } else { delete acikRepolar[r.yol]; }
    });

    var ozet = el("summary");
    var ad = el("span", "repo-ad", repoAdi(r.yol));
    ad.title = r.yol;
    ozet.appendChild(ad);

    var commit = el("span", "repo-meta",
      "son commit: " + (r.son_commit ? goreli(unixGun(r.son_commit)) : "bilinmiyor"));
    if (r.son_commit) { commit.title = tamZaman(r.son_commit); }
    ozet.appendChild(commit);

    if (r.kirli) { ozet.appendChild(el("span", "rozet kirli", "değişiklik var")); }

    var toplam = 0;
    gorunur.forEach(function (a) { if (!a.atlandi) { toplam += a.boyut || 0; } });
    var sayi = gorunur.filter(function (a) { return !a.atlandi; }).length;
    ozet.appendChild(el("span", "repo-meta", sayi + " aday"));
    ozet.appendChild(el("span", "repo-boyut", boyutYaz(toplam)));
    kutu.appendChild(ozet);

    var govde = el("div", "repo-govde");
    if (!gorunur.length) {
      govde.appendChild(el("p", "bos-satir", "Bu repoda temizlenecek aday yok."));
    } else {
      govde.appendChild(adayTablosu(gorunur, r.yol));
    }
    kutu.appendChild(govde);
    return kutu;
  }

  function repolarKur(f) {
    var kap = byId("repo-listesi");
    var bosKutu = byId("bos-durum");
    var rapor = raporKaydi();
    kap.replaceChildren();

    if (!rapor) {
      bosKutu.hidden = false;
      byId("bos-metin").textContent = "Henüz tarama yok. Başlamak için Tara'ya bas.";
      return;
    }

    var filtreVar = !!(f.grup || f.yas > 0 || f.guvenli);
    var sirali = repolariTopla(f).map(function (r) {
      var gorunur = r.adaylar.filter(function (a) { return adayGorunur(a, f); });
      var toplam = 0;
      gorunur.forEach(function (a) { if (!a.atlandi) { toplam += a.boyut || 0; } });
      return { r: r, gorunur: gorunur, toplam: toplam };
    }).sort(function (a, b) {
      return b.toplam - a.toplam || a.r.yol.localeCompare(b.r.yol);
    });

    var gosterilen = 0;
    sirali.forEach(function (s) {
      var ad = repoAdi(s.r.yol).toLowerCase();
      if (f.ara && ad.indexOf(f.ara) < 0) { return; }
      if (filtreVar && s.gorunur.length === 0) { return; }
      kap.appendChild(repoKutusu(s.r, s.gorunur, f));
      gosterilen += 1;
    });

    if (!gosterilen) {
      if (filtreVar || f.ara) {
        kap.appendChild(el("p", "bos-satir", "Filtrelerle eşleşen aday yok."));
      } else {
        bosKutu.hidden = false;
        byId("bos-metin").textContent = "Temizlenecek aday bulunamadı.";
        return;
      }
    }
    bosKutu.hidden = true;
  }

  function onbellekKur() {
    var govde = byId("onbellek-govde");
    var bos = byId("onbellek-bos");
    var rapor = raporKaydi();
    govde.replaceChildren();
    var liste = ((rapor && rapor.onbellekler) || []).filter(function (o) { return o.var; });
    byId("onbellek-sarayici").hidden = liste.length === 0;
    bos.hidden = !rapor || liste.length > 0;
    bos.textContent = "Önbellek bulunamadı ya da bu taramada önbellek taraması kapalıydı.";

    liste.forEach(function (o) {
      var satir = el("tr");
      var hucre = el("td", "onay-hucre");
      var kutu = el("input");
      kutu.type = "checkbox";
      kutu.checked = secili.has(o.id);
      kutu.setAttribute("aria-label", o.ad + " önbelleğini seç");
      kutu.addEventListener("change", function () { secimDegistir(onbellekKaydi(o), kutu); });
      hucre.appendChild(kutu);
      satir.appendChild(hucre);

      satir.appendChild(el("td", "", o.ad));
      var yol = el("td", "yol", kisalt(o.yol));
      yol.title = o.yol || "";
      satir.appendChild(yol);
      satir.appendChild(el("td", "sayi", boyutYaz(o.boyut)));

      var risk = el("td");
      risk.appendChild(riskRozeti(o.risk, false));
      satir.appendChild(risk);

      var yontem = el("td", "wrap");
      if (o.komut && o.komut.length) {
        yontem.appendChild(el("code", "", o.komut.join(" ")));
        yontem.appendChild(document.createTextNode(" çalıştırılır"));
      } else {
        yontem.textContent = "klasör silinir";
      }
      satir.appendChild(yontem);
      govde.appendChild(satir);
    });
  }

  function tumunuCiz() {
    ozetKur();
    dagilimKur();
    dockerKur();
    yenidenCiz();
  }

  function yenidenCiz() {
    var f = filtreAl();
    repolarKur(f);
    onbellekKur();
    secimGuncelle();
  }

  /* ------------------------------------------------------- onay paneli */

  var onayEl = null;
  var onayDugme = null;

  function onayAc() {
    if (!secili.size) { return; }
    onayKur();
    onayEl.hidden = false;
    byId("onay-baslik").focus();
  }

  function onayKapat() {
    if (!onayEl || onayEl.hidden) { return; }
    onayEl.hidden = true;
    if (!siliniyor) { byId("onizle").focus(); }
  }

  function onayKur() {
    var liste = byId("onay-liste");
    liste.replaceChildren();
    var toplam = 0;
    var dikkat = false;
    secili.forEach(function (v) {
      toplam += v.boyut || 0;
      if (v.dikkat) { dikkat = true; }
      var li = el("li");
      li.appendChild(el("span", "ad", v.baslik));
      li.appendChild(riskRozeti(v.risk, false));
      li.appendChild(el("span", "sayi", boyutYaz(v.boyut)));
      li.appendChild(el("span", "yol", v.gosterim));
      liste.appendChild(li);
    });

    byId("onay-ozet").textContent = secili.size + " öğe silinecek, toplam " + boyutYaz(toplam) +
      ". Silmeden önce listeyi kontrol edin.";
    byId("onay-dikkat").hidden = !dikkat;

    onayDugme.textContent = secili.size + " öğeyi sil (" + boyutYaz(toplam) + ")";
    onayDugme.disabled = siliniyor;
    byId("vazgec").disabled = siliniyor;
  }

  function silOnayla() {
    if (!secili.size || siliniyor) { return; }
    var idler = [];
    var dikkat = false;
    secili.forEach(function (v) {
      idler.push(v.id);
      if (v.dikkat) { dikkat = true; }
    });
    siliniyor = true;
    onayKur();
    durumYaz("Siliniyor…");
    apiGonder("/api/sil", { idler: idler, dikkat_dahil: dikkat }).then(function () {
      anketAktif = true;
      anketBaslat();
      anketAdim();
    }).catch(function (hata) {
      siliniyor = false;
      onayKur();
      durumYaz("Silme başlatılamadı: " + hata.message);
    });
  }

  /* ------------------------------------------------------------ tara */

  function taraBaslat() {
    var onbellek = byId("onbellek-tara").checked;
    apiGonder("/api/tara", { onbellek: onbellek }).then(function () {
      anketAktif = true;
      durumYaz("Tarama başladı.");
      anketBaslat();
      anketAdim();
    }).catch(function (hata) {
      durumYaz(hata.message);
    });
  }

  function panoyaKopyala() {
    var metin = byId("docker-komut").textContent;
    var not = byId("kopya-not");
    try {
      navigator.clipboard.writeText(metin).then(function () {
        not.textContent = "Kopyalandı.";
      }, function () {
        not.textContent = "Kopyalanamadı; komutu elle seçin.";
      });
    } catch (e) {
      not.textContent = "Kopyalanamadı; komutu elle seçin.";
    }
  }

  /* --------------------------------------------------------- baslat */

  function olaylariBagla() {
    byId("tara-dugme").addEventListener("click", taraBaslat);
    byId("bos-tara").addEventListener("click", taraBaslat);
    byId("hizli-sec").addEventListener("click", hizliSec);
    byId("filtre-grup").addEventListener("change", yenidenCiz);
    byId("filtre-yas").addEventListener("input", yenidenCiz);
    byId("filtre-ara").addEventListener("input", yenidenCiz);
    byId("filtre-guvenli").addEventListener("change", yenidenCiz);
    byId("onizle").addEventListener("click", onayAc);
    byId("vazgec").addEventListener("click", function () { onayKapat(); });
    byId("sil-onay").addEventListener("click", silOnayla);
    byId("komut-kopyala").addEventListener("click", panoyaKopyala);
    document.addEventListener("keydown", function (olay) {
      if (olay.key === "Escape" && onayEl && !onayEl.hidden && !siliniyor) { onayKapat(); }
    });
  }

  function ilkYukle() {
    apiOku("/api/durum").then(function (d) {
      ilerlemeKur(d);
      if (d.is !== "bos") {
        anketAktif = true;
        anketBaslat();
      } else if (d.hata) {
        durumYaz("Son işlem başarısız: " + d.hata);
      }
    }).catch(function () {
      durumYaz("Sunucuyla bağlantı kurulamadı.");
    });
    raporYukle();
  }

  function baslat() {
    onayEl = byId("onay");
    onayDugme = byId("sil-onay");
    olaylariBagla();
    ilkYukle();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", baslat);
  } else {
    baslat();
  }
})();
