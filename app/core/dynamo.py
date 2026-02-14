from __future__ import annotations

import aioboto3

from app.core.config import settings

_session: aioboto3.Session | None = None


def get_dynamo_session() -> aioboto3.Session:
    global _session
    if _session is None:
        kwargs: dict = {}
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        kwargs["region_name"] = settings.AWS_REGION
        _session = aioboto3.Session(**kwargs)
    return _session


def _resource_kwargs() -> dict:
    kwargs: dict = {}
    if settings.AWS_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL
    return kwargs


def dynamo_resource():
    """Return an async context-manager for a DynamoDB resource."""
    return get_dynamo_session().resource("dynamodb", **_resource_kwargs())
