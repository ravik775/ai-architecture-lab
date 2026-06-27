from pydantic import BaseModel, Field
from typing import List

class ArchitectureRequest(BaseModel):
    business_requirement: str = Field(..., min_length=40, max_length=100000, description="Base requirement")
    domain: str = Field(default="general", min_length=5, max_length=100, description="Domain name")
    expected_users: int = Field(default=20, ge=5, description="Expected users")
    provider: str = Field("openai", description="AI Model provider solution be build on")

class ArchitectureRecommendation(BaseModel):
    architecture_style: str
    key_concepts: List[str]
    recomended_tech_stach: List[str]
    riks: List[str]
    clarification: List[str]
    summary: str



