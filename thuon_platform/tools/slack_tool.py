import requests
from typing import Any

from core.settings_manager import get_settings


class SlackTool:

	def send_message(
		self,
		channel: str,
		message: str,
		webhook_url: str = '',
		username: str = 'Thuon',
		icon_emoji: str = ':robot_face:',
	) -> dict[str, Any]:
		try:
			settings = get_settings()

			if not webhook_url:
				webhook_url = settings.get_setting('tools.slack.webhook_url', '')

			if not webhook_url:
				return {
					'status': 'error',
					'error': 'Slack webhook not configured. Set tools.slack.webhook_url in config.yaml or pass webhook_url param',
				}

			payload: dict[str, Any] = {
				'channel': channel,
				'username': username,
				'text': message,
				'icon_emoji': icon_emoji,
			}

			r = requests.post(webhook_url, json=payload, timeout=10)

			if r.status_code == 200 and r.text == 'ok':
				return {
					'status': 'success',
					'channel': channel,
					'message': message[:200],
					'webhook_used': bool(webhook_url),
				}

			return {
				'status': 'error',
				'error': f'Slack API returned {r.status_code}: {r.text}',
			}
		except Exception as e:
			return {'status': 'error', 'error': str(e)}
