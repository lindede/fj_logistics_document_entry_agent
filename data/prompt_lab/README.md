# Prompt Lab（抽取提示词试验台）

试验台与线上可对照。当前生产抽取提示对齐 **v4_staged**（先 ANALYSIS 再 JSON）；lab 仍可继续改变体做对比。

## 用法

```bash
# 单个变体
python scripts/prompt_lab_run.py --pdf data/samples/BKG.pdf --prompt baseline

# 目录内全部 .txt（baseline / explain / v1_letterhead …）
python scripts/prompt_lab_run.py --pdf data/samples/BKG.pdf --prompt all
```

结果写入 `data/prompt_lab/runs/`（已 gitignore）。控制台会打印 `party_snapshot`（shipper/consignee/notify_party/vessel/voyage/freight）便于扫一眼。  
讲解类（解析不成 JSON）会额外写同名 `.md`，直接打开读正文，不必盯 JSON 里的 `raw`。

## 提示变体

| 文件 | 作用 |
| --- | --- |
| `prompts/baseline.txt` | 现行生产抽取提示拷贝 |
| `prompts/explain.txt` | 讲解对照（强调抬头 vs 业务栏，不抽 JSON） |
| `prompts/v1_letterhead.txt` | 候选：禁区式「抬头≠当事人」 |
| `prompts/v2_title_anchor.txt` | 候选：正向标题锚点读法（偏单例） |
| `prompts/v3_staged.txt` | 同一次：先 ANALYSIS 再 JSON（含「按页阅读版面」） |
| `prompts/v4_staged.txt` | 分阶段精简版：可含多页；ANALYSIS 少禁令；JSON 留必要映射规则 |

新增变体：在 `prompts/` 下放 `.txt` 即可。分阶段变体会写出 `.json`（`analysis` + `parsed`）和可读 `.md`。
