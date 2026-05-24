"""Smoke tests for the backup-prune shell script (Phase C inc 12.3).

Like `test_restore_smoke.py`, the destructive path is exercised against
a shimmed `aws` binary on PATH rather than a real (or testcontainer)
MinIO. The shim records every invocation, lets us stub the
`list-objects-v2` response with a mix of old and recent timestamped
folders, and asserts that:

  * dry-run mode never calls `aws s3 rm`
  * confirmed mode calls `aws s3 rm` exactly for folders older than the
    cutoff -- recent folders survive, unrecognized prefixes are skipped

We use a shim instead of MinIO because (a) the script's correctness
gates are purely shell-level (env validation, timestamp parsing,
dry-run vs confirmed branch), (b) the project does not have
`testcontainers[minio]` installed and the brief forbids adding deps,
and (c) the sibling backup/restore smoke tests follow the same shape.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PRUNE_SCRIPT = _REPO_ROOT / "scripts" / "backup-prune.sh"


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    base_env = {k: v for k, v in os.environ.items() if k.startswith(("PATH", "HOME", "LANG", "LC_"))}
    base_env.update(env)
    return subprocess.run(
        ["bash", str(_PRUNE_SCRIPT)],
        env=base_env,
        capture_output=True,
        text=True,
        check=False,
    )


def _install_aws_shim(tmp_path: Path, common_prefixes: list[str]) -> tuple[Path, Path]:
    """Write a fake `aws` to tmp_path/bin and return (bin_dir, calls_log).

    The shim:
      * answers `s3api list-objects-v2 ... --output text` with a single
        TAB-separated line containing the supplied CommonPrefixes
        (matching the real CLI's text shape for that --query)
      * records every argv to `calls_log` for assertion afterwards
      * exits 0 for `s3 rm ... --recursive`
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    calls_log = tmp_path / "aws-calls.log"

    # Stage the response on disk as the real `aws --output text` would render
    # it: prefixes separated by literal TAB on a single line. Avoids any shell
    # quoting / escape ambiguity in the heredoc'd shim body.
    response_file = tmp_path / "aws-list-response.txt"
    if common_prefixes:
        response_file.write_text("\t".join(common_prefixes) + "\n")
    else:
        response_file.write_text("None\n")

    shim = bin_dir / "aws"
    shim.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            printf '%s\\n' "$*" >> {calls_log}
            for arg in "$@"; do
              if [[ "$arg" == "list-objects-v2" ]]; then
                cat {response_file}
                exit 0
              fi
              if [[ "$arg" == "rm" ]]; then
                exit 0
              fi
            done
            exit 0
            """
        )
    )
    shim.chmod(0o755)
    return bin_dir, calls_log


def _base_env(bin_dir: Path) -> dict[str, str]:
    return {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "S3_BUCKET": "deployai-test-backups",
        "AWS_ACCESS_KEY_ID": "x",
        "AWS_SECRET_ACCESS_KEY": "x",
        "BACKUP_RETENTION_DAYS": "1",
    }


def test_prune_script_passes_bash_syntax_check() -> None:
    assert _PRUNE_SCRIPT.is_file()
    subprocess.run(["bash", "-n", str(_PRUNE_SCRIPT)], check=True)


def test_prune_script_pins_security_invariants() -> None:
    body = _PRUNE_SCRIPT.read_text()

    assert "set -euo pipefail" in body, "strict mode required"
    assert 'if [[ -z "${S3_BUCKET:-}" ]]' in body, "must refuse to run without S3_BUCKET"
    assert "exit 2" in body, "missing required env must surface as exit 2"

    assert "DEPLOYAI_PRUNE_CONFIRM" in body, "must guard destructive path on operator confirmation"
    assert "BACKUP_RETENTION_DAYS" in body, "must read retention window from env"
    assert "=~ ^[0-9]+$" in body, "must validate BACKUP_RETENTION_DAYS is numeric"

    # The script must never name the bucket on the s3 rm path without the
    # timestamp prefix -- it deletes objects under $S3_PREFIX/<ts>/ only.
    assert 'aws "${aws_args[@]}" s3 rb' not in body, "must never `s3 rb` (bucket-delete)"

    # Unrecognized prefixes are skipped, not deleted.
    assert "unrecognized prefix" in body, "must skip + log non-timestamp prefixes"

    assert "tenant_dek_ciphertext" not in body, "prune must never reference the secret column"


def test_prune_refuses_without_s3_bucket() -> None:
    result = _run({"AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "x"})
    assert result.returncode == 2, result.stderr
    assert "S3_BUCKET" in result.stderr


def test_prune_refuses_without_aws_creds() -> None:
    result = _run({"S3_BUCKET": "deployai-test-backups"})
    assert result.returncode == 2, result.stderr
    assert "AWS_ACCESS_KEY_ID" in result.stderr or "AWS_SECRET_ACCESS_KEY" in result.stderr


def test_prune_refuses_non_numeric_retention(tmp_path: Path) -> None:
    bin_dir, _ = _install_aws_shim(tmp_path, [])
    env = _base_env(bin_dir)
    env["BACKUP_RETENTION_DAYS"] = "thirty"
    result = _run(env)
    assert result.returncode == 2, result.stderr
    assert "BACKUP_RETENTION_DAYS" in result.stderr


def test_prune_refuses_zero_retention(tmp_path: Path) -> None:
    bin_dir, _ = _install_aws_shim(tmp_path, [])
    env = _base_env(bin_dir)
    env["BACKUP_RETENTION_DAYS"] = "0"
    result = _run(env)
    assert result.returncode == 2, result.stderr
    assert "BACKUP_RETENTION_DAYS" in result.stderr


def _ts(delta_days: int) -> str:
    """Render a UTC timestamp `delta_days` from now in backup.sh's format."""
    when = datetime.now(UTC) - timedelta(days=delta_days)
    return when.strftime("%Y%m%dT%H%M%SZ")


def test_prune_dry_run_lists_but_does_not_delete(tmp_path: Path) -> None:
    """Without DEPLOYAI_PRUNE_CONFIRM the script must never call `aws s3 rm`."""
    old_one = _ts(30)
    old_two = _ts(15)
    recent = _ts(0)
    prefixes = [
        f"deployai/backups/{old_one}/",
        f"deployai/backups/{old_two}/",
        f"deployai/backups/{recent}/",
        "deployai/backups/manual-test-upload/",  # unrecognized prefix
    ]
    bin_dir, calls_log = _install_aws_shim(tmp_path, prefixes)

    result = _run(_base_env(bin_dir))

    assert result.returncode == 0, result.stderr
    assert "DRY-RUN" in result.stdout or "DRY" in result.stderr
    assert "WOULD delete" in result.stderr
    assert old_one in result.stderr
    assert old_two in result.stderr
    assert recent not in result.stderr.replace("WOULD delete", "")  # not flagged
    assert "unrecognized prefix" in result.stderr
    assert "manual-test-upload" in result.stderr

    calls = calls_log.read_text() if calls_log.exists() else ""
    assert "list-objects-v2" in calls
    assert " rm " not in calls and "s3 rm" not in calls, f"dry-run must not invoke `aws s3 rm`, got calls:\n{calls}"


def test_prune_confirmed_deletes_only_old_folders(tmp_path: Path) -> None:
    """With DEPLOYAI_PRUNE_CONFIRM=YES the script deletes old folders, keeps recent."""
    old_one = _ts(30)
    old_two = _ts(15)
    recent = _ts(0)
    prefixes = [
        f"deployai/backups/{old_one}/",
        f"deployai/backups/{old_two}/",
        f"deployai/backups/{recent}/",
        "deployai/backups/manual-test-upload/",  # unrecognized -- must skip
    ]
    bin_dir, calls_log = _install_aws_shim(tmp_path, prefixes)
    env = _base_env(bin_dir)
    env["DEPLOYAI_PRUNE_CONFIRM"] = "YES"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert "kept=1" in result.stdout
    assert "deleted=2" in result.stdout
    assert "skipped=1" in result.stdout

    calls = calls_log.read_text() if calls_log.exists() else ""
    # Each old folder triggers one `aws s3 rm ... --recursive`. The recent
    # folder and the unrecognized prefix must not appear in any rm call.
    assert calls.count("s3 rm ") == 2, f"expected 2 rm calls, got:\n{calls}"
    assert f"deployai/backups/{old_one}/" in calls
    assert f"deployai/backups/{old_two}/" in calls
    assert f"deployai/backups/{recent}/" not in [
        line.replace("WOULD delete", "") for line in calls.splitlines() if "s3 rm" in line
    ]
    assert "manual-test-upload" not in calls.replace("list-objects-v2", "")


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_prune_script_passes_shellcheck() -> None:
    subprocess.run(["shellcheck", str(_PRUNE_SCRIPT)], check=True)
