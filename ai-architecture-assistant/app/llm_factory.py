from langchain_openai import ChatOpenAI
from app.config import settings

def get_llm(provider:str) -> ChatOpenAI:
    if provider == "openai":
        return ChatOpenAI(model=settings.OPENAI_MODEL,
                        api_key=settings.OPENAI_API_KEY,
                        temperature=settings.MODEL_TEMPATURE)
    elif provider == "huggingface":
        return ChatOpenAI(model=settings.HF_MODEL, api_key=settings.HF_API_KEY, temperature=settings.MODEL_TEMPERATURE,
                        base_url=settings.HF_BASE_URL)
    elif provider == "ollama":
        return ChatOpenAI(model=settings.OLLAMA_MODEL, api_key=settings.OLLAMA_API_KEY, temperature=settings.MODEL_TEMPERATURE,
                          base_url=settings.OLLAMA_BASE_URL)
    raise ValueError(f"Unsupported provider: {provider}")



