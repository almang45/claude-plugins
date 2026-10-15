Find what will fail, slow down or be hard to operate in production.

- Load: N+1 queries, queries or result sets with no limit or pagination, quadratic work on a
  request path, work repeated where it should be cached or batched, large per-request
  allocations.
- Remote calls: missing timeouts, retries without backoff or jitter, retry storms,
  non-idempotent operations being retried, no circuit breaking around a slow dependency.
- State and rollout: migrations that lock large tables or cannot be rolled back, schema or
  message changes that old and new versions cannot both handle during a rolling deploy,
  feature flags with no off path, defaults that differ between environments.
- Resources: unbounded memory, goroutine or thread growth, connection pool exhaustion, file
  descriptor leaks, Kubernetes manifests missing requests, limits or probes.
- Observability: errors logged without context or not at all, unstructured logs on new code
  paths, new failure modes with no metric or trace, sensitive data in logs.

State the load or failure condition that triggers each issue.
