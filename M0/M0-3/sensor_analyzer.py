#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor_analyzer.py  —— 上一届学长留下的"能用"的脚本

注释（学长原话）：
    "处理一下传感器数据就能用"

原本意图：
    1. 读取 sensor_data.csv（列：time, value）
    2. 计算 value 的平均值、标准差
    3. 剔除离群值（|value - mean| > 2 * std）
    4. 把清洗后的数据保存为 cleaned_data.csv
    5. 打印一份统计摘要

已完成排查与修复，并补充命令行参数和异常输入处理。
"""

import argparse
import csv
import math
import sys

INPUT_FILE = "sensor_data.csv"
OUTPUT_FILE = "cleaned_data.csv"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="分析传感器数据并剔除 2σ 离群值")
    parser.add_argument("--input", default=INPUT_FILE, help="输入 CSV 路径")
    parser.add_argument("--output", default=OUTPUT_FILE, help="输出 CSV 路径")
    return parser.parse_args(argv)


def read_rows(path):
    rows = []
    try:
        with open(path, "r", newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                raise ValueError("输入文件为空")

            missing = {"time", "value"} - set(reader.fieldnames)
            if missing:
                names = "、".join(sorted(missing))
                raise ValueError("输入文件缺少列: %s" % names)

            for line_number, row in enumerate(reader, start=2):
                try:
                    time_text = row["time"].strip()
                    value_text = row["value"].strip()
                    time_value = float(time_text)
                    value_value = float(value_text)
                except (AttributeError, KeyError, TypeError, ValueError):
                    raise ValueError(
                        "第 %d 行的 time/value 不是有效数值" % line_number
                    ) from None

                if not (math.isfinite(time_value) and math.isfinite(value_value)):
                    raise ValueError(
                        "第 %d 行的 time/value 必须是有限数值" % line_number
                    )
                rows.append((time_text, value_text, time_value, value_value))
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise OSError("无法读取输入文件 %s: %s" % (path, reason)) from None
    except csv.Error as exc:
        raise ValueError("CSV 格式错误: %s" % exc) from None

    if not rows:
        raise ValueError("输入文件没有数据行")
    return rows


def analyze(rows):
    values = [row[3] for row in rows]
    mean = math.fsum(values) / len(values)
    std = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / len(values))
    cleaned = [
        (time_text, value_text)
        for time_text, value_text, _, value in rows
        if abs(value - mean) <= 2 * std
    ]
    return mean, std, cleaned


def write_cleaned(path, cleaned):
    try:
        with open(path, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["time", "value"])
            writer.writerows(cleaned)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise OSError("无法写入输出文件 %s: %s" % (path, reason)) from None


def main(argv=None):
    args = parse_args(argv)
    print("=== 传感器数据分析 ===")

    try:
        rows = read_rows(args.input)
        mean, std, cleaned = analyze(rows)
        write_cleaned(args.output, cleaned)
    except (OSError, ValueError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1

    print("共读取 %d 条数据" % len(rows))
    print("均值 mean = %.6f" % mean)
    print("标准差 std = %.6f" % std)
    print("清洗后剩余 %d 条" % len(cleaned))
    print("已保存到 %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
