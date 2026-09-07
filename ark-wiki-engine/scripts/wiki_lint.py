"""wiki_lint.py — Wiki 健康檢查腳本

用途：檢查 wiki/ 目錄下所有頁面的品質問題。
- frontmatter 必要欄位驗證
- 孤立頁面偵測（無任何 inbound wikilink）
- 斷裂 wikilink（指向不存在的頁面）
- status 過期提醒

使用方式：
    python scripts/wiki_lint.py --wiki_dir knowledge/wiki

    # 只看錯誤（忽略警告）
    python scripts/wiki_lint.py --wiki_dir knowledge/wiki --errors-only

    # JSON 輸出（給程式用）
    python scripts/wiki_lint.py --wiki_dir knowledge/wiki --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _wikilib import (  # noqa: E402
    ErrorCode,
    emit_error,
    emit_json,
    extract_wikilinks,
    index_dir,
    iter_pages,
    parse_frontmatter,
)


REQUIRED_FIELDS = ["title", "type", "created", "updated", "trust"]
RECOMMENDED_FIELDS = ["tags", "status"]
VALID_TRUST = ["deterministic", "llm-distilled"]
VALID_TYPES = ["concept", "entity", "source", "synthesis", "comparison", "overview", "system"]
# `evergreen`（2026-09-04 加入）：長青頁面 —— 內容穩定、不該被 seedling 逾期規則催。
# W1 baseline 實測有 2 頁在用它，語意合理 → **是枚舉表少了一個值，不是資料錯**。
# （為了讓 lint 變綠而改資料語意是本末倒置。）
VALID_STATUS = ["seedling", "developing", "mature", "evergreen"]


def lint_wiki(wiki_dir: Path, errors_only: bool = False,
              schema: Path | None = None) -> dict:
    """執行 lint，回傳結果字典。"""
    md_files = [f for f in iter_pages(wiki_dir) if index_dir(wiki_dir) not in f.parents]
    if not md_files:
        return {"files": 0, "errors": [], "warnings": []}

    whitelist: set[str] | None = None
    if schema is not None:
        import wiki_taxonomy
        whitelist = wiki_taxonomy.load_whitelist(schema)

    errors = []
    warnings = []
    all_pages = {}  # filename_stem → path
    all_inbound: dict[str, int] = {}  # page_name → inbound count
    all_outbound: dict[str, list[str]] = {}  # page_name → list of targets

    # Pass 1: 收集所有頁面 + 驗證 frontmatter
    for f in md_files:
        content = f.read_text(encoding="utf-8", errors="replace")
        page_name = f.stem
        rel = f.relative_to(wiki_dir)
        all_pages[page_name] = f
        fm = parse_frontmatter(content)

        # Frontmatter 存在性
        if not fm:
            errors.append({"file": str(rel), "level": "error", "msg": "缺少 frontmatter"})
            continue

        # 必要欄位
        for field in REQUIRED_FIELDS:
            if field not in fm:
                errors.append({"file": str(rel), "level": "error", "msg": f"缺少必要欄位：{field}"})

        # 推薦欄位
        if not errors_only:
            for field in RECOMMENDED_FIELDS:
                if field not in fm:
                    warnings.append({"file": str(rel), "level": "warning", "msg": f"建議補充：{field}"})

        # type 合法值
        if "type" in fm and fm["type"] not in VALID_TYPES:
            warnings.append({"file": str(rel), "level": "warning", "msg": f"type 不在合法值中：{fm['type']}"})

        # status 合法值
        if "status" in fm and fm["status"] not in VALID_STATUS:
            warnings.append({"file": str(rel), "level": "warning", "msg": f"status 不在合法值中：{fm['status']}"})

        # ── 兩層信任模型（v3 新增；SKILL.md 早已宣告，實作是零檢查 = F-7）
        #
        # trust=llm-distilled 的頁面是模型蒸餾產出，**必須**有 approved 欄位表態；
        # 未審核（approved:false）的內容只能停在 seedling ——
        # 一旦標成 developing/mature，下游引用時就不會再懷疑它。
        if "trust" in fm and fm["trust"] not in VALID_TRUST:
            errors.append({"file": str(rel), "level": "error",
                           "msg": f"trust 不在合法值中：{fm['trust']}（{'|'.join(VALID_TRUST)}）"})
        if fm.get("trust") == "llm-distilled" and "approved" not in fm:
            errors.append({"file": str(rel), "level": "error",
                           "msg": "trust: llm-distilled 必須帶 approved 欄位（true/false 皆可，但要表態）"})
        # [2026-09-04 放寬] 原規則是「approved:false 只能是 seedling」，
        # 但實測 paddy-bot 的 hoyeah 知識庫有 96 頁是 llm-distilled + developing ——
        # **`developing` 是有意義的成熟度資訊，強制降成 seedling 會把它毀掉**。
        # 規則的本意是「未審核的內容不可看起來像權威」，那只需要擋 `mature`。
        if fm.get("approved") is False and fm.get("status") == "mature":
            errors.append({"file": str(rel), "level": "error",
                           "msg": "approved: false 的頁面不可標 status: mature"
                                  "（未經人工審核不該看起來像權威；developing 可以）"})

        # ── tags 受控詞彙（--schema 給了才驗）
        if whitelist is not None:
            page_tags_val = fm.get("tags", [])
            if isinstance(page_tags_val, str):
                page_tags_val = [page_tags_val]
            for t in page_tags_val:
                if t not in whitelist:
                    errors.append({"file": str(rel), "level": "error",
                                   "msg": f"tag 不在白名單：{t}"
                                          f"（用 wiki_taxonomy.py propose 提案）"})

        # status 過期（seedling 超過 30 天）
        if not errors_only and fm.get("status") == "seedling" and "created" in fm:
            try:
                created = date.fromisoformat(str(fm["created"]))
                if date.today() - created > timedelta(days=30):
                    warnings.append({
                        "file": str(rel), "level": "warning",
                        "msg": f"seedling 已超過 30 天（created: {fm['created']}），考慮升級或刪除"
                    })
            except ValueError:
                pass

        # Wikilinks
        links = extract_wikilinks(content)
        all_outbound[page_name] = links
        for link in links:
            all_inbound[link] = all_inbound.get(link, 0) + 1

    # Pass 2: 斷裂 wikilink + 孤立頁面
    # [2026-09-04 降級 error → warning]
    #
    # 指向尚未建立的頁面是 wiki 的**正常成長狀態**（red link），不是缺陷 ——
    # 它壞不了任何工具，而且是「蒸餾時就知道該有這頁」的需求訊號。
    #
    # 實測 paddy-bot 的 hoyeah 知識庫：144 筆斷裂連結指向 45 個頁，
    # 其中 **25 個被 3 頁以上引用** = 真的知識缺口。把它們當 error 的後果是
    # lint 永遠紅、CI 掛不上，而 144 筆在 v2 時代累積數月無人處理 ——
    # 那正是本 repo 記過的「常駐假警報的代價不是雜訊，是維運開始習慣性忽略該檢查」。
    #
    # error 保留給**破壞工具契約**的問題（缺必填欄位、trust 語意違規、tag 不在白名單）。
    # 缺口清單改由 wiki_graph.py 的 broken_links 與缺口報告提供。
    for page_name, targets in all_outbound.items():
        for target in targets:
            if target not in all_pages:
                warnings.append({
                    "file": str(all_pages[page_name].relative_to(wiki_dir)),
                    "level": "warning",
                    "msg": f"斷裂 wikilink：[[{target}]] 指向不存在的頁面"
                            f"（red link —— 若被多頁引用代表真的該建這一頁）"
                })

    if not errors_only:
        for page_name, path in all_pages.items():
            if page_name not in all_inbound and page_name != "overview":
                warnings.append({
                    "file": str(path.relative_to(wiki_dir)),
                    "level": "warning",
                    "msg": "孤立頁面（無任何 inbound wikilink）"
                })

    return {
        "files": len(md_files),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Wiki Lint — 健康檢查")
    p.add_argument("--wiki_dir", required=True, help="wiki/ 目錄路徑")
    p.add_argument("--errors-only", action="store_true", help="只顯示錯誤")
    p.add_argument("--schema", default="", help="schema.md 路徑（給了才驗 tags 白名單）")
    p.add_argument("--json", action="store_true", help="JSON 格式輸出")
    args = p.parse_args()

    wiki_dir = Path(args.wiki_dir)
    if not wiki_dir.exists():
        emit_error(ErrorCode.WIKI_DIR_NOT_FOUND, f"目錄不存在：{wiki_dir}")
    schema = Path(args.schema) if args.schema else None
    if schema is not None and not schema.exists():
        emit_error(ErrorCode.SCHEMA_NOT_FOUND, f"schema 不存在：{schema}")

    result = lint_wiki(wiki_dir, args.errors_only, schema)
    errors, warnings = result["errors"], result["warnings"]

    if args.json:
        # exit code 以 errors 數為準 —— CI 靠它擋，不靠人讀輸出
        emit_json({"ok": not errors, "action": "lint", "files": result["files"],
                   "error_count": len(errors), "warning_count": len(warnings),
                   "errors": errors, "warnings": warnings}, 1 if errors else 0)

    print(f"🔍 Wiki Lint：{result['files']} 頁面")
    print(f"   ❌ errors: {len(errors)}｜⚠️  warnings: {len(warnings)}\n")
    for e in errors:
        print(f"  ❌ {e['file']}：{e['msg']}")
    if not args.errors_only:
        for w in warnings:
            print(f"  ⚠️  {w['file']}：{w['msg']}")
    if not errors and not warnings:
        print("✅ 全數通過")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
