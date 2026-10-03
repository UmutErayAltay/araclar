# baglam-rontgeni

Claude Code'un her oturumda bağlama yüklediği kalemleri (skill / CLAUDE.md / MCP) tarar ve
her kalemin **açılış token maliyetini** çıkarır. **Varsayılan kuru çalıştırmadır** —
`--uygula` verilmeden `settings.json`'a dokunulmaz. Yalnız Python standart kütüphanesi (3.11+).

## Ne yapar

`tara` bağlamı tarayıp `~/.baglam-rontgeni/son.json`'a raporlar, `goster` son raporu okur (yeniden taramaz), `kapat`/`ac` bir skill'i ya da plugin'i devre dışı bırakır — ikisi de **kuru çalışır**, sadece değişecek satırı gösterir.

| `tur` | Nereden | `acilis` | `cagrilinca` |
|---|---|---|---|
| `skill` | `enabledPlugins`'ta **açık** plugin'lerin `**/SKILL.md`'i + `~/.claude/skills/*/SKILL.md` | name + description | SKILL.md gövdesi |
| `claude_md` | `~/.claude/CLAUDE.md` (+ `--proje`: proje `CLAUDE.md`, `CLAUDE.local.md`) | dosyanın tamamı | `-` |
| `mcp` | proje `.mcp.json` (`mcpServers`) + aktif plugin `.mcp.json` | `-` | `-` |

Plugin skill'i `plugin:skill` adıyla raporlanır (skillOverrides anahtarıyla aynı yazım). Nokta ile başlayan gizli iç dizinler atlanır (plugin'lerin kendi eski aynaları sayılmaz); bir plugin'in birden çok kurulum kaydı varsa en güncel `lastUpdated`/`installedAt` olan seçilir.

## Kurulum

```bash
cd baglam-rontgeni
pip install -e .        # ya da kurulum yapmadan: python3 -m baglam_rontgeni
```

## Kullanım

```bash
rontgen tara                                 # tara + raporu kaydet
rontgen tara --proje ~/Documents/projeler    # proje CLAUDE.md / CLAUDE.local.md / .mcp.json dahil
rontgen tara --json                          # JSON (rapor yolu "rapor" alanında)
rontgen goster                               # son rapor (yeniden taramaz)
rontgen goster --ilk 30                      # kaç satır (varsayılan 15; yalnız goster)
rontgen kapat plugin:skill --uygula          # KURU: --uygula'sız yalnız diff, ekleyince yazar
rontgen kapat ad@pazar --uygula              # plugin'i tümüyle kapatır
rontgen ac plugin:skill --uygula             # skill'i geri açar
```

Hedef `plugin:skill` ya da `ad@pazar` olmalı; başka biçim veya `enabledPlugins`'ta olmayan plugin `Hata: bilinmeyen plugin: ...` ile reddedilir (çıkış kodu `2`). Hedefte yol kaçışı (`..`), boş ad, boş skill adı (`kule:`) ve kontrol karakteri varsa `Hata: gecersiz hedef: ...` ile reddedilir. `kapat bilinmeyen-skill:adı` **reddedilmez**, yalnız `uyari: ... bilinen skill degil` yazılır (amaçlanan değişiklik yine uygulanır). Zaten istenen durumdaysa `zaten kapali` / `zaten acik, degisiklik yok` yazılır, dosyaya dokunulmaz. Rapor dizini `RONTGEN_DIR`, ayar dizini `CLAUDE_DIR` ile değiştirilebilir (göreli yol mutlağa çevrilir).

## Gerçek çıktı

`--proje` ile vault taranmış, tabloda ilk satırlar (kısaltılmış):

```console
$ rontgen tara --proje ~/Documents/Mt3Ui55OS
ad                                                        tur        acilis  cagrilinca  durum
CLAUDE.md                                                 claude_md  1559    -
python-library-complete:normalizing-text-for-measurement  skill      242     2873        kapali
impeccable:impeccable                                     skill      227     2680
supabase:supabase-postgres-best-practices                 skill      218     442
python-library-complete:shipping-across-surfaces          skill      217     2556        kapali
supabase:supabase                                         skill      200     2980
... ve 49 kalem daha
toplam acilis ~4877 token (TAHMIN), 2 olculemeyen kalem, 25 kapali

rapor: ~/.baglam-rontgeni/son.json
```

