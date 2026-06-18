import ast
import math
from typing import Any


def _npv(rate: float, cashflows: list) -> float:
	return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))


def _irr(cashflows: list, max_iter: int = 1000, tol: float = 1e-6) -> float:
	# Newton-Raphson: find rate where NPV == 0
	rate = 0.1
	for _ in range(max_iter):
		npv_val = sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))
		dnpv = sum(-t * cf / (1 + rate) ** (t + 1) for t, cf in enumerate(cashflows))
		if dnpv == 0:
			break
		new_rate = rate - npv_val / dnpv
		if abs(new_rate - rate) < tol:
			return new_rate
		rate = new_rate
	return rate


def _compound(principal: float, rate: float, n: float, t: float) -> float:
	return principal * (1 + rate / n) ** (n * t)


def _pmt(rate: float, nper: float, pv: float) -> float:
	# Standard annuity payment formula
	if rate == 0:
		return -pv / nper
	return rate * pv / (1 - (1 + rate) ** (-nper))


_SAFE_LOCALS: dict[str, Any] = {
	'abs': abs, 'round': round, 'min': min, 'max': max, 'sum': sum,
	'sqrt': math.sqrt, 'log': math.log, 'log10': math.log10,
	'exp': math.exp, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
	'pi': math.pi, 'e': math.e, 'ceil': math.ceil, 'floor': math.floor,
	'factorial': math.factorial,
	'npv': _npv, 'irr': _irr, 'compound': _compound, 'pmt': _pmt,
}

_ALLOWED_OPS = (
	ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
	ast.FloorDiv, ast.Mod, ast.USub, ast.UAdd,
)

# nodes that are valid structural wrappers (no security surface)
_STRUCTURAL_NODES = (
	ast.Expression, ast.Load, ast.List, ast.Tuple,
	ast.keyword,
)


def _check_node(node: ast.AST, allowed_names: set[str]) -> None:
	# operators are not AST statement nodes — allow them when encountered as children
	if isinstance(node, _ALLOWED_OPS):
		return
	if isinstance(node, _STRUCTURAL_NODES):
		for child in ast.iter_child_nodes(node):
			_check_node(child, allowed_names)
		return
	if isinstance(node, (ast.BinOp, ast.UnaryOp)):
		if not isinstance(node.op, _ALLOWED_OPS):
			raise ValueError(f'Disallowed operator: {type(node.op).__name__}')
		for child in ast.iter_child_nodes(node):
			_check_node(child, allowed_names)
		return
	if isinstance(node, (ast.Num, ast.Constant)):
		return
	if isinstance(node, ast.Name):
		if node.id not in allowed_names:
			raise ValueError(f'Unknown name: {node.id!r}')
		return
	if isinstance(node, ast.Call):
		# only allow calls to names present in allowed_names; no attribute calls
		if not isinstance(node.func, ast.Name):
			raise ValueError('Only direct function calls allowed, not attribute calls')
		if node.func.id not in allowed_names:
			raise ValueError(f'Unknown function: {node.func.id!r}')
		for child in ast.iter_child_nodes(node):
			_check_node(child, allowed_names)
		return
	if isinstance(node, ast.Attribute):
		raise ValueError('Attribute access not allowed')
	raise ValueError(f'Disallowed AST node: {type(node).__name__}')


class Calculator:

	def calculate(self, expression: str, variables: dict = {}) -> dict[str, Any]:
		try:
			# substitute variables via safe_locals so no string injection risk
			local_ns = dict(_SAFE_LOCALS)
			for k, v in variables.items():
				local_ns[k] = v

			tree = ast.parse(expression.strip(), mode='eval')
			_check_node(tree, set(local_ns.keys()))

			result = eval(compile(tree, '<expr>', 'eval'), {'__builtins__': {}}, local_ns)  # noqa: S307

			if isinstance(result, (int, float)):
				result_formatted = f'{result:,.6g}'
			else:
				result_formatted = str(result)

			return {
				'status': 'success',
				'expression': expression,
				'result': result,
				'result_formatted': result_formatted,
			}
		except Exception as e:
			return {'status': 'error', 'error': str(e)}
