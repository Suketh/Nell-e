# Nellie learning pipeline

Nellie uses three separate learning layers:

1. Runtime memory in `data/memory.db`
2. Explicit response feedback collected in the chat UI
3. Optional offline adapter training

The desktop app never updates model weights automatically.

## Collect feedback

- `Useful` approves the displayed response.
- `Improve` stores the original response and your corrected response.
- A negative rating without a correction is retained for analysis but excluded
  from training exports.

## Export reviewed data

SFT:

```powershell
.\.venv\Scripts\python.exe tools\export_training_dataset.py `
  --format sft `
  --output data\training\nellie_sft.jsonl
```

DPO preference pairs:

```powershell
.\.venv\Scripts\python.exe tools\export_training_dataset.py `
  --format dpo `
  --output data\training\nellie_dpo.jsonl
```

Inspect the JSONL before training. Remove secrets, accidental personal data,
low-quality corrections, and duplicated examples.

## Adapter training

Train outside the desktop environment, preferably in WSL2 or Linux. Keep the
base model fixed and use a LoRA or QLoRA adapter. A 24 GB GPU is suitable for
an 8B model with 4-bit QLoRA, but batch size and sequence length still need to
be conservative.

Recommended gates before activating an adapter:

- At least 200 reviewed SFT examples
- A held-out evaluation set that is never trained on
- No regression in memory accuracy, refusal behavior, language consistency,
  tool use, or response latency
- Manual review of at least 50 fixed prompts

After training, import the adapter into the serving runtime and register it as
a separate model name. Do not replace `hermes3:8b`; keep it available as the
rollback model.
