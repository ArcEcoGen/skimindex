"""
Config validation for skimindex — checks all structural invariants and
cross-section dependencies, reporting every violation with a clear message.

Usage:
    from skimindex.config import validate, validate_or_raise

    errors = validate(cfg)        # list[ConfigError], empty if valid
    validate_or_raise(cfg)        # raises ConfigValidationError if any errors
"""


from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skimindex.config import Config

VALID_SOURCES = frozenset({"ncbi", "genbank", "internal", "sra"})
VALID_ROLES = frozenset({"decontamination", "genomes", "genome_skims"})
VALID_GB_DIVISIONS = frozenset({"bct", "inv", "mam", "phg", "pln", "pri", "rod", "vrl", "vrt"})
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


@dataclass(frozen=True)
class ConfigError:
    """A single config validation error with location and description.

    Attributes:
        section: TOML section path, e.g. ``"data.fungi"`` or
                 ``"processing.prepare_decontam"``.
        key:     Key within the section, e.g. ``"divisions"`` or ``"run"``.
        message: Human-readable description of the violation.
    """
    section: str
    key: str
    message: str


class ConfigValidationError(Exception):
    """Raised by validate_or_raise() when the config has one or more errors."""

    def __init__(self, errors: list[ConfigError]) -> None:
        self.errors = errors
        lines = [f"Config validation failed ({len(errors)} error(s)):"]
        for e in errors:
            lines.append(f"  [{e.section}]  {e.key}: {e.message}")
        super().__init__("\n".join(lines))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(cfg: "Config") -> list[ConfigError]:
    """Return all validation errors found in cfg (empty list = valid)."""
    errors: list[ConfigError] = []
    errors += _validate_data_sections(cfg)
    errors += _validate_role_sections(cfg)
    errors += _validate_processing_sections(cfg)
    errors += _validate_directory_refs(cfg)
    errors += _validate_source_sections(cfg)
    errors += _validate_logging(cfg)
    return errors


def validate_or_raise(cfg: "Config") -> None:
    """Raise ConfigValidationError listing all errors, or return silently if valid."""
    errors = validate(cfg)
    if errors:
        raise ConfigValidationError(errors)


# ---------------------------------------------------------------------------
# A. Data sections
# ---------------------------------------------------------------------------

def _validate_data_sections(cfg: "Config") -> list[ConfigError]:
    errors: list[ConfigError] = []
    gb_divisions = set(cfg.sources.get("genbank", {}).get("divisions", []))
    declared_processing = cfg.processing

    for name, ds in cfg.datasets.items():
        sec = f"data.{name}"

        # A1 / A2 — source and role required
        if "source" not in ds:
            errors.append(ConfigError(sec, "source", "required key is missing"))
        if "role" not in ds:
            errors.append(ConfigError(sec, "role", "required key is missing"))

        source = ds.get("source")
        role = ds.get("role")

        # A3 — source value
        if source is not None and source not in VALID_SOURCES:
            errors.append(ConfigError(
                sec, "source",
                f"'{source}' is not valid; must be one of {sorted(VALID_SOURCES)}"
            ))

        # A4 — role value
        if role is not None and role not in VALID_ROLES:
            errors.append(ConfigError(
                sec, "role",
                f"'{role}' is not valid; must be one of {sorted(VALID_ROLES)}"
            ))

        # A5 — source=ncbi requires taxon
        if source == "ncbi" and "taxon" not in ds:
            errors.append(ConfigError(sec, "taxon", "required when source = \"ncbi\""))

        # A6 — role=decontamination requires example (bool)
        if role == "decontamination":
            if "example" not in ds:
                errors.append(ConfigError(
                    sec, "example",
                    "required when role = \"decontamination\" (true = positive example, "
                    "false = counter-example)"
                ))
            elif not isinstance(ds["example"], bool):
                errors.append(ConfigError(
                    sec, "example",
                    f"must be true or false, got {ds['example']!r}"
                ))

        # A7 / A8 — source=genbank: divisions optional but must be subset if present
        if source == "genbank" and "divisions" in ds:
            ds_divs = set(ds["divisions"]) if isinstance(ds["divisions"], list) else set()
            if gb_divisions:
                extra = ds_divs - gb_divisions
                if extra:
                    errors.append(ConfigError(
                        sec, "divisions",
                        f"{sorted(extra)} not declared in [source.genbank] divisions "
                        f"{sorted(gb_divisions)}"
                    ))

        # A9 — source=genbank + by_species=True: not yet implemented
        if source == "genbank" and ds.get("by_species") is True:
            errors.append(ConfigError(
                sec, "by_species",
                "by_species = true for source=\"genbank\" is not yet implemented "
                "(planned: obidistribute pre-processing)"
            ))

        # A10 — run (if present) must reference a processing section with directory
        if "run" in ds:
            errors += _check_run_ref(sec, "run", ds["run"], declared_processing)

        # E21 — source value must have a matching [source.X] section
        if source in VALID_SOURCES and source not in cfg.sources:
            errors.append(ConfigError(
                sec, "source",
                f"[source.{source}] section is not declared in the config"
            ))

        # E22 — role value must have a matching [role.X] section
        if role in VALID_ROLES and role not in cfg.roles:
            errors.append(ConfigError(
                sec, "role",
                f"[role.{role}] section is not declared in the config"
            ))

    return errors


