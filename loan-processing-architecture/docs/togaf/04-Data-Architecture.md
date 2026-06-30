# Data Architecture

## Entities
- LoanApplication
- Customer
- CreditScore
- DocumentVerification
- LoanDecision
- Notification

## Cache Keys
- `loan:{applicationId}` stores current status.

## Current Implementation
For laptop simplicity, Loan Service uses in-memory storage plus Redis cache. In production, replace in-memory map with PostgreSQL or another durable database.

## Data Consistency
The system uses eventual consistency because downstream processing is asynchronous. Loan submission is immediately acknowledged; credit/document/notification processing happens independently.
