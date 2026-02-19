from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    CONTROL_DB_DSN: str = Field(
        default="postgresql+psycopg2://airbender@localhost:5432/aisthetic_control"
    )

    # OpenSearch
    OPENSEARCH_HOST: str = Field(default="http://localhost:9200")
    OPENSEARCH_USER: str | None = Field(default=None)
    OPENSEARCH_PASSWORD: str | None = Field(default=None)

    # Embeddings (OpenAI)
    TEXT_EMBEDDING_MODEL_NAME: str = Field(default="text-embedding-3-small")
    TEXT_EMBEDDING_API_KEY: str = Field(default="")

    # Image embedding service URL (if any)
    REPLICATE_API_TOKEN: str = Field(default="")
    REPLICATE_IMAGE_EMBEDDING_MODEL: str = Field(default="openai/clip")

    STYLIST_MODEL_NAME: str = Field(default="gpt-4.1-mini")

    # Catalog defaults
    INCLUDE_OUT_OF_STOCK: bool = Field(default=False)

    # Redis / chat session caching
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    CHAT_SESSION_TTL_SECONDS: int = Field(default=6 * 60 * 60)
    CHAT_SESSION_STORAGE_TURNS: int = Field(default=40)
    CHAT_SESSION_SUMMARY_PRODUCT_LIMIT: int = Field(default=6)
    CHAT_SESSION_CONTEXT_WINDOW: int = Field(default=20)
    SHORTLIST_MAX_SIZE: int = Field(default=10)

    # mem0 (persistent user memory)
    MEM0_API_KEY: str = Field(default="")
    MEM0_ENABLED: bool = Field(default=True)

    # Tavily Search (trend awareness)
    TAVILY_API_KEY: str = Field(default="")
    TAVILY_SEARCH_ENABLED: bool = Field(default=True)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()