# ---------------------------------------------------------------------------
# B. Role sections
# ---------------------------------------------------------------------------

def _validate_role_sections(cfg: "Config") -> list[ConfigError]:
    errors: list[ConfigError] = []
    declared_processing = cfg.processing

    # Collect roles that have at least one dataset assigned
    roles_with_datasets: set[str] = {
        ds.get("role") for ds in cfg.datasets.values() if ds.get("role")
    }

    for name, role in cfg.roles.items():
        sec = f"role.{name}"

        # B11 — directory required
        if "directory" not in role:
            errors.append(ConfigError(sec, "directory", "required key is missing"))

        # B12 — run (if present) must reference processing with directory
        if "run" in role:
            errors += _check_run_ref(sec, "run", role["run"], declared_processing)

        # B13 — run required when datasets are assigned to this role,
        # unless all datasets for this role use source = "sra" (raw reads, no processing step)
        elif name in roles_with_datasets:
            role_datasets = [d for d in cfg.datasets.values() if d.get("role") == name]
            all_sra = all(d.get("source") == "sra" for d in role_datasets)
            if not all_sra:
                errors.append(ConfigError(
                    sec, "run",
                    f"required: {len(role_datasets)} "
                    f"dataset(s) are assigned to this role but no processing pipeline is declared"
                ))

    return errors


# ---------------------------------------------------------------------------
# C. Processing sections
# ---------------------------------------------------------------------------

def _validate_processing_sections(cfg: "Config") -> list[ConfigError]:
    from skimindex.processing import registered_types
    known_types = registered_types()

    errors: list[ConfigError] = []
    all_proc = cfg.processing

    # Collect every processing name referenced via run (roles + datasets)
    run_refs: set[str] = set()
    for role in cfg.roles.values():
        if "run" in role:
            run_refs.add(role["run"])
    for ds in cfg.datasets.values():
        if "run" in ds:
            run_refs.add(ds["run"])

    for name, proc in all_proc.items():
        sec = f"processing.{name}"
        has_type = "type" in proc
        has_steps = "steps" in proc

        # C13 — exactly one of type or steps
        if has_type and has_steps:
            errors.append(ConfigError(
                sec, "type/steps",
                "a processing section must have either 'type' (atomic) or 'steps' "
                "(composite), not both"
            ))
            continue
        if not has_type and not has_steps:
            errors.append(ConfigError(
                sec, "type/steps",
                "a processing section must have either 'type' (atomic) or 'steps' "
                "(composite); neither is present"
            ))
            continue

        if has_type:
            # C16 — type must be registered
            t = proc["type"]
            if t not in known_types:
                errors.append(ConfigError(
                    sec, "type",
                    f"'{t}' is not a registered @data_process type; "
                    f"known types: {sorted(known_types)}"
                ))

        if has_steps:
            steps = proc["steps"]
            if not isinstance(steps, list):
                errors.append(ConfigError(sec, "steps", "must be an array"))
            else:
                for i, step in enumerate(steps):
                    if isinstance(step, str):
                        # C15 — named reference must exist
                        if step not in all_proc:
                            errors.append(ConfigError(
                                sec, "steps",
                                f"step [{i}] references \"{step}\" which is not "
                                f"a declared [processing.X] section"
                            ))
                    elif isinstance(step, dict):
                        # C14 — inline step must have type, must not have steps
                        if "type" not in step:
                            errors.append(ConfigError(
                                sec, "steps",
                                f"inline step [{i}] must have a 'type' key"
                            ))
                        if "steps" in step:
                            errors.append(ConfigError(
                                sec, "steps",
                                f"inline step [{i}] cannot have 'steps' (inline steps "
                                f"are always atomic)"
                            ))
                        # C16 for inline steps
                        if "type" in step and step["type"] not in known_types:
                            t = step["type"]
                            errors.append(ConfigError(
                                sec, "steps",
                                f"inline step [{i}] type '{t}' is not a registered "
                                f"@data_process type; known types: {sorted(known_types)}"
                            ))
                    else:
                        errors.append(ConfigError(
                            sec, "steps",
                            f"step [{i}] must be a string (named reference) or an "
                            f"inline table {{type = ...}}"
                        ))

        # C17 — processing referenced by run must have output
        if name in run_refs and "output" not in proc:
            errors.append(ConfigError(
                sec, "output",
                f"this processing section is referenced by a 'run' key but has no "
                f"'output'; a runnable processing section must declare its output artifact"
            ))

        # C18 — output (if present) must be a valid artifact reference
        if "output" in proc:
            errors += _check_artifact_ref(sec, "output", proc["output"], cfg)

        # C19 — sequence / histogram / index (if present) must be valid artifact references
        for artifact_key in ("sequence", "histogram", "index"):
            if artifact_key in proc:
                errors += _check_artifact_ref(sec, artifact_key, proc[artifact_key], cfg)

    return errors


