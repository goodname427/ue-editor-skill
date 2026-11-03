"""运行时对象与列表的只读快照；对象路径需每次解析，不加载资产，不执行业务方法。"""
import math
import unreal
from ue_input import find
import ue_projection


def _object_info(obj):
    if obj is None:
        return None
    return {'path': obj.get_path_name(), 'name': obj.get_name(), 'class': obj.get_class().get_name()}


def resolve(path='', locator='', window='', index=None):
    if bool(path) == bool(locator):
        raise ValueError('Use exactly one object path or current widget Locator')
    if locator:
        nodes = find(locator, window)
        if index is None and len(nodes) != 1:
            raise RuntimeError('Object Locator must match exactly one widget (%d matched)' % len(nodes))
        selected = 0 if index is None else index
        if isinstance(selected, bool) or not isinstance(selected, int) or not 0 <= selected < len(nodes):
            raise ValueError('Object Locator index out of range')
        path = nodes[selected].get('object_path', '')
        if not path:
            raise RuntimeError('Widget has no source object_path; rebuild/update AgentSlateDriver or select an explicit runtime object path')
    elif index is not None:
        raise ValueError('index only applies to a Locator')
    obj = unreal.find_object(None, path)
    if obj is None:
        raise RuntimeError('Runtime object not found; paths are not stable across rebuilds or sessions: ' + path)
    return obj


def _property_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise TypeError('Non-finite float cannot be represented in JSON')
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, unreal.Object):
        return _object_info(value)
    if isinstance(value, getattr(unreal, 'EnumBase', ())):
        return str(value)
    raise TypeError('Only scalar, enum or UObject properties are supported; inspect structs/arrays explicitly')


def _properties(obj, fields):
    values, errors = {}, {}
    for name in fields:
        try:
            values[name] = _property_value(obj.get_editor_property(name))
        except Exception as error:
            errors[name] = str(error)
    return {'properties': values, 'property_errors': errors}


def project_nodes(nodes, columns=(), properties=(), offset=0, limit=80, indices=None, truncated=False):
    """Project already-selected Slate nodes; optionally read their existing source UObjects."""
    column_fields = ue_projection.names_to_fields(columns)
    property_fields = ue_projection.names_to_fields(properties)
    if not column_fields and not property_fields:
        raise ValueError('Select node columns and/or reflected properties')
    if len(column_fields) + len(property_fields) > 16:
        raise ValueError('At most 16 combined columns/properties')
    if (isinstance(offset, bool) or not isinstance(offset, int) or offset < 0
            or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500):
        raise ValueError('Projection offset must be nonnegative and limit in 1..500')
    records, cache, resolved_paths = [], {}, set()
    for position in range(offset, min(len(nodes), offset + limit)):
        node = nodes[position]
        identity = {k: node[k] for k in ('d', 'type', 'name', 'window', 'pie_instance', 'query_only', 'visible_path',
                                         'geometry_valid', 'target_match_count') if k in node}
        row = ue_projection.new_record(indices[position] if indices is not None else position, identity)
        for name, pointer in zip(columns, column_fields):
            try:
                row['fields']['/node' + pointer] = ue_projection.dict_field(node, pointer)
            except ue_projection.ProjectionError as error:
                ue_projection.field_error(row, '/node' + pointer, 'FieldMissingOrUnsupported', error)
        if properties:
            path = node.get('object_path', '')
            if path not in cache:
                try:
                    if not path:
                        raise ValueError('Slate node has no source object_path; no object is guessed or loaded')
                    cache[path] = _properties(resolve(path=path), properties)
                    resolved_paths.add(path)
                except Exception as error:
                    cache[path] = {'properties': {}, 'property_errors': {n: str(error) for n in properties}}
            values = cache[path]
            for name, pointer in zip(properties, property_fields):
                if name in values['property_errors']:
                    ue_projection.field_error(row, '/property' + pointer, 'ReflectedPropertyError', values['property_errors'][name])
                else:
                    try:
                        row['fields']['/property' + pointer] = ue_projection.bounded_value(values['properties'][name])
                    except ue_projection.ProjectionError as error:
                        ue_projection.field_error(row, '/property' + pointer, 'FieldUnsupported', error)
        records.append(row)
    result = ue_projection.finish(records, ['/node' + p for p in column_fields] + ['/property' + p for p in property_fields],
                                  len(nodes), offset, limit, 'slate+reflection' if properties else 'slate', truncated)
    result.update(reflected_object_count=len(resolved_paths),
                  coverage='Selected Slate node columns and explicit reflected source properties only; indices are current-query-local, not inventory counts or business assertions.')
    ue_projection.check_output(result)
    return result


