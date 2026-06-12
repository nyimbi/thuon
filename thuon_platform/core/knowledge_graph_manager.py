# core/knowledge_graph_manager.py

import logging

logger = logging.getLogger('thuon.knowledge_graph_manager')


class KnowledgeGraphManager:
	def __init__(self, weaviate_client=None):
		self.weaviate_client = weaviate_client

	@classmethod
	def from_settings(cls) -> 'KnowledgeGraphManager':
		from core.settings_manager import get_settings
		import weaviate
		settings = get_settings()
		url = settings.get_setting('weaviate.url', 'http://localhost:8080')
		client = weaviate.connect_to_local(host=url.replace('http://', '').split(':')[0],
		                                    port=int(url.split(':')[-1]))
		return cls(weaviate_client=client)

	def create_schema(self, class_name: str, properties: list[dict]) -> bool:
		try:
			import weaviate.classes.config as wvc
			collection = self.weaviate_client.collections.create(
				name=class_name,
				properties=[wvc.Property(name=p['name'], data_type=wvc.DataType.TEXT) for p in properties],
			)
			logger.info(f"Created Weaviate collection: {class_name}")
			return collection is not None
		except Exception as e:
			if 'already exists' in str(e).lower():
				return True
			logger.error(f"Create schema error: {e}")
			return False

	def add_node(self, class_name: str, properties: dict) -> str | None:
		try:
			collection = self.weaviate_client.collections.get(class_name)
			uuid = collection.data.insert(properties)
			return str(uuid)
		except Exception as e:
			logger.error(f"Add node error: {e}")
			return None

	def add_edge(self, from_node_uuid: str, to_node_uuid: str, relationship_name: str, class_name: str, edge_properties: dict | None = None) -> bool:
		try:
			import weaviate.classes as wvc
			collection = self.weaviate_client.collections.get(class_name)
			collection.data.reference_add(
				from_uuid=from_node_uuid,
				from_property=relationship_name,
				to=wvc.query.Filter.by_id().equal(to_node_uuid),
			)
			return True
		except Exception as e:
			logger.error(f"Add edge error: {e}")
			return False

	def query_graph(self, class_name: str, query_text: str, limit: int = 5) -> list[dict]:
		try:
			collection = self.weaviate_client.collections.get(class_name)
			results = collection.query.near_text(query=query_text, limit=limit)
			return [obj.properties for obj in results.objects]
		except Exception as e:
			logger.error(f"Query graph error: {e}")
			return []

	def update_node_properties(self, node_uuid: str, class_name: str, properties: dict) -> bool:
		try:
			collection = self.weaviate_client.collections.get(class_name)
			collection.data.update(uuid=node_uuid, properties=properties)
			return True
		except Exception as e:
			logger.error(f"Update node error: {e}")
			return False

	def delete_node(self, node_uuid: str, class_name: str) -> bool:
		try:
			collection = self.weaviate_client.collections.get(class_name)
			collection.data.delete_by_id(node_uuid)
			return True
		except Exception as e:
			logger.error(f"Delete node error: {e}")
			return False

	def delete_edge(self, from_node_uuid: str, to_node_uuid: str, relationship_name: str, class_name: str) -> bool:
		try:
			import weaviate.classes as wvc
			collection = self.weaviate_client.collections.get(class_name)
			collection.data.reference_delete(
				from_uuid=from_node_uuid,
				from_property=relationship_name,
				to=wvc.query.Filter.by_id().equal(to_node_uuid),
			)
			return True
		except Exception as e:
			logger.error(f"Delete edge error: {e}")
			return False
