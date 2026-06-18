import base64
from typing import Any

from core.settings_manager import get_settings


class BrowserAgent:

	def navigate(self, url: str, actions: list = [], screenshot: bool = False, timeout: int = 30) -> dict[str, Any]:
		try:
			try:
				from playwright.sync_api import sync_playwright
			except ImportError:
				return {'status': 'error', 'error': 'playwright not installed. Run: uv add playwright && playwright install chromium'}

			settings = get_settings()
			headless = settings.get_setting('tools.browser.headless', True)

			with sync_playwright() as pw:
				browser = pw.chromium.launch(headless=headless)
				page = browser.new_page()
				page.goto(url, timeout=timeout * 1000)

				for action in actions:
					atype = action.get('type')
					if atype == 'click':
						page.click(action['selector'])
					elif atype == 'fill':
						page.fill(action['selector'], action['value'])
					elif atype == 'wait':
						page.wait_for_timeout(action.get('ms', 1000))
					elif atype == 'scroll':
						page.mouse.wheel(0, action.get('delta', 500))
					elif atype == 'press':
						page.press(action.get('selector', 'body'), action['key'])

				title = page.title()
				text = page.inner_text('body')[:5000]

				b64 = None
				if screenshot:
					b64 = base64.b64encode(page.screenshot(type='png')).decode()

				final_url = page.url
				browser.close()

			return {
				'status': 'success',
				'url': final_url,
				'title': title,
				'text': text,
				'screenshot_base64': b64,
				'actions_performed': len(actions),
			}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}
