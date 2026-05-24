"""Smoke tests for the restore shell script (Phase C inc 12.2).

The script is destructive by design, so the tests never invoke the real
`pg_restore` / `aws` chain against the testcontainer. They cover:

* bash syntax + (optionally) shellcheck cleanliness
* the safety-envelope invariants pinned in the script body
* CLI-level refusal behaviour: missing $BACKUP, non-s3 URI, missing AWS
  creds, missing DEPLOYAI_RESTORE_CONFIRM
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RESTORE_SCRIPT = _REPO_ROOT / "scripts" / "restore.sh"


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    base_env = {k: v for k, v in os.environ.items() if k.startswith(("PATH", "HOME", "LANG", "LC_"))}
    base_env.update(env)
    return subprocess.run(
        ["bash", str(_RESTORE_SCRIPT), *args],
        env=base_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_restore_script_passes_bash_syntax_check() -> None:
    assert _RESTORE_SCRIPT.is_file()
    subprocess.run(["bash", "-n", str(_RESTORE_SCRIPT)], check=True)


def test_restore_script_pins_security_invariants() -> None:
    body = _RESTORE_SCRIPT.read_text()

    assert "set -euo pipefail" in body, "strict mode required"
    assert "mktemp -d" in body and "trap" in body, "temp dir cleanup must be wired"

    assert "DEPLOYAI_RESTORE_CONFIRM" in body, "must guard on operator confirmation"
    assert "DEPLOYAI_RESTORE_FORCE_OVERWRITE" in body, "must guard non-empty DB overwrite"

    assert "--single-transaction" in body, "pg_restore must roll back on failure"

    assert "tenant_dek_ciphertext" not in body, "restore must never name the secret column"

    assert "s3://" in body, "must validate BACKUP is an s3:// URI"

    assert "dump_bytes" in body and "-le 0" in body, "must refuse to restore an empty dump"


def test_restore_refuses_without_backup() -> None:
    result = _run({})
    assert result.returncode == 2, result.stderr
    assert "BACKUP" in result.stderr


def test_restore_refuses_non_s3_backup() -> None:
    result = _run(
        {
            "AWS_ACCESS_KEY_ID": "x",
            "AWS_SECRET_ACCESS_KEY": "x",
            "DEPLOYAI_RESTORE_CONFIRM": "YES",
        },
        "/tmp/local-backup",
    )
    assert result.returncode == 2, result.stderr
    assert "s3://" in result.stderr


def test_restore_refuses_without_aws_creds() -> None:
    result = _run(
        {"DEPLOYAI_RESTORE_CONFIRM": "YES"},
        "s3://bucket/prefix/20260524T000000Z/",
    )
    assert result.returncode == 2, result.stderr
    assert "AWS_ACCESS_KEY_ID" in result.stderr or "AWS_SECRET_ACCESS_KEY" in result.stderr


def test_restore_refuses_without_confirm() -> None:
    result = _run(
        {
            "AWS_ACCESS_KEY_ID": "x",
            "AWS_SECRET_ACCESS_KEY": "x",
        },
        "s3://bucket/prefix/20260524T000000Z/",
    )
    assert result.returncode == 2, result.stderr
    assert "DEPLOYAI_RESTORE_CONFIRM" in result.stderr


def test_restore_refuses_wrong_confirm_value() -> None:
    result = _run(
        {
            "AWS_ACCESS_KEY_ID": "x",
            "AWS_SECRET_ACCESS_KEY": "x",
            "DEPLOYAI_RESTORE_CONFIRM": "yes",
        },
        "s3://bucket/prefix/20260524T000000Z/",
    )
    assert result.returncode == 2, result.stderr
    assert "DEPLOYAI_RESTORE_CONFIRM" in result.stderr


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_restore_script_passes_shellcheck() -> None:
    subprocess.run(["shellcheck", str(_RESTORE_SCRIPT)], check=True)
