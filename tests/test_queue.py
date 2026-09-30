"""Kuyruk: ekleme, listeleme, FIFO, gecisler, iptal, tekrar, kalicilik, kurtarma."""

import os
from pathlib import Path

import pytest

from orkestra.models import (
    Durum,
    GecersizGecis,
    GecersizGirdi,
    GorevBulunamadi,
    RunSonuc,
    Task,
    utc_simdi,
)
from orkestra.queue import YARIM_KALDI_HATASI, Queue
from orkestra.runner import FakeRunner


# -- ekleme / listeleme -------------------------------------------------


def test_ekle_bekliyor_durumunda(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "kisa bir is")
    assert isinstance(gorev, Task)
    assert gorev.durum is Durum.BEKLIYOR
    assert gorev.id > 0
    assert gorev.ajan == "bunny-coder"


def test_ekle_zaman_damgasi_iso8601(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    assert gorev.olusturma == utc_simdi() or gorev.olusturma.endswith("Z")
    assert gorev.olusturma.endswith("Z")


def test_liste_filtresiz_kimlik_sirasi(kuyruk):
    a = kuyruk.ekle("bunny-coder", "birinci")
    b = kuyruk.ekle("nemotron", "ikinci")
    assert [g.id for g in kuyruk.liste()] == [a.id, b.id]


def test_liste_durum_filtresi(kuyruk):
    a = kuyruk.ekle("bunny-coder", "birinci")
    b = kuyruk.ekle("nemotron", "ikinci")
    kuyruk.iptal(b.id)
    assert [g.id for g in kuyruk.liste(Durum.BEKLIYOR)] == [a.id]
    assert [g.id for g in kuyruk.liste("iptal")] == [b.id]
    assert kuyruk.liste("bitti") == []


def test_al_bilinmeyen_kimlik(kuyruk):
    with pytest.raises(GorevBulunamadi):
        kuyruk.al(4242)


def test_var_mi(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    assert kuyruk.var_mi(gorev.id)
    assert not kuyruk.var_mi(gorev.id + 999)


def test_onizleme_kisaltir(kuyruk):
    kisa = kuyruk.ekle("bunny-coder", "kisa")
    assert kisa.onizleme == "kisa"
    uzun = kuyruk.ekle("bunny-coder", "x" * 200)
    assert len(uzun.onizleme) == 63 and uzun.onizleme.endswith("...")


# -- FIFO ---------------------------------------------------------------


def test_sonraki_bekleyen_fifo_en_eski(kuyruk):
    ilk = kuyruk.ekle("bunny-coder", "ilk")
    ikinci = kuyruk.ekle("bunny-coder", "ikinci")
    ucuncu = kuyruk.ekle("bunny-coder", "ucuncu")
    assert kuyruk.sonraki_bekleyen().id == ilk.id
    kuyruk.gecis(ilk.id, Durum.IPTAL)
    assert kuyruk.sonraki_bekleyen().id == ikinci.id
    kuyruk.gecis(ikinci.id, Durum.IPTAL)
    assert kuyruk.sonraki_bekleyen().id == ucuncu.id


def test_sonraki_bekleyen_bos_kuyruk(kuyruk):
    assert kuyruk.sonraki_bekleyen() is None


def test_sonraki_bekleyen_calisan_gorevi_atlar(kuyruk):
    ilk = kuyruk.ekle("bunny-coder", "ilk")
    kuyruk.gecis(ilk.id, Durum.CALISIYOR)
    ikinci = kuyruk.ekle("bunny-coder", "ikinci")
    assert kuyruk.sonraki_bekleyen().id == ikinci.id


# -- gecis / iptal / tekrar --------------------------------------------


def test_gecis_gecerli(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    assert kuyruk.gecis(gorev.id, Durum.CALISIYOR).durum is Durum.CALISIYOR
    assert kuyruk.gecis(gorev.id, Durum.BITTI).durum is Durum.BITTI


def test_gecis_gecersiz_db_degismez(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    with pytest.raises(GecersizGecis):
        kuyruk.gecis(gorev.id, Durum.BITTI)
    assert kuyruk.al(gorev.id).durum is Durum.BEKLIYOR


def test_son_durumden_cikamaz(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    kuyruk.iptal(gorev.id)
    with pytest.raises(GecersizGecis):
        kuyruk.gecis(gorev.id, Durum.BEKLIYOR)
    assert kuyruk.al(gorev.id).durum is Durum.IPTAL


def test_iptal(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    assert kuyruk.iptal(gorev.id).durum is Durum.IPTAL


def test_iptal_olmayan_gorev(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    with pytest.raises(GorevBulunamadi):
        kuyruk.iptal(gorev.id + 5)


def test_tekrar_hata_dan_bekliyor(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    kuyruk.gecis(gorev.id, Durum.CALISIYOR)
    kuyruk.gecis(gorev.id, Durum.HATA)
    assert kuyruk.tekrar(gorev.id).durum is Durum.BEKLIYOR


def test_tekrar_bekleyen_gorevde_gecersiz(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    with pytest.raises(GecersizGecis):
        kuyruk.tekrar(gorev.id)
    assert kuyruk.al(gorev.id).durum is Durum.BEKLIYOR


def test_onay_bekliyor_tekrar_akisi(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    kuyruk.gecis(gorev.id, Durum.CALISIYOR)
    kuyruk.gecis(gorev.id, Durum.ONAY_BEKLIYOR)
    assert kuyruk.gecis(gorev.id, Durum.BEKLIYOR).durum is Durum.BEKLIYOR


# -- kalicilik ----------------------------------------------------------


def test_kalicilik_db_kapat_ve_yeniden_ac(db_yolu):
    q = Queue(db_yolu)
    a = q.ekle("bunny-coder", "kalici is")
    b = q.ekle("nemotron", "ikinci is")
    q.gecis(a.id, Durum.CALISIYOR)
    q.gecis(a.id, Durum.HATA)
    q.iptal(b.id)
    q.kapat()

    q2 = Queue(db_yolu)
    assert q2.al(a.id).durum is Durum.HATA
    assert q2.al(b.id).durum is Durum.IPTAL
    assert q2.al(a.id).istem == "kalici is"
    assert q2.al(a.id).ajan == "bunny-coder"
    q2.kapat()


def test_kurtarma_acikca_cagrilir(db_yolu):
    """Yarim kalan calisiyor gorev, yeni Queue acilisinda kendiliginden duzelmez."""
    q = Queue(db_yolu)
    gorev = q.ekle("bunny-coder", "yarim kalan")
    q.gecis(gorev.id, Durum.CALISIYOR)
    q.kapat()

    q2 = Queue(db_yolu)
    assert q2.al(gorev.id).durum is Durum.CALISIYOR  # hâlâ calisiyor
    kurtarilan = q2.kurtar()  # yalnızca açık çağrıyla düzeltilir
    assert [g.id for g in kurtarilan] == [gorev.id]
    assert q2.al(gorev.id).durum is Durum.HATA
    q2.kapat()


def test_kurtarma_calisan_gorevleri_hata_cevirir(db_yolu):
    q = Queue(db_yolu)
    a = q.ekle("bunny-coder", "bir")
    b = q.ekle("bunny-coder", "iki")
    c = q.ekle("bunny-coder", "uctu")
    q.gecis(a.id, Durum.CALISIYOR)
    q.gecis(b.id, Durum.CALISIYOR)
    q.iptal(c.id)
    q.kapat()

    q2 = Queue(db_yolu)
    kurtarilan = q2.kurtar()
    assert {g.id for g in kurtarilan} == {a.id, b.id}
    assert q2.al(a.id).durum is Durum.HATA
    assert q2.al(b.id).durum is Durum.HATA
    assert q2.al(c.id).durum is Durum.IPTAL
    assert q2.kurtar() == []  # ikinci cagrida bos
    q2.kapat()


def test_kurtarma_acik_kosu_kaydini_kapatir(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    kuyruk.gecis(gorev.id, Durum.CALISIYOR)
    # Surec olmesi benzetimi: yarim acik bir kosu kaydi birakiliyor.
    kuyruk._baglanti.execute(
        "INSERT INTO runs (task_id, baslangic) VALUES (?, ?)", (gorev.id, utc_simdi())
    )
    assert len(kurtarilan := kuyruk.kurtar()) == 1
    assert kurtarilan[0].durum is Durum.HATA
    kosu = kuyruk.kosular(gorev.id)[-1]
    assert kosu.hata == YARIM_KALDI_HATASI
    assert kosu.bitis is not None


# -- tablo / sema -------------------------------------------------------


def test_quota_snapshots_tablosu_var(kuyruk):
    satir = kuyruk._baglanti.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='quota_snapshots'"
    ).fetchone()
    assert satir is not None


def test_db_dosyasi_klasoru_olusur(tmp_path):
    hedef = tmp_path / "yeni" / "klasor" / "o.db"
    q = Queue(hedef)
    assert hedef.exists()
    q.kapat()


def test_bos_kuyruk_calistir_bir_none(kuyruk):
    assert kuyruk.calistir_bir(object()) is None


# -- Dalga B: cikti_yolu artik gercek dosya yolu; kayitlar maskelenir ----

# Gerçek anahtar test kaynağında tam literal olarak YAZILMAZ.
GIZLI_ANAHTAR = "sk-" + "a1" * 15


def test_cikti_yolu_gercek_dosya_yolu(kuyruk, tmp_path):
    """`runs.cikti_yolu` metin DEĞİL, log dosyasının yoludur."""
    log = tmp_path / "gorev-1.log"
    log.write_text("kayitli cikti\n", encoding="utf-8")
    kuyruk.ekle("bunny-coder", "is")
    _, kosu = kuyruk.calistir_bir(FakeRunner(calistir_ile=lambda t: RunSonuc(cikti=str(log))))
    assert kosu.cikti_yolu == str(log)
    assert Path(kosu.cikti_yolu).is_file()


def test_hata_kaydi_maskelenir(kuyruk):
    """Runner hata metni kayda ÖNCE maskelenir (çıktıda sır olabilir)."""
    kuyruk.ekle("bunny-coder", "is")
    sirli = f"claude patladi: {GIZLI_ANAHTAR}"
    _, kosu = kuyruk.calistir_bir(FakeRunner(calistir_ile=lambda t: RunSonuc(cikis_kodu=1, hata=sirli)))
    assert GIZLI_ANAHTAR not in kosu.hata
    assert "[maskeli]" in kosu.hata


def test_cikti_yolu_kaydi_maskelenir(kuyruk):
    kuyruk.ekle("bunny-coder", "is")
    sirli = f"/tmp/{GIZLI_ANAHTAR}/log.txt"
    _, kosu = kuyruk.calistir_bir(FakeRunner(calistir_ile=lambda t: RunSonuc(cikti=sirli)))
    assert GIZLI_ANAHTAR not in kosu.cikti_yolu


def test_istisna_metni_maskelenir(kuyruk):
    """İstisna metni runner çıktısından sır taşıyabilir; kayda maskeli gider."""
    kuyruk.ekle("bunny-coder", "is")

    def patlat(_task):
        raise RuntimeError(f"baglanti hatasi: {GIZLI_ANAHTAR}")

    _, kosu = kuyruk.calistir_bir(FakeRunner(calistir_ile=patlat))
    assert "RuntimeError" in kosu.hata
    assert GIZLI_ANAHTAR not in kosu.hata
    assert "[maskeli]" in kosu.hata


def test_kanit_yollari_maskelenir(kuyruk):
    kuyruk.ekle("bunny-coder", "is")
    _, kosu = kuyruk.calistir_bir(
        FakeRunner(calistir_ile=lambda t: RunSonuc(kanit_yollari=[f"/k/{GIZLI_ANAHTAR}/a.png"]))
    )
    assert GIZLI_ANAHTAR not in " ".join(kosu.kanit_yollari)


def test_temiz_hata_metni_bozulmaz(kuyruk):
    kuyruk.ekle("bunny-coder", "is")
    _, kosu = kuyruk.calistir_bir(
        FakeRunner(calistir_ile=lambda t: RunSonuc(cikis_kodu=1, hata="claude cikis kodu 3"))
    )
    assert kosu.hata == "claude cikis kodu 3"


def test_none_hata_ve_cikti_kaydedilir(kuyruk):
    kuyruk.ekle("bunny-coder", "is")
    _, kosu = kuyruk.calistir_bir(FakeRunner(calistir_ile=lambda t: RunSonuc()))
    assert kosu.hata is None and kosu.cikti_yolu is None


# -- Dalga B: atomik bekliyor -> calisiyor ------------------------------


def test_atomik_al_bekleyeni_calisiyora_cekir(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    alinan = kuyruk._atomik_al()
    assert alinan.id == gorev.id
    assert alinan.durum is Durum.CALISIYOR
    # İkinci çağrı aynı görevi alamaz.
    assert kuyruk._atomik_al() is None


def test_atomik_al_ikinci_goreve_gecer(kuyruk):
    kuyruk.ekle("bunny-coder", "bir")
    kuyruk.ekle("bunny-coder", "iki")
    ilk = kuyruk._atomik_al()
    ikinci = kuyruk._atomik_al()
    assert ilk.id == 1 and ikinci.id == 2
    assert ilk.istem == "bir" and ikinci.istem == "iki"


def test_atomik_al_bos_kuyruk_none(kuyruk):
    assert kuyruk._atomik_al() is None


YARIS_SENARYO = "yaris_senaryo.py"


@pytest.mark.skipif(os.name == "nt", reason="POSIX sinyalleri (start_new_session) gerekli")
def test_iki_surec_yarisi_her_gorevi_tek_kez_calistirir(tmp_path):
    """GERÇEK iki süreç aynı kuyruğa yarışır: her görev tam bir kez çalışır.

    `multiprocessing` ile iki bağımsız Queue bağlantısı açılır; ikisi de
    `calistir_bir` çağırır. Atomik UPDATE olmazsa aynı görev iki kez çalışırdı.
    """
    import subprocess
    import sys
    import textwrap

    db = tmp_path / "yaris.db"
    gorev_sayisi = 24

    with Queue(db) as q:
        for i in range(gorev_sayisi):
            q.ekle("bunny-coder", f"gorev {i}")

    senaryo = tmp_path / YARIS_SENARYO
    senaryo.write_text(
        textwrap.dedent(
            f"""
            import sys
            from orkestra.queue import Queue
            from orkestra.runner import FakeRunner

            db, kimlik = sys.argv[1], sys.argv[2]
            q = Queue(db)
            cizilen = []
            for _ in range({gorev_sayisi + 5}):
                sonuc = q.calistir_bir(FakeRunner("basari"))
                if sonuc is None:
                    break
                gorev, _kosu = sonuc
                cizilen.append(gorev.id)
            with open(db + "." + kimlik, "w", encoding="utf-8") as f:
                f.write(",".join(map(str, cizilen)))
            q.kapat()
            """
        ),
        encoding="utf-8",
    )

    repo = Path(__file__).resolve().parent.parent
    cevre = dict(os.environ)
    # Alt süreç `orkestra`'yı PYTHONPATH üzerinden görsün (cwd yetmiyor).
    cevre["PYTHONPATH"] = str(repo) + os.pathsep + cevre.get("PYTHONPATH", "")
    surecler = [
        subprocess.Popen(
            [sys.executable, str(senaryo), str(db), kimlik],
            cwd=str(repo),
            env=cevre,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for kimlik in ("a", "b")
    ]
    hatalar = []
    for s in surecler:
        _, hata = s.communicate(timeout=120)
        if s.returncode != 0:
            hatalar.append(hata)
    assert not hatalar, hatalar

    tum = []
    for kimlik in ("a", "b"):
        yol = tmp_path / f"{db}.{kimlik}"
        icerik = yol.read_text(encoding="utf-8").strip()
        if icerik:
            tum += [int(x) for x in icerik.split(",")]

    # Her görev tam bir kez: ne eksik ne fazla.
    assert sorted(tum) == list(range(1, gorev_sayisi + 1))
    assert len(tum) == len(set(tum)), "ayni gorev birden fazla calistirildi"

    with Queue(db) as q:
        assert all(g.durum is Durum.BITTI for g in q.liste())
        assert len(q.liste()) == gorev_sayisi