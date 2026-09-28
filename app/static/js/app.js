(() => {
  "use strict";

  const state = {
    items: [],
    kind: "",
    status: "",
    q: "",
  };

  const grid = document.getElementById("grid");
  const emptyState = document.getElementById("empty-state");
  const toast = document.getElementById("toast");
  const addForm = document.getElementById("add-form");
  const addTitle = document.getElementById("add-title");
  const addKind = document.getElementById("add-kind");
  const addStatus = document.getElementById("add-status");
  const search = document.getElementById("search");
  const kindChips = document.getElementById("kind-chips");
  const statusChips = document.getElementById("status-chips");

  const KIND_LABELS = { film: "Film", dizi: "Dizi", anime: "Anime", kitap: "Kitap" };
  const STATUS_LABELS = {
    planlanan: "Planlanan",
    izleniyor: "İzleniyor",
    tamamlandi: "Tamamlandı",
    birakildi: "Bırakıldı",
  };

  const SOURCE_LABELS = { tmdb: "TMDB", openlibrary: "Open Library" };

  // Arama uç noktası bu alanları dönmüyorsa sonuç yine başlıkla gösterilir,
  // yalnızca poster/kimlik ve dolayısıyla "nerede izlerim" butonu eksik kalır.
  const API_BASE = "/api";
  const SEARCH_FIELDS = ["title", "year", "poster_url", "external_id", "external_source", "author"];

  let toastTimer = null;
  function showToast(message) {
    toast.textContent = message;
    toast.classList.remove("hidden");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add("hidden"), 4000);
  }

  async function apiFetch(path, options) {
    let res;
    try {
      res = await fetch(path, options);
    } catch (err) {
      showToast("Sunucuya ulaşılamadı — ağ hatası.");
      throw err;
    }
    if (res.status === 204) return null;
    let data = null;
    try {
      data = await res.json();
    } catch (err) {
      // no body
    }
    if (!res.ok) {
      const message = (data && data.detail) || `İstek başarısız oldu (${res.status}).`;
      showToast(message);
      throw Object.assign(new Error(message), { status: res.status });
    }
    return data;
  }

  // Faz A uç noktaları; yalnızca hata durumunda toast gösterir (sessizce yutulmaz).
  async function apiGetSilent(path) {
    let res;
    try {
      res = await fetch(path);
    } catch (err) {
      throw new Error("Sunucuya ulaşılamadı — ağ hatası.");
    }
    if (res.status === 204) return null;
    let data = null;
    try {
      data = await res.json();
    } catch (err) {
      // no body
    }
    if (!res.ok) {
      throw Object.assign(new Error((data && data.detail) || `İstek başarısız oldu (${res.status}).`), {
        status: res.status,
        detail: (data && data.detail) || null,
      });
    }
    return data;
  }

  function buildQuery() {
    const params = new URLSearchParams();
    if (state.kind) params.set("kind", state.kind);
    if (state.status) params.set("status", state.status);
    if (state.q) params.set("q", state.q);
    const qs = params.toString();
    return qs ? `/api/items?${qs}` : "/api/items";
  }

  async function loadItems() {
    try {
      const data = await apiFetch(buildQuery());
      state.items = (data && data.items) || [];
      render();
    } catch (err) {
      // hata zaten toast ile gösterildi
    }
  }

  function starsHtml(itemId, rating) {
    const r = rating || 0;
    let html = '<div class="stars">';
    for (let i = 1; i <= 5; i++) {
      html += `<button type="button" class="star${i <= r ? " filled" : ""}" data-id="${itemId}" data-value="${i}" aria-label="${i} yıldız">★</button>`;
    }
    html += "</div>";
    return html;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  function cardInnerHtml(item) {
    const sourceLabel = SOURCE_LABELS[item.external_source] || item.external_source;
    const canWatch = Boolean(item.external_id) && item.kind !== "kitap";
    const body = `
      <div class="card-top">
        <div class="card-title">${escapeHtml(item.title)}</div>
        <button type="button" class="delete-btn" data-id="${item.id}" title="Sil" aria-label="Sil">✕</button>
      </div>
      <div class="badges">
        <span class="badge badge-kind">${KIND_LABELS[item.kind] || item.kind}</span>
        <span class="badge badge-status" data-status="${item.status}">${STATUS_LABELS[item.status] || item.status}</span>
        ${item.external_source ? `<span class="badge badge-source">${escapeHtml(sourceLabel)}</span>` : ""}
      </div>
      <select class="status-select" data-id="${item.id}">
        ${Object.entries(STATUS_LABELS)
          .map(
            ([value, label]) =>
              `<option value="${value}"${value === item.status ? " selected" : ""}>${label}</option>`
          )
          .join("")}
      </select>
      ${starsHtml(item.id, item.rating)}
      <textarea class="note" data-id="${item.id}" placeholder="Not ekle…">${escapeHtml(item.note || "")}</textarea>
      ${
        canWatch
          ? `<button type="button" class="watch-btn" data-id="${item.id}" aria-expanded="false">Nerede izlerim?</button>`
          : ""
      }
      ${canWatch ? `<div class="watch-panel hidden" data-id="${item.id}"></div>` : ""}
    `;
    if (!item.poster_url) return body;
    return `
      <img class="card-poster" src="${escapeHtml(item.poster_url)}" alt="" loading="lazy"
           onerror="this.remove()">
      <div class="card-body">${body}</div>
    `;
  }

  function cardHtml(item) {
    const id = Number(item.id);
    if (!Number.isFinite(id)) return cardInnerHtml(item);
    const hasMedia =
      Boolean(item.poster_url) || (Boolean(item.external_id) && item.kind !== "kitap");
    const attrs = hasMedia ? ` data-id="${id}"` : "";
    return `<div class="card"${attrs}>${cardInnerHtml(item)}</div>`;
  }

  function render() {
    if (state.items.length === 0) {
      grid.innerHTML = "";
      emptyState.classList.remove("hidden");
      return;
    }
    emptyState.classList.add("hidden");
    grid.innerHTML = state.items.map(cardHtml).join("");
  }

  addForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = addTitle.value.trim();
    if (!title) return;
    const body = { title, kind: addKind.value, status: addStatus.value };
    // Sonuçtan seçim yapıldıysa poster/kimlik alanları eklenir; elle yazılan
    // başlıkta bu alanlar gönderilmez (Faz A davranışı).
    if (selectedExternal) {
      if (selectedExternal.poster_url) body.poster_url = selectedExternal.poster_url;
      if (selectedExternal.external_source) body.external_source = selectedExternal.external_source;
      if (selectedExternal.external_id) body.external_id = selectedExternal.external_id;
    }
    try {
      await apiFetch("/api/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      addTitle.value = "";
      selectedExternal = null;
      closeDropdown();
      await loadItems();
    } catch (err) {
      // toast zaten gösterildi
    }
  });

  function wireChips(container, key) {
    container.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      container.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      state[key] = btn.dataset.value || "";
      loadItems();
    });
  }
  wireChips(kindChips, "kind");
  wireChips(statusChips, "status");

  let searchTimer = null;
  search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.q = search.value.trim();
      loadItems();
    }, 250);
  });

  grid.addEventListener("click", async (e) => {
    const star = e.target.closest(".star");
    if (star) {
      const id = star.dataset.id;
      const value = Number(star.dataset.value);
      try {
        await apiFetch(`/api/items/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rating: value }),
        });
        await loadItems();
      } catch (err) {
        // toast zaten gösterildi
      }
      return;
    }

    const delBtn = e.target.closest(".delete-btn");
    if (delBtn) {
      const id = delBtn.dataset.id;
      try {
        await apiFetch(`/api/items/${id}`, { method: "DELETE" });
        await loadItems();
      } catch (err) {
        // toast zaten gösterildi
      }
    }
  });

  grid.addEventListener("change", async (e) => {
    const select = e.target.closest(".status-select");
    if (!select) return;
    const id = select.dataset.id;
    try {
      await apiFetch(`/api/items/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: select.value }),
      });
      await loadItems();
    } catch (err) {
      // toast zaten gösterildi
    }
  });

  let noteTimer = null;
  grid.addEventListener(
    "blur",
    async (e) => {
      const note = e.target.closest(".note");
      if (!note) return;
      const id = note.dataset.id;
      clearTimeout(noteTimer);
      try {
        await apiFetch(`/api/items/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note: note.value }),
        });
      } catch (err) {
        // toast zaten gösterildi
      }
    },
    true
  );

  // ---------------------------------------------------------------
  // Faz B: dış arama (dropdown) + "Nerede izlerim?"
  // ---------------------------------------------------------------

  const searchDropdown = document.getElementById("search-dropdown");
  let selectedExternal = null; // dropdown'dan seçilen {poster_url, external_source, external_id}
  let dropdownResults = [];
  let activeResultIndex = -1;
  let titleSearchTimer = null;
  let searchSeq = 0;

  function showDropdown() {
    searchDropdown.classList.remove("hidden");
    addTitle.setAttribute("aria-expanded", "true");
  }

  function closeDropdown() {
    searchDropdown.classList.add("hidden");
    addTitle.setAttribute("aria-expanded", "false");
    activeResultIndex = -1;
  }

  function setActiveResult(index) {
    const rows = searchDropdown.querySelectorAll(".search-row");
    rows.forEach((row, i) => row.classList.toggle("active", i === index));
    activeResultIndex = index;
  }

  function posterFallbackHtml() {
    return '<span class="search-poster-fallback" aria-hidden="true"></span>';
  }

  function resultMetaText(result) {
    const parts = [];
    if (result.year) parts.push(String(result.year));
    if (result.author) parts.push(String(result.author));
    if (result.external_source) parts.push(SOURCE_LABELS[result.external_source] || result.external_source);
    return parts.join(" · ");
  }

  function renderDropdown() {
    if (!dropdownResults.length) {
      searchDropdown.innerHTML = '<div class="search-note">Sonuç bulunamadı. Elle ekleyebilirsin.</div>';
      showDropdown();
      return;
    }
    searchDropdown.innerHTML = dropdownResults
      .map((result, index) => {
        const poster = result.poster_url
          ? `<img src="${escapeHtml(result.poster_url)}" alt="" loading="lazy">`
          : posterFallbackHtml();
        const meta = resultMetaText(result);
        return `
          <button type="button" class="search-row" role="option" aria-selected="false"
                  data-index="${index}">
            ${poster}
            <span class="search-text">
              <span class="search-title">${escapeHtml(result.title || "")}</span>
              ${meta ? `<span class="search-meta">${escapeHtml(meta)}</span>` : ""}
            </span>
          </button>
        `;
      })
      .join("");
    setActiveResult(-1);
    showDropdown();
  }

  function selectResult(result) {
    selectedExternal = {
      poster_url: result.poster_url || null,
      external_source: result.external_source || null,
      external_id: result.external_id || null,
    };
    if (result.title) addTitle.value = result.title;
    closeDropdown();
    addTitle.focus();
  }

  async function runTitleSearch(query) {
    const seq = ++searchSeq;
    const params = new URLSearchParams();
    params.set("kind", addKind.value);
    params.set("q", query);
    let data;
    try {
      data = await apiGetSilent(`${API_BASE}/search?${params.toString()}`);
    } catch (err) {
      if (seq !== searchSeq) return; // eski istek — sessizce geç
      // 503 (TMDB_API_KEY yok) kullanıcıya gösterilir, sayfa çökmez.
      showToast(err.detail || err.message || "Arama yapılamadı.");
      closeDropdown();
      return;
    }
    if (seq !== searchSeq) return;
    const results = (data && data.results) || [];
    dropdownResults = results.map((raw) => {
      const result = {};
      for (const field of SEARCH_FIELDS) {
        if (raw && raw[field] != null) result[field] = raw[field];
      }
      return result;
    });
    renderDropdown();
  }

  function closeIfClickedOutside(e) {
    const target = e.target;
    if (!target || typeof target.closest !== "function" || !target.closest(".add-title-wrap")) {
      closeDropdown();
    }
  }

  addTitle.addEventListener("input", () => {
    // Başlık elle değiştirildi — önceki seçim artık geçerli değil.
    selectedExternal = null;
    clearTimeout(titleSearchTimer);
    const query = addTitle.value.trim();
    if (query.length < 2) {
      dropdownResults = [];
      closeDropdown();
      return;
    }
    titleSearchTimer = setTimeout(() => runTitleSearch(query), 300);
  });

  addTitle.addEventListener("keydown", (e) => {
    if (searchDropdown.classList.contains("hidden")) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!dropdownResults.length) return;
      const step = e.key === "ArrowDown" ? 1 : -1;
      const next = (activeResultIndex + step + dropdownResults.length) % dropdownResults.length;
      setActiveResult(next);
    } else if (e.key === "Enter") {
      if (activeResultIndex < 0) return; // seçim yok → normal submit (Faz A)
      e.preventDefault();
      const result = dropdownResults[activeResultIndex];
      if (result) selectResult(result);
    } else if (e.key === "Escape") {
      closeDropdown();
    }
  });

  searchDropdown.addEventListener("mousedown", (e) => {
    // Dışarı tıklama dinleyicisi mousedown'da çalışıyor; burada iptal ederek
    // input'un blur olmasını engelliyoruz ki seçim tıklaması düşmesin.
    e.preventDefault();
  });

  searchDropdown.addEventListener("click", (e) => {
    const row = e.target.closest(".search-row");
    if (!row) return;
    const result = dropdownResults[Number(row.dataset.index)];
    if (result) selectResult(result);
  });

  // focusout, tıklamanın hangi öğede bittiğine bakar — mousedown + focusout
  // birlikte güvenli: seçim tıklaması içeride bittiği için kapanmaz.
  addTitle.addEventListener("focusout", (e) => {
    const next = e.relatedTarget;
    if (next && next.closest && next.closest(".add-title-wrap")) return;
    closeDropdown();
  });

  document.addEventListener("mousedown", closeIfClickedOutside);
  document.addEventListener("click", closeIfClickedOutside);

  addKind.addEventListener("change", () => {
    // Tür değişince açık kalan sonuçlar geçersizdir.
    dropdownResults = [];
    closeDropdown();
  });

  function watchPanelFor(id) {
    return grid.querySelector(`.watch-panel[data-id="${id}"]`);
  }

  async function loadWatchProviders(id) {
    const panel = watchPanelFor(id);
    if (!panel) return;
    const btn = grid.querySelector(`.watch-btn[data-id="${id}"]`);
    const open = !panel.classList.contains("hidden");
    panel.classList.add("hidden");
    if (btn) btn.setAttribute("aria-expanded", "false");
    if (open) return;

    panel.classList.remove("hidden");
    if (btn) btn.setAttribute("aria-expanded", "true");
    panel.innerHTML = '<div class="watch-empty">Sağlayıcılar aranıyor…</div>';

    let providers;
    try {
      const data = await apiGetSilent(`${API_BASE}/items/${id}/watch`);
      providers = (data && data.providers) || [];
    } catch (err) {
      // 503 (TMDB_API_KEY yok) / 404 (kitap ya da dış kimlik yok) mevcut
      // toast mekanizmasıyla gösterilir; kart yerinde bilgi mesajı kalır.
      showToast(err.detail || err.message || "Sağlayıcılar alınamadı.");
      panel.innerHTML = `<div class="watch-empty">${
        err.detail || "Sağlayıcı bilgisi alınamadı."
      }</div>`;
      return;
    }

    const rows = providers.filter((p) => p && typeof p === "object");
    if (!rows.length) {
      panel.innerHTML = '<div class="watch-empty">Bu bölgede bir abonelik seçeneği bulunamadı.</div>';
      return;
    }
    panel.innerHTML = rows
      .map((provider) => {
        const name = provider.provider_name || provider.name || "Sağlayıcı";
        const link = provider.link;
        const logo = provider.logo_url
          ? `<img src="${escapeHtml(provider.logo_url)}" alt="" loading="lazy" onerror="this.remove()">`
          : "";
        const inner = `${logo}<span>${escapeHtml(name)}</span>`;
        // Yeni sekmede, güvenli rel ile açılır.
        return link
          ? `<a class="watch-provider" href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">${inner}</a>`
          : `<span class="watch-provider">${inner}</span>`;
      })
      .join("");
  }

  grid.addEventListener("click", async (e) => {
    const watchBtn = e.target.closest(".watch-btn");
    if (!watchBtn) return;
    e.stopPropagation();
    await loadWatchProviders(watchBtn.dataset.id);
  });

  loadItems();
})();
