# core/scheduler.py
"""
Background scheduler using the `schedule` library + a daemon thread.
Registers all periodic Thuon jobs. Call start() once from create_app().
"""

from __future__ import annotations
import logging
import threading
import time

import schedule

from core.settings_manager import get_settings

log = logging.getLogger(__name__)

_started = False
_start_lock = threading.Lock()


def _run_job(name: str, fn) -> None:
	try:
		fn()
	except Exception as exc:
		log.error('Scheduler job %s failed: %s', name, exc)


def _job_rfp_discovery() -> None:
	from core.company_profile import get_company_profile
	from core.notification_bus import get_notification_bus
	bus = get_notification_bus()
	bus.publish(
		event='rfp_discovery_started',
		title='RFP Discovery Running',
		body='Scanning configured portals for new RFPs.',
		url='/rfps',
	)
	log.info('rfp_discovery job ran')


def _job_blog_suggestions() -> None:
	from core.notification_bus import get_notification_bus
	bus = get_notification_bus()
	bus.publish(
		event='blog_ready',
		title='Weekly Blog Topics Ready',
		body='New blog topic suggestions are available.',
		url='/content/blog',
	)
	log.info('blog_suggestions job ran')


def _job_social_daily() -> None:
	from core.notification_bus import get_notification_bus
	from core.obsidian_bridge import get_obsidian_bridge
	bus = get_notification_bus()
	bridge = get_obsidian_bridge()
	ideas = bridge.read_ideas() if bridge.enabled else []
	# Also collect in-app ideas
	from pathlib import Path
	ideas_dir = Path(__file__).parent.parent / 'data' / 'ideas'
	if ideas_dir.is_dir():
		for f in ideas_dir.glob('*.md'):
			try:
				text = f.read_text(encoding='utf-8').strip()
				if text:
					ideas.append(text)
			except Exception:
				pass
	if ideas:
		bus.publish(
			event='social_ready',
			title=f'Social Posts Ready ({len(ideas)} ideas)',
			body='Daily social media post suggestions are available.',
			url='/content/social',
		)
	log.info('social_daily job ran, %d ideas', len(ideas))


def _job_website_refresh() -> None:
	from core.notification_bus import get_notification_bus
	bus = get_notification_bus()
	bus.publish(
		event='website_ready',
		title='Website Refresh Available',
		body='Weekly website content refresh is ready to review.',
		url='/content/website',
	)
	log.info('website_refresh job ran')


def _job_kb_reload() -> None:
	from core.company_profile import get_company_profile
	get_company_profile().reload()
	log.info('company KB reloaded')


def _schedule_loop() -> None:
	while True:
		schedule.run_pending()
		time.sleep(30)


def start(app=None) -> None:
	"""Register all jobs and start the background scheduler thread. Idempotent."""
	global _started
	with _start_lock:
		if _started:
			return
		_started = True

	settings = get_settings()
	enabled = settings.get_setting('scheduler.enabled', True)
	if not enabled:
		log.info('Scheduler disabled by config.')
		return

	interval_h = settings.get_setting('scheduler.rfp_discovery_interval_hours', 6)
	blog_day   = settings.get_setting('scheduler.blog_suggestions_day', 'monday').lower()
	social_h   = settings.get_setting('scheduler.social_daily_hour', 8)
	website_day = settings.get_setting('scheduler.website_refresh_day', 'sunday').lower()

	schedule.every(interval_h).hours.do(lambda: _run_job('rfp_discovery', _job_rfp_discovery))
	schedule.every(1).hours.do(lambda: _run_job('kb_reload', _job_kb_reload))
	schedule.every().day.at(f'{social_h:02d}:00').do(lambda: _run_job('social_daily', _job_social_daily))

	_day_map = {
		'monday': schedule.every().monday,
		'tuesday': schedule.every().tuesday,
		'wednesday': schedule.every().wednesday,
		'thursday': schedule.every().thursday,
		'friday': schedule.every().friday,
		'saturday': schedule.every().saturday,
		'sunday': schedule.every().sunday,
	}
	(_day_map.get(blog_day) or schedule.every().monday).at('09:00').do(
		lambda: _run_job('blog_suggestions', _job_blog_suggestions)
	)
	(_day_map.get(website_day) or schedule.every().sunday).at('09:00').do(
		lambda: _run_job('website_refresh', _job_website_refresh)
	)

	t = threading.Thread(target=_schedule_loop, daemon=True, name='thuon-scheduler')
	t.start()
	log.info('Thuon scheduler started.')
