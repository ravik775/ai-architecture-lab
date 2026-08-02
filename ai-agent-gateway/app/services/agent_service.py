    from app.llm.client import LLMClient, LiteLLMClient
    from app.models.schemas import AgentRequest, AgentResponse, Intent, ToolCallRecord
    from app.services.intent_router_o import IntentRouter
    from app.tools.registry import ToolRegistry


    class AgentService:
        def __init__(self, llm_client: LLMClient | None = None) -> None:
            self.llm = llm_client or LiteLLMClient()
            self.router = IntentRouter(llm_client=self.llm, confidence_threshold=0.75)
            self.tools = ToolRegistry()

        async def handle(self, request: AgentRequest) -> AgentResponse:
            decision = await self.router.classify(request.message)

            if decision.intent == Intent.weather:
                city = decision.city or self.router.extract_city(request.message)

                output = self.tools.get("weather").run(city=city)

                answer = self._summarize_tool_result(
                    request.message,
                    output,
                    request.preferred_model,
                )

                return AgentResponse(
                    answer=answer,
                    intent=decision.intent,
                    model=request.preferred_model,
                    tool_calls=[
                        ToolCallRecord(
                            tool_name="weather",
                            input={"city": city},
                            output=output,
                        )
                    ],
                    sources=["https://open-meteo.com/"],
                )

            if decision.intent == Intent.calculation:
                expression = decision.math_expression or self.router.extract_math_expression(
                    request.message
                )

                output = self.tools.get("calculator").run(expression=expression)

                return AgentResponse(
                    answer=f"The result is {output['result']}.",
                    intent=decision.intent,
                    model=None,
                    tool_calls=[
                        ToolCallRecord(
                            tool_name="calculator",
                            input={"expression": expression},
                            output=output,
                        )
                    ],
                )

            if decision.intent == Intent.internet:
                query = decision.search_query or request.message

                output = self.tools.get("web_search").run(query=query, max_results=5)

                answer = self._answer_from_search(
                    request.message,
                    output,
                    request.preferred_model,
                )

                sources = [
                    result["href"]
                    for result in output.get("results", [])
                    if result.get("href")
                ]

                return AgentResponse(
                    answer=answer,
                    intent=decision.intent,
                    model=request.preferred_model,
                    tool_calls=[
                        ToolCallRecord(
                            tool_name="web_search",
                            input={"query": query},
                            output=output,
                        )
                    ],
                    sources=sources,
                )

            answer = self.llm.generate(
                messages=[
                    {
                        "role": "user",
                        "content": request.message,
                    }
                ],
                model=request.preferred_model,
            )

            return AgentResponse(
                answer=answer,
                intent=decision.intent,
                model=request.preferred_model,
            )

        def _summarize_tool_result(
            self,
            user_question: str,
            tool_output: dict,
            model: str | None,
        ) -> str:
            return self.llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "You summarize tool output into a concise user answer.",
                    },
                    {
                        "role": "user",
                        "content": f"Question: {user_question}\nTool output: {tool_output}",
                    },
                ],
                model=model,
            )

        def _answer_from_search(
            self,
            user_question: str,
            search_output: dict,
            model: str | None,
        ) -> str:
            return self.llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Answer using only the provided search results. "
                            "If unclear, say the results are insufficient."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Question: {user_question}\nSearch results: {search_output}",
                    },
                ],
                model=model,
            )