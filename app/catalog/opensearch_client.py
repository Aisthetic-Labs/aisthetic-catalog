from opensearchpy import OpenSearch
from app.core.config import settings


def get_opensearch_client() -> OpenSearch:
    host = settings.OPENSEARCH_HOST

    if settings.OPENSEARCH_USER and settings.OPENSEARCH_PASSWORD:
        auth = (settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD)
    else:
        auth = None

    client = OpenSearch(
        hosts=[host],
        http_auth=auth,
        use_ssl=host.startswith("https"),
        verify_certs=not host.startswith("http://"),
    )
    return client


def get_catalog_index_name(merchant_id: str) -> str:
    # per-merchant index
    return f"catalog-{merchant_id}"