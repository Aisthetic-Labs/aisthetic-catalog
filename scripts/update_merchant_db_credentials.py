"""
Update DB username/password for a merchant using merchant UUID.

Usage:
    # With empty password:
    python -m scripts.update_merchant_db_credentials \
        --merchant-id <uuid> \
        --db-user newuser \
        --db-password ""

    # Or just press ENTER when prompted:
    python -m scripts.update_merchant_db_credentials \
        --merchant-id <uuid> \
        --db-user newuser
"""

import argparse
import getpass
from uuid import UUID

from app.core.db_control import ControlSessionLocal
from app.control.models_control import Merchant, MerchantDBConnection


def update_db_credentials(merchant_id: str, db_user: str, db_password: str):
    session = ControlSessionLocal()
    try:
        # Validate UUID format
        try:
            mid = UUID(merchant_id)
        except ValueError:
            raise SystemExit(f"❌ Invalid merchant UUID: {merchant_id}")

        merchant = (
            session.query(Merchant)
            .filter(Merchant.id == mid)
            .one_or_none()
        )
        if not merchant:
            raise SystemExit(f"❌ No merchant found with ID: {merchant_id}")

        conn = (
            session.query(MerchantDBConnection)
            .filter(MerchantDBConnection.merchant_id == merchant.id)
            .one_or_none()
        )
        if not conn:
            raise SystemExit(
                f"❌ No MerchantDBConnection entry found for merchant {merchant_id}"
            )

        old_user = conn.db_user
        old_pass = conn.db_password

        # Update fields
        conn.db_user = db_user
        conn.db_password = db_password   # may be empty string

        session.add(conn)
        session.commit()

        print("✅ Merchant DB credentials updated.")
        print(f"  Merchant ID   : {merchant_id}")
        print(f"  Old DB User   : {old_user}")
        print(f"  New DB User   : {db_user}")
        print(f"  Old Password  : {'<empty>' if old_pass == '' else '***'}")
        print(f"  New Password  : {'<empty>' if db_password == '' else '***'}")

    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Update merchant DB username/password (allows empty password)"
    )
    parser.add_argument("--merchant-id", required=True, help="Merchant UUID")
    parser.add_argument("--db-user", required=True, help="New DB username")
    parser.add_argument(
        "--db-password",
        help="New DB password. If omitted, you will be prompted (ENTER = empty).",
    )

    args = parser.parse_args()

    if args.db_password is not None:
        # Password was passed explicitly (even empty string)
        db_password = args.db_password
    else:
        # Prompt for password (ENTER = empty)
        db_password = getpass.getpass(
            "Enter new DB password (ENTER for empty): "
        )

    # db_password may legitimately be empty
    update_db_credentials(
        merchant_id=args.merchant_id,
        db_user=args.db_user,
        db_password=db_password,
    )


if __name__ == "__main__":
    main()