#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M0-4 TaskScheduler.

Read a YAML/JSON task graph, execute it in dependency order, and write a
machine-readable execution report. The task "execution" is simulated by
sleeping for each task's configured duration.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence, TextIO


MAX_ATTEMPTS = 3
REPORT_STATUSES = {"SUCCESS", "FAILED", "SKIPPED", "TIMEOUT"}
ANSI_COLORS = {
    "SUCCESS": "\033[32m",
    "FAILED": "\033[31m",
    "RETRY": "\033[33m",
    "SKIPPED": "\033[34m",
    "TIMEOUT": "\033[31m",
}
ANSI_RESET = "\033[0m"


class SchedulerError(Exception):
    """An expected, user-facing error that should not print a traceback."""


@dataclass(frozen=True)
class Task:
    name: str
    duration: float
    success_rate: float
    dependencies: tuple[str, ...]
    index: int


@dataclass(frozen=True)
class SchedulerConfig:
    tasks: tuple[Task, ...]
    timeout: float | None


@dataclass
class TaskResult:
    name: str
    status: str
    attempts: int = 0
    duration: float = 0.0
    started_at: float | None = None
    ended_at: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "attempts": self.attempts,
            "duration": round(self.duration, 6),
            "started_at": (
                round(self.started_at, 6) if self.started_at is not None else None
            ),
            "ended_at": (
                round(self.ended_at, 6) if self.ended_at is not None else None
            ),
        }


class ConsoleLogger:
    """Print flush-safe status lines and only use ANSI when writing to a TTY."""

    def __init__(
        self,
        stream: TextIO,
        run_started: float,
        color: bool | None = None,
    ) -> None:
        self.stream = stream
        self.run_started = run_started
        if color is None:
            color = (
                getattr(stream, "isatty", lambda: False)()
                and "NO_COLOR" not in os.environ
                and os.environ.get("TERM") != "dumb"
            )
        self.color = color

    def emit(self, status: str, message: str) -> None:
        elapsed = time.monotonic() - self.run_started
        label = f"{status:<7}"
        if self.color and status in ANSI_COLORS:
            label = f"{ANSI_COLORS[status]}{label}{ANSI_RESET}"
        print(f"[{elapsed:8.3f}s] {label} {message}", file=self.stream, flush=True)

    def info(self, message: str) -> None:
        elapsed = time.monotonic() - self.run_started
        print(f"[{elapsed:8.3f}s] {message}", file=self.stream, flush=True)


