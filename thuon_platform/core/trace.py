# core/trace.py
"""
Execution trace context — records capability calls, tool invocations,
data sources hit, LLM token counts, and confidence scores.

Usage:
    with TraceContext() as tc:
        result = capability.run(...)
    print(tc.summary())
"""

from __future__ import annotations
import time
import threading
from contextlib import contextmanager
from typing import Any


_local = threading.local()


class TraceEvent:
	__slots__ = ('ts', 'type', 'data')

	def __init__(self, type_: str, data: dict):
		self.ts   = time.time()
		self.type = type_
		self.data = data


class TraceContext:
	"""Thread-local execution trace collector."""

	def __init__(self):
		self._events: list[TraceEvent] = []
		self._start: float = 0.0

	# ── Context manager ──────────────────────────────────────────────────────

	def __enter__(self) -> 'TraceContext':
		self._start = time.time()
		_local.trace = self
		return self

	def __exit__(self, *_) -> None:
		_local.trace = None

	# ── Emit events ──────────────────────────────────────────────────────────

	def emit(self, type_: str, **data) -> None:
		self._events.append(TraceEvent(type_, data))

	# ── Read ─────────────────────────────────────────────────────────────────

	@property
	def events(self) -> list[dict]:
		return [{'ts': e.ts, 'type': e.type, **e.data} for e in self._events]

	@property
	def elapsed(self) -> float:
		return round(time.time() - self._start, 2)

	def to_dict(self) -> dict:
		events = self.events
		return {
			'elapsed_seconds':  self.elapsed,
			'event_count':      len(events),
			'llm_calls':        sum(1 for e in events if e['type'] == 'llm_call'),
			'tool_calls':       sum(1 for e in events if e['type'] == 'tool_call'),
			'data_sources':     list({e['source'] for e in events if e.get('source')}),
			'phases':           [e['name'] for e in events if e['type'] == 'phase'],
			'events':           events,
		}

	def summary(self) -> str:
		d = self.to_dict()
		lines = [
			f'Elapsed: {d["elapsed_seconds"]}s',
			f'LLM calls: {d["llm_calls"]}',
			f'Tool calls: {d["tool_calls"]}',
		]
		if d['data_sources']:
			lines.append(f'Data sources: {", ".join(d["data_sources"])}')
		if d['phases']:
			lines.append(f'Phases: {" → ".join(d["phases"])}')
		return '\n'.join(lines)


# ── Module-level helpers (call from anywhere) ────────────────────────────────

def trace_emit(type_: str, **data) -> None:
	"""Emit a trace event if a TraceContext is active on this thread."""
	tc: TraceContext | None = getattr(_local, 'trace', None)
	if tc is not None:
		tc.emit(type_, **data)


def trace_llm(prompt: str, response: str = '', model: str = '') -> None:
	trace_emit('llm_call',
		prompt_chars=len(prompt),
		response_chars=len(response),
		model=model,
	)


def trace_tool(tool_name: str, args: dict | None = None, result_chars: int = 0) -> None:
	trace_emit('tool_call', tool=tool_name, args=args or {}, result_chars=result_chars)


def trace_phase(name: str) -> None:
	trace_emit('phase', name=name)


def trace_source(source: str, items_found: int = 0) -> None:
	trace_emit('data_source', source=source, items_found=items_found)


@contextmanager
def capturing_trace():
	"""Convenience context manager that yields a dict-form trace."""
	with TraceContext() as tc:
		yield tc
