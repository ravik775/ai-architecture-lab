from app.rag.chroma_retriever import ChromaPolicyRetriever


def test_chroma_retriever_creates_collection_and_seeds_policies(tmp_path):
    retriever = ChromaPolicyRetriever(
        persist_directory=str(tmp_path / "chroma"),
        collection_name="test_expense_policies",
        top_k=3,
    )

    assert retriever.collection.count() == 7


def test_chroma_retriever_returns_relevant_policy_documents(tmp_path):
    retriever = ChromaPolicyRetriever(
        persist_directory=str(tmp_path / "chroma"),
        collection_name="test_expense_policies",
        top_k=3,
    )

    policies = retriever.retrieve(
        "hotel lodging expense missing receipt manager approval overnight travel"
    )

    assert len(policies) > 0

    titles = {policy.title for policy in policies}

    assert (
        "Hotel Approval Policy" in titles
        or "Missing Receipt Policy" in titles
        or "Travel Reimbursement Policy" in titles
    )


def test_chroma_retriever_returns_empty_list_for_blank_query(tmp_path):
    retriever = ChromaPolicyRetriever(
        persist_directory=str(tmp_path / "chroma"),
        collection_name="test_expense_policies",
        top_k=3,
    )

    policies = retriever.retrieve("   ")

    assert policies == []