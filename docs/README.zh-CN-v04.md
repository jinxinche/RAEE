# RAEE-Lite v0.4.0 中文快速入门

**定位**：面向 AI 编程的角色感知证据工程工具。它记录实际的检查结果、给出需求与证据之间的缺口、对比 PR 修改前后的证据变化。它不声称证明所有代码正确，也不会把 AI 历史日志直接当作当前验证。

## 安装与用法

```bash
python -m pip install -e .
raee-lite check
raee-lite add "登录功能能正常工作"
raee-lite expect --for R1 --kind e2e
raee-lite plan
```

**导入 Codex/Claude Code 记录**（需用户显式选择自己的 JSONL 日志）：

```bash
raee-lite import-agent --provider codex --file /path/to/rollout.jsonl
raee-lite import-agent --provider claude --file /path/to/session.jsonl
raee-lite report
```

`A...` 证据编号可在 `.raee/report.json` 中找到；它只代表日志内容的观察记录。

**关联需求**：

```bash
raee-lite link --for R1 --evidence Axxxxxxxxxxxx --reason "与登录测试相关的命令记录"
```

用户关联本身仍然不是测试充分性的证明。要求明确后，需由用户授权重新执行真实测试：

```bash
raee-lite run --for R1 --kind e2e -- npx playwright test
```

**PR 差异**：

```bash
raee-lite compare --base base/.raee/report.json --head head/.raee/report.json --out comparison --fail-on-regression
```

HTML 页面默认生成 `.raee/report.html`，PR 对比页面为 `comparison/pr-diff.html`。

**默认安全规则**：不上传任何代码或日志；导入不执行命令；`check` 不执行项目脚本，只有 `check --run` 和 `run` 显式执行。执行不受信任代码前请使用隔离环境。完整限制详见英文 README 和 `examples/AGENT_IMPORT.md`。
