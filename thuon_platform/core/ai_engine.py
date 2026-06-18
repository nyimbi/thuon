# core/ai_engine.py

import json
import re
from abc import ABC, abstractmethod
from core.settings_manager import get_settings


class AIModel(ABC):
	@abstractmethod
	def __init__(self, model_name: str):
		self.model_name = model_name

	@abstractmethod
	def generate_text(self, prompt: str, generation_parameters: dict = {}) -> str:
		pass

	@abstractmethod
	def analyze_sentiment(self, text: str) -> str:
		pass

	@abstractmethod
	def extract_entities(self, text: str, entity_types: list) -> dict:
		pass

	@abstractmethod
	def summarize_text(self, text: str, length: str = 'medium') -> str:
		pass

	@abstractmethod
	def translate_text(self, text: str, target_language: str) -> str:
		pass


class OllamaModel(AIModel):
	def __init__(self, model_name: str | None = None, base_url: str | None = None):
		settings = get_settings()
		resolved_model = model_name or settings.get_setting('ollama.model', 'deepseek-r1')
		resolved_url = base_url or settings.get_setting('ollama.endpoint', 'http://localhost:11434')
		super().__init__(resolved_model)
		from langchain_ollama import OllamaLLM
		self.llm = OllamaLLM(model=resolved_model, base_url=resolved_url)

	def generate_text(self, prompt: str, generation_parameters: dict = {}) -> str:
		return self.llm.invoke(prompt)

	def generate_stream(self, prompt: str):
		"""Yield tokens as they are produced by the model."""
		for chunk in self.llm.stream(prompt):
			yield chunk

	def analyze_sentiment(self, text: str) -> str:
		prompt = (
			f"Classify the sentiment of the following text as exactly one of: "
			f"'positive', 'negative', or 'neutral'. Reply with only the label.\n\nText: {text}\nSentiment:"
		)
		return self.generate_text(prompt).strip().lower()

	def extract_entities(self, text: str, entity_types: list) -> dict:
		types_str = ', '.join(entity_types)
		prompt = (
			f"Extract the following entity types from the text: {types_str}.\n"
			f"Return a JSON object where each key is an entity type and the value is a list of extracted entities.\n\n"
			f"Text: {text}\nJSON:"
		)
		response = self.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			return json.loads(match.group()) if match else {t: [] for t in entity_types}
		except Exception:
			return {t: [] for t in entity_types}

	def summarize_text(self, text: str, length: str = 'medium') -> str:
		word_counts = {'short': 100, 'medium': 300, 'long': 600}
		words = word_counts.get(length, 300)
		prompt = f"Summarize the following text in approximately {words} words:\n\n{text}\n\nSummary:"
		return self.generate_text(prompt).strip()

	def translate_text(self, text: str, target_language: str) -> str:
		prompt = f"Translate the following text to {target_language}. Reply with only the translation.\n\nText: {text}\n\nTranslation:"
		return self.generate_text(prompt).strip()