# ---------------------------------------------------------------------------
# D. directory → [local_directories] cross-references
# ---------------------------------------------------------------------------

def _validate_directory_refs(cfg: "Config") -> list[ConfigError]:
    errors: list[ConfigError] = []
    local_dirs = set(cfg._config_section("local_directories").keys())

    if not local_dirs:
        return errors  # nothing to check against

    def _check_dir(section: str, key: str, value: Any) -> None:
        if value and value not in local_dirs:
            errors.append(ConfigError(
                section, key,
                f"'{value}' is not declared in [local_directories]; "
                f"known keys: {sorted(local_dirs)}"
            ))

    # D16 — [logging].directory
    log_dir = cfg._config_section("logging").get("directory")
    if log_dir:
        _check_dir("logging", "directory", log_dir)

    # D17–D19 — [processed_data], [indexes], [stamp]
    for cfg_sec in ("processed_data", "indexes", "stamp"):
        d = cfg._config_section(cfg_sec).get("directory")
        if d:
            _check_dir(cfg_sec, "directory", d)

    # D20 — each [source.X].directory
    for src_name, src in cfg.sources.items():
        d = src.get("directory")
        if d:
            _check_dir(f"source.{src_name}", "directory", d)

    return errors


# ---------------------------------------------------------------------------
# F. Source sections
# ---------------------------------------------------------------------------

def _validate_source_sections(cfg: "Config") -> list[ConfigError]:
    errors: list[ConfigError] = []

    # F23 — [source.genbank].divisions codes must be valid
    gb = cfg.sources.get("genbank", {})
    if "divisions" in gb:
        divs = gb["divisions"] if isinstance(gb["divisions"], list) else []
        invalid = [d for d in divs if d not in VALID_GB_DIVISIONS]
        if invalid:
            errors.append(ConfigError(
                "source.genbank", "divisions",
                f"invalid division code(s) {invalid}; "
                f"valid codes: {sorted(VALID_GB_DIVISIONS)}"
            ))

    return errors


# ---------------------------------------------------------------------------
# G. Logging section
# ---------------------------------------------------------------------------

def _validate_logging(cfg: "Config") -> list[ConfigError]:
    errors: list[ConfigError] = []
    log = cfg._config_section("logging")

    level = log.get("level")
    if level is not None and level not in VALID_LOG_LEVELS:
        errors.append(ConfigError(
            "logging", "level",
            f"'{level}' is not valid; must be one of {sorted(VALID_LOG_LEVELS)}"
        ))

    return errors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_run_ref(
    section: str,
    key: str,
    run_value: Any,
    declared_processing: dict[str, dict],
) -> list[ConfigError]:
    """Check that a run= value references an existing processing section with output."""
    errors: list[ConfigError] = []
    if not isinstance(run_value, str):
        errors.append(ConfigError(section, key, "must be a string (processing section name)"))
        return errors
    if run_value not in declared_processing:
        errors.append(ConfigError(
            section, key,
            f"references processing section \"{run_value}\" which is not declared"
        ))
    elif "output" not in declared_processing[run_value]:
        errors.append(ConfigError(
            section, key,
            f"processing section \"{run_value}\" has no 'output'; "
            f"a runnable processing section must declare its output artifact"
        ))
    return errors


def _check_artifact_ref(
    section: str,
    key: str,
    value: Any,
    cfg: "Config",
) -> list[ConfigError]:
    """Validate an artifact reference (string or dict form)."""
    errors: list[ConfigError] = []

    if isinstance(value, dict):
        role_spec = value.get("role")
        if not role_spec:
            errors.append(ConfigError(section, key, "dict artifact reference must have a 'role' key"))
            return errors
    elif isinstance(value, str):
        if "@" not in value:
            errors.append(ConfigError(
                section, key,
                f"artifact reference {value!r} must follow 'dir@[idx:]role' notation"
            ))
            return errors
        _, role_spec = value.split("@", 1)
    else:
        errors.append(ConfigError(section, key, "must be a string or dict artifact reference"))
        return errors

    role_name = role_spec[4:] if role_spec.startswith("idx:") else role_spec
    if role_name not in cfg.roles:
        errors.append(ConfigError(
            section, key,
            f"artifact reference uses role '{role_name}' which is not declared in [role.{role_name}]"
        ))
    return errors
