#!/usr/bin/env python3
"""engineering-pitfalls 仓库自检（本地与 CI 通用）。

检查项：frontmatter / 内部链接 / E 编号唯一 / agents 描述长度 / 待办标记。
用法：python3 scripts/validate_skill.py [skill目录]
"""

import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

errors: list[str] = []


def frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}, ""
    body = m.group(1)
    if HAS_YAML:
        return (yaml.safe_load(body) or {}), body
    data = {}
    for key in ("name", "description"):
        km = re.search(rf"^{key}:\s*(.+)$", body, re.M)
        if km:
            data[key] = km.group(1).strip().strip('"').strip("'")
    return data, body


root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

skill_md = root / "SKILL.md"
if not skill_md.exists():
    errors.append("SKILL.md 不存在")
else:
    data, _ = frontmatter(skill_md.read_text(encoding="utf-8"))
    if data.get("name") != root.name:
        errors.append(f"frontmatter name={data.get('name')!r} 与目录名 {root.name!r} 不一致")
    if not data.get("description"):
        errors.append("frontmatter description 为空")

link_re = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
for md in sorted(root.rglob("*.md")):
    for target in link_re.findall(md.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = target.partition("#")[0]
        if path and not (md.parent / path).resolve().exists():
            errors.append(f"{md.relative_to(root)}: 链接失效 -> {target}")

log = root / "references" / "log.md"
if log.exists():
    ids = re.findall(r"^###\s+(E-\d{3})\b", log.read_text(encoding="utf-8"), re.M)
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        errors.append(f"log E 编号重复: {', '.join(dups)}")

agents = root / "agents" / "openai.yaml"
if agents.exists():
    text = agents.read_text(encoding="utf-8")
    if HAS_YAML:
        cfg = yaml.safe_load(text) or {}
        short = (cfg.get("interface") or {}).get("short_description", "")
    else:
        m = re.search(r"short_description:\s*\"([^\"]*)\"", text)
        short = m.group(1) if m else ""
    if not 25 <= len(short) <= 64:
        errors.append(f"agents/openai.yaml short_description 长度 {len(short)} 不在 25~64")

for path in sorted(root.rglob("*")):
    if path.is_file() and ".git" not in path.parts and path.suffix in (".md", ".py", ".yml", ".yaml", ".tmpl"):
        if path.resolve() == Path(__file__).resolve():
            continue
        if re.search(r"\b(TODO|FIXME)\b", path.read_text(encoding="utf-8", errors="ignore"), re.I):
            errors.append(f"{path.relative_to(root)}: 含待办标记")

if errors:
    for e in errors:
        print(f"FAIL  {e}")
    print(f"共 {len(errors)} 个错误")
    sys.exit(1)
print("OK    技能自检通过")
