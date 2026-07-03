from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# %x1e = record separator between commits, %x1f = field separator within header
_LOG_FORMAT = "%x1e%H%x1f%ae%x1f%an%x1f%aI%x1f%P"


@dataclass
class FileChange:
    path: str
    added: int
    deleted: int


@dataclass
class Commit:
    sha: str
    author_email: str
    author_name: str
    authored_at: datetime
    changes: list[FileChange]
    parents: list[str] = field(default_factory=list)


class RepoIngest:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self._commits: list[Commit] | None = None
        self._patch_text: str | None = None

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), *args],
            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return result.stdout

    def commits(self) -> list[Commit]:
        if self._commits is not None:
            return self._commits
        raw = self._git("log", "--numstat", f"--format={_LOG_FORMAT}")
        parsed: list[Commit] = []
        for record in raw.split("\x1e")[1:]:
            lines = [ln for ln in record.strip("\n").split("\n") if ln.strip()]
            sha, email, name, iso_date, parents_raw = lines[0].split("\x1f")
            changes = []
            for line in lines[1:]:
                added_s, deleted_s, path = line.split("\t", 2)
                changes.append(FileChange(
                    path=path,
                    added=0 if added_s == "-" else int(added_s),
                    deleted=0 if deleted_s == "-" else int(deleted_s),
                ))
            parsed.append(Commit(
                sha=sha, author_email=email, author_name=name,
                authored_at=datetime.fromisoformat(iso_date), changes=changes,
                parents=parents_raw.split(),
            ))
        self._commits = parsed
        return parsed

    def list_files(self) -> list[str]:
        return [ln for ln in self._git("ls-files").splitlines() if ln.strip()]

    def tags(self) -> list[tuple[str, datetime]]:
        """Tags with their commit author dates, oldest first."""
        names = [t for t in self._git("tag", "--list").splitlines() if t.strip()]
        result = []
        for name in names:
            iso = self._git("log", "-1", "--format=%aI", name).strip()
            result.append((name, datetime.fromisoformat(iso)))
        result.sort(key=lambda pair: pair[1])
        return result

    def full_patch_text(self) -> str:
        """git log -p output; each commit record starts with \\x1eCOMMIT <sha>. Cached."""
        if self._patch_text is None:
            self._patch_text = self._git("log", "-p", "--format=%x1eCOMMIT %H")
        return self._patch_text

    def iter_patch_records(self):
        """Yields each commit's 'COMMIT <sha>\\n<diff>' record from git log -p one at a
        time, streaming git's stdout instead of buffering the full history in memory.
        Equivalent in content to full_patch_text().split("\\x1e"), but memory use is
        bounded by the largest single commit's diff rather than total history size --
        needed for repos where a full-history patch text can exceed available RAM."""
        proc = subprocess.Popen(
            ["git", "-C", str(self.repo_path), "log", "-p", "--format=%x1eCOMMIT %H"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        )
        assert proc.stdout is not None
        buffer = ""
        try:
            for chunk in iter(lambda: proc.stdout.read(1 << 20), ""):
                buffer += chunk
                *records, buffer = buffer.split("\x1e")
                yield from records
            if buffer:
                yield buffer
        finally:
            proc.stdout.close()
            returncode = proc.wait()
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, proc.args)
