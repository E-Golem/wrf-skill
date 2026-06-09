# WRF Tmax 评分代码合理性与参数化方案可行性评估

生成时间：2026-06-08

## 1. 评估对象

- 评分对象：`data/wrfout/lw4-sw4`
- 评价变量：WRF 气象诊断变量 `T2MAX`
- 观测数据：中国地面气象站日最高温
- 有效评价时段：2003-05-02 至 2003-10-01
- 有效样本：34119 个站点-日期配对样本，223 个站点

## 2. 代码合理性结论

当前评分代码在“WRF 诊断日最高温与地面站日最高温配对验证”这个目标下是合理的，可以作为参数化方案快速筛选和论文方法部分的基础流程。

主要依据如下：

1. 指标计算公式合理。代码计算 Bias、MAE、RMSE、PCC、RSD、MAPE、NSE，并在计算前剔除非有限值，避免 NaN 或无效站点污染结果。
2. WRF 诊断文件读取方式合理。程序直接读取 `T2MAX`，识别 K 单位并转换为摄氏度；对 0 K 这类明显无效场进行过滤。
3. 多文件合并逻辑合理。程序支持目录输入，按日期排序合并，检查重复日期和网格坐标一致性。
4. 观测匹配逻辑合理。程序先按日期筛选观测，再按长江流域边界筛站点，并进行站点-网格配对。
5. 输出结构合理。总体评分、逐日评分、逐站评分和匹配明细均已输出，便于复核和后续制图。

## 3. 需要在论文或报告中说明的限制

1. 站点取样目前采用最近邻格点，而不是双线性插值或投影距离最近邻。对 10 km 左右分辨率的初步筛选可以接受，但如果用于正式参数化方案优选，建议增加双线性插值版本作为敏感性检验。
2. 当前没有进行海拔订正。高海拔站点误差明显偏大，2000-3000 m 站点 Bias 为 -4.56 degC，RMSE 为 6.09 degC，说明地形高度差可能放大冷偏。
3. 综合分数是项目内自定义评分，不是通用文献标准。它适合在同一数据、同一时段、同一评价体系下比较不同方案，但不应单独作为“模型优劣”的唯一依据。
4. MAPE 对摄氏温度不是最稳健指标，暖季 Tmax 中问题不大，但若扩展到冬季或全年，不建议把 MAPE 作为核心判断指标。
5. 当前只评估 `T2MAX`。一个参数化方案是否“可行”，还需要至少补充 T2MEAN/T2MIN、降水、风速、相对湿度或短波辐射中的若干变量。

## 4. 当前评分结果解释

总体指标如下：

| 指标 | 数值 |
|---|---:|
| 样本数 n | 34119 |
| Score | 77.47 |
| PCC | 0.8305 |
| RMSE | 4.0548 degC |
| MAE | 3.2546 degC |
| Bias | -1.6330 degC |
| RSD | 1.0548 |
| NSE | 0.5696 |

这个结果说明：WRF 对暖季日最高温的时空变化有较好的捕捉能力，PCC 大于 0.8，RSD 接近 1，说明变化幅度没有明显失真；但绝对误差仍然偏大，RMSE 约 4.05 degC，且存在系统性冷偏。

月尺度看，5-9 月 Bias 均为负，约 -1.17 至 -1.99 degC，说明冷偏不是个别日期造成的随机现象。站点尺度看，有 41 个站点 Bias 小于 -3 degC，14 个站点综合分低于 60，高海拔站点误差尤其突出。

因此，`lw4-sw4` 可以作为“可用的候选参数化方案”或“基线方案”，但不宜直接表述为“最优方案”。

## 5. 与文献结果的对比

Zotero 本地库中检索到的相关 WRF 参数化和验证研究包括 Mooney et al. (2013)、Varga and Breuer (2020)、Kumar et al. (2014)、Ran et al. (2016)、Lee et al. (2020)、Shiferaw et al. (2024) 等。进一步核对公开页面后，可得到以下对比认识。

| 文献或区域 | 变量与指标特征 | 对当前结果的启示 |
|---|---|---|
| Liu 2024，黄土高原 WRF 物理方案敏感性 | 10 km WRF，对 2 m 气温和降水进行日、月尺度评价；论文强调不同判据下“最佳方案”不同。 | 不能只用一个综合分确定最优方案，应进行多方案、多指标排序。 |
| Chen et al. 2024，长三角 PBL 方案敏感性 | 四套 PBL 方案对典型气象变量影响明显，MYNN 在夏季温度 MB 约 0.41 degC；文献强调不同变量和情景下方案优劣不同。 | 当前 `lw4-sw4` 的 Tmax Bias 为 -1.63 degC，温度偏差大于该长三角 PBL 研究中的夏季最优 MB，说明还有优化空间。 |
| Lee et al. 2020，WRF 粗糙子层参数化 | RSL 参数化使气温 RMSE 从 2.74 K 改善到 2.67 K。 | 当前 Tmax RMSE 为 4.05 degC，高于该研究中的近地面气温 RMSE，说明若追求高精度应用，还需做插值、海拔订正或物理方案对比。 |
| Varga and Breuer 2020，喀尔巴阡盆地 WRF 配置敏感性 | 多套 WRF 配置下温度低估可达 4-7 degC，方案组合能减弱冷偏。 | 当前冷偏 -1.63 degC 不算极端，但高海拔站点冷偏较强，符合 WRF 在复杂地形和陆面过程上容易产生系统误差的经验。 |

## 6. 是否表明当前参数化方案可行

建议结论表述为：

当前 `lw4-sw4` 参数化方案对长江流域暖季日最高温具有初步可行性。它能够较好捕捉日最高温的时空变化，方差比例合理，综合评分达到 77.47，可作为后续植被恢复情景试验的候选基线方案。但该方案存在稳定冷偏和高海拔站点误差偏大的问题，当前评分不足以证明它是最优参数化方案。

如果论文中需要把它作为正式试验方案，建议增加以下内容：

1. 至少增加 2-3 套备选参数化方案，用同一套评分体系比较。
2. 增加双线性插值或投影距离最近邻，与当前最近邻结果对比。
3. 增加海拔订正敏感性测试，尤其关注 2000 m 以上站点。
4. 增加 T2MIN、T2MEAN、降水或风速验证，避免只用 Tmax 评价整个参数化方案。
5. 在论文中把综合分定义为“工程化筛选指标”，最终判断仍以 PCC、RMSE、MAE、Bias、RSD 等单项指标共同支撑。

## 7. 参考文献来源

- Liu, S. 2024. Sensitivity of WRF-Simulated 2 m Temperature and Precipitation to Physics Options over the Loess Plateau. DOI: https://doi.org/10.1155/2024/6633255
- Chen, D. et al. 2024. Sensitivity analysis of planetary boundary layer parameterization on meteorological simulations in the Yangtze River Delta region, China. DOI: https://doi.org/10.1039/d4ea00038b
- Lee, J. et al. 2020. Implementation of a roughness sublayer parameterization in WRF and its evaluation for regional climate simulations. DOI: https://doi.org/10.5194/gmd-13-521-2020
- Varga, A. J. and Breuer, H. 2020. Sensitivity of simulated temperature, precipitation, and global radiation to different WRF configurations over the Carpathian Basin. DOI: https://doi.org/10.1007/s00382-020-05416-x
- Mooney, P. A. et al. 2013. Evaluation of the sensitivity of WRF to parameterization schemes for regional climates of Europe. DOI: https://doi.org/10.1175/JCLI-D-11-00676.1
