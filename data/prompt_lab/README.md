# Prompt Lab（抽取提示词试验台）

试验台与线上可对照。生产 LLM 路径仍用分阶段 `### ANALYSIS` + `### JSON`；lab 可继续改变体做对比。

**约定**：不要覆盖旧脚本、旧 prompts、旧 runs。新实验用新文件（如 `prompt_lab_html_run.py`、`v5_html.txt`）。

## 用法

```bash
# PDF / vision 类变体（旧入口，保留）
python scripts/prompt_lab_run.py --pdf data/samples/BKG.pdf --prompt baseline
python scripts/prompt_lab_run.py --pdf data/samples/BKG.pdf --prompt all

# 文字坐标 HTML + 文本模型（与生产 html / html_mix 同源思路）
python scripts/prompt_lab_html_run.py --pdf data/samples/BKG.pdf --prompt v5_html --model glm-5.3

# 纯文本对照（会丢版面）
python scripts/prompt_lab_text_run.py --pdf data/samples/BKG.pdf --prompt v4_text
```

结果写入 `data/prompt_lab/runs/`（已 gitignore）。控制台会打印 party 快照便于扫一眼。  
讲解类（解析不成 JSON）会额外写同名 `.md`。

## 提示变体

| 文件 | 作用 |
| --- | --- |
| `prompts/baseline.txt` | 早期生产抽取提示拷贝 |
| `prompts/explain.txt` | 讲解对照（抬头 vs 业务栏，不抽 JSON） |
| `prompts/v1_letterhead.txt` | 候选：禁区式「抬头≠当事人」 |
| `prompts/v2_title_anchor.txt` | 候选：正向标题锚点读法 |
| `prompts/v3_staged.txt` | 同一次：先 ANALYSIS 再 JSON |
| `prompts/v4_staged.txt` | 分阶段精简版（pdf/vision 对照） |
| `prompts/v4_text.txt` | 纯文本输入试验 |
| `prompts/v4_html.txt` / `v5_html.txt` | 坐标 HTML 输入；v5 强化 notify 同左栏等 |

线上 `html` / `html_mix` 的提示在 `app/parse/extract.py` 的 `_extract_prompt_html()`，与 v5_html 对齐思路。

新增变体：在 `prompts/` 下放 `.txt` 即可。分阶段变体会写出 `.json`（`analysis` + `parsed`）和可读 `.md`。

## 与生产模式的关系

| Lab | 生产 `LLM_INPUT_MODE` |
| --- | --- |
| `prompt_lab_run.py` | `pdf` / `vision` 对照 |
| `prompt_lab_html_run.py` | `html` / `html_mix` 的 LLM 侧 |
| `prompt_lab_text_run.py` | `text` |
| （无 lab）`html_struct` | 规则路径，见 `app/parse/struct_forms/` |
