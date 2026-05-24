"""Smoke tests for the backup CLI + shell-script half."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import uuid
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from control_plane.cli import dek_metadata

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKUP_SCRIPT = _REPO_ROOT / "scripts" / "backup.sh"


def _sync_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.render_as_string(hide_password=False)


@pytest.mark.integration
def test_dek_metadata_collect_returns_tenants_without_secret(postgres_engine: Engine) -> None:
    tid_one = uuid.UUID("00000000-0000-7000-8000-00000000b001")
    tid_two = uuid.UUID("00000000-0000-7000-8000-00000000b002")

    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app_tenants (id, name, tenant_dek_ciphertext, tenant_dek_key_id) "
                "VALUES (:id, :name, :ct, :kid)"
            ),
            {
                "id": str(tid_one),
                "name": "Backup Co A",
                "ct": "DO-NOT-LEAK-CIPHERTEXT-A",
                "kid": "stub-local",
            },
        )
        conn.execute(
            text(
                "INSERT INTO app_tenants (id, name, tenant_dek_ciphertext, tenant_dek_key_id) "
                "VALUES (:id, :name, :ct, :kid)"
            ),
            {
                "id": str(tid_two),
                "name": "Backup Co B",
                "ct": "DO-NOT-LEAK-CIPHERTEXT-B",
                "kid": "stub-local",
            },
        )

    payload = dek_metadata.collect(_sync_url(postgres_engine))
    serialised = json.dumps(payload)

    assert "DO-NOT-LEAK-CIPHERTEXT-A" not in serialised
    assert "DO-NOT-LEAK-CIPHERTEXT-B" not in serialised
    assert "tenant_dek_ciphertext" not in serialised

    names = {t["name"] for t in payload["tenants"]}
    assert {"Backup Co A", "Backup Co B"}.issubset(names)
    ids = {t["id"] for t in payload["tenants"]}
    assert {str(tid_one), str(tid_two)}.issubset(ids)
    for tenant in payload["tenants"]:
        if tenant["id"] in {str(tid_one), str(tid_two)}:
            assert tenant["dek_key_id"] == "stub-local"
    assert "note" not in payload


@pytest.mark.integration
def test_dek_metadata_emits_pending_note_when_no_dek_ids(postgres_engine: Engine) -> None:
    tid = uuid.UUID("00000000-0000-7000-8000-00000000b003")
    with postgres_engine.begin() as conn:
        conn.execute(text("DELETE FROM app_tenants"))
        conn.execute(
            text("INSERT INTO app_tenants (id, name, tenant_dek_key_id) VALUES (:id, :name, NULL)"),
            {"id": str(tid), "name": "No DEK Tenant"},
        )

    payload = dek_metadata.collect(_sync_url(postgres_engine))

    assert payload["note"] == "dek_management_pending"
    assert payload["tenants"][0]["id"] == str(tid)
    assert payload["tenants"][0]["dek_key_id"] is None


def test_dek_metadata_main_writes_json_to_stdout(postgres_engine: Engine) -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = dek_metadata.main(["--database-url", _sync_url(postgres_engine)])
    assert rc == 0

    parsed = json.loads(buf.getvalue())
    assert "tenants" in parsed
    assert isinstance(parsed["tenants"], list)


def test_dek_metadata_main_errors_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rc = dek_metadata.main([])
    assert rc == 2


def test_backup_script_passes_bash_syntax_check() -> None:
    assert _BACKUP_SCRIPT.is_file()
    subprocess.run(["bash", "-n", str(_BACKUP_SCRIPT)], check=True)


def test_backup_script_pins_security_invariants() -> None:
    body = _BACKUP_SCRIPT.read_text()

    assert 'if [[ -z "${S3_BUCKET:-}" ]]' in body, "must refuse to run without S3_BUCKET"
    assert "exit 2" in body, "missing S3_BUCKET must surface as exit 2"

    assert "tenant_dek_ciphertext" not in body, "backup must never name the secret column"

    assert '>"$DUMP_PATH"' in body, "pg_dump must write to a file, never to stdout"
    assert "set -euo pipefail" in body, "strict mode required"
    assert "mktemp -d" in body and "trap" in body, "temp dir cleanup must be wired"


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_backup_script_passes_shellcheck() -> None:
    subprocess.run(["shellcheck", str(_BACKUP_SCRIPT)], check=True)
