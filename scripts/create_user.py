from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models import User
from app.models.enums import UserRole


def main():
    email = input("Email: ").strip().lower()
    password = getpass("Password: ")

    with SessionLocal() as db:
        existing = db.execute(
            select(User).where(
                User.email == email
            )
        ).scalar_one_or_none()

        if existing:
            print("User already exists.")
            return

        user = User(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            department_id=None,
        )

        db.add(user)
        db.commit()

        print(f"Created admin user: {email}")


if __name__ == "__main__":
    main()