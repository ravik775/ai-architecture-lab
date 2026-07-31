from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app


class TestExpenseAPI:
    client = TestClient(app)

    def test_health_check(self):
        response = self.client.get("/health")
        assert response.status_code == 200
        # FIX 1: Match HealthResponse schema fields
        data = response.json()
        assert data["status"] == "UP"
        assert "provider" in data
        assert "model" in data

    def test_analyze_expenses_success(self):
        payload = {
            "submitted_by": "John Doe",
            "currency": "INR",
            "submitted_date": datetime.now(timezone.utc).isoformat(),
            "expenses": [
                {
                    "description": "Team Lunch",
                    "amount": 150.0,
                    "merchant": "Restaurant XYZ",
                    "category": "Food",
                    "notes": "Client meeting",
                }
            ],
        }
        response = self.client.post("/api/v1/expenses/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["tenant"] == "Guest"
        assert data["total_expenses"] == 1
        assert data["total_amount"] == 150.0
        assert data["currency"] == "INR"
        # FIX 2: Agentic workflow auto-approves valid low-value expenses
        assert data["status"] in ("APPROVED", "ANALYZED")
        assert "analysis_id" in data

    def test_analyze_expenses_future_submitted_date_error(self):
        future_date = datetime.now(timezone.utc) + timedelta(minutes=10)
        payload = {
            "submitted_by": "John Doe",
            "currency": "INR",
            "submitted_date": future_date.isoformat(),
            "expenses": [],
        }
        response = self.client.post("/api/v1/expenses/analyze", json=payload)
        assert response.status_code == 422

    def test_analyze_expenses_future_expense_date_error(self):
        future_date = datetime.now(timezone.utc) + timedelta(minutes=10)
        payload = {
            "submitted_by": "John Doe",
            "currency": "INR",
            "submitted_date": datetime.now(timezone.utc).isoformat(),
            "expenses": [
                {
                    "description": "Future Flight",
                    "amount": 100.0,
                    "expense_date": future_date.isoformat(),
                    "merchant": "Airline",
                    "category": "Travel",
                }
            ],
        }
        response = self.client.post("/api/v1/expenses/analyze", json=payload)
        assert response.status_code == 422

    def test_analyze_expenses_invalid_amount_error(self):
        payload = {
            "submitted_by": "John Doe",
            "currency": "INR",
            "submitted_date": datetime.now(timezone.utc).isoformat(),
            "expenses": [
                {
                    "description": "Bad Amount",
                    "amount": -50.0,
                }
            ],
        }
        response = self.client.post("/api/v1/expenses/analyze", json=payload)
        assert response.status_code == 422

    def test_analyze_expenses_invalid_submitted_by_length_error(self):
        payload = {
            "submitted_by": "Jo",  # Too short (min_length=3)
            "currency": "INR",
            "submitted_date": datetime.now(timezone.utc).isoformat(),
            "expenses": [],
        }
        response = self.client.post("/api/v1/expenses/analyze", json=payload)
        assert response.status_code == 422

    def test_analyze_expenses_invalid_currency_length_error(self):
        payload = {
            "submitted_by": "John Doe",
            "currency": "IN",  # Too short (min_length=3, max_length=3)
            "submitted_date": datetime.now(timezone.utc).isoformat(),
            "expenses": [],
        }
        response = self.client.post("/api/v1/expenses/analyze", json=payload)
        assert response.status_code == 422