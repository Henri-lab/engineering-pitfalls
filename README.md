# engineering-pitfalls 🕳️ 细碎工程踩坑库

> A **Codex skill** that accumulates cross-project "small engineering pitfalls" —
> shell, build/deploy, SQL, docker/infra, toolchain/network — the kind that cost
> one minute if you know them and half an hour if you don't. Docs are in Chinese.

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
  <img alt="Version" src="https://img.shields.io/badge/version-v0.1.0-informational">
  <img alt="Validate" src="https://github.com/Henri-lab/engineering-pitfalls/actions/workflows/validate.yml/badge.svg">
</p>

只做两件事：**动手前先搜，踩完就记**。不做严格分类，因为这类坑的边界本来就模糊
（算 shell 还是算部署？），检索友好比分类整齐更重要。

## 快速开始

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/Henri-lab/engineering-pitfalls.git ~/.codex/skills/engineering-pitfalls
```

之后在任意 Codex 会话中按 skill 名（`engineering-pitfalls`）触发即可。

## 目录

```text
SKILL.md              使用与记录规则
agents/openai.yaml    agent 元数据
references/log.md     经验正文（E-001 起，按"场景/现象/根因/修法/教训"五段式）
```

## 边界（与其它技能的分工）

- 这里记**跨项目可复用的单点小坑**（工程/工具/环境）；项目内的事故复盘留在项目自己的 `docs/bug-log.md`；
- **业务/架构设计决策**归各自的领域技能：membership-system-builder（会员支付）、
  identity-system-builder（认证）、subscription-splitter（边界拆分）、quality-gate-builder（门禁）；
- 服务器加固归 server-hardening；日志体系归 logging-system-builder。

## 起源与署名

源自课程站/粉丝站真实开发与上线复盘（`docs/bug-log.md`），2026-10-17 独立为公开仓库。
作者清单见 [AUTHORS.md](AUTHORS.md)；二次分发须保留 [LICENSE](LICENSE) 版权声明。

```text
engineering-pitfalls（v0.1.0）
作者：henrifox
仓库：https://github.com/Henri-lab/engineering-pitfalls
首发：2026-10-17｜许可：MIT（保留署名）
```

## License

[MIT](LICENSE) © 2026 henrifox
