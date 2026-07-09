import logging
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.services.knowledge.vector_store_base import BaseVectorStore

logger = logging.getLogger("opsgraph.knowledge.qdrant")

class QdrantVectorStoreAdapter(BaseVectorStore):
    """
    Qdrant vector database adapter. Supports in-memory fallback for local execution.
    """
    def __init__(self, host: str | None = None, port: int | None = None, api_key: str | None = None):
        if host:
            logger.info(f"Connecting to Qdrant server at {host}:{port}")
            self.client = QdrantClient(url=host, port=port, api_key=api_key)
            self.mode = "qdrant"
        else:
            logger.info("Initializing in-memory local Qdrant client fallback")
            self.client = QdrantClient(location=":memory:")
            self.mode = "memory"

    def create_collection(self, collection_name: str, vector_size: int) -> None:
        try:
            # Check if exists
            if self.client.collection_exists(collection_name):
                logger.info(f"Collection '{collection_name}' already exists.")
                return
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE)
            )
            logger.info(f"Collection '{collection_name}' created successfully.")
        except Exception as e:
            logger.error(f"Error creating collection '{collection_name}': {e}")
            raise e

    def delete_collection(self, collection_name: str) -> None:
        try:
            if self.client.collection_exists(collection_name):
                self.client.delete_collection(collection_name)
                logger.info(f"Collection '{collection_name}' deleted.")
        except Exception as e:
            logger.error(f"Error deleting collection: {e}")
            raise e

    def _to_uuid(self, string_id: str) -> str:
        import uuid
        try:
            uuid.UUID(string_id)
            return string_id
        except ValueError:
            namespace = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
            return str(uuid.uuid5(namespace, string_id))

    def upsert(self, collection_name: str, points: list[dict]) -> None:
        try:
            qdrant_points = []
            for p in points:
                payload = dict(p["payload"])
                payload["chunk_id"] = p["id"]
                qdrant_points.append(
                    models.PointStruct(
                        id=self._to_uuid(p["id"]),
                        vector=p["vector"],
                        payload=payload
                    )
                )
            self.client.upsert(
                collection_name=collection_name,
                points=qdrant_points
            )
            logger.info(f"Upserted {len(points)} points into collection '{collection_name}'.")
        except Exception as e:
            logger.error(f"Error upserting points: {e}")
            raise e

    def search(
        self,
        collection_name: str,
        vector: list[float],
        limit: int,
        filter_metadata: dict | None = None
    ) -> list[dict]:
        try:
            # Build filters
            qdrant_filter = None
            if filter_metadata:
                conditions = []
                for k, v in filter_metadata.items():
                    if v is None:
                        continue
                    if isinstance(v, list):
                        conditions.append(
                            models.FieldCondition(
                                key=k,
                                match=models.MatchAny(any=v)
                            )
                        )
                    else:
                        conditions.append(
                            models.FieldCondition(
                                key=k,
                                match=models.MatchValue(value=v)
                            )
                        )
                if conditions:
                    qdrant_filter = models.Filter(must=conditions)

            results = self.client.query_points(
                collection_name=collection_name,
                query=vector,
                limit=limit,
                query_filter=qdrant_filter
            )

            points = []
            for r in results.points:
                orig_id = r.payload.get("chunk_id", r.id) if r.payload else r.id
                points.append({
                    "id": orig_id,
                    "score": r.score,
                    "payload": r.payload
                })
            return points
        except Exception as e:
            logger.error(f"Error searching vector store: {e}")
            raise e

    def health_check(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False
