"""Unit tests for skimindex.unix wrapper modules (compress, ncbi, obitools, download)."""

from unittest.mock import MagicMock, patch

import pytest

from skimindex.unix.base import LoggedBoundCommand


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def make_lbc():
    """Return a LoggedBoundCommand wrapping a fresh MagicMock."""
    cmd = MagicMock()
    cmd.__getitem__ = MagicMock(return_value=cmd)
    return LoggedBoundCommand(cmd)


def patch_local(target_module, return_lbc=None):
    """Patch 'local' in a unix wrapper module and return a context manager."""
    lbc = return_lbc or make_lbc()
    mock_local = MagicMock()
    mock_local.__getitem__ = MagicMock(return_value=lbc._cmd)
    return patch(f"{target_module}.local", mock_local), lbc


# ──────────────────────────────────────────────
# compress.py
# ──────────────────────────────────────────────

class TestCompress:
    def _local_ctx(self, modname="skimindex.unix.compress"):
        return patch_local(modname)

    def test_pigz_returns_logged_bound_command(self):
        from skimindex.unix import compress
        cmd = MagicMock()
        cmd.__getitem__ = MagicMock(return_value=cmd)
        with patch("skimindex.unix.compress.local") as mock_local:
            mock_local.__getitem__ = MagicMock(return_value=cmd)
            result = compress.pigz("-9", "file.txt")
        assert result is not None

    def test_pigz_compress_delegates_to_pigz(self):
        from skimindex.unix import compress
        with patch.object(compress, "pigz") as mock_pigz:
            compress.pigz_compress("file.txt")
        mock_pigz.assert_called_once_with("file.txt")

    def test_pigz_decompress_adds_d_flag(self):
        from skimindex.unix import compress
        with patch.object(compress, "pigz") as mock_pigz:
            compress.pigz_decompress("file.txt.gz")
        mock_pigz.assert_called_once_with("-d", "file.txt.gz")

    def test_pigz_test_adds_t_flag(self):
        from skimindex.unix import compress
        with patch.object(compress, "pigz") as mock_pigz:
            compress.pigz_test("file.txt.gz")
        mock_pigz.assert_called_once_with("-t", "file.txt.gz")

    def test_unzip_list_adds_l_flag(self):
        from skimindex.unix import compress
        with patch.object(compress, "unzip") as mock_unzip:
            compress.unzip_list("archive.zip")
        mock_unzip.assert_called_once_with("-l", "archive.zip")

    def test_unzip_extract_adds_d_flag(self):
        from skimindex.unix import compress
        with patch.object(compress, "unzip") as mock_unzip:
            compress.unzip_extract("/output", "archive.zip")
        mock_unzip.assert_called_once_with("-d", "/output", "archive.zip")


# ──────────────────────────────────────────────
# ncbi.py
# ──────────────────────────────────────────────

