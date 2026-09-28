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
      throw new Error(message);
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

  function cardHtml(item) {
    return `
      <div class="card" data-id="${item.id}">
        <div class="card-top">
          <div class="card-title">${escapeHtml(item.title)}</div>
          <button type="button" class="delete-btn" data-id="${item.id}" title="Sil" aria-label="Sil">✕</button>
        </div>
        <div class="badges">
          <span class="badge badge-kind">${KIND_LABELS[item.kind] || item.kind}</span>
          <span class="badge badge-status" data-status="${item.status}">${STATUS_LABELS[item.status] || item.status}</span>
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
      </div>
    `;
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
    try {
      await apiFetch("/api/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, kind: addKind.value, status: addStatus.value }),
      });
      addTitle.value = "";
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

  loadItems();
})();
