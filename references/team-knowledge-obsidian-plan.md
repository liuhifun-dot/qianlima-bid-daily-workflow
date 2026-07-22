# Team Knowledge and Obsidian Planning

## Purpose

Use this reference when planning future team sharing of bid-screening experience, scoring rules, daily run summaries, and false-positive or false-negative review cases. This is a planning document only. Do not automatically write to Obsidian during the daily workflow unless the user explicitly enables that behavior.

## What Should Be Stored

Store knowledge that improves future judgment:

- Stable screening rules.
- Hard exclusion examples.
- Evidence examples for recommendation.
- Borderline cases that require manual review.
- False positives and false negatives found by the user or team.
- Daily run summary with links to generated files.
- Rule-version change notes.

Do not store:

- Qianlima passwords, cookies, tokens, QR codes, or Webhooks.
- DingTalk OAuth tokens.
- Full private logs with secrets.
- Large raw Excel files duplicated into notes.
- Personal contact details beyond what is public in bid documents.

## Suggested Obsidian Structure

Use a team vault or project vault chosen by the user. Suggested structure:

```text
标讯知识库/
  00_规则总览/
  01_硬排除规则/
  02_推荐候选证据样本/
  03_待人工复核案例/
  04_误判复盘/
  05_每日运行摘要/
  06_评分规则版本/
```

Keep the current Codex memory vault separate from a future team knowledge vault unless the user explicitly merges them.

## Daily Summary Note Contract

If enabled later, each daily run can write one concise note:

```markdown
# 标讯日报运行摘要 YYYY-MM-DD

## Run

- run_id:
- date_range:
- raw_export_count:
- phase2_total:
- keep:
- needs_review:
- reject:

## Files

- local_excel:
- shared_excel:
- dingpan_doc_url:
- phase2_json:

## 推荐候选

| 项目 | 证据 | 金额 | 地区 | 链接 |
|---|---|---:|---|---|

## 待人工复核

| 项目 | 为什么不能自动定论 | 需要人工看什么 |
|---|---|---|

## 误判与规则候选

- false_positive:
- false_negative:
- proposed_rule_change:

## 人工结论

- reviewer:
- decision:
- rule_update_needed:
```

## Scoring Rule Governance

Do not let daily runs silently rewrite scoring rules. Use this promotion path:

1. Human reviewer marks wrong recommendations, missed opportunities, or wrong exclusions.
2. Agent extracts the pattern into a candidate rule.
3. Candidate rule includes at least one positive example and one negative example.
4. Candidate rule is tested against recent baseline runs.
5. Only then promote it into the formal screening reference or script.

## Human Experience Capture

When the user or a colleague reviews bids manually, ask them to record reasoning in plain language. Convert the recording into:

- business scope signals;
- red flags;
- evidence needed before recommendation;
- hard exclusion patterns;
- example titles and body text snippets;
- "looks relevant but actually not ours" cases.

The goal is to distill judgment habits, not to create a keyword-only filter.

## Future Automation Options

When the user decides to enable Obsidian writing:

- Add a separate script that writes only sanitized summaries.
- Keep it behind an explicit config flag such as `enable_obsidian_summary=true`.
- Write to a team vault path configured outside the skill.
- Record every generated note path in the run manifest.
- Stop writing if the vault path is unavailable.

Do not enable this by default in the current skill.
