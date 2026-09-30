---
title: Repo Sağlık Atlası
created: 2026-09-30
modified: 2026-09-30
type: project-plan
status: planned
tags: [proje-plani, atlas, gelistirici-araci, flask, sqlite, git, gizlilik]
---
# Repo Sağlık Atlası (`atlas`)

Bir kök dizindeki (bulutta `/home/user`, Umut'un makinesinde `~/Desktop` gibi) tüm git repolarını tarayıp
sağlık durumunu SQLite'a yazan bir CLI + Flask web panel. Doğuş nedeni 2026-09-30 oturumu: README
ekran görüntülerinde gerçek kişi fotoğrafı, `C:\Users\...` yolu ve API anahtarı parçası public repoya
gitti; yarım işler ve bayat README'ler elle aranıyordu.

**Durum:** Dalga A, A.1, B, C ve **D tamam** (2026-09-30, repo `atlas` main'de). D: `atlas readme` (README bayatlık skoru: davranış commit + görsel yaşı; eşikler taze<3 / eskiyor 3–7 / bayat 8+), `readme_status` tablosuna 7 sütun + `summaries` tablosu (SCHEMA_VERSION 2, eski DB veri kaybetmeden göç eder), `atlas ozet` (varsayılan **ağsız** kural tabanlı ≤3 satır; `--cor` yalnız açıkça istenirse LLM'e gider ve dar/sabit veri kümesi yollar — dosya içeriği/yolu/snippet/TODO metni asla gitmez; sır satırı başlıkları tümüyle atılır, prompt enjeksiyonuna karşı `<<<VERI…VERI>>>` sınırlı blok), `/bayat-readme` sayfası + `/` kartı + `/repo/<id>` özet/README satırı, `atlas guncelle` beş adıma çıktı (son adım ağsız yerel özet). Bilinen sınırlar: Windows'ta doğrulanmadı; tarama penceresi 2000 commit (aşılırsa seviye `sinir` + skor alt sınır 8); `screenshot_age_days` yalnız İZLENEN görseller için; yoğunluk grafiği ham sayı; Flask geliştirme sunucusu (yerel, tek kullanıcı); `sk-` tespiti ≥20 karakter eşiğinin altındaki diziyi yakalamaz (mevcut kural). Sıradaki dalga yok; açık kalan: gerçek Windows taraması Umut'un elinde. `atlas durum --json` eklendi (kule entegrasyonu, sözleşme v1): `atlas/durum.py` ortak modülü web paneli ve CLI'ın **tek sayı kaynağı**, DB `mode=ro`, bulgu içeriği/yolu/anahtarı çıktı dışı, DB yoksa `hata: "db_yok"` + çıkış kodu 1.
Bağlantılar: [[readme-dokumantasyon-kod-senkron-gecikmesi]], [[ne-izlesem-delegasyon-modeli-ajan-kendi-dogrular]],
[[cor-bulut-oturumu-agent-tool-erisimsizligi-headless-cozum]]. Referans: `repo-durum` skill'i
(`.agents/skills/repo-durum/SKILL.md`) git tarama mantığı için okunur, kopyalanmaz.

## Amaç
- Hangi repoda commit'lenmemiş değişiklik / pushlanmamış commit / eski dal var?
- Hangi README bayat? (README'nin son değiştiği committen sonra davranış değiştiren kaç commit var, README ekran görüntüsü kod değişikliğinden eski mi?)
- Çalışma ağacında VE git geçmişinde sızıntı var mı? (API anahtarı, `C:\Users\`, e-posta, `.env`, kişisel veri)
- TODO/FIXME borcu nerede yoğun?
- cor ile repo başına 3 satırlık "şimdi ne yapmalı" özeti.

## Kapsam dışı
Otomatik düzeltme, otomatik push, geçmiş yeniden yazma (yalnızca öneri metni üretir), bulut barındırma, çoklu kullanıcı.

## Mimari
- Python 3.11, stdlib + Flask + `sqlite3`. Git için `subprocess` (`git` CLI), kütüphane yok.
- cor'a `urllib` ile istemci (`atlas/llm.py`, `ne-izlesem/app/llm.py` deseni). cor kapalıysa özet adımı atlanır, tarama çalışır.
- Dizin: `atlas/scan.py` (repo keşfi + git durumu), `atlas/leaks.py`, `atlas/readme_stale.py`, `atlas/todo.py`, `atlas/db.py`, `atlas/summary.py`, `atlas/web/` (Flask, Jinja, tek CSS), `atlas/cli.py`, `tests/`.
- Veri modeli (SQLite): `repos(path, name, scanned_at, dirty, unpushed, branch, last_commit_at)`, `findings(repo, kind, severity, file, line, commit, snippet_redacted)`, `readme_status(repo, readme_commit, behavior_commits_after, screenshot_age_days)`, `todos(repo, file, line, text)`.
- Kök dizin listesi `~/.atlas/config.toml` içinde (`roots = [...]`); varsayılan `~`.

## Güvenlik ve gizlilik (bağlayıcı)
- Bulgu metni HER ZAMAN maskelenir: anahtar `sk-…xxxx`, yol `C:\Users\<kullanıcı>` → `<yol>`. DB'ye ve web'e ham sır yazılmaz.
- Salt okunur: repolara asla yazmaz, `git push/reset/filter-branch` çalıştırmaz.
- Web yalnızca `127.0.0.1`'e bağlanır.

## Dalgalar
**Dalga A — çekirdek tarayıcı + DB**
- `atlas tara` kökleri gezer, her repo için dirty/unpushed/dal/son commit yazar. `atlas liste` tablo basar.
- Kabul: geçici git repolarıyla (fixture: dirty, unpushed, temiz) ≥25 test; `python -m pytest -q` yeşil; `atlas tara --root <tmp>` 0 çıkış koduyla biter.

**Dalga B — sızıntı ve geçmiş taraması**
- Çalışma ağacı + `git log -p` (son N commit, varsayılan 500) regex seti: `sk-[A-Za-z0-9_-]{20,}`, `C:\\Users\\[^\\]+`, e-posta, `.env` izlenen dosya, özel anahtar başlıkları. Görsellerde (`docs/**/*.png,jpg`) yalnızca dosyanın varlığı + "elle kontrol et" bulgusu (OCR opsiyonel, kapsam dışı ilk turda).
- Kabul: sahte sır içeren fixture repo'da bulgu çıkar, ham sır çıktıda ve DB'de YOK (testle kanıtla); temiz repoda 0 bulgu.

**Dalga C — web panel**
- Sayfalar: `/` özet kartları, `/yarim-is`, `/sizinti`, `/bayat-readme`, `/borc`, `/repo/<ad>`. Boş durum dahil; koyu tema, sol hizalı, zero-dependency (CDN yok).
- Kabul: Flask test client 200 döner; Playwright ile ekran görüntüsü alınır ve OKUNUR (taşma yok). Ekran görüntüleri KURGUSAL fixture verisiyle çekilir (README kuralı).

**Dalga D — README bayatlığı + cor özeti**
- Bayatlık skoru: `behavior_commits_after` (mesajı `fix|feat|refactor|perf` olan, yalnızca doc olmayan dosyaları değiştiren commitler) + görüntü yaşı. Repo başına cor özeti `/repo/<ad>` sayfasında.
- Kabul: cor yoksa sahte LLM istemcisiyle test; skor sıralaması testli; README (TR+EN) yazılır.

## Bulut oturumu talimatı
İlk mesaj örneği: "Mt3Ui55OS vault'unu oku, `🏰 300-Projects/Repo-Saglik-Atlasi.md` planındaki Dalga A'yı `/home/user/atlas`'ta yap."
Oturum: (1) bu notu ve Threads'i oku, (2) `cor start` dene, (3) Umut repo açtıysa klonla, yoksa prefilled GitHub URL ver, (4) dalgayı yap, testleri KOŞ, (5) projeyi pushla, (6) vault'ta bu notun "Durum" satırını, `Threads.md`'yi ve `Last-Session.md`'yi güncelleyip vault'u pushla.

## Açık kararlar (Umut'a sor)
- Repo adı/kök dizin varsayılanı.
- Görsel sızıntısı için OCR (pytesseract) eklensin mi (yeni bağımlılık)?
- Windows'ta gerçek makine taraması Umut'un elinde doğrulanacak (bulutta yapılamaz).
