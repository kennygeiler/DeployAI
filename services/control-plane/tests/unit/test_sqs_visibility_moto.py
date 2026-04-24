"""Story 3-6: SQS change_message_visibility with NFR12 delays (moto)."""

from __future__ import annotations

import boto3
from ingest.nfr12_backoff import nfr12_visibility_timeout_seconds
from moto import mock_aws


@mock_aws
def test_sqs_visibility_uses_nfr12_schedule() -> None:
    c = boto3.client("sqs", region_name="us-east-1")
    u = c.create_queue(QueueName="q-nfr12")["QueueUrl"]
    c.send_message(QueueUrl=u, MessageBody='{"k":"v"}')
    msg = c.receive_message(QueueUrl=u, MaxNumberOfMessages=1, WaitTimeSeconds=0)["Messages"][0]
    tok = nfr12_visibility_timeout_seconds(2)
    c.change_message_visibility(QueueUrl=u, ReceiptHandle=msg["ReceiptHandle"], VisibilityTimeout=tok)
    assert 0 < tok <= 300
