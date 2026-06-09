# Groq Structured Extraction

Groq extraction is isolated in `core/llm/groq.py` and routed through
`core/agents/requirement_extractor.py`.

Scene edits also use Groq through `core/agents/scene_edit_agent.py` when a key is configured.
The edit agent can only return a typed `ScenePatch`; it never generates Blender Python code.

Document-pack ingestion can invoke a separate bounded Groq extractor in
`core/document_pack/groq_extractor.py` when a Groq client/key is configured. This extractor is not
the requirements extractor; it accepts only selected document chunks and must return source-backed
field candidates.

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
- Groq-backed prompt editing with deterministic fallback and visible `edit_llm_provider` /
  `edit_llm_fallback_used` fields in `scene_patch.json` and the edit API response.
- Bounded document-pack extraction over selected high/medium text/table/OCR/CAD chunks.
- Groq document-pack output requires strict JSON fields with `field`, `value`, `confidence`,
  `document_id`, `page`, and `evidence`.
- Groq document-pack fields are rejected when evidence is empty, not present in the selected chunk,
  tied to an invalid document, or outside supported field prefixes.
- Adversarial deterministic extraction tests for French, English, slash azimuths, words for
  sector counts, missing values, and invalid heights.

Available with fallback:

- Groq may still generate invalid numeric arrays for azimuths on some prompts. Invalid
  non-critical fields are repaired from deterministic baseline and surfaced as warnings.
- Groq edit patching may return invalid/empty operations. The system falls back to deterministic
  patch parsing, then validates all paths and values through Pydantic and SceneSpec validation.
- Document-pack Groq extraction is visible in `source_mode`, `llm_provider`,
  `llm_fallback_used`, `groq_rejected_fields`, QA, and processing reports. It cannot bypass
  deterministic conflicts, user corrections, `ProjectDesignSpec` contracts, or QA.

Known runtime result:

- A local smoke run with `use_llm=true` verified `llm_provider = groq:openai/gpt-oss-120b`,
  `llm_fallback_used = false`, real Blender generation, and passing geometry QA. The LLM response
  still required an explicit `LLM_FIELD_REPAIRED` warning for azimuth formatting, which is visible
  in the extraction and validation reports.
