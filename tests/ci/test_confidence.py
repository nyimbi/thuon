"""Tests for core/confidence.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from core.confidence import ConfidenceCalibrator, _text_score, _structural_score, json_flatten


class TestTextScore:
	def test_hedged_text_scores_lower(self):
		hedged = 'This might possibly perhaps be unclear, but it could be approximately right.'
		score = _text_score(hedged)
		assert score < 0.5

	def test_definitive_text_scores_higher(self):
		definitive = 'According to the study, the data shows confirmed and verified results.'
		score = _text_score(definitive)
		assert score > 0.5

	def test_empty_text_returns_midpoint(self):
		assert _text_score('') == 0.5

	def test_score_clamped(self):
		score = _text_score('x ' * 1000)
		assert 0.0 <= score <= 1.0


class TestStructuralScore:
	def test_empty_dict(self):
		assert _structural_score({}) == 0.2

	def test_fully_populated(self):
		result = {'a': 1, 'b': 'text', 'c': [1, 2], 'd': {'x': 1}}
		score = _structural_score(result)
		assert score > 0.7

	def test_mostly_empty_fields(self):
		result = {'a': '', 'b': None, 'c': [], 'd': {}, 'e': 'something'}
		score = _structural_score(result)
		assert score < 0.7


class TestJsonFlatten:
	def test_string_passthrough(self):
		assert json_flatten('hello') == 'hello'

	def test_dict_flattened(self):
		result = json_flatten({'a': 'foo', 'b': 'bar'})
		assert 'foo' in result
		assert 'bar' in result

	def test_nested(self):
		result = json_flatten({'outer': {'inner': 'deep_value'}})
		assert 'deep_value' in result

	def test_list(self):
		result = json_flatten(['x', 'y', 'z'])
		assert 'x' in result and 'z' in result


class TestConfidenceCalibrator:
	def setup_method(self):
		self.cal = ConfidenceCalibrator()

	def test_score_returns_required_keys(self):
		result = self.cal.score({'key': 'value'})
		for key in ('text_score', 'structural_score', 'source_score', 'overall', 'level'):
			assert key in result

	def test_level_high(self):
		# A result with sources, many fields, and definitive language
		result = {
			'summary': 'According to the study, confirmed results were verified.',
			'source': 'https://example.com/study',
			'title': 'Research',
			'author': 'Dr Smith',
			'date': '2024',
		}
		confidence = self.cal.score(result)
		assert confidence['overall'] >= 0.5

	def test_level_low_for_sparse_hedged(self):
		result = {'maybe': 'it might possibly be unclear'}
		confidence = self.cal.score(result)
		assert confidence['level'] in ('LOW', 'MEDIUM')

	def test_annotate_adds_confidence_key(self):
		result = {'analysis': 'some text'}
		annotated = self.cal.annotate(result)
		assert '_confidence' in annotated
		assert 'analysis' in annotated

	def test_annotate_does_not_mutate_original(self):
		original = {'a': 1}
		self.cal.annotate(original)
		assert '_confidence' not in original

	def test_overall_clamped_0_to_1(self):
		confidence = self.cal.score({'x': 'y'})
		assert 0.0 <= confidence['overall'] <= 1.0

	def test_extra_context_influences_score(self):
		base = self.cal.score({})
		with_context = self.cal.score({}, extra_context='According to research, verified confirmed.')
		assert with_context['text_score'] >= base['text_score']
