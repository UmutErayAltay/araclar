"""Arayüz metinleri (TR/EN). İçerik (ad, açıklama, deneyim) yapılandırmadan gelir; burada yalnız sabit etiketler var."""

from __future__ import annotations

DILLER = ("tr", "en")

_TR = {
    "atla": "İçeriğe geç",
    "sayfa_bolumleri": "Sayfa bölümleri",
    "dil_etiket": "Dil",
    "menu_projeler": "Projeler",
    "menu_deneyim": "Deneyim",
    "menu_yetenekler": "Yetenekler",
    "menu_egitim": "Eğitim",
    "menu_yazilar": "Yazılar",
    "menu_iletisim": "İletişim",
    "cv_kisa": "CV",
    "cv_indir": "CV indir",
    "cv_etiket": "CV:",
    "cv_tr": "Türkçe (PDF)",
    "cv_en": "English (PDF)",
    "eposta": "E-posta",
    "oneci_baslik": "Öne çıkan projeler",
    "oneci_alt": "Önce bunlara bak",
    "diger_baslik": "Diğer projeler",
    "deneyim_baslik": "Deneyim",
    "egitim_baslik": "Eğitim",
    "yetenek_baslik": "Yetenekler",
    "yazi_baslik": "Yazılar",
    "commit": "commit",
    "son_commit": "Son commit:",
    "hafta_once": "12 hafta önce",
    "bu_hafta": "bu hafta",
    "olcer_aria": "Son 12 haftada commit sayısı:",
    "hic_commit": "hiç commit yok",
    "olcer_toplam": "Commit etkinliği · son 12 hafta",
    "iletisim_baslik": "Birlikte çalışalım",
    "iletisim_metin": "Yeni bir pozisyon ya da proje için ulaşabilirsin. CV'm iki dilde, indirmeye hazır.",
    "uretildi": "Otomatik üretildi:",
    "ana_sayfa": "← Ana sayfa",
    "dk_okuma": "dk okuma",
    "diger_yazilar": "Diğer yazılar",
    "locale": "tr_TR",
}

_EN = {
    "atla": "Skip to content",
    "sayfa_bolumleri": "Page sections",
    "dil_etiket": "Language",
    "menu_projeler": "Projects",
    "menu_deneyim": "Experience",
    "menu_yetenekler": "Skills",
    "menu_egitim": "Education",
    "menu_yazilar": "Writing",
    "menu_iletisim": "Contact",
    "cv_kisa": "CV",
    "cv_indir": "Download CV",
    "cv_etiket": "CV:",
    "cv_tr": "Türkçe (PDF)",
    "cv_en": "English (PDF)",
    "eposta": "Email",
    "oneci_baslik": "Featured projects",
    "oneci_alt": "Start here",
    "diger_baslik": "Other projects",
    "deneyim_baslik": "Experience",
    "egitim_baslik": "Education",
    "yetenek_baslik": "Skills",
    "yazi_baslik": "Writing",
    "commit": "commits",
    "son_commit": "Last commit:",
    "hafta_once": "12 weeks ago",
    "bu_hafta": "this week",
    "olcer_aria": "Commits per week over the last 12 weeks:",
    "hic_commit": "no commits",
    "olcer_toplam": "Commit activity · last 12 weeks",
    "iletisim_baslik": "Let's work together",
    "iletisim_metin": "Reach out about a role or a project. My CV is available in both languages.",
    "uretildi": "Generated automatically:",
    "ana_sayfa": "← Home",
    "dk_okuma": "min read",
    "diger_yazilar": "More posts",
    "locale": "en_US",
}

METIN = {"tr": _TR, "en": _EN}


def m(dil: str, anahtar: str) -> str:
    """Etiket döndürür; bilinmeyen dil Türkçeye düşer, bilinmeyen anahtar KeyError (testle yakalanır)."""
    return METIN.get(dil, _TR)[anahtar]
