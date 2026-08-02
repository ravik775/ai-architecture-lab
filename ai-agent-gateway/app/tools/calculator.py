import ast
import operator as op
from typing import Any

from app.tools.base import Tool


_ALLOWED_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}


class SafeCalculatorTool(Tool):
    name = 'calculator'
    description = 'Safely evaluates basic arithmetic expressions.'

    def run(self, expression: str, **_: Any) -> dict[str, Any]:
        value = self._eval(ast.parse(expression, mode='eval').body)
        return {'expression': expression, 'result': value}

    def _eval(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
            return _ALLOWED_OPERATORS[type(node.op)](self._eval(node.left), self._eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
            return _ALLOWED_OPERATORS[type(node.op)](self._eval(node.operand))
        raise ValueError('Only basic arithmetic is allowed.')
