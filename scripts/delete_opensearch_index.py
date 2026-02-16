"""
Delete the OpenSearch index for a merchant.

Usage:
    python -m scripts.delete_opensearch_index --merchant-id <uuid>
"""

import argparse
from uuid import UUID

from app.catalog.opensearch_client import get_catalog_index_name, get_opensearch_client


def delete_index(merchant_id: str):
    try:
        UUID(merchant_id)
    except ValueError:
        raise SystemExit(f"Invalid merchant UUID: {merchant_id}")

    client = get_opensearch_client()
    index_name = get_catalog_index_name(merchant_id)

    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)
        print(f"Deleted index: {index_name}")
    else:
        print(f"Index does not exist: {index_name}")


def main():
    parser = argparse.ArgumentParser(description="Delete OpenSearch index for a merchant")
    parser.add_argument("--merchant-id", required=True, help="Merchant UUID")
    args = parser.parse_args()
    delete_index(args.merchant_id)


if __name__ == "__main__":
    main()
