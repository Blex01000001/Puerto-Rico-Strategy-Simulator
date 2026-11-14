import json
import os

import numpy as np
import pytest

import positions


def test_load_round_trip(dump):
    a = dump("a.bin", games=10)
    b = dump("b.bin", games=6, seed=1)
    x, reward, win, groups, names, metas = positions.load([a, b])
    assert x.shape == (10 * 20 + 6 * 20, 6)
    assert x.dtype == np.int16
    assert names[1] == "round"
    assert len(np.unique(groups)) == 16  # games of different files never share a group
    assert [m["path"] for m in metas] == [a, b]
    assert np.all((reward >= 0) & (reward <= 1))


def test_wildcards_and_directories_are_expanded(dump, tmp_path):
    dump("a.bin")
    dump("b.bin")
    pattern = os.path.join(str(tmp_path), "*.bin")
    assert [os.path.basename(p) for p in positions.expand([pattern])] == ["a.bin", "b.bin"]
    assert positions.expand([str(tmp_path)]) == positions.expand([pattern])
    assert len(positions.expand([pattern, str(tmp_path)])) == 2  # duplicates removed
    with pytest.raises(ValueError, match="no position dump"):
        positions.expand([os.path.join(str(tmp_path), "*.nothing")])


def test_split_is_by_game(dump):
    _, _, _, groups, _, _ = positions.load([dump(games=50)])
    valid = positions.split(groups, 0.2, seed=3)
    assert not set(groups[valid]) & set(groups[~valid])
    assert len(np.unique(groups[valid])) == 10


def test_cancelled_dump_is_readable_and_old_dumps_count_as_completed(dump):
    a = dump("a.bin", status="cancelled")
    b = dump("b.bin")
    with open(b + ".json", encoding="utf-8") as f:
        meta = json.load(f)
    del meta["status"]
    with open(b + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f)
    *_, metas = positions.load([a, b])
    assert [m["status"] for m in metas] == ["cancelled", "completed"]


@pytest.mark.parametrize("override, message", [
    ({"formatVersion": 2}, "format version"),
    ({"format": "other"}, "not a position dump"),
    ({"rows": 999}, "size does not match"),
    ({"recordBytes": 4}, "record size"),
])
def test_bad_metadata_is_refused(dump, override, message):
    with pytest.raises(ValueError, match=message):
        positions.load([dump(**override)])


def test_missing_metadata_is_refused(dump):
    a = dump()
    os.remove(a + ".json")
    with pytest.raises(ValueError, match="metadata"):
        positions.load([a])


@pytest.mark.parametrize("override, message", [
    ({"featureVersion": 2}, "featureVersion"),
    ({"players": 3}, "players"),
])
def test_files_must_agree(dump, override, message):
    a = dump("a.bin")
    b = dump("b.bin", **override)
    with pytest.raises(ValueError, match=message):
        positions.load([a, b])


def test_feature_lists_must_agree(dump):
    a = dump("a.bin")
    b = dump("b.bin", names=["players", "round", "x", "y", "z", "w"])
    with pytest.raises(ValueError, match="feature list"):
        positions.load([a, b])
