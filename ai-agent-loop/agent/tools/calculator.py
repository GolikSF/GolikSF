"""Safe arithmetic calculator tool.

Deliberately does NOT use eval()/exec() on model-provided strings. Instead it
parses the expression into a Python AST and walks it, allowing only numeric
literals and a whitelist of arithmetic operators. This makes it safe to run
against untrusted, model-generated input.
"""

from __future__ import annotations

import ast
import operator

from pydantic import BaseModel, Field

from agent.tools.base import Tool, ToolResult

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalculatorError(ValueError):
    pass


def safe_eval(expression: str) -> float:
    """Evaluate a purely arithmetic expression safely."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError(f"Could not parse expression: {exc}") from exc

    def _eval(node: ast.AST):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise CalculatorError(f"Unsupported constant: {node.value!r}")
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
            left, right = _eval(node.left), _eval(node.right)
            try:
                return _ALLOWED_BINOPS[type(node.op)](left, right)
            except ZeroDivisionError as exc:
                raise CalculatorError("Division by zero") from exc
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
            return _ALLOWED_UNARYOPS[type(node.op)](_eval(node.operand))
        raise CalculatorError(f"Unsupported expression element: {type(node).__name__}")

    result = _eval(tree)
    if isinstance(result, complex) or (isinstance(result, float) and (result != result)):
        raise CalculatorError("Expression did not produce a real number")
    return result


class CalculatorInput(BaseModel):
    expression: str = Field(
        description="An arithmetic expression using + - * / // % ** and parentheses, e.g. '17 * 23.50 * 1.0825'."
    )


class CalculatorTool(Tool):
    name = "calculator"
    description = (
        "Evaluate an arithmetic expression (+ - * / // % ** and parentheses). "
        "Use this for any numeric computation instead of doing math yourself."
    )
    input_model = CalculatorInput

    def _execute(self, parsed_input: CalculatorInput) -> ToolResult:
        try:
            value = safe_eval(parsed_input.expression)
        except CalculatorError as exc:
            return ToolResult(success=False, error=str(exc))
        return ToolResult(success=True, output={"expression": parsed_input.expression, "result": value})
