# Arch Statement-to-Proposal Engine

A local command-line tool that turns a merchant's credit-card processing
statement (PDF) into an Arch proposal with their real numbers.

**Current status: Milestone 1 — Extract + Structure.** Upload a statement PDF
(local web app or CLI) and get clean, structured JSON.

## Pipeline

1. **Extract** (`extract.py`) — pull raw text and tables from the PDF with
   pdfplumber, flattened into one blob. No per-processor layout hardcoding.
2. **Structure** (`structure.py`) — hand the blob to Claude and get back JSON
   matching a fixed schema, validated and retried on bad output.
3. *Analyze* — _(milestone 2, not built yet)_
4. *Generate* — _(milestone 3, not built yet)_

## Setup

```bash
cd arch-engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your ANTHROPIC_API_KEY
```

## Usage — web app (recommended)

Run the local web app, then open it in your browser:

```bash
uvicorn app:app --reload
# open http://127.0.0.1:8000
```

Drag a statement PDF onto the page (or click to choose) and hit **Process**.
You'll get summary cards (merchant, volume, fees, effective rate, pricing model)
plus the full structured JSON with a copy button.

## Usage — CLI

```bash
python main.py path/to/statement.pdf
```

The structured JSON prints to stdout (progress messages go to stderr, so you can
pipe the JSON cleanly). Useful flags:

```bash
python main.py statement.pdf --raw                 # also dump the raw extract
python main.py statement.pdf -o output/result.json # save the JSON to a file
python main.py statement.pdf --model claude-opus-4-8
```

To prove it works across processors, run 2–3 different statements (e.g. Fiserv,
TSYS, Elavon) through it and eyeball the JSON.

## Output schema

```jsonc
{
  "merchant_name": "string | null",
  "statement_period": "string | null",
  "total_volume": "number | null",
  "transaction_count": "integer | null",
  "total_fees": "number | null",
  "interchange_fees": "number | null",
  "assessment_fees": "number | null",
  "processor_markup": "number | null",   // Arch-addressable markup; null if not separable
  "fixed_fees": { "pci": "number|null", "monthly": "number|null",
                  "batch": "number|null", "statement": "number|null",
                  "other": "number|null" },
  "current_model": "flat | tiered | IC+ | unknown",
  "card_mix": "[{card_type, volume, percentage}] | null",
  "notes": "string | null"              // junk fees / ambiguities / assumptions
}
```

Numbers come back as plain numbers (no `$` or commas). Fields the statement
doesn't report come back as `null` rather than guessed values.

## Notes

- Milestone 1 handles text-based PDFs. Scanned/image-only statements (no
  embedded text) aren't supported yet — they'd need OCR.
- The model is `claude-opus-4-8` by default; override with `--model` or the
  `ARCH_MODEL` env var.
