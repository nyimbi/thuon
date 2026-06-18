import hashlib
import os
import tempfile
from typing import Any


class PDFExtractor:

	def extract(self, source: str, max_pages: int = 0, page_range: str = '') -> dict[str, Any]:
		try:
			try:
				from pypdf import PdfReader
			except ImportError:
				return {'status': 'error', 'error': 'Package pypdf not installed. Run: uv add pypdf'}

			pdf_path = source
			tmp_path = None

			# download URL to /tmp/ before extracting
			if source.startswith('http://') or source.startswith('https://'):
				try:
					import requests
				except ImportError:
					return {'status': 'error', 'error': 'Package requests not installed. Run: uv add requests'}
				url_hash = hashlib.md5(source.encode()).hexdigest()
				tmp_path = f'/tmp/thuon_pdf_{url_hash}.pdf'
				resp = requests.get(source, timeout=60)
				resp.raise_for_status()
				with open(tmp_path, 'wb') as f:
					f.write(resp.content)
				pdf_path = tmp_path

			try:
				reader = PdfReader(pdf_path)
				total_pages = len(reader.pages)

				# determine which page indices to extract (0-indexed internally)
				if page_range:
					if '-' in page_range:
						parts = page_range.split('-', 1)
						start = int(parts[0]) - 1
						end = int(parts[1]) - 1
					else:
						start = int(page_range) - 1
						end = start
					indices = list(range(max(0, start), min(total_pages - 1, end) + 1))
				elif max_pages and max_pages > 0:
					indices = list(range(min(max_pages, total_pages)))
				else:
					indices = list(range(total_pages))

				pages_out: list[dict[str, Any]] = []
				combined_parts: list[str] = []

				for i in indices:
					text = reader.pages[i].extract_text() or ''
					word_count = len(text.split()) if text.strip() else 0
					pages_out.append({
						'page_num': i + 1,
						'text': text,
						'word_count': word_count,
					})
					combined_parts.append(text)

				full_text = '\n'.join(combined_parts)
				total_words = sum(p['word_count'] for p in pages_out)

				raw_meta = reader.metadata or {}
				metadata: dict[str, Any] = {
					'title': raw_meta.get('/Title') or raw_meta.get('title'),
					'author': raw_meta.get('/Author') or raw_meta.get('author'),
					'subject': raw_meta.get('/Subject') or raw_meta.get('subject'),
					'creator': raw_meta.get('/Creator') or raw_meta.get('creator'),
					'num_pages': total_pages,
				}

				truncated = len(indices) < total_pages

				return {
					'status': 'success',
					'source': source,
					'text': full_text,
					'pages': pages_out,
					'metadata': metadata,
					'page_count': len(indices),
					'word_count': total_words,
					'truncated': truncated,
				}
			finally:
				if tmp_path and os.path.exists(tmp_path):
					os.unlink(tmp_path)

		except Exception as e:
			return {'status': 'error', 'error': str(e)}
