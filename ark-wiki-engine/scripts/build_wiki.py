"""build_wiki.py — 知識庫骨架 scaffold（v3）

    python build_wiki.py <output_dir> [project_name]
    python build_wiki.py <output_dir> <name> --install-skill <.kiro/skills>
    python build_wiki.py --validate <project_dir>

## v3 只做一件事：產 `knowledge/{name}/` 骨架

**v2 產 23 個檔案**，其中 18 個是 `src/skills/wiki_skills/`、`src/server/`、
Web UI 三檔、`run.py`、`requirements.txt` 的模板字串 —— 那些是四層引擎與
FastAPI server 的**第二份實作**，而消費端（ark-agent）的 `src/wiki` 已被刪除
（design F-3／F-5）。同一功能兩份實作必然漂移。

**D-2 裁定（2026-09-04）：直接刪除，不封存。** 理由：四層邏輯已在 `scripts/`
且是唯一實作；要取回舊模板可用
`git show <v2 commit>:ark-wiki-engine/scripts/build_wiki.py`。

v3 產出：

    knowledge/{name}/
      ├─ raw/            原始素材（唯讀）
      ├─ wiki/           結構化頁面
      │   └─ .index/     索引（自帶 .gitignore，內容不進版控）
      ├─ schema.md       頁面規格 + tags 白名單（wiki_taxonomy 讀這裡）
      ├─ index.md        頁面索引（wiki_index.py md 重建）
      └─ log.md          操作日誌（append-only）
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _wikilib import ErrorCode, emit_error, emit_json  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
TODAY = str(date.today())

# .index/ 放在 wiki/ 底下（與 _wikilib.index_dir 一致）
DIRS = [
    "knowledge/{name}/raw",
    "knowledge/{name}/wiki",
    "knowledge/{name}/wiki/.index",
]

# 隨 skill 走的腳本（--install-skill 時複製）
SKILL_SCRIPTS = [
    "_wikilib.py", "wiki_query.py", "wiki_index.py", "wiki_context.py",
    "wiki_ingest.py", "wiki_lint.py", "wiki_graph.py", "wiki_guard.py",
    "wiki_taxonomy.py", "validate_wiki.py", "build_wiki.py",
]


def _schema_md(name: str) -> str:
    return f'''---
title: "Schema 規則"
version: "3.0"
updated: {TODAY}
---

# {name} 知識庫 Schema v3.0

## 頁面類型（type）

| type | 說明 |
|------|------|
| concept | 概念說明、方法論 |
| entity | 實體（工具、服務、框架） |
| source | 原始資料萃取 |
| synthesis | 多來源綜合分析 |
| comparison | 比較對照 |
| overview | 總覽索引 |
| system | 系統規範 |

## 成熟度（status）

| status | 說明 |
|--------|------|
| seedling | 剛建立，待充實 |
| developing | 有內容但不完整 |
| mature | 完整可參考 |

## 信任等級（trust，v3 必填）

| trust | 說明 | approved |
|-------|------|----------|
| deterministic | 人工撰寫或由確定式流程產出 | 不需要 |
| llm-distilled | 模型蒸餾產出 | **必填**（true/false 皆可，但要表態） |

> `approved: false` 的頁面 **不可標 `status: mature`**（seedling/developing 皆可）——
> 未審核的內容標成 mature，下游引用時就不會再懷疑它。
> `wiki_context.py` 會在注入時為它加上 ⚠。

## Frontmatter 必填欄位

```yaml
---
title: "頁面標題"
type: concept | entity | source | synthesis | comparison | overview | system
tags: [tag1, tag2]          # 必須在下方白名單內
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: seedling | developing | mature | evergreen
trust: deterministic | llm-distilled
# approved: true            # trust: llm-distilled 時必填
---
```

## tags 白名單

- overview

> ⚠️ **`- ` 清單必須緊接在本標題之後**（中間不可插入 `>` 說明或表格）——
> `wiki_taxonomy.load_whitelist` 只抓「標題後緊接的連續 `- ` 行」。
> 格式不合會讓白名單靜默變成**空集合**，而空集合的語意是
> **所有 tag 都不合法 → ingest 全部被擋**（fail-closed，不是全部放行）。
> **LLM 不得自創 tag**，新概念走 `wiki_taxonomy.py propose` → 人工 `approve`。
> `wiki_ingest.py --schema` 與 `wiki_lint.py --schema` 都讀這個區塊。

## tags 提案佇列

| tag | 提案原因 | 提案者 | 日期 |
|-----|----------|--------|------|

## 連結規則

- 雙向連結：`[[page_name]]`（不含 .md、不含路徑）
- 矛盾標記：`> ⚠️ **矛盾**：來源 A 說 X，來源 B 說 Y，待釐清。`
- 不確定：`(?)`

## 操作規則

- `raw/` 唯讀（LLM 只讀不改）
- 修改 wiki 後必須更新 `index.md` + `log.md`
- 禁止刪除 `log.md` 舊記錄（append-only）
- 禁止自行解決矛盾（只能標記）
'''


def _index_md(name: str) -> str:
    return f'''---
title: "{name} 知識庫索引"
updated: {TODAY}
---

# {name} 知識庫

## 頁面索引

- [[overview]]

## 分類

（待新增）
'''


def _log_md() -> str:
    return f'''# 操作日誌

> Append-only，禁止刪除舊記錄。

- **{TODAY}** | init | 知識庫初始化
'''


def _overview_md(name: str) -> str:
    return f'''---
title: "{name} 總覽"
type: overview
tags: [index]
created: {TODAY}
updated: {TODAY}
status: seedling
---

# {name}

專案總覽頁面。

## 架構

（待補充）

## 關鍵頁面

（待新增知識後自動更新）
'''


# ── 8 個 Wiki Skills ──────────────────────────────────────────


# ── Build 主流程 ──────────────────────────────────────────────

def build_wiki(output_dir: Path, project_name: str = "default") -> list[str]:
    """產出 knowledge/{name}/ 骨架。回傳已建立的檔案清單（已存在的不覆寫）。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    for d in DIRS:
        (output_dir / d.format(name=project_name)).mkdir(parents=True, exist_ok=True)

    kb_root = output_dir / "knowledge" / project_name
    files = {
        kb_root / "schema.md": _schema_md(project_name),
        kb_root / "index.md": _index_md(project_name),
        kb_root / "log.md": _log_md(),
        kb_root / "wiki" / "overview.md": _overview_md(project_name),
        # 索引是執行期產物：自我忽略，避免每個消費端 repo 都要記得加 ignore 規則
        kb_root / "wiki" / ".index" / ".gitignore": "*\n",
    }
    for path, content in files.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(str(path.relative_to(output_dir)))
    return created


