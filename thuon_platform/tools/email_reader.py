import imaplib
import email
import email.header
import re
from typing import Any

from core.settings_manager import get_settings


class EmailReader:

	def read_inbox(self, folder: str = 'INBOX', max_messages: int = 20, search_filter: str = 'UNSEEN', mark_read: bool = False) -> dict[str, Any]:
		try:
			settings = get_settings()
			imap_host = settings.get_setting('tools.email.imap_host', '')
			port = int(settings.get_setting('tools.email.imap_port', 993))
			username = settings.get_setting('tools.email.username', '')
			password = settings.get_setting('tools.email.password', '')

			if not imap_host:
				return {'status': 'error', 'error': 'Email not configured. Set tools.email.* in config.yaml'}

			mail = imaplib.IMAP4_SSL(imap_host, port)
			mail.login(username, password)
			mail.select(folder)

			status, data = mail.search(None, search_filter)
			if status != 'OK':
				return {'status': 'error', 'error': f'Search failed: {status}'}

			all_uids = data[0].split()
			uids = all_uids[-max_messages:]

			messages: list[dict[str, Any]] = []
			for uid in uids:
				try:
					_, msg_data = mail.fetch(uid, '(RFC822)')
					raw = msg_data[0][1]
					msg = email.message_from_bytes(raw)

					from_addr = self._decode_header(msg.get('From', ''))
					to_addr = self._decode_header(msg.get('To', ''))
					subject = self._decode_header(msg.get('Subject', ''))
					date = msg.get('Date', '')

					body, has_attachments = self._extract_body(msg)

					if mark_read:
						mail.store(uid, '+FLAGS', '\\Seen')

					messages.append({
						'uid': uid.decode(),
						'from': from_addr,
						'to': to_addr,
						'subject': subject,
						'date': date,
						'body': body,
						'has_attachments': has_attachments,
					})
				except Exception:
					# skip malformed messages, continue fetching rest
					continue

			mail.logout()

			return {
				'status': 'success',
				'folder': folder,
				'messages': messages,
				'count': len(messages),
			}
		except Exception as e:
			return {'status': 'error', 'error': str(e)}

	def _decode_header(self, value: str) -> str:
		parts = email.header.decode_header(value)
		decoded = []
		for part, charset in parts:
			if isinstance(part, bytes):
				decoded.append(part.decode(charset or 'utf-8', errors='replace'))
			else:
				decoded.append(part)
		return ''.join(decoded)

	def _extract_body(self, msg: email.message.Message) -> tuple[str, bool]:
		plain = ''
		html = ''
		has_attachments = False

		if msg.is_multipart():
			for part in msg.walk():
				ct = part.get_content_type()
				cd = str(part.get('Content-Disposition', ''))
				# count inline attachments too
				if 'attachment' in cd:
					has_attachments = True
					continue
				if ct == 'text/plain' and not plain:
					payload = part.get_payload(decode=True)
					if payload:
						plain = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
				elif ct == 'text/html' and not html:
					payload = part.get_payload(decode=True)
					if payload:
						html = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
		else:
			ct = msg.get_content_type()
			payload = msg.get_payload(decode=True)
			if payload:
				text = payload.decode(msg.get_content_charset() or 'utf-8', errors='replace')
				if ct == 'text/plain':
					plain = text
				elif ct == 'text/html':
					html = text

		if plain:
			return plain.strip(), has_attachments
		if html:
			return self._strip_tags(html).strip(), has_attachments
		return '', has_attachments

	def _strip_tags(self, html: str) -> str:
		return re.sub(r'<[^>]+>', '', html)
