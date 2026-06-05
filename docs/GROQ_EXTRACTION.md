# Groq Structured Extraction

Groq extraction is isolated in `core/llm/groq.py` and routed through
`core/agents/requirement_extractor.py`.

Supported key sources:

- `TELECOM_STUDIO_GROQ_API_KEY`
- `GROQ_API_KEY`
- `.env` key named `groq_api`

The default model is `openai/gpt-oss-120b`. The primary request uses Groq's
OpenAI-compatible Chat Completions endpoint and `response_format.type = json_schema`
with `strict = true`.

Runtime behavior:

1. Try strict JSON Schema mode.
2. If Groq returns a schema-generation `400`, retry with JSON Object Mode.
3. Validate with Pydantic.
4. Repair invalid non-critical LLM fields from the deterministic baseline with
   `LLM_FIELD_REPAIRED`.
5. If validation still fails, fall back to the deterministic parser with
   `LLM_EXTRACTION_FALLBACK`.

If the API key is absent, the request fails, or Pydantic validation rejects the response,
the workflow falls back to the deterministic parser and adds `LLM_EXTRACTION_FALLBACK`.

Automated unit tests use local provider doubles and do not call the real Groq API by default.

Completed:

- Real Groq provider integration.
- API workflow tests proving `use_llm=true` calls the configured provider and `use_llm=false`
  bypasses it.
- Strict schema extraction of `tower_characteristics`, including structure, leg count,
  base/top width, foundation, platforms, ladder, lightning rod, aviation light, and material.
- Deterministic fallback when key/API/validation fails.
- Controlled field repair with `LLM_FIELD_REPAIRED`.
- `extraction_report.json` per workflow.
- Adversarial deterministic extraction tests for French, English, slash azimuths, words for
  sector counts, missing values, and invalid heights.

Available with fallback:

- Groq may still generate invalid numeric arrays for azimuths on some prompts. Invalid
  non-critical fields are repaired from deterministic baseline and surfaced as warnings.

Known runtime result:

- A local smoke run with `use_llm=true` verified `llm_provider = groq:openai/gpt-oss-120b`,
  `llm_fallback_used = false`, real Blender generation, and passing geometry QA. The LLM response
  still required an explicit `LLM_FIELD_REPAIRED` warning for azimuth formatting, which is visible
  in the extraction and validation reports.
