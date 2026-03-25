"""Unit tests for skimindex.config.validate module."""

import pytest

import skimindex.log as _log_mod
from skimindex.config import Config, validate, validate_or_raise, ConfigValidationError


@pytest.fixture(autouse=True)
def reset_log_state():
    """Ensure any log state changes made by Config() are cleaned up."""
    original_level = _log_mod.LOG_LEVEL
    yield
    if _log_mod._logfile:
        _log_mod.closelogfile()
    _log_mod.LOG_LEVEL = original_level
    _log_mod._logfile = None
    _log_mod._mirror_to_stderr = False
    _log_mod._logeverything = False
    _log_mod._original_stderr = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _cfg(toml: bytes, tmp_path) -> Config:
    p = tmp_path / "skimindex.toml"
    p.write_bytes(toml)
    return Config(p)


def _has_error(errors, section, key):
    """Return True if errors contains an entry with matching section and key."""
    return any(e.section == section and e.key == key for e in errors)


# Minimal valid base config used as a foundation for many tests
BASE = b"""
[local_directories]
genbank  = "genbank"
raw_data = "raw_data"
processed_data = "processed_data"
indexes = "indexes"
stamp   = "stamp"
log     = "log"

[processed_data]
directory = "processed_data"

[indexes]
directory = "indexes"

[stamp]
directory = "stamp"

[source.ncbi]
directory = "genbank"

[source.genbank]
directory = "genbank"
divisions = ["bct", "pln"]

[source.internal]
directory = "raw_data"

[role.decontamination]
directory = "decontamination"
run = "prepare_ok"

[processing.split_ok]
type   = "split"
output = "split@decontamination"
size   = 200

[processing.prepare_ok]
output = "prepared@decontamination"
steps  = ["split_ok"]
"""

VALID_DATA = b"""
[data.human]
source           = "ncbi"
role             = "decontamination"
example          = true
taxon            = "human"
"""


def _valid(tmp_path) -> Config:
    return _cfg(BASE + VALID_DATA, tmp_path)


# ===========================================================================
# A. Data sections
# ===========================================================================

class TestDataSectionValidation:
    def test_A1_source_required(self, tmp_path):
        toml = BASE + b"[data.x]\nrole = \"decontamination\"\nexample = true\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "source")

    def test_A2_role_required(self, tmp_path):
        toml = BASE + b"[data.x]\nsource = \"ncbi\"\ntaxon = \"human\"\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "role")

    def test_A3_invalid_source(self, tmp_path):
        toml = BASE + b"[data.x]\nsource = \"unknown\"\nrole = \"decontamination\"\nexample = true\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "source")

    def test_A4_invalid_role(self, tmp_path):
        toml = BASE + b"[data.x]\nsource = \"ncbi\"\nrole = \"unknown\"\ntaxon = \"human\"\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "role")

    def test_A5_ncbi_requires_taxon(self, tmp_path):
        toml = BASE + b"[data.x]\nsource = \"ncbi\"\nrole = \"decontamination\"\nexample = true\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "taxon")

    def test_A6_decontamination_requires_example(self, tmp_path):
        toml = BASE + b"[data.x]\nsource = \"ncbi\"\nrole = \"decontamination\"\ntaxon = \"human\"\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "example")

    def test_A6_example_must_be_bool(self, tmp_path):
        toml = BASE + b"[data.x]\nsource = \"ncbi\"\nrole = \"decontamination\"\ntaxon = \"human\"\nexample = \"yes\"\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "example")

    def test_A7_genbank_divisions_absent_is_ok(self, tmp_path):
        toml = BASE + b"[data.x]\nsource = \"genbank\"\nrole = \"decontamination\"\nexample = true\n"
        errors = validate(_cfg(toml, tmp_path))
        assert not _has_error(errors, "data.x", "divisions")

    def test_A8_genbank_divisions_must_be_subset(self, tmp_path):
        toml = BASE + b"[data.x]\nsource = \"genbank\"\nrole = \"decontamination\"\nexample = true\ndivisions = [\"xyz\"]\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "divisions")

    def test_A8_valid_divisions_subset_no_error(self, tmp_path):
        toml = BASE + b"[data.x]\nsource = \"genbank\"\nrole = \"decontamination\"\nexample = true\ndivisions = [\"bct\"]\n"
        errors = validate(_cfg(toml, tmp_path))
        assert not _has_error(errors, "data.x", "divisions")

    def test_A9_genbank_by_species_true_warns(self, tmp_path):
        toml = BASE + b"[data.x]\nsource = \"genbank\"\nrole = \"decontamination\"\nexample = true\nby_species = true\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "by_species")

    def test_A10_run_must_reference_existing_processing(self, tmp_path):
        toml = BASE + VALID_DATA + b"[data.extra]\nsource=\"ncbi\"\nrole=\"decontamination\"\nexample=true\ntaxon=\"t\"\nrun=\"no_such_proc\"\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.extra", "run")

    def test_A10_run_processing_must_have_directory(self, tmp_path):
        toml = BASE + b"""
[processing.no_dir]
type = "split"
size = 100

[data.x]
source  = "ncbi"
role    = "decontamination"
example = true
taxon   = "human"
run     = "no_dir"
"""
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "run")

    def test_valid_data_section_no_errors(self, tmp_path):
        errors = validate(_valid(tmp_path))
        data_errors = [e for e in errors if e.section.startswith("data.")]
        assert data_errors == []


