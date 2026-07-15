# 计算与预测算法

## 1. 符号

- `u(t)`：当前 reset epoch 中的已用百分比
- `r(t) = 100 - u(t)`：剩余百分比
- `T_reset`：重置时间
- `c_i(t)`：第 i 类 token 累计量
- `Δt`：观察间隔（小时）

## 2. 实时消耗速度

最直接的额度速度：

```text
burn_pph = max(0, u(t2) - u(t1)) / hours(t2 - t1)
```

为降低额度百分比量化带来的跳变，UI 默认展示指数平滑速度：

```text
ema_t = α * burn_t + (1 - α) * ema_(t-1)
```

建议对 5 分钟与 1 小时使用不同 α，并同时保留原始值用于审计。

## 3. 建议速度与风险

```text
allowed_pph = remaining_percent / hours_until_reset
pace_ratio  = observed_burn_pph / allowed_pph
```

- `pace_ratio < 0.8`：安全
- `0.8 ≤ pace_ratio ≤ 1.2`：接近预算
- `pace_ratio > 1.2`：有提前耗尽风险

阈值应该允许用户配置。样本少于 30 分钟时只显示“早期趋势”。

## 4. 耗尽时间 ETA

朴素估计：

```text
eta_hours = remaining_percent / observed_burn_pph
```

正式实现使用 bootstrap：从最近 N 个有效时间桶中有放回抽样，得到 burn rate 分布，再计算耗尽时间 P10/P50/P90。结果必须截断到合理范围，并明确处理 burn rate 为 0 的情况。

## 5. 最快使用时段

1. 把每个 reset epoch 内的快照重采样为固定桶。当前插件使用 15 分钟桶，正式版可根据事件密度缩短到 5 分钟。
2. 对每个桶计算 `Δused_percent` 与 token delta。
3. 合并过短、相邻且同方向的突增。
4. 按 `burn_pph` 排序。
5. 过滤有效覆盖率低于 70% 的桶。

当前插件只使用最近 28 天数据。单个最快时段至少包含 3 条额度快照；热力图使用本地时区按 `weekday × 3-hour bucket` 聚合中位数，并显示具体日期范围与有效窗口数。少于 3 个有效窗口的热力格标记为“数据不足”，且不作为稳定规律展示。

固定桶不能跨越 reset epoch。实时速度与历史规律分开计算：实时速度使用当前额度周期的最近 60/180/360 分钟快照，历史热力图只使用上述 15 分钟固定窗口。

## 6. Credits 估算

当费率表提供每百万 token 的 rates 时：

```text
credits = (
  input_tokens        * input_rate
  + cached_input_tokens * cached_input_rate
  + output_tokens       * output_rate
) / 1_000_000
```

若 speed mode 有独立倍率，再按带版本的 rate card 应用。`reasoning_output_tokens` 不能在已经包含于 output token 时重复计费；adapter 必须根据来源语义标注。

注意：额度窗口百分比和 credits 是两个独立量。没有可靠映射时，禁止将 `1%` 宣称为固定 credits。

## 7. 模型与推理强度情景模拟

### 个人历史优先

按以下维度构建 workload profile：

```text
task_class × model × reasoning_effort × speed_mode
```

每个 profile 保存 input/cached/output token 的 P25/P50/P75/P90。样本不足时逐级回退：

1. 同 task + model + effort
2. 同 task + model
3. 同 task
4. 全局先验

### 推理强度的处理

不使用固定倍率。系统从同一用户的相似任务中学习条件比率：

```text
effort_factor = median(cost | task, model, effort)
              / median(cost | task, model, baseline_effort)
```

样本不足时只给宽区间，并标记低置信度。

### Monte Carlo

对未来每个任务从 profile 的联合经验分布中抽样 token 组合，应用对应费率，重复至少 2,000 次。输出：

- 总消耗 P50/P90
- 在重置前耗尽的概率
- 可完成任务数 P10/P50/P90
- 预算内最便宜的模型/effort 组合

## 8. 外部消耗识别

如果额度百分比下降，但同一时间没有本地 token 事件，则标记为 `unattributed usage`。原因可能包括云任务、其他设备或共享 agentic 使用池。规划器应把这部分作为背景消耗，而不是错误分摊给最近的本地任务。

## 9. 置信度评分

建议综合：

- 数据来源等级
- 相似样本数量
- 数据新鲜度
- profile 方差
- 未归因消耗占比
- 费率表是否过期

最终输出 High/Medium/Low，并让用户能展开查看原因。

## 10. 必测边界

- 重置前后两条相邻快照
- used percent 一段时间不变后突然跳变
- 客户端重启导致 token counter 回退
- 同一事件重复写入
- 时区与夏令时切换
- 未来/过去异常 resets_at
- reasoning token 与 output token 的包含关系
- 未知模型和未知 effort
