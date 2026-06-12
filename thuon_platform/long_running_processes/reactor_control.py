# long_running_processes/reactor_control.py

"""
Reactor Control Module for Thuon Platform Long-Running Processes (with Blinker Events)
"""

import subprocess
import time
import logging
import signal as _signal
import os
import threading
from typing import List, Dict, Optional
import blinker

logger = logging.getLogger('thuon.reactor_control')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# --- Blinker Signals ---
process_started_signal = blinker.Signal()
process_completed_signal = blinker.Signal()
process_error_signal = blinker.Signal()
process_stopped_signal = blinker.Signal()
price_change_detected_signal = blinker.Signal()
ma_announcement_detected_signal = blinker.Signal()
environmental_event_detected_signal = blinker.Signal()


class ProcessReactor:
	def __init__(self, ai_engine=None, search_engine=None, polling_interval: float = 5.0):
		self.ai_engine = ai_engine
		self.search_engine = search_engine
		self.process_list: List[subprocess.Popen] = []
		self.process_status: Dict[int, str] = {}
		self.process_metadata: Dict[int, dict] = {}
		self.polling_interval: float = polling_interval
		self.running: bool = False
		self._process_lock = threading.Lock()
		logger.info("ProcessReactor initialized.")

	def start_process(self, capability_module: str, command: str, options: Optional[List[str]] = None, metadata: Optional[dict] = None) -> Optional[int]:
		base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
		script = os.path.join(base_dir, 'thuon.sh')
		command_list = ['bash', script, capability_module, command]
		if options:
			command_list.extend(options)
		try:
			process = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=base_dir)
			with self._process_lock:
				self.process_list.append(process)
				self.process_status[process.pid] = 'running'
				proc_meta = {'capability_module': capability_module, 'command': command, 'options': options or [], 'start_time': time.time()}
				if metadata:
					proc_meta.update(metadata)
				self.process_metadata[process.pid] = proc_meta
			logger.info(f"Process started: PID={process.pid}")
			process_started_signal.send(self, pid=process.pid, capability_module=capability_module, command=command)
			return process.pid
		except Exception as e:
			logger.error(f"Error starting process: {e}")
			return None

	def monitor_processes(self) -> None:
		processes_to_remove = []
		with self._process_lock:
			for process in self.process_list:
				pid = process.pid
				return_code = process.poll()
				if return_code is None:
					self.process_status[pid] = 'running'
					continue
				metadata = self.process_metadata.get(pid, {})
				if return_code == 0:
					self.process_status[pid] = 'completed'
					logger.info(f"Process completed: PID={pid}")
					process_completed_signal.send(self, pid=pid, metadata=metadata)
				else:
					self.process_status[pid] = 'error'
					stderr_output = process.stderr.read().decode() if process.stderr else ''
					logger.error(f"Process error: PID={pid}, rc={return_code}, stderr={stderr_output}")
					process_error_signal.send(self, pid=pid, return_code=return_code, stderr_output=stderr_output, metadata=metadata)
				processes_to_remove.append(process)
			for p in processes_to_remove:
				self.process_list.remove(p)

	def stop_process(self, pid: int) -> bool:
		with self._process_lock:
			for proc in self.process_list:
				if proc.pid == pid:
					try:
						proc.terminate()
						time.sleep(1)
						if proc.poll() is None:
							proc.kill()
						self.process_status[pid] = 'stopped'
						self.process_list.remove(proc)
						logger.info(f"Process stopped: PID={pid}")
						process_stopped_signal.send(self, pid=pid, metadata=self.process_metadata.get(pid, {}))
						return True
					except Exception as e:
						logger.error(f"Error stopping PID={pid}: {e}")
						return False
			logger.warning(f"PID={pid} not found.")
			return False

	def stop_all_processes(self) -> None:
		pids = [p.pid for p in self.process_list]
		for pid in pids:
			self.stop_process(pid)

	def get_process_status(self, pid: int) -> str:
		return self.process_status.get(pid, 'unknown')

	def run(self) -> None:
		self.running = True
		logger.info("ProcessReactor main loop started.")
		try:
			while self.running:
				self.monitor_processes()
				time.sleep(self.polling_interval)
		except KeyboardInterrupt:
			logger.info("ProcessReactor interrupted.")
		finally:
			self.stop_all_processes()
			self.running = False