# ===========================================================================
# B. Role sections
# ===========================================================================

class TestRoleSectionValidation:
    def test_B11_directory_required(self, tmp_path):
        toml = b"""
[local_directories]
genbank = "genbank"

[source.ncbi]
directory = "genbank"

[role.decontamination]
run = "prepare_ok"

[processing.prepare_ok]
output = "prepared@decontamination"
steps = []
"""
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "role.decontamination", "directory")

    def test_B12_run_references_nonexistent_processing(self, tmp_path):
        toml = BASE + b""  # BASE has run = "prepare_ok" which exists; test a bad one
        # Modify role to have bad run
        bad = BASE.replace(b'run = "prepare_ok"', b'run = "does_not_exist"')
        errors = validate(_cfg(bad, tmp_path))
        assert _has_error(errors, "role.decontamination", "run")

    def test_B12_run_processing_must_have_directory(self, tmp_path):
        toml = BASE.replace(b'run = "prepare_ok"', b'run = "split_ok"')
        # split_ok has directory — should be fine
        errors = validate(_cfg(toml, tmp_path))
        assert not _has_error(errors, "role.decontamination", "run")

    def test_B12_run_processing_without_directory_error(self, tmp_path):
        toml = BASE + b"""
[processing.no_dir_proc]
type = "split"
""" + BASE.replace(b'run = "prepare_ok"', b'run = "no_dir_proc"')[len(BASE):]
        # Simpler: build from scratch
        toml2 = b"""
[local_directories]
genbank = "genbank"

[source.ncbi]
directory = "genbank"

[processing.no_dir_proc]
type = "split"

[role.decontamination]
directory = "decontamination"
run = "no_dir_proc"
"""
        errors = validate(_cfg(toml2, tmp_path))
        assert _has_error(errors, "role.decontamination", "run")


# ===========================================================================
# C. Processing sections
# ===========================================================================

class TestProcessingSectionValidation:
    def test_C13_neither_type_nor_steps(self, tmp_path):
        toml = BASE + b"\n[processing.bad]\nsize = 10\n"
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "processing.bad", "type/steps")

    def test_C13_both_type_and_steps(self, tmp_path):
        toml = BASE + b'\n[processing.bad]\ntype = "split"\nsteps = []\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "processing.bad", "type/steps")

    def test_C14_inline_step_must_have_type(self, tmp_path):
        toml = BASE + b'\n[processing.bad]\noutput = "x@decontamination"\nsteps = [{size = 10}]\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "processing.bad", "steps")

    def test_C14_inline_step_must_not_have_steps(self, tmp_path):
        toml = BASE + b'\n[processing.bad]\noutput = "x@decontamination"\nsteps = [{type = "split", steps = []}]\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "processing.bad", "steps")

    def test_C15_named_step_must_exist(self, tmp_path):
        toml = BASE + b'\n[processing.bad]\noutput = "x@decontamination"\nsteps = ["nonexistent"]\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "processing.bad", "steps")

    def test_C16_type_must_be_registered(self, tmp_path):
        toml = BASE + b'\n[processing.bad]\ntype = "totally_unknown_op"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "processing.bad", "type")

    def test_C16_known_type_no_error(self, tmp_path):
        toml = BASE + b'\n[processing.ok2]\ntype = "split"\nsize = 100\n'
        errors = validate(_cfg(toml, tmp_path))
        assert not _has_error(errors, "processing.ok2", "type")

    def test_C17_run_target_must_have_output(self, tmp_path):
        toml = b"""
[local_directories]
genbank = "genbank"

[source.ncbi]
directory = "genbank"

[processing.atomic_no_output]
type = "split"

[role.decontamination]
directory = "decontamination"
run = "atomic_no_output"
"""
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "processing.atomic_no_output", "output")

    def test_C18_output_must_have_at_sign(self, tmp_path):
        toml = BASE + b'\n[processing.bad]\ntype = "split"\noutput = "noatsign"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "processing.bad", "output")

    def test_C18_output_role_must_be_declared(self, tmp_path):
        toml = BASE + b'\n[processing.bad]\ntype = "split"\noutput = "parts@undeclared_role"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "processing.bad", "output")

    def test_C18_valid_output_artifact_ref(self, tmp_path):
        toml = BASE + b'\n[processing.ok]\ntype = "split"\noutput = "parts@decontamination"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert not _has_error(errors, "processing.ok", "output")

    def test_C18_valid_output_index_ref(self, tmp_path):
        toml = BASE + b'\n[processing.ok]\ntype = "split"\noutput = "@idx:decontamination"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert not _has_error(errors, "processing.ok", "output")

    def test_C18_output_dict_form_valid(self, tmp_path):
        toml = BASE + b'\n[processing.ok]\ntype = "split"\n[processing.ok.output]\nrole = "decontamination"\ndir = "parts"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert not _has_error(errors, "processing.ok", "output")


