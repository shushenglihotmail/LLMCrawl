"""
File indexer for semantic search using embeddings.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import List, Optional

import aiofiles
from llama_index.core import (
    Document,
    Settings,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

logger = logging.getLogger(__name__)


class FileIndexer:
    """Index and search files using embeddings."""

    def __init__(self, root_folder: str, vector_db_path: str):
        """
        Initialize FileIndexer.

        Args:
            root_folder: Absolute path to the root folder
            vector_db_path: Path to store vector database
        """
        self.root_folder = Path(root_folder).resolve()
        self.vector_db_path = Path(vector_db_path)
        self.index: Optional[VectorStoreIndex] = None

        # Default text file extensions
        self.text_extensions = {
            ".txt",
            ".md",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".csv",
            ".log",
            ".py",
            ".js",
            ".ts",
            ".go",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".sh",
            ".ps1",
            ".sql",
        }

    async def initialize(self):
        """Initialize LlamaIndex settings and load existing index."""
        logger.info("Initializing FileIndexer...")
        # Only initialize if OpenAI API key is available
        if not os.getenv("OPENAI_API_KEY"):
            logger.warning(
                "OPENAI_API_KEY not set - semantic search and indexing "
                "will be unavailable"
            )
            return

        try:
            logger.info("Configuring LlamaIndex Settings...")
            # Configure LlamaIndex
            Settings.llm = OpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0
            )
            logger.info("LLM configured.")

            Settings.embed_model = OpenAIEmbedding(
                model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
            )
            logger.info("Embedding model configured.")

            Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
            logger.info("Node parser configured.")

            # Try to load existing index
            if (
                self.vector_db_path.exists()
                and (self.vector_db_path / "docstore.json").exists()
            ):
                try:
                    logger.info(f"Loading existing index from {self.vector_db_path}...")
                    storage_context = StorageContext.from_defaults(
                        persist_dir=str(self.vector_db_path)
                    )
                    self.index = load_index_from_storage(storage_context)
                    logger.info(f"Loaded existing index from {self.vector_db_path}")
                except Exception as e:
                    logger.warning(f"Failed to load existing index: {e}")
                    self.index = None
            else:
                logger.info("No existing index found.")

        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {e}", exc_info=True)
            self.index = None

        logger.info("FileIndexer initialization complete.")

    def _validate_path(self, file_path: str) -> Path:
        """Validate path is within root folder."""
        if os.path.isabs(file_path):
            path = Path(file_path).resolve()
        else:
            path = (self.root_folder / file_path).resolve()

        try:
            path.relative_to(self.root_folder)
        except ValueError:
            raise ValueError(
                f"Access denied: Path '{file_path}' is outside root folder"
            )

        return path

    def _is_text_file(self, file_path: Path) -> bool:
        """Check if file is a text file based on extension."""
        return file_path.suffix.lower() in self.text_extensions

    async def _read_file_content(self, file_path: Path) -> Optional[str]:
        """Read file content as text."""
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                return await f.read()
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return None

    def _get_file_hash(self, file_path: Path) -> str:
        """Get hash of file path and modification time for cache invalidation."""
        stats = file_path.stat()
        content = f"{file_path}: {stats.st_mtime}: {stats.st_size}"
        return hashlib.md5(content.encode()).hexdigest()

    async def index_folder(
        self,
        folder_path: str = ".",
        recursive: bool = True,
        extensions: Optional[List[str]] = None,
    ) -> dict:
        """
        Index files in a folder.

        Args:
            folder_path: Path to folder (relative to root)
            recursive: Whether to index subdirectories
            extensions: File extensions to index. None for all text files.

        Returns:
            Dict with indexing results
        """
        # Check if embeddings are available
        if not os.getenv("OPENAI_API_KEY"):
            return {
                "folder": folder_path,
                "indexed": 0,
                "skipped": 0,
                "total": 0,
                "error": (
                    "OPENAI_API_KEY not set - indexing unavailable. "
                    "Use list_files or read_local_file instead."
                ),
            }

        validated_path = self._validate_path(folder_path)

        if not validated_path.exists() or not validated_path.is_dir():
            raise ValueError(f"Invalid folder path: {folder_path}")

        # Collect files to index
        if recursive:
            pattern = "**/*"
        else:
            pattern = "*"

        file_paths = list(validated_path.glob(pattern))

        # Filter by extension
        if extensions:
            ext_set = {
                ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                for ext in extensions
            }
            file_paths = [f for f in file_paths if f.suffix.lower() in ext_set]
        else:
            file_paths = [f for f in file_paths if self._is_text_file(f)]

        file_paths = [f for f in file_paths if f.is_file()]

        logger.info(f"Indexing {len(file_paths)} files from {validated_path}")

        # Create documents
        documents = []
        indexed_count = 0
        skipped_count = 0

        for file_path in file_paths:
            content = await self._read_file_content(file_path)
            if content:
                relative_path = str(file_path.relative_to(self.root_folder))
                doc = Document(
                    text=content,
                    metadata={
                        "file_path": relative_path,
                        "file_name": file_path.name,
                        "file_extension": file_path.suffix,
                        "file_size": file_path.stat().st_size,
                        "file_hash": self._get_file_hash(file_path),
                    },
                )
                documents.append(doc)
                indexed_count += 1
            else:
                skipped_count += 1

        # Create or update index
        if documents:
            if self.index is None:
                self.index = VectorStoreIndex.from_documents(documents)
            else:
                # Refresh index with new documents
                for doc in documents:
                    self.index.insert(doc)

            # Persist index
            self.vector_db_path.mkdir(parents=True, exist_ok=True)
            self.index.storage_context.persist(persist_dir=str(self.vector_db_path))

            logger.info(f"Indexed {indexed_count} files, skipped {skipped_count}")

        return {
            "folder": str(validated_path.relative_to(self.root_folder)),
            "indexed": indexed_count,
            "skipped": skipped_count,
            "total": len(file_paths),
        }

    async def search(self, query: str, folder_path: str = ".", top_k: int = 5) -> dict:
        """
        Search indexed files by content.

        Args:
            query: Search query
            folder_path: Limit search to specific folder
            top_k: Number of results to return

        Returns:
            Dict with search results
        """
        if self.index is None:
            return {
                "query": query,
                "results": [],
                "message": "No files indexed yet. Please index files first.",
            }

        validated_path = self._validate_path(folder_path)
        folder_relative = str(validated_path.relative_to(self.root_folder))

        # Create query engine
        query_engine = self.index.as_query_engine(similarity_top_k=top_k)

        # Execute query
        response = query_engine.query(query)

        # Format results
        results = []
        for node in response.source_nodes:
            metadata = node.metadata
            file_path = metadata.get("file_path", "")

            # Filter by folder if specified
            if folder_relative != "." and not file_path.startswith(folder_relative):
                continue

            results.append(
                {
                    "file_path": file_path,
                    "file_name": metadata.get("file_name", ""),
                    "score": node.score,
                    "text_snippet": node.text[:500],  # First 500 chars
                }
            )

        return {
            "query": query,
            "folder": folder_relative,
            "count": len(results),
            "results": results[:top_k],
            "answer": str(response),
        }
