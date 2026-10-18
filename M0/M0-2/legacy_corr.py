import argparse
import csv
import math
import os
import sys

import yaml

CONFIG_PATH = "config.yaml"


def pearson_r(xs, ys):
    n = len(xs)

    sum_x = 0.0
    sum_y = 0.0
    for i in range(n):
        sum_x = sum_x + xs[i]
        sum_y = sum_y + ys[i]

    mean_x = sum_x / n
    mean_y = sum_y / n

    dx = 0.0
    dy = 0.0
    prod = 0.0
    for i in range(n):
        a = xs[i] - mean_x
        b = ys[i] - mean_y
        dx = dx + a * a
        dy = dy + b * b
        prod = prod + a * b

    if dx == 0.0 or dy == 0.0:
        raise ValueError("某一列取值恒定，相关系数无定义")

    r = prod / math.sqrt(dx * dy)
    return r, mean_x, mean_y


def main():
    parser = argparse.ArgumentParser(description="计算两列数据的皮尔逊相关系数")
    parser.add_argument("--config", default=CONFIG_PATH, help="配置文件路径")
    args = parser.parse_args()

    try:
        with open(args.config, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        if not isinstance(cfg, dict):
            raise ValueError("配置文件内容为空或格式不正确")

        csv_path = cfg["input_csv"]
        base_dir = os.path.dirname(os.path.abspath(args.config))
        if not os.path.isabs(csv_path):
            candidate = os.path.join(base_dir, csv_path)
            if os.path.exists(candidate):
                csv_path = candidate

        col_x = cfg["columns"]["x"]
        col_y = cfg["columns"]["y"]

        xs = []
        ys = []
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                xs.append(float(row[col_x]))
                ys.append(float(row[col_y]))

        n = len(xs)
        if n < 2:
            raise ValueError("有效数据少于 2 行，无法计算相关系数")

        r, mean_x, mean_y = pearson_r(xs, ys)

        task_cfg = cfg.get("task") or {}
        if task_cfg.get("verbose", True):
            print("n =", n)
            print("mean_x =", mean_x)
            print("mean_y =", mean_y)
        print("r =", r)
        return 0
    except FileNotFoundError as exc:
        print(f"错误：找不到文件：{exc.filename}", file=sys.stderr)
    except KeyError as exc:
        print(f"错误：缺少配置字段或 CSV 列：{exc}", file=sys.stderr)
    except yaml.YAMLError as exc:
        print(f"错误：配置文件格式错误：{exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
