# M0-2 相关系数计算工具

读取 YAML 配置指定的 CSV 两列数据，手写计算皮尔逊相关系数，并打印结果。

## 运行方式

在 `M0-2` 目录下运行：

```bash
cd "/media/yuki/外置硬盘/22SmartCar/M0/M0-2"
python3 legacy_corr.py --config config.yaml
```

也可以从其他目录用绝对路径运行：

```bash
python3 "/media/yuki/外置硬盘/22SmartCar/M0/M0-2/legacy_corr.py" \
  --config "/media/yuki/外置硬盘/22SmartCar/M0/M0-2/config.yaml"
```

`--config` 不填时默认使用当前目录下的 `config.yaml`。

## 输入格式

YAML 配置示例：

```yaml
input_csv: "sample_data.csv"

columns:
  x: "sensor_a"
  y: "sensor_b"

task:
  verbose: true
```

字段说明：

| 字段 | 是否必填 | 说明 |
| :-- | :-- | :-- |
| `input_csv` | 是 | CSV 文件路径 |
| `columns.x` | 是 | 作为 x 的列名 |
| `columns.y` | 是 | 作为 y 的列名 |
| `task.verbose` | 否 | 为 `false` 时只打印 `r`，默认打印全部中间量 |

CSV 要求：

- 第一行必须是表头，列名要和配置中的 `columns.x` / `columns.y` 完全一致
- 指定的两列必须能转换为数字
- 至少要有 2 行有效数据
- 推荐 UTF-8 编码

`input_csv` 是相对路径时，先相对配置文件所在目录查找，找不到再按当前工作目录查找。

## 输出含义

```text
n = 40
mean_x = 49.43782499999999
mean_y = 43.310725
r = 0.5634747254524842
```

- `n`：参与计算的有效样本对数
- `mean_x` / `mean_y`：两列数据各自的平均值
- `r`：皮尔逊相关系数，范围为 `[-1, 1]`
  - 接近 `1`：强正相关
  - 接近 `-1`：强负相关
  - 接近 `0`：线性相关性弱

示例数据中的 `sensor_b` 在 10:19 有一个 `-12.5` 的离群值，属于原始数据特征，程序不会自动清理。

## 错误处理

出错时错误信息输出到 stderr，退出码非 0，不会打印 Python Traceback：

| 情况 | 提示示例 |
| :-- | :-- |
| 配置文件不存在 | `错误：找不到文件：config.yaml` |
| CSV 不存在 | `错误：找不到文件：sample_data.csv` |
| 空文件或数据不足 | `错误：有效数据少于 2 行，无法计算相关系数` |
| 缺列/缺配置字段 | `错误：缺少配置字段或 CSV 列：'sensor_a'` |
| 非数字内容 | `错误：could not convert string to float: 'x'` |
| 某列取值恒定 | `错误：某一列取值恒定，相关系数无定义` |

## 运行测试

```bash
cd "/media/yuki/外置硬盘/22SmartCar/M0/M0-2"
python3 -m unittest discover -s tests -v
```

测试包含：

- `[1,2,3]` 与 `[2,4,6]`，相关系数为 `1`
- `[1,2,3]` 与 `[6,4,2]`，相关系数为 `-1`
- 零方差输入报错
- 与 `numpy.corrcoef` 对拍
- 从其他目录用 `--config` 运行
- 配置文件不存在时非 0 退出且无 Traceback

## 修复记录

原脚本的问题和对应修复：

| 问题 | 修复 |
| :-- | :-- |
| 相关系数分母写成 `dx * dy` | 改为 `math.sqrt(dx * dy)` |
| 全部代码写在全局作用域 | 核心计算封装为 `pearson_r()`，入口改为 `main()` |
| 配置路径写死为 `config.yaml` | 增加 `--config`，并解析 `input_csv` 相对路径 |
| 文件、空数据、缺列、零方差直接崩溃 | `main()` 中统一捕获并输出可读错误，非 0 退出 |
| 没有测试和说明 | 增加 `tests/test_corr.py` 和本 README |

修复后示例数据结果为 `r = 0.5634747254524842`，与 `numpy.corrcoef` 一致。

## AI 使用说明

本题使用 AI 辅助完成函数封装、异常处理、单元测试和 README 初稿。提交者已逐行检查代码，并在本地运行示例、异常用例和单元测试进行验证；核心相关系数计算仍为手写循环，未调用 `numpy.corrcoef` 代替。
