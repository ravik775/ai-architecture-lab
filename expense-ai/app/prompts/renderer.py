from string import Template
from app.prompts.template import PromptTemplate


class PromptRenderer:
    @staticmethod
    def render(template: PromptTemplate, variables: dict[str, str]) -> str:
        rendered = Template(template.template).substitute(variables)

        if template.examples:
            # Clean up indentation and format few-shot examples clearly
            examples_list = []
            for ex in template.examples:
                example_block = (
                    f"Example Input:\n{ex.input.strip()}\n\n"
                    f"Expected Output:\n{ex.output.strip()}"
                )
                examples_list.append(example_block)

            examples_str = "\n\n---\n\n".join(examples_list)

            # Properly separate few-shot examples from the actual request
            rendered = (
                f"{examples_str}\n\n"
                f"---"
                f"\n\nActual Request:\n{rendered}"
            )

        return rendered.strip()