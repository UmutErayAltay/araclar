# danis — bash/zsh entegrasyonu
#
# Kullanım (bash):
#     source /path/to/danis/shell/danis.sh
# veya ~/.bashrc'ye ekle:
#     [ -f /path/to/danis/shell/danis.sh ] && source /path/to/danis/shell/danis.sh
#
# Kullanım (zsh): aynı satır ~/.zshrc'ye.
#
# Ne yapar:
#   * Her komuttan sonra son komutun çıkış kodunu DANIS_LAST_EXIT'e, komut
#     metnini DANIS_LAST_CMD'ye yazar.
#   * Çıkış kodu 0 DEĞİLSE otomatik LLM çağrısı YAPMAZ — maliyet/gürültü
#     riski. Sadece stderr'e kısa bir ipucu basar.
#   * `danis` fonksiyonu argümansız çağrılırsa son hatayı analiz ettirir.
#
# Uyarı: bu script yalnızca ETKİLEŞİMli bir shell'de işe yarar;
# PROMPT_COMMAND/precmd yalnızca orada çalışır.

if [ -n "$DANIS_HOOK_YUKLENDI" ]; then
    return 0 2>/dev/null || true
fi
DANIS_HOOK_YUKLENDI=1

# Başka bir PROMPT_COMMAND varsa EZME, sonuna ekle.
_danis_kancaya_ekle() {
    if [ -n "$ZSH_VERSION" ]; then
        # zsh PROMPT_COMMAND'ı kullanmaz; doğru karşılığı `precmd` kancasıdır.
        typeset -ga precmd_functions
        if [[ " ${precmd_functions[*]} " != *' _danis_kaydet '* ]]; then
            precmd_functions+=( _danis_kaydet )
        fi
    else
        case "${PROMPT_COMMAND:-}" in
            *_danis_kaydet*) : ;;  # zaten eklenmiş
            '') PROMPT_COMMAND="_danis_kaydet" ;;
            *)  PROMPT_COMMAND="${PROMPT_COMMAND%;};_danis_kaydet" ;;
        esac
    fi
}

# history çıktısından komut metnini ayıklar.
#   bash: "  512  ls /tmp"  → "ls /tmp"
#   zsh : "ls /tmp"         → "ls /tmp"
# HISTTIMEFORMAT boşaltılır, aksi halde zaman damgası komuta karışır. Yakalanan
# metin LLM'e tırnaklı argüman olarak olduğu gibi gider, bu yüzden çevreleyen
# boşluklar da temizlenir.
_danis_komutu_ayikla() {
    local ham="$1" konu
    # Baştaki tüm boşlukları at.
    while :; do
        case "$ham" in
            [[:space:]]*) ham="${ham#?}" ;;
            *) break ;;
        esac
    done
    # Başta rakam varsa (bash'ın history indeksi) o da at.
    konu="${ham%%[![:digit:]]*}"
    if [ -n "$konu" ]; then
        ham="${ham#"$konu"}"
        while :; do
            case "$ham" in
                [[:space:]]*) ham="${ham#?}" ;;
                *) break ;;
            esac
        done
    fi
    # Sondaki boşlukları at.
    while :; do
        case "$ham" in
            *[[:space:]]) ham="${ham%?}" ;;
            *) break ;;
        esac
    done
    printf '%s' "$ham"
}

# PROMPT_COMMAND/precmd tarafından HER komuttan sonra çağrılır.
# $? o an hâlâ kullanıcının son komutunun çıkış kodudur.
_danis_kaydet() {
    local durum="$?" ham komut
    local HISTTIMEFORMAT=          # zaman damgası gelmesin
    ham="$(history 1 2>/dev/null)" || ham=""
    komut="$(_danis_komutu_ayikla "$ham")"

    # Kendi çağrılarımızı ve geçmiş komutlarını HARİÇ TUT: aksi halde
    # `danis` kendi kendini analiz eder ve ipucu her seferinde tekrarlanır.
    case "$komut" in
        ""|danis*|_danis*|history*|"fc "*|"fc -"*) return 0 ;;
    esac

    DANIS_LAST_EXIT="$durum"
    DANIS_LAST_CMD="$komut"
    if [ "$durum" -ne 0 ]; then
        printf '❌ (çıkış %s) — danis\n' "$durum" >&2
    fi
    return 0
}

# Kurulu bir `danis` varsa onu kullan, yoksa kaynak ağacından modülü çalıştır.
# (fonksiyon, PATH'teki aynı adlı executable'ı gölgeler; `command` onu atlar)
_danis_calistir() {
    local yol=""
    if [ -n "$ZSH_VERSION" ]; then
        yol="$(whence -p danis 2>/dev/null)" || yol=""
    else
        yol="$(type -P danis 2>/dev/null)" || yol=""
    fi
    if [ -n "$yol" ]; then
        command danis "$@"
    else
        python3 -m danis.cli "$@"
    fi
}

# Argümansız: son hatayı analiz ettir.  Argümanlı: doğrudan CLI'ya aktar
# (`danis dosya rapor.pdf "özetle"`).
#
# Boş `$DANIS_LAST_CMD` durumunda CLI'ye gidilmez: argparse boş metni
# "invalid int value" hatasıyla reddeder, kullanıcı da yanlış yönlendirilir.
danis() {
    if [ "$#" -eq 0 ]; then
        if [ -z "$DANIS_LAST_CMD" ]; then
            printf 'danis: analiz edilecek komut yok. Önce bir komut çalıştırın.\n' >&2
            return 1
        fi
        _danis_calistir hata "$DANIS_LAST_CMD" "$DANIS_LAST_EXIT"
    else
        _danis_calistir "$@"
    fi
}

_danis_kancaya_ekle
