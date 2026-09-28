import pytest

from sonic_config_version.errors import ValidationError
from sonic_config_version.snapshot.exporter import StableExporter
from sonic_config_version.snapshot.semantic_diff import semantic_diff


class SequencedAdapter:
    def __init__(self, values):
        self.values = iter(values)

    def export_running(self):
        return next(self.values)


def test_stable_export_accepts_two_matching_observations():
    exporter = StableExporter(SequencedAdapter([{"a": 1}, {"a": 2}, {"a": 1}]))
    normalized, _ = exporter.export()
    assert normalized == b'{"a":1}\n'


def test_stable_export_rejects_three_different_observations():
    exporter = StableExporter(SequencedAdapter([{"a": 1}, {"a": 2}, {"a": 3}]))
    with pytest.raises(ValidationError):
        exporter.export()


def test_semantic_diff_reports_leaf_paths():
    left = {"VLAN": {"Vlan100": {"vlanid": "100"}}}
    right = {"VLAN": {"Vlan100": {"vlanid": "200"}}, "BGP_NEIGHBOR": {"10.0.0.1": {"asn": "1"}}}
    changes = semantic_diff(left, right)
    assert {item["path"] for item in changes} == {
        "/VLAN/Vlan100/vlanid",
        "/BGP_NEIGHBOR/10.0.0.1/asn",
    }


def test_semantic_diff_reports_added_empty_entries():
    changes = semantic_diff({}, {"LOOPBACK_INTERFACE": {"Loopback0|10.0.0.1/32": {}}})
    assert changes == [
        {
            "path": "/LOOPBACK_INTERFACE/Loopback0|10.0.0.1/32",
            "change": "added",
            "old": None,
            "new": {},
        }
    ]
