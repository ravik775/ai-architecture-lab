from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PolicyDocument:
    """
    Static policy document used to seed the vector store.

    These documents represent the initial enterprise knowledge base for
    Module 8 RAG. Later modules can replace this static corpus with uploaded
    policy documents, PDFs, or tenant-specific policy sources.
    """

    id: str
    title: str
    category: str
    content: str
    source: str = "static-expense-policy"

    def metadata(self) -> dict[str, str]:
        return {
            "title": self.title,
            "category": self.category,
            "source": self.source,
        }


EXPENSE_POLICY_DOCUMENTS: tuple[PolicyDocument, ...] = (
    PolicyDocument(
        id="expense-policy-travel-reimbursement",
        title="Travel Reimbursement Policy",
        category="travel",
        content=(
            "Business travel expenses are reimbursable only when they are "
            "directly related to approved business activity. Eligible expenses "
            "include airfare, train fare, taxi, rideshare, parking, tolls, and "
            "reasonable local transport. Personal travel, sightseeing, family "
            "travel, seat upgrades, and non-business detours are not reimbursable "
            "unless explicitly approved before the trip."
        ),
    ),
    PolicyDocument(
        id="expense-policy-meals-limit",
        title="Meals Limit Policy",
        category="meals",
        content=(
            "Meal expenses are reimbursable when incurred during approved business "
            "travel or client meetings. Daily meal reimbursement should remain "
            "within the approved company limit. Alcohol, luxury dining, personal "
            "celebrations, and meals without a business purpose should be flagged "
            "for review. Repeated high meal expenses from the same employee require "
            "manager validation."
        ),
    ),
    PolicyDocument(
        id="expense-policy-hotel-approval",
        title="Hotel Approval Policy",
        category="lodging",
        content=(
            "Hotel and lodging expenses are reimbursable for approved overnight "
            "business travel. Premium suites, resort charges, minibar charges, spa "
            "services, and personal amenities are not reimbursable. Hotel expenses "
            "above the standard nightly limit require prior manager approval. "
            "Missing booking details or unusually high lodging amounts should be "
            "flagged for approval review."
        ),
    ),
    PolicyDocument(
        id="expense-policy-suspicious-merchant-pattern",
        title="Suspicious Merchant Pattern Policy",
        category="fraud",
        content=(
            "Expenses should be reviewed when merchant names are missing, vague, "
            "unknown, duplicated, or unrelated to the submitted category. Suspicious "
            "patterns include repeated transactions at the same merchant on the same "
            "day, round-number amounts, split expenses designed to avoid approval "
            "limits, and expenses from merchants associated with personal services "
            "or entertainment."
        ),
    ),
    PolicyDocument(
        id="expense-policy-duplicate-expenses",
        title="Duplicate Expense Policy",
        category="fraud",
        content=(
            "Duplicate expenses are not reimbursable. An expense should be flagged "
            "as a possible duplicate when the employee submits multiple items with "
            "the same or similar date, merchant, amount, description, or receipt "
            "reference. Duplicate detection should consider exact matches and near "
            "matches because employees may slightly alter descriptions or categories."
        ),
    ),
    PolicyDocument(
        id="expense-policy-missing-receipt",
        title="Missing Receipt Policy",
        category="receipt",
        content=(
            "Receipts are required for reimbursable expenses above the company "
            "receipt threshold and for all hotel, airfare, equipment, and client "
            "entertainment expenses. Missing receipts should be flagged for review. "
            "Employees must provide a reason for any missing receipt, and repeated "
            "missing receipts from the same employee may require manager approval."
        ),
    ),
    PolicyDocument(
        id="expense-policy-currency-mismatch",
        title="Currency Mismatch Policy",
        category="currency",
        content=(
            "Expenses must be submitted in the correct reimbursement currency. "
            "Foreign currency expenses should include the original currency, exchange "
            "rate, converted amount, and transaction date. A currency mismatch should "
            "be flagged when the submitted currency does not match the merchant "
            "location, travel destination, receipt currency, or expected corporate "
            "reimbursement currency."
        ),
    ),
)


def get_expense_policy_documents() -> tuple[PolicyDocument, ...]:
    """
    Return the static seed corpus for the expense policy knowledge base.

    The tuple is immutable by design so tests and startup seeding get the same
    deterministic policy corpus every time.
    """

    return EXPENSE_POLICY_DOCUMENTS


def get_policy_texts() -> list[str]:
    return [document.content for document in EXPENSE_POLICY_DOCUMENTS]


def get_policy_ids() -> list[str]:
    return [document.id for document in EXPENSE_POLICY_DOCUMENTS]


def get_policy_metadatas() -> list[dict[str, str]]:
    return [document.metadata() for document in EXPENSE_POLICY_DOCUMENTS]