import { Boxes, ClipboardCheck, GitCompare, History, PackageOpen } from "lucide-react";

import { artifactUrl, useAssetInventory, useStudioMutations, useVersions } from "../../api/hooks";
import type { WorkflowStatus } from "../../api/types";
import { Badge, StatusBadge } from "../../components/Badge";
import { JsonBlock } from "../../components/JsonBlock";
import { asPercent, shortId, stringifyCompact } from "../../lib/format";
import { type InspectorTab, useStudioStore } from "../../stores/studioStore";

type InspectorPanelProps = {
  workflow?: WorkflowStatus;
};

const tabs: Array<{ id: InspectorTab; label: string; icon: typeof ClipboardCheck }> = [
  { id: "qa", label: "QA", icon: ClipboardCheck },
  { id: "assets", label: "Assets", icon: Boxes },
  { id: "versions", label: "Versions", icon: History },
  { id: "diff", label: "Diff", icon: GitCompare },
  { id: "downloads", label: "Downloads", icon: PackageOpen },
];

export function InspectorPanel({ workflow }: InspectorPanelProps) {
  const activeTab = useStudioStore((state) => state.inspectorTab);
  const setTab = useStudioStore((state) => state.setInspectorTab);

  return (
    <aside className="inspector-panel">
      <div className="inspector-tabs">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              className={activeTab === tab.id ? "active" : ""}
              key={tab.id}
              type="button"
              onClick={() => setTab(tab.id)}
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>
      {activeTab === "qa" ? <QAPanel workflow={workflow} /> : null}
      {activeTab === "assets" ? <AssetPanel workflow={workflow} /> : null}
      {activeTab === "versions" ? <VersionsPanel workflow={workflow} /> : null}
      {activeTab === "diff" ? <DiffPanel workflow={workflow} /> : null}
      {activeTab === "downloads" ? <DownloadPanel workflow={workflow} /> : null}
    </aside>
  );
}

function QAPanel({ workflow }: InspectorPanelProps) {
  const gates = workflow?.quality_gates ?? [];
  return (
    <div className="inspector-content">
      <div className="metric-strip">
        <div>
          <span>QA score</span>
          <strong>{asPercent(workflow?.qa_score)}</strong>
        </div>
        <div>
          <span>Structural</span>
          <StatusBadge status={workflow?.structural_qa_passed ? "passed" : "unknown"} />
        </div>
        <div>
          <span>Preview</span>
          <StatusBadge
            status={
              workflow?.preview_inspection_summary?.preview_qa_passed === true
                ? "passed"
                : "unknown"
            }
          />
        </div>
      </div>
      <h3>Quality gates</h3>
      {gates.length ? (
        gates.map((gate, index) => (
          <article className="qa-row" key={`${stringifyCompact(gate.name)}-${index}`}>
            <div>
              <strong>{stringifyCompact(gate.name ?? gate.gate_name ?? `gate_${index}`)}</strong>
              <p>{stringifyCompact(gate.reason ?? gate.message ?? gate.status)}</p>
            </div>
            <StatusBadge status={gate.passed === true ? "passed" : "failed"} />
          </article>
        ))
      ) : (
        <div className="empty-state">No quality gates yet.</div>
      )}
      <h3>Warnings / errors</h3>
      {[...(workflow?.errors ?? []), ...(workflow?.warnings ?? [])].length ? (
        [...(workflow?.errors ?? []), ...(workflow?.warnings ?? [])].map((item, index) => (
          <article className="qa-row warning" key={`${stringifyCompact(item.code)}-${index}`}>
            <strong>{stringifyCompact(item.code ?? item.severity ?? "issue")}</strong>
            <p>{stringifyCompact(item.message ?? item)}</p>
          </article>
        ))
      ) : (
        <div className="empty-state">No warnings or errors exposed.</div>
      )}
      <details className="technical-details">
        <summary>QA summaries JSON</summary>
        <JsonBlock
          value={{
            glb: workflow?.glb_inspection_summary,
            geometry: workflow?.geometry_validation_summary,
            preview: workflow?.preview_inspection_summary,
            tower: workflow?.tower_validation,
            rf: workflow?.rf_validation,
          }}
        />
      </details>
    </div>
  );
}

