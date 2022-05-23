from itertools import accumulate
import numpy as np

import pytest

from bionumpy.chromosome_provider import ChromosomeFileStreamProvider
from npstructures.npdataclasses import VarLenArray, npdataclass


@npdataclass
class DummyClass:
    chromosome: VarLenArray
    data: np.ndarray

    def __post_init__(self):
        if not isinstance(self.chromosome, VarLenArray):
            print("#", self.chromosome)
            self.chromosome = VarLenArray(np.asanyarray([[ord(c) for c in chrom] for chrom in self.chromosome]))
        self.data = np.asanyarray(self.data)
# 
#     def __getitem__(self, idx):
#         return self.__class__(self.chromosome[idx], self.data[idx])
# 
#     def __eq__(self, other):
#         return np.all(self.chromosome == other.chromosome) and np.all(self.data == other.data)
# '
#     def __len__(self):
#         return len(self.chromosome)

    def __eq__(self, other):
        return all(np.all(s == o) for s, o in zip(self.shallow_tuple(), other.shallow_tuple()))

    @classmethod
    def concatenate(cls, objects):
        chrom_str_lens = [o.chromosome.shape[-1] for o in objects]
        max_len = max(chrom_str_lens)
        if all(l == max_len for l in chrom_str_lens):
            chroms = np.concatenate([o.chromosome for o in objects], dtype=objects[0].chromosome.dtype)
        else:
            lens = [len(o) for o in objects]
            chroms = np.zeros((sum(lens), max_len), dtype=objects[0].chromosome.dtype)
            for start, end, o, l in zip(accumulate(lens, initial=0), accumulate(lens), objects, chrom_str_lens):
                chroms[start:end, -l:] = o.chromosome
        
        return cls(chroms, np.concatenate([o.data for o in objects]))


@pytest.fixture
def buffers():
    return [DummyClass(["chr1", "chr1"], [0, 1]),
            DummyClass(["chr1", "chr2"], [2, 3]),
            DummyClass(["chr3", "chr4", "chr5"], [4, 5, 6]),
            DummyClass(["\x00chr5", "chr16"], [7, 8])]


def test_chromosome_stream(buffers):
    for val, true in zip(ChromosomeFileStreamProvider(buffers),
                         [("chr1", DummyClass(["chr1"]*3, [0, 1, 2])),
                          ("chr2", DummyClass(["chr2"], [3])),
                          ("chr3", DummyClass(["chr3"], [4])),
                          ("chr4", DummyClass(["chr4"], [5])),
                          ("chr5", DummyClass(["\x00chr5"]*2, [6, 7])),
                          ("chr16", DummyClass(["chr16"], [8]))]):
        assert val == true
