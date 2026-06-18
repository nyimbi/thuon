import os
from pathlib import Path
from typing import Any


class WhisperTranscriber:

	def transcribe(self, file_path: str, language: str = '', model_size: str = 'base') -> dict[str, Any]:
		try:
			try:
				import whisper
			except ImportError:
				return {'status': 'error', 'error': 'openai-whisper not installed. Run: uv add openai-whisper'}

			if not os.path.exists(file_path):
				return {'status': 'error', 'error': f'File not found: {file_path}'}

			model = whisper.load_model(model_size)
			options = {} if not language else {'language': language}
			result = model.transcribe(file_path, **options)

			segments = [
				{'start': float(s['start']), 'end': float(s['end']), 'text': str(s['text'])}
				for s in result.get('segments', [])
			]

			# derive duration from last segment's end time
			duration = float(segments[-1]['end']) if segments else 0.0

			return {
				'status': 'success',
				'file_path': file_path,
				'text': result['text'],
				'language': result['language'],
				'segments': segments,
				'duration_seconds': duration,
				'model_size': model_size,
			}
		except Exception as e:
			return {'status': 'error', 'error': str(e)}
