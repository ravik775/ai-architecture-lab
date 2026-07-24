from abc import ABC
from string import Template

from app.prompts.template import PromptTemplate


class PromptRenderer:

    @staticmethod
    def render(template: PromptTemplate,
               variables: dict[str, str]) -> str:
        return Template(template.template).safe_substitute(variables)
