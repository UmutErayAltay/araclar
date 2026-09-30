import pytest

from orkestra.queue import Queue


@pytest.fixture()
def db_yolu(tmp_path):
    return tmp_path / "orkestra-test.db"


@pytest.fixture()
def kuyruk(db_yolu):
    q = Queue(db_yolu)
    yield q
    q.kapat()