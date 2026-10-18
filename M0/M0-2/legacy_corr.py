import argparse
import csv
import math
import os

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

    denom = dx * dy
    r = prod / math.sqrt(denom)
    return r, mean_x, mean_y


def main():
    parser = argparse.ArgumentParser(description="计算两列数据的皮尔逊相关系数")
    parser.add_argument("--config", default=CONFIG_PATH, help="配置文件路径")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

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

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            xs.append(float(row[col_x]))
            ys.append(float(row[col_y]))

    n = len(xs)
    r, mean_x, mean_y = pearson_r(xs, ys)

    print("n =", n)
    print("mean_x =", mean_x)
    print("mean_y =", mean_y)
    print("r =", r)


if __name__ == "__main__":
    main()
