from langchain_core.prompts import ChatPromptTemplate

from app.llm_factory import get_llm
from app.schemas import ArchitectureRecommendation, ArchitectureRequest


def generate_architecture_recommendation(request: ArchitectureRequest) -> ArchitectureRecommendation:
    llm = get_llm(request.provider)
    structured_llm = llm.with_structured_output(ArchitectureRecommendation )
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
            You are a senior AI Solution Architect.

            Analyze the business requirement and recommend an architecture.
            Focus on:
            - scalability
            - API design
            - data flow
            - cloud readiness
            - risks
            - clarifying questions

            Return only structured output.
            """
        ),
        (
            "human",
            """
            Requirement:
            {business_requirement}

            Domain:
            {domain}

            Expected Users:
            {expected_users}
            """
        )
    ])

    chain = prompt | structured_llm

    return chain.invoke({
        "business_requirement": request.business_requirement,
        "domain": request.domain,
        "expected_users": request.expected_users
    })