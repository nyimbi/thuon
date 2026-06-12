# capabilities/process_optimization_analyst.py

import json
import re
import statistics
from core.ai_engine import AIModel
from core.data_handler import DatabaseHandler


def _compute_process_stats(rows: list[dict]) -> dict:
	if not rows:
		return {}
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
		mean = statistics.mean(values)
		std  = statistics.stdev(values)
		stats[col] = {
			'count':     len(values),
			'mean':      round(mean, 4),
			'median':    round(statistics.median(values), 4),
			'stdev':     round(std, 4),
			'min':       min(values),
			'max':       max(values),
			'range':     round(max(values) - min(values), 4),
			'cv_percent': round(std / abs(mean) * 100, 2) if mean != 0 else None,
		}
	return stats


class ProcessOptimizationAnalyst:
	def __init__(self, ai_engine: AIModel, data_handler: DatabaseHandler = None):
		self.ai_engine    = ai_engine
		self.data_handler = data_handler

	def analyze_process_efficiency(
		self,
		process_description: str,
		process_data_table: str,
		efficiency_metrics: list = ['cycle_time', 'resource_utilization', 'error_rate'],
	) -> dict:
		process_data: list = []
		if self.data_handler:
			try:
				process_data = self.data_handler.fetch_data(process_data_table) or []
			except Exception:
				pass

		computed_stats = _compute_process_stats(process_data)
		data_summary   = json.dumps(process_data[:15], indent=2) if process_data else f"No data from {process_data_table}"
		stats_summary  = json.dumps(computed_stats, indent=2) if computed_stats else 'No computable statistics.'
		metrics_str    = ', '.join(efficiency_metrics)

		prompt = (
			f"You are a process improvement expert using Lean and Six Sigma methodologies.\n\n"
			f"Process: {process_description}\nMetrics to analyze: {metrics_str}\n\n"
			f"Process data sample:\n{data_summary}\n\n"
			f"Computed process statistics (mean, stdev, CV%, range per column):\n{stats_summary}\n\n"
			f"High CV% signals unstable process steps — key targets for improvement.\n\n"
			f"Return JSON with keys: process_summary, current_performance (object per metric with: "
			f"current_value, benchmark, gap), bottlenecks (list with: step, issue, impact, cv_percent_if_available), "
			f"waste_identified (list with: waste_type, description, estimated_cost), "
			f"root_causes (list), improvement_opportunities (list with: opportunity, methodology, "
			f"estimated_improvement, implementation_effort, priority), "
			f"quick_wins (list), implementation_roadmap (phases list), "
			f"estimated_efficiency_gain_percent, roi_estimate."
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
		result = {'result': response, 'process': process_description, 'metrics': efficiency_metrics, 'status': 'success'}
		if computed_stats:
			result['computed_statistics'] = computed_stats
		return result
