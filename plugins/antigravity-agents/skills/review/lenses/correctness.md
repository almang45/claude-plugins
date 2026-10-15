Find code that returns a wrong result, crashes, hangs or corrupts state.

- Logic and boundaries: inverted or incomplete conditions, off-by-one errors, the wrong
  operator or unit, integer overflow, float equality, time zone and encoding mistakes.
- Absent and empty values: null, nil or None dereferences, empty collections, zero values
  that mean "unset", unchecked casts.
- Error handling: swallowed or discarded errors, the wrong error returned, a partial failure
  that leaves state half-written, missing rollback or cleanup on the error path.
- Concurrency: data races, check-then-act, lock ordering, leaked goroutines, threads or tasks,
  missing cancellation, blocking calls made while holding a lock.
- Resources: files, connections, response bodies or cursors left open, especially on early
  returns and error paths.
- Contracts: callers broken by a changed signature, return value, default or side effect;
  serialization or schema changes that existing data or clients cannot read.

Trace each suspect back to the inputs that trigger it before you report it.
