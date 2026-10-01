_MISSING = object()


def _walk(left, right, path, changes):
    if left is _MISSING and isinstance(right, dict) and right:
        for key in sorted(right):
            _walk(_MISSING, right[key], path + [str(key)], changes)
        return
    if right is _MISSING and isinstance(left, dict) and left:
        for key in sorted(left):
            _walk(left[key], _MISSING, path + [str(key)], changes)
        return
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            _walk(left.get(key, _MISSING), right.get(key, _MISSING), path + [str(key)], changes)
        return
    if left == right:
        return
    if left is _MISSING:
        kind, old, new = "added", None, right
    elif right is _MISSING:
        kind, old, new = "removed", left, None
    else:
        kind, old, new = "changed", left, right
    changes.append({"segments": list(path), "change": kind, "old": old, "new": new})


def _raw_changes(left, right):
    changes = []
    _walk(left, right, [], changes)
    return changes


def semantic_diff(left, right):
    return [
        {
            "path": "/" + "/".join(item["segments"]),
            "change": item["change"],
            "old": item["old"],
            "new": item["new"],
        }
        for item in _raw_changes(left, right)
    ]


def semantic_diff_records(left, right):
    """Return semantic changes split into CONFIG_DB table, key, and field."""
    result = []
    for item in _raw_changes(left, right):
        segments = item["segments"]
        result.append(
            {
                "operation": item["change"],
                "table": segments[0] if segments else None,
                "key": segments[1] if len(segments) > 1 else None,
                "field": "/".join(segments[2:]) if len(segments) > 2 else None,
                "old": item["old"],
                "new": item["new"],
            }
        )
    return result


def summarize_config_changes(left, right):
    """Count changed CONFIG_DB tables and unique added, updated, or deleted entries."""
    tables = set()
    added = set()
    updated = set()
    deleted = set()
    for table in set(left) | set(right):
        left_table = left.get(table, _MISSING)
        right_table = right.get(table, _MISSING)
        if left_table == right_table:
            continue
        tables.add(str(table))
        if left_table is _MISSING and isinstance(right_table, dict):
            added.update((str(table), str(key)) for key in right_table)
            continue
        if right_table is _MISSING and isinstance(left_table, dict):
            deleted.update((str(table), str(key)) for key in left_table)
            continue
        if not isinstance(left_table, dict) or not isinstance(right_table, dict):
            if left_table is _MISSING:
                added.add((str(table), None))
            elif right_table is _MISSING:
                deleted.add((str(table), None))
            else:
                updated.add((str(table), None))
            continue
        for key in set(left_table) | set(right_table):
            left_entry = left_table.get(key, _MISSING)
            right_entry = right_table.get(key, _MISSING)
            identity = (str(table), str(key))
            if left_entry is _MISSING:
                added.add(identity)
            elif right_entry is _MISSING:
                deleted.add(identity)
            elif left_entry != right_entry:
                updated.add(identity)
    return {
        "tables_changed": len(tables),
        "entries_added": len(added),
        "entries_updated": len(updated),
        "entries_deleted": len(deleted),
    }