def install_skill(dest_skills_dir: Path) -> list[str]:
    """把 scripts/ 與 references/ 複製到消費端 .kiro/skills/ark-wiki-engine/。"""
    dest = dest_skills_dir / "ark-wiki-engine"
    copied: list[str] = []
    for name in SKILL_SCRIPTS:
        src = SKILL_ROOT / "scripts" / name
        if not src.exists():
            continue
        out = dest / "scripts" / name
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        copied.append(str(out.relative_to(dest_skills_dir)))
    for rel in ("SKILL.md", "requirements.txt"):
        src = SKILL_ROOT / rel
        if src.exists():
            shutil.copy2(src, dest / rel)
            copied.append(f"ark-wiki-engine/{rel}")
    refs = SKILL_ROOT / "references"
    if refs.is_dir():
        for f in sorted(refs.iterdir()):
            if f.is_file():
                out = dest / "references" / f.name
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, out)
                copied.append(str(out.relative_to(dest_skills_dir)))
    return copied


REQUIRED_KB_FILES = ["schema.md", "index.md", "log.md", "wiki/overview.md"]


def validate_wiki(project_dir: Path) -> tuple[list[str], list[str]]:
    """驗證骨架完整性 + `.index/manifest.json` 的 tokenizer/backend 合法。

    v2 驗的是 23 個模板檔存不存在 —— 那些檔案 v3 不再產出，
    照舊會永遠 missing 21 個（**驗一個不該存在的東西，比不驗更糟**）。
    """
    found: list[str] = []
    missing: list[str] = []
    kb_root = project_dir / "knowledge"
    if not kb_root.exists():
        return found, ["knowledge/"]

    for kb_dir in sorted(p for p in kb_root.iterdir() if p.is_dir()
                         and not p.name.startswith(".")):
        for f in REQUIRED_KB_FILES:
            rel = f"knowledge/{kb_dir.name}/{f}"
            (found if (kb_dir / f).exists() else missing).append(rel)

        mf = kb_dir / "wiki" / ".index" / "manifest.json"
        if mf.exists():
            try:
                m = json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                missing.append(f"knowledge/{kb_dir.name}/wiki/.index/manifest.json (不可解析)")
                continue
            ok = (m.get("tokenizer") in ("jieba", "bigram")
                  and m.get("bm25_backend") in ("purepy", "bm25s"))
            (found if ok else missing).append(
                f"knowledge/{kb_dir.name}/wiki/.index/manifest.json"
                f" (tokenizer={m.get('tokenizer')}, backend={m.get('bm25_backend')})")
    return found, missing


def main() -> None:
    p = argparse.ArgumentParser(description="Wiki 骨架 scaffold（v3）")
    p.add_argument("output_dir", nargs="?", help="產出目錄")
    p.add_argument("project_name", nargs="?", default="default")
    p.add_argument("--validate", metavar="PROJECT_DIR", default="")
    p.add_argument("--install-skill", dest="install_skill", metavar="SKILLS_DIR",
                   default="", help="同時把 scripts/references 複製到該 .kiro/skills/")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if args.validate:
        found, missing = validate_wiki(Path(args.validate))
        total = len(found) + len(missing)
        if args.json:
            emit_json({"ok": not missing, "action": "validate", "checked": total,
                       "found": found, "missing": missing}, 1 if missing else 0)
        if missing:
            print(f"❌ 驗證失敗：{len(found)}/{total}，缺 {len(missing)} 個")
            for m in missing:
                print(f"  - {m}")
            sys.exit(1)
        print(f"✅ 驗證通過：{len(found)}/{total}")
        return

    if not args.output_dir:
        p.error("需要 output_dir，或用 --validate <project_dir>")

    created = build_wiki(Path(args.output_dir), args.project_name)
    installed = install_skill(Path(args.install_skill)) if args.install_skill else []

    if args.json:
        emit_json({"ok": True, "action": "build", "project": args.project_name,
                   "created": created, "installed": installed})
    print(f"✅ 知識庫骨架完成：{len(created)} 個檔案")
    for f in created:
        print(f"  + {f}")
    if installed:
        print(f"📦 skill 已安裝：{len(installed)} 個檔案 → {args.install_skill}")


if __name__ == "__main__":
    main()
