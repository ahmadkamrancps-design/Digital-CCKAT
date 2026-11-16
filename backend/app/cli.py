"""Trusted local provisioning; no public registration or privilege escalation endpoint."""

import argparse
import getpass
import sys

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import load_settings
from app.db.session import create_db_engine, create_session_factory
from app.models import Candidate, Role, User
from app.services.staff_login_service import set_staff_password


def provision_password(email: str, from_stdin: bool) -> None:
    if from_stdin:
        # A bounded single line permits secure pipes without exposing shell arguments.
        password = sys.stdin.readline(1026).removesuffix("\n")
    else:
        password = getpass.getpass("New staff password (15–128 characters): ")
        if password != getpass.getpass("Confirm new password: "):
            raise ValueError("Passwords did not match.")
    engine = create_db_engine(load_settings())
    try:
        with create_session_factory(engine)() as db:
            set_staff_password(db, email, password)
    finally:
        engine.dispose()


class Registration(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr | None = None
    name: str = Field(min_length=1, max_length=200)
    roll_number: str | None = Field(default=None, min_length=1, max_length=64)
    google_subject: str | None = Field(default=None, min_length=1, max_length=255)
    father_name: str | None = Field(default=None, min_length=1, max_length=200)


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a preapproved CCK account")
    subcommands = parser.add_subparsers(dest="command", required=True)
    candidate = subcommands.add_parser("register-candidate", help="Approve a candidate account")
    staff = subcommands.add_parser("register-staff", help="Approve a staff account")
    password_command = subcommands.add_parser(
        "set-staff-password", help="Set/reset an approved staff password and revoke old sessions"
    )
    password_command.add_argument("--email", required=True)
    password_command.add_argument("--password-stdin", action="store_true")
    for command in (candidate, staff):
        command.add_argument("--email", required=command is staff)
        command.add_argument("--name", required=True)
        command.add_argument(
            "--google-subject", help="Independently verified Google sub, if available"
        )
    candidate.add_argument("--roll-number", required=True)
    candidate.add_argument("--father-name", required=True)
    staff.add_argument("--role", choices=["ADMIN", "PROCTOR", "EXAMINER"], required=True)
    args = parser.parse_args()
    if args.command == "set-staff-password":
        try:
            provision_password(args.email, args.password_stdin)
        except ValueError as exc:
            parser.exit(2, str(exc) + "\n")
        except SQLAlchemyError:
            parser.exit(2, "Unable to update password. Check configuration and migrations.\n")
        print("Staff password updated. Existing sessions have been revoked.")
        return
    try:
        data = Registration(
            email=args.email.strip().lower() if args.email else None,
            name=args.name.strip(),
            roll_number=getattr(args, "roll_number", None),
            google_subject=args.google_subject,
            father_name=getattr(args, "father_name", None),
        )
    except ValidationError:
        parser.exit(
            2, "Invalid registration fields. Check email, name, roll number, and subject.\n"
        )
    engine = create_db_engine(load_settings())
    try:
        with create_session_factory(engine)() as db:
            user = User(
                email=str(data.email).lower() if data.email else None,
                display_name=data.name,
                google_subject=data.google_subject,
                role=Role.CANDIDATE if args.command == "register-candidate" else Role(args.role),
            )
            db.add(user)
            db.flush()
            if args.command == "register-candidate":
                assert data.roll_number is not None
                db.add(
                    Candidate(
                        user_id=user.id,
                        full_name=data.name,
                        roll_number=data.roll_number.strip(),
                        father_name=data.father_name,
                    )
                )
            db.commit()
            print(f"Approved {user.role.value} account created: {user.id}")
    except IntegrityError:
        parser.exit(2, "Registration conflicts with an existing email, identity, or roll number.\n")
    except SQLAlchemyError:
        parser.exit(
            2, "Database unavailable or schema missing. Check configuration and migrations.\n"
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
