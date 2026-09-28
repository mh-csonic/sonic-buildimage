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
    changes.append({"path": "/" + "/".join(path), "change": kind, "old": old, "new": new})


def semantic_diff(left, right):
    changes = []
    _walk(left, right, [], changes)
    return changes
