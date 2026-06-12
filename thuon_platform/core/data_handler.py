# core/data_handler.py

import logging
import psycopg2
import psycopg2.extras
from core.settings_manager import get_settings

logger = logging.getLogger('thuon.data_handler')


class DatabaseHandler:
	def __init__(self, db_config: dict | None = None):
		if db_config is None:
			s = get_settings()
			db_config = {
				'host': s.get_setting('database.host', 'localhost'),
				'port': s.get_setting('database.port', 5432),
				'dbname': s.get_setting('database.dbname', 'thuon_db'),
				'user': s.get_setting('database.user', 'thuon_user'),
				'password': s.get_setting('database.password', ''),
			}
		self.db_config = db_config
		self.conn: psycopg2.extensions.connection | None = None

	def connect(self) -> bool:
		try:
			self.conn = psycopg2.connect(**self.db_config)
			self.conn.autocommit = False
			logger.info("Database connected.")
			return True
		except Exception as e:
			logger.error(f"DB connect error: {e}")
			return False

	def disconnect(self) -> None:
		if self.conn:
			self.conn.close()
			self.conn = None

	def _ensure_connected(self) -> bool:
		if self.conn is None or self.conn.closed:
			return self.connect()
		return True

	def execute_query(self, query: str, params: tuple = ()) -> list[dict]:
		if not self._ensure_connected():
			return []
		try:
			with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
				cur.execute(query, params)
				if cur.description:
					rows = cur.fetchall()
					self.conn.commit()
					return [dict(r) for r in rows]
				self.conn.commit()
				return []
		except Exception as e:
			self.conn.rollback()
			logger.error(f"Query error: {e}")
			return []

	def create_table(self, table_name: str, schema: dict) -> bool:
		cols = ', '.join(f'"{k}" {v}' for k, v in schema.items())
		sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({cols})'
		try:
			if not self._ensure_connected():
				return False
			with self.conn.cursor() as cur:
				cur.execute(sql)
			self.conn.commit()
			return True
		except Exception as e:
			self.conn.rollback()
			logger.error(f"Create table error: {e}")
			return False

	def drop_table(self, table_name: str) -> bool:
		try:
			if not self._ensure_connected():
				return False
			with self.conn.cursor() as cur:
				cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')
			self.conn.commit()
			return True
		except Exception as e:
			self.conn.rollback()
			logger.error(f"Drop table error: {e}")
			return False

	def insert_data(self, table_name: str, data: dict) -> bool:
		if not self._ensure_connected():
			return False
		cols = ', '.join(f'"{k}"' for k in data)
		placeholders = ', '.join(['%s'] * len(data))
		sql = f'INSERT INTO "{table_name}" ({cols}) VALUES ({placeholders})'
		try:
			with self.conn.cursor() as cur:
				cur.execute(sql, list(data.values()))
			self.conn.commit()
			return True
		except Exception as e:
			self.conn.rollback()
			logger.error(f"Insert error: {e}")
			return False

	def fetch_data(self, table_name: str, condition: str | None = None, params: tuple = ()) -> list[dict]:
		sql = f'SELECT * FROM "{table_name}"'
		if condition:
			sql += f' WHERE {condition}'
		return self.execute_query(sql, params)

	def update_data(self, table_name: str, updates: dict, condition: str, params: tuple = ()) -> bool:
		if not self._ensure_connected():
			return False
		set_clause = ', '.join(f'"{k}" = %s' for k in updates)
		sql = f'UPDATE "{table_name}" SET {set_clause} WHERE {condition}'
		all_params = list(updates.values()) + list(params)
		try:
			with self.conn.cursor() as cur:
				cur.execute(sql, all_params)
			self.conn.commit()
			return True
		except Exception as e:
			self.conn.rollback()
			logger.error(f"Update error: {e}")
			return False

	def delete_data(self, table_name: str, condition: str, params: tuple = ()) -> bool:
		if not self._ensure_connected():
			return False
		sql = f'DELETE FROM "{table_name}" WHERE {condition}'
		try:
			with self.conn.cursor() as cur:
				cur.execute(sql, params)
			self.conn.commit()
			return True
		except Exception as e:
			self.conn.rollback()
			logger.error(f"Delete error: {e}")
			return False
