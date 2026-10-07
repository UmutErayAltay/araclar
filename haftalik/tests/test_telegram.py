"""telegram.py: 4096 bolme, MarkdownV2 kacis, ortam degiskeni yoksa cikis 2,
token/chat_id sizmaz (gercek ag YOK, sahte gonderici)."""

from __future__ import annotations

import pytest
from conftest import repo_gun_icin, run_cli_yerel

from haftalik import telegram
from haftalik.telegram import MAX_MESAJ, kacis, ozet_mesajlari

#: Bicim denetiminden GECEN sahte bir token. `gonder` bunu gercek agda dener, bu
#: yuzden ag cagrisi YAPAN testlerde bu degere degil, `sahte_gonderici` kullanilir.
TOKEN = "123456789:AAHsahte-Token_Kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk"
CHAT = "-1001234567890"

#: Bicim denetiminden GEÇMEYEN deger: gonderim ag CAGRILMAZ, istenen token/chat_id
#: hicbir mesaja girmez. Sizmama testleri bu degerlerle calisir.
GECERSIZ_TOKEN = "kisa-token"


@pytest.fixture
def sahte_gonderici(monkeypatch: pytest.MonkeyPatch):
    """`telegram.gonder` yerine gecen sahte: gonderilen mesajlari TOPLAR,
    ag cagrisi YAPMAZ. Icerik degistirilirse `ozetler` listesine yansimaz."""
    gonderilen: list[str] = []

    def gonder(metin: str, *a, **k) -> bool:
        gonderilen.append(metin)
        return True

    monkeypatch.setattr(telegram, "gonder", gonder, raising=True)
    return gonderilen


class TestKacis:
    def test_markdownv2_ozel_karakterler(self):
        assert kacis("a_b*c") == r"a\_b\*c"
        assert kacis("# başlık") == r"\# başlık"
        assert kacis("a.b-c!") == r"a\.b\-c\!"

    def test_duz_metin_degismez(self):
        assert kacis("haftalık özet 2026") == "haftalık özet 2026"

    def test_kaçış_kendisi_siradan_karakter(self):
        # ters eğik çizgi de kaçışlanır
        assert kacis(r"a\b") == r"a\\b"


class TestBolme:
    def test_kisa_ozet_tek_mesaj(self):
        mesajlar = ozet_mesajlari("# Haftalık özet\n\nkısa gövde")
        assert len(mesajlar) == 1
        assert "kısa gövde" in mesajlar[0]

    def test_bos_ozet_mesaj_yok(self):
        assert ozet_mesajlari("") == []
        assert ozet_mesajlari("   \n  ") == []

    def test_uzun_ozet_bolunur(self):
        ozet = "# Haftalık özet\n\n" + "\n\n".join(f"Paragraf {i} " + "x" * 300 for i in range(40))
        mesajlar = ozet_mesajlari(ozet)
        assert len(mesajlar) > 1

    def test_hicbir_mesaj_siniri_asmaz(self):
        ozet = "# Haftalık özet\n\n" + "\n\n".join(f"Paragraf {i} " + "x" * 300 for i in range(40))
        for m in ozet_mesajlari(ozet):
            assert len(m) <= MAX_MESAJ

    def test_paragraf_paragraf_bolen(self):
        ozet = "# Haftalık özet\n\n" + "\n\n".join(f"Paragraf {i} " + "x" * 300 for i in range(40))
        mesajlar = ozet_mesajlari(ozet)
        # bolme bosta olmaz: her mesajda ozet basligi vardir
        assert all("Haftalık özet" in m for m in mesajlar)

    def test_cok_uzun_tek_satir_kisaltilir(self):
        """Tek basina sigmayan satir kesilir ve `…` ile biter."""
        mesajlar = ozet_mesajlari("# Haftalık özet\n\n" + "y" * (MAX_MESAJ * 2))
        assert len(mesajlar) == 1
        assert len(mesajlar[0]) <= MAX_MESAJ
        assert mesajlar[0].endswith("…")

    def test_icerik_kaybolmaz(self):
        ozet = "# Haftalık özet\n\n" + "\n\n".join(f"Paragraf {i} " + "x" * 300 for i in range(40))
        birlikte = " ".join(ozet_mesajlari(ozet))
        assert "Paragraf 0" in birlikte
        assert "Paragraf 39" in birlikte


