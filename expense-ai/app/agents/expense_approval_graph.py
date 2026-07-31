import uuid
from uuid import UUID

from opentelemetry import trace
from psycopg.rows import dict_row

from app.exceptions import LLMNotFoundError
from app.schemas import ExpenseRequest, ExpenseResponse, ExpenseApprovalState
from app.services.expense_service import ExpenseService
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

# Global database pool for checkpointer persistence
DB_URI = "postgresql://myuser:mypassword@localhost:5432/expense_db"
pool = ConnectionPool(conninfo=DB_URI, max_size=20, kwargs={"row_factory": dict_row})

tracer = trace.get_tracer("expense-ai")


class ExpenseApprovalGraph(ExpenseService):

    def __init__(self, expense_service: ExpenseService):
        self.expense_service = expense_service
        self.checkpointer = PostgresSaver(pool)
        self._setup_checkpointer()
        self.workflow = self._build()

    def _setup_checkpointer(self):
        """Ensures migrations run in autocommit mode to support CONCURRENTLY index creation."""
        with pool.connection() as conn:
            conn.autocommit = True
            PostgresSaver(conn).setup()

    def _build(self) -> StateGraph:
        builder = StateGraph(ExpenseApprovalState)

        # Add Nodes
        builder.add_node("analyze_expense", self._analyze_expense)
        builder.add_node("evaluate_approval", self._evaluate_approval)
        builder.add_node("approval_review", self._approval_review)
        builder.add_node("finalize", self._finalize)

        # Add Edges
        builder.add_edge(START, "analyze_expense")
        builder.add_edge("analyze_expense", "evaluate_approval")
        builder.add_conditional_edges(
            "evaluate_approval",
            self._route_approval,
            {
                "approval_review": "approval_review",
                "finalize": "finalize",
            },
        )
        builder.add_edge("approval_review", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile(checkpointer=self.checkpointer)

    def _analyze_expense(self, state: ExpenseApprovalState) -> dict:
        response = self.expense_service.analyze(state["request"])
        response.status = "IN_PROGRESS"
        # Preserve the deterministic analysis_id created in analyze()
        if state.get("response") and state["response"].analysis_id:
            response.analysis_id = state["response"].analysis_id
        return {"response": response}

    def _evaluate_approval(self, state: ExpenseApprovalState) -> dict:
        response: ExpenseResponse = state["response"]
        if response:
            reason = []
            if response.total_expenses >= 1000:
                reason.append(f"Total expenses: {response.total_expenses}")
            if response.suspicious:
                reason.append(f"Suspicious: {response.suspicious}")
            if response.policy_flags:
                reason.append(f"Policy Flags: {','.join(response.policy_flags)}")
            if response.requires_approval:
                reason.append(f"Requires approval: {response.requires_approval}")

            # FIX 1: Map key to 'approval_reason' to match ExpenseApprovalState definition
            return {
                "approval_required": bool(reason),
                "approval_reason": "; ".join(reason) if reason else None
            }
        raise RuntimeError("Expense Response not available.")

    def _route_approval(self, state: ExpenseApprovalState) -> str:
        return "approval_review" if state["approval_required"] else "finalize"

    def _approval_review(self, state: ExpenseApprovalState) -> dict:
        response = state["response"]
        response.status = "APPROVAL_REQUIRED"
        human_decision = interrupt({
            "message": "Awaiting manual approval",
            "analysis_id": str(state["response"].analysis_id),
            "reason": state.get("approval_reason"),
        })
        return {
            "human_action": human_decision.get("action"),
            "final_message": f"Approved by human: {human_decision.get('action')}",
        }

    def _finalize(self, state: ExpenseApprovalState) -> dict:
        response = state["response"]
        approval_required = state["approval_required"]

        if approval_required:
            action = state.get("human_action")
            # FIX 3: Set status to APPROVAL_REQUIRED if human hasn't submitted action yet
            if action:
                response.status = action  # 'APPROVED' or 'REJECTED'
            else:
                response.status = "APPROVAL_REQUIRED"
            message = state.get("final_message") or "Expense awaiting human review."
        else:
            response.status = "APPROVED"
            message = "Expense approved automatically without review."

        return {"response": response, "message": message}

    def analyze(self, request: ExpenseRequest, analysis_id:UUID| None=None) -> ExpenseResponse:
        analysis_id = analysis_id or uuid.uuid4()
        temp_response = ExpenseResponse(
            analysis_id=analysis_id,
            tenant="Guest",
            total_expenses=len(request.expenses),
            total_amount=sum(e.amount * e.quantity for e in request.expenses),
            currency=request.currency,
            status="PENDING",
        )

        initial_state: ExpenseApprovalState = {
            "analysis_id": analysis_id,
            "request": request,
            "response": temp_response,
            "approval_required": False,
            "approval_reason": None,
            "human_action": None,
            "final_message": None,
        }

        # FIX 2: Use deterministic analysis_id for thread_id
        config = {"configurable": {"thread_id": str(analysis_id)}}

        with tracer.start_as_current_span("analyze_expenses_agentic"):
            final_state = self.workflow.invoke(initial_state, config=config)
            return final_state["response"]

    def resume_approval(self, analysis_id: str, action: str) -> ExpenseResponse:
        config = {"configurable": {"thread_id": str(analysis_id)}}

        # 1. Fetch current checkpoint state from PostgreSQL
        state_snapshot = self.workflow.get_state(config)

        # 2. Validate that the thread exists and actually has state saved in checkpointer
        if not state_snapshot or not state_snapshot.values:
            raise LLMNotFoundError(f"Expense analysis with ID '{analysis_id}' was not found or has expired.")

        # 3. Check if workflow is already completed (state_snapshot.next is empty)
        if not state_snapshot.next:
            # Workflow finished previously; return the finalized response directly from checkpointer
            print(f"Workflow is already Completed... {analysis_id=}")
            return state_snapshot.values["response"]
        print(f"Workflow resumed... {analysis_id=}")
        # 4. Resume execution safely if currently paused at interrupt
        final_state = self.workflow.invoke(Command(resume={"action": action}), config=config)
        return final_state["response"]