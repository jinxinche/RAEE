# RAEE-Lite：面向 AI 编程的角色感知证据工程

**让 AI 编程有证据，而不只是有“已完成”的回答。**

[English](../README.md) · [简体中文](README.zh-CN.md) · [Deutsch](README.de-DE.md) · [Español](README.es-ES.md)

**快速体验（候选分支）：** 在可信的隔离环境中安装 [v0.10.0rc2 源码候选](https://github.com/jinxinche/RAEE/tree/release/raee-lite-v0.10.0rc2)，然后运行 `raee-lite init`、`raee-lite add "注册必须拒绝无效邮箱"`、`raee-lite expect --for R1 --kind unit`、`raee-lite status`。预期结果为 `UNTESTED`；没有自动执行项目测试。正式稳定版尚未发布。


## 为什么需要 RAEE-Lite？

Codex、Claude Code、Cursor 等 AI 编程工具可以快速修改代码，但“AI 声称已修复”“测试进程退出码为 0”“功能真实满足用户要求”是三件不同的事。

**RAEE-Lite** 将角色感知证据工程思想应用到软件开发，把原本容易混为一谈的证据拆分为五个互不替代的角色：

| 证据角色 | 要回答的问题 | 不应过度推断的内容 |
| --- | --- | --- |
| **意图证据** | 用户真正要求什么？ | 有需求描述不等于功能已经实现。 |
| **变更证据** | 哪些代码和提交发生变化？ | 代码差异不等于正确性证明。 |
| **验证证据** | 实际执行了哪些检查？结果如何？ | 测试通过不意味着需求得到充分覆盖。 |
| **环境证据** | 在什么环境和条件下运行？ | 环境信息不自动构成可信身份。 |
| **边界证据** | 哪些部分缺失、过期或未验证？ | 没测过的行为不能标为已验证。 |

## 工具的设计能力

开发候选版本包含只读仓库预检查、需求与检查类别关联、部分 Codex / Claude Code JSONL 日志导入、代码版本指纹、验证记录、PR 前后证据差异，以及 HTML / Markdown / JSON / SARIF 报告。

Agent 历史日志只作为**未经独立验证的会话证据**；本地实际执行和可信 CI 来源证明也分别记录，不能相互替代。

## 最简使用方式

**发布状态提示：** 本仓库刚刚建立，当前正在准备首次公开源码发布；CLI 源码和安装包尚未上传到此仓库。以下命令展示开发候选版本的使用方式，并非当前可以直接从本仓库安装的承诺。

在已安装经过审查的本地开发版本后：

```bash
raee-lite preflight   # 只读检查配置与 CI 风险
raee-lite doctor      # 发现可能的检查项，不执行项目代码
raee-lite check       # 生成证据缺口报告
```

默认不会执行项目脚本；主动执行检查时，应使用可信代码与受限环境。

## 隐私与安全边界

- Agent 日志是不可信输入，不是可执行指令；公开分享前必须脱敏。
- 退出码为 0 仅说明对应命令完成，不代表需求、测试质量或安全性得到证明。
- Docker 隔离不等同于经过安全认证的虚拟机沙盒。
- 证据签名可以帮助验证来源和完整性，但不能证明测试结论真实充分。
- 真实用户日志兼容率、GitHub 云端签名、三系统 CI 和独立安全审计仍需在正式发布前完成验证。

## 研究来源与预印本引用

本软件从另一项肿瘤多模态 AI 研究提出的 **Role-Aware Evidence Engineering（RAEE，角色感知证据工程）** 思想获得启发：

> Hu, J., Jin, X., Song, Y., Chen, Z., & Xin, L. (2026). *Restricted Multimodal Oncology AI: Role-Aware Evidence Organisation and Cross-Domain Transfer Boundaries*. Research Square，预印本 v1。[DOI: 10.21203/rs.3.rs-10194336/v1](https://doi.org/10.21203/rs.3.rs-10194336/v1)。

原研究强调：不同生物学证据来源承担不同角色，不能因为被融合就视为等价。RAEE-Lite 将这种**角色不可交换性与适用边界**的设计原则迁移到代码变更和软件验证中。

**注意：预印本没有开发或实验验证 RAEE-Lite。** 引用该研究是为了说明方法论来源，而不是证明这款开发工具已经得到论文验证。引用软件时也应单独引用 GitHub 仓库。另见 [BibTeX](../REFERENCES.bib)。

## 项目现状

当前优先任务是公开可审查源码、取得真实 Linux / Windows / macOS CI 结果、完成独立 Artifact Attestation 验证，并通过授权的真实日志建立评测集。

许可证：[MIT](../LICENSE)。欢迎未来提交规范的复现案例、翻译改进和安全反馈，但不要在公开 Issue 中上传密钥或私人会话。
