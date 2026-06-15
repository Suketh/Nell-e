import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.memory.sqlite_store import MemoryStore


def persona_instruction(persona: dict) -> str:
    name = str(persona.get("name", "Nellie")).strip() or "Nellie"
    summary = str(persona.get("identity", {}).get("summary", "")).strip()
    tone = str(persona.get("style", {}).get("tone", "")).strip()
    parts = [f"You are {name}."]
    if summary:
        parts.append(summary)
    if tone:
        parts.append(f"Use a {tone} tone.")
    return " ".join(parts)


def export_dataset(db_path: Path, output_path: Path, dataset_format: str) -> int:
    store = MemoryStore(db_path)
    try:
        rows = store.approved_feedback()
    finally:
        store.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            user = row["user"].strip()
            original = row["ai"].strip()
            correction = row["correction"].strip()
            chosen = correction or original
            if not user or not chosen:
                continue

            if dataset_format == "dpo":
                if not correction or not original or correction == original:
                    continue
                payload = {
                    "prompt": user,
                    "chosen": correction,
                    "rejected": original,
                    "model": row["model"],
                    "feedback_id": row["id"],
                }
            else:
                payload = {
                    "messages": [
                        {"role": "system", "content": persona_instruction(row["persona"])},
                        {"role": "user", "content": user},
                        {"role": "assistant", "content": chosen},
                    ],
                    "model": row["model"],
                    "feedback_id": row["id"],
                }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export explicitly approved Nellie feedback as JSONL training data."
    )
    parser.add_argument("--db", type=Path, default=Path("data/memory.db"))
    parser.add_argument("--output", type=Path, default=Path("data/training/nellie_sft.jsonl"))
    parser.add_argument("--format", choices=("sft", "dpo"), default="sft")
    args = parser.parse_args()
    count = export_dataset(args.db, args.output, args.format)
    print(f"Exported {count} {args.format.upper()} examples to {args.output}")


if __name__ == "__main__":
    main()
