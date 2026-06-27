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


Flow:
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

Advantage:
    Loose coupling from AI provider
    Easy model switching
    Better cost control
    Cloud/vendor flexibility
    Reusable API contract
    Enterprise-ready design
    Supports experimentation with open models
    
Running the APP:
  pip3 install -r .\requirement.txt
  uvicorn app.main:app --reload
  Swagger Page: http://localhost:8000/docs#/default
