# v1.0 示例运行说明

本文档演示如何使用 v1.0 工具对一组 WRF 长波/短波辐射参数化方案进行日最高温站点验证。

## 1. 数据组织

推荐目录结构：

```text
data/
  wrfout/
    lw1-sw1/
      T2_output.nc
    lw3-sw3/
      T2_output.nc
    lw4-sw2/
      T2_output.nc
    lw4-sw4/
      T2_output1.nc
      T2_output2.nc
    lw5-sw5/
      T2_output.nc
  observed/
    SURF_CLI_CHN_MUL_DAY-TEM-*.TXT
  boundary/
    Yangtze.shp
```

方案文件夹命名规则：

```text
lw<长波辐射方案编号>-sw<短波辐射方案编号>
```

例如：

```text
lw4-sw2
```

表示长波辐射方案编号为 `4`，短波辐射方案编号为 `2`。

## 2. 配置文件

默认配置文件：

```text
configs/tmax_validation.yaml
```

关键设置：

```yaml
project:
  name: wrf_tmax_station_validation

wrf:
  input_root: data/wrfout
  schemes: auto
  input_kind: hourly_t2
  variable: T2
  file_patterns:
    - "T2_output*.nc"
    - "T2_out*.nc"

observed:
  data_dir: data/observed
  boundary: data/boundary/Yangtze.shp

time:
  time_offset_hours: 8
  local_day_boundary_hour: 20

validation:
  start: "06-01"
  end: "10-01"
```

说明：

- `time_offset_hours: 8` 表示将 WRF UTC 时间转换为北京时间。
- `local_day_boundary_hour: 20` 表示使用北京时 20 时日界。
- `validation.start/end` 用于排除预热期，例如不使用 5 月数据。

## 3. 检查方案识别

```powershell
cd D:\文档\wrf_learning
$env:PYTHONPATH='src'
conda run -n geocompy python -m wrf_eval.cli inspect --config configs/tmax_validation.yaml
```

期望输出类似：

```text
run_id=wrf_tmax_station_validation
scheme=lw1-sw1    path=data\wrfout\lw1-sw1    file_pattern=T2_output*.nc
scheme=lw3-sw3    path=data\wrfout\lw3-sw3    file_pattern=T2_output*.nc
scheme=lw4-sw2    path=data\wrfout\lw4-sw2    file_pattern=T2_output*.nc
```

如果某个方案没有出现，通常表示该文件夹中没有匹配 `T2_output*.nc` 或 `T2_out*.nc` 的文件。

## 4. 批量评分

```powershell
conda run -n geocompy python -m wrf_eval.cli run --config configs/tmax_validation.yaml
```

运行过程中会显示进度，例如：

```text
[1/3] Discovered 5 scheme(s) for run 'wrf_tmax_station_validation'.
[2/3] (1/5) Evaluating scheme 'lw1-sw1'...
[2/3] (1/5) Completed 'lw1-sw1' in 70.2s; matched_rows=27206, score=75.2864.
[3/3] Building comparison report for 5 successful scheme(s)...
[3/3] Best scheme: lw4-sw2; score=76.9725.
```

## 5. 输出文件

单方案结果：

```text
outputs/runs/wrf_tmax_station_validation/lw4-sw2/tables/overall_score.csv
outputs/runs/wrf_tmax_station_validation/lw4-sw2/tables/daily_scores.csv
outputs/runs/wrf_tmax_station_validation/lw4-sw2/tables/station_scores.csv
reports/runs/wrf_tmax_station_validation/lw4-sw2/wrf_tmax_evaluation_report.md
```

多方案对比：

```text
outputs/runs/wrf_tmax_station_validation/scheme-comparison/scheme_comparison.csv
reports/runs/wrf_tmax_station_validation/scheme-comparison/scheme_comparison_report.md
```

## 6. v1.0 适用范围

v1.0 只适用于：

- WRF 日最高温验证。
- 基于逐小时 `T2` 聚合得到日最高温，或读取诊断日最高温。
- 中国气象站日值温度观测数据。
- 长波辐射和短波辐射参数化方案组合比较。

v1.0 不包含：

- 热浪事件命中率、空报率、持续时间等事件指标。
- 降水、风速、相对湿度等变量验证。
- 格点化观测或再分析资料验证。
- Web 可视化界面。
