import bz2
import pickle
import time

import pipeline.extern.asizeof as asizeof
import pipeline.infrastructure.logging as logging

LOG = logging.get_logger(__name__)


# object compression/decopmpression utility
class CompressedObj(object):
    def __init__(self, obj, protocol=pickle.HIGHEST_PROTOCOL, compresslevel=9):
        self.compressed = compress_object(obj, protocol=protocol, compresslevel=compresslevel)

    def decompress(self):
        return decompress_object(self.compressed)


def compress_object(obj, protocol=pickle.HIGHEST_PROTOCOL, compresslevel=9):
    start = time.time() if LOG.isEnabledFor(logging.DEBUG) else None

    try:
        compressed = bz2.compress(pickle.dumps(obj, protocol), compresslevel=compresslevel)
    except Exception:
        compressed = obj

    if LOG.isEnabledFor(logging.DEBUG):
        size_org = asizeof.asizeof(obj)
        size_comp = asizeof.asizeof(compressed)
        LOG.debug('compress: size before {0} after {1} ({2} %)'.format(size_org, size_comp, float(size_comp)/float(size_org) * 100))
        end = time.time()
        LOG.debug('elapsed {0} sec'.format(end - start))

    return compressed


def decompress_object(obj):
    start = time.time() if LOG.isEnabledFor(logging.DEBUG) else None

    decompressed = pickle.loads(bz2.decompress(obj))

    if LOG.isEnabledFor(logging.DEBUG):
        size_comp = asizeof.asizeof(obj)
        size_org = asizeof.asizeof(decompressed)
        LOG.debug('decompress: size before {0} after {1} ({2} %)'.format(size_org, size_comp, float(size_comp)/float(size_org) * 100))
        end = time.time()
        LOG.debug('elapsed {0} sec'.format(end - start))

    return decompressed


class CompressedIter(object):
    def __init__(self, obj):
        self.obj = obj
        self._count = 0

    def __next__(self):
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
    def __iter__(self):
        return CompressedIter(self)
