"""Environment settings. Loading is implemented in a later step."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view of the repo-root .env file."""

    model_config = SettingsConfigDict(extra="ignore")

    use_mock_data: bool = True
    mock_cities_path: str = "data/mock/cities.csv"
    mock_disasters_path: str = "data/mock/disasters.json"
    mock_news_path: str = "data/mock/news.json"

    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_warehouse: str = ""
    snowflake_database: str = ""
    snowflake_schema: str = ""
    snowflake_role: str = ""
    snowflake_disaster_table: str = ""
    snowflake_news_table: str = ""

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    avg_speed_mph: float = 55
    min_hop_miles: float = 150
    max_hop_miles: float = 350
    road_factor: float = 1.25
    candidate_route_count: int = 3
    hazard_weight_hours: float = 10
    news_weight_hours: float = 6
    news_lookback_days: float = 7


def get_settings() -> Settings:
    """Load settings from the environment and the repo-root .env file."""
    raise NotImplementedError
