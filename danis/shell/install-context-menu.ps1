# danis — Windows sağ-tık menüsü kurulumu.
#
# UYARI: Bu script Linux container'ında test edilmedi (burada PowerShell
# YOKTUR). Asıl mantık saf metin işlemesi olan danis/context_menu.py'de
# durur ve pytest ile test edilmiştir; bu dosya yalnızca o modülü çağıran ince
# bir sarmalayıcıdır.
#
#   .\install-context-menu.ps1 -DryRun     # üretilen .reg'i SADECE ekrana bas
#   .\install-context-menu.ps1            # üret ve reg import ile kaydet
#   .\install-context-menu.ps1 -ExePath C:\tools\danis.exe
#
# .reg dosyası UTF-8 BOM ile yazılır: reg.exe, BOM'suz UTF-8'deki Türkçe
# karakterleri bozuk gösterir.

[CmdletBinding()]
param(
    # Kurulu danis.exe'yi PATH'ten ara; bulunamazsa hata ver.
    [string]$ExePath,

    # Üretilen .reg içeriğini yazdır, kayıt defterine DOKUNMA.
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Bu script repo ağacından ya da kopyalanmış olarak çalışabilir; modülü bul.
$repoKok = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$repoKok;$env:PYTHONPATH" } else { $repoKok }

$shellDir = $PSScriptRoot

# 1) danis.exe'nin gerçek yolunu bul.
if (-not $ExePath) {
    $bulunan = Get-Command danis.exe -CommandType Application -ErrorAction SilentlyContinue
    if (-not $bulunan) {
        throw "danis.exe PATH'te bulunamadı. Kurulumu yapın veya -ExePath ile tam yolu verin."
    }
    $ExePath = $bulunan[0].Source
}

# 2) Doğrulama + .reg üretimi (saf metin işlemesi, test edilmiş modül).
$python = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { 'python3' }
$regYolu = & $python -c @"
import sys
from pathlib import Path
from danis.context_menu import exe_yolu_coz, reg_dosyasi_yaz
print(reg_dosyasi_yaz(Path(sys.argv[1]), exe_yolu_coz(sys.argv[2])))
"@ $shellDir $ExePath

if ($LASTEXITCODE -ne 0) { throw "danis/context_menu.py başarısız oldu." }

# 3) İçeriği göster (import etmeden).
$icerik = Get-Content -Raw -Path $regYolu
Write-Host $icerik

if ($DryRun) {
    Write-Host "[DryRun] Kayıt defteri DEĞİŞTİRİLMEDİ. Kurmak için bu bayrağı kaldırın."
    return
}

# 4) Kaydet.
Write-Host "İçe aktarılıyor: $regYolu"
& reg.exe import $regYolu
if ($LASTEXITCODE -ne 0) { throw "reg import başarısız oldu (çıkış $LASTEXITCODE)." }
Write-Host "Kuruldu. Herhangi bir dosyaya sağ tıkla -> 'Bu dosyayı danis'e sor'."
