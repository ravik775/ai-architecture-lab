from app.tools.calculator import SafeCalculatorTool


def test_calculator_addition():
    tool = SafeCalculatorTool()
    assert tool.run(expression='100 + 200')['result'] == 300


def test_calculator_precedence():
    tool = SafeCalculatorTool()
    assert tool.run(expression='100 + 200 * 2')['result'] == 500
