from app.core.db_control import control_engine, ControlBase
from app.control.models_control import Merchant, MerchantDBConnection

if __name__ == "__main__":
    ControlBase.metadata.create_all(bind=control_engine)