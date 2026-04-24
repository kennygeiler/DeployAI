"""Service-level errors the HTTP layer maps to safe client responses."""


class AccountProvisionError(Exception):
    """Base for account provisioning failures (generic 5xx in the API)."""


class CanonicalBaselineNotEmptyError(AccountProvisionError):
    """A brand-new tenant_id unexpectedly had canonical_memory rows."""


class UserRecordIncompleteError(AccountProvisionError):
    """Inconsistent ORM state after commit (e.g. missing expected timestamps)."""


class TenantDekModeNotAvailableError(AccountProvisionError):
    """The configured ``tenant_dek_mode`` (e.g. ``aws_kms``) is not implemented."""


class NotFoundError(Exception):
    """Generic missing row (map to 404 in HTTP layer)."""