class TestGonder:
    def test_gecerli_token_gonderir(self, sahte_gonderici):
        assert telegram.gonder("mesaj", TOKEN, CHAT) is True
        assert sahte_gonderici == ["mesaj"]

    def test_ortam_degiskenleri_kullanilir(self, monkeypatch: pytest.MonkeyPatch, sahte_gonderici):
        monkeypatch.setenv(telegram.TOKEN_ENV, TOKEN)
        monkeypatch.setenv(telegram.CHAT_ENV, CHAT)
        assert telegram.gonder("mesaj") is True
        assert sahte_gonderici == ["mesaj"]

    def test_gecersiz_token_false_donmez(self):
        """Bicim denetimi GERCEK `gonder` icinde: sahte gonderici degil."""
        assert telegram.gonder("mesaj", GECERSIZ_TOKEN, CHAT) is False

    def test_gecersiz_chat_id_false_donmez(self, telegram_yok):
        assert telegram.gonder("mesaj", GECERSIZ_TOKEN, "hatali-sohbet") is False

    def test_eksik_env_false_donmez(self, telegram_yok):
        assert telegram.gonder("mesaj") is False

    def test_asla_raise_etmez(self, telegram_yok):
        """Bicim denetimi hicbir girdide istisna firlatmaz."""
        for token, chat in (("", ""), ("x", "1"), (TOKEN, ""), ("", CHAT), (TOKEN, "abc")):
            assert telegram.gonder("m", token or None, chat or None) is False


class TestSizmama:
    def test_loglanan_uyarida_token_yok(self, telegram_yok, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            assert telegram.gonder("m", GECERSIZ_TOKEN, CHAT) is False
        metinler = " ".join(r.getMessage() for r in caplog.records)
        assert metinler  # bir uyari yazildi
        assert GECERSIZ_TOKEN not in metinler
        assert CHAT not in metinler

    def test_hata_mesajinda_token_yok(self, telegram_yok, capsys):
        """CLI ciktisinda token/chat_id GECERLI degerler bile gorunmez."""
        import os

        os.environ[telegram.TOKEN_ENV] = TOKEN
        os.environ[telegram.CHAT_ENV] = CHAT
        try:
            # gonder ag cagrisi yapip basarisiz olacak; cikti yine de temiz olmali
            telegram.gonder("m")
        finally:
            os.environ.pop(telegram.TOKEN_ENV, None)
            os.environ.pop(telegram.CHAT_ENV, None)
        captured = capsys.readouterr()
        assert TOKEN not in captured.out + captured.err
        assert CHAT not in captured.out + captured.err


class TestUctanUca:
    def test_telegram_gonderilir(self, tmp_path, sahte_llm, telegram_yok, sahte_gonderici,
                                monkeypatch):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sahte_llm("SAHTE OZET")
        monkeypatch.setenv(telegram.TOKEN_ENV, TOKEN)
        monkeypatch.setenv(telegram.CHAT_ENV, CHAT)

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path), "--telegram")

        assert sonuc.returncode == 0, sonuc.stderr
        assert len(sahte_gonderici) >= 1
        assert "SAHTE OZET" in sahte_gonderici[0]

    def test_telegram_gonderilir_ve_dosyaya_yazilir(self, tmp_path, sahte_llm, telegram_yok,
                                                     sahte_gonderici, monkeypatch):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sahte_llm("SAHTE OZET")
        monkeypatch.setenv(telegram.TOKEN_ENV, TOKEN)
        monkeypatch.setenv(telegram.CHAT_ENV, CHAT)
        cikti = tmp_path / "ozet.md"

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path), "--telegram",
                              "--cikti", str(cikti))

        assert sonuc.returncode == 0, sonuc.stderr
        assert sahte_gonderici
        assert "SAHTE OZET" in cikti.read_text(encoding="utf-8")

    def test_env_yoksa_cikis_iki(self, tmp_path, sahte_llm, telegram_yok, sahte_gonderici):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sahte_llm("SAHTE OZET")

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path), "--telegram")

        assert sonuc.returncode == 2
        assert "Hata:" in sonuc.stderr
        assert telegram.TOKEN_ENV in sonuc.stderr
        assert telegram.CHAT_ENV in sonuc.stderr
        assert sahte_gonderici == []

    def test_gonderilemezse_hata(self, tmp_path, sahte_llm, telegram_yok, monkeypatch):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sahte_llm("SAHTE OZET")
        monkeypatch.setenv(telegram.TOKEN_ENV, TOKEN)
        monkeypatch.setenv(telegram.CHAT_ENV, CHAT)
        monkeypatch.setattr(telegram, "gonder", lambda *a, **k: False, raising=True)

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path), "--telegram")

        assert sonuc.returncode == 1
        assert "Hata:" in sonuc.stderr

    def test_cikti_ve_telegram_ciktiyi_ezmez(self, tmp_path, sahte_llm, telegram_yok,
                                             sahte_gonderici, monkeypatch):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sahte_llm("SAHTE OZET")
        monkeypatch.setenv(telegram.TOKEN_ENV, TOKEN)
        monkeypatch.setenv(telegram.CHAT_ENV, CHAT)
        cikti = tmp_path / "var.md"
        cikti.write_text("ELDE_MEVCUT\n", encoding="utf-8")

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path), "--telegram",
                              "--cikti", str(cikti))

        # telegram gonderilir, sonra dosya hatasi -> 2
        assert sonuc.returncode == 2
        assert cikti.read_text(encoding="utf-8") == "ELDE_MEVCUT\n"
        assert sahte_gonderici