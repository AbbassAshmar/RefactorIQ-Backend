"""Script to create an initial admin user interactively."""

import os
import sys
from getpass import getpass

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.user import User  # noqa: E402
from app.core.enums import UserRole  # noqa: E402


def create_admin() -> None:
    email = input("Admin email: ").strip()
    if not email:
        print("Email is required.")
        sys.exit(1)

    full_name = input("Full name: ").strip()
    if not full_name:
        print("Full name is required.")
        sys.exit(1)

    password = getpass("Password: ")
    confirm = getpass("Confirm password: ")

    if password != confirm:
        print("Passwords do not match!")
        sys.exit(1)

    if len(password) < 8:
        print("Password must be at least 8 characters!")
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"User with email '{email}' already exists!")
            sys.exit(1)

        admin = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print(f"✔ Admin user '{email}' created successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
