import logging
import re
import yaml
from pathlib import Path
from app.schemas.knowledge import KnowledgeDocument

logger = logging.getLogger("opsgraph.knowledge.loader")

class KnowledgeLoader:
    """
    Loads, parses, and normalizes enterprise knowledge documents (e.g. Markdown runbooks).
    """
    def load_markdown(self, filepath: Path) -> KnowledgeDocument:
        """
        Parses a Markdown file with YAML front matter into a KnowledgeDocument.
        """
        logger.info(f"Loading document: {filepath}")
        content = filepath.read_text(encoding="utf-8")
        
        # Parse front matter
        front_matter = {}
        markdown_body = content
        
        # Regex to match front matter
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if match:
            fm_text = match.group(1)
            markdown_body = match.group(2)
            try:
                front_matter = yaml.safe_load(fm_text)
            except Exception as e:
                logger.error(f"Error parsing front matter in {filepath}: {e}")
                raise ValueError(f"Invalid front matter in {filepath}: {e}")

        # Extract required metadata fields with fallbacks
        doc_id = front_matter.get("document_id", filepath.stem)
        doc_type = front_matter.get("document_type", "runbook")
        title = front_matter.get("title", filepath.stem)
        version = str(front_matter.get("version", "1.0"))
        
        # Package raw front matter metadata dictionary
        meta = {k: v for k, v in front_matter.items() if k not in ("document_id", "document_type", "title", "version")}

        return KnowledgeDocument(
            document_id=doc_id,
            document_type=doc_type,
            source_path=str(filepath.relative_to(filepath.parents[3]) if len(filepath.parents) > 3 else filepath),
            version=version,
            title=title,
            section=None,
            language="en",
            last_updated=front_matter.get("last_updated"),
            tags=front_matter.get("service_scope", []),
            metadata=meta,
            content=markdown_body.strip()
        )

    def load_directory(self, dirpath: Path) -> list[KnowledgeDocument]:
        """
        Recursively scans and loads all Markdown documents within a directory.
        """
        logger.info(f"Scanning directory: {dirpath}")
        documents = []
        if not dirpath.exists():
            logger.warning(f"Directory {dirpath} does not exist.")
            return []
            
        for path in dirpath.rglob("*.md"):
            try:
                doc = self.load_markdown(path)
                documents.append(doc)
            except Exception as e:
                logger.error(f"Failed to load document at {path}: {e}")
                
        return documents