def object_snapshot(path='', locator='', window='', index=None, fields=()):
    if isinstance(fields, str) or len(fields) > 16 or any(not isinstance(n, str) or not n for n in fields):
        raise ValueError('fields must contain at most 16 explicit property names')
    obj = resolve(path, locator, window, index)
    return dict(kind='object', object=_object_info(obj), **_properties(obj, fields),
                coverage='Requested reflected properties only; no arbitrary TS payload or business validation.')


def _native_getter(obj, name):
    if obj is None or not isinstance(obj, unreal.Widget):
        return None
    for cls in type(obj).__mro__:
        if name in vars(cls):
            descriptor = vars(cls)[name]
            if (type(descriptor).__name__ not in ('method_descriptor', 'methodwithclosure_descriptor')
                    or not callable(getattr(cls, 'static_class', None))
                    or not cls.static_class().get_path_name().startswith('/Script/')):
                return None
            getter = getattr(obj, name, None)
            return getter if callable(getter) else None
    return None


def list_snapshot(path='', locator='', window='', index=None, offset=0, limit=10, fields=()):
    if (isinstance(offset, bool) or not isinstance(offset, int) or offset < 0
            or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100):
        raise ValueError('offset must be nonnegative and limit in 1..100')
    if isinstance(fields, str) or len(fields) > 16 or any(not isinstance(n, str) or not n for n in fields):
        raise ValueError('fields must contain at most 16 explicit property names')
    obj = resolve(path, locator, window, index)
    count_getter = 'get_num_items' if _native_getter(obj, 'get_num_items') else 'get_item_count'
    get_count, get_item, get_entries = (_native_getter(obj, name) for name in (count_getter, 'get_item_at', 'get_displayed_entry_widgets'))
    if not all((get_count, get_item, get_entries)):
        raise RuntimeError('Object does not expose supported native readonly list count/item/entry getters')
    count = get_count()
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise RuntimeError('Invalid native list item count')
    entries = get_entries()
    entry_by_item = {}
    sampled_entries = list(entries[:limit])
    entry_scan_complete = len(entries) <= limit
    get_entry = _native_getter(obj, 'get_entry_widget_from_item')
    entry_mapping_supported = bool(get_entry)
    entry_scan_mapped = True
    for entry in sampled_entries:
        get_entry_item = _native_getter(entry, 'get_list_item_object_internal')
        if get_entry_item:
            entry_mapping_supported = True
            item = get_entry_item()
            if item is not None:
                entry_by_item.setdefault(item.get_path_name(), []).append(entry)
        elif entry is not None:
            entry_scan_mapped = False
    get_selected, get_index = (_native_getter(obj, name) for name in ('bp_get_selected_item', 'get_index_for_item'))
    selection_supported = bool(get_selected)
    selected = get_selected() if get_selected else None
    selected_index = get_index(selected) if selected is not None and get_index else None
    items = []
    for item_index in range(offset, min(count, offset + limit)):
        item = get_item(item_index)
        item_info = _object_info(item)
        item_entries = entry_by_item.get(item_info['path'], []) if item_info else []
        if not item_entries and get_entry and item is not None:
            entry = get_entry(item)
            if entry is not None:
                item_entries = [entry]
        mapping_complete = (entry_scan_complete and entry_scan_mapped and entry_mapping_supported) or bool(get_entry)
        items.append(dict(index=item_index, item=item_info, entries=[_object_info(e) for e in item_entries],
                          entry_mapping_complete=mapping_complete,
                          **(_properties(item, fields) if item is not None else {'properties': {}, 'property_errors': {}})))
    return {'kind': 'list', 'object': _object_info(obj), 'count_getter': count_getter,
            'logical_item_count': count, 'generated_entry_count': len(entries), 'selected_item': _object_info(selected),
            'selection_supported': selection_supported, 'entry_mapping_supported': entry_mapping_supported,
            'entry_scan_complete': entry_scan_complete,
            'selected_index': selected_index, 'offset': offset, 'limit': limit, 'items': items,
            'items_truncated': offset > 0 or offset + len(items) < count,
            'generated_entries': [_object_info(e) for e in entries[:limit]], 'entries_truncated': len(entries) > limit,
            'coverage': 'Native list model and generated entries; not nonempty inventory count, visible Slate count, pool capacity or arbitrary TS business data.'}
