# Ollama Installation Guide for Windows

## Prerequisites

* Windows 10 or Windows 11 (64-bit)
* Internet connection
* PowerShell or Command Prompt

---

# Step 1: Download Ollama

Download the Windows installer from:

https://ollama.com/download

Run the installer and complete the installation.

---

# Step 2: Verify Installation

Open **PowerShell** and execute:

```powershell
ollama --version
```

Expected output:

```text
ollama version 0.x.x
```

---

# Step 3: Verify Ollama Service

Run:

```powershell
ollama list
```

Expected output for a fresh installation:

```text
NAME    ID    SIZE    MODIFIED
```

This indicates that Ollama is installed successfully but no models have been downloaded yet.

---

# Step 4: Download a Model

Download the recommended model for this course:

```powershell
ollama pull llama3.2
```

The initial download may take several minutes depending on your internet connection.

---

# Step 5: Verify Download

List the installed models:

```powershell
ollama list
```

Expected output:

```text
NAME              SIZE
llama3.2:latest   2 GB
```

---

# Step 6: Test the Model

Start an interactive chat session:

```powershell
ollama run llama3.2
```

You should see:

```text
>>> Send a message (/? for help)
```

Example:

```text
Explain FastAPI
```

Exit the session:

```text
/bye
```

---

# Step 7: Verify REST API

Ollama automatically starts a local REST server.

Open the following URL in your browser:

```
http://localhost:11434/api/tags
```

or execute:

```powershell
curl http://localhost:11434/api/tags
```

Expected response:

```json
{
  "models": [
    {
      "name": "llama3.2:latest"
    }
  ]
}
```

---

# Step 8: Verify OpenAI-Compatible Endpoint

Open:

```
http://localhost:11434/v1/models
```

Expected response:

```json
{
  "data": [
    {
      "id": "llama3.2"
    }
  ]
}
```

This endpoint will be used by our FastAPI and LangChain applications.

---

# Useful Commands

## List Installed Models

```powershell
ollama list
```

---

## Download a Model

```powershell
ollama pull llama3.2
```

---

## Start a Model

```powershell
ollama run llama3.2
```

---

## Remove a Model

```powershell
ollama rm llama3.2
```

---

## Display Model Information

```powershell
ollama show llama3.2
```

---

## Update an Existing Model

```powershell
ollama pull llama3.2
```

---

# Recommended Models

| Model            | Purpose                                          |
| ---------------- | ------------------------------------------------ |
| llama3.2         | General AI Assistant (Recommended for beginners) |
| qwen2.5-coder:7b | Coding Assistant                                 |
| mistral          | General Purpose LLM                              |
| llama3.3         | Advanced Reasoning (Requires More Resources)     |

Example:

```powershell
ollama pull qwen2.5-coder:7b
```

---

# Installation Verification Checklist

* [ ] Ollama installed successfully
* [ ] `ollama --version` returns a version
* [ ] `ollama list` executes successfully
* [ ] `llama3.2` model downloaded
* [ ] `ollama run llama3.2` starts an interactive chat
* [ ] `http://localhost:11434/api/tags` is accessible
* [ ] `http://localhost:11434/v1/models` returns the available models

