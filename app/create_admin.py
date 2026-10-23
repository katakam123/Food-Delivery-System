import os
from getpass import getpass

from sqlalchemy.exc import IntegrityError

from app.auth.security import hash_password
from app.database import SessionLocal
from app.models.user import User


def main():
    email = input("Admin email: ").strip().lower()
    password = getpass("Admin password (minimum 8 characters): ")

    if len(password) < 8 or len(password) > 128:
        print("Password must contain 8 to 128 characters.")
        return

    db = SessionLocal()

    try:
        existing = db.query(User).filter(User.email == email).first()

        if existing:
            print("An account with this email already exists.")
            return

        admin = User(
            email=email,
            password_hash=hash_password(password),
            role="Admin",
            is_active=True,
            is_approved=True,
        )

        db.add(admin)
        db.commit()
        print("Admin account created successfully.")

    except IntegrityError:
        db.rollback()
        print("Could not create Admin; the email may already exist.")

    finally:
        db.close()


if __name__ == "__main__":
    main()