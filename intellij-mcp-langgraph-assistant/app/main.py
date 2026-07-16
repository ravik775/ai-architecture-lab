from mcp.server.fastmcp import FastMCP

from pydantic import BaseModel, Field

from langchain_litellm import ChatLiteLLM
from langchain_core.prompts import ChatPromptTemplate

from dotenv import load_dotenv
import sys
import json
import os, logging

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger(__name__)

# -----------------------------------------------------
# Environment
# -----------------------------------------------------

load_dotenv()

MODEL_NAME = os.getenv(
    "LLM_MODEL",
    "github/gpt-4.1"
)

if MODEL_NAME.startswith("github/"):

    github_token = os.getenv("GITHUB_TOKEN")

    if not github_token:
        raise RuntimeError(
            "GITHUB_TOKEN not configured"
        )

    os.environ["GITHUB_API_KEY"] = github_token


# -----------------------------------------------------
# Response Schema
# -----------------------------------------------------

class PolishedText(BaseModel):

    text: str = Field(
        description="Grammar corrected text"
    )

    changes_made: list[str] = Field(
        default_factory=list,
        description="List of modifications performed"
    )


# -----------------------------------------------------
# LLM
# -----------------------------------------------------

chat_model = ChatLiteLLM(
    model=MODEL_NAME,
    temperature=0,
    max_tokens=512
)


# -----------------------------------------------------
# Prompt
# -----------------------------------------------------

system_prompt = """
You are a professional editor.

Responsibilities:

1. Correct grammar.
2. Correct spelling.
3. Correct punctuation.
4. Improve clarity.
5. Improve professionalism.
6. Improve consistency.

Return ONLY valid JSON.

Example:

{{
  "text": "This is the corrected text.",
  "changes_made": [
    "Fixed capitalization",
    "Corrected spelling",
    "Improved punctuation"
  ]
}}

Rules:

- Do not return markdown.
- Do not return explanations.
- Do not return code fences.
- Output must be valid JSON.
"""


prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            system_prompt
        ),
        (
            "human",
            "{raw_text}"
        )
    ]
)


# -----------------------------------------------------
# Chain
# -----------------------------------------------------

chain = prompt | chat_model


# -----------------------------------------------------
# MCP
# -----------------------------------------------------
host = os.getenv("MCP_HOST", "0.0.0.0")
port = int(os.getenv("MCP_PORT", 8000))

mcp = FastMCP("text-polisher",  host=host, port=port, log_level="WARNING")


@mcp.tool()
def polish_text(raw_text: str) -> PolishedText:
    """
    Correct grammar and improve text quality.
    """

    response = chain.invoke(
        {
            "raw_text": raw_text
        }
    )

    content = response.content

    try:

        if isinstance(content, list):
            content = "".join(
                str(x)
                for x in content
            )

        data = json.loads(content)

        result = PolishedText.model_validate(
            data
        )
        logger.info(f"Polished text: {result.text}, raw_text: {raw_text}")
        return result
    except Exception as ex:

        return {
            "error": "Invalid model response",
            "details": str(ex),
            "raw_response": content
        }


# -----------------------------------------------------
# Main
# -----------------------------------------------------

if __name__ == "__main__":
    args = { "transport" :"stdio"}
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", 8000))
    if os.getenv("MCP_TRANSPORT") == "stdio":
        args = { "transport" :"stdio"}
        logger.info("Starting MCP Server [text-polisher] using STDIO transport")
    elif os.getenv("MCP_TRANSPORT") == "http":
        logger.info(f"Starting MCP Server [text-polisher] using HTTP transport on {host}:{port}")
        args = { "transport": "streamable-http"}
    mcp.run(**args)