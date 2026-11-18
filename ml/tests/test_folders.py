import os

import pytest

import folders


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(folders.subprocess, "Popen", lambda args, **kw: seen.append(args))
    monkeypatch.setattr(folders.sys, "platform", "linux")
    return seen


def test_opens_a_folder_or_the_folder_of_a_file(tmp_path, calls):
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "a.bin").write_text("x")
    assert folders.open_folder(str(tmp_path / "results"), str(tmp_path)) == (True, "")
    assert folders.open_folder(str(tmp_path / "results" / "a.bin"), str(tmp_path)) == (True, "")
    assert calls == [["xdg-open", str(tmp_path / "results")]] * 2


def test_refuses_folders_outside_the_project_and_missing_ones(tmp_path, calls):
    root = tmp_path / "proj"
    root.mkdir()
    ok, why = folders.open_folder(str(tmp_path), str(root))
    assert not ok and "專案" in why
    ok, why = folders.open_folder(os.path.join(str(root), "results", "ml"), str(root))
    assert not ok and "還不存在" in why
    assert calls == []


def test_a_machine_without_a_file_manager_gets_a_message(tmp_path, monkeypatch):
    monkeypatch.setattr(folders.sys, "platform", "linux")

    def boom(*a, **kw):
        raise FileNotFoundError("xdg-open")
    monkeypatch.setattr(folders.subprocess, "Popen", boom)
    ok, why = folders.open_folder(str(tmp_path), str(tmp_path))
    assert not ok and "檔案管理員" in why
