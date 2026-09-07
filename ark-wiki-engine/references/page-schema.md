---
title: "Wiki 頁面規格 v3.1"
type: reference
updated: 2026-09-04
---

# Wiki 頁面規格 v3.1

## Frontmatter

```yaml
---
title: "頁面標題"
type: concept | entity | source | synthesis | comparison | overview | system
tags: [tag1, tag2]              # 必須在 schema.md 的白名單內
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: seedling | developing | mature | evergreen
trust: deterministic | llm-distilled
approved: true | false          # trust: llm-distilled 時必填
aliases: [別名1, 別名2]          # 選填，但強烈建議
---
```

`wiki_lint.py` 對必填欄位（`title` / `type` / `created` / `updated` / `trust`）
缺一即 error，`errors > 0` → exit 1。

## type

| type | 說明 |
|------|------|
| `concept` | 概念說明、方法論 |
| `entity` | 實體（工具、服務、框架） |
| `source` | 原始資料萃取 |
| `synthesis` | 多來源綜合分析 |
| `comparison` | 比較對照 |
| `overview` | 總覽索引 |
| `system` | 系統規範 |

## status

| status | 說明 |
|--------|------|
| `seedling` | 剛建立，待充實（超過 30 天未升級會 warning） |
| `developing` | 有內容但不完整 |
| `mature` | 完整可參考 |
| `evergreen` | 長青頁面，內容穩定 —— **不受 seedling 逾期規則約束** |

> `evergreen` 於 2026-09-04 加入。W1 baseline 發現既有頁面已在使用它，
> 語意合理 → **是枚舉表少了一個值，不是資料錯**。
> 不要為了讓 lint 變綠而改資料語意。

## trust —— 兩層信任模型

| trust | 來源 | `approved` |
|-------|------|-----------|
| `deterministic` | 人工撰寫，或由確定式流程（ingest 骨架、腳本）產出 | 不需要 |
| `llm-distilled` | 模型蒸餾產出 | **必填**（`true`/`false` 皆可，但要表態） |

兩條由 `wiki_lint.py` 強制：

1. `trust: llm-distilled` 未帶 `approved` → **error**
2. `approved: false` 的頁面 **不可標 `status: mature`** → 否則 error
   （`seedling`／`developing` 皆可）

> 🔴 第 2 條的理由：未審核的內容標成 `mature` 會讓下游引用時不再懷疑它。
> `wiki_context.py` 注入時一律為它加上 ⚠。
>
> ⚠️ **2026-09-04 放寬**：原規則是「只能 `seedling`」。實測有 96 頁是
> `llm-distilled` + `developing` —— **`developing` 是有意義的成熟度資訊，
> 強制降級會毀掉它**。規則本意只需要擋 `mature`。

## aliases 為什麼重要

L0 精確層比對 `slug` / `title` / `aliases`：

| 命中 | 分數 |
|------|-----:|
| 等於 slug / title / page_id | 1.0（固定置頂） |
| 等於 alias | 0.95 |
| title 或 alias 包含查詢字串 | 0.8 |

「留存口徑」這種口語說法通常不是 title，**沒有 alias 就只能靠 BM25 碰運氣**。
aliases 同時會寫進 `.index/userdict.txt` 供 jieba 分詞，避免複合詞被切散。

## wikilink

- 雙向連結：`[[page_name]]`（不含 `.md`、不含路徑）
- 支援顯示文字：`[[target|顯示文字]]`
- `[[link]]` 的內容可以是 slug（`retention-definition`）或 page_id（`kpi/retention-definition`），兩者都會被解析
- L3 圖譜層用 `.index/graph.json` 的 1-hop 出／入鄰居擴散 ——
  **只被連結指到、完全不含查詢關鍵字的頁面也會被找出來**

## 矛盾與不確定

- 矛盾標記：`> ⚠️ **矛盾**：來源 A 說 X，來源 B 說 Y，待釐清。`
- 不確定：`(?)`
- **禁止自行解決矛盾**（只能標記）—— 判錯比沒判更糟

## 操作規則

- `raw/` 唯讀
- 修改 wiki 後必須更新 `index.md`（或跑 `wiki_index.py md`）
- `log.md` **append-only**，欄位 `date | op | page | trust | by | note`
- 索引 `.index/` 是執行期產物，自帶 `.gitignore`（不進版控）
