from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # OpenAI
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Hugging Face
    HF_API_KEY: str | None = None
    HF_MODEL: str = "meta-llama/Llama-3.1-8B-Instruct"
    HF_BASE_URL: str = "https://router.huggingface.co/v1"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_API_KEY: str | None = "ollama"
    # Common Settings
    MODEL_TEMPERATURE: float = 0.2

    class Config:
        env_file = ".env"


settings = Settings()