def _number(
    value: object,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchedulerError(f"{field} 必须是数值")
    number = float(value)
    if not math.isfinite(number):
        raise SchedulerError(f"{field} 必须是有限数值")
    if minimum is not None and number < minimum:
        raise SchedulerError(f"{field} 不能小于 {minimum:g}")
    if maximum is not None and number > maximum:
        raise SchedulerError(f"{field} 不能大于 {maximum:g}")
    return number


def _load_document(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise SchedulerError(f"配置文件不存在: {path}") from None
    except UnicodeDecodeError as exc:
        raise SchedulerError(f"配置文件不是有效的 UTF-8 文本: {exc}") from None
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise SchedulerError(f"无法读取配置文件 {path}: {reason}") from None

    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            return json.loads(text)
        if suffix in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError:
                raise SchedulerError(
                    "读取 YAML 需要 PyYAML，请先执行 "
                    "python -m pip install -r requirements.txt"
                ) from None
            return yaml.safe_load(text)
    except json.JSONDecodeError as exc:
        raise SchedulerError(
            f"JSON 语法错误（第 {exc.lineno} 行，第 {exc.colno} 列）: {exc.msg}"
        ) from None
    except SchedulerError:
        raise
    except Exception as exc:
        # PyYAML exceptions derive from yaml.YAMLError; importing yaml here keeps
        # JSON-only environments usable without adding a global dependency.
        raise SchedulerError(f"YAML 语法错误: {exc}") from None

    raise SchedulerError(
        f"不支持的配置文件类型 {path.suffix!r}，请使用 .yaml、.yml 或 .json"
    )


def load_config(path_value: str | Path) -> SchedulerConfig:
    path = Path(path_value).expanduser()
    document = _load_document(path)
    if not isinstance(document, dict):
        raise SchedulerError("配置文件顶层必须是对象，并包含 timeout 和 tasks 字段")

    timeout_value = document.get("timeout")
    timeout = (
        None
        if timeout_value is None
        else _number(timeout_value, "timeout", minimum=0)
    )

    raw_tasks = document.get("tasks")
    if not isinstance(raw_tasks, list):
        raise SchedulerError("tasks 必须是任务列表")
    if not raw_tasks:
        raise SchedulerError("tasks 不能为空")

    tasks: list[Task] = []
    seen_names: set[str] = set()
    for index, raw_task in enumerate(raw_tasks):
        label = f"tasks[{index}]"
        if not isinstance(raw_task, dict):
            raise SchedulerError(f"{label} 必须是对象")

        raw_name = raw_task.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise SchedulerError(f"{label}.name 必须是非空字符串")
        name = raw_name.strip()
        if name in seen_names:
            raise SchedulerError(f"任务名重复: {name}")
        seen_names.add(name)

        if "duration" not in raw_task:
            raise SchedulerError(f"任务 {name} 缺少 duration")
        duration = _number(
            raw_task["duration"], f"任务 {name} 的 duration", minimum=0
        )

        if "success_rate" not in raw_task:
            raise SchedulerError(f"任务 {name} 缺少 success_rate")
        success_rate = _number(
            raw_task["success_rate"],
            f"任务 {name} 的 success_rate",
            minimum=0,
            maximum=1,
        )

        raw_dependencies = raw_task.get("dependencies", [])
        if not isinstance(raw_dependencies, list):
            raise SchedulerError(f"任务 {name} 的 dependencies 必须是字符串列表")

        dependencies: list[str] = []
        dependency_seen: set[str] = set()
        for dependency_index, raw_dependency in enumerate(raw_dependencies):
            if not isinstance(raw_dependency, str) or not raw_dependency.strip():
                raise SchedulerError(
                    f"任务 {name} 的 dependencies[{dependency_index}] "
                    "必须是非空字符串"
                )
            dependency = raw_dependency.strip()
            if dependency not in dependency_seen:
                dependencies.append(dependency)
                dependency_seen.add(dependency)

        tasks.append(
            Task(
                name=name,
                duration=duration,
                success_rate=success_rate,
                dependencies=tuple(dependencies),
                index=index,
            )
        )

    for task in tasks:
        for dependency in task.dependencies:
            if dependency not in seen_names:
                raise SchedulerError(
                    f"任务 {task.name} 依赖了不存在的任务: {dependency}"
                )

    return SchedulerConfig(tasks=tuple(tasks), timeout=timeout)


def _find_cycle(tasks: Sequence[Task]) -> list[str]:
    by_name = {task.name: task for task in tasks}
    visited: set[str] = set()
    active: set[str] = set()
    stack: list[str] = []

    def visit(name: str) -> list[str] | None:
        if name in active:
            start = stack.index(name)
            return stack[start:] + [name]
        if name in visited:
            return None

        active.add(name)
        stack.append(name)
        for dependency in by_name[name].dependencies:
            cycle = visit(dependency)
            if cycle is not None:
                return cycle
        stack.pop()
        active.remove(name)
        visited.add(name)
        return None

    for task in tasks:
        cycle = visit(task.name)
        if cycle is not None:
            return cycle
    return []


def topological_order(tasks: Sequence[Task]) -> list[Task]:
    by_name = {task.name: task for task in tasks}
    indegree = {task.name: len(task.dependencies) for task in tasks}
    dependents: dict[str, list[str]] = {task.name: [] for task in tasks}
    for task in tasks:
        for dependency in task.dependencies:
            dependents[dependency].append(task.name)

    ready = [(task.index, task.name) for task in tasks if indegree[task.name] == 0]
    heapq.heapify(ready)
    ordered: list[Task] = []

    while ready:
        _, name = heapq.heappop(ready)
        ordered.append(by_name[name])
        for dependent in dependents[name]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, (by_name[dependent].index, dependent))

    if len(ordered) != len(tasks):
        cycle = _find_cycle(tasks)
        cycle_text = " -> ".join(cycle) if cycle else "未知环"
        raise SchedulerError(f"检测到依赖环: {cycle_text}")
    return ordered


class TaskScheduler:
    def __init__(
        self,
        config: SchedulerConfig,
        order: Sequence[Task],
        rng: random.Random,
        logger: ConsoleLogger,
    ) -> None:
        self.config = config
        self.order = list(order)
        self.rng = rng
        self.logger = logger
        self.run_started_monotonic = time.monotonic()
        self.deadline = (
            None
            if config.timeout is None
            else self.run_started_monotonic + config.timeout
        )

    def _is_expired(self) -> bool:
        return self.deadline is not None and time.monotonic() >= self.deadline

    def _wait_for_attempt(self, duration: float) -> bool:
        """Sleep for one attempt, stopping at the scheduler deadline."""
        if self.deadline is None:
            time.sleep(duration)
            return False

        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(duration, remaining))
        return time.monotonic() >= self.deadline

    def _mark_current_timeout(
        self,
        result: TaskResult,
        task_started_monotonic: float | None,
    ) -> None:
        result.status = "TIMEOUT"
        result.ended_at = time.time()
        result.duration = (
            max(0.0, time.monotonic() - task_started_monotonic)
            if task_started_monotonic is not None
            else 0.0
        )
        self.logger.emit("TIMEOUT", f"{result.name} 已达到全局超时")

    def _execute_task(self, task: Task, result: TaskResult) -> None:
        task_started_monotonic: float | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self._is_expired():
                self._mark_current_timeout(result, task_started_monotonic)
                return

            if task_started_monotonic is None:
                task_started_monotonic = time.monotonic()
                result.started_at = time.time()

            result.attempts = attempt
            timed_out = self._wait_for_attempt(task.duration)
            if timed_out:
                self._mark_current_timeout(result, task_started_monotonic)
                return

            if self.rng.random() < task.success_rate:
                result.status = "SUCCESS"
                result.ended_at = time.time()
                result.duration = time.monotonic() - task_started_monotonic
                self.logger.emit(
                    "SUCCESS", f"{task.name}（第 {attempt} 次尝试成功）"
                )
                return

            if attempt < MAX_ATTEMPTS:
                self.logger.emit(
                    "RETRY",
                    f"{task.name} 第 {attempt} 次尝试失败，准备第 {attempt + 1} 次",
                )

        result.status = "FAILED"
        result.ended_at = time.time()
        result.duration = time.monotonic() - task_started_monotonic
        self.logger.emit(
            "FAILED", f"{task.name} 连续 {MAX_ATTEMPTS} 次尝试均失败"
        )

    def run(self) -> tuple[bool, float, list[TaskResult]]:
        results: dict[str, TaskResult] = {}
        timed_out = False

        for index, task in enumerate(self.order):
            if self._is_expired():
                for pending in self.order[index:]:
                    results.setdefault(
                        pending.name, TaskResult(name=pending.name, status="TIMEOUT")
                    )
                for pending in self.order[index:]:
                    self.logger.emit(
                        "TIMEOUT", f"{pending.name} 未执行，已终止"
                    )
                timed_out = True
                break

            result = TaskResult(name=task.name, status="PENDING")
            results[task.name] = result
            blocked_by = [
                dependency
                for dependency in task.dependencies
                if results[dependency].status != "SUCCESS"
            ]
            if blocked_by:
                result.status = "SKIPPED"
                self.logger.emit(
                    "SKIPPED",
                    f"{task.name}（前置任务未成功: {', '.join(blocked_by)}）",
                )
                continue

            self.logger.info(f"START   {task.name}")
            self._execute_task(task, result)
            if result.status == "TIMEOUT":
                for pending in self.order[index + 1 :]:
                    pending_result = results.setdefault(
                        pending.name, TaskResult(name=pending.name, status="TIMEOUT")
                    )
                    if pending_result.status not in REPORT_STATUSES:
                        pending_result.status = "TIMEOUT"
                    self.logger.emit(
                        "TIMEOUT", f"{pending.name} 未完成，已终止"
                    )
                timed_out = True
                break

        total_duration = time.monotonic() - self.run_started_monotonic
        ordered_results = [
            results.get(task.name, TaskResult(task.name, "TIMEOUT"))
            for task in self.config.tasks
        ]
        return timed_out, total_duration, ordered_results


