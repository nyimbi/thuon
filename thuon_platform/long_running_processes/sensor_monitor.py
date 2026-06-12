# long_running_processes/sensor_monitor.py

"""
Sensor Monitor Module for Thuon Platform — Environmental Data Collection & LLM Event Evaluation

Monitors RSS feeds, web pages, and simulated market events. Evaluates items via LLM
and emits Blinker signals for strategically significant events.

TODO: Integrate Crawl4AI into the scraping pipeline
"""

import time
import random
import logging
import threading
import requests
import feedparser
from bs4 import BeautifulSoup
from abc import ABC, abstractmethod
from typing import List, Optional

from long_running_processes.reactor_control import (
	price_change_detected_signal,
	ma_announcement_detected_signal,
	environmental_event_detected_signal,
)

logger = logging.getLogger('thuon.sensor_monitor')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')


class MarketEventSimulator:
	def __init__(self):
		self.current_price = 150.0
		self._stop_event = threading.Event()
		logger.info("MarketEventSimulator initialized.")

	def monitor_environment(self) -> None:
		logger.info("MarketEventSimulator loop started.")
		while not self._stop_event.is_set():
			self._simulate_price_fluctuations()
			self._simulate_ma_announcements()
			self._stop_event.wait(10)

	def stop(self) -> None:
		self._stop_event.set()

	def _simulate_price_fluctuations(self) -> None:
		price_change = random.uniform(-5, 5)
		new_price = self.current_price + price_change
		if abs(price_change) > 4:
			event_type = "significant_price_increase" if price_change > 0 else "significant_price_decrease"
			price_change_detected_signal.send(
				self,
				event_type=event_type,
				current_price=new_price,
				previous_price=self.current_price,
				timestamp=time.time(),
			)
			logger.info(f"Price change: {event_type}, new={new_price:.2f}")
		self.current_price = new_price

	def _simulate_ma_announcements(self) -> None:
		if random.random() < 0.05:
			company_a = f"Company_{random.randint(100, 999)}"
			company_b = f"Acquirer_{random.randint(1000, 1999)}"
			url = f"https://example.com/ma/{company_a}_{company_b}"
			ma_announcement_detected_signal.send(
				self,
				company_a=company_a,
				company_b=company_b,
				announcement_details_url=url,
				timestamp=time.time(),
			)
			logger.info(f"Simulated M&A: {company_b} acquires {company_a}")


class DataSource(ABC):
	def __init__(self, config: dict):
		self.config = config
		self.source_name = config.get('name', 'Unnamed DataSource')

	@abstractmethod
	def fetch_data(self):
		pass

	@abstractmethod
	def parse_data(self, raw_data) -> list:
		pass

	def evaluate_event(self, parsed_item: dict, ai_engine) -> bool:
		title = parsed_item.get('title', 'No Title')
		summary = parsed_item.get('summary', parsed_item.get('description', title))
		prompt = (
			f"Is the following news item strategically significant for a business? "
			f"Source: {self.source_name}\nTitle: {title}\nSummary: {summary}\n"
			f"Reply 'YES' or 'NO' with a one-sentence justification."
		)
		response = ai_engine.generate_text(prompt)
		return 'YES' in response.upper()


class RSSFeedDataSource(DataSource):
	def __init__(self, config: dict):
		super().__init__(config)
		self.feed_url = config.get('feed_url')
		if not self.feed_url:
			raise ValueError(f"RSSFeedDataSource '{self.source_name}' requires 'feed_url'.")

	def fetch_data(self):
		try:
			resp = requests.get(self.feed_url, timeout=30)
			resp.raise_for_status()
			return feedparser.parse(resp.text)
		except Exception as e:
			logger.error(f"RSS fetch error for '{self.source_name}': {e}")
			return None

	def parse_data(self, raw_feed) -> list:
		if raw_feed and hasattr(raw_feed, 'entries'):
			return list(raw_feed.entries)
		return []


