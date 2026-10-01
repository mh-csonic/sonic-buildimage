import json


OPERATION_NAMES = {"added": "ADD", "removed": "DELETE", "changed": "UPDATE"}


def _text(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _table(headers, rows):
    rendered = [[_text(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in rendered:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def line(values):
        cells = []
        for index, value in enumerate(values):
            cells.append(value if index == len(values) - 1 else value.ljust(widths[index]))
        return "  ".join(cells).rstrip()

    output = [line(headers), line(["-" * width for width in widths])]
    output.extend(line(row) for row in rendered)
    return "\n".join(output)


def _fields(rows):
    width = max(len(name) for name, _ in rows)
    return "\n".join("{:<{}}: {}".format(name, width, _text(value)) for name, value in rows)


def _short_sha(commit, length=8):
    return commit[:length] if commit else "-"


def _named_commit(labels, commit):
    if not commit:
        return "-"
    if labels:
        return "{} ({})".format(", ".join(labels), _short_sha(commit))
    return _short_sha(commit)


def _described_revision(description):
    label = description.get("label")
    if label:
        return "{} ({})".format(label, description["short_commit"])
    supplied = description.get("input")
    if supplied and supplied != description.get("commit") and not supplied.startswith(description["short_commit"]):
        return "{} ({})".format(supplied, description["short_commit"])
    return description["short_commit"]


def format_status(value):
    if not value.get("initialized"):
        return _fields(
            [
                ("Repository status", "NOT INITIALIZED"),
                ("Repository", value.get("repository", "-")),
            ]
        )
    active = _named_commit(value.get("active_labels", []), value.get("active_commit"))
    startup_ref = _named_commit(value.get("startup_labels", []), value.get("startup_commit"))
    if "startup_error" in value:
        startup = "Unavailable ({})".format(value["startup_error"])
    elif value.get("startup_commit") and not value.get("startup_matches_ref"):
        startup = "Uncommitted changes (expected {})".format(startup_ref)
    else:
        startup = startup_ref
    if "running_error" in value:
        running = "Unavailable ({})".format(value["running_error"])
        drift = "Unknown"
    elif value.get("running_matches_active"):
        running = active
        drift = "No"
    else:
        running = "Uncommitted changes"
        drift = "Yes"
    return _fields(
        [
            ("Repository status", value.get("repository_status", "UNKNOWN")),
            ("Running version", running),
            ("Active version", active),
            ("Startup version", startup),
            ("Configuration drift", drift),
        ]
    )


def format_history(entries):
    if not entries:
        return "No SonicGit configuration versions found."
    rows = []
    for entry in entries:
        rows.append(
            [
                ",".join(entry.get("labels", [])) or "-",
                _short_sha(entry.get("commit"), 12),
                entry.get("time", "-"),
                entry.get("operator", "-"),
                entry.get("author", "-"),
                entry.get("message", "-"),
            ]
        )
    return _table(["LABEL", "COMMIT", "DATE/TIME", "OPERATOR", "AUTHOR", "MESSAGE"], rows)


def _format_change_value(value, missing=False):
    return "-" if missing else _text(value)


def format_change_table(rows):
    rendered = []
    for row in rows:
        operation = OPERATION_NAMES.get(row.get("operation"), str(row.get("operation", "")).upper())
        rendered.append(
            [
                operation,
                row.get("table") if row.get("table") is not None else "null",
                row.get("key") if row.get("key") is not None else "null",
                row.get("field") if row.get("field") is not None else "null",
                _format_change_value(row.get("old"), missing=row.get("operation") == "added"),
                _format_change_value(row.get("new"), missing=row.get("operation") == "removed"),
            ]
        )
    return _table(["OPERATION", "TABLE", "KEY", "FIELD", "OLD", "NEW"], rendered)


def format_diff(report):
    heading = "From: {}\nTo:   {}".format(
        _described_revision(report["from"]),
        _described_revision(report["to"]),
    )
    if not report.get("rows"):
        return heading + "\n\nNo semantic configuration differences."
    return heading + "\n\n" + format_change_table(report["rows"])


def format_drift(value):
    active = _named_commit(value.get("active_labels", []), value.get("active_commit"))
    summary = value.get("summary", {})
    output = [
        _fields(
            [
                ("Active version", active),
                ("Active commit", _short_sha(value.get("active_commit"))),
                ("Expected hash", _short_sha(value.get("expected_sha256")) + "..."),
                ("Running hash", _short_sha(value.get("running_sha256")) + "..."),
                ("Drift", "Detected" if value.get("drifted") else "Not detected"),
            ]
        ),
        "",
        "Changes since active version:",
        _fields(
            [
                ("  Tables changed", summary.get("tables_changed", 0)),
                ("  Entries added", summary.get("entries_added", 0)),
                ("  Entries updated", summary.get("entries_updated", 0)),
                ("  Entries deleted", summary.get("entries_deleted", 0)),
            ]
        ),
    ]
    if value.get("rows"):
        output.extend(["", format_change_table(value["rows"])])
    return "\n".join(output)


def format_audit(events):
    if not events:
        return "No SonicGit audit records found."
    rows = []
    for event in events:
        details = event.get("details", {})
        summary = []
        if details.get("label"):
            summary.append("label={}".format(details["label"]))
        commit = details.get("target_commit") or details.get("commit")
        if commit:
            summary.append("commit={}".format(_short_sha(commit)))
        if "dry_run" in details:
            summary.append("dry-run={}".format("yes" if details["dry_run"] else "no"))
        if "startup_matches" in details:
            summary.append("startup-match={}".format("yes" if details["startup_matches"] else "no"))
        if details.get("message"):
            summary.append("message={}".format(details["message"]))
        if details.get("error"):
            summary.append("error={}".format(details["error"]))
        rendered_summary = "; ".join(summary) or "-"
        if len(rendered_summary) > 120:
            rendered_summary = rendered_summary[:117] + "..."
        rows.append(
            [
                event.get("timestamp", "-"),
                event.get("operator", "-"),
                event.get("action", "-"),
                event.get("result", "-"),
                _short_sha(details.get("operation_id")),
                rendered_summary,
            ]
        )
    return _table(["DATE/TIME", "OPERATOR", "ACTION", "RESULT", "OP ID", "DETAILS"], rows)


def format_labels(entries):
    if not entries:
        return "No SonicGit labels found."
    rows = []
    for entry in entries:
        rows.append(
            [
                entry["label"],
                _short_sha(entry["commit"], 12),
                entry.get("message", "-"),
            ]
        )
    return _table(["LABEL", "COMMIT", "MESSAGE"], rows)


def format_inspect(value):
    metadata = value["metadata"]
    return _fields(
        [
            ("Label", ", ".join(value.get("labels", [])) or "-"),
            ("Commit", value["commit"]),
            ("Created", metadata.get("created_at", "-")),
            ("Operator", metadata.get("operator", "-")),
            ("Author", "SonicGit"),
            ("Message", metadata.get("message", "-")),
            ("Configuration SHA256", metadata.get("configuration_sha256", "-")),
            ("Active", value.get("active", False)),
            ("Startup", value.get("startup", False)),
        ]
    )


def format_capability(value):
    sections = [
        _fields(
            [
                ("SonicGit version", value.get("sonic_git_version", "-")),
                ("Repository", value.get("repository", "-")),
                ("Repository initialized", value.get("repository_initialized", False)),
                ("Repository policy", value.get("policy", "-")),
                ("Configured remotes", value.get("remote_count", 0)),
                ("Git", value.get("git_version", "-")),
            ]
        )
    ]
    system = value.get("system", {})
    if system:
        sections.extend(
            [
                "",
                "System:",
                _fields(
                    [
                        ("  Platform", system.get("platform", "-")),
                        ("  HwSKU", system.get("hwsku", "-")),
                        ("  SONiC release", system.get("sonic_release", "-")),
                        ("  ASIC count", system.get("asic_count", "-")),
                    ]
                ),
            ]
        )
    native = value.get("native", {})
    commands = native.get("native_commands", {})
    if commands:
        sections.extend(
            [
                "",
                "Native commands:",
                _table(
                    ["COMMAND", "AVAILABLE"],
                    [[name, available] for name, available in sorted(commands.items())],
                ),
            ]
        )
    if value.get("system_error"):
        sections.extend(["", "System error: {}".format(value["system_error"])])
    return "\n".join(sections)
