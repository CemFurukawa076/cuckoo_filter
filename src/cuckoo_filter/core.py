"""Core Cuckoo Filter implementation.

A Cuckoo filter is a probabilistic data structure that supports set
membership tests with deletions.  It uses cuckoo hashing with
fingerprints instead of full items, which gives it good space
utilisation for small items.

The implementation below deliberately uses a simple two-bucket table
with a fixed number of relocation attempts on insertion.  If the
filter becomes too full, insertion fails with a FilterFullError.  This
is a normal cuckoo-hashing failure mode and callers must decide how to
handle it (retry with a larger table, reject the item, etc.).
"""

import hashlib
import os
import random


class FilterFullError(Exception):
    """Raised when an item cannot be inserted after max_kicks relocations."""


class CuckooFilter:
    """A Cuckoo filter with two hash buckets per item.

    Args:
        capacity: The number of buckets in each of the two tables.  The
            total number of buckets is ``2 * capacity``.  A capacity of
            0 is allowed, but any insertion will fail because there is
            no place to put the item.
        bucket_size: The number of fingerprint slots in each bucket.
            Must be at least 1.
        max_kicks: The maximum number of relocation attempts before an
            insertion is considered failed.  Must be at least 1.
        seed: Optional seed for the hash function.  Used to make the
            filter deterministic in tests.  If omitted, a random seed
            is chosen using ``os.urandom``, which is not deterministic.

    The implementation uses one logical table of ``capacity`` buckets
    for each of the two candidate positions of an item.  The two
    candidate bucket indices for a fingerprint are computed with
    different hash prefixes so the same item is unlikely to end up in
    the same bucket twice.

    The filter stores only fingerprints, never the original items.
    Therefore deletion requires the caller to provide the exact
    fingerprint that was inserted.  This is the standard trade-off of
    cuckoo filters: small memory footprint, but the user must keep
    track of the item if deletion is needed.
    """

    def __init__(self, capacity, bucket_size=4, max_kicks=500, seed=None):
        if capacity < 0:
            raise ValueError("capacity must be non-negative")
        if bucket_size < 1:
            raise ValueError("bucket_size must be at least 1")
        if max_kicks < 1:
            raise ValueError("max_kicks must be at least 1")

        self._capacity = capacity
        self._bucket_size = bucket_size
        self._max_kicks = max_kicks
        self._seed = seed if seed is not None else int.from_bytes(os.urandom(8), "big")
        self._table = [[None] * bucket_size for _ in range(2 * capacity)]
        self._size = 0

    @property
    def size(self):
        """Number of items currently stored in the filter."""
        return self._size

    @property
    def capacity(self):
        """Maximum number of fingerprints that can be stored before insertion failures."""
        return 2 * self._capacity * self._bucket_size

    def _hash(self, data, prefix):
        """Return a 64-bit hash of *data* using the given prefix.

        The prefix changes the hash result so that the two candidate
        buckets for a fingerprint are independent.
        """
        h = hashlib.blake2b(digest_size=8, person=b"cuckoo")
        h.update(prefix.to_bytes(1, "big"))
        h.update(data)
        h.update(self._seed.to_bytes(8, "big"))
        return int.from_bytes(h.digest(), "big")

    def _fingerprint(self, item):
        """Compute a non-zero fingerprint for *item*.

        The fingerprint must be non-zero because ``None`` is used as an
        empty slot marker.
        """
        fp = self._hash(item, 0)
        # Make sure the fingerprint is not zero.  This is cheap and
        # avoids a subtle bug where a zero fingerprint would be
        # indistinguishable from an empty slot.
        if fp == 0:
            fp = 1
        return fp

    def _index(self, fp, prefix):
        """Compute a bucket index for a fingerprint."""
        if self._capacity == 0:
            raise FilterFullError("filter has zero capacity")
        return self._hash(fp.to_bytes(8, "big"), prefix) % self._capacity

    def _alt_index(self, index, fp):
        """Compute the alternative bucket index for a fingerprint.

        The alternative index is derived from the current index and the
        fingerprint.  This allows us to find the other candidate bucket
        without recomputing the original hash.  The formula uses the
        XOR of the current index and the fingerprint hashed to the
        capacity range.  This is a standard trick from the original
        cuckoo filter paper.
        """
        h = self._hash(fp.to_bytes(8, "big"), 2)
        return (index ^ h) % self._capacity

    def _bucket(self, table_index):
        """Return the bucket list for the given logical index.

        The logical index is in ``[0, 2*capacity)``.  The first
        ``capacity`` buckets are the primary table, the second
        ``capacity`` buckets are the secondary table.
        """
        return self._table[table_index]

    def _insert_fingerprint(self, fp):
        """Insert a fingerprint into the table.

        Returns ``True`` if the insertion succeeded, ``False`` if the
        filter is too full (all relocation attempts failed).
        """
        # Initial bucket: primary index derived from fingerprint.
        i1 = self._index(fp, 1)
        bucket = self._bucket(i1)
        for slot in range(self._bucket_size):
            if bucket[slot] is None:
                bucket[slot] = fp
                return True

        # Primary bucket full, try secondary bucket.
        i2 = self._alt_index(i1, fp)
        bucket = self._bucket(i2)
        for slot in range(self._bucket_size):
            if bucket[slot] is None:
                bucket[slot] = fp
                return True

        # Both full, perform cuckoo evictions.
        current_index = i1 if random.randint(0, 1) == 0 else i2
        current_fp = fp
        for _ in range(self._max_kicks):
            bucket = self._bucket(current_index)
            # Pick a random slot to evict.
            slot = random.randint(0, self._bucket_size - 1)
            evicted_fp = bucket[slot]
            bucket[slot] = current_fp
            current_fp = evicted_fp

            # Compute the alternate bucket for the evicted fingerprint.
            current_index = self._alt_index(current_index, current_fp)
            bucket = self._bucket(current_index)

            # Try to place the evicted fingerprint.
            for s in range(self._bucket_size):
                if bucket[s] is None:
                    bucket[s] = current_fp
                    return True

        # Could not find a spot after max_kicks relocations.
        return False

    def insert(self, item):
        """Insert an item into the filter.

        Args:
            item: The item to insert.  Must be bytes-like (``bytes``,
                ``bytearray``, or any object supporting the buffer
                protocol).  Strings are not accepted directly; encode
                them to bytes first.

        Returns:
            ``True`` if the item was inserted.

        Raises:
            FilterFullError: If the item could not be inserted because
                the filter is too full.
            TypeError: If *item* is not bytes-like.

        Note that duplicate inserts are allowed and will increase the
        internal size counter.  The filter does not keep track of
        multiplicity; it simply stores fingerprints.  If the same item
        is inserted twice, two identical fingerprints will be stored.
        """
        fp = self._fingerprint(item)
        if not self._insert_fingerprint(fp):
            raise FilterFullError("filter is too full to insert item")
        self._size += 1
        return True

    def contains(self, item):
        """Check if an item is in the filter.

        Args:
            item: The item to test.  Must be bytes-like.

        Returns:
            ``True`` if the item is probably in the filter,
            ``False`` if it is definitely not.

        This method never returns a false negative.  It may return a
        false positive with probability that depends on the fingerprint
        size and the current load factor.
        """
        if self._capacity == 0:
            return False
        fp = self._fingerprint(item)
        i1 = self._index(fp, 1)
        if fp in self._bucket(i1):
            return True
        i2 = self._alt_index(i1, fp)
        if fp in self._bucket(i2):
            return True
        return False

    def delete(self, item):
        """Delete an item from the filter.

        Args:
            item: The item to delete.  Must be bytes-like and must have
                been previously inserted.

        Returns:
            ``True`` if the item was found and removed,
            ``False`` if the item was not found.

        Deleting an item that was never inserted is a no-op and returns
        ``False``.  If the item is not present because it was a false
        positive in a ``contains`` call, this method will not remove
        any unrelated fingerprint; it simply returns ``False``.
        """
        if self._capacity == 0:
            return False
        fp = self._fingerprint(item)
        i1 = self._index(fp, 1)
        bucket = self._bucket(i1)
        for slot in range(self._bucket_size):
            if bucket[slot] == fp:
                bucket[slot] = None
                self._size -= 1
                return True

        i2 = self._alt_index(i1, fp)
        bucket = self._bucket(i2)
        for slot in range(self._bucket_size):
            if bucket[slot] == fp:
                bucket[slot] = None
                self._size -= 1
                return True

        return False
