import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import scheduler


class SchedulerTests(unittest.TestCase):
    def _write_json(self, directory: Path, data: object) -> Path:
        path = directory / "tasks.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def _main(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = scheduler.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_success_uses_dependency_order_and_writes_report(self) -> None:
        config_data = {
            "timeout": 1,
            "tasks": [
                {
                    "name": "Init",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": [],
                },
                {
                    "name": "Left",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["Init"],
                },
                {
                    "name": "Right",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["Init"],
                },
                {
                    "name": "Merge",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["Left", "Right"],
                },
                {
                    "name": "Done",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["Merge"],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            config_path = self._write_json(directory, config_data)
            report_path = directory / "report.json"
            code, stdout, stderr = self._main(
                "--config",
                str(config_path),
                "--report",
                str(report_path),
                "--seed",
                "42",
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 0, stderr)
        self.assertFalse(report["timeout"])
        self.assertTrue(all(item["status"] == "SUCCESS" for item in report["tasks"]))
        positions = [
            stdout.index("START   Init"),
            stdout.index("START   Left"),
            stdout.index("START   Right"),
            stdout.index("START   Merge"),
            stdout.index("START   Done"),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_failed_branch_is_skipped_but_independent_branch_runs(self) -> None:
        config_data = {
            "tasks": [
                {
                    "name": "Init",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": [],
                },
                {
                    "name": "Good",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["Init"],
                },
                {
                    "name": "Bad",
                    "duration": 0,
                    "success_rate": 0,
                    "dependencies": ["Init"],
                },
                {
                    "name": "Tail",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["Bad"],
                },
                {
                    "name": "Merge",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["Good", "Tail"],
                },
            ]
        }
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            config_path = self._write_json(directory, config_data)
            report_path = directory / "report.json"
            code, stdout, stderr = self._main(
                "--config", str(config_path), "--report", str(report_path)
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            statuses = {item["name"]: item for item in report["tasks"]}

        self.assertEqual(code, 0, stderr)
        self.assertEqual(statuses["Good"]["status"], "SUCCESS")
        self.assertEqual(statuses["Bad"]["status"], "FAILED")
        self.assertEqual(statuses["Bad"]["attempts"], 3)
        self.assertEqual(statuses["Tail"]["status"], "SKIPPED")
        self.assertEqual(statuses["Merge"]["status"], "SKIPPED")
        self.assertEqual(stdout.count("RETRY"), 2)

    def test_timeout_interrupts_and_marks_every_unfinished_task(self) -> None:
        config_data = {
            "timeout": 10,
            "tasks": [
                {
                    "name": "Slow",
                    "duration": 0.05,
                    "success_rate": 1,
                    "dependencies": [],
                },
                {
                    "name": "After",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["Slow"],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            config_path = self._write_json(directory, config_data)
            report_path = directory / "report.json"
            code, _, stderr = self._main(
                "--config",
                str(config_path),
                "--timeout",
                "0.01",
                "--report",
                str(report_path),
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 0, stderr)
        self.assertTrue(report["timeout"])
        self.assertLess(report["total_duration"], 0.05)
        self.assertEqual(
            [item["status"] for item in report["tasks"]], ["TIMEOUT", "TIMEOUT"]
        )

    def test_cycle_returns_readable_error_without_traceback(self) -> None:
        config_data = {
            "tasks": [
                {
                    "name": "A",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["B"],
                },
                {
                    "name": "B",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["A"],
                },
            ]
        }
        with tempfile.TemporaryDirectory() as directory_text:
            config_path = self._write_json(Path(directory_text), config_data)
            code, _, stderr = self._main("--config", str(config_path))

        self.assertEqual(code, 1)
        self.assertIn("依赖环", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_validation_rejects_missing_dependency_and_rate_out_of_range(self) -> None:
        bad_dependency = {
            "tasks": [
                {
                    "name": "A",
                    "duration": 0,
                    "success_rate": 1,
                    "dependencies": ["Missing"],
                }
            ]
        }
        bad_rate = {
            "tasks": [
                {
                    "name": "A",
                    "duration": 0,
                    "success_rate": 1.1,
                    "dependencies": [],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            for data in (bad_dependency, bad_rate):
                path = self._write_json(directory, data)
                code, _, stderr = self._main("--config", str(path))
                self.assertEqual(code, 1)
                self.assertNotIn("Traceback", stderr)


if __name__ == "__main__":
    unittest.main()
