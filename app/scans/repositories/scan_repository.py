

from __future__ import annotations

import uuid

from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.models import Scan
from app.schemas.scan import ScanCreate, ScanProjectUserResponse, ScanResponse
from app.models.models import Project

class ScanRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _to_response(scan: Scan) -> ScanResponse:
        return ScanResponse.model_validate(scan)
    
    @staticmethod
    def _to_response_include_project_user(scan: Scan) -> ScanProjectUserResponse:
        return ScanProjectUserResponse.model_validate(scan)

    def create_scan(self, project_id: uuid.UUID) -> ScanResponse:
        scan = Scan(project_id=project_id)
        try:
            self._db.add(scan)
            self._db.commit()
            self._db.refresh(scan)
            return self._to_response(scan)
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException(
                "Failed to create scan",
                details={
                    "project_id": str(project_id),
                },
            ) from exc
        
    def get_scan_by_id(self, scan_id: uuid.UUID) -> ScanResponse:
        try:
            scan = self._db.query(Scan).filter(Scan.id == scan_id).one()
            return self._to_response(scan)
        except NoResultFound:
            raise RecordNotFoundException(
                "Scan not found",
                details={"scan_id": str(scan_id)},
            )
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to retrieve scan",
                details={
                    "scan_id": str(scan_id),
                },
            ) from exc
        

    def get_scan_by_id_include_project_user(self, scan_id: uuid.UUID) -> ScanProjectUserResponse:
        try:
            scan = (
                self._db.query(Scan)
                .filter(Scan.id == scan_id)
                .options(
                    joinedload(Scan.project).joinedload(Project.user)
                )
                .one()
            )
            
            return self._to_response_include_project_user(scan)
        except NoResultFound:
            raise RecordNotFoundException(
                "Scan not found",
                details={"scan_id": str(scan_id)},
            )
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to retrieve scan with project and user",
                details={
                    "scan_id": str(scan_id),
                },
            ) from exc