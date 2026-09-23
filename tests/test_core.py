"""Tests for the CuckooFilter class."""

import unittest

from cuckoo_filter import CuckooFilter
from cuckoo_filter.core import FilterFullError


class CuckooFilterTest(unittest.TestCase):
    def test_insert_and_contains(self):
        cf = CuckooFilter(capacity=100, seed=42)
        self.assertTrue(cf.insert(b"hello"))
        self.assertTrue(cf.contains(b"hello"))
        self.assertFalse(cf.contains(b"world"))

    def test_delete_existing_item(self):
        cf = CuckooFilter(capacity=100, seed=42)
        cf.insert(b"apple")
        self.assertTrue(cf.delete(b"apple"))
        self.assertFalse(cf.contains(b"apple"))
        self.assertEqual(cf.size, 0)

    def test_delete_non_existing_item(self):
        cf = CuckooFilter(capacity=100, seed=42)
        self.assertFalse(cf.delete(b"missing"))
        self.assertEqual(cf.size, 0)

    def test_delete_only_one_duplicate(self):
        cf = CuckooFilter(capacity=100, seed=42)
        cf.insert(b"dup")
        cf.insert(b"dup")
        self.assertEqual(cf.size, 2)
        self.assertTrue(cf.delete(b"dup"))
        self.assertTrue(cf.contains(b"dup"))
        self.assertEqual(cf.size, 1)
        self.assertTrue(cf.delete(b"dup"))
        self.assertFalse(cf.contains(b"dup"))
        self.assertEqual(cf.size, 0)

    def test_insert_many_items(self):
        cf = CuckooFilter(capacity=64, bucket_size=4, seed=7)
        items = [("item-%d" % i).encode() for i in range(100)]
        for item in items:
            cf.insert(item)
        for item in items:
            self.assertTrue(cf.contains(item), "missing %r" % item)

    def test_insert_failure_on_full_filter(self):
        # Use very small capacity so insertion fails quickly.
        cf = CuckooFilter(capacity=1, bucket_size=1, max_kicks=5, seed=123)
        inserted = 0
        with self.assertRaises(FilterFullError):
            for i in range(100):
                cf.insert(("item-%d" % i).encode())
                inserted += 1
        # At least some items were inserted before failure.
        self.assertGreater(inserted, 0)

    def test_contains_never_false_negative_after_insert(self):
        cf = CuckooFilter(capacity=50, seed=99)
        for i in range(200):
            item = ("key-%d" % i).encode()
            cf.insert(item)
            self.assertTrue(cf.contains(item))

    def test_false_positive_is_possible(self):
        # We cannot force a false positive reliably, but we can check
        # that contains on a never-inserted item returns a bool.
        cf = CuckooFilter(capacity=10, seed=5)
        result = cf.contains(b"never inserted")
        self.assertIsInstance(result, bool)

    def test_capacity_zero(self):
        cf = CuckooFilter(capacity=0, seed=1)
        self.assertEqual(cf.capacity, 0)
        with self.assertRaises(FilterFullError):
            cf.insert(b"anything")
        self.assertFalse(cf.contains(b"anything"))

    def test_invalid_constructor_args(self):
        with self.assertRaises(ValueError):
            CuckooFilter(capacity=-1)
        with self.assertRaises(ValueError):
            CuckooFilter(capacity=1, bucket_size=0)
        with self.assertRaises(ValueError):
            CuckooFilter(capacity=1, max_kicks=0)

    def test_non_bytes_item_raises_type_error(self):
        cf = CuckooFilter(capacity=10, seed=1)
        with self.assertRaises(TypeError):
            cf.insert("string")
        with self.assertRaises(TypeError):
            cf.contains("string")
        with self.assertRaises(TypeError):
            cf.delete("string")


if __name__ == "__main__":
    unittest.main()
