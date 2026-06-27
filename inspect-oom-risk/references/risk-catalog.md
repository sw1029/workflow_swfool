# OOM Risk Catalog

Use this reference to choose search patterns and classify OOM findings. Load only the relevant sections when context is tight.

## High-Signal Search Patterns

Start broad, then inspect targeted snippets:

```bash
rg -n "read_csv|read_json|read_parquet|read_table|load\\(|loads\\(|read_text|readFileSync|fs\\.readFile|Files\\.readAll|readAllBytes|collect\\(|toPandas|to_pandas|to_pylist|to_dict\\(|concat\\(|append\\(|extend\\(|cache|lru_cache|memo|Queue\\(|Pool\\(|ProcessPool|ThreadPool|Executor|submit\\(|gather\\(|workers|concurrency|batch_size|max_batch|prefetch|buffer|chunk|stream|mmap|cuda|vram|gpu_memory|device_map|max_model_len|max_new_tokens|context|token|dtype|quant|no_grad|inference_mode|empty_cache|Xmx|max-old-space-size|memory_limit|requests\\.memory|limits\\.memory|OOM|out of memory|Killed" .
```

For large artifacts, prefer metadata commands such as `find . -type f -size +100M`, `du -sh`, `parquet-tools meta`, or targeted schema inspection when available. Do not dump large file contents.

Check whether row/item/token caps apply before materialization. A `limit`, `top_k`, `sample`, `max_rows`, `max_chunks`, or filter applied after read-all conversion is a reporting finding, not a safeguard.

## CPU/RSS Patterns

- Full-file reads: loading large CSV/JSON/parquet/text/archive data into memory without projection, row filters, chunking, or streaming.
- DataFrame blowups: `concat` in loops, wide joins, `groupby` over unbounded rows, converting columnar batches to full pandas frames, or materializing nested lists.
- Result accumulation: appending all rows, model outputs, graph nodes, logs, images, or request payloads before writing/streaming.
- Incremental writes with retained state: writing per-item outputs but still keeping every output in an in-memory `results`, `rows`, `payloads`, or report list for final aggregation.
- Unbounded queues: producer faster than consumer, no max queue size, retry buffers, prefetch, or async gather over unbounded inputs.
- Multiprocessing amplification: each worker loads its own large dataset/model/cache, all futures are submitted at once, or large payloads/results are copied between parent and workers.
- Cache retention: global dictionaries, `lru_cache(maxsize=None)`, singleton loaders, memoized models, large in-memory indexes, or missing eviction.
- Archive/image expansion: compressed inputs, decompression bombs, large image decode, OCR/PDF page fanout, or temporary extracted payloads.
- Unbounded sentinels: `0 means all`, `None means no limit`, empty filters, or user-provided ID lists that bypass default sampling.

## GPU/VRAM Patterns

- Model load exceeds available VRAM: large model, full precision dtype, missing quantization, duplicated model instances, or per-worker model replication.
- Context/KV cache growth: high max context/model length, high max new tokens, large batch, beam search, speculative decoding, or many concurrent requests.
- Token accounting gaps: character-based prompt truncation without tokenizer-aware checks, or output/token limits that can exceed the serving context window.
- Training/inference graph retention: missing `torch.no_grad()` or `torch.inference_mode()` for inference, storing tensors with gradients, not detaching outputs.
- Device placement mistakes: implicit `.cuda()`, `device_map="auto"` surprises, CPU-to-GPU copies of large batches, mixed devices causing duplication.
- Fragmentation and lifecycle: repeated model creation, pipeline recreation per request, no process isolation, or relying on `empty_cache()` as the primary fix.
- Serving config: high `gpu_memory_utilization`, unlimited request concurrency, large prefill, high parallelism, or no fallback for smaller batch/context.

## Build, Test, and Runtime Environment

- CI/build OOM: parallel compile/test defaults, bundler heap limits, JVM/Node heap flags, TypeScript/webpack/Vite memory, Docker build context bloat.
- Container mismatch: memory request/limit absent or lower than documented workload; app detects host RAM instead of cgroup limit.
- Kubernetes/serverless: no pod memory limit, aggressive autoscaling concurrency, missing liveness behavior for OOMKilled loops.
- Browser/frontend: retaining large blobs/images, virtualized lists missing, canvas/image buffers, WebGL textures, object URLs not revoked.
- Database/search: unbounded query results, loading entire result sets client-side, in-memory sort/join, large vector indexes without mmap/read-only mode.

## Safeguards To Credit

- Limits applied before I/O or allocation: pushed-down filters, selected columns, server-side pagination, bounded queues, bounded executor windows.
- Streaming with bounded batch size: iterators, `chunksize`, `iter_batches`, streaming JSONL/zstd readers, mmap/read-only indexes.
- Runtime adaptation: memory preflight, cgroup-aware limits, GPU/RSS telemetry, adaptive batch/context downshift, explicit OOM fallback commands.
- Lifecycle cleanup: single model/index ownership, clear unload points, worker process recycling, temporary artifact cleanup.
- Tests and checks: memory smoke tests, large fixture avoidance, cap-regression tests, CI limits, and documented runbooks.

## Severity Heuristics

- Raise severity when a risky path is a default command, request path, CI job, or documented workflow.
- Raise severity when the scaling input is user-controlled or known large from repo docs/artifact sizes.
- Lower severity when the code already streams, caps rows/items/tokens, projects columns, uses mmap, enforces queue limits, or documents safe defaults.
- Raise severity when a cap is enforced only after the large allocation it is supposed to protect.
- Mark confidence low when only names imply large scale and no code/config path was inspected.
