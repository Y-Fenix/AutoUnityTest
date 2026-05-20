from __future__ import annotations

import fnmatch
import json
import os
import pathlib
import subprocess
import threading
import time
from datetime import datetime
from typing import Any, Callable


DEFAULT_WATCH_PATTERNS = "\n".join([
    "LevelData/*.csv",
    "Assets/Resources/Config/Localization/*.asset",
])
EVENT_LIMIT = 80


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def split_patterns(raw: str) -> list[str]:
    return [line.strip() for line in str(raw or "").splitlines() if line.strip()]


def normalize_changed_files(files: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in files:
        value = str(item or "").strip().replace("\\", "/")
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def iter_pattern_variants(pattern: str) -> list[str]:
    variants = [pattern]
    collapsed = pattern
    while "**/" in collapsed:
        collapsed = collapsed.replace("**/", "", 1)
        if collapsed not in variants:
            variants.append(collapsed)
    return variants


def match_path_pattern(file: str, pattern: str) -> bool:
    for candidate in iter_pattern_variants(pattern):
        if fnmatch.fnmatch(file, candidate):
            return True
        if not candidate.startswith("/") and fnmatch.fnmatch(file, f"*/{candidate}"):
            return True
    return False


def filter_watched_files(files: list[str], include_raw: str, ignore_raw: str) -> list[str]:
    include_patterns = split_patterns(include_raw) or split_patterns(DEFAULT_WATCH_PATTERNS)
    ignore_patterns = split_patterns(ignore_raw)
    matched: list[str] = []
    for file in normalize_changed_files(files):
        if ignore_patterns and any(match_path_pattern(file, pattern) for pattern in ignore_patterns):
            continue
        if any(match_path_pattern(file, pattern) for pattern in include_patterns):
            matched.append(file)
    return matched


def git_command(repo_path: pathlib.Path, args: list[str], timeout: int = 120) -> str:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    completed = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return completed.stdout.strip()


def git_commit_info(repo_path: pathlib.Path, rev: str) -> dict[str, str]:
    raw = git_command(
        repo_path,
        [
            "show",
            "-s",
            "--format=%H%n%h%n%an%n%ad%n%s",
            "--date=format:%Y-%m-%d %H:%M:%S",
            rev,
        ],
    )
    lines = raw.splitlines()
    return {
        "commit": lines[0] if len(lines) > 0 else rev,
        "short_commit": lines[1] if len(lines) > 1 else rev[:8],
        "author": lines[2] if len(lines) > 2 else "",
        "date": lines[3] if len(lines) > 3 else "",
        "subject": lines[4] if len(lines) > 4 else "",
    }


def git_changed_files(repo_path: pathlib.Path, old_rev: str, new_rev: str) -> list[str]:
    if not old_rev or old_rev == new_rev:
        return []
    raw = git_command(repo_path, ["diff", "--name-only", old_rev, new_rev], timeout=180)
    return normalize_changed_files(raw.splitlines())


class GitWatchController:
    def __init__(
        self,
        store_path: pathlib.Path,
        defaults: dict[str, Any],
        on_trigger: Callable[[dict[str, Any], dict[str, Any]], None],
        is_job_running: Callable[[], bool],
    ) -> None:
        self.store_path = store_path
        self.lock = threading.Lock()
        self.on_trigger = on_trigger
        self.is_job_running = is_job_running
        self.defaults = dict(defaults)
        self.settings = dict(defaults)
        self.enabled = False
        self.checking = False
        self.last_check_at = ""
        self.last_error = ""
        self.watch_ref = ""
        self.current_head = ""
        self.last_seen_commit = ""
        self.last_triggered_commit = ""
        self.last_triggered_at = ""
        self.last_match_files: list[str] = []
        self.pending_trigger: dict[str, Any] | None = None
        self.events: list[dict[str, Any]] = []
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self._load()

    def _repo_path(self, settings: dict[str, Any]) -> pathlib.Path:
        value = str(settings.get("git_repo_path") or "").strip()
        if not value:
            raise ValueError("请先填写 Git 仓库路径。")
        return pathlib.Path(value).expanduser().resolve()

    def _watch_ref(self, settings: dict[str, Any]) -> str:
        remote = str(settings.get("git_remote") or "").strip()
        branch = str(settings.get("git_branch") or "").strip()
        if remote and branch:
            return f"{remote}/{branch}"
        if branch:
            return branch
        return "HEAD"

    def _normalize_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = dict(self.defaults)
        merged.update(settings or {})
        default_remote = str(self.defaults.get("git_remote") or "").strip()
        default_branch = str(self.defaults.get("git_branch") or "main").strip() or "main"
        merged["git_repo_path"] = str(merged.get("git_repo_path") or "").strip()
        merged["git_remote"] = str(merged.get("git_remote") if merged.get("git_remote") is not None else default_remote).strip()
        merged["git_branch"] = str(merged.get("git_branch") if merged.get("git_branch") is not None else default_branch).strip() or default_branch
        merged["watch_patterns"] = str(merged.get("watch_patterns") or DEFAULT_WATCH_PATTERNS).strip()
        merged["ignore_patterns"] = str(merged.get("ignore_patterns") or "").strip()
        merged["project_path"] = str(merged.get("project_path") or "").strip()
        merged["unity_path"] = str(merged.get("unity_path") or "").strip()
        merged["webhook"] = str(merged.get("webhook") or "").strip()
        merged["poll_seconds"] = max(10, int(merged.get("poll_seconds") or 30))
        merged["timeout_seconds"] = max(60, int(merged.get("timeout_seconds") or 1800))
        merged["process_timeout_seconds"] = max(0, int(merged.get("process_timeout_seconds") or 0))
        merged["send_after_run"] = bool(merged.get("send_after_run", True))
        merged["keep_runner"] = bool(merged.get("keep_runner", False))
        return merged

    def _event(self, level: str, title: str, detail: str = "", **extra: Any) -> dict[str, Any]:
        event = {
            "time": now_text(),
            "level": level,
            "title": title,
            "detail": detail,
        }
        for key, value in extra.items():
            if value not in (None, "", [], {}):
                event[key] = value
        return event

    def _push_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        self.events = self.events[-EVENT_LIMIT:]

    def _save_unlocked(self) -> None:
        payload = {
            "settings": self.settings,
            "runtime": {
                "enabled": self.enabled,
                "last_check_at": self.last_check_at,
                "last_error": self.last_error,
                "watch_ref": self.watch_ref,
                "current_head": self.current_head,
                "last_seen_commit": self.last_seen_commit,
                "last_triggered_commit": self.last_triggered_commit,
                "last_triggered_at": self.last_triggered_at,
                "last_match_files": self.last_match_files,
                "pending_trigger": self.pending_trigger,
                "events": self.events,
            },
        }
        self.store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save(self) -> None:
        with self.lock:
            self._save_unlocked()

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            return
        settings = payload.get("settings") or {}
        runtime = payload.get("runtime") or {}
        self.settings = self._normalize_settings(settings)
        self.enabled = bool(runtime.get("enabled", False))
        self.last_check_at = str(runtime.get("last_check_at") or "")
        self.last_error = str(runtime.get("last_error") or "")
        self.watch_ref = str(runtime.get("watch_ref") or "")
        self.current_head = str(runtime.get("current_head") or "")
        self.last_seen_commit = str(runtime.get("last_seen_commit") or "")
        self.last_triggered_commit = str(runtime.get("last_triggered_commit") or "")
        self.last_triggered_at = str(runtime.get("last_triggered_at") or "")
        self.last_match_files = list(runtime.get("last_match_files") or [])
        self.pending_trigger = runtime.get("pending_trigger") or None
        self.events = list(runtime.get("events") or [])[-EVENT_LIMIT:]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "settings": dict(self.settings),
                "enabled": self.enabled,
                "checking": self.checking,
                "last_check_at": self.last_check_at,
                "last_error": self.last_error,
                "watch_ref": self.watch_ref,
                "current_head": self.current_head,
                "last_seen_commit": self.last_seen_commit,
                "last_triggered_commit": self.last_triggered_commit,
                "last_triggered_at": self.last_triggered_at,
                "last_match_files": list(self.last_match_files),
                "pending_trigger": dict(self.pending_trigger) if self.pending_trigger else None,
                "events": list(self.events),
            }

    def current_settings(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.settings)

    def sync_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_settings(settings)
        with self.lock:
            self.settings = normalized
            self._save_unlocked()
        return self.snapshot()

    def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_settings(settings)
        with self.lock:
            identity_changed = any(
                self.settings.get(key) != normalized.get(key)
                for key in ("git_repo_path", "git_remote", "git_branch")
            )
            self.settings = normalized
            self.last_error = ""
            if identity_changed:
                self.watch_ref = ""
                self.current_head = ""
                self.last_seen_commit = ""
                self.pending_trigger = None
                self.last_match_files = []
                self._push_event(
                    self._event(
                        "info",
                        "已重置监听基线",
                        "Git 跟踪目标已变更，请重新设为当前基线或立即检查。",
                    )
                )
            self._push_event(self._event("info", "已保存监听参数"))
            self._save_unlocked()
        return self.snapshot()

    def start(self) -> dict[str, Any]:
        should_start_thread = False
        with self.lock:
            if self.enabled and self.thread is not None and self.thread.is_alive():
                return {
                    "settings": dict(self.settings),
                    "enabled": self.enabled,
                    "checking": self.checking,
                    "last_check_at": self.last_check_at,
                    "last_error": self.last_error,
                    "watch_ref": self.watch_ref,
                    "current_head": self.current_head,
                    "last_seen_commit": self.last_seen_commit,
                    "last_triggered_commit": self.last_triggered_commit,
                    "last_triggered_at": self.last_triggered_at,
                    "last_match_files": list(self.last_match_files),
                    "pending_trigger": dict(self.pending_trigger) if self.pending_trigger else None,
                    "events": list(self.events),
                }
            self.enabled = True
            self.stop_event = threading.Event()
            self._push_event(self._event("success", "已开始监听 Git"))
            self._save_unlocked()
            thread = threading.Thread(target=self._loop, daemon=True)
            self.thread = thread
            should_start_thread = True
        if should_start_thread:
            thread.start()
        return self.snapshot()

    def stop(self) -> dict[str, Any]:
        with self.lock:
            self.enabled = False
            self.stop_event.set()
            self._push_event(self._event("warn", "已停止监听 Git"))
            self._save_unlocked()
        return self.snapshot()

    def request_check(self) -> dict[str, Any]:
        if not self._begin_check():
            raise RuntimeError("Git 正在检查中，请稍后。")
        with self.lock:
            self.last_error = ""
            self._push_event(self._event("info", "开始手动检查", f"正在检查 {self._watch_ref(self.settings)}"))
            self._save_unlocked()
        threading.Thread(target=self.poll_once, kwargs={"manual": True, "already_started": True}, daemon=True).start()
        return self.snapshot()

    def set_baseline_to_current(self) -> dict[str, Any]:
        settings = self.current_settings()
        repo_path = self._repo_path(settings)
        ref = self._watch_ref(settings)
        remote = str(settings.get("git_remote") or "").strip()
        if remote:
            git_command(repo_path, ["fetch", remote, "--prune"], timeout=180)
        commit = git_command(repo_path, ["rev-parse", ref])
        info = git_commit_info(repo_path, commit)
        with self.lock:
            self.watch_ref = ref
            self.current_head = commit
            self.last_seen_commit = commit
            self.last_check_at = now_text()
            self.last_error = ""
            self._push_event(
                self._event(
                    "info",
                    "已设定当前基线",
                    f"{info.get('short_commit', commit[:8])} {info.get('subject', '')}".strip(),
                    commit=commit,
                )
            )
            self._save_unlocked()
        return self.snapshot()

    def _begin_check(self) -> bool:
        with self.lock:
            if self.checking:
                return False
            self.checking = True
            self._save_unlocked()
            return True

    def _finish_check(self) -> None:
        with self.lock:
            self.checking = False
            self._save_unlocked()

    def _loop(self) -> None:
        while True:
            with self.lock:
                enabled = self.enabled
                stop_event = self.stop_event
                interval = max(10, int(self.settings.get("poll_seconds") or 30))
            if not enabled:
                return
            self.poll_once(manual=False)
            for _ in range(interval):
                if stop_event.wait(1):
                    return

    def poll_once(self, manual: bool = False, already_started: bool = False) -> None:
        if not already_started and not self._begin_check():
            return
        trigger_to_start: dict[str, Any] | None = None
        try:
            settings = self.current_settings()
            repo_path = self._repo_path(settings)
            if not repo_path.is_dir():
                raise FileNotFoundError(f"Git 仓库路径不存在：{repo_path}")
            if not (repo_path / ".git").exists():
                raise FileNotFoundError(f"目标路径不是 Git 仓库：{repo_path}")

            remote = str(settings.get("git_remote") or "").strip()
            ref = self._watch_ref(settings)
            with self.lock:
                self.watch_ref = ref
                self._save_unlocked()
            if remote:
                git_command(repo_path, ["fetch", remote, "--prune"], timeout=180)
            head_commit = git_command(repo_path, ["rev-parse", ref])
            head_info = git_commit_info(repo_path, head_commit)

            changed_files: list[str] = []
            matched_files: list[str] = []
            with self.lock:
                previous_commit = self.last_seen_commit

            if previous_commit and previous_commit != head_commit:
                changed_files = git_changed_files(repo_path, previous_commit, head_commit)
                matched_files = filter_watched_files(
                    changed_files,
                    str(settings.get("watch_patterns") or DEFAULT_WATCH_PATTERNS),
                    str(settings.get("ignore_patterns") or ""),
                )

            with self.lock:
                self.last_check_at = now_text()
                self.last_error = ""
                self.watch_ref = ref
                self.current_head = head_commit

                if not self.last_seen_commit:
                    self.last_seen_commit = head_commit
                    self._push_event(
                        self._event(
                            "info",
                            "已记录初始基线",
                            f"{head_info.get('short_commit', head_commit[:8])} {head_info.get('subject', '')}".strip(),
                            commit=head_commit,
                        )
                    )
                elif self.last_seen_commit != head_commit:
                    old_commit = self.last_seen_commit
                    self.last_seen_commit = head_commit
                    if matched_files:
                        trigger = {
                            "commit": head_commit,
                            "short_commit": head_info.get("short_commit", head_commit[:8]),
                            "subject": head_info.get("subject", ""),
                            "author": head_info.get("author", ""),
                            "date": head_info.get("date", ""),
                            "files": matched_files,
                            "all_changed_files": changed_files,
                            "old_commit": old_commit,
                        }
                        if self.is_job_running():
                            self.pending_trigger = trigger
                            self._push_event(
                                self._event(
                                    "warn",
                                    "发现命中提交，等待当前任务完成",
                                    f"{trigger['short_commit']} {trigger['subject']}".strip(),
                                    commit=head_commit,
                                    files=matched_files,
                                )
                            )
                        else:
                            self.pending_trigger = None
                            self.last_triggered_commit = head_commit
                            self.last_triggered_at = now_text()
                            self.last_match_files = matched_files
                            trigger_to_start = trigger
                            self._push_event(
                                self._event(
                                    "success",
                                    "发现命中提交，准备运行脚本",
                                    f"{trigger['short_commit']} {trigger['subject']}".strip(),
                                    commit=head_commit,
                                    files=matched_files,
                                )
                            )
                    else:
                        self._push_event(
                            self._event(
                                "info",
                                "检测到新提交，但未命中监听规则",
                                f"{head_info.get('short_commit', head_commit[:8])} {head_info.get('subject', '')}".strip(),
                                commit=head_commit,
                                files=changed_files[:20],
                            )
                        )

                if not trigger_to_start and self.pending_trigger and not self.is_job_running():
                    trigger_to_start = dict(self.pending_trigger)
                    self.pending_trigger = None
                    self.last_triggered_commit = str(trigger_to_start.get("commit") or "")
                    self.last_triggered_at = now_text()
                    self.last_match_files = list(trigger_to_start.get("files") or [])
                    self._push_event(
                        self._event(
                            "success",
                            "开始处理等待中的命中提交",
                            f"{trigger_to_start.get('short_commit', '')} {trigger_to_start.get('subject', '')}".strip(),
                            commit=trigger_to_start.get("commit", ""),
                            files=trigger_to_start.get("files", []),
                        )
                    )

                if manual and not changed_files:
                    self._push_event(
                        self._event(
                            "info",
                            "已完成手动检查",
                            f"当前 {ref} 指向 {head_info.get('short_commit', head_commit[:8])}",
                            commit=head_commit,
                        )
                    )

                self._save_unlocked()

            if trigger_to_start:
                self.on_trigger(trigger_to_start, settings)
        except Exception as exc:
            with self.lock:
                self.last_check_at = now_text()
                self.last_error = str(exc)
                self._push_event(self._event("error", "Git 检查失败", str(exc)))
                self._save_unlocked()
        finally:
            self._finish_check()
