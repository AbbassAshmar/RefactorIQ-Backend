"""Seed default permissions and role-permission mappings."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal  # noqa: E402
from app.core.enums import UserRole  # noqa: E402
from app.models.permission import Permission, RolePermission  # noqa: E402

# Define the default permissions
DEFAULT_PERMISSIONS = [
    {"name": "manage-users", "description": "Create, update, delete users"},
    {"name": "manage-scans", "description": "Create, view, delete scans"},
]

# Map roles to their permissions
ROLE_PERMISSION_MAP: dict[UserRole, list[str]] = {
    UserRole.ADMIN: ["manage-users", "manage-scans"],
    UserRole.CLIENT: [],
}


def seed() -> None:
    db = SessionLocal()
    try:
        # Upsert permissions
        for perm_data in DEFAULT_PERMISSIONS:
            perm = (
                db.query(Permission)
                .filter(Permission.name == perm_data["name"])
                .first()
            )
            if not perm:
                perm = Permission(**perm_data)
                db.add(perm)
                print(f"  + Permission '{perm_data['name']}'")
            else:
                print(f"  = Permission '{perm_data['name']}' already exists")

        db.flush()

        # Upsert role-permission mappings
        for role, perm_names in ROLE_PERMISSION_MAP.items():
            for name in perm_names:
                perm = (
                    db.query(Permission)
                    .filter(Permission.name == name)
                    .first()
                )
                if not perm:
                    continue

                exists = (
                    db.query(RolePermission)
                    .filter(
                        RolePermission.role == role,
                        RolePermission.permission_id == perm.id,
                    )
                    .first()
                )
                if not exists:
                    db.add(RolePermission(role=role, permission_id=perm.id))
                    print(f"  + {role.value} → {name}")
                else:
                    print(f"  = {role.value} → {name} already exists")

        db.commit()
        print("\n✔ Seed completed.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
