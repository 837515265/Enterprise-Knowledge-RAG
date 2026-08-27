# Dev ES Huawei Cloud CSS Adaptation

## Background

Dev Nacos has been changed to point to the same Elasticsearch/CSS service as SIT. The Python retrieval service therefore needs to use Huawei Cloud CSS vector index creation, bulk writes, and vector query syntax when `ES_VECTOR_TYPE=css`.

## Updated Files

- `src/danbao_poc/es_store.py`
  - Elasticsearch client creation
  - CSS vector mapping generation
  - ES bulk write path
  - CSS vector query branch
  - refresh timeout after indexing

## What Changed

1. Elasticsearch client

   `client()` now builds the client with a `hosts` list, supports comma-separated ES URLs, and passes:

   ```python
   verify_certs=False
   ssl_show_warn=False
   ```

   This matches the common Huawei Cloud CSS access style for internal HTTP/HTTPS clusters.

2. CSS vector index mapping

   When `ES_VECTOR_TYPE=css`, new indices use Huawei Cloud CSS vector settings:

   ```yaml
   settings:
     index:
       vector: "true"
       number_of_shards: 1
       number_of_replicas: 0
   ```

   The `embedding_vector` field is created as:

   ```json
   {
     "type": "vector",
     "dimension": 1024,
     "indexing": true,
     "algorithm": "GRAPH",
     "metric": "cosine"
   }
   ```

   `dimension` still follows `EMBEDDING_DIMENSION`. `metric` can be overridden with `ES_VECTOR_METRIC`.

3. Vector indexing default

   `ES_VECTOR_INDEXING` now defaults to `true` in CSS mode. This makes CSS mode use GRAPH vector indexing and CSS native vector query by default.

   To force the old brute-force CSS query path, set:

   ```env
   ES_VECTOR_INDEXING=false
   ```

4. Bulk writes

   The six ES write paths now use `elasticsearch.helpers.bulk()` instead of per-document `es.index()`:

   - chunk index
   - field index
   - QA index
   - section summary index
   - anchor index
   - knowledge unit index

   Bulk chunk size is controlled by:

   ```env
   ES_BULK_CHUNK_SIZE=500
   ES_BULK_REQUEST_TIMEOUT=3600
   ```

5. CSS vector query

   When `ES_VECTOR_TYPE=css` and `ES_VECTOR_INDEXING=true`, vector retrieval uses:

   ```json
   {
     "query": {
       "vector": {
         "embedding_vector": {
           "vector": [0.1, 0.2],
           "topk": 10
         }
       }
     }
   }
   ```

   Existing filters are still passed into the vector query's `filter` clause.

## Deployment Notes

Dev Nacos should include:

```yaml
ES_VECTOR_TYPE: css
ES_VECTOR_INDEXING: "true"
```

If the target ES already has old indices created with `dense_vector` or `vector indexing=false`, those mappings cannot be changed in place. Delete and rebuild the affected indices, or use new index names.

Affected index names:

- `knowledge_chunks_v1`
- `knowledge_fields_v1`
- `knowledge_qa_v1`
- `section_summary_v1`
- `knowledge_anchor_v1`
- `knowledge_unit_v1`

## Verification

Executed locally:

```powershell
$env:PYTHONPATH='D:\pyproject\bisheng\danbao-poc\src'
.\.venv\Scripts\python.exe -m compileall -q src\danbao_poc
```

Also ran a lightweight monkeypatch check to verify bulk action shape:

```text
_index/_id/_routing + document fields
```

