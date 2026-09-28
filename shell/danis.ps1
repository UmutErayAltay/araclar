# UYARI: Bu script Linux container'ında test edilmedi, elle bash mantığıyla
# simetrik yazıldı. Bu ortamda `pwsh`/PowerShell YOKTUR; tests/test_shell_hook.py
# yalnızca bash dalını gerçek alt süreçle doğrular. Aşağıdaki PowerShell mantığı
# shell/danis.sh'in birebir karşılığı olacak şekilde YAZILDI, ÇALIŞTIRILMADI.
#
# Kurulum (PowerShell profiline ekle):
#     notepad $PROFILE
#     # ...sonuna ekle:
#     . C:\path\to\danis\shell\danis.ps1
#
# Ne yapar (danis.sh ile aynı):
#   * Her komuttan sonra son komutun çıkış kodunu $global:DANIS_LAST_EXIT'e,
#     komut metnini $global:DANIS_LAST_CMD'ye yazar.
#   * Çıkış kodu 0 DEĞİLSE otomatik LLM çağrısı YAPMAZ; sadece stderr'e kısa
#     bir ipucu basar.
#   * `danis` fonksiyonu argümansız çağrılırsa son hatayı analiz ettirir.

# Bu dosya Türkçe karakter içeriyor; Windows PowerShell 5.1 .ps1 dosyalarını
# BOM'suz UTF-8'i ANSI sanıp karakterleri bozar. Bu yüzden dosya UTF-8 BOM ile
# kaydedilmiştir (bkz. tests/test_install_context_menu.py::test_ps1_is_utf8_bom).

# --------------------------------------------------------------------------
# Kanca kurulumu (bir kez, script dot-source edildiğinde çalışır)
# --------------------------------------------------------------------------

if ($global:DANIS_HOOK_YUKLENDI) {
    return
}
$global:DANIS_HOOK_YUKLENDI = $true

# history'den komut metnini ayıklar. PowerShell'da history girdisi bash'tan
# farklı olarak ZATEN sadece komut metnidir (indeks/zaman damgası yok), bu
# yüzden burada ek bir ayrıştırma gerekmez.
function global:_DanisSonKomut {
    $girdi = @(Get-History -Count 1 -ErrorAction SilentlyContinue)
    if ($girdi.Count -eq 0) { return '' }
    return [string]$girdi[-1].CommandLine
}

# prompt tarafından HER komuttan sonra çağrılır.
function global:_DanisKaydet {
    # $LASTEXITCODE yalnızca DIŞ (native) komutlar için set edilir; cmdlet
    # çalıştırıldıysa değer bayat kalır. $? o anki başarı durumunu verdiği
    # için ikisi birlikte değerlendirilir.
    if ($LASTEXITCODE -ne $null) { $durum = [int]$LASTEXITCODE }
    elseif ($?) { $durum = 0 }
    else { $durum = 1 }

    $komut = (_DanisSonKomut).Trim()

    # Kendi çağrılarımızı ve geçmiş komutlarını HARİÇ TUT: aksi halde `danis`
    # kendi kendini analiz eder ve ipucu her seferinde tekrarlanır.
    # (h/history PowerShell'de Get-History'in takma adıdır.)
    if ($komut -eq '') { return }
    if ($komut -match '^(danis\b|_Danis\b|Get-History\b|Invoke-History\b|history\b|h\b)') { return }

    $global:DANIS_LAST_EXIT = $durum
    $global:DANIS_LAST_CMD = $komut
    if ($durum -ne 0) {
        [Console]::Error.WriteLine("❌ (çıkış $durum) — danis")
    }
}

# prompt'u EZMEDEN zincirle: eski prompt varsa önce/sonra çağrılır.
$global:__danisEskiPrompt = $function:prompt
function global:prompt {
    _DanisKaydet
    if ($global:__danisEskiPrompt) { & $global:__danisEskiPrompt }
}

# --------------------------------------------------------------------------
# danis komutu
# --------------------------------------------------------------------------

# Kurulu bir `danis` varsa onu kullan, yoksa kaynak ağacından modülü çalıştır.
# (fonksiyon, PATH'teki aynı adlı executable'ı gölgeler; Get-Command -CommandType
# ile ararken fonksiyonumuzu görmez)
function global:_DanisCalistir {
    $kurulu = Get-Command danis -CommandType Application -ErrorAction SilentlyContinue
    if ($kurulu) { & danis @args }
    else { & python3 -m danis.cli @args }
}

function global:danis {
    if ($args.Count -eq 0) {
        # Boş $DANIS_LAST_CMD durumunda CLI'ye gidilmez: argparse boş metni
        # "invalid int value" hatasıyla reddeder, kullanıcı yanlış yönlendirilir.
        if (-not $global:DANIS_LAST_CMD) {
            [Console]::Error.WriteLine('danis: analiz edilecek komut yok. Önce bir komut çalıştırın.')
            return 1
        }
        _DanisCalistir hata $global:DANIS_LAST_CMD $global:DANIS_LAST_EXIT
    }
    else {
        _DanisCalistir @args
    }
}
