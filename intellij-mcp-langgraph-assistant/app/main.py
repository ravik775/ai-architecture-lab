"""
text-polisher MCP Server
-------------------------
A minimal, reference-quality MCP server that demonstrates the three
core *server-side* primitives defined by the Model Context Protocol:

    1. Resources -> read-only context      (resource://...)
    2. Prompts   -> reusable interaction templates (@mcp.prompt())
    3. Tools     -> executable actions             (@mcp.tool())

The domain is intentionally simple (polishing text) so the MCP
concepts stay the star of the show rather than the business logic.
"""

import logging
import os
from typing import Literal

from mcp.server.fastmcp.prompts import base
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_litellm import ChatLiteLLM
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
import sys

load_dotenv()

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(message)s")

logger = logging.getLogger(__name__)

# -----------------------------------------------------
# Environment
# -----------------------------------------------------

load_dotenv()

MODEL_NAME = os.getenv("LLM_MODEL", "github/gpt-4.1")

if MODEL_NAME.startswith("github/"):
    github_token = os.getenv("MODEL_API_KEY")
    if not github_token:
        raise RuntimeError("GITHUB_TOKEN not configured")
    os.environ["GITHUB_API_KEY"] = github_token



# ---------------------------------------------------------------------------
# Structured output contract
# ---------------------------------------------------------------------------
class PolishedText(BaseModel):
    """The shape every polish_text call returns, so downstream tools/agents
    can consume the result programmatically instead of parsing prose."""

    text: str = Field(description="The polished version of the input text.")
    changes_made: list[str] = Field( description="Short bullet list of the concrete edits that were made.")

# ---------------------------------------------------------------------------
# Model + chain
#
# We bind the Pydantic schema directly via with_structured_output instead of
# hand-parsing the model's raw text response. This removes an entire class
# of failures (stray markdown fences, trailing prose, truncated JSON) that a
# manual json.loads() on free-form model output is exposed to.
# ---------------------------------------------------------------------------
chat_model = ChatLiteLLM(model=MODEL_NAME, temperature=0)
structured_model = chat_model.with_structured_output(PolishedText)

SYSTEM_PROMPT = """
You are a professional editor. Polish the user's text for clarity,
tone, and correctness while preserving their original meaning and intent.
Follow the company's writing standards and writing rules provided as
context. Do not invent information that isn't in the source text.
""".strip()

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "{raw_text}"),
    ]
)

chain = prompt | structured_model


# -----------------------------------------------------
# MCP
# -----------------------------------------------------
host = os.getenv("MCP_HOST", "0.0.0.0")
port = int(os.getenv("MCP_PORT", 8000))

mcp = FastMCP("text-polisher",  host=host, port=port, log_level="WARNING")

# ---------------------------------------------------------------------------
# 1) RESOURCES — read-only, application-controlled context.
#    The host decides when to pull these into context; the model never
#    "calls" a resource the way it calls a tool.
# ---------------------------------------------------------------------------
@mcp.resource("resource://style-guide", name="Company Writing Standards", description="Company writing standards for professional communication.")
def style_guide() -> str:
    logging.info("1. style_guide resource requested")
    return (
        "- Prefer active voice.\n"
        "- Keep sentences under 25 words where possible.\n"
        "- Avoid jargon unless the audience is technical.\n"
        "- Use inclusive, plain language.\n"
        "- Lead with the main point, then supporting detail."
    )


@mcp.resource("resource://writing-rules", name="Writing Rules", description="General writing rules for professional communication.")
def writing_rules() -> str:
    logging.info("2. writing_rules resource requested")
    return (
        "- No ALL CAPS except for acronyms.\n"
        "- One idea per sentence.\n"
        "- Spell out numbers below 10 in prose.\n"
        "- Match the tone requested (formal/casual) if the user specifies one."
    )


# ---------------------------------------------------------------------------
# 2) PROMPTS — reusable, user-controlled interaction templates.
#    Unlike a tool, a prompt is surfaced to the *user* as something they can
#    explicitly select (e.g. a slash command), rather than something the
#    model decides to invoke on its own.
#
#    This is the primitive the previous version of this server was missing.
#    It composes the two resources above with the polish_text tool into a
#    guided, channel-aware workflow.
# ---------------------------------------------------------------------------
@mcp.prompt(
    name="polish_for_channel",
    description=(
        "Guided workflow: polish a piece of text for a specific "
        "communication channel (email, chat, or formal document), "
        "using the company style guide and writing rules as context."
    ),
)
def polish_for_channel( raw_text: str, channel: Literal["email", "chat", "doc"] = "email") -> str:
    logging.info(f"3. polish_for_channel prompt requested for channel={channel}")
    channel_guidance = {
        "email": "Use a professional greeting and sign-off. Medium formality.",
        "chat": "Be brief and conversational. Skip greetings/sign-offs.",
        "doc": "Use formal tone. No contractions. Prefer complete sentences.",
    }[channel]

    return (
        "Read the resource://style-guide and resource://writing-rules "
        "resources for context, then call the polish_text tool on the "
        f"text below.\n\nChannel: {channel}\nChannel guidance: {channel_guidance}"
        f"\n\nText to polish:\n{raw_text}"
    )


# ---------------------------------------------------------------------------
# 3) TOOLS — model-controlled, executable actions with typed inputs/outputs.
# ---------------------------------------------------------------------------
@mcp.tool()
def polish_text(raw_text: str) -> PolishedText:
    """Polish the given text for clarity, tone, and correctness.

    Returns a PolishedText object containing the rewritten text and a
    short list of the changes made, so the result can be consumed
    programmatically by other tools or agents.
    """
    logging.info(f"4. polish_text tool requested, {raw_text=}")
    try:
        result = chain.invoke({"raw_text": raw_text})
    except Exception:
        logger.exception("polish_text failed to produce structured output")
        raise

    if not isinstance(result, PolishedText):
        # with_structured_output can return a dict depending on the
        # underlying provider; normalize defensively.
        result = PolishedText.model_validate(result)

    return result


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "stdio":
        args = {"transport": "stdio"}
    else:
        args = {"transport": "streamable-http"}

    mcp.run(**args)