class WebScrapingDataSource(DataSource):
	def __init__(self, config: dict):
		super().__init__(config)
		self.scrape_url = config.get('scrape_url')
		self.content_selector = config.get('content_selector')
		if not self.scrape_url or not self.content_selector:
			raise ValueError(f"WebScrapingDataSource '{self.source_name}' requires 'scrape_url' and 'content_selector'.")

	def fetch_data(self):
		try:
			resp = requests.get(self.scrape_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
			resp.raise_for_status()
			return resp.text
		except Exception as e:
			logger.error(f"Web scrape fetch error for '{self.source_name}': {e}")
			return None

	def parse_data(self, raw_html) -> list:
		if not raw_html:
			return []
		try:
			soup = BeautifulSoup(raw_html, 'html.parser')
			elements = soup.select(self.content_selector)
			if elements:
				return [{'title': f"Scraped from {self.scrape_url}", 'summary': elements[0].get_text().strip(), 'source_url': self.scrape_url}]
		except Exception as e:
			logger.error(f"Parse error for '{self.source_name}': {e}")
		return []


class DataSourceManager:
	def __init__(self, ai_engine, search_engine, data_sources_config: list):
		self.ai_engine = ai_engine
		self.search_engine = search_engine
		self.data_sources: List[DataSource] = []
		self._stop_event = threading.Event()
		self._load_data_sources(data_sources_config)
		logger.info(f"DataSourceManager initialized with {len(self.data_sources)} sources.")

	def _load_data_sources(self, configs: list) -> None:
		for cfg in configs:
			source_type = cfg.get('type')
			try:
				if source_type == 'rss_feed':
					self.data_sources.append(RSSFeedDataSource(cfg))
				elif source_type == 'web_scrape':
					self.data_sources.append(WebScrapingDataSource(cfg))
				else:
					logger.warning(f"Unknown data source type: '{source_type}'")
			except Exception as e:
				logger.error(f"Error loading data source: {e}")

	def monitor_data_sources(self) -> None:
		logger.info("DataSourceManager monitoring loop started.")
		while not self._stop_event.is_set():
			for source in self.data_sources:
				try:
					raw = source.fetch_data()
					if raw:
						for item in source.parse_data(raw):
							if source.evaluate_event(item, self.ai_engine):
								environmental_event_detected_signal.send(
									self,
									source_name=source.source_name,
									source_type=type(source).__name__,
									event_data=item,
								)
								logger.info(f"Environmental event from '{source.source_name}': {item.get('title', '')}")
				except Exception as e:
					logger.error(f"Error processing '{source.source_name}': {e}")
			self._stop_event.wait(60)

	def stop(self) -> None:
		self._stop_event.set()


def run_monitor(ai_engine, search_engine, data_handler=None) -> None:
	logger.info("Sensor Monitor starting...")

	market_simulator = MarketEventSimulator()
	market_thread = threading.Thread(target=market_simulator.monitor_environment, daemon=True)
	market_thread.start()

	data_sources_config = [
		{'type': 'rss_feed', 'name': 'TechCrunch', 'feed_url': 'http://feeds.feedburner.com/TechCrunch/'},
	]
	dsm = DataSourceManager(ai_engine=ai_engine, search_engine=search_engine, data_sources_config=data_sources_config)
	dsm_thread = threading.Thread(target=dsm.monitor_data_sources, daemon=True)
	dsm_thread.start()

	try:
		while True:
			time.sleep(60)
	except KeyboardInterrupt:
		logger.info("Sensor Monitor shutting down...")
		market_simulator.stop()
		dsm.stop()

	logger.info("Sensor Monitor stopped.")


if __name__ == '__main__':
	import sys
	import os
	sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
	from core.ai_engine import OllamaModel
	from core.search_engine import DuckDuckGoSearch
	run_monitor(ai_engine=OllamaModel(), search_engine=DuckDuckGoSearch())
