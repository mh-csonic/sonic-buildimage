import json
import uuid

from sonic_config_version import __version__
from sonic_config_version.adapters.community_sonic import CommunitySonicAdapter
from sonic_config_version.audit import AuditLog
from sonic_config_version.checkpoint import verify_checkpoint
from sonic_config_version.constants import ACTIVE_REF, BASE_DIR, RELOAD_LOCK_PATH, STARTUP_REF
from sonic_config_version.errors import CapabilityError, RepositoryError, RestoreError, ValidationError
from sonic_config_version.locking import FileLock
from sonic_config_version.repository.manager import Repository, current_operator
from sonic_config_version.snapshot.exporter import StableExporter
from sonic_config_version.snapshot.normalizer import digest, normalize_and_hash
from sonic_config_version.snapshot.semantic_diff import semantic_diff
from sonic_config_version.storage import Storage


class SonicGitManager:
    def __init__(self, base_dir=BASE_DIR, adapter=None, reload_lock_path=RELOAD_LOCK_PATH, required_uid=0):
        self.storage = Storage(base_dir)
        self.adapter = adapter or CommunitySonicAdapter()
        self.repository = Repository(self.storage, required_uid=required_uid)
        self.audit = AuditLog(self.storage.audit_path)
        self.exporter = StableExporter(self.adapter)
        self.reload_lock_path = reload_lock_path

    @staticmethod
    def _check_single_asic(info):
        if info.get("asic_count") != 1:
            raise CapabilityError("SonicGit MVP supports single-ASIC systems only")
        for field in ("platform", "hwsku", "sonic_release"):
            if not isinstance(info.get(field), str) or not info[field]:
                raise CapabilityError("SONiC {} is unavailable".format(field))

    @staticmethod
    def _check_compatibility(metadata, info):
        if info.get("asic_count") != 1 or metadata.get("asic_count") != 1:
            raise ValidationError("candidate is not a single-ASIC snapshot")
        for field in ("platform", "hwsku", "sonic_release"):
            if metadata.get(field) != info.get(field):
                raise ValidationError(
                    "candidate {} {!r} does not match this switch {!r}".format(
                        field, metadata.get(field), info.get(field)
                    )
                )

    def _record_failure(self, action, operation_id, exc):
        self.audit.append(
            action,
            "failure",
            operation_id=operation_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )

    def _update_startup_if_matching(self, sha, snapshot_hash):
        try:
            _, startup_hash = normalize_and_hash(self.adapter.read_startup())
        except Exception:
            return False
        if startup_hash == snapshot_hash:
            self.repository.update_ref(STARTUP_REF, sha)
            return True
        return False

    def initialize(self):
        operation_id = uuid.uuid4().hex
        self.storage.ensure_layout()
        try:
            with FileLock(self.storage.operation_lock_path, "init"):
                self.repository.preflight(allow_uninitialized=True)
                if self.repository.resolve_optional_ref(ACTIVE_REF):
                    raise RepositoryError("SonicGit is already initialized")
                info = self.adapter.system_info()
                self._check_single_asic(info)
                self.repository.initialize_repository()
                self.repository.preflight()
                normalized, snapshot_hash = self.exporter.export()
                sha, _ = self.repository.commit_snapshot(
                    normalized,
                    snapshot_hash,
                    "SonicGit baseline",
                    current_operator(),
                    info,
                )
                startup_matches = self._update_startup_if_matching(sha, snapshot_hash)
                self.audit.append(
                    "init",
                    "success",
                    operation_id=operation_id,
                    commit=sha,
                    configuration_sha256=snapshot_hash,
                    startup_matches=startup_matches,
                )
                return {"commit": sha, "configuration_sha256": snapshot_hash, "startup_matches": startup_matches}
        except Exception as exc:
            self._record_failure("init", operation_id, exc)
            raise

    def commit(self, message, allow_empty=False):
        operation_id = uuid.uuid4().hex
        self.storage.ensure_layout()
        try:
            with FileLock(self.storage.operation_lock_path, "commit"):
                self.repository.preflight()
                info = self.adapter.system_info()
                self._check_single_asic(info)
                normalized, snapshot_hash = self.exporter.export()
                sha, _ = self.repository.commit_snapshot(
                    normalized,
                    snapshot_hash,
                    message,
                    current_operator(),
                    info,
                    allow_empty=allow_empty,
                )
                startup_matches = self._update_startup_if_matching(sha, snapshot_hash)
                self.audit.append(
                    "commit",
                    "success",
                    operation_id=operation_id,
                    commit=sha,
                    configuration_sha256=snapshot_hash,
                    startup_matches=startup_matches,
                    message=message,
                )
                return {"commit": sha, "configuration_sha256": snapshot_hash, "startup_matches": startup_matches}
        except Exception as exc:
            self._record_failure("commit", operation_id, exc)
            raise

    def _restore_after_failure(self, checkpoint_name, original_hash):
        try:
            self.adapter.rollback_checkpoint(checkpoint_name)
            _, restored_hash = self.exporter.export()
            if restored_hash != original_hash:
                raise RestoreError("checkpoint rollback did not restore the original running hash")
            self.adapter.save_startup()
            _, startup_hash = normalize_and_hash(self.adapter.read_startup())
            if startup_hash != original_hash:
                raise RestoreError("restored startup configuration does not match the original hash")
        except Exception as exc:
            if isinstance(exc, RestoreError):
                raise
            raise RestoreError("critical: native checkpoint restoration failed: {}".format(exc))

    def _apply_revision(self, revision, dry_run, action):
        operation_id = uuid.uuid4().hex
        checkpoint_name = "sonicgit-{}".format(operation_id)
        self.storage.ensure_layout()
        try:
            with FileLock(self.storage.operation_lock_path, action):
                self.repository.preflight()
                info = self.adapter.system_info()
                self._check_single_asic(info)
                if revision is None:
                    revision = self.repository.parent_of_active()
                target_sha = self.repository.resolve_revision(revision)
                candidate, metadata = self.repository.load_snapshot(target_sha)
                candidate_hash = digest(candidate)
                self._check_compatibility(metadata, info)
                previous_active = self.repository.resolve_optional_ref(ACTIVE_REF)
                previous_startup = self.repository.resolve_optional_ref(STARTUP_REF)
                with self.storage.private_candidate(candidate) as candidate_path:
                    with FileLock(self.reload_lock_path, "sonic-git-{}".format(action), create_parent=False):
                        _, original_hash = self.exporter.export()
                        checkpoint_created = False
                        mutation_possible = False
                        checkpoint_metadata = {
                            "operation_id": operation_id,
                            "action": action,
                            "native_checkpoint": checkpoint_name,
                            "original_sha256": original_hash,
                            "target_commit": target_sha,
                            "target_sha256": candidate_hash,
                            "status": "creating",
                        }
                        self.storage.write_checkpoint_metadata(operation_id, checkpoint_metadata)
                        try:
                            self.adapter.create_checkpoint(checkpoint_name)
                            checkpoint_created = True
                            verify_checkpoint(self.adapter, checkpoint_name, original_hash)
                            checkpoint_metadata["status"] = "verified"
                            self.storage.write_checkpoint_metadata(operation_id, checkpoint_metadata)

                            try:
                                self.adapter.validate_candidate(candidate_path)
                            except Exception:
                                try:
                                    _, failed_dry_run_hash = self.exporter.export()
                                    mutation_possible = failed_dry_run_hash != original_hash
                                except Exception:
                                    mutation_possible = True
                                raise
                            try:
                                _, after_dry_run_hash = self.exporter.export()
                            except Exception:
                                mutation_possible = True
                                raise
                            if after_dry_run_hash != original_hash:
                                mutation_possible = True
                                raise ValidationError("native dry-run changed running CONFIG_DB")

                            if dry_run:
                                checkpoint_metadata["status"] = "dry-run-success"
                                self.storage.write_checkpoint_metadata(operation_id, checkpoint_metadata)
                                result = {
                                    "operation": action,
                                    "dry_run": True,
                                    "target_commit": target_sha,
                                    "configuration_sha256": candidate_hash,
                                }
                                self.audit.append(action, "success", operation_id=operation_id, **result)
                                try:
                                    self.adapter.delete_checkpoint(checkpoint_name)
                                    result["checkpoint_deleted"] = True
                                except Exception as cleanup_error:
                                    result["checkpoint_deleted"] = False
                                    checkpoint_metadata["checkpoint_cleanup_error"] = str(cleanup_error)
                                    try:
                                        self.storage.write_checkpoint_metadata(operation_id, checkpoint_metadata)
                                        self.audit.append(
                                            "checkpoint-cleanup",
                                            "failure",
                                            operation_id=operation_id,
                                            error=str(cleanup_error),
                                        )
                                    except Exception:
                                        pass
                                return result

                            mutation_possible = True
                            self.adapter.apply_candidate(candidate_path)
                            _, running_hash = self.exporter.export()
                            if running_hash != candidate_hash:
                                raise ValidationError("running CONFIG_DB does not match the selected commit")
                            self.adapter.save_startup()
                            _, startup_hash = normalize_and_hash(self.adapter.read_startup())
                            if startup_hash != candidate_hash:
                                raise ValidationError("startup configuration does not match the selected commit")

                            self.repository.update_ref(ACTIVE_REF, target_sha)
                            self.repository.update_ref(STARTUP_REF, target_sha)
                            checkpoint_metadata["status"] = "success"
                            self.storage.write_checkpoint_metadata(operation_id, checkpoint_metadata)
                            result = {
                                "operation": action,
                                "dry_run": False,
                                "target_commit": target_sha,
                                "configuration_sha256": candidate_hash,
                            }
                            self.audit.append(action, "success", operation_id=operation_id, **result)
                            try:
                                self.adapter.delete_checkpoint(checkpoint_name)
                                result["checkpoint_deleted"] = True
                            except Exception as cleanup_error:
                                result["checkpoint_deleted"] = False
                                checkpoint_metadata["checkpoint_cleanup_error"] = str(cleanup_error)
                                try:
                                    self.storage.write_checkpoint_metadata(operation_id, checkpoint_metadata)
                                    self.audit.append(
                                        "checkpoint-cleanup",
                                        "failure",
                                        operation_id=operation_id,
                                        error=str(cleanup_error),
                                    )
                                except Exception:
                                    pass
                            return result
                        except Exception as operation_error:
                            checkpoint_metadata["status"] = "failed"
                            checkpoint_metadata["error"] = str(operation_error)
                            if checkpoint_created and mutation_possible:
                                try:
                                    self._restore_after_failure(checkpoint_name, original_hash)
                                    self.repository.restore_ref(ACTIVE_REF, previous_active)
                                    self.repository.restore_ref(STARTUP_REF, previous_startup)
                                    try:
                                        self.adapter.delete_checkpoint(checkpoint_name)
                                    except Exception:
                                        pass
                                    checkpoint_metadata["restoration"] = "success"
                                except Exception as restore_error:
                                    checkpoint_metadata["restoration"] = "failed"
                                    checkpoint_metadata["restoration_error"] = str(restore_error)
                                    self.storage.write_checkpoint_metadata(operation_id, checkpoint_metadata)
                                    raise RestoreError(
                                        "{}; checkpoint restoration also failed: {}".format(
                                            operation_error, restore_error
                                        )
                                    )
                            elif checkpoint_created:
                                try:
                                    self.adapter.delete_checkpoint(checkpoint_name)
                                except Exception:
                                    pass
                            self.storage.write_checkpoint_metadata(operation_id, checkpoint_metadata)
                            raise
        except Exception as exc:
            self._record_failure(action, operation_id, exc)
            raise

    def apply(self, revision, dry_run=False):
        return self._apply_revision(revision, dry_run, "apply")

    def rollback(self, revision=None, dry_run=False):
        return self._apply_revision(revision, dry_run, "rollback")

    def status(self):
        if not self.repository.git.exists():
            return {"initialized": False, "repository": self.storage.repository}
        active = self.repository.resolve_optional_ref(ACTIVE_REF)
        startup = self.repository.resolve_optional_ref(STARTUP_REF)
        result = {
            "initialized": True,
            "repository": self.storage.repository,
            "active_commit": active,
            "startup_commit": startup,
            "remote_count": self.repository.remote_count(),
        }
        try:
            _, running_hash = self.exporter.export()
            result["running_sha256"] = running_hash
            result["running_matches_active"] = bool(
                active and digest(self.repository.load_snapshot(active)[0]) == running_hash
            )
        except Exception as exc:
            result["running_error"] = str(exc)
        try:
            _, startup_hash = normalize_and_hash(self.adapter.read_startup())
            result["startup_sha256"] = startup_hash
            result["startup_matches_ref"] = bool(
                startup and digest(self.repository.load_snapshot(startup)[0]) == startup_hash
            )
        except Exception as exc:
            result["startup_error"] = str(exc)
        return result

    def history(self, limit=20):
        return self.repository.history(limit)

    def diff(self, left, right, output_format="semantic"):
        if output_format == "git":
            return self.repository.raw_diff(left, right)
        left_value = json.loads(self.repository.load_snapshot(self.repository.resolve_revision(left))[0])
        right_value = json.loads(self.repository.load_snapshot(self.repository.resolve_revision(right))[0])
        return semantic_diff(left_value, right_value)

    def drift(self, verbose=False):
        active = self.repository.resolve_optional_ref(ACTIVE_REF)
        if not active:
            raise RepositoryError("active reference is not set")
        active_value = json.loads(self.repository.load_snapshot(active)[0])
        running, running_hash = self.exporter.export()
        changes = semantic_diff(active_value, json.loads(running))
        result = {"drifted": bool(changes), "change_count": len(changes), "running_sha256": running_hash}
        if verbose:
            result["changes"] = changes
        return result

    def audit_events(self, limit=20):
        return self.audit.read(limit)

    def capability(self):
        info = {}
        info_error = None
        try:
            info = self.adapter.system_info()
        except Exception as exc:
            info_error = str(exc)
        try:
            git_version = self.repository.git.version()
        except Exception as exc:
            git_version = "unavailable: {}".format(exc)
        result = {
            "sonic_git_version": __version__,
            "repository": self.storage.repository,
            "repository_initialized": self.repository.git.exists(),
            "policy": "local-only; Git remotes block modifying operations",
            "remote_count": self.repository.remote_count() if self.repository.git.exists() else 0,
            "git_path": self.repository.git.git_path,
            "git_version": git_version,
            "system": info,
            "native": self.adapter.capabilities(),
        }
        if info_error:
            result["system_error"] = info_error
        return result
