"""CLI doctor command smoke tests."""

from __future__ import annotations

from config.doctor import CheckResult, run_checks, run_doctor
from config.settings import Settings


def test_run_doctor_returns_int():
    settings = Settings(_env_file=None)
    code = run_doctor(settings)
    assert isinstance(code, int)
    assert code in (0, 1)


def test_run_checks_returns_results():
    settings = Settings(_env_file=None)
    results = run_checks(settings)
    names = [r.name for r in results]
    assert "ffmpeg" in names
    assert "python deps" in names
    assert ".env loaded" in names
    assert all(isinstance(r, CheckResult) for r in results)


def test_check_dotenv_missing(tmp_path):
    from config.doctor import check_dotenv

    result = check_dotenv(tmp_path / ".env")
    assert result.status == "FAIL"


def test_check_dotenv_present(tmp_path):
    from config.doctor import check_dotenv

    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    result = check_dotenv(env)
    assert result.status == "PASS"
