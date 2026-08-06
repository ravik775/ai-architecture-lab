from string import Template

from app.ai.models import PromptOptions
from app.prompts.template import PromptTemplate

OUTPUT_FORMAT_TOKEN="OUTPUT_FORMAT"
class PromptRenderer:

    @staticmethod
    def render(template: PromptTemplate, variables: dict[str, str],  options: PromptOptions) -> str:
        rendered = Template(template.template).substitute(variables)
        if options.include_examples and template.examples:
            # Clean up indentation and format few-shot examples clearly
            examples_list = []
            for ex in template.examples:
                example_block = (
                    f"Example Input:\n{ex.input.strip()}\n\n"
                    f"Expected Output:\n{ex.output.strip()}"
                )
                examples_list.append(example_block)

            examples_str = "\n\n******\n".join(examples_list)
            # Properly separate few-shot examples from the actual request
            rendered = f"Examples:\n{examples_str}\n\n---\n\nActual Request:\n{rendered}\n"
        return rendered.strip()