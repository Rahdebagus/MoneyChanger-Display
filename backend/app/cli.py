"""Management commands.

    python -m app.cli create-admin
    python -m app.cli create-admin --username admin --from-env
    python -m app.cli reset-password --username admin
    python -m app.cli list-users
    python -m app.cli check

No command ever prints a secret back, and there is no default password baked
into the source: the password is typed interactively or supplied through
PAM_ADMIN_PASSWORD for an unattended install.
"""

import argparse
import getpass
import os
import sys
from typing import Optional

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Branch, User, UserBranch, UserRole
from app.services import audit

MIN_PASSWORD_LENGTH = 8


def _read_password(confirm: bool = True) -> str:
    """Interactive password entry, or PAM_ADMIN_PASSWORD for automation."""
    from_env = os.environ.get("PAM_ADMIN_PASSWORD")
    if from_env:
        if len(from_env) < MIN_PASSWORD_LENGTH:
            raise SystemExit(
                f"PAM_ADMIN_PASSWORD terlalu pendek (minimal {MIN_PASSWORD_LENGTH} karakter)."
            )
        return from_env

    if not sys.stdin.isatty():
        raise SystemExit(
            "Tidak ada terminal interaktif. Set PAM_ADMIN_PASSWORD lalu jalankan ulang."
        )

    while True:
        password = getpass.getpass("Password admin baru: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Minimal {MIN_PASSWORD_LENGTH} karakter. Coba lagi.")
            continue
        if confirm:
            again = getpass.getpass("Ulangi password: ")
            if password != again:
                print("Password tidak sama. Coba lagi.")
                continue
        return password


def cmd_create_admin(args: argparse.Namespace) -> int:
    username = (args.username or input("Username admin: ")).strip().lower()
    if not username:
        raise SystemExit("Username tidak boleh kosong.")

    db = SessionLocal()
    try:
        existing = db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()

        if existing is not None:
            if not args.force:
                print(f"User '{username}' sudah ada. Gunakan --force untuk mengubahnya.")
                return 1
            password = _read_password()
            existing.password_hash = hash_password(password)
            existing.role = UserRole.ADMIN.value
            existing.is_active = True
            existing.token_version += 1
            audit.record(
                db,
                action="user.bootstrap_updated",
                actor_label="cli",
                target_type="user",
                target_id=existing.id,
            )
            db.commit()
            print(f"User '{username}' diperbarui menjadi admin aktif.")
            return 0

        password = _read_password()
        user = User(
            username=username,
            full_name=args.full_name,
            password_hash=hash_password(password),
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        db.add(user)
        db.flush()

        audit.record(
            db,
            action="user.bootstrap_created",
            actor_label="cli",
            target_type="user",
            target_id=user.id,
        )
        db.commit()
        print(f"Admin '{username}' dibuat. Silakan login di aplikasi.")
        return 0
    finally:
        db.close()


def cmd_reset_password(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        user = db.execute(
            select(User).where(User.username == args.username.strip().lower())
        ).scalar_one_or_none()
        if user is None:
            print(f"User '{args.username}' tidak ditemukan.")
            return 1

        user.password_hash = hash_password(_read_password())
        # Every existing session for this account stops working immediately.
        user.token_version += 1
        audit.record(
            db,
            action="user.password_reset_cli",
            actor_label="cli",
            target_type="user",
            target_id=user.id,
        )
        db.commit()
        print(f"Password '{user.username}' diperbarui. Sesi lama otomatis berakhir.")
        return 0
    finally:
        db.close()


def cmd_list_users(_args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        users = list(db.execute(select(User).order_by(User.username)).scalars())
        if not users:
            print("Belum ada user. Jalankan: python -m app.cli create-admin")
            return 0

        print(f"{'ID':<5}{'USERNAME':<20}{'ROLE':<8}{'AKTIF':<7}CABANG")
        for user in users:
            branches = list(
                db.execute(
                    select(Branch.name)
                    .join(UserBranch, UserBranch.branch_id == Branch.id)
                    .where(UserBranch.user_id == user.id)
                ).scalars()
            )
            print(
                f"{user.id:<5}{user.username:<20}{user.role:<8}"
                f"{'ya' if user.is_active else 'tidak':<7}"
                f"{', '.join(branches) if branches else '-'}"
            )
        return 0
    finally:
        db.close()


def cmd_create_branch(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        existing = db.execute(
            select(Branch).where(Branch.name == args.name)
        ).scalar_one_or_none()
        if existing is not None:
            print(f"Cabang '{args.name}' sudah ada (id={existing.id}).")
            return 0

        branch = Branch(name=args.name, timezone=args.timezone, is_active=True)
        db.add(branch)
        db.commit()
        print(f"Cabang '{branch.name}' dibuat (id={branch.id}, tz={branch.timezone}).")
        return 0
    finally:
        db.close()


def cmd_check(_args: argparse.Namespace) -> int:
    """Verify configuration and connectivity without starting the server."""
    from app.core.config import get_settings

    settings = get_settings()
    print(f"Environment  : {settings.environment}")
    print(f"Assets dir   : {settings.assets_path}")
    print(f"Storage dir  : {settings.storage_path}")

    # Never print the DSN: it can carry a password.
    try:
        from sqlalchemy import text

        from app.db.session import engine

        with engine.connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
            mode = conn.execute(text("SELECT @@session.sql_mode")).scalar()
        print(f"Database     : terhubung ({version})")
        print(f"sql_mode     : {mode}")
    except Exception as exc:
        print(f"Database     : GAGAL - {type(exc).__name__}: {exc}")
        return 1

    missing = [
        str(path)
        for path in (
            settings.assets_path / "pam_bg.png",
            settings.assets_path / "pam_logo.png",
        )
        if not path.exists()
    ]
    if missing:
        print("Aset hilang  : " + ", ".join(missing))
        return 1

    print("Aset         : lengkap")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-admin", help="Buat atau perbarui akun admin")
    create.add_argument("--username")
    create.add_argument("--full-name", dest="full_name")
    create.add_argument(
        "--force", action="store_true", help="Perbarui user yang sudah ada"
    )
    create.set_defaults(func=cmd_create_admin)

    reset = sub.add_parser("reset-password", help="Ganti password seorang user")
    reset.add_argument("--username", required=True)
    reset.set_defaults(func=cmd_reset_password)

    listing = sub.add_parser("list-users", help="Tampilkan daftar user")
    listing.set_defaults(func=cmd_list_users)

    branch = sub.add_parser("create-branch", help="Buat cabang")
    branch.add_argument("--name", required=True)
    branch.add_argument("--timezone", default="Asia/Makassar")
    branch.set_defaults(func=cmd_create_branch)

    check = sub.add_parser("check", help="Cek konfigurasi, database dan aset")
    check.set_defaults(func=cmd_check)

    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
