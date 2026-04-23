from deployai_authz.resolver import is_allowed


def test_platform_admin_ingest_runs() -> None:
    d = is_allowed("platform_admin", "ingest:view_runs")
    assert d.allow is True


def test_auditor_no_promote() -> None:
    d = is_allowed("external_auditor", "admin:promote_schema")
    assert d.allow is False
