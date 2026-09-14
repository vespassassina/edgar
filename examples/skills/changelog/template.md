### Added
- `edgar skills list` shows every skill a session here can load, and where it came from.

### Changed
- `--mode` is required with `-p`, so a piped run never asks a question nobody can answer.

### Fixed
- A cancelled shell command no longer waits on a pipe its child process still holds.
