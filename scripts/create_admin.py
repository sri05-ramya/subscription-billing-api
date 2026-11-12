"""Create a staff user from the terminal.

Usage:
    python -m scripts.create_admin
"""

from getpass import getpass

from sqlalchemy import select

from app import models  # noqa: F401  (loads all tables)
from app.database import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password


def main() -> None:
    Base.metadata.create_all(bind=engine)

    email = input("Email: ").strip().lower()
    full_name = input("Full name: ").strip()
    role = input("Role (admin/viewer) [admin]: ").strip().lower() or "admin"
    if role not in ("admin", "viewer"):
        print("Role must be admin or viewer.")
        return

    password = getpass("Password (min 8 characters, hidden while typing): ")
    if len(password) < 8:
        print("Password is too short.")
        return
    if password != getpass("Repeat password: "):
        print("Passwords do not match.")
        return

    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == email)):
            print(f"A user with email {email} already exists.")
            return
        db.add(User(email=email, full_name=full_name, role=role, hashed_password=hash_password(password)))
        db.commit()
        print(f"Created {role} user: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()