from dataclasses import dataclass, field

@dataclass(frozen=True)
class FewShotExample:
    input: str
    output: str

@dataclass(frozen=True)
class PromptTemplate:
    """Immutable Prompt Template"""
    name: str
    version: str
    template: str
    examples: list[FewShotExample] = field(default_factory=list)
