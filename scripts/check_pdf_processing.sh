#!/bin/bash

# Database Status Checker - Monitor document indexing
echo "📊 Document Processing Status"
echo "=============================="

echo "📚 All indexed documents:"
docker compose exec db psql -U rag -d rag -c \
"SELECT d.id, d.source, d.title, COUNT(c.id) as chunks
 FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
 GROUP BY d.id, d.source, d.title
 ORDER BY d.id;"

echo -e "\n📈 System summary:"
docker compose exec db psql -U rag -d rag -c \
"SELECT 
  COUNT(DISTINCT d.id) as total_docs,
  COUNT(c.id) as total_chunks,
  ROUND(AVG(LENGTH(c.text))) as avg_chunk_length
 FROM documents d LEFT JOIN chunks c ON c.document_id = d.id;"

echo -e "\n⚠️ Documents without content:"
docker compose exec db psql -U rag -d rag -c \
"SELECT d.source, d.title
 FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
 WHERE c.id IS NULL;"

echo -e "\n=== Verification Complete ==="