class TestNcbi:
    def test_datasets_download_genome_chain(self):
        from skimindex.unix import ncbi
        with patch.object(ncbi, "datasets") as mock_datasets:
            ncbi.datasets_download_genome("--taxon", "human")
        mock_datasets.assert_called_once_with("download", "genome", "--taxon", "human")

    def test_datasets_summary_genome_chain(self):
        from skimindex.unix import ncbi
        with patch.object(ncbi, "datasets") as mock_datasets:
            ncbi.datasets_summary_genome("taxon", "Homo sapiens")
        mock_datasets.assert_called_once_with("summary", "genome", "taxon", "Homo sapiens")

    def test_datasets_download_gene_chain(self):
        from skimindex.unix import ncbi
        with patch.object(ncbi, "datasets") as mock_datasets:
            ncbi.datasets_download_gene("--taxon", "human")
        mock_datasets.assert_called_once_with("download", "gene", "--taxon", "human")

    def test_datasets_download_protein_chain(self):
        from skimindex.unix import ncbi
        with patch.object(ncbi, "datasets") as mock_datasets:
            ncbi.datasets_download_protein("--taxon", "human")
        mock_datasets.assert_called_once_with("download", "protein", "--taxon", "human")

    def test_dataformat_tsv_chain(self):
        from skimindex.unix import ncbi
        with patch.object(ncbi, "dataformat") as mock_df:
            ncbi.dataformat_tsv("--input-file", "data.json")
        mock_df.assert_called_once_with("tsv", "--input-file", "data.json")

    def test_dataformat_fasta_chain(self):
        from skimindex.unix import ncbi
        with patch.object(ncbi, "dataformat") as mock_df:
            ncbi.dataformat_fasta("--input-file", "data.json")
        mock_df.assert_called_once_with("fasta", "--input-file", "data.json")

    def test_dataformat_gff3_chain(self):
        from skimindex.unix import ncbi
        with patch.object(ncbi, "dataformat") as mock_df:
            ncbi.dataformat_gff3("--input-file", "data.json")
        mock_df.assert_called_once_with("gff3", "--input-file", "data.json")


# ──────────────────────────────────────────────
# obitools.py
# ──────────────────────────────────────────────

class TestObitools:
    def test_obik_count_prepends_count(self):
        from skimindex.unix import obitools
        with patch.object(obitools, "obik") as mock_obik:
            obitools.obik_count("-k", "21")
        mock_obik.assert_called_once_with("count", "-k", "21")

    def test_obik_filter_prepends_filter(self):
        from skimindex.unix import obitools
        with patch.object(obitools, "obik") as mock_obik:
            obitools.obik_filter("--min-count", "5")
        mock_obik.assert_called_once_with("filter", "--min-count", "5")

    def test_obiscript_prepends_s_flag(self):
        from skimindex.unix import obitools
        cmd = MagicMock()
        cmd.__getitem__ = MagicMock(return_value=cmd)
        with patch("skimindex.unix.obitools.local") as mock_local:
            mock_local.__getitem__ = MagicMock(return_value=cmd)
            obitools.obiscript("/path/to/script.lua", "--extra")
        mock_local.__getitem__.assert_called_with("obiscript")

    def test_obigrep_no_extra_args(self):
        from skimindex.unix import obitools
        cmd = MagicMock()
        cmd.__getitem__ = MagicMock(return_value=cmd)
        with patch("skimindex.unix.obitools.local") as mock_local:
            mock_local.__getitem__ = MagicMock(return_value=cmd)
            obitools.obigrep()
        mock_local.__getitem__.assert_called_with("obigrep")


# ──────────────────────────────────────────────
# download.py
# ──────────────────────────────────────────────

class TestDownload:
    def test_curl_download_passes_url(self):
        from skimindex.unix import download
        cmd = MagicMock()
        cmd.__getitem__ = MagicMock(return_value=cmd)
        with patch("skimindex.unix.download.local") as mock_local:
            mock_local.__getitem__ = MagicMock(return_value=cmd)
            download.curl_download("https://example.com/file.gz")
        mock_local.__getitem__.assert_called_with("curl")

    def test_curl_download_includes_retry(self):
        from skimindex.unix import download
        with patch.object(download, "curl") as mock_curl:
            download.curl_download("https://example.com/file")
        args = mock_curl.call_args[0]
        assert "--retry" in args
        assert "3" in args

    def test_curl_download_follows_redirects(self):
        from skimindex.unix import download
        with patch.object(download, "curl") as mock_curl:
            download.curl_download("https://example.com/file")
        args = mock_curl.call_args[0]
        assert "-L" in args

    def test_curl_download_extra_args_passed(self):
        from skimindex.unix import download
        with patch.object(download, "curl") as mock_curl:
            download.curl_download("https://example.com/file", "-o", "out.txt")
        args = mock_curl.call_args[0]
        assert "-o" in args
        assert "out.txt" in args
