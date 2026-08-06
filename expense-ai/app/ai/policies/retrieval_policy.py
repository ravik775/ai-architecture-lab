from functools import lru_cache

from app.ai.models import ExecutionContext, ProviderResponse, TResponse
from app.ai.policies.base import ExecutionHandler, Policy
from app.config import settings
from app.observability.logging import log_info
from app.rag.chroma_retriever import (
    ChromaPolicyRetriever,
    build_expense_policy_query,
)


@lru_cache(maxsize=1)
def get_policy_retriever() -> ChromaPolicyRetriever:
    return ChromaPolicyRetriever(
        persist_directory=settings.rag.persist_directory,
        collection_name=settings.rag.collection_name,
        top_k=settings.rag.top_k,
    )


class RetrievalPolicy(Policy):
    """
    Retrieves policy context before prompt rendering.

    This policy gives the LLM enterprise context without putting retrieval logic
    inside ExpenseService or the prompt builder.
    """

    priority = 15
    name = "retrieval"

    def execute(
        self,
        context: ExecutionContext,
        next_handler: ExecutionHandler,
    ) -> ProviderResponse[TResponse]:
        if not settings.rag.enabled:
            return next_handler()

        expenses = getattr(context.request.request, "expenses", [])
        query = build_expense_policy_query(expenses)
        policies = get_policy_retriever().retrieve(query)
        context.retrieved_context = policies

        log_info(
            "rag.policy_context.retrieved",
            retrieved_count=len(policies),
            policy_ids=[policy.id for policy in policies],
        )

        return next_handler()