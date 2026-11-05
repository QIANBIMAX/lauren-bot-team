"""W0 doctor: machine-readable report on the current environment."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from lauren_team_kit.cli import main
from lauren_team_kit.doctor import SCHEMA, collect_report


def test_doctor_report_shape_and_linux_facts() -> None:
    report = collect_report()
    assert report["schema"] == SCHEMA
    assert isinstance(report["hints"], list)
    assert report["hints"]
    assert all(isinstance(item, str) and len(item) < 400 for item in report["hints"])

    assert report["os"]["system"]
    assert report["os"]["machine"]
    assert report["python"]["version"]
    assert report["python"]["version_info"][0] == sys.version_info.major
    assert report["package"]["name"] == "lauren_team_kit"
    assert report["package"]["import_ok"] is True
    assert isinstance(report["lock"]["fcntl_present"], bool)
    assert "W3" in report["lock"]["hint"]
    assert report["subprocess_utf8"]["sample_ok"] is True
    assert isinstance(report["bash"]["present"], bool)
    assert report["bash"]["optional"] is True
    assert report["workbench"]["probed"] is False
    assert report["workbench"]["omb_gui_import"] == "not_probed"
    assert report["workbench"]["omb_delegate"] == "not_connected"
    assert report["workbench"]["engine"] == "not_probed"
    assert any("不探测" in hint for hint in report["hints"])

    labels = [row["label"] for row in report["writable_dirs"]]
    assert labels[:2] == ["temp", "cwd"]
    assert report["writable_dirs"][0]["writable"] is True

    if sys.platform.startswith("linux"):
        assert report["ok"] is True
        assert report["required_failures"] == []
        assert report["os"]["system"] == "Linux"
        assert report["python"]["ok"] is True
        assert report["git"]["present"] is True
        assert report["git"]["merge_tree_write_tree"] is True
        assert report["lock"]["fcntl_present"] is True
        assert report["lock"]["capability"] == "fcntl"
        assert report["long_path"]["status"] == "not_applicable"
        assert report["long_path"]["enabled"] is None
    elif sys.platform == "win32":
        assert report["lock"]["fcntl_present"] is False
        assert report["lock"]["capability"] == "msvcrt"
        assert report["lock"]["cross_process_lock"] == "msvcrt_locking"
        assert "no-op" in report["lock"]["hint"]
        assert report["long_path"]["applicable"] is True


def test_doctor_cli_prints_json_only(capsys) -> None:
    rc = main(["doctor"])
    captured = capsys.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["schema"] == SCHEMA
    assert data["workbench"]["probed"] is False
    if sys.platform.startswith("linux"):
        assert rc == 0
        assert data["ok"] is True


def test_doctor_root_must_be_writable_directory(tmp_path: Path, capsys) -> None:
    target = tmp_path / "not-a-dir"
    target.write_text("x", encoding="utf-8")
    rc = main(["doctor", "--root", str(target)])
    data = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert data["ok"] is False
    assert "writable:root" in data["required_failures"]
    root_row = next(row for row in data["writable_dirs"] if row["label"] == "root")
    assert root_row["writable"] is False
    assert "不会提权" in root_row["hint"] or "不是目录" in root_row["hint"]


def test_doctor_omits_environment_secrets(monkeypatch) -> None:
    monkeypatch.setenv("LAUREN_DUMMY_API_KEY", "sk-super-secret-value")
    monkeypatch.setenv("GIT_SSL_NO_VERIFY", "1")
    blob = json.dumps(collect_report(), ensure_ascii=False)
    assert "sk-super-secret-value" not in blob
    assert "LAUREN_DUMMY_API_KEY" not in blob
    assert "GIT_SSL_NO_VERIFY" not in blob


def test_git_probe_does_not_rewrite_config(monkeypatch) -> None:
    calls: list[list[str]] = []
    real_run = subprocess.run

    def wrapped(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(cmd, (list, tuple)):
            calls.append([str(part) for part in cmd])
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr("lauren_team_kit.doctor.subprocess.run", wrapped)
    collect_report()
    git_calls = [cmd for cmd in calls if cmd and Path(cmd[0]).name.startswith("git")]
    assert git_calls, "doctor should probe git"
    saw_config_read = False
    for cmd in git_calls:
        assert "--system" not in cmd
        assert "--global" not in cmd
        joined = " ".join(cmd).lower()
        assert "sslverify" not in joined
        assert "http.sslverify" not in joined
        if "config" in cmd:
            saw_config_read = True
            assert "--get" in cmd or "--get-all" in cmd
            assert "--unset" not in cmd
            assert "--replace-all" not in cmd
            assert "--add" not in cmd
    assert saw_config_read, "doctor should read autocrlf / safe.directory without writing"


def test_doctor_source_does_not_disable_tls() -> None:
    src = Path(collect_report.__code__.co_filename).read_text(encoding="utf-8")
    # The child environment drops GIT_SSL_NO_VERIFY; it must not set it.
    assert 'GIT_SSL_NO_VERIFY"] =' not in src
    assert "GIT_SSL_NO_VERIFY'] =" not in src
    assert "sslVerify" not in src
    assert '["git", "config"' not in src
    assert "['git', 'config'" not in src
