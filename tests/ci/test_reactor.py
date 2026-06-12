# tests/ci/test_reactor.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

import threading
from unittest.mock import MagicMock, patch


def test_signals_importable():
	from long_running_processes.reactor_control import (
		price_change_detected_signal,
		ma_announcement_detected_signal,
		environmental_event_detected_signal,
		process_completed_signal,
		process_error_signal,
	)
	import blinker
	assert isinstance(price_change_detected_signal, blinker.Signal)
	assert isinstance(environmental_event_detected_signal, blinker.Signal)


def test_process_reactor_start():
	from long_running_processes.reactor_control import ProcessReactor
	ai = MagicMock()
	ai.generate_text.return_value = '{"action": "monitor", "priority": 5}'
	reactor = ProcessReactor(ai_engine=ai)

	with patch('subprocess.Popen') as mock_popen:
		mock_proc = MagicMock()
		mock_proc.communicate.return_value = (b'output', b'')
		mock_proc.returncode = 0
		mock_popen.return_value = mock_proc
		result = reactor.start_process('research_assistant', 'perform_research')
	assert result is not None or mock_popen.called


def test_event_reactor_handles_signal():
	from long_running_processes.reactor_control import EventReactor, ProcessReactor, price_change_detected_signal
	ai = MagicMock()
	ai.generate_text.return_value = '{"action": "buy", "priority": 8}'
	pr = MagicMock(spec=ProcessReactor)
	reactor = EventReactor(ai_engine=ai, process_reactor=pr)
	# Send a signal — verify no exception raised
	price_change_detected_signal.send({'price': 100.0, 'symbol': 'AAPL'})


def test_sensor_monitor_imports():
	from long_running_processes.sensor_monitor import DataSourceManager, MarketEventSimulator
	assert DataSourceManager is not None
	assert MarketEventSimulator is not None


def test_data_source_manager_stop():
	from long_running_processes.sensor_monitor import DataSourceManager
	ai = MagicMock()
	search = MagicMock()
	dsm = DataSourceManager(ai_engine=ai, search_engine=search, data_sources_config=[])
	# Start in thread and stop immediately
	t = threading.Thread(target=dsm.monitor_data_sources, daemon=True)
	t.start()
	dsm.stop()
	t.join(timeout=3)
	# Thread should have stopped (or at least stop flag is set)
	assert dsm._stop_event.is_set()
