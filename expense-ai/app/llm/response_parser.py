from pydantic import ValidationError
from app.ai.models import ProviderResponse, TResponse
from app.exceptions import StructuredOutputError


class ResponseParser:

    def parse(self, response: ProviderResponse[TResponse], response_model: type[TResponse]) -> TResponse:
        if isinstance(response.parsed, response_model):
            return response.parsed
        if response.content is None:
            raise StructuredOutputError("Provider returned neither parsed object nor JSON.")
        try:
            return response_model.model_validate_json(response.content)
        except ValidationError as ex:
                raise StructuredOutputError("Invalid structured output.") from ex