class OllamaVisionModel:
	"""
	Multimodal vision+language model via Ollama.

	Recommended models (pull before use):
	  ollama pull minicpm-v:4.5   # fast, great OCR + chart reading, ~4GB
	  ollama pull minicpm-v:4.6   # same + better multilingual OCR, ~5GB
	  ollama pull gemma4           # stronger reasoning over complex scenes, ~8GB

	All run locally — no Anthropic API key needed.
	"""

	def __init__(self, model_name: str | None = None, base_url: str | None = None):
		settings = get_settings()
		resolved_model = (
			model_name
			or settings.get_setting('ollama.vision_model')
			or 'minicpm-v:4.5'
		)
		resolved_url = base_url or settings.get_setting('ollama.endpoint', 'http://localhost:11434')
		self.model_name = resolved_model
		from langchain_ollama import ChatOllama
		self.llm = ChatOllama(model=resolved_model, base_url=resolved_url)

	# ── Core primitives ───────────────────────────────────────────────────

	def analyze_bytes(self, image_bytes: bytes, prompt: str, mime: str = 'image/png') -> str:
		"""Analyze raw image bytes with a text prompt."""
		import base64
		from langchain_core.messages import HumanMessage
		b64 = base64.standard_b64encode(image_bytes).decode()
		message = HumanMessage(content=[
			{'type': 'text',      'text': prompt},
			{'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}},
		])
		response = self.llm.invoke([message])
		return response.content if hasattr(response, 'content') else str(response)

	def analyze_image(self, image_path: str, prompt: str) -> str:
		"""Analyze an image file with a text prompt."""
		import mimetypes
		mime = mimetypes.guess_type(image_path)[0] or 'image/png'
		with open(image_path, 'rb') as f:
			return self.analyze_bytes(f.read(), prompt, mime)

	def analyze_url(self, url: str, prompt: str) -> str:
		"""Download an image from a URL and analyze it."""
		import requests
		r = requests.get(url, timeout=15)
		r.raise_for_status()
		mime = r.headers.get('content-type', 'image/png').split(';')[0]
		return self.analyze_bytes(r.content, prompt, mime)

	# ── High-level task methods ───────────────────────────────────────────

	def describe(self, image_path: str) -> str:
		"""General description of what's in an image."""
		return self.analyze_image(
			image_path,
			'Describe this image in detail. Include all visible text, objects, layout, and context.',
		)

	def extract_text(self, image_path: str) -> str:
		"""OCR — extract all visible text from an image or document scan."""
		return self.analyze_image(
			image_path,
			'Extract all text from this image exactly as it appears. '
			'Preserve formatting, headings, and structure. Return only the extracted text.',
		)

	def analyze_chart(self, image_path: str) -> dict:
		"""
		Extract structured data from a chart or graph.
		Returns: {chart_type, title, x_axis, y_axis, data_points, key_insights, raw_values}
		"""
		import json, re
		prompt = (
			'Analyze this chart or graph. Extract all data precisely.\n\n'
			'Return JSON with keys: chart_type, title, x_axis (label + values list), '
			'y_axis (label + unit + range), data_series (list with: name, values list), '
			'key_insights (list of 3-5 observations), trend (up/down/flat/mixed).'
		)
		response = self.analyze_image(image_path, prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'raw_description': response, 'status': 'parsed_as_text'}

	def analyze_document_page(self, image_path: str) -> dict:
		"""
		OCR + structure extraction from a scanned document page.
		Returns: {title, sections, tables, key_clauses, metadata}
		"""
		import json, re
		prompt = (
			'This is a scanned document page. Extract its full content and structure.\n\n'
			'Return JSON with keys: title, document_type, sections (list with: heading, content), '
			'tables (list with: headers, rows), key_clauses (list of important statements), '
			'dates_mentioned (list), parties_mentioned (list), page_number_if_visible.'
		)
		response = self.analyze_image(image_path, prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'raw_text': response, 'status': 'parsed_as_text'}

	def analyze_screenshot(self, image_path: str, question: str = '') -> dict:
		"""
		Analyze a screenshot of a webpage or application UI.
		Returns: {page_title, main_content, navigation, key_data_points, answer_to_question}
		"""
		import json, re
		base_prompt = (
			'This is a screenshot of a web page or application. '
			'Extract all visible text and data.\n\n'
		)
		if question:
			base_prompt += f'Also answer this specific question: {question}\n\n'
		base_prompt += (
			'Return JSON with keys: page_title, main_content (text), '
			'data_tables (list), key_numbers (list with: label, value, unit), '
			'navigation_items (list), ' + (f'answer (to the question above)' if question else 'summary') + '.'
		)
		response = self.analyze_image(image_path, base_prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'raw_content': response, 'status': 'parsed_as_text'}

	def compare_images(self, image_path_a: str, image_path_b: str, aspect: str = '') -> dict:
		"""
		Compare two images side-by-side using a two-call approach
		(Ollama doesn't support multi-image in one call on all models).
		"""
		desc_a = self.describe(image_path_a)
		desc_b = self.describe(image_path_b)
		import json, re
		prompt = (
			f"Compare these two image descriptions"
			f"{' focusing on: ' + aspect if aspect else ''}.\n\n"
			f"Image A: {desc_a}\n\nImage B: {desc_b}\n\n"
			f"Return JSON with keys: similarities (list), differences (list), "
			f"recommendation (which is better and why)."
		)
		# Text-only comparison after descriptions are extracted
		from langchain_core.messages import HumanMessage
		response = self.llm.invoke([HumanMessage(content=prompt)])
		text = response.content if hasattr(response, 'content') else str(response)
		try:
			match = re.search(r'\{.*\}', text, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'comparison': text}


def screenshot_url(url: str, output_path: str = '/tmp/thuon_screenshot.png') -> str:
	"""
	Take a screenshot of a URL using Playwright (headless Chromium).
	Returns the path to the saved PNG.
	Requires: uv add playwright && playwright install chromium
	"""
	from playwright.sync_api import sync_playwright
	with sync_playwright() as p:
		browser = p.chromium.launch(headless=True)
		page    = browser.new_page(viewport={'width': 1280, 'height': 900})
		page.goto(url, wait_until='networkidle', timeout=30000)
		page.screenshot(path=output_path, full_page=False)
		browser.close()
	return output_path


class LiteLLMModel(AIModel):
	"""
	Route requests through a LiteLLM proxy (e.g. the ml server at 62.169.25.77).
	Falls back to OllamaModel on import error or connection failure.

	config.yaml keys used:
	  litellm.api_base      — proxy URL, e.g. http://62.169.25.77:4000
	  litellm.model         — default model, e.g. openai/gpt-4o
	  litellm.api_key       — proxy API key (optional)
	  litellm.timeout       — seconds (default 120)
	  litellm.max_retries   — default 2
	"""

	def __init__(
		self,
		model_name: str | None = None,
		api_base: str | None = None,
		api_key: str | None = None,
	):
		settings = get_settings()
		resolved_model = (
			model_name
			or settings.get_setting('litellm.model', 'openai/gpt-4o-mini')
		)
		super().__init__(resolved_model)
		self._api_base    = api_base or settings.get_setting('litellm.api_base', '')
		self._api_key     = api_key  or settings.get_setting('litellm.api_key', 'no-key')
		self._timeout     = int(settings.get_setting('litellm.timeout', 120))
		self._max_retries = int(settings.get_setting('litellm.max_retries', 2))
		try:
			import litellm as _ll
			self._ll = _ll
		except ImportError:
			self._ll = None

	def _call(self, messages: list[dict], **kw) -> str:
		if self._ll is None:
			raise RuntimeError('litellm not installed — run: uv add litellm')
		kwargs: dict = dict(
			model=self.model_name,
			messages=messages,
			timeout=self._timeout,
			num_retries=self._max_retries,
			**kw,
		)
		if self._api_base:
			kwargs['api_base'] = self._api_base
		if self._api_key:
			kwargs['api_key'] = self._api_key
		resp = self._ll.completion(**kwargs)
		return resp.choices[0].message.content or ''

	def generate_text(self, prompt: str, generation_parameters: dict = {}) -> str:
		return self._call(
			[{'role': 'user', 'content': prompt}],
			**{k: v for k, v in generation_parameters.items()
			   if k in ('temperature', 'max_tokens', 'top_p', 'stop')},
		)

	def generate_stream(self, prompt: str):
		"""Yield token chunks from the LiteLLM proxy."""
		if self._ll is None:
			yield self.generate_text(prompt)
			return
		kwargs: dict = dict(
			model=self.model_name,
			messages=[{'role': 'user', 'content': prompt}],
			stream=True,
			timeout=self._timeout,
		)
		if self._api_base:
			kwargs['api_base'] = self._api_base
		if self._api_key:
			kwargs['api_key'] = self._api_key
		for chunk in self._ll.completion(**kwargs):
			delta = chunk.choices[0].delta.content
			if delta:
				yield delta

	def analyze_sentiment(self, text: str) -> str:
		prompt = (
			"Classify the sentiment of the following text as exactly one of: "
			"'positive', 'negative', or 'neutral'. Reply with only the label.\n\nText: "
			+ text + "\nSentiment:"
		)
		return self.generate_text(prompt).strip().lower()

	def extract_entities(self, text: str, entity_types: list) -> dict:
		types_str = ', '.join(entity_types)
		prompt = (
			f"Extract the following entity types from the text: {types_str}.\n"
			f"Return a JSON object where each key is an entity type and the value is a list "
			f"of extracted entities.\n\nText: {text}\nJSON:"
		)
		response = self.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			return json.loads(match.group()) if match else {t: [] for t in entity_types}
		except Exception:
			return {t: [] for t in entity_types}

	def summarize_text(self, text: str, length: str = 'medium') -> str:
		word_counts = {'short': 100, 'medium': 300, 'long': 600}
		words = word_counts.get(length, 300)
		prompt = f"Summarize the following text in approximately {words} words:\n\n{text}\n\nSummary:"
		return self.generate_text(prompt).strip()

	def translate_text(self, text: str, target_language: str) -> str:
		prompt = (
			f"Translate the following text to {target_language}. "
			f"Reply with only the translation.\n\nText: {text}\n\nTranslation:"
		)
		return self.generate_text(prompt).strip()


# ── Tier-based factory ────────────────────────────────────────────────────────

def get_ai_engine(tier: str = 'default') -> AIModel:
	"""
	Return the right AIModel for the requested capability tier.

	  tier='fast'    → LiteLLM proxy (cloud model, lowest latency)
	  tier='default' → OllamaModel (local, balanced)
	  tier='vision'  → OllamaVisionModel (multimodal tasks)
	  tier='strong'  → LiteLLM proxy with a stronger model

	Falls back to OllamaModel if LiteLLM is unavailable.
	"""
	settings = get_settings()

	if tier == 'vision':
		return OllamaVisionModel()  # type: ignore[return-value]

	if tier in ('fast', 'strong'):
		model_key = 'litellm.strong_model' if tier == 'strong' else 'litellm.fast_model'
		model = settings.get_setting(model_key, settings.get_setting('litellm.model', ''))
		api_base = settings.get_setting('litellm.api_base', '')
		# Only use LiteLLM when explicitly configured; otherwise Ollama is the default
		if api_base and model:
			return LiteLLMModel(model_name=model)
		return OllamaModel()

	return OllamaModel()


# Backward-compat alias
OllamaDeepSeekR1 = OllamaModel
