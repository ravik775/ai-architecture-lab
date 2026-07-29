---

# Validation

The best way to troubleshoot OpenCode + OmniRoute is to validate one layer at a time.

```
OpenCode
    │
    ▼
OmniRoute
    │
    ▼
LLM Provider
```

If one layer fails, don't continue until it is fixed.

---

## Validation 1 - Verify OmniRoute can access the model

This validates:

- OmniRoute is running
- Authentication works
- Provider configuration works
- The model is reachable

```powershell
curl http://localhost:9000/v1/chat/completions ^
-H "Authorization: Bearer sk-xxxxxxxxxxxxxxxx" ^
-H "Content-Type: application/json" ^
-d "{\"model\":\"hf/deepseek-ai/DeepSeek-V3\",\"stream\":false,\"messages\":[{\"role\":\"user\",\"content\":\"Say Hello\"}]}"
```

Expected Response

```json
{
  "choices": [
    {
      "message": {
        "content": "Hello..."
      }
    }
  ]
}
```

If this succeeds, OmniRoute is correctly communicating with the upstream LLM.

---

## Validation 2 - Verify OpenCode Configuration

Display the effective configuration that OpenCode is using.

```powershell
opencode debug config
```

Expected output

```json
{
  "provider": {
    "omniroute": {
      "options": {
        "baseURL": "http://localhost:9000/v1"
      },
      "models": {
        "hf/deepseek-ai/DeepSeek-V3": {
          "name": "DeepSeek V3"
        }
      }
    }
  },
  "model": "omniroute/hf/deepseek-ai/DeepSeek-V3"
}
```

Things to verify:

- Provider name is `omniroute`
- Base URL points to `http://localhost:9000/v1`
- Model key is the fully qualified model ID (`hf/deepseek-ai/DeepSeek-V3`)
- Default model is `omniroute/hf/deepseek-ai/DeepSeek-V3`

---

## Validation 3 - Verify Available Models in OpenCode

```powershell
opencode models
```

Expected

```text
omniroute/hf/deepseek-ai/DeepSeek-V3
```

If the model is not listed, OpenCode has not loaded the provider configuration correctly.

---

## Validation 4 - Verify the End-to-End OpenCode → OmniRoute Flow

This validates the complete request path:

```
OpenCode
      │
      ▼
OmniRoute
      │
      ▼
DeepSeek V3
```

Run:

```powershell
opencode run ^
-m omniroute/hf/deepseek-ai/DeepSeek-V3 ^
"Create a simple FastAPI application that returns Hello World"
```

Expected behavior:

- OpenCode loads the configured provider.
- OmniRoute receives the request.
- OmniRoute routes the request to `hf/deepseek-ai/DeepSeek-V3`.
- The generated FastAPI code is returned.

---

## Validation 5 - Verify OmniRoute Receives Requests

While the previous command is running, monitor the OmniRoute terminal.

You should observe:

- Incoming request to `/v1/chat/completions`
- Requested model:
  ```
  hf/deepseek-ai/DeepSeek-V3
  ```
- Successful upstream routing
- HTTP 200 response

If OmniRoute reports:

```
Ambiguous model 'deepseek-v3'
```

then OpenCode is sending an alias instead of the fully qualified model identifier.

---

# Validation Checklist

| Step | Validation | Expected |
|------|------------|----------|
| 1 | `curl /v1/chat/completions` | OmniRoute successfully invokes the model |
| 2 | `opencode debug config` | Correct provider and default model are loaded |
| 3 | `opencode models` | Fully qualified model appears in the model list |
| 4 | `opencode run` | OpenCode generates code successfully |
| 5 | OmniRoute logs | Requests show the fully qualified model ID and complete successfully |
