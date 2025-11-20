# scripts/create_demo_user.py
"""
Create a demo user in a merchant's tenant DB.
Usage:
    python scripts/create_demo_user.py <merchant_uuid> <external_user_id>
"""

import sys
import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

# Import your tenant DB loader
from app.core.tenant_db import get_tenant_sessionmaker

# Import your models
from app.stylist.models_user import UserProfile, UserEvent


async def create_demo_user(merchant_id: str, external_user_id: str):
    """
    Creates a demo user profile + some synthetic events
    inside the merchant's tenant DB.
    """

    SessionLocal = get_tenant_sessionmaker(merchant_id)

    async with SessionLocal() as session:   # type: AsyncSession
        # Check if user already exists
        existing = await session.execute(
            UserProfile.__table__.select().where(
                UserProfile.external_user_id == external_user_id
            )
        )
        row = existing.fetchone()
        if row:
            user = UserProfile(**row._asdict())
            print(f"User already exists: {user.id}")
            return user

        # Create new user profile
        user = UserProfile(
            external_user_id=external_user_id,
            name="Aisthetic Demo User",
            gender="male",
            preferred_sizes=["M"],
            body_type="athletic",

            liked_colors=["black", "navy", "beige"],
            disliked_colors=["neon green"],
            liked_fits=["slim", "regular"],
            liked_styles=["minimal", "smart casual"],
            liked_occasions=["office", "party", "wedding"],
            price_sensitivity="mid",

            meta={"profile_type": "demo"},
        )

        session.add(user)
        await session.flush()  # assigns UUID

        # Add some synthetic user events
        sample_events = [
            ("view", None, {"desc": "Viewed catalog landing"}),
            ("stylist_question", None, {"message": "Recommend something minimal"}),
            ("view", None, {"desc": "Looked at shirts"}),
            ("stylist_question", None, {"message": "Best shirt for office?"}),
        ]

        for event_type, pid, ctx in sample_events:
            evt = UserEvent(
                user_id=user.id,
                event_type=event_type,
                product_id=pid,
                context=ctx,
            )
            session.add(evt)

        await session.commit()
        print(f"\n🎉 Demo user created successfully.\nUUID: {user.id}\n")

        return user


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/create_demo_user.py <merchant_uuid> <external_user_id>")
        sys.exit(1)

    merchant_uuid = sys.argv[1]
    external_user_id = sys.argv[2]

    # Validate UUID format
    try:
        UUID(merchant_uuid)
    except Exception:
        print("Invalid merchant UUID")
        sys.exit(1)

    asyncio.run(create_demo_user(merchant_uuid, external_user_id))