import logging
import re
from app.schemas.knowledge import KnowledgeDocument, KnowledgeChunk

logger = logging.getLogger("opsgraph.knowledge.chunker")

class HeadingAwareChunker:
    """
    Deterministically splits Markdown documents by structural headings,
    preserving context and appending inherited front-matter metadata.
    """
    def __init__(self, max_chunk_chars: int = 1000, overlap_chars: int = 100):
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars

    def chunk_document(self, doc: KnowledgeDocument) -> list[KnowledgeChunk]:
        """
        Parses document content, splits by H1/H2/H3 headings, and sub-chunks if text exceeds max size.
        """
        logger.info(f"Chunking document '{doc.document_id}'")
        lines = doc.content.splitlines()
        
        sections = []
        current_heading = "Introduction"
        current_heading_line = doc.title
        current_body_lines = []

        for line in lines:
            # Check if line is a markdown heading
            match = re.match(r"^(#{1,4})\s+(.*)$", line)
            if match:
                # Save previous section if there was content
                if current_body_lines:
                    sections.append((current_heading, current_heading_line, "\n".join(current_body_lines).strip()))
                    current_body_lines = []
                # Update current heading details
                current_heading = match.group(2).strip()
                current_heading_line = line.strip()
            else:
                current_body_lines.append(line)
        
        # Append last section
        if current_body_lines or not sections:
            sections.append((current_heading, current_heading_line, "\n".join(current_body_lines).strip()))

        chunks = []
        seq = 1

        # Process each section, dividing further if exceeding max size
        for heading, heading_line, body in sections:
            if not body:
                continue
            
            sub_bodies = []
            if len(body) <= self.max_chunk_chars:
                sub_bodies.append(body)
            else:
                # Chunk with overlap
                start = 0
                while start < len(body):
                    end = start + self.max_chunk_chars
                    sub_bodies.append(body[start:end])
                    start += self.max_chunk_chars - self.overlap_chars

            for idx, content in enumerate(sub_bodies):
                chunk_id = f"{doc.document_id}-CHUNK-{seq:03d}"
                seq += 1
                
                # Inherit metadata
                meta = dict(doc.metadata)
                meta.update({
                    "document_id": doc.document_id,
                    "section": heading,
                    "heading": heading_line,
                    "service_scope": doc.tags,
                    "version": doc.version
                })

                chunks.append(
                    KnowledgeChunk(
                        chunk_id=chunk_id,
                        document_id=doc.document_id,
                        section=heading,
                        heading=heading_line,
                        content=content.strip(),
                        metadata=meta
                    )
                )

        logger.info(f"Split document '{doc.document_id}' into {len(chunks)} chunks.")
        return chunks
