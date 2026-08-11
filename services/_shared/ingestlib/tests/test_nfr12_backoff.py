from deployai_ingestlib.nfr12_backoff import nfr12_visibility_timeout_seconds


def test_nfr12_exponential_capped() -> None:
    assert nfr12_visibility_timeout_seconds(0) == 2
    assert nfr12_visibility_timeout_seconds(1) == 4
    assert nfr12_visibility_timeout_seconds(2) == 8
    assert nfr12_visibility_timeout_seconds(20) == 300
