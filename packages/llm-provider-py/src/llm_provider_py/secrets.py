"""Resolve API keys from env vars or AWS Secrets Manager (optional boto3)."""

from __future__ import annotations

import os


def _aws_region() -> str:
    return (os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1").strip()


def get_secret_string(arn: str) -> str:
    try:
        import boto3
    except ImportError as e:
        msg = "boto3 is required to read DEPLOYAI_*_SECRET_ARN; `uv pip install boto3` or set the env API key"
        raise OSError(msg) from e
    client = boto3.client("secretsmanager", region_name=_aws_region())
    resp = client.get_secret_value(SecretId=arn)
    sec = resp.get("SecretString")
    if not isinstance(sec, str) or not sec.strip():
        msg = f"Secret {arn} has no SecretString"
        raise OSError(msg)
    return sec.strip()


def resolve_from_env_or_arn(*, key_env: str, arn_env: str) -> str:
    """Prefer ``key_env``; if empty, load plain secret string from ``arn_env`` (AWS Secrets Manager)."""
    direct = (os.environ.get(key_env) or "").strip()
    if direct:
        return direct
    arn = (os.environ.get(arn_env) or "").strip()
    if not arn:
        return ""
    return get_secret_string(arn)


def resolve_anthropic_api_key() -> str:
    return resolve_from_env_or_arn(
        key_env="ANTHROPIC_API_KEY",
        arn_env="DEPLOYAI_ANTHROPIC_SECRET_ARN",
    )


def resolve_openai_api_key() -> str:
    return resolve_from_env_or_arn(
        key_env="OPENAI_API_KEY",
        arn_env="DEPLOYAI_OPENAI_SECRET_ARN",
    )
