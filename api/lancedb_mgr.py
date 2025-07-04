
from config import EMBEDDING_DIMENSIONS
import lancedb
from lancedb.pydantic import LanceModel, Vector
from lancedb.embeddings import get_registry
from typing import List, Optional
import os
import logging

logger = logging.getLogger(__name__)

# Pydantic model for the tags table in LanceDB
class Tags(LanceModel):
    vector: Vector(EMBEDDING_DIMENSIONS)  # type: ignore
    text: str
    tag_id: int

class LanceDBMgr:
    def __init__(self, base_dir: str):
        self.uri = os.path.join(base_dir, "lancedb")
        self.db = lancedb.connect(self.uri)
        self.tbl = None

    def init_db(self, table_name: str = "tags"):
        """Initializes the LanceDB table for tags."""
        try:
            # First try to create with exist_ok=True
            self.tbl = self.db.create_table(table_name, schema=Tags, exist_ok=True)
            logger.info(f"LanceDB table '{table_name}' initialized successfully at {self.uri}")
        except ValueError as e:
            if "Schema Error" in str(e):
                # If schema doesn't match, drop the existing table and recreate
                logger.warning(f"Schema mismatch detected. Dropping existing table '{table_name}' and recreating...")
                try:
                    self.db.drop_table(table_name)
                    self.tbl = self.db.create_table(table_name, schema=Tags)
                    logger.info(f"LanceDB table '{table_name}' recreated successfully at {self.uri}")
                except Exception as recreate_error:
                    logger.error(f"Failed to recreate LanceDB table: {recreate_error}")
                    raise
            else:
                logger.error(f"Failed to initialize LanceDB table: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to initialize LanceDB table: {e}")
            raise

    def add_tags(self, tags_data: List[dict]):
        """
        Adds or updates tags in the LanceDB table.
        
        Args:
            tags_data: A list of dictionaries, each with 'vector', 'text', and 'tag_id'.
        """
        if not self.tbl:
            self.init_db()
        
        if not tags_data:
            return

        try:
            self.tbl.add(tags_data)
            logger.info(f"Successfully added {len(tags_data)} tags to LanceDB.")
        except Exception as e:
            logger.error(f"Failed to add tags to LanceDB: {e}")

    def search_tags(self, query_vector: List[float], limit: int = 50) -> List[dict]:
        """
        Searches for similar tags based on a query vector.
        
        Args:
            query_vector: The vector to search with.
            limit: The maximum number of results to return.
            
        Returns:
            A list of dictionaries representing the nearest tags.
        """
        if not self.tbl:
            self.init_db()

        try:
            results = self.tbl.search(query_vector).limit(limit).to_pydantic(Tags)
            logger.info(f"LanceDB search found {len(results)} results.")
            # Convert Pydantic models to dictionaries for easier use
            return [result.model_dump() for result in results]
        except Exception as e:
            logger.error(f"Failed to search tags in LanceDB: {e}")
            return []

# Example usage
if __name__ == '__main__':
    # This should be the directory where your SQLite DB is located
    db_directory = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in"
    
    lancedb_mgr = LanceDBMgr(base_dir=db_directory)
    lancedb_mgr.init_db()
    
    # Example data
    sample_tags = [
        {"vector": [0.1] * EMBEDDING_DIMENSIONS, "text": "人工智能", "tag_id": 1},
        {"vector": [0.2] * EMBEDDING_DIMENSIONS, "text": "机器学习", "tag_id": 2},
    ]
    
    lancedb_mgr.add_tags(sample_tags)
    
    # Example search
    search_results = lancedb_mgr.search_tags(query_vector=[0.15] * EMBEDDING_DIMENSIONS)
    print("Search results:", search_results)
