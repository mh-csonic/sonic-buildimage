from sonic_config_version.adapters.community_sonic import CommunitySonicAdapter


class RecordingRunner:
    def __init__(self):
        self.calls = []

    def run(self, argv, check=True):
        self.calls.append((argv, check))
        if argv[-2:] == ["-d", "--print-data"]:
            return 0, '{"DEVICE_METADATA":{"localhost":{}}}', ""
        return 0, "", ""


def test_native_adapter_uses_argument_vectors_and_expected_commands():
    runner = RecordingRunner()
    adapter = CommunitySonicAdapter(
        config_path="/usr/local/bin/config",
        cfggen_path="/usr/local/bin/sonic-cfggen",
        runner=runner,
    )
    assert adapter.export_running() == {"DEVICE_METADATA": {"localhost": {}}}
    adapter.create_checkpoint("sonicgit-abc")
    adapter.validate_candidate("/private/candidate.json")
    adapter.apply_candidate("/private/candidate.json")
    adapter.rollback_checkpoint("sonicgit-abc")
    adapter.delete_checkpoint("sonicgit-abc")
    adapter.save_startup()
    assert [call[0] for call in runner.calls] == [
        ["/usr/local/bin/sonic-cfggen", "-d", "--print-data"],
        ["/usr/local/bin/config", "checkpoint", "sonicgit-abc"],
        ["/usr/local/bin/config", "replace", "--dry-run", "/private/candidate.json"],
        ["/usr/local/bin/config", "replace", "/private/candidate.json"],
        ["/usr/local/bin/config", "rollback", "sonicgit-abc"],
        ["/usr/local/bin/config", "delete-checkpoint", "sonicgit-abc"],
        ["/usr/local/bin/config", "save", "-y"],
    ]
