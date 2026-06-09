import { FileSearch, Layers, ShieldAlert, WandSparkles } from "lucide-react";
import { useState } from "react";

import { useDocumentPack, useDocumentPacks, useStudioMutations } from "../../api/hooks";
import { Badge, StatusBadge } from "../../components/Badge";
import { ActionButton, EmptyState, MetricCard } from "../../components/Primitives";
import { stringifyCompact } from "../../lib/format";
import { useStudioStore } from "../../stores/studioStore";

export function DocumentPackPanel() {
  const activePackId = useStudioStore((state) => state.activePackId);
  const setActivePackId = useStudioStore((state) => state.setActivePackId);
  const setActiveWorkflowId = useStudioStore((state) => state.setActiveWorkflowId);
  const packQuery = useDocumentPack(activePackId);
  const packsQuery = useDocumentPacks();
  const mutations = useStudioMutations(undefined, activePackId);
  const pack = packQuery.data;
  const [correctionField, setCorrectionField] = useState("");
  const [correctionValue, setCorrectionValue] = useState("");

  const generateFromPack = async () => {
    if (!activePackId) return;
    const response = await mutations.generateFromPack.mutateAsync();
    setActiveWorkflowId(response.workflow_id);
  };

  const applyCorrection = async () => {
    if (!correctionField.trim() || !correctionValue.trim()) return;
    await mutations.applyCorrection.mutateAsync({
      field: correctionField,
      value: correctionValue,
      reason: "Frontend correction before design generation",
    });
    setCorrectionField("");
    setCorrectionValue("");
  };

  return (
    <section className="dock-panel document-workspace">
      <div className="panel-heading compact">
        <FileSearch size={16} />
        <h2>Document Intelligence</h2>
        <StatusBadge status={pack?.summary?.status ?? "no_pack"} />
      </div>

      <div className="document-toolbar">
        <select
          value={activePackId ?? ""}
          onChange={(event) => setActivePackId(event.target.value || undefined)}
        >
          <option value="">Select document pack</option>
          {packsQuery.data?.map((packItem) => (
            <option key={packItem.pack_id} value={packItem.pack_id}>
              {packItem.pack_id} · {packItem.document_count} docs · QA {packItem.qa_score ?? "n/a"}
            </option>
          ))}
        </select>
        <ActionButton
          onClick={generateFromPack}
          disabled={!activePackId || !pack?.summary?.can_generate_design || mutations.generateFromPack.isPending}
        >
          <WandSparkles size={15} />
          Generate from pack
        </ActionButton>
      </div>

      {!activePackId ? (
        <EmptyState
          title="Upload APD / PDF / DXF / ZIP to generate a 3D design"
          description="Le backend peut classifier les documents, extraire les champs utiles, signaler les conflits et produire un design depuis ProjectDesignSpec."
        />
      ) : null}

      {pack?.summary ? (
        <div className="document-metrics">
          <MetricCard label="Documents" value={pack.summary.document_count} tone="idle" />
          <MetricCard label="High priority" value={pack.summary.high_priority_count} tone="good" />
          <MetricCard
            label="Missing"
            value={pack.summary.missing_blocking_count}
            tone={pack.summary.missing_blocking_count ? "bad" : "good"}
          />
          <MetricCard
            label="Conflicts"
            value={pack.summary.conflict_count}
            tone={pack.summary.conflict_count ? "warn" : "good"}
          />
        </div>
      ) : null}

      <div className="document-grid">
        <div className="document-list">
          <h3>Documents</h3>
          {pack?.documents?.length ? (
            pack.documents.map((document) => (
              <article className="document-row" key={document.document_id}>
                <div>
                  <strong>{document.filename}</strong>
                  <p>{document.why_used_or_ignored || document.reason}</p>
                  <small>
                    {document.processing_tools.join(", ") || "tool n/a"} · {document.extractability}
                  </small>
                </div>
                <div className="row-badges">
                  <Badge tone={document.used_for_design ? "good" : "idle"}>
                    {document.category}
                  </Badge>
                  <StatusBadge status={document.extraction_status} />
                  <span>{Math.round(document.relevance_score * 100)}%</span>
                </div>
              </article>
            ))
          ) : (
            <EmptyState
              title="No document selected"
              description="Select a pack to inspect PDFs, OCR output, DXF layers and extraction status."
            />
          )}
        </div>

        <div className="field-list">
          <h3>
            <Layers size={15} />
            Extracted fields
          </h3>
          {pack?.extractions?.length ? (
            pack.extractions.slice(0, 18).map((field) => (
              <article className="field-row" key={`${field.field}-${stringifyCompact(field.value)}`}>
                <div>
                  <strong>{field.field}</strong>
                  <p>{stringifyCompact(field.value)}</p>
                  <small>{sourceLabel(field.sources)}</small>
                </div>
                <div className="row-badges">
                  <StatusBadge status={field.status} />
                  <span>{Math.round(field.confidence * 100)}%</span>
                </div>
              </article>
            ))
          ) : (
            <EmptyState
              title="No extracted fields loaded"
              description="The selected pack has not returned extraction candidates yet."
            />
          )}
        </div>

        <div className="risk-list">
          <h3>
            <ShieldAlert size={15} />
            Missing / conflicts
          </h3>
          {[...(pack?.missing ?? []), ...(pack?.conflicts ?? [])].length ? (
            [...(pack?.missing ?? []), ...(pack?.conflicts ?? [])].map((item) => (
              <article className="field-row warning" key={`${item.field}-${item.status}`}>
                <div>
                  <strong>{item.field}</strong>
                  <p>{item.reason ?? stringifyCompact(item.values ?? item.value)}</p>
                </div>
                <StatusBadge status={item.severity ?? item.status} />
              </article>
            ))
          ) : (
            <EmptyState
              title="No blocking issue"
              description="No missing blocking field or unresolved conflict was exposed."
            />
          )}

          <div className="correction-card">
            <strong>Correction rapide</strong>
            <input
              placeholder="field, e.g. tower_height_m"
              value={correctionField}
              onChange={(event) => setCorrectionField(event.target.value)}
            />
            <input
              placeholder="correct value"
              value={correctionValue}
              onChange={(event) => setCorrectionValue(event.target.value)}
            />
            <ActionButton
              variant="secondary"
              onClick={applyCorrection}
              disabled={!activePackId || mutations.applyCorrection.isPending}
            >
              Apply correction
            </ActionButton>
          </div>
        </div>
      </div>
    </section>
  );
}

function sourceLabel(sources?: Array<Record<string, unknown>>) {
  const first = sources?.[0];
  if (!first) return "source n/a";
  const file = first.filename ?? first.document_id ?? "document";
  const page = first.page ? `p.${first.page}` : undefined;
  const layer = first.layer ? `layer ${first.layer}` : undefined;
  return [file, page, layer].filter(Boolean).join(" · ");
}