function AssetPanel({ workflow }: InspectorPanelProps) {
  const inventory = useAssetInventory();
  const imports = workflow?.asset_imports ?? [];
  return (
    <div className="inspector-content">
      <div className="metric-strip">
        <div>
          <span>Inventory</span>
          <StatusBadge status={inventory.data?.status ?? "loading"} />
        </div>
        <div>
          <span>Real GLB</span>
          <strong>{inventory.data?.real_glb_asset_count ?? "n/a"}</strong>
        </div>
        <div>
          <span>Missing</span>
          <strong>{inventory.data?.missing_file_count ?? "n/a"}</strong>
        </div>
      </div>
      <h3>Current scene imports</h3>
      {imports.length ? (
        imports.map((record, index) => (
          <article className="asset-row" key={`${record.asset_id}-${index}`}>
            <div>
              <strong>{record.asset_id ?? "unknown_asset"}</strong>
              <p>{record.object_role ?? "scene object"}</p>
            </div>
            <div className="row-badges">
              <StatusBadge status={record.import_mode} />
              {record.warnings?.map((warning) => (
                <Badge key={warning} tone="warn">
                  {warning}
                </Badge>
              ))}
            </div>
          </article>
        ))
      ) : (
        <div className="empty-state">No scene asset import metadata yet.</div>
      )}
      <h3>Registry</h3>
      <div className="inventory-list">
        {inventory.data?.entries.map((entry) => (
          <article className="asset-row" key={entry.asset_id}>
            <div>
              <strong>{entry.asset_id}</strong>
              <p>
                {entry.type} · {entry.source} · {entry.license ?? "license n/a"}
              </p>
            </div>
            <div className="row-badges">
              <StatusBadge status={entry.asset_import_mode} />
              {entry.attribution_required ? <Badge tone="warn">attribution</Badge> : null}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function VersionsPanel({ workflow }: InspectorPanelProps) {
  const setSelectedVersionId = useStudioStore((state) => state.setSelectedVersionId);
  const selectedVersionId = useStudioStore((state) => state.selectedVersionId);
  const versions = useVersions(workflow?.workflow_id);
  const mutations = useStudioMutations(workflow?.workflow_id);

  return (
    <div className="inspector-content">
      <h3>Version history</h3>
      {versions.data?.length ? (
        versions.data.map((version) => (
          <article
            className={selectedVersionId === version.version_id ? "version-row active" : "version-row"}
            key={version.version_id}
          >
            <button type="button" onClick={() => setSelectedVersionId(version.version_id)}>
              <strong>{version.version_id}</strong>
              <span>{version.edit_description ?? "initial"}</span>
            </button>
            <div className="row-badges">
              <StatusBadge status={version.status ?? undefined} />
              <Badge tone={version.active ? "good" : "idle"}>{version.active ? "active" : "stored"}</Badge>
              <button
                type="button"
                disabled={version.active || mutations.rollback.isPending}
                onClick={() => mutations.rollback.mutate({ versionId: version.version_id })}
              >
                rollback
              </button>
            </div>
          </article>
        ))
      ) : (
        <div className="empty-state">No versions loaded.</div>
      )}
    </div>
  );
}

function DiffPanel({ workflow }: InspectorPanelProps) {
  const versions = useVersions(workflow?.workflow_id);
  const selectedVersionId = useStudioStore((state) => state.selectedVersionId);
  const selected = versions.data?.find((version) => version.version_id === selectedVersionId);
  return (
    <div className="inspector-content">
      <h3>Before / after diff</h3>
      <JsonBlock value={selected?.diff_summary ?? versions.data?.find((v) => v.active)?.diff_summary} />
    </div>
  );
}

function DownloadPanel({ workflow }: InspectorPanelProps) {
  const selectedVersionId = useStudioStore((state) => state.selectedVersionId);
  const names = [
    "glb",
    "preview",
    "scene_spec",
    "metadata",
    "qa_report",
    "geometry_validation",
    "quality_gates",
    "trace",
    "download",
  ];
  return (
    <div className="inspector-content">
      <h3>Download center</h3>
      <div className="download-grid">
        {names.map((name) => (
          <a
            key={name}
            href={artifactUrl(workflow?.workflow_id, name, selectedVersionId)}
            target="_blank"
            rel="noreferrer"
            aria-disabled={!workflow?.workflow_id}
          >
            {name}
          </a>
        ))}
      </div>
      <p className="hint">
        Links resolve through the backend artifact endpoint; missing files return a visible 404.
      </p>
      <p className="hint">Active workflow: {shortId(workflow?.workflow_id)}</p>
    </div>
  );
}