# ===========================================================================
# D. directory → [local_directories]
# ===========================================================================

class TestDirectoryRefValidation:
    def _base_with_local(self):
        return b"""
[local_directories]
genbank = "genbank"
log     = "log"
processed_data = "processed_data"
indexes = "indexes"
stamp   = "stamp"
"""

    def test_D16_logging_directory_must_exist(self, tmp_path):
        toml = self._base_with_local() + b'[logging]\ndirectory = "nowhere"\nfile = "x.log"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "logging", "directory")

    def test_D16_valid_logging_directory(self, tmp_path):
        toml = self._base_with_local() + b'[logging]\ndirectory = "log"\nfile = "x.log"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert not _has_error(errors, "logging", "directory")

    def test_D17_processed_data_directory_must_exist(self, tmp_path):
        toml = self._base_with_local() + b'[processed_data]\ndirectory = "nowhere"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "processed_data", "directory")

    def test_D18_indexes_directory_must_exist(self, tmp_path):
        toml = self._base_with_local() + b'[indexes]\ndirectory = "nowhere"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "indexes", "directory")

    def test_D19_stamp_directory_must_exist(self, tmp_path):
        toml = self._base_with_local() + b'[stamp]\ndirectory = "nowhere"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "stamp", "directory")

    def test_D20_source_directory_must_exist(self, tmp_path):
        toml = self._base_with_local() + b'[source.ncbi]\ndirectory = "nowhere"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "source.ncbi", "directory")

    def test_D20_valid_source_directory(self, tmp_path):
        toml = self._base_with_local() + b'[source.ncbi]\ndirectory = "genbank"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert not _has_error(errors, "source.ncbi", "directory")


# ===========================================================================
# E. Cross-references: data → source and role sections
# ===========================================================================

class TestCrossRefValidation:
    def test_E21_data_source_must_have_source_section(self, tmp_path):
        # Use "internal" source but don't declare [source.internal]
        toml = b"""
[local_directories]
raw_data = "raw_data"

[role.genome_skims]
directory = "skims"

[data.x]
source = "internal"
role   = "genome_skims"
"""
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "source")

    def test_E22_data_role_must_have_role_section(self, tmp_path):
        toml = b"""
[local_directories]
genbank = "genbank"

[source.ncbi]
directory = "genbank"

[data.x]
source = "ncbi"
role   = "genomes"
taxon  = "human"
"""
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "data.x", "role")


# ===========================================================================
# F. Source sections
# ===========================================================================

class TestSourceSectionValidation:
    def test_F23_invalid_genbank_division_code(self, tmp_path):
        toml = b"""
[local_directories]
genbank = "genbank"

[source.genbank]
directory = "genbank"
divisions = ["bct", "INVALID"]
"""
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "source.genbank", "divisions")

    def test_F23_all_valid_division_codes(self, tmp_path):
        toml = b"""
[local_directories]
genbank = "genbank"

[source.genbank]
directory = "genbank"
divisions = ["bct", "pln", "vrl"]
"""
        errors = validate(_cfg(toml, tmp_path))
        assert not _has_error(errors, "source.genbank", "divisions")


# ===========================================================================
# G. Logging
# ===========================================================================

class TestLoggingValidation:
    def test_G24_invalid_log_level(self, tmp_path):
        toml = b'[logging]\nlevel = "VERBOSE"\n'
        errors = validate(_cfg(toml, tmp_path))
        assert _has_error(errors, "logging", "level")

    def test_G24_valid_log_level(self, tmp_path):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            toml = f'[logging]\nlevel = "{level}"\n'.encode()
            errors = validate(_cfg(toml, tmp_path))
            assert not _has_error(errors, "logging", "level")


# ===========================================================================
# validate_or_raise
# ===========================================================================

class TestValidateOrRaise:
    def test_valid_config_does_not_raise(self, tmp_path):
        validate_or_raise(_valid(tmp_path))  # should not raise

    def test_invalid_config_raises(self, tmp_path):
        toml = BASE + b"[data.bad]\nsource = \"wrong\"\nrole = \"decontamination\"\nexample = true\n"
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_or_raise(_cfg(toml, tmp_path))
        assert "data.bad" in str(exc_info.value)

    def test_error_message_lists_all_violations(self, tmp_path):
        # Two violations: bad source + missing taxon for ncbi
        toml = BASE + b"[data.bad]\nsource = \"ncbi\"\nrole = \"decontamination\"\nexample = true\n"
        # missing taxon is 1 error
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_or_raise(_cfg(toml, tmp_path))
        msg = str(exc_info.value)
        assert "data.bad" in msg
        assert "taxon" in msg

    def test_exception_carries_errors_list(self, tmp_path):
        toml = BASE + b"[data.bad]\nsource = \"ncbi\"\nrole = \"decontamination\"\nexample = true\n"
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_or_raise(_cfg(toml, tmp_path))
        assert len(exc_info.value.errors) >= 1
