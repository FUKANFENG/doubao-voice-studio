"""统一错误响应模型。
所有 HTTP 错误都返回 {code, message}，前端用 code 区分。
"""
from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def http_error(code: str, message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


# 常用错误码
ERR_INVALID_TEXT = "invalid_text"
ERR_INVALID_PARAM = "invalid_param"
ERR_UPSTREAM_FAILED = "upstream_failed"
ERR_AUTH_EXPIRED = "auth_expired"
ERR_RATE_LIMITED = "rate_limited"
ERR_INTERNAL = "internal"
