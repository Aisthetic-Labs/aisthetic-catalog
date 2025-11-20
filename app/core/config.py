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
    EMBEDDING_MODEL_NAME: str = Field(default="text-embedding-3-small")
    EMBEDDING_API_KEY: str = Field(default="")

    # Image embedding service URL (if any)
    REPLICATE_API_TOKEN: str = Field(default="")
    REPLICATE_IMAGE_EMBEDDING_MODEL: str = Field(default="openai/clip")

    STYLIST_MODEL_NAME: str = "gpt-4.1-mini"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()