"""
Create a UserProfile (+ empty UserPreferences) in a tenant DB for dev testing.

Usage:
    python -m scripts.create_user <merchant_id> <external_user_id> [--name NAME] [--gender GENDER]

Examples:
    python -m scripts.create_user 550e8400-e29b-41d4-a716-446655440000 user_42
    python -m scripts.create_user 550e8400-e29b-41d4-a716-446655440000 user_42 --name "Arjun" --gender male --dob 1996-04-15
"""

import argparse
import asyncio
from datetime import date

from app.core.tenant_db import get_tenant_sessionmaker
from app.stylist.models_user import UserProfile, UserPreferences


async def create_user(
    merchant_id: str,
    external_user_id: str,
    name: str | None = None,
    gender: str | None = None,
    dob: str | None = None,
):
    SessionLocal = get_tenant_sessionmaker(merchant_id)
    async with SessionLocal() as session:
        profile = UserProfile(
            external_user_id=external_user_id,
            name=name,
            gender=gender,
            dob=date.fromisoformat(dob) if dob else None,
        )
        session.add(profile)
        await session.flush()

        prefs = UserPreferences(user_id=profile.id, preferences={})
        session.add(prefs)

        await session.commit()

        print(f"external_user_id: {external_user_id}")
        print(f"profile_id:       {profile.id}")

        return str(profile.id)


def main():
    parser = argparse.ArgumentParser(description="Create a test UserProfile in a tenant DB")
    parser.add_argument("merchant_id", help="Merchant UUID")
    parser.add_argument("external_user_id", help="External user ID")
    parser.add_argument("--name", default=None, help="User's name")
    parser.add_argument("--gender", default=None, help="Gender (male/female/non-binary)")
    parser.add_argument("--dob", default=None, help="Date of birth (YYYY-MM-DD)")
    args = parser.parse_args()

    asyncio.run(create_user(
        merchant_id=args.merchant_id,
        external_user_id=args.external_user_id,
        name=args.name,
        gender=args.gender,
        dob=args.dob,
    ))


if __name__ == "__main__":
    main()