Satırlar açılış maliyetine göre büyükten küçüğe sıralanır. `toplam acilis` yalnız **açık** kalemleri toplar (kapalı ve ölçülemeyenler dışarıda); `CLAUDE.md` ya da skill dosyaları değiştikçe değişir, sabit bir bütçe değildir. Sütunda `-` o değerin ölçülmediğini demektir.

## Tahmin notu

- **Her sayı tahmindir**, tokenizer çağrılmaz: `ceil(karakter / 4)`; rapor bunu `tahmin_notu` alanında saklar.
- Skill'de **yalnız `name` + `description` her açılışta yüklenir**, gövde ancak çağrılınca gelir; `cagrilinca` bu yüzden açılıştan çok büyüktür, ikisini toplamak yanlış olur.
- Skill `description` listesi bağlam penceresinin kabaca **%1'iyle sınırlıdır**: skill sayısı arttıkça kısalır. **Toplam açılış bir üst sınır tahminidir**, ölçülmüş gerçek değil.
- **MCP araç şemaları ölçülemez** (sunucu tanımları bağlam metnine girmez). Bu kalemler `acilis: -` ve `olculemedi: true` ile raporlanır, özette `olculemeyen kalem` sayısında durur — **sıfır da sayılmaz, temiz de sayılmaz.**

## Güvenlik

- **Varsayılan kuru çalıştırma:** `kapat`/`ac` `--uygula` olmadan yalnız diff gösterir.
- Gerçek yazmada önce `settings.json.rontgen-bak-<YYYYmmddTHHMMSS>` yedeği alınır, sonra geçici dosya + `os.replace` ile **atomik** yazılır. Yedekler **en yeni 5** ile sınırlıdır, eskileri silinir.
- **Yalnız `skillOverrides` ve `enabledPlugins` değişir**; diğer ayarlar ve anahtar sırası korunur, hedef zaten istenen durumdaysa hiç yazılmaz.
- **Yazma öncesi kontrol (TOCTOU):** okunan ayar yazma anında yeniden okunur; arada değişmişse üstüne yazılmaz, `Hata: settings.json arada degisti, tekrar deneyin` (çıkış `2`).
- `settings.json` bir **symlink** ise bağlantı kırılmaz; gerçek dosya (bağlantının hedefi) güncellenir.
- Plugin taraması **bağlantı (symlink/junction) döngülerine girmez**, derinlik 6 ile sınırlıdır; okunamayan bir `SKILL.md` taramayı düşürmez, yalnız o kalem atlanır.
- `installPath` çözüldükten sonra `~/.claude/plugins` altında değilse o plugin **sayılmaz** (ayar dosyası istediği dizini tarattıramaz).
- Dosya adları, skill adları ve tablo sütunları **kontrol karakterlerinden arındırılır** (`?`); rapordaki `kaynak` yolları `~` ile kısaltılır (paylaşımda kullanıcı adı sızmaz).
- **Rapora skill metni girmez:** gövde ve `description` yalnız sayıya indirgenir.

## Bilinen sınır

Resmî doküman, plugin skill'lerinin `skillOverrides`'tan **etkilenmediğini** söylüyor. Bu makinedeki `settings.json` ise `python-library-complete:*` ve `supabase:*` gibi **plugin önekli** anahtarlar kullanıyor ve röntgen `kapali` işaretini oradan okuyor. Bu eşleşmenin Claude Code tarafından gerçekten uygulandığı **doğrulanmadı**: `kapat --uygula` sonrası `/skills` ile skill'in hâlâ listelenip listelenmediğini kontrol edin, listede kalıyorsa anahtar etkisizdir.

## Çıkış kodları

| Kod | Anlamı |
|---|---|
| `0` | Tamam — **kapalı/ölçülemeyen kalem bulunması hata değildir**, sayılar raporda durur |
| `2` | Kullanım/keşif yazma hatası: `settings.json` yok/bozuk, bilinmeyen plugin, geçersiz hedef, ayar arada değişti, dosya/dizin **yazılamadı** (izin, salt-okunur), rapor yok |

## Web sekmesi ve kule kartı

**Henüz yok:** kule panelinde kart yok, web arayüzünde sekmesi yok.

## Testler

```bash
python3 -m pytest -q
```