class EventReactor:
	def __init__(self, ai_engine, process_reactor: ProcessReactor, search_engine=None):
		self.ai_engine = ai_engine
		self.process_reactor = process_reactor
		self.search_engine = search_engine
		logger.info("EventReactor initialized.")

	def _parse_llm_choice(self, response: str) -> int:
		import re
		import json
		try:
			data = json.loads(re.search(r'\{.*\}', response, re.DOTALL).group())
			return int(data.get('choice', 1))
		except Exception:
			for i in range(5, 0, -1):
				if str(i) in response:
					return i
			return 1

	def handle_price_change(self, sender, **event_data):
		logger.info(f"Price change event: {event_data}")
		current_price = event_data.get('current_price')
		previous_price = event_data.get('previous_price')
		prompt = (
			f"A price change was detected. Current: {current_price}, Previous: {previous_price}. "
			f"Choose the best reaction: 1=monitor, 2=market_research, 3=alert_sales, 4=financial_forecast, 5=competitive_intel. "
			f"Reply with JSON: {{\"choice\": N, \"reason\": \"...\"}}"
		)
		response = self.ai_engine.generate_text(prompt)
		choice = self._parse_llm_choice(response)
		logger.info(f"LLM chose reaction {choice} for price change.")
		actions = {
			2: ('market_sales_research', 'analyze_market_trends'),
			3: ('internal_communications_automator', 'draft_internal_communication'),
			4: ('financial_forecasting_analyst', 'forecast_financial_performance'),
			5: ('competitive_intelligence_operative', 'analyze_competitor_landscape'),
		}
		if choice in actions:
			self.process_reactor.start_process(*actions[choice], metadata={'triggered_by': 'price_change'})

	def handle_ma_announcement(self, sender, **event_data):
		logger.info(f"M&A announcement event: {event_data}")
		company_a = event_data.get('company_a', 'Unknown')
		company_b = event_data.get('company_b', 'Unknown')
		prompt = (
			f"M&A announcement: {company_a} + {company_b}. "
			f"Choose: 1=monitor, 2=competitive_intel, 3=ma_profile, 4=market_research, 5=supply_chain. "
			f"Reply with JSON: {{\"choice\": N, \"reason\": \"...\"}}"
		)
		response = self.ai_engine.generate_text(prompt)
		choice = self._parse_llm_choice(response)
		actions = {
			2: ('competitive_intelligence_operative', 'analyze_competitor_landscape'),
			3: ('ma_target_profiler', 'profile_ma_target'),
			4: ('market_sales_research', 'analyze_market_trends'),
			5: ('supply_chain_resilience_planner', 'assess_supply_chain_risks'),
		}
		if choice in actions:
			self.process_reactor.start_process(*actions[choice], metadata={'triggered_by': 'ma_announcement'})

	def handle_environmental_event(self, sender, **event_data):
		logger.info(f"Environmental event: {event_data}")

	def handle_process_completed(self, sender, **process_info):
		logger.info(f"Process completed: PID={process_info.get('pid')}")

	def handle_process_error(self, sender, **process_info):
		logger.error(f"Process error: PID={process_info.get('pid')}, rc={process_info.get('return_code')}")

	def handle_process_stopped(self, sender, **process_info):
		logger.info(f"Process stopped: PID={process_info.get('pid')}")


if __name__ == '__main__':
	import sys
	sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
	from core.ai_engine import OllamaModel
	from core.search_engine import DuckDuckGoSearch

	def signal_handler(sig, frame):
		logger.info("Shutting down...")
		reactor.stop_all_processes()
		sys.exit(0)

	_signal.signal(_signal.SIGINT, signal_handler)
	_signal.signal(_signal.SIGTERM, signal_handler)

	ai_engine = OllamaModel()
	search_engine = DuckDuckGoSearch()
	reactor = ProcessReactor(ai_engine=ai_engine, search_engine=search_engine, polling_interval=2.0)
	event_reactor = EventReactor(ai_engine=ai_engine, process_reactor=reactor, search_engine=search_engine)

	price_change_detected_signal.connect(event_reactor.handle_price_change)
	ma_announcement_detected_signal.connect(event_reactor.handle_ma_announcement)
	environmental_event_detected_signal.connect(event_reactor.handle_environmental_event)
	process_completed_signal.connect(event_reactor.handle_process_completed)
	process_error_signal.connect(event_reactor.handle_process_error)
	process_stopped_signal.connect(event_reactor.handle_process_stopped)

	reactor.run()
