import uuid
import base64
from typing import Any


class ChartGenerator:

	def generate(self, chart_type: str, data: dict, title: str = '', xlabel: str = '', ylabel: str = '', output_path: str = '') -> dict[str, Any]:
		try:
			try:
				import matplotlib
				matplotlib.use('Agg')
				import matplotlib.pyplot as plt
			except ImportError:
				return {'status': 'error', 'error': 'Package matplotlib not installed. Run: uv add matplotlib'}

			plt.style.use('dark_background')
			fig, ax = plt.subplots(figsize=(10, 6), dpi=100)

			if chart_type == 'line':
				labels = data.get('labels', [])
				for ds in data.get('datasets', []):
					ax.plot(labels, ds['data'], label=ds.get('label', ''))
				if any(ds.get('label') for ds in data.get('datasets', [])):
					ax.legend()

			elif chart_type == 'bar':
				labels = data.get('labels', [])
				datasets = data.get('datasets', [])
				import numpy as np
				x = np.arange(len(labels))
				width = 0.8 / max(len(datasets), 1)
				for i, ds in enumerate(datasets):
					offset = (i - len(datasets) / 2 + 0.5) * width
					ax.bar(x + offset, ds['data'], width, label=ds.get('label', ''))
				ax.set_xticks(x)
				ax.set_xticklabels(labels)
				if any(ds.get('label') for ds in datasets):
					ax.legend()

			elif chart_type == 'pie':
				labels = data.get('labels', [])
				values = data.get('values', [])
				ax.pie(values, labels=labels, autopct='%1.1f%%')

			elif chart_type == 'scatter':
				if 'points' in data:
					xs = [p['x'] for p in data['points']]
					ys = [p['y'] for p in data['points']]
				else:
					xs = data.get('x', [])
					ys = data.get('y', [])
				ax.scatter(xs, ys)

			elif chart_type == 'histogram':
				values = data.get('values', [])
				bins = data.get('bins', 20)
				ax.hist(values, bins=bins)

			else:
				plt.close(fig)
				return {'status': 'error', 'error': f'Unknown chart_type: {chart_type}. Supported: line, bar, pie, scatter, histogram'}

			if title:
				ax.set_title(title)
			if xlabel:
				ax.set_xlabel(xlabel)
			if ylabel:
				ax.set_ylabel(ylabel)

			path = output_path if output_path else f'/tmp/thuon_chart_{uuid.uuid4().hex}.png'
			plt.savefig(path, bbox_inches='tight', facecolor='#1c1917')
			plt.close(fig)

			with open(path, 'rb') as f:
				b64 = base64.b64encode(f.read()).decode()

			return {
				'status': 'success',
				'chart_type': chart_type,
				'title': title,
				'image_path': path,
				'image_base64': b64,
			}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}
