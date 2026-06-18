from pathlib import Path
from typing import Any


class FileWriter:

	def write(self, file_path: str, content: str, mode: str = 'w', create_dirs: bool = True) -> dict[str, Any]:
		try:
			path = Path(file_path)
			if create_dirs:
				path.parent.mkdir(parents=True, exist_ok=True)
			with open(path, mode, encoding='utf-8') as f:
				f.write(content)
			return {
				'status': 'success',
				'path': str(path.resolve()),
				'size_bytes': path.stat().st_size,
				'mode': mode,
			}
		except Exception as e:
			return {'status': 'error', 'error': str(e)}

	def read_file(self, file_path: str, max_chars: int = 50000) -> dict[str, Any]:
		try:
			path = Path(file_path)
			size_bytes = path.stat().st_size
			with open(path, 'r', encoding='utf-8') as f:
				content = f.read(max_chars)
			truncated = len(content) == max_chars and size_bytes > max_chars
			return {
				'status': 'success',
				'path': str(path.resolve()),
				'content': content,
				'size_bytes': size_bytes,
				'truncated': truncated,
			}
		except Exception as e:
			return {'status': 'error', 'error': str(e)}

	def list_files(self, directory: str, pattern: str = '*', recursive: bool = False) -> dict[str, Any]:
		try:
			path = Path(directory)
			glob_fn = path.rglob if recursive else path.glob
			files = []
			for item in glob_fn(pattern):
				files.append({
					'name': item.name,
					'path': str(item.resolve()),
					'size_bytes': item.stat().st_size if item.exists() else 0,
					'is_dir': item.is_dir(),
				})
			return {
				'status': 'success',
				'directory': str(path.resolve()),
				'files': files,
				'count': len(files),
			}
		except Exception as e:
			return {'status': 'error', 'error': str(e)}

	def delete_file(self, file_path: str) -> dict[str, Any]:
		try:
			path = Path(file_path)
			resolved = str(path.resolve())
			path.unlink()
			return {
				'status': 'success',
				'path': resolved,
				'deleted': True,
			}
		except Exception as e:
			return {'status': 'error', 'error': str(e)}
