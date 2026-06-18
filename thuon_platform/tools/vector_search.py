import uuid
from typing import Any

from core.settings_manager import get_settings


class VectorSearchTool:

	def __init__(self, rag_engine=None):
		self.rag_engine = rag_engine

	def search(self, query: str, collection: str = 'default', max_results: int = 10) -> dict[str, Any]:
		try:
			if self.rag_engine is not None:
				raw = self.rag_engine.search(query)
				results = []
				for item in (raw if isinstance(raw, list) else []):
					results.append({
						'text': item.get('text', item.get('content', '')),
						'score': item.get('score', item.get('distance', 0.0)),
						'metadata': item.get('metadata', {}),
						'id': item.get('id', ''),
					})
				return {'status': 'success', 'query': query, 'collection': collection, 'results': results, 'count': len(results)}

			try:
				import chromadb
			except ImportError:
				return {'status': 'error', 'error': 'Package chromadb not installed. Run: uv add chromadb'}

			settings = get_settings()
			persist_dir = settings.get_setting('tools.vector_search.persist_dir', '/tmp/thuon_vectors')
			client = chromadb.PersistentClient(path=persist_dir)
			col = client.get_or_create_collection(collection)

			raw = col.query(query_texts=[query], n_results=max_results)

			docs = raw.get('documents', [[]])[0]
			distances = raw.get('distances', [[]])[0]
			metadatas = raw.get('metadatas', [[]])[0]
			ids = raw.get('ids', [[]])[0]

			results = []
			for i, text in enumerate(docs):
				results.append({
					'text': text,
					# chroma returns L2 distance; invert to a score so lower distance = higher score
					'score': 1.0 / (1.0 + distances[i]) if i < len(distances) else 0.0,
					'metadata': metadatas[i] if i < len(metadatas) else {},
					'id': ids[i] if i < len(ids) else '',
				})

			return {'status': 'success', 'query': query, 'collection': collection, 'results': results, 'count': len(results)}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}

	def add_documents(self, texts: list, metadata: list = [], collection: str = 'default') -> dict[str, Any]:
		try:
			if self.rag_engine is not None:
				self.rag_engine.add_documents(texts)
				ids = [str(uuid.uuid4()) for _ in texts]
				return {'status': 'success', 'collection': collection, 'added': len(texts), 'ids': ids}

			try:
				import chromadb
			except ImportError:
				return {'status': 'error', 'error': 'Package chromadb not installed. Run: uv add chromadb'}

			settings = get_settings()
			persist_dir = settings.get_setting('tools.vector_search.persist_dir', '/tmp/thuon_vectors')
			client = chromadb.PersistentClient(path=persist_dir)
			col = client.get_or_create_collection(collection)

			ids = [str(uuid.uuid4()) for _ in texts]
			metas = metadata if metadata else [{} for _ in texts]
			col.add(documents=texts, ids=ids, metadatas=metas)

			return {'status': 'success', 'collection': collection, 'added': len(texts), 'ids': ids}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}
