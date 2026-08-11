"""Unit: E4 auto-accept decision logic — threshold boundary + deterministic sampling."""

from __future__ import annotations

import uuid

from control_plane.services.proposal_auto_accept import (
    AutoAcceptSettings,
    decide_auto_accept,
    extract_confidence,
    sampling_bucket,
)

_PID = uuid.UUID("00000000-0000-7000-8000-00000000e401")


class TestExtractConfidence:
    def test_reads_numeric_confidence(self) -> None:
        assert extract_confidence({"confidence": 0.87}) == 0.87
        assert extract_confidence({"confidence": 1}) == 1.0
        assert extract_confidence({"confidence": 0}) == 0.0

    def test_missing_or_malformed_is_none(self) -> None:
        assert extract_confidence(None) is None
        assert extract_confidence({}) is None
        assert extract_confidence({"confidence": "0.9"}) is None
        assert extract_confidence({"confidence": True}) is None
        assert extract_confidence({"confidence": None}) is None

    def test_out_of_range_is_none(self) -> None:
        assert extract_confidence({"confidence": -0.1}) is None
        assert extract_confidence({"confidence": 1.5}) is None


class TestThresholdBoundary:
    def test_policy_off_always_queues(self) -> None:
        settings = AutoAcceptSettings(threshold=None)
        d = decide_auto_accept(_PID, {"confidence": 0.99}, settings)
        assert d.action == "queue"
        assert not d.sampled_for_audit

    def test_missing_confidence_never_auto_accepts(self) -> None:
        settings = AutoAcceptSettings(threshold=0.0)
        d = decide_auto_accept(_PID, {"node_type": "risk", "title": "x"}, settings)
        assert d.action == "queue"
        assert d.confidence is None

    def test_below_threshold_queues(self) -> None:
        settings = AutoAcceptSettings(threshold=0.8)
        assert decide_auto_accept(_PID, {"confidence": 0.7999}, settings).action == "queue"

    def test_exactly_at_threshold_accepts(self) -> None:
        settings = AutoAcceptSettings(threshold=0.8)
        d = decide_auto_accept(_PID, {"confidence": 0.8}, settings)
        assert d.action == "accept"
        assert d.confidence == 0.8
        assert d.threshold == 0.8

    def test_above_threshold_accepts(self) -> None:
        settings = AutoAcceptSettings(threshold=0.8)
        assert decide_auto_accept(_PID, {"confidence": 0.95}, settings).action == "accept"


class TestSamplingDeterminism:
    def test_bucket_is_deterministic_and_in_range(self) -> None:
        ids = [uuid.uuid4() for _ in range(200)]
        buckets = [sampling_bucket(i) for i in ids]
        assert buckets == [sampling_bucket(i) for i in ids]
        assert all(0.0 <= b < 1.0 for b in buckets)

    def test_rate_zero_never_audits(self) -> None:
        settings = AutoAcceptSettings(threshold=0.5, sampling_audit_rate=0.0)
        for _ in range(50):
            d = decide_auto_accept(uuid.uuid4(), {"confidence": 0.9}, settings)
            assert d.action == "accept"

    def test_rate_one_always_audits(self) -> None:
        settings = AutoAcceptSettings(threshold=0.5, sampling_audit_rate=1.0)
        for _ in range(50):
            d = decide_auto_accept(uuid.uuid4(), {"confidence": 0.9}, settings)
            assert d.action == "audit"
            assert d.sampled_for_audit

    def test_same_proposal_always_gets_same_decision(self) -> None:
        settings = AutoAcceptSettings(threshold=0.5, sampling_audit_rate=0.35)
        first = decide_auto_accept(_PID, {"confidence": 0.9}, settings)
        for _ in range(10):
            assert decide_auto_accept(_PID, {"confidence": 0.9}, settings) == first

    def test_rate_partitions_population_roughly(self) -> None:
        # Not a statistical assertion — just proof the hash actually splits
        # the population instead of collapsing to one side.
        settings = AutoAcceptSettings(threshold=0.5, sampling_audit_rate=0.5)
        actions = {decide_auto_accept(uuid.uuid4(), {"confidence": 0.9}, settings).action for _ in range(200)}
        assert actions == {"accept", "audit"}
