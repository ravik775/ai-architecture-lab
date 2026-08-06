"""LangGraph agent construction."""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from src.agent.llm import LiteLLMChatModel


def build_agent(llm: LiteLLMChatModel, tools: list, system_prompt: str):
    """Build a ReAct-style agent: model <-> tools loop, LangGraph-managed."""
    return create_react_agent(model=llm, tools=tools, prompt=system_prompt)
