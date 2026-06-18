import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from core.settings_manager import get_settings


class EmailSender:

	def send(self, to: str, subject: str, body: str, attachments: list = [], cc: str = '', html_body: str = '') -> dict[str, Any]:
		try:
			settings = get_settings()
			smtp_host = settings.get_setting('tools.email.smtp_host', '')
			port = int(settings.get_setting('tools.email.smtp_port', 587))
			username = settings.get_setting('tools.email.username', '')
			password = settings.get_setting('tools.email.password', '')
			from_addr = settings.get_setting('tools.email.from_address', username)

			if not smtp_host:
				return {'status': 'error', 'error': 'Email not configured'}

			msg = MIMEMultipart('alternative' if html_body else 'mixed')
			msg['From'] = from_addr
			msg['To'] = to
			msg['Subject'] = subject
			if cc:
				msg['Cc'] = cc

			msg.attach(MIMEText(body, 'plain'))
			if html_body:
				msg.attach(MIMEText(html_body, 'html'))

			for attachment_path in attachments:
				path = Path(attachment_path)
				with open(path, 'rb') as f:
					part = MIMEBase('application', 'octet-stream')
					part.set_payload(f.read())
				encoders.encode_base64(part)
				part.add_header('Content-Disposition', f'attachment; filename="{path.name}"')
				msg.attach(part)

			smtp = smtplib.SMTP(smtp_host, port)
			smtp.starttls()
			smtp.login(username, password)
			recipients = [to] + ([cc] if cc else [])
			smtp.sendmail(from_addr, recipients, msg.as_string())
			smtp.quit()

			return {
				'status': 'success',
				'to': to,
				'subject': subject,
				'from': from_addr,
				'attachment_count': len(attachments),
				'sent': True,
			}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}
