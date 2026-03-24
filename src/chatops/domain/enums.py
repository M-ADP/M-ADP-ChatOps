from enum import Enum


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class RequestType(str, Enum):
    INQUIRY = "inquiry"
    QUERY = "query"
    COMMAND = "command"


class RequestStatus(str, Enum):
    CREATED = "created"
    CLASSIFYING = "classifying"
    PROCESSING = "processing"
    INPUT_REQUIRED = "input_required"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPROVAL_EXPIRED = "approval_expired"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
