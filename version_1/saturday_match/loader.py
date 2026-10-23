"""Read-only questionnaire import with explicit identity and row accounting.

Names and contacts are kept in the local process/output only. Audit events never
contain response values. Unknown categories and identity collisions require review.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .models import Tutor, Tutee
from .normalization import (NormalizationError, normalize_text, canonical_subject,
                            parse_subjects, canonical_gender, canonical_preference)


class InputError(ValueError):
    """An actionable error with no raw submitted response in its message."""


@dataclass
class LoadedInput:
    role: str
    records: list = field(default_factory=list)
    contacts: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    ledger: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def errors(self):
        return [e for e in self.events if e['severity'] == 'error']


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _header(value):
    return (normalize_text(value) or '').casefold()


def _grade(value, config):
    """Normalize a numeric grade only if its canonical value is approved."""
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise NormalizationError('unknown_grade')
    token = str(value).strip().casefold()
    match = re.fullmatch(r'(?:grade\s+)?(\d+)(?:\.0)?', token)
    if not match or match.group(1) not in config['grade_values']:
        raise NormalizationError('unknown_grade')
    return match.group(1)


def read_table(path, worksheet):
    path = Path(path)
    header_row = worksheet.get('header_row', 1)
    if path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as f:
            values = list(csv.reader(f))
        if len(values) < header_row:
            raise InputError('header_row_missing')
        headers = values[header_row - 1]
        rows = [(n, row, set()) for n, row in enumerate(values[header_row:], header_row + 1)]
    elif path.suffix.lower() == '.xlsx':
        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            if worksheet['name'] not in workbook.sheetnames:
                raise InputError('configured_sheet_missing')
            sheet = workbook[worksheet['name']]
            values = list(sheet.iter_rows(min_row=header_row))
            if not values:
                raise InputError('header_row_missing')
            headers = [c.value for c in values[0]]
            rows = [(n, [c.value for c in cells], {i for i,c in enumerate(cells) if c.data_type == 'f'})
                    for n, cells in enumerate(values[1:], header_row + 1)]
        finally:
            workbook.close()
    else:
        raise InputError('unsupported_input_format: use XLSX or CSV')
    # Unmapped duplicate headers are common in Forms exports (guardian emails).
    # Ambiguity is rejected only for a field that the selected profile consumes.
    try:
        return [_header(h) for h in headers], rows
    except NormalizationError:
        raise InputError('non_text_header') from None


def read_corrections(path):
    """Corrections are private, hash-bound, explicit values; never edit the raw file."""
    if path is None:
        return {}
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if len(reader.fieldnames or []) != 5 or set(reader.fieldnames or []) != {'role', 'source_sha256', 'row', 'field', 'value'}:
            raise InputError('corrections_header_invalid')
        corrections = {}
        for r in reader:
            if None in r or any(v is None for v in r.values()):
                raise InputError('corrections_row_width_invalid')
            try:
                n = int(r['row'])
            except (ValueError, TypeError):
                raise InputError('corrections_row_invalid') from None
            if r['role'] not in ('tutor', 'tutee') or n < 2:
                raise InputError('corrections_location_invalid')
            digest = r['source_sha256'].strip().lower()
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise InputError('corrections_source_hash_invalid')
            key = (r['role'], n, r['field'])
            if key in corrections:
                raise InputError('duplicate_correction')
            corrections[key] = (digest, r['value'])
    return corrections


def load_input(path, role, config, corrections=None):
    if role not in ('tutor', 'tutee'):
        raise InputError('unknown_input_role')
    result = LoadedInput(role)
    digest = fingerprint(path)
    headers, rows = read_table(path, config['worksheets'][role])
    fields = config['columns'][role]
    selected = {}
    for name, spec in fields.items():
        aliases = {_header(a) for a in spec['aliases']}
        matches = [i for i, header in enumerate(headers) if header in aliases]
        if len(matches) > 1:
            raise InputError(f'{role}.{name}: ambiguous_column')
        if not matches and spec.get('required', False):
            raise InputError(f'{role}.{name}: required_column_missing')
        selected[name] = matches[0] if matches else None
    if len([v for v in selected.values() if v is not None]) != len(set(v for v in selected.values() if v is not None)):
        raise InputError('one_column_mapped_to_multiple_fields')
    consumed = set(v for v in selected.values() if v is not None)
    if config.get('input_policy', {}).get('unknown_columns') == 'error' and len(consumed) != len(headers):
        raise InputError(f'{role}: unmapped_columns_present')
    corrections = corrections or {}
    row_numbers = {n for n, _, _ in rows}
    for (corr_role, n, name), (source_hash, _) in corrections.items():
        if corr_role != role:
            continue
        if source_hash != digest:
            raise InputError(f'{role}: corrections_source_hash_mismatch')
        if n not in row_numbers or name not in fields:
            raise InputError(f'{role}: corrections_location_not_found')
        original_values = next(values for row_number, values, _ in rows if row_number == n)
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in original_values):
            raise InputError(f'{role}: correction_targets_blank_row')
    result.metadata = {'role': role, 'sha256': digest, 'source_rows': len(rows),
                       'schema_version': config['schema_version'],
                       'ignored_column_count': len(headers) - len(set(v for v in selected.values() if v is not None))}
    candidates = []
    for number, values, formulas in rows:
        status = {'role': role, 'source_row': number, 'status': 'invalid', 'participant_id': None}
        result.ledger.append(status)
        def event(code, name='', severity='change', suggestions=()):
            e = {'role': role, 'source_row': number, 'field': name, 'rule': code, 'severity': severity}
            if suggestions:
                e['approved_catalog_suggestions'] = list(suggestions)
            result.events.append(e)
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in values):
            status['status'] = 'blank'
            event('blank_row_recorded', severity='info')
            continue
        if len(values) != len(headers):
            event('row_width_differs_from_header', severity='error')
            continue
        raw = {name: values[i] if i is not None else None for name, i in selected.items()}
        corrected = set()
        for name in fields:
            if (role, number, name) in corrections:
                raw[name] = corrections[role, number, name][1]
                corrected.add(name)
                event('explicit_hash_bound_correction', name)
        errors_before = len(result.errors)
        for name, i in selected.items():
            if i in formulas and name not in corrected:
                event('formula_in_consumed_field', name, 'error')
        if len(result.errors) > errors_before:
            continue
        try:
            active_field = 'first_name'
            def text(name, required=False):
                nonlocal active_field
                active_field = name
                value = normalize_text(raw.get(name))
                if required and not value:
                    raise NormalizationError(f'missing_{name}')
                if raw.get(name) is not None and raw.get(name) != value:
                    event('normalized_whitespace_or_unicode', name)
                return value
            first, last = text('first_name', True), text('last_name', True)
            display = f'{first} {last}'
            email = text('email')
            # A local identity digest is not an anonymization promise and is not
            # exported as a public fixture. Never identify people by name alone.
            explicit_id = text('id')
            if explicit_id:
                identity = explicit_id
            else:
                key = json.dumps([role, first.casefold(), last.casefold(), (email or '').casefold()], ensure_ascii=False)
                identity = f'{role}-' + hashlib.sha256(key.encode()).hexdigest()[:24]
                event('generated_private_identity_from_name_and_contact' if email else 'generated_private_identity_from_name', 'id')
            def change(name):
                return lambda code: event(code, name)
            def tokens(name):
                value = text(name)
                parsed = tuple(sorted(set(s.strip().casefold() for s in (value or '').split('|') if s.strip())))
                if value and value != '|'.join(parsed):
                    event('normalized_structured_tokens', name)
                return parsed
            slots = tokens('slots')
            if config['matching']['enforce_availability'] and not slots:
                raise NormalizationError('structured_availability_required')
            if role == 'tutor':
                active_field = 'subjects'
                subjects = parse_subjects(raw.get('subjects'), config, on_change=change('subjects'))
                if not subjects:
                    raise NormalizationError('missing_required_subject')
                active_field = 'gender'
                gender = canonical_gender(raw.get('gender'), config, on_change=change('gender'))
                active_field = 'capacity'
                capacity_raw = raw.get('capacity')
                capacity = config['matching'].get('default_capacity', 1)
                if capacity_raw is not None and str(capacity_raw).strip():
                    try:
                        parsed = float(capacity_raw)
                        if isinstance(capacity_raw, bool) or not parsed.is_integer() or parsed < 1:
                            raise ValueError
                        capacity = int(parsed)
                    except (ValueError, TypeError, OverflowError):
                        raise NormalizationError('invalid_capacity') from None
                active_field = 'grades'
                if isinstance(raw.get('grades'), (int, float)) and not isinstance(raw.get('grades'), bool):
                    grades = (_grade(raw['grades'], config),) if config['matching']['enforce_grade'] else (str(raw['grades']),)
                else:
                    grades = tokens('grades')
                if config['matching']['enforce_grade'] and grades:
                    grades = tuple(sorted(set(_grade(g, config) for g in grades)))
                    event('normalized_program_grade_bands', 'grades')
                if config['matching']['enforce_grade'] and not grades:
                    raise NormalizationError('tutor_grade_capabilities_required')
                participant = Tutor(identity, display, subjects, gender, capacity, grades, slots, number)
            else:
                preferences = []
                for name in ('primary', 'secondary', 'tertiary'):
                    active_field = name
                    preferences.append(canonical_subject(raw.get(name), config, allow_none=name != 'primary', on_change=change(name)))
                preferences = tuple(preferences)
                active_field = 'gender_preference'
                preference = canonical_preference(raw.get('gender_preference'), config, on_change=change('gender_preference'))
                active_field = 'grade'
                grade_raw = raw.get('grade')
                if isinstance(grade_raw, (int, float)) and not isinstance(grade_raw, bool):
                    grade = str(int(grade_raw)) if float(grade_raw).is_integer() else str(grade_raw)
                    event('numeric_grade_to_text', 'grade')
                else:
                    grade = text('grade')
                if config['matching']['enforce_grade'] and grade:
                    grade = _grade(grade, config)
                    event('normalized_program_grade_band', 'grade')
                if config['matching']['enforce_grade'] and not grade:
                    raise NormalizationError('student_grade_required')
                participant = Tutee(identity, display, preferences, preference, grade, slots, number)
            status['participant_id'] = identity
            status['status'] = 'valid'
            candidates.append((participant, status, {'name': display, 'email': email or ''}))
        except NormalizationError as exc:
            event(exc.code, active_field, severity='error', suggestions=exc.suggestions)
        except ValueError:
            event('invalid_canonical_record', severity='error')
    groups = defaultdict(list)
    for entry in candidates:
        groups[entry[0].id].append(entry)
    for identity, entries in groups.items():
        if len(entries) > 1:
            for person, status, _ in entries:
                status['status'] = 'invalid'
                result.events.append({'role': role, 'source_row': person.source_row, 'field': 'id',
                                      'rule': 'duplicate_identity_requires_review', 'severity': 'error'})
        else:
            person, _, contact = entries[0]
            result.records.append(person)
            result.contacts[identity] = contact
    names = Counter(p.display_name.casefold() for p in result.records)
    for p in result.records:
        if names[p.display_name.casefold()] > 1:
            result.events.append({'role': role, 'source_row': p.source_row, 'field': 'id',
                                  'rule': 'same_name_distinct_ids_retained', 'severity': 'warning'})
    result.metadata['valid_records'] = len(result.records)
    result.metadata['invalid_rows'] = sum(row['status'] == 'invalid' for row in result.ledger)
    result.metadata['blank_rows'] = sum(row['status'] == 'blank' for row in result.ledger)
    if len(result.ledger) != result.metadata['valid_records'] + result.metadata['invalid_rows'] + result.metadata['blank_rows']:
        raise RuntimeError('Input row conservation failed')
    return result
