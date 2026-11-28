import os

import pytest

import favorites
import modelmeta


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(modelmeta, "LOCAL_DIR", str(tmp_path / "local"))
    return tmp_path


def test_starring_and_unstarring_by_name_or_path(ws):
    assert favorites.names("dumps") == set() and not favorites.is_favorite("models", "a.txt")
    favorites.set_favorite("dumps", ["results/ml/x.bin", "y.bin"], True)
    favorites.set_favorite("models", ["ml/local/models/a.txt"], True)
    assert favorites.names("dumps") == {"x.bin", "y.bin"} and favorites.is_favorite("models", "a.txt")
    assert not favorites.is_favorite("models", "x.bin")                 # dumps and models are separate lists
    favorites.set_favorite("dumps", ["x.bin"], False)
    assert favorites.names("dumps") == {"y.bin"}
    assert os.path.exists(favorites.path())


def test_a_broken_file_reads_as_no_favorites(ws):
    os.makedirs(os.path.dirname(favorites.path()))
    with open(favorites.path(), "w", encoding="utf-8") as f:
        f.write("{not json")
    assert favorites.names("models") == set()


def test_rename_keeps_the_star_and_prune_drops_deleted_files(ws):
    favorites.set_favorite("models", ["a.txt", "b.txt"], True)
    favorites.rename("models", "a.txt", "c.txt")
    assert favorites.names("models") == {"b.txt", "c.txt"}
    favorites.prune("models", ["ml/models/c.txt"])                       # b.txt was deleted
    assert favorites.names("models") == {"c.txt"}


def test_renaming_a_dump_and_a_model_carries_the_star(ws, monkeypatch):
    from conftest import write_dump
    dump = str(ws / "d.bin")
    write_dump(dump, games=10)
    favorites.set_favorite("dumps", ["d.bin"], True)
    modelmeta.rename_dump(dump, "e")
    assert favorites.names("dumps") == {"e.bin"}
