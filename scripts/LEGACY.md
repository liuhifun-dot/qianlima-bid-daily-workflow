# Legacy scripts (not used by formal pipeline)

Formal daily workflow is **CDP-only** (`run_daily_pipeline_20260622_v04.py`).

The following scripts remain in the Skill package for historical compatibility and manual debugging. They are **not** copied into the production runtime by `prepare_runtime_20260622_v02.py`:

| Script | Former role |
|--------|-------------|
| `kimi_webbridge_preflight_20260610_v01.py` | Kimi WebBridge preflight |
| `kimi_vip_body_read_20260622_v04.py` | VIP body via Kimi |
| `kimi_attachment_preview_read_20260622_v06.py` | Attachment preview / OCR via Kimi |

Do **not** wire these into unattended scheduled jobs. Using Kimi and CDP with the same Qianlima account can kick sessions.

See `references/kimi-webbridge-usage.md` for optional manual use.
