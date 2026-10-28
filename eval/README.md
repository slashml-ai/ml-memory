# `slashml-eval` — SlashML Benchmark Verification CLI

Standalone benchmark verification CLI for **SlashML (`/` `ml`)** against LongMemEval, LoCoMo, and ConvoMem via the SlashML Cloud API (`https://api.slashml.ai`).

## Usage

```bash
export SLASHML_API_KEY="sml_live_..."

# Run all public benchmarks (LongMemEval, LoCoMo, ConvoMem)
slashml-eval --benchmark all

# Run a single benchmark with JSON output
slashml-eval --benchmark longmemeval --json
```
