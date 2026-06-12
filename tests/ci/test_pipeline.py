"""Tests for core/pipeline.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from core.pipeline import Pipeline


def _echo(**kwargs):
	return {'echo': kwargs, 'status': 'ok'}


def _append(echo=None, **kwargs):
	return {'appended': True, 'prev': echo}


def _fail(**kwargs):
	raise RuntimeError('deliberate failure')


class TestPipeline:
	def test_single_step(self):
		p = Pipeline()
		p.add_step('step1', _echo, x=1, y=2)
		result = p.run()
		assert result['status'] == 'ok'
		assert result['final']['echo'] == {'x': 1, 'y': 2}

	def test_two_steps_inject_keys(self):
		p = Pipeline()
		p.add_step('first', _echo, a='hello')
		p.add_step('second', _append, inject_keys=['echo'])
		result = p.run()
		assert result['status'] == 'ok'
		assert result['final']['appended'] is True
		assert result['final']['prev'] == {'a': 'hello'}

	def test_error_step_returns_error(self):
		p = Pipeline()
		p.add_step('good', _echo, x=1)
		p.add_step('bad', _fail)
		result = p.run()
		assert result['status'] == 'error'
		assert result['error_step'] == 'bad'
		assert 'deliberate failure' in result['final']['error']

	def test_error_stops_pipeline(self):
		called = []
		def step_after(**kw):
			called.append(True)
			return {}
		p = Pipeline()
		p.add_step('fail', _fail)
		p.add_step('after', step_after)
		p.run()
		assert called == []

	def test_empty_pipeline(self):
		p = Pipeline()
		result = p.run()
		assert result['status'] == 'ok'
		assert result['final'] == {}

	def test_method_chaining(self):
		p = Pipeline()
		ret = p.add_step('a', _echo).add_step('b', _echo)
		assert ret is p

	def test_get_step_result(self):
		p = Pipeline()
		p.add_step('s', _echo, v=42)
		p.run()
		assert p.get_step_result('s')['echo']['v'] == 42

	def test_get_step_result_missing(self):
		p = Pipeline()
		assert p.get_step_result('nope') == {}

	def test_steps_dict_in_result(self):
		p = Pipeline()
		p.add_step('a', _echo, n=1)
		p.add_step('b', _echo, n=2)
		result = p.run()
		assert 'a' in result['steps']
		assert 'b' in result['steps']

	def test_static_kwargs_override_not_clobbered_by_inject(self):
		def receiver(x=None, extra=None, **kw):
			return {'x': x, 'extra': extra}
		p = Pipeline()
		p.add_step('source', lambda **kw: {'extra': 'injected'})
		p.add_step('target', receiver, inject_keys=['extra'], x='static')
		result = p.run()
		assert result['final']['x'] == 'static'
		assert result['final']['extra'] == 'injected'
