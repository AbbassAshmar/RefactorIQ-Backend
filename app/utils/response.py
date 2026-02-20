# app/utils/responses.py
from typing import Any, Optional
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.schemas.response import (
    SuccessResponse,
    ErrorResponse,
    ErrorDetail,
    ResponseMeta,
    PaginationMeta
)


class ApiResponse:
    @staticmethod
    def success(
        data: Any,
        status_code: int = 200,
        meta: Optional[ResponseMeta] = None
    ) -> JSONResponse:
        
        response = SuccessResponse(
            data=data,
            error=None,
            meta=meta or ResponseMeta()
        )
        return JSONResponse(
            content=jsonable_encoder(response.model_dump(exclude_none=True)),
            status_code=status_code
        )
    
    @staticmethod
    def error(
        code: str,
        message: str,
        status_code: int,
        details: Optional[dict] = None,
        meta: Optional[ResponseMeta] = None
    ) -> JSONResponse:

        response = ErrorResponse(
            data=None,
            error=ErrorDetail(
                code=code,
                message=message,
                details=details
            ),
            meta=meta or ResponseMeta()
        )
        return JSONResponse(
            content=jsonable_encoder(response.model_dump(exclude_none=True)),
            status_code=status_code
        )