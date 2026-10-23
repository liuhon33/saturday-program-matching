"""Run downloaded Forms exports locally; no Google credentials or network calls."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import uuid
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError
from openpyxl.utils.exceptions import InvalidFileException

from . import __version__
from .config import load_config, ConfigError
from .loader import InputError, load_input, read_corrections, fingerprint
from .matcher import match_greedy
from .quality import validate_result
from .output import write_json, export_cleaning, export_matches

BASE = Path(__file__).resolve().parents[1]


def parser():
    p = argparse.ArgumentParser(description='Validate and greedily match local Saturday Program exports.')
    p.add_argument('command', choices=['validate','clean','run'])
    p.add_argument('--tutors', required=True, type=Path)
    p.add_argument('--tutees', required=True, type=Path)
    p.add_argument('--config', type=Path, default=BASE/'config/default.yaml')
    p.add_argument('--output-dir', type=Path, help='New output directory; default: ignored local_runs/<unique run>.')
    p.add_argument('--corrections', type=Path, help='Reviewed, source-hash-bound corrections CSV; raw input stays unchanged.')
    p.add_argument('--allow-partial', action='store_true', help='Explicitly match valid records while recording invalid source rows separately.')
    p.add_argument('--include-contacts', action='store_true', help='Add a separate private name/email sheet to local match output.')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    target = args.output_dir or BASE/'local_runs'/('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    target = target.resolve()
    # A run folder must never replace inputs, code, config, or shared examples.
    protected = [BASE/'data',BASE/'config',BASE/'saturday_match',BASE/'tests',BASE/'tools']
    if any(target == p.resolve() or target.is_relative_to(p.resolve()) for p in protected):
        print('Error: output directory is inside protected project content.', file=sys.stderr)
        return 2
    if target.exists():
        print('Error: output directory already exists; choose a new run directory.', file=sys.stderr)
        return 2
    manifest = {'application_version':__version__, 'python':platform.python_version(),
                'command':args.command, 'allow_partial':args.allow_partial,
                'include_contacts':args.include_contacts, 'status':'validating',
                'created_utc':datetime.now(timezone.utc).isoformat()}
    try:
        config = load_config(args.config)
        corrections = read_corrections(args.corrections)
        target.mkdir(parents=True, exist_ok=False)
        manifest['schema_version'] = config['schema_version']
        manifest['configuration_sha256'] = fingerprint(args.config)
        manifest['configuration'] = config  # approved configuration, never raw responses
        manifest['dependencies'] = {p:importlib.metadata.version(p) for p in ['openpyxl','PyYAML']}
        manifest['code_sha256'] = {p.name:fingerprint(p) for p in sorted((BASE/'saturday_match').glob('*.py'))}
        if args.corrections:
            manifest['corrections_sha256'] = fingerprint(args.corrections)
        tutors = load_input(args.tutors,'tutor',config,corrections)
        tutees = load_input(args.tutees,'tutee',config,corrections)
        manifest['inputs'] = [tutors.metadata,tutees.metadata]
        export_cleaning(target,[tutors,tutees])
        errors = tutors.errors + tutees.errors
        summary = {'valid_tutors':len(tutors.records),'valid_tutees':len(tutees.records),
                   'invalid_rows':tutors.metadata['invalid_rows']+tutees.metadata['invalid_rows'],
                   'validation_error_count':len(errors),
                   'cleaning_rule_counts':dict(Counter(e['rule'] for g in (tutors,tutees) for e in g.events))}
        if args.command == 'run' and (not errors or args.allow_partial):
            result = match_greedy(tutees.records,tutors.records,config)
            summary['quality_checks'] = validate_result(tutees.records,tutors.records,result,config)
            summary.update(result['summary'])
            export_matches(target,result,tutees,tutors,include_contacts=args.include_contacts)
            manifest['status'] = 'completed_with_invalid_rows' if errors else 'completed'
        else:
            manifest['status'] = 'needs_review' if errors else 'validated'
        write_json(target/'summary.json',summary)
        write_json(target/'run_manifest.json',manifest)
        print(json.dumps({'status':manifest['status'],**summary},indent=2))
        print('Outputs are local and may contain participant names. See the new run directory.')
        # This is the destination selected by the operator, not a submitted
        # questionnaire value. Keep raw input paths out of manifests/logs.
        print('Output directory: ' + str(target))
        return 2 if errors and (args.command != 'run' or not args.allow_partial) else 0
    except (InputError, ValueError, OSError, KeyError, TypeError, BadZipFile, InvalidFileException, ParseError) as exc:
        # Known safe validation errors use codes; other exceptions may embed a
        # private path/response, so their string is deliberately not printed.
        code = str(exc) if isinstance(exc,(InputError,ConfigError)) else type(exc).__name__
        print('Input/configuration error: ' + code, file=sys.stderr)
        if target.is_dir() and not (target/'run_manifest.json').exists():
            manifest['status'] = 'failed'
            manifest['error_code'] = code
            write_json(target/'run_manifest.json',manifest)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
