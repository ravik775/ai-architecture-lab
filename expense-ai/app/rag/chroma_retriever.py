from dataclasses import dataclass
from pathlib import Path
import hashlib
import math
import re

import chromadb
from chromadb.api.types import Documents, Embeddings

from app.rag.policy_corpus import (
    get_expense_policy_documents,
    get_policy_ids,
    get_policy_metadatas,
    get_policy_texts,
)


@dataclass(frozen=True, slots=True)
class RetrievedPolicy:
    id: str
    title: str
    category: str
    content: str
    score: float | None = None


class LocalHashEmbeddingFunction:
    """
    Deterministic local embedding function.
    """

    def __init__(self, dimensions: int = 128):
        self.dimensions = dimensions

    def name(self) -> str:
        return "LocalHashEmbeddingFunction"

    def __call__(self, input: Documents) -> Embeddings:
        return self._embed_many(input)

    def embed_documents(self, input: Documents) -> Embeddings:
        return self._embed_many(input)

    def embed_query(self, input: Documents) -> Embeddings:
        return self._embed_many(input)

    def _embed_many(self, input: Documents | str) -> Embeddings:
        if isinstance(input, str):
            input = [input]
        return [self._embed(document) for document in input]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())

        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            index = int(digest, 16) % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector

        return [value / norm for value in vector]


class ChromaPolicyRetriever:
    """
    ChromaDB-backed retriever for expense policy documents.

    Responsibility:
    - Own ChromaDB collection access.
    - Seed static policy documents.
    - Retrieve relevant policies for a query.

    It does not:
    - Build prompts.
    - Call the LLM.
    - Make business decisions.
    """

    def __init__(
        self,
        persist_directory: str = ".chroma",
        collection_name: str = "expense_policies",
        top_k: int = 3,
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.top_k = top_k
        self.embedding_function = LocalHashEmbeddingFunction()

        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=self.persist_directory)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
        )

        self.seed()

    def seed(self) -> None:
        """
        Seed static expense policies into ChromaDB.

        This method is idempotent enough for local use:
        - It checks existing IDs.
        - It only inserts missing policies.
        """

        existing = self.collection.get(ids=get_policy_ids())
        existing_ids = set(existing.get("ids", []))

        documents = get_policy_texts()
        ids = get_policy_ids()
        metadatas = get_policy_metadatas()

        missing_ids: list[str] = []
        missing_documents: list[str] = []
        missing_metadatas: list[dict[str, str]] = []

        for policy_id, document, metadata in zip(ids, documents, metadatas):
            if policy_id not in existing_ids:
                missing_ids.append(policy_id)
                missing_documents.append(document)
                missing_metadatas.append(metadata)

        if not missing_ids:
            return

        self.collection.add(
            ids=missing_ids,
            documents=missing_documents,
            metadatas=missing_metadatas,
        )

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedPolicy]:
        if not query.strip():
            return []

        result = self.collection.query(
            query_texts=[query],
            n_results=top_k or self.top_k,
        )

        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        retrieved: list[RetrievedPolicy] = []

        for policy_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
        ):
            retrieved.append(
                RetrievedPolicy(
                    id=policy_id,
                    title=metadata.get("title", ""),
                    category=metadata.get("category", ""),
                    content=document,
                    score=distance,
                )
            )

        return retrieved


def build_expense_policy_query(expenses: list) -> str:
    """
    Convert expense request data into retrieval text.

    Keep this simple for Module 8. The retriever needs enough text to match
    against policy documents.
    """

    query_parts: list[str] = []

    for expense in expenses:
        query_parts.append(
            " ".join(
                str(value)
                for value in [
                    getattr(expense, "merchant", ""),
                    getattr(expense, "category", ""),
                    getattr(expense, "description", ""),
                    getattr(expense, "amount", ""),
                    getattr(expense, "notes", ""),
                ]
                if value is not None
            )
        )

    return "\n".join(query_parts)


def format_retrieved_policies(policies: list[RetrievedPolicy]) -> str:
    """
    Convert retrieved policies into prompt-ready context.
    """

    if not policies:
        return "No relevant policy context was retrieved."

    blocks: list[str] = []

    for index, policy in enumerate(policies, start=1):
        blocks.append(
            "\n".join(
                [
                    f"Policy {index}: {policy.title}",
                    f"Category: {policy.category}",
                    f"Content: {policy.content}",
                ]
            )
        )

    return "\n\n".join(blocks)