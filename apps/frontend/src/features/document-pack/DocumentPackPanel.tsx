import { FileSearch, ShieldAlert } from "lucide-react";

import { useDocumentPack, useDocumentPacks } from "../../api/hooks";
import { Badge, StatusBadge } from "../../components/Badge";
import { JsonBlock } from "../../components/JsonBlock";
import { stringifyCompact } from "../../lib/format";
import { useStudioStore } from "../../stores/studioStore";

export function DocumentPackPanel() {
  const activePackId = useStudioStore((state) => state.activePackId);
  const setActivePackId = useStudioStore((state) => state.setActivePackId);
  const packQuery = useDocumentPack(activePackId);
  const packsQuery = useDocumentPacks();
  const pack = packQuery.data;

  return (
    <section className="dock-panel">
      <div className="panel-heading compact">
        <FileSearch size={16} />
        <h2>Documents</h2>
        <StatusBadge status={pack?.summary?.status ?? "no_pack"} />
      </div>

      <div className="pack-selector">
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
      </div>

      <div className="document-grid">
        <div className="document-list">
          {pack?.documents?.length ? (
            pack.documents.map((document) => (
              <article className="document-row" key={document.document_id}>
                <div>
                  <strong>{document.filename}</strong>
                  <p>{document.why_used_or_ignored || document.reason}</p>
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
            <div className="empty-state">Upload or select a pack to inspect documents.</div>
          )}
        </div>

        <div className="field-list">
          <h3>Extracted fields</h3>
          {pack?.extractions?.slice(0, 14).map((field) => (
            <article className="field-row" key={`${field.field}-${stringifyCompact(field.value)}`}>
              <div>
                <strong>{field.field}</strong>
                <p>{stringifyCompact(field.value)}</p>
              </div>
              <div className="row-badges">
                <StatusBadge status={field.status} />
                <span>{Math.round(field.confidence * 100)}%</span>
              </div>
            </article>
          )) ?? <div className="empty-state">No extracted fields loaded.</div>}
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
            <div className="empty-state">No blocking missing fields or conflicts.</div>
          )}
        </div>
      </div>

      <details className="technical-details">
        <summary>ProjectDesignSpec / QA / processing JSON</summary>
        <JsonBlock value={{ spec: pack?.spec, qa: pack?.qa, processing: pack?.processing }} />
      </details>
    </section>
  );
}
