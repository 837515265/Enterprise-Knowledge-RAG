from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorCode:
    code: str
    retryable: bool
    stage: str


PARSE_UNSUPPORTED_PROFILE = ErrorCode("PARSE_001", False, "validate")
PARSE_OCR_FAILED = ErrorCode("PARSE_002", True, "ocr")
PARSE_SAVE_FAILED = ErrorCode("PARSE_003", True, "saving")
PARSE_TASK_NOT_FOUND = ErrorCode("PARSE_004", False, "task_lookup")
PARSE_FAILED = ErrorCode("PARSE_999", True, "parse")

INDEX_WRITE_FAILED = ErrorCode("INDEX_001", True, "index_write")
INDEX_LOCKED = ErrorCode("INDEX_002", True, "lock")
INDEX_INVALID_OPERATION = ErrorCode("INDEX_003", False, "validate")
INDEX_TASK_NOT_FOUND = ErrorCode("INDEX_004", False, "task_lookup")
INDEX_SWITCH_FAILED = ErrorCode("INDEX_005", True, "switch_pointer")
INDEX_FAILED = ErrorCode("INDEX_999", True, "index")

RETRIEVE_FAILED = ErrorCode("RETRIEVE_001", True, "retrieve")
REVIEW_FAILED = ErrorCode("REVIEW_001", True, "review")
MODEL_FAILED = ErrorCode("MODEL_001", True, "model")
TABLE_RETRIEVE_FAILED = ErrorCode("TABLE_001", True, "table_retrieve")
RATE_LIMITED = ErrorCode("RATE_001", True, "rate_limit")


def detail(code: ErrorCode, message: str) -> dict[str, object]:
    return {
        "error_code": code.code,
        "message": message,
        "retryable": code.retryable,
        "stage": code.stage,
    }
