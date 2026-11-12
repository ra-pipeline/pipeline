"""Compression helpers for objects stored in single-dish pipeline results."""

from __future__ import annotations

import bz2
import pickle
import time
from typing import Any
from logging import Logger

import pipeline.infrastructure.logging as logging
from pipeline.infrastructure.utils import get_obj_size

LOG: Logger = logging.get_logger(__name__)


# object compression/decopmpression utility
class CompressedObj:
    """Store an object in compressed form and provide access to its value."""

    def __init__(
        self,
        obj: Any,
        protocol: int = pickle.HIGHEST_PROTOCOL,
        compresslevel: int = 9,
    ):
        """Generate compressed object instance from given object.

        Compression is done by serializing the object with pickle
        and then compressing the serialized data with bz2 module.
        The object is immediately compressed.

        Args:
            obj: Any picklable object.
            protocol: Protocol flag for pickling. Defaults to pickle.HIGHEST_PROTOCOL.
            compresslevel: Compression level. Defaults to 9.
        """
        self.compressed: Any = compress_object(obj, protocol=protocol, compresslevel=compresslevel)

    def decompress(self) -> Any:
        """Return the uncompressed object."""
        return decompress_object(self.compressed)


def compress_object(
    obj: Any,
    protocol: int = pickle.HIGHEST_PROTOCOL,
    compresslevel: int = 9,
) -> Any:
    """Compress an object, returning it unchanged if compression fails.

    Args:
        obj: Any picklable object.
        protocol: Protocol flag for pickling. Defaults to pickle.HIGHEST_PROTOCOL.
        compresslevel: Compression level. Defaults to 9.

    Returns:
        The compressed object, or the original object if compression fails.
    """
    size_org = get_obj_size(obj)
    start = time.time()
    try:
        compressed = bz2.compress(pickle.dumps(obj, protocol), compresslevel=compresslevel)
    except Exception:
        compressed = obj
    end = time.time()
    size_comp = get_obj_size(compressed)
    LOG.debug('compress: size before {0} after {1} ({2} %)'.format(size_org, size_comp, float(size_comp)/float(size_org) * 100))
    LOG.debug('elapsed {0} sec'.format(end - start))
    return compressed


def decompress_object(obj: bytes) -> Any:
    """Decompress bytes and deserialize the contained object.

    Args:
        obj: Compressed bytes representing a pickled object.

    Returns:
        The original uncompressed object.
    """
    size_comp = get_obj_size(obj)
    start = time.time()
    decompressed = pickle.loads(bz2.decompress(obj))
    end = time.time()
    size_org = get_obj_size(decompressed)
    LOG.debug('decompress: size before {0} after {1} ({2} %)'.format(size_org, size_comp, float(size_comp)/float(size_org) * 100))
    LOG.debug('elapsed {0} sec'.format(end - start))
    return decompressed


class CompressedIter:
    """Iterate over a list, decompressing any compressed objects it contains."""

    def __init__(self, obj: list[Any]):
        """Initialize the iterator with a list of objects.

        Args:
            obj: A list of objects, some of which may be instances of CompressedObj.
        """
        self.obj: list[Any] = obj
        self._count: int = 0

    def __next__(self) -> Any:
        """Return the next value, decompressing it when necessary."""
        if self._count < len(self.obj):
            v = self.obj[self._count]
            self._count += 1
            if isinstance(v, CompressedObj):
                return v.decompress()
            else:
                return v
        else:
            raise StopIteration()


class CompressedList(list):
    """A list that decompresses its members during iteration."""

    def __iter__(self) -> CompressedIter:
        """Return an iterator that decompresses compressed members."""
        return CompressedIter(self)
