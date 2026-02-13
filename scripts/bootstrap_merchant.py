# scripts/bootstrap_merchant.py
from app.core.db_control import ControlSessionLocal
from app.control.models_control import Merchant, MerchantDBConnection, MerchantStatus

def main():
    session = ControlSessionLocal()
    try:
        m = Merchant(
            name="Demo Merchant",
            slug="demo-merchant",
            status=MerchantStatus.active,
            plan="starter"
        )
        session.add(m)
        session.flush()

        conn = MerchantDBConnection(
            merchant_id=m.id,
            db_type="postgres",
            db_host="db",
            db_port=5432,
            db_name="aisthetic_merchant_1",
            db_user="airbender",
            db_password="password",
        )
        session.add(conn)
        session.commit()
        print("Merchant ID:", m.id)
    finally:
        session.close()

if __name__ == "__main__":
    main()