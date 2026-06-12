# tests/ci/test_knowledge_ingestion.py
"""Tests for core/knowledge_ingestion.py"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from unittest.mock import patch, MagicMock


class TestChunkText:
	def test_splits_long_text(self):
		from core.knowledge_ingestion import _chunk_text
		text = ' '.join(['word'] * 3000)
		chunks = _chunk_text(text, size=100, overlap=20)
		assert len(chunks) > 1

	def test_filters_tiny_chunks(self):
		from core.knowledge_ingestion import _chunk_text
		chunks = _chunk_text('hi', size=100, overlap=10)
		assert chunks == []

	def test_overlap_creates_extra_chunks(self):
		from core.knowledge_ingestion import _chunk_text
		text = ' '.join(['word'] * 500)
		chunks_no_overlap = _chunk_text(text, size=100, overlap=0)
		chunks_overlap    = _chunk_text(text, size=100, overlap=50)
		assert len(chunks_overlap) > len(chunks_no_overlap)


class TestKnowledgeIngestionPipeline:
	def test_ingest_text_adds_chunks(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		pipe = KnowledgeIngestionPipeline()
		result = pipe.ingest_text(' '.join(['word'] * 200), source='test')
		assert result['status'] == 'ok'
		assert result['chunks_added'] > 0
		assert pipe.chunk_count > 0

	def test_duplicate_text_skipped(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		pipe = KnowledgeIngestionPipeline()
		text = ' '.join(['unique'] * 200)
		pipe.ingest_text(text, source='first')
		result2 = pipe.ingest_text(text, source='second')
		assert result2['status'] == 'duplicate'

	def test_source_count_tracks_unique_sources(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		pipe = KnowledgeIngestionPipeline()
		pipe.ingest_text(' '.join(['a'] * 200), source='src1')
		pipe.ingest_text(' '.join(['b'] * 200), source='src2')
		assert pipe.source_count == 2

	def test_search_returns_ranked_results(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		pipe = KnowledgeIngestionPipeline()
		# Need 5+ distinct docs for BM25 IDF to produce non-zero scores
		pipe.ingest_text('machine learning artificial intelligence neural networks deep learning ' * 20, source='ml_doc')
		pipe.ingest_text('cooking recipes food preparation kitchen baking ingredients flavour ' * 20, source='food_doc')
		pipe.ingest_text('finance accounting revenue profit balance sheet investments portfolio ' * 20, source='finance_doc')
		pipe.ingest_text('sports football basketball athletics competition tournament championship ' * 20, source='sports_doc')
		pipe.ingest_text('travel tourism hotels flights destinations culture geography journey ' * 20, source='travel_doc')
		results = pipe.search('machine learning', top_k=3)
		assert len(results) > 0
		assert results[0]['source'] == 'ml_doc'

	def test_search_empty_pipeline_returns_empty(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		pipe = KnowledgeIngestionPipeline()
		assert pipe.search('anything') == []

	def test_get_context_returns_string(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		pipe = KnowledgeIngestionPipeline()
		# 5+ docs so BM25 IDF is non-zero
		pipe.ingest_text('python programming language functions classes decorators ' * 30, source='py_doc')
		pipe.ingest_text('javascript typescript react nodejs frontend web browser ' * 30, source='js_doc')
		pipe.ingest_text('database sql postgresql queries indexes transactions joins ' * 30, source='db_doc')
		pipe.ingest_text('devops docker kubernetes deployment containers orchestration ' * 30, source='devops_doc')
		pipe.ingest_text('security cryptography encryption authentication authorization ' * 30, source='sec_doc')
		ctx = pipe.get_context('python functions')
		assert isinstance(ctx, str)
		assert 'py_doc' in ctx

	def test_get_context_empty_pipeline(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		pipe = KnowledgeIngestionPipeline()
		assert pipe.get_context('query') == ''

	def test_clear_resets_state(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		pipe = KnowledgeIngestionPipeline()
		pipe.ingest_text(' '.join(['w'] * 200), source='s')
		assert pipe.chunk_count > 0
		pipe.clear()
		assert pipe.chunk_count == 0
		assert pipe.source_count == 0

	def test_persists_to_json(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
			store_path = f.name
		try:
			pipe = KnowledgeIngestionPipeline(store_path=store_path)
			pipe.ingest_text(' '.join(['data'] * 200), source='persisted')
			# Reload from disk
			pipe2 = KnowledgeIngestionPipeline(store_path=store_path)
			assert pipe2.chunk_count == pipe.chunk_count
		finally:
			os.unlink(store_path)

	def test_ingest_file_plain_text(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		with tempfile.NamedTemporaryFile(suffix='.txt', mode='w', delete=False) as f:
			f.write((' '.join(['text'] * 300)))
			path = f.name
		try:
			pipe = KnowledgeIngestionPipeline()
			result = pipe.ingest_file(path)
			assert result['status'] == 'ok'
			assert result['chunks_added'] > 0
		finally:
			os.unlink(path)

	def test_ingest_file_docx(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		from docx import Document
		with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
			path = f.name
		try:
			doc = Document()
			for _ in range(5):
				doc.add_paragraph('word ' * 60)
			doc.save(path)
			pipe = KnowledgeIngestionPipeline()
			result = pipe.ingest_file(path)
			assert result['status'] == 'ok'
		finally:
			os.unlink(path)

	def test_ingest_url_uses_requests_fallback(self):
		from core.knowledge_ingestion import KnowledgeIngestionPipeline
		mock_resp = MagicMock()
		mock_resp.text = '<html><body><p>' + ' '.join(['content'] * 300) + '</p></body></html>'
		with patch('requests.get', return_value=mock_resp):
			with patch.dict('sys.modules', {'trafilatura': None}):
				pipe = KnowledgeIngestionPipeline()
				result = pipe.ingest_url('https://example.com/article')
		assert result['status'] in ('ok', 'duplicate')


class TestExtractPdf:
	def test_extracts_text_from_pdf(self):
		from core.knowledge_ingestion import _extract_pdf
		mock_reader = MagicMock()
		mock_page = MagicMock()
		mock_page.extract_text.return_value = 'This is page content.'
		mock_reader.pages = [mock_page]
		with patch('pypdf.PdfReader', return_value=mock_reader):
			text = _extract_pdf('/fake/path.pdf')
		assert 'This is page content.' in text
