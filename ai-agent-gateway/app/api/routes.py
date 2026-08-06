from fastapi import APIRouter
from app.models.schemas import AgentRequest, AgentResponse
from app.services.agent_service import AgentService

router = APIRouter(prefix='/agent', tags=['agent'])
service = AgentService()


@router.post('/ask', response_model=AgentResponse)
def ask_agent(request: AgentRequest) -> AgentResponse:
    return service.handle(request)
