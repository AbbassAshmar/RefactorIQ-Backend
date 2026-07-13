



import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, String, Table, Text, Column, Enum, DateTime, Index, JSON, Numeric, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.enums import UserRole, ScanStatus
from app.models.base import Base, TimestampMixin, UUIDMixin
from datetime import datetime

class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)

    github_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_username: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    github_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default=text("true"))

    # foreign key 
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False
    )

    # relationships
    role: Mapped["Role"] = relationship("Role", back_populates="users")

    projects: Mapped[list["Project"]] = relationship(
        "Project",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} role_id={self.role_id}>"


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(UUIDMixin, Base):
    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    roles: Mapped[list["Role"]] = relationship(secondary=role_permissions, back_populates="permissions")

    def __repr__(self) -> str:
        return f"<Permission {self.name}>"


class Role(UUIDMixin, Base):
    __tablename__ = "roles"

    name: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=UserRole.CLIENT,
        nullable=False,
        server_default=text("'client'")
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions, back_populates="roles")
    users: Mapped[list["User"]] = relationship("User", back_populates="role")

    def __repr__(self) -> str:
        return f"<Role {self.name}>"



class Project(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)

    # Foreign key to users table
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Relationship back to User, and to Scans
    user: Mapped["User"] = relationship("User", back_populates="projects")
    scans: Mapped[list["Scan"]] = relationship(
        "Scan",
        back_populates="project",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "repo_owner",
            "repo_name",
            "branch",
            name="uq_user_repo_branch"
        ),
    )
    def __repr__(self) -> str:
        return f"<Project {self.name} owner={self.repo_owner} repo={self.repo_name} branch={self.branch} user_id={self.user_id}>"


class Scan(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "scans"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    status: Mapped[ScanStatus] = mapped_column(
        Enum(
            ScanStatus,
            name="scan_status_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ScanStatus.PENDING,
        server_default=text(f"'{ScanStatus.PENDING.value}'")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    project: Mapped["Project"] = relationship("Project", back_populates="scans")

    __table_args__ = (
        Index("ix_scans_created_at", "created_at"),
        Index("ix_scans_status_finished_at", "status", "finished_at"),
        Index("ix_scans_project_id", "project_id"),
    )

    def __repr__(self) -> str:
        return f"<Scan project_id={self.project_id} status={self.status}>"


json_payload_type = JSONB().with_variant(JSON(), "sqlite")


class ScanVisualizationRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "scan_visualization_records"

    scan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    layer: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    metrics: Mapped[dict] = mapped_column(json_payload_type, nullable=False, default=dict)
    errors: Mapped[list] = mapped_column(json_payload_type, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column("metadata", json_payload_type, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_scan_visualization_scan_layer", "scan_id", "layer"),
        Index("ix_scan_visualization_scan_file", "scan_id", "file_path"),
    )

    def __repr__(self) -> str:
        return f"<ScanVisualizationRecord scan_id={self.scan_id} layer={self.layer} file_path={self.file_path}>"


class ScanFile(UUIDMixin, Base):
    __tablename__ = "files"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    refactor_score: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    priority_band: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(json_payload_type, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", json_payload_type, nullable=False, default=dict)
    errors: Mapped[dict] = mapped_column(json_payload_type, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("scan_id", "file_path", name="uq_files_scan_file_path"),
        Index("idx_files_scan_score", "scan_id", "refactor_score"),
        Index("idx_files_scan_band", "scan_id", "priority_band"),
        Index("idx_files_metrics", "metrics", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<ScanFile scan_id={self.scan_id} file_path={self.file_path}>"


class DependencyEdge(Base):
    __tablename__ = "dependency_edges"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    )
    target_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (
        Index("idx_dep_edges_source", "scan_id", "source_file_id"),
        Index("idx_dep_edges_target", "scan_id", "target_file_id"),
    )


class CircularDependencyGroup(UUIDMixin, Base):
    __tablename__ = "circular_dependency_groups"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    size: Mapped[int] = mapped_column(Integer, nullable=False)


class CircularDependencyMember(Base):
    __tablename__ = "circular_dependency_members"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("circular_dependency_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    )


class CoChangeEdge(Base):
    __tablename__ = "co_change_edges"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id_a: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id_b: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (
        CheckConstraint("file_id_a < file_id_b", name="ck_co_change_file_order"),
    )
