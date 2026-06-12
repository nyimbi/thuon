# capabilities/financial_forecasting_analyst.py

import json
import re
import statistics
from core.ai_engine import AIModel
from core.data_handler import DatabaseHandler


def _compute_stats(rows: list[dict]) -> dict:
	"""
	Compute descriptive statistics on numeric columns from a list of row dicts.
	Returns a dict of {column: {mean, median, stdev, min, max, count, cagr}}.
	"""
	if not rows:
		return {}
	# Collect numeric columns
	numeric: dict[str, list[float]] = {}
	for row in rows:
		for k, v in row.items():
			try:
				numeric.setdefault(k, []).append(float(v))
			except (TypeError, ValueError):
				pass

	stats: dict = {}
	for col, values in numeric.items():
		if len(values) < 2:
			continue
		col_stats: dict = {
			'count':  len(values),
			'mean':   round(statistics.mean(values), 4),
			'median': round(statistics.median(values), 4),
			'min':    min(values),
			'max':    max(values),
		}
		if len(values) >= 2:
			col_stats['stdev'] = round(statistics.stdev(values), 4)
		# Simple CAGR if first/last are positive
		if values[0] > 0 and values[-1] > 0 and len(values) >= 2:
			n = len(values) - 1
			cagr = (values[-1] / values[0]) ** (1 / n) - 1
			col_stats['cagr'] = round(cagr, 4)
		stats[col] = col_stats
	return stats


class FinancialForecastingAnalyst:
	def __init__(self, ai_engine: AIModel, data_handler: DatabaseHandler = None):
		self.ai_engine = ai_engine
		self.data_handler = data_handler

	def forecast_financial_performance(
		self,
		financial_data_table: str,
		forecast_metrics: list = ['revenue_forecast', 'profit_margin_forecast', 'cash_flow_forecast'],
		forecast_period_years: int = 5,
	) -> dict:
		historical_data: list = []
		if self.data_handler:
			try:
				historical_data = self.data_handler.fetch_data(financial_data_table) or []
			except Exception:
				pass

		# Statistical computation on real data
		computed_stats = _compute_stats(historical_data) if historical_data else {}

		data_summary = json.dumps(historical_data[:20], indent=2) if historical_data else f"No historical data from {financial_data_table}"
		stats_summary = json.dumps(computed_stats, indent=2) if computed_stats else 'No computable statistics.'
		metrics_str   = ', '.join(forecast_metrics)

		prompt = (
			f"You are a financial analyst. Forecast financial performance based on historical data and computed statistics.\n\n"
			f"Forecast Period: {forecast_period_years} years\nMetrics: {metrics_str}\n\n"
			f"Historical data sample:\n{data_summary}\n\n"
			f"Computed statistics (mean, median, stdev, CAGR per column):\n{stats_summary}\n\n"
			f"Return JSON with keys: forecast_summary, assumptions (list), "
			f"forecasts (object per metric with: year_1, year_2, year_3, year_4, year_5, "
			f"growth_rate, confidence_interval), scenario_analysis (object with: optimistic, base, pessimistic), "
			f"key_drivers (list), risks_to_forecast (list), recommended_actions (list), "
			f"break_even_analysis, cash_runway_months."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				result = json.loads(match.group())
				if computed_stats:
					result['computed_statistics'] = computed_stats
				return result
		except Exception:
			pass
		result = {
			'result':      response,
			'metrics':     forecast_metrics,
			'period_years': forecast_period_years,
			'status':      'success',
		}
		if computed_stats:
			result['computed_statistics'] = computed_stats
		return result
