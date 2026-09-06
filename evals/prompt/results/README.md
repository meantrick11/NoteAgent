# prompt eval results

每次跑分写在 **黄金集文件名** 下面，文件夹名带题号和时间，不用猜 `--name`。

```text
evals/prompt/results/<jsonl 主文件名>/<可选标签>_<题号或 all>_<时间>/
  config.json    # cases_path、case_filter、rubric、模型、prompt hash
  system.txt
  index.json     # 同样带 cases_path；各题总分（差的在前）
  n05.md
  b06.md
```

例如默认 `evals/prompt/cases.jsonl`、只跑 b06 和 n05：

```text
evals/prompt/results/cases/b06-n05_20260906-192615/
```

加 `--name v8` 时是 `cases/v8_b06-n05_20260906-192615/`。每题一份 `{id}.md`（如 `b06.md`），题头也有 `dataset` / `filter`。

`config.json` 必须能看出用了哪份考题：`cases_path`、`case_filter`（`null` 表示全集）、可选 `label`。另有 `rubric_version`、`chat_model`、`prompt_sha256`、`prompt_path`、UTC 起止、`case_ids`（黄金 id → `n05.md`）。

`n05.md` 含题头、得分摘要、全部小指标（含满分）、行为期望与实际、完整 `user` / `seed_files`、工具轨迹预览、草稿、助手气泡。不写本机 notes 绝对路径、API 密钥、token 流。

行为门失败或无需提案的题：正文写「未评正文」，不要把忠实记成 0。

合成考题的基线报告可以入库。含私人笔记的跑分不要提交。覆盖已有同一结果目录须 `--force`。以前扁平的 `results/<阶段名>/` 不必迁；新跑分走上面的布局。
