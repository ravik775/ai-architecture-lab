from dataclasses import dataclass

@dataclass(frozen=True)
class PromptTemplate:
    """Immutable Prompt Template"""
    name: str
    version: str
    template: str
    