"""Load a versioned questionnaire contract without silently accepting YAML mistakes."""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import re
import unicodedata

import yaml


class ConfigError(ValueError):
    """Configuration failed validation; messages never include submitted answers."""


class _UniqueKeysLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConfigError("Configuration mapping keys must be scalar strings.") from exc
        if duplicate:
            raise ConfigError("Duplicate YAML mapping key; keep one explicit value per setting.")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeysLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _strings(value, label: str, *, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ConfigError(f"{label} must be a list of nonempty text labels.")
    if any(not isinstance(item, str) or not _key(item) for item in value):
        raise ConfigError(f"{label} contains a blank or non-text label.")
    return value


def validate_config(config: dict) -> dict:
    """Validate and return a detached config. Unknown setting keys are rejected."""
    if not isinstance(config, dict):
        raise ConfigError("Configuration must be a mapping.")
    cfg = deepcopy(config)
    allowed = {
        "schema_version", "description", "worksheets", "columns", "subjects", "genders",
        "no_preference", "no_subject", "preference_values", "grade_values", "normalization", "matching", "input_policy",
    }
    if set(cfg) - allowed:
        raise ConfigError("Unknown top-level configuration setting.")
    if not isinstance(cfg.get("schema_version"), str) or not cfg["schema_version"].strip():
        raise ConfigError("A nonempty schema_version is required.")
    for section in ("worksheets", "columns", "subjects", "genders", "matching"):
        if not isinstance(cfg.get(section), dict) or not cfg[section]:
            raise ConfigError(f"{section} must be a nonempty mapping.")
    if set(cfg["worksheets"]) != {"tutor", "tutee"} or set(cfg["columns"]) != {"tutor", "tutee"}:
        raise ConfigError("Worksheet and column mappings must define tutor and tutee.")
    fields = {
        "id", "first_name", "last_name", "subjects", "gender", "primary", "secondary",
        "tertiary", "gender_preference", "email", "capacity", "grade", "grades", "slots",
    }
    for role in ("tutor", "tutee"):
        sheet = cfg["worksheets"][role]
        if not isinstance(sheet, dict) or set(sheet) != {"name", "header_row"}:
            raise ConfigError("Each worksheet needs name and header_row only.")
        if not isinstance(sheet["name"], str) or not sheet["name"].strip():
            raise ConfigError("Worksheet names must be explicit nonempty strings.")
        if type(sheet["header_row"]) is not int or sheet["header_row"] < 1:
            raise ConfigError("Worksheet header_row must be a positive integer.")
        columns = cfg["columns"][role]
        if not isinstance(columns, dict) or set(columns) - fields:
            raise ConfigError("Column mappings contain an unsupported internal field.")
        essential = {"first_name", "last_name", "subjects" if role == "tutor" else "primary"}
        if not essential.issubset(columns):
            raise ConfigError("Column mappings omit an essential internal field.")
        seen = {}
        for field, spec in columns.items():
            if not isinstance(spec, dict) or set(spec) != {"aliases", "required"}:
                raise ConfigError("Each column needs aliases and required only.")
            if type(spec["required"]) is not bool:
                raise ConfigError("Column required must be true or false.")
            for label in _strings(spec["aliases"], "Column aliases"):
                normalized = _key(label)
                if normalized in seen and seen[normalized] != field:
                    raise ConfigError("Ambiguous column alias maps to multiple internal fields.")
                seen[normalized] = field
    subject_lookup = {}
    for subject_id, spec in cfg["subjects"].items():
        if not isinstance(subject_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", subject_id):
            raise ConfigError("Subject IDs must be lowercase machine-readable identifiers.")
        if not isinstance(spec, dict) or set(spec) - {"label", "aliases", "typo_aliases"}:
            raise ConfigError("Subject definitions support label, aliases, and typo_aliases only.")
        if not isinstance(spec.get("label"), str) or not _key(spec["label"]):
            raise ConfigError("Each subject needs a nonempty label.")
        aliases = _strings(spec.get("aliases", []), "Subject aliases", allow_empty=True)
        typos = _strings(spec.get("typo_aliases", []), "Subject typo aliases", allow_empty=True)
        normal_keys = {_key(x) for x in [subject_id, spec["label"], *aliases]}
        if normal_keys.intersection(_key(x) for x in typos):
            raise ConfigError("A subject alias cannot also be a typo alias.")
        for label in [subject_id, spec["label"], *aliases, *typos]:
            normalized = _key(label)
            if normalized in subject_lookup and subject_lookup[normalized] != subject_id:
                raise ConfigError("Ambiguous subject label maps to multiple subjects.")
            subject_lookup[normalized] = subject_id
    no_subject = _strings(cfg.get("no_subject"), "no_subject")
    if subject_lookup.keys() & {_key(x) for x in no_subject}:
        raise ConfigError("A no-subject marker overlaps a real subject.")
    gender_lookup = {}
    for gender_id, aliases in cfg["genders"].items():
        if not isinstance(gender_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", gender_id):
            raise ConfigError("Gender IDs must be lowercase machine-readable identifiers.")
        for label in [gender_id, *_strings(aliases, "Gender aliases")]:
            normalized = _key(label)
            if normalized in gender_lookup and gender_lookup[normalized] != gender_id:
                raise ConfigError("Ambiguous gender label maps to multiple gender values.")
            gender_lookup[normalized] = gender_id
    no_preference = _strings(cfg.get("no_preference"), "no_preference")
    if gender_lookup.keys() & {_key(x) for x in no_preference}:
        raise ConfigError("A no-preference marker overlaps a gender label.")
    preference_values = _strings(cfg.get("preference_values"), "preference_values")
    if not set(preference_values).issubset(cfg["genders"]) or len(preference_values) != len(set(preference_values)):
        raise ConfigError("preference_values must contain unique configured gender IDs.")
    grade_values = _strings(cfg.get("grade_values"), "grade_values")
    if any(not re.fullmatch(r"[0-9]+", grade) for grade in grade_values) or len(grade_values) != len(set(grade_values)):
        raise ConfigError("grade_values must contain unique digit-only text labels.")
    normalization = cfg.setdefault("normalization", {"missing_preference": "no_preference"})
    if not isinstance(normalization, dict) or set(normalization) != {"missing_preference"}:
        raise ConfigError("normalization supports missing_preference only.")
    if normalization["missing_preference"] not in {"no_preference", "error"}:
        raise ConfigError("missing_preference must be no_preference or error.")
    input_policy = cfg.setdefault("input_policy", {"unknown_columns": "ignore", "unknown_values": "review"})
    if not isinstance(input_policy, dict) or set(input_policy) != {"unknown_columns", "unknown_values"}:
        raise ConfigError("input_policy needs unknown_columns and unknown_values.")
    if input_policy["unknown_columns"] not in {"ignore", "error"} or input_policy["unknown_values"] != "review":
        raise ConfigError("Unknown choices require review; unknown columns may be ignored or rejected.")
    matching = cfg["matching"]
    matching_keys = {
        "subject_policy", "gender_policy", "weights", "urgency_weights", "urgency_scale",
        "gender_urgency_bonus", "default_capacity", "enforce_availability", "enforce_grade",
    }
    if set(matching) != matching_keys:
        raise ConfigError("Matching settings are missing or unsupported.")
    if matching["subject_policy"] not in {"primary", "any", "legacy_flag"}:
        raise ConfigError("subject_policy must be primary, any, or legacy_flag.")
    if matching["gender_policy"] not in {"required", "legacy_flag"}:
        raise ConfigError("gender_policy must be required or legacy_flag.")
    for setting in ("enforce_availability", "enforce_grade"):
        if type(matching[setting]) is not bool:
            raise ConfigError(f"{setting} must be true or false.")
    if type(matching["default_capacity"]) is not int or matching["default_capacity"] < 1:
        raise ConfigError("default_capacity must be a positive integer.")
    numbers = []
    for setting in ("weights", "urgency_weights"):
        values = matching[setting]
        if not isinstance(values, dict) or set(values) != {"primary", "secondary", "tertiary"}:
            raise ConfigError("Each weight mapping needs primary, secondary, and tertiary.")
        numbers.extend(values.values())
    numbers.extend(matching[x] for x in ("urgency_scale", "gender_urgency_bonus"))
    if any(type(number) not in {int, float} or not math.isfinite(number) or number < 0 for number in numbers):
        raise ConfigError("Matching weights must be finite nonnegative numbers.")
    return cfg


def load_config(path: str | Path) -> dict:
    """Read YAML locally; reject duplicate keys rather than using the last one."""
    try:
        with Path(path).open(encoding="utf-8") as stream:
            config = yaml.load(stream, Loader=_UniqueKeysLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise ConfigError("Configuration is not valid UTF-8 YAML.") from exc
    return validate_config(config)
