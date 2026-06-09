import {
  Boxes,
  ClipboardCheck,
  Download,
  GitCompare,
  History,
  Info,
  PackageOpen,
} from "lucide-react";

import { artifactUrl, useAssetInventory, useStudioMutations, useVersions } from "../../api/hooks";
import type { AssetImportRecord, WorkflowStatus } from "../../api/types";
import { Badge, StatusBadge } from "../../components/Badge";
import { JsonBlock } from "../../components/JsonBlock";
import { EmptyState, MetricCard, PanelShell, WarningCard } from "../../components/Primitives";
import { asPercent, shortId, stringifyCompact } from "../../lib/format";
import { presentIssues } from "../../lib/issuePresenter";
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
  const selectedObject = useStudioStore((state) => state.selectedObject);

  return (
    <PanelShell
      className="inspector-panel"
      title="Smart Inspector"
      eyebrow={selectedObject ? `Selected · ${selectedObject}` : "workflow context"}
      icon={<Info size={18} />}
    >
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
      {activeTab === "assets" ? <AssetPanel workflow={workflow} selectedObject={selectedObject} /> : null}
      {activeTab === "versions" ? <VersionsPanel workflow={workflow} /> : null}
      {activeTab === "diff" ? <DiffPanel workflow={workflow} /> : null}
      {activeTab === "downloads" ? <DownloadPanel workflow={workflow} /> : null}
    </PanelShell>
  );
}

