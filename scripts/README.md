# Verification and operations

Operational scripts use nonzero failures, explicit owned paths and redacted output. `acceptance.sh` runs the complete verification suite and exits 2 with PARTIAL while external hard gates remain unavailable; `backup.sh` and `restore-check.sh` never create or modify a database.
