# GitHub 发布路线

## 1. 仓库定位

- 名称：`codex-quota-lens`
- 描述：`Local-first Codex quota dashboard, burn-rate analytics, and usage planner.`
- License：MIT
- 默认分支：`main`
- Topics：`codex`, `openai`, `tauri`, `usage-analytics`, `quota`, `developer-tools`, `local-first`

## 2. 推荐里程碑

### M0 — Feasibility

- [ ] 建立匿名合成 JSONL fixtures
- [ ] 实现 schema 探测与字段白名单
- [ ] 增量解析 token_count/rate-limit snapshot
- [ ] 验证 Windows/macOS/Linux 路径发现
- [ ] 写清楚非官方与兼容性声明

### M1 — Collector CLI

- [ ] `codex-lens doctor`
- [ ] `codex-lens ingest --since 7d`
- [ ] `codex-lens snapshot --json`
- [ ] SQLite migrations
- [ ] reset epoch 检测与测试

### M2 — Desktop MVP

- [ ] Overview 实时仪表盘
- [ ] 5m/1h burn rate
- [ ] fastest periods 与热力图
- [ ] 数据新鲜度和质量等级
- [ ] 本地数据清理

### M3 — Planner

- [ ] workload profiles
- [ ] versioned rate-card catalog
- [ ] model/effort scenario comparison
- [ ] bootstrap/Monte Carlo 区间
- [ ] 背景消耗识别

### M4 — Team & Hardening

- [ ] Enterprise adapter
- [ ] 可访问性与国际化
- [ ] signed releases
- [ ] schema 诊断包
- [ ] threat model 与独立安全审查

## 3. 首批 Issues

1. `feat(collector): discover Codex session directories cross-platform`
2. `feat(schema): normalize token_count events without persisting content`
3. `feat(analytics): detect rate-limit reset epochs`
4. `feat(storage): add idempotent SQLite ingestion`
5. `feat(cli): add doctor and snapshot commands`
6. `test(fixtures): create fully synthetic schema fixtures`
7. `feat(ui): build quota overview cards`
8. `feat(analytics): calculate rolling burn rate and fastest windows`
9. `feat(planner): implement budget pace and ETA intervals`
10. `security: document local data threat model`

建议给每个 issue 加：背景、范围、非目标、验收标准、隐私影响、测试计划。

## 4. 标签

- `area:collector`
- `area:analytics`
- `area:planner`
- `area:ui`
- `area:security`
- `source:local`
- `source:enterprise`
- `schema-change`
- `good first issue`
- `help wanted`

## 5. CI

Pull request 必跑：

- Rust format/clippy/test
- TypeScript lint/typecheck/test
- synthetic fixture compatibility matrix
- secret scan
- dependency audit
- 禁止 fixtures 中出现绝对用户路径、email、token 或真实 prompt 的隐私检查

Release 构建应生成 SBOM、校验和与签名，并覆盖三大桌面平台。

## 6. 社区策略

- 第一版 README 同时提供中文与英文摘要
- 把“非官方、只读、本地优先”放在首屏
- 提供 screenshots/GIF，但使用合成数据
- 不接受包含真实会话内容的 bug report
- schema 兼容问题只接收字段名/类型诊断包

## 7. 发布前检查

- [ ] 仓库名无明显冲突
- [ ] 所有截图使用合成数据
- [ ] LICENSE、SECURITY、CONTRIBUTING 完整
- [ ] 官方来源链接可访问，费率版本有日期
- [ ] 应用未绑定公网接口
- [ ] 从干净机器验证安装、卸载和数据删除
- [ ] 明确声明不保证额度、账单或服务可用性

