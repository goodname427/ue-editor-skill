"""Shared bounded field selection contracts; adapters own source-specific reads."""
import json
import math
import re


class ProjectionError(ValueError):
    pass


def validate_fields(fields, allow_empty=False):
    if (not isinstance(fields, (tuple, list)) or len(fields) > 16 or not fields and not allow_empty
            or any(not isinstance(p, str) or not p.startswith('/') or len(p) > 256
                   or len(p[1:].split('/')) > 4 or re.search(r'~(?![01])', p) for p in fields)):
        raise ProjectionError('Use 1..16 explicit JSON pointers, at most four segments/256 characters each')
    if len(set(fields)) != len(fields):
        raise ProjectionError('Field paths must be unique')
    return tuple(fields)


def names_to_fields(names):
    if not isinstance(names, (tuple, list)) or any(not isinstance(n, str) or not n for n in names):
        raise ProjectionError('Field names must be nonempty strings')
    return validate_fields(tuple('/' + n.replace('~', '~0').replace('/', '~1') for n in names), allow_empty=True)


def new_record(index, identity=None):
    result = {'index': index, 'fields': {}, 'field_errors': {}}
    if identity is not None:
        result['identity'] = identity
    return result


def field_error(record, path, kind, message):
    record['field_errors'][path] = {'error_type': kind, 'message': str(message)[:256]}


def bounded_value(value, depth=0):
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is str:
        if len(value) > 512:
            return {'value': value[:512], 'value_truncated': True, 'length': len(value)}
        return value
    if depth < 4 and type(value) is list and len(value) <= 32:
        return [bounded_value(v, depth + 1) for v in value]
    if depth < 4 and type(value) is dict and len(value) <= 32 and all(type(k) is str for k in value):
        return {k: bounded_value(v, depth + 1) for k, v in value.items()}
    raise ProjectionError('Unsupported, nonfinite or oversized field value; narrow the selected field')


def dict_field(obj, pointer):
    for part in pointer[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        if type(obj) is dict and part in obj:
            obj = obj[part]
        elif type(obj) is list and re.fullmatch(r'0|[1-9][0-9]*', part) and int(part) < len(obj):
            obj = obj[int(part)]
        else:
            raise ProjectionError('Selected data field not found: ' + part)
    return bounded_value(obj)


def _truncated(value):
    if type(value) is dict:
        return value.get('value_truncated') is True or any(_truncated(v) for v in value.values())
    if type(value) is list:
        return any(_truncated(v) for v in value)
    return False


def finish(records, fields, length, offset, limit, source, truncated=False):
    truncated = truncated or offset > 0 or offset + limit < length
    result = {'kind': 'projection', 'source': source, 'length': length, 'offset': offset, 'limit': limit,
              'fields': list(fields), 'records': records, 'records_truncated': truncated,
              'complete': not truncated and all(not r['field_errors'] and not r.get('row_error')
                                               and not _truncated(r['fields']) for r in records)}
    check_output(result)
    return result


def check_output(result):
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 65536:
        raise ProjectionError('Projection output exceeds 64 KiB; narrow fields or sample, no partial success')
