# scripts/bootstrap_merchant.py
from app.core.db_control import ControlSessionLocal
from app.control.models_control import Merchant, MerchantDBConnection, MerchantStatus

def main():
    session = ControlSessionLocal()
    try:
        # Try to find existing merchant by slug first
        m = session.query(Merchant).filter(Merchant.slug == "demo-merchant").first()
        if not m:
            m = Merchant(
                name="Demo Merchant",
                slug="demo-merchant",
                status=MerchantStatus.active,
                plan="starter"
            )
            session.add(m)
            session.flush()

        # Update or create connection
        conn = session.query(MerchantDBConnection).filter(MerchantDBConnection.merchant_id == m.id).first()
        if not conn:
            conn = MerchantDBConnection(merchant_id=m.id)
            session.add(conn)
        
        conn.db_type = "postgres"
        conn.db_host = "db"
        conn.db_port = 5432
        conn.db_name = "aisthetic_merchant_1"
        conn.db_user = "airbender"
        conn.db_password = "password"
        
        session.commit()
        print("Merchant ID:", m.id)
        print("Merchant DB connection updated to 'db:5432'")
    finally:
        session.close()

if __name__ == "__main__":
    main()