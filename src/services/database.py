# src/services/database.py
"""
Database utility module for SQLite (conversation history) and ChromaDB
(vector memory for personas and semantic search).
"""

import logging
import sqlite3
import json
import time
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any

import src.config as config

try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    VECTOR_LIBS_INSTALLED = True
except ImportError:
    VECTOR_LIBS_INSTALLED = False

logger = logging.getLogger(__name__)

# --- Module Globals ---
db_pool = None
vector_db_client = None
embedding_model = None
memory_collection = None


# --- Database Initialization ---
def init_db():
    """Initializes both the SQLite and Vector (ChromaDB) databases."""
    global db_pool, vector_db_client, embedding_model, memory_collection

    os.makedirs(config.DB_DIR, exist_ok=True)

    try:
        db_pool = _DatabasePool(config.CONVERSATION_DB_FILE)
        with sqlite3.connect(config.CONVERSATION_DB_FILE) as con:
            cur = con.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS user_rate_limits (
                    user_id INTEGER PRIMARY KEY,
                    last_message_timestamp REAL NOT NULL
                )
            ''')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_chat_id_timestamp ON conversations (chat_id, timestamp DESC)')
            con.commit()
        logger.info("SQLite database initialized successfully.")
    except Exception as e:
        logger.critical(f"SQLite database initialization failed: {e}", exc_info=True)
        raise

    if not VECTOR_LIBS_INSTALLED:
        logger.warning("ChromaDB or Sentence-Transformers not installed. Vector memory disabled.")
        config.VECTOR_MEMORY_ENABLED = False
        return

    try:
        from chromadb.config import Settings
        
        os.makedirs(config.VECTOR_DB_PATH, exist_ok=True)
        
        logger.info(f"Loading embedding model: {config.EMBEDDING_MODEL_NAME}...")
        embedding_model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
        
        vector_db_client = chromadb.PersistentClient(
            path=config.VECTOR_DB_PATH,
            settings=Settings(anonymized_telemetry=False)
        )
        
        logger.info("ChromaDB telemetry explicitly disabled via settings.")
        
        memory_collection = vector_db_client.get_or_create_collection(
            name=config.VECTOR_DB_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info("Vector DB (ChromaDB) initialized successfully.")
    except Exception as e:
        logger.critical(f"Vector Database initialization failed: {e}", exc_info=True)
        config.VECTOR_MEMORY_ENABLED = False


# --- SQLite Connection Pool Class (Internal) ---
class _DatabasePool:
    """An asynchronous connection pool for SQLite."""
    def __init__(self, db_path: str, max_connections: int = 10):
        self.db_path = db_path
        self._pool: asyncio.Queue[sqlite3.Connection] = asyncio.Queue(maxsize=max_connections)
        self._semaphore = asyncio.Semaphore(max_connections)

    async def _create_connection(self) -> sqlite3.Connection:
        conn = await asyncio.to_thread(sqlite3.connect, self.db_path, check_same_thread=False)
        await asyncio.to_thread(conn.execute, "PRAGMA journal_mode=WAL")
        return conn

    async def get_connection(self) -> sqlite3.Connection:
        await self._semaphore.acquire()
        try:
            if not self._pool.empty():
                return self._pool.get_nowait()
            else:
                return await self._create_connection()
        except asyncio.QueueEmpty:
            return await self._create_connection()
        except Exception:
            self._semaphore.release()
            raise

    async def return_connection(self, conn: sqlite3.Connection):
        try:
            await self._pool.put(conn)
        finally:
            self._semaphore.release()


@asynccontextmanager
async def get_db_connection():
    """Provides a database connection from the pool within an async context."""
    if not db_pool: raise RuntimeError("Database not initialized.")
    conn = await db_pool.get_connection()
    try:
        yield conn
    finally:
        await db_pool.return_connection(conn)

# --- Core Database Functions ---

async def get_user_timestamp(user_id: int) -> float:
    """Retrieves the last message timestamp for a given user."""
    async with get_db_connection() as con:
        cursor = await asyncio.to_thread(con.execute, "SELECT last_message_timestamp FROM user_rate_limits WHERE user_id = ?", (user_id,))
        row = await asyncio.to_thread(cursor.fetchone)
        return row[0] if row else 0.0

async def update_user_timestamp(user_id: int, timestamp: float):
    """Updates or inserts the last message timestamp for a given user."""
    async with get_db_connection() as con:
        await asyncio.to_thread(
            con.execute,
            "INSERT OR REPLACE INTO user_rate_limits (user_id, last_message_timestamp) VALUES (?, ?)",
            (user_id, timestamp)
        )
        await asyncio.to_thread(con.commit)

async def add_message_to_db(chat_id: int, role: str, content: str):
    """Adds a message to SQLite and its vector embedding to ChromaDB."""
    db_id = None
    async with get_db_connection() as con:
        cursor = await asyncio.to_thread(
            con.execute, "INSERT INTO conversations (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, role, content)
        )
        db_id = cursor.lastrowid
        await asyncio.to_thread(con.commit)

    if config.VECTOR_MEMORY_ENABLED and db_id and embedding_model and memory_collection:
        try:
            embedding = await asyncio.to_thread(embedding_model.encode, [content])
            await asyncio.to_thread(
                memory_collection.add,
                embeddings=[embedding[0].tolist()],
                documents=[content],
                metadatas=[{"chat_id": chat_id, "timestamp": time.time(), "type": "message"}],
                ids=[str(db_id)]
            )
        except Exception as e:
            logger.error(f"Failed to add vector embedding for chat {chat_id} (SQLite ID: {db_id}): {e}", exc_info=True)

async def add_summary_to_db(chat_id: int, summary_text: str):
    """Adds a conversation summary to the SQLite and vector databases."""
    db_id = None
    content_with_prefix = f"Memory Summary: {summary_text}"

    async with get_db_connection() as con:
        cursor = await asyncio.to_thread(
            con.execute, "INSERT INTO conversations (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, "system", content_with_prefix)
        )
        db_id = cursor.lastrowid
        await asyncio.to_thread(con.commit)

    if config.VECTOR_MEMORY_ENABLED and db_id and embedding_model and memory_collection:
        try:
            embedding = await asyncio.to_thread(embedding_model.encode, [summary_text])
            await asyncio.to_thread(
                memory_collection.add,
                embeddings=[embedding[0].tolist()],
                documents=[summary_text],
                metadatas=[{"chat_id": chat_id, "timestamp": time.time(), "type": "summary"}],
                ids=[str(db_id)]
            )
            logger.info(f"Successfully added a new summary to vector memory for chat {chat_id}.")
        except Exception as e:
            logger.error(f"Failed to add summary vector embedding for chat {chat_id}: {e}", exc_info=True)

async def get_history_from_db(chat_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves conversation history from SQLite, including message IDs."""
    async with get_db_connection() as con:
        con.row_factory = sqlite3.Row
        query = "SELECT id, role, content FROM conversations WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?"
        cursor = await asyncio.to_thread(con.execute, query, (chat_id, limit))
        rows = await asyncio.to_thread(cursor.fetchall)
        rows.reverse()
        return [{"id": row["id"], "role": row["role"], "content": row["content"]} for row in rows]

async def get_summaries_from_db(chat_id: int, limit: int = 5) -> List[str]:
    """Retrieves the most recent summaries for a given chat."""
    async with get_db_connection() as con:
        query = "SELECT content FROM conversations WHERE chat_id = ? AND role = 'system' AND content LIKE 'Memory Summary:%' ORDER BY timestamp DESC LIMIT ?"
        cursor = await asyncio.to_thread(con.execute, query, (chat_id, limit))
        rows = await asyncio.to_thread(cursor.fetchall)
        return [row[0].replace("Memory Summary: ", "") for row in rows]

async def delete_messages_by_ids(ids_to_delete: List[int]):
    """Deletes messages from SQLite and ChromaDB by their IDs."""
    if not ids_to_delete:
        return

    placeholders = ','.join('?' for _ in ids_to_delete)
    async with get_db_connection() as con:
        await asyncio.to_thread(con.execute, f"DELETE FROM conversations WHERE id IN ({placeholders})", ids_to_delete)
        await asyncio.to_thread(con.commit)

    if config.VECTOR_MEMORY_ENABLED and memory_collection:
        try:
            string_ids = [str(id_val) for id_val in ids_to_delete]
            await asyncio.to_thread(memory_collection.delete, ids=string_ids)
            logger.info(f"Pruned {len(string_ids)} messages from vector memory.")
        except Exception as e:
            logger.error(f"Failed to prune vector embeddings for IDs {string_ids}: {e}", exc_info=True)

# --- REWRITTEN: Implements Hybrid Search with correct ChromaDB filter syntax ---
async def search_semantic_memory(chat_id: int, query_text: str) -> List[str]:
    """
    Performs a hybrid semantic search, prioritizing one summary and then recent messages.
    """
    if not config.VECTOR_MEMORY_ENABLED or not memory_collection or not embedding_model:
        return []

    try:
        query_embedding = await asyncio.to_thread(embedding_model.encode, [query_text])
        
        # 1. Search for the single most relevant summary
        summary_results = await asyncio.to_thread(
            memory_collection.query,
            query_embeddings=[query_embedding[0].tolist()],
            n_results=1,
            where={
                "$and": [
                    {"chat_id": {"$eq": chat_id}},
                    {"type": {"$eq": "summary"}}
                ]
            }
        )
        
        # 2. Search for the N-1 most relevant individual messages
        # Note: SEMANTIC_SEARCH_K_RESULTS is the *total* desired memories.
        num_messages_to_fetch = max(1, config.SEMANTIC_SEARCH_K_RESULTS - 1)
        message_results = await asyncio.to_thread(
            memory_collection.query,
            query_embeddings=[query_embedding[0].tolist()],
            n_results=num_messages_to_fetch,
            where={
                "$and": [
                    {"chat_id": {"$eq": chat_id}},
                    # Using "$ne" for "not equal to" to exclude summaries
                    {"type": {"$ne": "summary"}}
                ]
            }
        )
        
        # Combine results, summary first
        final_memories = []
        if summary_results and summary_results.get('documents', [[]])[0]:
            final_memories.extend(summary_results['documents'][0])
        
        if message_results and message_results.get('documents', [[]])[0]:
            final_memories.extend(message_results['documents'][0])
            
        return final_memories

    except Exception as e:
        logger.error(f"Hybrid semantic memory search failed for chat {chat_id}: {e}", exc_info=True)
        return []

async def delete_last_interaction(chat_id: int):
    """Deletes the last user/assistant pair from the databases."""
    async with get_db_connection() as con:
        cursor = await asyncio.to_thread(con.execute, "SELECT id FROM conversations WHERE chat_id = ? ORDER BY id DESC LIMIT 2", (chat_id,))
        rows = await asyncio.to_thread(cursor.fetchall)
    
    if rows:
        ids_to_delete = [row[0] for row in rows]
        await delete_messages_by_ids(ids_to_delete)

async def clear_history(chat_id: int):
    """Deletes all data for a user from the databases."""
    async with get_db_connection() as con:
        await asyncio.to_thread(con.execute, "DELETE FROM user_rate_limits WHERE user_id = ?", (chat_id,))
        await asyncio.to_thread(con.execute, "DELETE FROM conversations WHERE chat_id = ?", (chat_id,))
        await asyncio.to_thread(con.commit)

    if config.VECTOR_MEMORY_ENABLED and memory_collection:
        try:
            await asyncio.to_thread(memory_collection.delete, where={"chat_id": chat_id})
        except Exception as e:
            logger.error(f"Failed to clear vector memory for chat {chat_id}: {e}", exc_info=True)