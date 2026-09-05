from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models import Department, User
from app.models.enums import UserRole


def main():
    email = input("Email: ").strip().lower()
    password = getpass("Password: ")

    with SessionLocal() as db:
        existing = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if existing:
            print("User already exists.")
            return

        departments = db.execute(
            select(Department).order_by(Department.name)
        ).scalars().all()

        if not departments:
            print("No departments found.")
            return

        print("\nDepartments:")
        for department in departments:
            print(f"{department.id}: {department.name}")

        department_id = int(input("\nDepartment ID: "))

        department = db.get(Department, department_id)

        if department is None:
            print("Invalid department ID.")
            return

        user = User(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.USER,
            department_id=department.id,
        )

        db.add(user)
        db.commit()

        print(
            f"Created user: {email} "
            f"({department.name})"
        )


if __name__ == "__main__":
    main()