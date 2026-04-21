"""Seed helpers for roles, permissions, and admin users.

Exported methods:
- ``create_roles_permissions``
- ``create_admin``
"""

from __future__ import annotations

import os
import sys

from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.enums import UserRole  # noqa: E402
from app.core.security import hash_password, verify_password  # noqa: E402
from app.models import Permission, Role, User  # noqa: E402

DEFAULT_PERMISSIONS = [
    {"name": "manage-users", "description": "Create, update, delete users"},
    {"name": "manage-scans", "description": "Create, view, delete scans"},
]

ROLE_PERMISSION_MAP: dict[UserRole, list[str]] = {
    UserRole.ADMIN: ["manage-users", "manage-scans"],
    UserRole.CLIENT: [],
}

ROLE_DESCRIPTIONS: dict[UserRole, str] = {
    UserRole.ADMIN: "Platform administrator",
    UserRole.CLIENT: "Default client role",
}

__all__ = ["create_roles_permissions", "create_admin"]


def create_roles_permissions(db: Session | None = None) -> None:
    """Create/update default roles, permissions, and role-permission links."""
    owns_session = db is None
    session = db or SessionLocal()

    try:
        permissions_by_name: dict[str, Permission] = {}
        for perm_data in DEFAULT_PERMISSIONS:
            perm = (
                session.query(Permission)
                .filter(Permission.name == perm_data["name"])
                .first()
            )

            if not perm:
                perm = Permission(**perm_data)
                session.add(perm)
                print(f"  + Permission '{perm_data['name']}'")
            else:
                expected_description = perm_data.get("description")
                if expected_description and perm.description != expected_description:
                    perm.description = expected_description
                    print(f"  ~ Permission '{perm_data['name']}' description updated")
                else:
                    print(f"  = Permission '{perm_data['name']}' already exists")

            permissions_by_name[perm_data["name"]] = perm

        session.flush()

        roles_by_enum: dict[UserRole, Role] = {}
        for role_enum in ROLE_PERMISSION_MAP.keys():
            role_name = role_enum.value
            role = session.query(Role).filter(Role.name == role_name).first()

            if not role:
                role = Role(name=role_name, description=ROLE_DESCRIPTIONS.get(role_enum))
                session.add(role)
                print(f"  + Role '{role_name}'")
            else:
                print(f"  = Role '{role_name}' already exists")

            roles_by_enum[role_enum] = role

        session.flush()

        for role_enum, permission_names in ROLE_PERMISSION_MAP.items():
            role = roles_by_enum[role_enum]
            existing_permission_names = {p.name for p in role.permissions}

            for perm_name in permission_names:
                perm = permissions_by_name.get(perm_name)
                if not perm:
                    print(
                        f"  ! Permission '{perm_name}' not found while seeding role '{role_enum.value}'"
                    )
                    continue

                if perm_name not in existing_permission_names:
                    role.permissions.append(perm)
                    print(f"  + {role_enum.value} -> {perm_name}")
                else:
                    print(f"  = {role_enum.value} -> {perm_name} already exists")

        session.commit()
        print("\nSeeded roles and permissions successfully.")
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def create_admin(
    db: Session | None = None,
) -> None:
    """Create an admin user linked to the admin role.

    Required environment variables:
    - ``ADMIN_EMAIL``
    - ``ADMIN_USERNAME``
    - ``ADMIN_PASSWORD``

    Requires roles to be seeded first via ``create_roles_permissions``.
    """
    email = settings.ADMIN_EMAIL.strip()
    username = settings.ADMIN_USERNAME.strip()
    password = settings.ADMIN_PASSWORD

    if not email:
        raise ValueError("ADMIN_EMAIL is required.")
    if not username:
        raise ValueError("ADMIN_USERNAME is required.")
    if len(password) < 8:
        raise ValueError("ADMIN_PASSWORD must be at least 8 characters.")

    owns_session = db is None
    session = db or SessionLocal()

    try:
        admin_role = session.query(Role).filter(Role.name == UserRole.ADMIN.value).first()
        if not admin_role:
            raise RuntimeError(
                "Admin role is missing. Call create_roles_permissions() before create_admin()."
            )

        other_admin = (
            session.query(User)
            .filter(User.role_id == admin_role.id, User.email != email)
            .first()
        )
        if other_admin:
            raise RuntimeError(
                "Another admin user already exists. This seeder supports exactly one admin account."
            )

        existing = session.query(User).filter(User.email == email).first()
        if existing:
            changed = False

            if existing.role_id != admin_role.id:
                existing.role_id = admin_role.id
                changed = True

            if existing.username != username:
                existing.username = username
                changed = True

            if not existing.password or not verify_password(password, existing.password):
                existing.password = hash_password(password)
                changed = True

            if not existing.is_active:
                existing.is_active = True
                changed = True

            if changed:
                session.commit()
                print(f"  ~ Admin '{email}' updated from environment")
            else:
                print(f"  = Admin '{email}' already exists")
            return

        admin = User(
            email=email,
            username=username,
            password=hash_password(password),
            role_id=admin_role.id,
            is_active=True,
        )
        session.add(admin)
        session.commit()
        print(f"  + Admin '{email}' created")
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


if __name__ == "__main__":
    create_roles_permissions()
    create_admin()
