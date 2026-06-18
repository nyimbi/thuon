import time
from typing import Any

try:
	import psycopg2
	import psycopg2.extras
except ImportError:
	psycopg2 = None

from core.settings_manager import get_settings

settings = get_settings()

_READONLY_PREFIXES = ('select', 'with', 'explain')


class SQLExecutor:

	def __init__(self, data_handler=None):
		self.data_handler = data_handler

	def query(self, sql: str, params: dict = {}, readonly: bool = True, max_rows: int = 1000) -> dict[str, Any]:
		try:
			if readonly:
				first_word = sql.strip().split()[0].lower() if sql.strip() else ''
				if first_word not in _READONLY_PREFIXES:
					return {'status': 'error', 'error': 'Only SELECT queries allowed in readonly mode'}

			start = time.monotonic()

			# direct psycopg2 connection (data_handler silently swallows errors, so bypass it)
			if psycopg2 is None:
				return {'status': 'error', 'error': 'psycopg2-binary not installed. Run: uv add psycopg2-binary'}

			db_url = settings.get_setting('database.url', '')
			if not db_url:
				return {'status': 'error', 'error': 'Database not configured'}

			try:
				conn = psycopg2.connect(db_url)
				cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
				cur.execute(sql, params or None)
				raw_rows = cur.fetchmany(max_rows + 1)
				elapsed_ms = int((time.monotonic() - start) * 1000)
				columns = [desc[0] for desc in cur.description] if cur.description else []
				truncated = len(raw_rows) > max_rows
				rows = [dict(r) for r in raw_rows[:max_rows]]
				cur.close()
				conn.close()
				return {
					'status': 'success',
					'sql': sql[:200],
					'columns': columns,
					'rows': rows,
					'count': len(rows),
					'truncated': truncated,
					'execution_time_ms': elapsed_ms,
				}
			except Exception as e:
				return {'status': 'error', 'error': str(e)}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}
