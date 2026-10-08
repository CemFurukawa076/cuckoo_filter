# Cuckoo Filter

A probabilistic set membership data structure with deletion support, implemented in pure Python with no third-party dependencies.

```python
from cuckoo_filter import CuckooFilter

cf = CuckooFilter(capacity=1000)
cf.insert(b"alice")
cf.contains(b"alice")   # True
cf.delete(b"alice")
cf.contains(b"alice")   # False
```

The library exports one class, `CuckooFilter`, and one exception, `FilterFullError`, from `cuckoo_filter.core`. The package root `cuckoo_filter` re-exports the class.

## Why this exists

A regular hash set stores full items and answers membership exactly, but for very large sets the memory overhead can be prohibitive. Bloom filters use less memory but cannot delete items. A cuckoo filter gives the same space advantage as a Bloom filter while allowing deletions, at the cost of allowing false positives: `contains` may return `True` for an item that was never inserted, but it will never return `False` for an item that was inserted.

The trade-off here is that the filter stores only fingerprints, not the original items. This means deletion requires the caller to supply the exact item again; the filter cannot enumerate what it contains. It also means that if two different items have the same fingerprint, deleting one may remove the other's fingerprint and cause a false negative later. This is inherent to fingerprint-based filters and is the main awkward edge to be aware of.

## Usage details

- All items must be bytes-like (`bytes`, `bytearray`, etc.). Strings must be encoded first.
- `insert` returns `True` and raises `FilterFullError` if the filter is too full to place the item after a fixed number of relocation attempts.
- Duplicate inserts are allowed and increase the internal size counter, but the filter stores identical fingerprints. Deleting one duplicate removes a single fingerprint.
- `delete` returns `True` if it found and removed a matching fingerprint, otherwise `False`.
- The false positive rate depends on the fingerprint size (64 bits here) and the load factor; as the filter fills, false positives become more likely.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

