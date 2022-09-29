import os
from itertools import chain
import pytest
import numpy as np
from npstructures.testing import assert_npdataclass_equal 
from bionumpy.sequences import from_sequence_array
from bionumpy.file_buffers import FastQBuffer, TwoLineFastaBuffer
from bionumpy.datatypes import Interval, SNP, SequenceEntry, Variant
from bionumpy.delimited_buffers import BedBuffer, VCFBuffer, GfaSequenceBuffer, get_bufferclass_for_datatype
from bionumpy.files import bnp_open
from .buffers import fastq_buffer, twoline_fasta_buffer, bed_buffer, vcf_buffer, vcf_buffer2, gfa_sequence_buffer, combos
from bionumpy.parser import chunk_lines
from bionumpy.bnpdataclass import bnpdataclass
import bionumpy as bnp

np.seterr(all='raise')


def chunk_from_text(text):
    return np.frombuffer(bytes(text, encoding="utf8"), dtype=np.uint8)


@pytest.mark.parametrize("buffer_name", ["bed", "vcf2", "vcf", "fastq", "fasta", "gfa_sequence"])
def test_buffer_read(buffer_name):
    buf, true_data, buf_type = combos[buffer_name]
    data = buf_type.from_raw_buffer(buf).get_data()
    for line, true_line in zip(data, true_data):
        assert_npdataclass_equal(line, true_line)


@pytest.mark.parametrize("buffer_name", ["fasta", "fastq", "multiline_fasta"])  # "bed", "vcf2", "vcf", "fastq", "fasta"])
def test_buffer_write(buffer_name):
    true_buf, data, buf_type = combos[buffer_name]
    if buffer_name == "multiline_fasta":
        buf_type.n_characters_per_line = 6
    print(data)
    data = buf_type.dataclass.stack_with_ragged(data)
    buf = buf_type.from_data(data)
    print(buf.to_string())
    print(true_buf.to_string())
    assert np.all(true_buf == buf)


@pytest.mark.parametrize("file", ["example_data/reads.fq", "example_data/big.fq.gz"])
@pytest.mark.parametrize("chunk_size", [100, 5000000])
def test_buffered_writer_ctx_manager(file, chunk_size):

    file_path = "./tmp.fq"
    true_stream = bnp_open('example_data/reads.fq').read_chunks()

    with bnp_open(file_path, mode='w') as f:
        f.write(true_stream)

    true_stream = bnp_open('example_data/reads.fq').read_chunks()
    fq_stream = bnp_open(file_path)
    for fq_item, true_item in zip(fq_stream, true_stream):
        assert fq_item == true_item

    os.remove(file_path)


def test_custom_read():
    from npstructures import npdataclass

    @bnpdataclass
    class SampleDC:
        sequence_aa: str
        sequence: str

    for extension, delimiter in {"tsv": "\t", "csv": ","}.items():
        path = f"./tmp.{extension}"
        with open(path, 'w') as file:
            file.writelines(f"sequence{delimiter}sequence_aa\nAACCTAGGC{delimiter}ATF\nAACCTAGGC{delimiter}ATF")

        data = bnp_open(path, buffer_type=get_bufferclass_for_datatype(SampleDC, delimiter=delimiter, has_header=True)).read()
        assert [s.to_string() for s in data.sequence] == ["AACCTAGGC", "AACCTAGGC"]
        assert [s.to_string() for s in data.sequence_aa] == ["ATF", "ATF"]

        os.remove(path)


def test_raises_error_for_unsupported_types():
    with pytest.raises(RuntimeError):
        bnp_open("tmp.airr")

    with pytest.raises(RuntimeError):
        bnp_open('tmp.csv')


def test_twoline_fasta_buffer(twoline_fasta_buffer):
    buf = TwoLineFastaBuffer.from_raw_buffer(twoline_fasta_buffer)
    seqs = buf.get_sequences()
    assert from_sequence_array(seqs) == ["CTTGTTGA", "CGG"]


def test_fastq_buffer(fastq_buffer):
    buf = FastQBuffer.from_raw_buffer(fastq_buffer)
    seqs = buf.get_sequences()
    assert from_sequence_array(seqs) == ["CTTGTTGA", "CGG"]


def test_gfa_sequence_buffer(gfa_sequence_buffer):
    buf = GfaSequenceBuffer.from_raw_buffer(gfa_sequence_buffer)
    entries = list(buf.get_sequences())
    true = [
        SequenceEntry.single_entry("id1", "AACCTTGG"),
        SequenceEntry.single_entry("id4", "ACTG")
    ]
    for entry, t in zip(entries, true):
        assert_npdataclass_equal(entry, t)

@pytest.mark.skip("Replaced")
def test_vcf_buffer(vcf_buffer):
    buf = VCFBuffer.from_raw_buffer(vcf_buffer)
    snps = list(buf.get_snps())
    true = [SNP("chr1", 88361, "A", "G"),
            SNP("chr1", 887559, "A", "C"),
            SNP("chr2", 8877, "A", "G")]
    print(true)
    print(snps)
    assert snps == true

@pytest.mark.skip("Replaced")
def test_vcf_buffer2(vcf_buffer2):
    buf = VCFBuffer.from_raw_buffer(vcf_buffer2)
    variants = buf.get_variants()
    print(variants)
    true = [SNP("chr1", 88361, "A", "G"),
            SNP("chr1", 887559, "A", "CAA"),
            SNP("chr2", 8877, "AGG", "C")]
    assert list(variants) == true


def test_line_chunker(vcf_buffer2):
    lines = list(chain.from_iterable(chunk_lines([VCFBuffer.from_raw_buffer(vcf_buffer2).get_data()], n_lines=1)))
    true = [Variant.single_entry("chr1", 88361, "A", "G"),
            Variant.single_entry("chr1", 887559, "A", "CAA"),
            Variant.single_entry("chr2", 8877, "AGG", "C")]
    for line, t in zip(lines, true):
        assert_npdataclass_equal(line, t)


def test_read_chunk_after_read_chunks_returns_empty_dataclass():
    file = bnp.open("example_data/reads.fq")
    chunks = list(file.read_chunks())
    new_chunk = file.read_chunk()
    assert isinstance(new_chunk, type(chunks[0]))


def test_read_gtf():
    file = bnp.open("example_data/small.gtf")
    chunk = file.read_chunk()
    assert True