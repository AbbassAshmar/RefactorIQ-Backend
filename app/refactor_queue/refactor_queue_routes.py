from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.auth.auth_dtos import TokenPayload
from app.core.common_dtos import ResponseMeta
from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.refactor_queue.dependencies import get_refactor_queue_service
from app.refactor_queue.refactor_queue_dtos import RefactorQueueCreate, RefactorQueueMove
from app.refactor_queue.refactor_queue_service import RefactorQueueService
from app.users.users_service import UserService
from app.utils.response import ApiResponse


router = APIRouter(prefix="/refactor-queue", tags=["Refactor Queue"])


def _current_user_id(payload: TokenPayload, user_service: UserService) -> uuid.UUID:
    user_id = uuid.UUID(payload.sub)
    user_service.get_user(user_id)
    return user_id


@router.get("")
def list_refactor_queue(
    project_id: uuid.UUID = Query(...),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: RefactorQueueService = Depends(get_refactor_queue_service),
):
    response = service.list_items(_current_user_id(payload, user_service), project_id)
    return ApiResponse.success(data=response.model_dump(), meta=ResponseMeta(project_id=project_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def add_refactor_queue_item(
    body: RefactorQueueCreate,
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: RefactorQueueService = Depends(get_refactor_queue_service),
):
    item = service.add_item(_current_user_id(payload, user_service), body.project_id, body.file_path)
    return ApiResponse.success(data={"item": item.model_dump()}, status_code=status.HTTP_201_CREATED)


@router.patch("/{item_id}")
def move_refactor_queue_item(
    item_id: uuid.UUID,
    body: RefactorQueueMove,
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: RefactorQueueService = Depends(get_refactor_queue_service),
):
    item = service.move_item(
        _current_user_id(payload, user_service), item_id, body.status, body.position
    )
    return ApiResponse.success(data={"item": item.model_dump()})


@router.delete("/{item_id}")
def delete_refactor_queue_item(
    item_id: uuid.UUID,
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: RefactorQueueService = Depends(get_refactor_queue_service),
):
    service.delete_item(_current_user_id(payload, user_service), item_id)
    return ApiResponse.success(data={"deleted_item_id": item_id})
