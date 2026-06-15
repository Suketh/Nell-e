import ast
import operator
import re


_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_MAX_NODES = 40
_MAX_ABS_VALUE = 10**100
_MAX_EXPONENT = 12


def extract_expression(text: str) -> str:
    raw = str(text or "").strip()
    patterns = [
        r"^(?:what is|what's|calculate|compute|work out|räkna ut|beräkna)\s+(.+?)[?!.]*$",
        r"^(.+?)\s*(?:equals|är lika med)[?!.]*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, raw, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if re.fullmatch(r"[\d\s()+\-*/%.]+", candidate):
                return candidate
    return ""


def evaluate_expression(expression: str) -> str:
    text = str(expression or "").strip()
    if not text:
        raise ValueError("No expression provided.")
    tree = ast.parse(text, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
        raise ValueError("Expression is too complex.")
    value = _eval(tree.body)
    if abs(value) > _MAX_ABS_VALUE:
        raise ValueError("Result is too large.")
    if isinstance(value, float):
        rendered = f"{value:.10f}".rstrip("0").rstrip(".")
        return rendered or "0"
    return str(value)


def _eval(node):
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left = _eval(node.left)
        right = _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError("Exponent is too large.")
        value = _BINARY_OPS[type(node.op)](left, right)
        if abs(value) > _MAX_ABS_VALUE:
            raise ValueError("Intermediate result is too large.")
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    raise ValueError("Unsupported expression.")
