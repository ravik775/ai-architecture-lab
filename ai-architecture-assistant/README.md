# AI Architecture Assistant

AI Architecture Assistant is a FastAPI-based application that generates high-level architecture recommendations using multiple LLM providers such as OpenAI, Hugging Face, and Ollama. The application uses a Factory Pattern to decouple business logic from AI provider implementations, making it easy to switch models and providers without changing the API contract.

---

## Project Structure

```text
ai-architecture-assistant/
│
├── app/
│   ├── main.py
│   ├── schemas.py
│   ├── config.py
│   ├── llm_factory.py
│   └── architecture_service.py
│
├── requirements.txt
├── .env
└── README.md
```

---

## Architecture Flow

```text
                    FastAPI
                       |
                Architecture Service
                       |
                  LLM Factory
       +---------------+----------------+
       |               |                |
    OpenAI      Hugging Face        Ollama
       |               |                |
  GPT Models     Llama/Qwen       Local Llama
```

### Request Flow

1. Client sends a request to the FastAPI endpoint.
2. FastAPI validates the request using Pydantic schemas.
3. Architecture Service processes the business requirements.
4. LLM Factory selects the configured AI provider.
5. Selected provider generates architecture recommendations.
6. Response is returned through a common API contract.

---

## Advantages

* Loose coupling from AI providers
* Easy model switching
* Better cost control
* Cloud and vendor flexibility
* Reusable API contract
* Enterprise-ready design
* Supports experimentation with open-source models
* Factory Pattern simplifies provider onboarding
* Extensible architecture for future AI integrations

---

## Supported Providers

| Provider     | Models                             |
| ------------ | ---------------------------------- |
| OpenAI       | GPT Models                         |
| Hugging Face | Llama, Qwen, Mistral, etc.         |
| Ollama       | Local Llama and other local models |

---

## Running the Application

### Install Dependencies

```bash
pip3 install -r requirements.txt
```

### Start FastAPI Server

```bash
uvicorn app.main:app --reload
```

### Open Swagger UI

```text
http://localhost:8000/docs
```

---

## Example Request

```json
{
  "base_requirement": "Build an eCommerce platform where users can browse products, place orders, pay online, and track delivery.",
  "domain": "eCommerce",
  "expected_users": 50000,
  "provider": "ollama"
}
```

---

## Design Patterns Used

### Factory Pattern

The `LLMFactory` abstracts provider creation and selection.

Benefits:

* Decouples application logic from AI providers
* Simplifies provider replacement
* Supports dependency inversion
* Improves maintainability and testability

---

## Future Enhancements

* Multi-agent architecture generation
* Architecture diagram generation
* AWS/Azure/GCP-specific recommendations
* Cost estimation and sizing
* RAG-based architecture knowledge base
* Architecture review and optimization suggestions
* Multi-model response comparison
