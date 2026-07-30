import re

WORKFLOW_ID_PATTERN = r"^wf_[0-9a-f]{12}$"
VERSION_ID_PATTERN = r"^v[0-9a-f]{8}$"

_WORKFLOW_ID_RE = re.compile(WORKFLOW_ID_PATTERN)
_VERSION_ID_RE = re.compile(VERSION_ID_PATTERN)


def require_workflow_id(value: str) -> str:
    """Reject untrusted identifiers before they can participate in local paths."""

    if _WORKFLOW_ID_RE.fullmatch(value) is None:
        raise ValueError("workflow_id must match wf_<12 lowercase hex chars>")
    return value


def require_version_id(value: str) -> str:
    """Reject untrusted version identifiers before filesystem lookup."""

    if _VERSION_ID_RE.fullmatch(value) is None:
        raise ValueError("version_id must match v<8 lowercase hex chars>")
    return value
