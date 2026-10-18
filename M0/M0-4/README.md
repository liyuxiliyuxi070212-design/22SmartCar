# M0-4 TaskScheduler

终端任务调度模拟器。程序读取 YAML 或 JSON 任务图，按依赖关系执行任务，
模拟失败重试和全局超时，并生成结构化 JSON 报告。

## 环境与安装

要求 Python 3.10 或更高版本。建议在题目 M0-1 已配置的 Ubuntu 22.04
环境中为本题创建独立虚拟环境，不使用系统 Python 直接安装依赖：

```bash
cd "/media/yuki/外置硬盘/22SmartCar/M0/M0-4"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

确认运行环境：

```bash
which python
python --version
python -c "import yaml; print(yaml.__version__)"
```

`requirements.txt` 只包含读取 YAML 所需的 `PyYAML`。JSON 配置只使用
Python 标准库。

## 参数说明

```bash
python scheduler.py --config <path> [--timeout <float>]
                    [--report <path>] [--seed <int>] [--no-color]
```

| 参数 | 必填 | 默认值 | 说明 |
| :-- | :--: | :-- | :-- |
| `--config` | 是 | 无 | `.yaml`、`.yml` 或 `.json` 任务配置文件 |
| `--timeout` | 否 | 配置文件值 | 全局超时秒数；不填且配置也省略时表示不设超时 |
| `--report` | 否 | `report.json` | 报告输出路径，父目录不存在时会自动创建 |
| `--seed` | 否 | 系统随机 | 随机种子；相同配置、种子和耗时情况下结果可复现 |
| `--no-color` | 否 | 关闭 | 强制禁用 ANSI 颜色 |

控制台状态颜色为：`SUCCESS` 绿色、`FAILED` 红色、`RETRY` 黄色、
`SKIPPED` 蓝色。输出重定向到文件或管道时，程序会自动禁用颜色转义符。
每次输出都会立即刷新，因此可以在执行过程中观察每个任务的状态。

## 配置文件

```yaml
timeout: 15
tasks:
  - name: Init
    duration: 0.5
    success_rate: 1.0
    dependencies: []
  - name: Move
    duration: 2.0
    success_rate: 0.8
    dependencies: ["Init"]
```

| 字段 | 必填 | 规则 |
| :-- | :--: | :-- |
| `timeout` | 否 | 非负有限数值，单位为秒 |
| `tasks` | 是 | 非空任务列表 |
| `name` | 是 | 非空且全局唯一的字符串 |
| `duration` | 是 | 非负有限数值，每次尝试都会模拟该耗时 |
| `success_rate` | 是 | `0.0` 到 `1.0` 的有限数值 |
| `dependencies` | 否 | 前置任务名称列表，省略时为空 |

支持分叉和汇合。调度顺序采用稳定的拓扑排序：没有依赖的任务先运行；
同时可运行时，优先保持配置文件中的顺序。

## 执行规则

每次尝试都会先执行 `sleep(duration)`，再根据 `success_rate` 判定结果。
一个任务失败时最多重试 2 次，即最多执行 3 次；三次均失败后状态为
`FAILED`，其下游任务状态为 `SKIPPED`，但不相关的独立分支仍继续执行。

执行前和每次尝试后都会检查全局超时。到达超时时，正在执行的任务以及
尚未完成的任务都记为 `TIMEOUT`，程序不再启动新任务。报告中的
`duration` 是任务所有尝试的累计耗时，`total_duration` 是整个调度阶段
从开始到结束的真实单调时钟耗时。

## 三个运行示例

### 1. 按配置文件中的 15 秒超时运行

```bash
python scheduler.py --config tasks_demo.yaml \
  --timeout 15 --report report.json --seed 42
```

### 2. 使用 JSON 配置并自定义报告路径

```bash
python scheduler.py --config tasks_demo.json \
  --timeout 15 --report output/report_seed_7.json --seed 7
```

### 3. 用 3 秒超时观察强制终止

```bash
python scheduler.py --config tasks_demo.yaml \
  --timeout 3 --report report_timeout.json --seed 42
```

运行后查看报告：

```bash
python -m json.tool report.json
```

## 报告格式

```json
{
  "timeout": false,
  "total_duration": 11.01,
  "tasks": [
    {
      "name": "Init",
      "status": "SUCCESS",
      "attempts": 1,
      "duration": 0.5,
      "started_at": 1699999999.12,
      "ended_at": 1699999999.62
    }
  ]
}
```

`tasks` 按配置文件顺序列出全部任务。最终状态只会是 `SUCCESS`、
`FAILED`、`SKIPPED` 或 `TIMEOUT`。因前置任务失败或超时而从未开始的
任务，其 `started_at`、`ended_at` 为 `null`，`attempts` 和 `duration`
为 `0`。

## 异常处理与退出码

依赖成环、依赖不存在、空任务列表、字段缺失、数值越界、YAML/JSON
语法错误、文件不存在或报告不可写时，程序向标准错误输出可读提示并返回
退出码 `1`，不会打印 Python Traceback。正常的完整运行和正常触发超时
都会返回 `0`，因为超时是本程序的预期调度结果；调度结果以报告中的
`"timeout"` 字段为准。用户按 `Ctrl+C` 中断时返回 `130`。

## 自动测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖成功依赖顺序、失败重试与下游跳过、独立分支继续执行、硬超时、
JSON 配置、依赖环和报告结构。