def write_report(
    path_value: str | Path,
    timed_out: bool,
    total_duration: float,
    results: Iterable[TaskResult],
) -> Path:
    path = Path(path_value).expanduser()
    report = {
        "timeout": timed_out,
        "total_duration": round(total_duration, 6),
        "tasks": [result.to_dict() for result in results],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as report_file:
            json.dump(report, report_file, ensure_ascii=False, indent=2)
            report_file.write("\n")
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise SchedulerError(f"无法写入报告文件 {path}: {reason}") from None
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按依赖关系执行任务并生成 JSON 调度报告"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="任务配置文件路径（.yaml、.yml 或 .json）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        help="全局超时秒数，覆盖配置文件中的 timeout",
    )
    parser.add_argument(
        "--report",
        default="report.json",
        help="报告输出路径（默认: report.json）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="随机种子，用于复现相同执行结果",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="即使输出到终端也禁用 ANSI 颜色",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        if args.timeout is not None:
            timeout = _number(args.timeout, "--timeout", minimum=0)
            config = replace(config, timeout=timeout)

        order = topological_order(config.tasks)
        run_started = time.monotonic()
        logger = ConsoleLogger(
            sys.stdout,
            run_started,
            color=False if args.no_color else None,
        )
        logger.info(
            f"载入 {len(config.tasks)} 个任务；"
            f"timeout={config.timeout if config.timeout is not None else '无'}"
        )

        scheduler = TaskScheduler(
            config=config,
            order=order,
            rng=random.Random(args.seed),
            logger=logger,
        )
        timed_out, total_duration, results = scheduler.run()
        report_path = write_report(
            args.report, timed_out, total_duration, results
        )
    except SchedulerError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n错误: 执行已由用户中断", file=sys.stderr)
        return 130

    state = "TIMEOUT" if timed_out else "COMPLETE"
    logger.info(f"{state}，总耗时 {total_duration:.3f}s")
    logger.info(f"REPORT  {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
