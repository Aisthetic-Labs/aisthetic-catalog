import asyncio
import argparse
import json
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.tenant_db import get_tenant_sessionmaker
from app.stylist.persona import build_persona_context
from app.logger import logger

async def print_user_persona(merchant_id: str, external_user_id: str):
    """
    Fetches and prints the user persona JSON for a given merchant and user.
    Useful for debugging and optimizing the fashion persona independently.
    """
    try:
        SessionLocal = get_tenant_sessionmaker(merchant_id)
        async with SessionLocal() as session:
            print(f"--- Fetching Persona for Merchant: {merchant_id}, User: {external_user_id} ---")
            persona_json_str = await build_persona_context(session, external_user_id)
            
            # Parse and pretty print
            persona_data = json.loads(persona_json_str)
            print(json.dumps(persona_data, indent=2))
            print("--- End of Persona ---")
            
    except Exception as e:
        print(f"Error fetching persona: {e}")
        logger.exception("Failed to fetch persona in debug script")

def main():
    parser = argparse.ArgumentParser(description="Print user fashion persona for debugging.")
    parser.add_argument("--merchant-id", required=True, help="The UUID of the merchant")
    parser.add_argument("--user-id", required=True, help="The external user ID")
    
    args = parser.parse_args()
    
    asyncio.run(print_user_persona(args.merchant_id, args.user_id))

if __name__ == "__main__":
    main()