function QAPanel({ workflow }: InspectorPanelProps) {
  const gates = workflow?.quality_gates ?? [];
  const issues = presentIssues([...(workflow?.errors ?? []), ...(workflow?.warnings ?? [])]);
  const blockingCount = issues.filter((issue) => issue.severity === "error").length;
  const warningCount = issues.filter((issue) => issue.severity !== "error").length;
  const geometryStatus = stringifyCompact(workflow?.geometry_validation_summary?.status ?? "unknown");
  return (
    <div className="inspector-content">
      <div className="metric-strip product-metrics">
        <MetricCard label="QA score" value={asPercent(workflow?.qa_score)} tone={blockingCount ? "bad" : "good"} />
        <MetricCard
          label="Blocking"
          value={blockingCount}
          detail="errors"
          tone={blockingCount ? "bad" : "good"}
        />
        <MetricCard
          label="Warnings"
          value={warningCount}
          detail="visible"
          tone={warningCount ? "warn" : "good"}
        />
      </div>

      <section className="qa-check-summary">
        <h3>Verified by backend</h3>
        <div className="check-grid">
          <CheckItem label="SceneSpec" passed={gatePassed(gates, "scene")} />
          <CheckItem label="Structural QA" passed={workflow?.structural_qa_passed === true} />
          <CheckItem label="Geometry" passed={geometryStatus === "passed"} />
          <CheckItem
            label="Preview"
            passed={workflow?.preview_inspection_summary?.preview_qa_passed === true}
          />
          <CheckItem
            label="Asset imports"
            passed={Number(workflow?.asset_import_summary?.missing_file_count ?? 0) === 0}
          />
        </div>
      </section>

      <section className="quality-gate-list">
        <h3>Quality gates</h3>
        {gates.length ? (
          gates.map((gate, index) => (
            <article className="qa-row" key={`${stringifyCompact(gate.name)}-${index}`}>
              <div>
                <strong>{humanGateName(gate.name ?? gate.gate_name ?? `gate_${index}`)}</strong>
                <p>{stringifyCompact(gate.reason ?? gate.message ?? gate.status ?? "Validated")}</p>
              </div>
              <StatusBadge status={gate.passed === true ? "passed" : "failed"} />
            </article>
          ))
        ) : (
          <EmptyState
            title="No gates yet"
            description="Generate a design to see blocking quality gates and validation status."
          />
        )}
      </section>

      <section className="issue-section">
        <h3>Warnings and errors</h3>
        {issues.length ? (
          <div className="issue-list">
            {issues.slice(0, 8).map((issue, index) => (
              <WarningCard issue={issue} key={`${issue.code}-${index}`} />
            ))}
          </div>
        ) : (
          <EmptyState title="No visible issue" description="No warnings or errors were exposed by the backend." />
        )}
      </section>

      <details className="technical-details">
        <summary>QA reports JSON</summary>
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

function AssetPanel({
  workflow,
  selectedObject,
}: InspectorPanelProps & {
  selectedObject?: string;
}) {
  const inventory = useAssetInventory();
  const imports = workflow?.asset_imports ?? [];
  const selectedImport = imports.find(
    (record) => record.object_name === selectedObject || record.asset_id === selectedObject,
  );
  return (
    <div className="inspector-content">
      <div className="metric-strip product-metrics">
        <MetricCard label="Real GLB" value={inventory.data?.real_glb_asset_count ?? "n/a"} tone="good" />
        <MetricCard label="Missing" value={inventory.data?.missing_file_count ?? "n/a"} tone="warn" />
        <MetricCard
          label="Fallback"
          value={inventory.data?.procedural_fallback_count ?? "n/a"}
          tone={inventory.data?.procedural_fallback_count ? "warn" : "good"}
        />
      </div>

      <section>
        <h3>Selected object</h3>
        {selectedImport ? (
          <AssetRecord record={selectedImport} />
        ) : (
          <EmptyState
            title="No object selected"
            description="Click an imported object in the viewer rail to inspect import mode and license."
          />
        )}
      </section>

      <section>
        <h3>Current scene imports</h3>
        {imports.length ? (
          <div className="asset-card-list">
            {imports.map((record, index) => (
              <AssetRecord record={record} key={`${record.asset_id}-${record.object_name}-${index}`} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="No import metadata"
            description="The selected workflow has not exposed asset import metadata yet."
          />
        )}
      </section>

      <section>
        <h3>Inventory readiness</h3>
        <div className="inventory-list">
          {inventory.data?.entries.slice(0, 18).map((entry) => (
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
          )) ?? (
            <EmptyState
              title="Inventory unavailable"
              description="The asset inventory endpoint has not returned data yet."
            />
          )}
        </div>
      </section>
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
        <div className="version-list">
          {versions.data.map((version) => (
            <article
              className={selectedVersionId === version.version_id || version.active ? "version-row active" : "version-row"}
              key={version.version_id}
            >
              <button type="button" onClick={() => setSelectedVersionId(version.version_id)}>
                <strong>{version.version_id}</strong>
                <span>{version.edit_description ?? "Initial design"}</span>
                <small>
                  QA {asPercent(version.qa_score)} · {version.generation_mode ?? "mode n/a"}
                </small>
              </button>
              <div className="row-badges">
                <StatusBadge status={version.status ?? undefined} />
                <Badge tone={version.active ? "good" : "idle"}>{version.active ? "active" : "stored"}</Badge>
                <button
                  type="button"
                  disabled={version.active || mutations.rollback.isPending}
                  onClick={() => {
                    if (window.confirm(`Rollback to version ${version.version_id}?`)) {
                      mutations.rollback.mutate({ versionId: version.version_id });
                    }
                  }}
                >
                  rollback
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No versions loaded"
          description="Generate a design or apply a validated edit to create version history."
        />
      )}
    </div>
  );
}

function DiffPanel({ workflow }: InspectorPanelProps) {
  const versions = useVersions(workflow?.workflow_id);
  const selectedVersionId = useStudioStore((state) => state.selectedVersionId);
  const selected = versions.data?.find((version) => version.version_id === selectedVersionId);
  const active = versions.data?.find((version) => version.active);
  const diff = selected?.diff_summary ?? active?.diff_summary;
  return (
    <div className="inspector-content">
      <h3>Before / after diff</h3>
      {diff ? (
        <JsonBlock value={diff} />
      ) : (
        <EmptyState
          title="No diff for active version"
          description="Apply a validated prompt edit to compare the new SceneSpec against its parent."
        />
      )}
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
            <Download size={14} />
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

function CheckItem({ label, passed }: { label: string; passed: boolean }) {
  return (
    <article className={passed ? "check-item passed" : "check-item warning"}>
      <span>{label}</span>
      <StatusBadge status={passed ? "passed" : "check"} />
    </article>
  );
}

function AssetRecord({ record }: { record: AssetImportRecord }) {
  return (
    <article className="asset-row asset-record">
      <div>
        <strong>{record.asset_id ?? "unknown_asset"}</strong>
        <p>{stringifyCompact(record.object_name ?? record.object_role ?? "scene object")}</p>
        {record.asset_metadata && typeof record.asset_metadata === "object" ? (
          <small>{stringifyCompact((record.asset_metadata as Record<string, unknown>).license)}</small>
        ) : null}
      </div>
      <div className="row-badges">
        <StatusBadge status={record.import_mode} />
        {record.asset_file_exists === false ? <Badge tone="bad">missing file</Badge> : null}
        {record.warnings?.map((warning) => (
          <Badge key={warning} tone="warn">
            {warning.replaceAll("_", " ").toLowerCase()}
          </Badge>
        ))}
      </div>
    </article>
  );
}

function gatePassed(gates: Array<Record<string, unknown>>, needle: string) {
  return gates.some((gate) => {
    const name = stringifyCompact(gate.name ?? gate.gate_name).toLowerCase();
    return name.includes(needle) && gate.passed === true;
  });
}

function humanGateName(value: unknown) {
  return stringifyCompact(value)
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
