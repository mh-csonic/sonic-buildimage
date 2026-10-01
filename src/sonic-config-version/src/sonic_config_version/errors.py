class SonicGitError(Exception):
    code = "SG001"


class UsageError(SonicGitError):
    code = "SG002"


class CapabilityError(SonicGitError):
    code = "SG003"


class StorageError(SonicGitError):
    code = "SG004"


class LockError(SonicGitError):
    code = "SG005"


class CommandError(SonicGitError):
    code = "SG006"


class RepositoryError(SonicGitError):
    code = "SG007"


class ValidationError(SonicGitError):
    code = "SG008"


class NoChangeError(SonicGitError):
    code = "SG009"


class RestoreError(SonicGitError):
    code = "SG010"
