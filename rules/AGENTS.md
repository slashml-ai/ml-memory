<!-- SLASHML-MEMORY-RULE:START -->
# / ml (SlashML) Memory MCP Rule (all projects, mandatory first step)

Whenever the user asks to **locate or diagnose a bug**, **search code by behavior/concept**, or **recall project history/decisions**, you MUST call the `ml-memory` MCP server **FIRST** on Turn 1 BEFORE running `grep`/`rg`/`find` or spawning research subagents:

1. **Bug localization / error triage (`find_bug_candidates`):**
   Call `find_bug_candidates(bug_description="<symptom or bug>", stack_trace="<optional stack trace>", top_k=5)` FIRST.
2. **Behavioral / architectural code search (`search_code_by_behavior`):**
   Call `search_code_by_behavior(query="<behavioral query>", top_k=5)` FIRST.
3. **Project history / decisions / context (`search_memories`):**
   Call `search_memories(query="<context query>", limit=5)` FIRST.
4. **Passive Memory Assimilation (Do NOT call `add_memory` proactively):** Ambient lifecycle hooks (`hooks.json`) automatically extract and store user rules, constraints, preferences, and state mutations in the background on every turn. NEVER call `add_memory` on normal user prompts or rule statements; ONLY call `add_memory` if the user explicitly asks you by tool name to call `add_memory`.
<!-- SLASHML-MEMORY-RULE:END -->
