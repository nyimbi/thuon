# core/rag_engine.py

import logging
from core.knowledge_graph_manager import KnowledgeGraphManager

logger = logging.getLogger('thuon.rag_engine')


class RAGEngine:
	def __init__(self, weaviate_client=None, llm_engine=None, kg_manager: KnowledgeGraphManager | None = None):
		self.weaviate_client = weaviate_client
		self.llm_engine = llm_engine
		self.kg_manager = kg_manager or (KnowledgeGraphManager(weaviate_client) if weaviate_client else None)

	def create_vector_database_index(self, index_name: str, schema: dict) -> bool:
		if not self.kg_manager:
			logger.warning("No Weaviate client configured")
			return False
		properties = [{'name': k} for k in schema.get('properties', {}).keys()]
		return self.kg_manager.create_schema(index_name, properties)

	def index_documents(self, index_name: str, documents: list[dict], text_key: str = 'content', metadata_keys: list | None = None) -> bool:
		if not self.kg_manager:
			logger.warning("No Weaviate client configured")
			return False
		success = True
		for doc in documents:
			props = {text_key: doc.get(text_key, '')}
			if metadata_keys:
				props.update({k: doc.get(k, '') for k in metadata_keys if k in doc})
			uuid = self.kg_manager.add_node(index_name, props)
			if uuid is None:
				success = False
		return success

	def query_vector_database(self, index_name: str, query: str, top_k: int = 5) -> list[dict]:
		if not self.kg_manager:
			return []
		return self.kg_manager.query_graph(index_name, query, limit=top_k)

	def augment_prompt_with_context(self, query: str, context_documents: list[dict]) -> str:
		if not context_documents:
			return query
		context_parts = []
		for i, doc in enumerate(context_documents, 1):
			text = doc.get('content', doc.get('text', str(doc)))
			context_parts.append(f"[{i}] {text[:500]}")
		context_str = '\n'.join(context_parts)
		return f"<context>\n{context_str}\n</context>\n\nQuestion: {query}"

	def generate_response_with_rag(self, query: str, index_name: str, generation_parameters: dict = {}) -> str:
		if not self.llm_engine:
			logger.warning("No LLM engine configured for RAG")
			return ''
		context_docs = self.query_vector_database(index_name, query)
		augmented_prompt = self.augment_prompt_with_context(query, context_docs)
		return self.llm_engine.generate_text(augmented_prompt, generation_parameters)
