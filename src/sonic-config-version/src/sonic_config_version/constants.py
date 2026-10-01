BASE_DIR = "/var/lib/sonic/config-version"
REPOSITORY_DIRNAME = "repository"
AUDIT_RELATIVE_PATH = "audit/audit.jsonl"
OPERATION_LOCK_RELATIVE_PATH = "locks/operation.lock"
TMP_DIRNAME = "tmp"
CHECKPOINT_METADATA_DIRNAME = "checkpoints"

ACTIVE_REF = "refs/sonic/active"
STARTUP_REF = "refs/sonic/startup"
LABEL_REF_PREFIX = "refs/tags/"
CONFIG_PATH = "config/config_db.json"
METADATA_PATH = "metadata/version.json"
NORMALIZATION_VERSION = 1

GIT_PATH = "/usr/bin/git"
CONFIG_CLI_PATH = "/usr/local/bin/config"
SONIC_CFGGEN_PATH = "/usr/local/bin/sonic-cfggen"
STARTUP_CONFIG_PATH = "/etc/sonic/config_db.json"
NATIVE_CHECKPOINT_DIR = "/etc/sonic/checkpoints"
RELOAD_LOCK_PATH = "/etc/sonic/reload.lock"

COMMAND_TIMEOUT_SECONDS = 300
GIT_TIMEOUT_SECONDS = 30
MAX_COMMAND_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_JSON_BYTES = 64 * 1024 * 1024
MIN_FREE_BYTES = 1024 * 1024
MIN_FREE_INODES = 10
STABLE_EXPORT_ATTEMPTS = 3
