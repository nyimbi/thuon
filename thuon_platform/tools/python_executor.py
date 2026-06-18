import sys
import subprocess
import tempfile
import os
import time
from typing import Any


class PythonExecutor:

	def execute(self, code: str, timeout: int = 30) -> dict[str, Any]:
		try:
			tmp_path = None
			start = time.monotonic()
			try:
				with tempfile.NamedTemporaryFile(suffix='.py', delete=False, mode='w') as tmp:
					tmp.write(code)
					tmp_path = tmp.name

				result = subprocess.run(
					[sys.executable, tmp_path],
					capture_output=True,
					text=True,
					timeout=timeout,
				)

				elapsed_ms = int((time.monotonic() - start) * 1000)

				stdout = result.stdout
				stderr = result.stderr
				truncated = len(stdout) > 10000 or len(stderr) > 10000
				stdout = stdout[:10000]
				stderr = stderr[:10000]

				return {
					'status': 'success',
					'stdout': stdout,
					'stderr': stderr,
					'returncode': result.returncode,
					'execution_time_ms': elapsed_ms,
					'truncated': truncated,
				}

			except subprocess.TimeoutExpired:
				elapsed_ms = int((time.monotonic() - start) * 1000)
				return {
					'status': 'error',
					'error': f'execution timed out after {timeout}s',
					'stdout': '',
					'stderr': '',
					'returncode': -1,
					'execution_time_ms': elapsed_ms,
					'truncated': False,
				}

			finally:
				if tmp_path and os.path.exists(tmp_path):
					os.unlink(tmp_path)

		except Exception as e:
			return {'status': 'error', 'error': str(e)}
