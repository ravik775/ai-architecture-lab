# Business Architecture

## Business Capabilities
1. Loan Application Intake
2. Credit Score Assessment
3. Document Verification
4. Customer Notification
5. Loan Decisioning
6. Status Tracking

## Business Process
1. Customer submits loan application.
2. Loan Service creates application and caches status as SUBMITTED.
3. Loan Service publishes LoanApplicationSubmittedEvent.
4. Credit Score, Document Verification, and Notification services consume event.
5. Loan Decision Service provides decision status.

## Business Benefits
- Faster customer response.
- Improved scalability.
- Reduced manual follow-up.
- Better separation of business capabilities.
