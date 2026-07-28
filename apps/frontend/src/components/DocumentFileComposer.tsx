import { FilePlus2, Files, Trash2, UploadCloud } from "lucide-react";
import { useMemo, useState, type ChangeEvent, type DragEvent } from "react";
import type { DocumentPackCapabilities } from "../api/schemas";

type DocumentFileComposerProps = {
  busy: boolean;
  capabilities: DocumentPackCapabilities | null;
  onSubmit: (files: File[]) => Promise<boolean>;
};

export function DocumentFileComposer({
  busy,
  capabilities,
  onSubmit
}: DocumentFileComposerProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const acceptedExtensions = useMemo(
    () => [".zip", ...(capabilities?.supported_extensions ?? [])].join(","),
    [capabilities?.supported_extensions]
  );

  const addFiles = (incoming: File[]) => {
    const merged = deduplicateFiles([...files, ...incoming]);
    const error = documentSelectionError(merged, capabilities);
    if (error) {
      setSelectionError(error);
      return;
    }
    setSelectionError(null);
    setFiles(merged);
  };

  const submit = async () => {
    const error = documentSelectionError(files, capabilities);
    if (error) {
      setSelectionError(error);
      return;
    }
    if (await onSubmit(files)) {
      setFiles([]);
      setSelectionError(null);
    }
  };

  return (
    <section className="document-composer" aria-label="Pièces jointes du cahier de charge">
      <label
        className={dragging ? "file-drop dragging" : "file-drop"}
        onDragEnter={() => setDragging(true)}
        onDragLeave={() => setDragging(false)}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event: DragEvent<HTMLLabelElement>) => {
          event.preventDefault();
          setDragging(false);
          addFiles(Array.from(event.dataTransfer.files));
        }}
      >
        <UploadCloud size={18} aria-hidden="true" />
        <span>
          {busy
            ? "Analyse locale en cours…"
            : "Déposez des PDF, images, plans, tableaux ou un ZIP"}
        </span>
        <small>Plusieurs fichiers peuvent être joints ensemble.</small>
        <input
          accept={acceptedExtensions}
          aria-label="Ajouter des pièces techniques"
          disabled={busy}
          multiple
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            addFiles(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
          type="file"
        />
      </label>
      {files.length ? (
        <div className="document-file-queue">
          <div>
            <Files size={16} aria-hidden="true" />
            <strong>{files.length} pièce(s) prête(s) à analyser</strong>
            <small>{formatFileSize(files.reduce((total, file) => total + file.size, 0))}</small>
          </div>
          <ul>
            {files.map((file) => (
              <li key={fileIdentity(file)}>
                <span>
                  <FilePlus2 size={14} aria-hidden="true" />
                  <span>{file.name}</span>
                </span>
                <small>{formatFileSize(file.size)}</small>
                <button
                  aria-label={`Retirer ${file.name}`}
                  disabled={busy}
                  onClick={() =>
                    setFiles((current) =>
                      current.filter((candidate) => fileIdentity(candidate) !== fileIdentity(file))
                    )
                  }
                  type="button"
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
          <button
            className="secondary-action"
            disabled={busy}
            onClick={() => void submit()}
            type="button"
          >
            {busy ? "Analyse en cours…" : `Analyser ${files.length} pièce(s)`}
          </button>
        </div>
      ) : null}
      {selectionError ? (
        <p className="inline-alert" role="alert">
          {selectionError}
        </p>
      ) : null}
    </section>
  );
}

export function documentSelectionError(
  files: Array<Pick<File, "name" | "size">>,
  capabilities: DocumentPackCapabilities | null
): string | null {
  if (!files.length) {
    return "Ajoutez au moins une pièce technique.";
  }
  const zipFiles = files.filter((file) => file.name.toLowerCase().endsWith(".zip"));
  if (zipFiles.length && files.length > 1) {
    return "Un ZIP doit être analysé seul. Retirez les autres fichiers ou décompressez le ZIP.";
  }
  const seenNames = new Set<string>();
  const duplicateName = files.find((file) => {
    const normalized = file.name.trim().toLocaleLowerCase();
    if (seenNames.has(normalized)) {
      return true;
    }
    seenNames.add(normalized);
    return false;
  });
  if (duplicateName) {
    return `Deux pièces portent le nom ${duplicateName.name}. Renommez-en une avant l’analyse.`;
  }
  const limits = capabilities?.limits;
  const maxCount = limits?.max_member_count;
  if (maxCount && files.length > maxCount) {
    return `Le cahier de charge dépasse la limite de ${maxCount} fichiers.`;
  }
  if (zipFiles.length === 1) {
    const maxZipSizeMb = limits?.max_zip_size_mb;
    if (maxZipSizeMb && zipFiles[0].size > maxZipSizeMb * 1024 * 1024) {
      return `Le ZIP dépasse la limite locale de ${maxZipSizeMb} Mo.`;
    }
    return null;
  }
  const maxMemberSizeMb = limits?.max_member_size_mb;
  const oversized = maxMemberSizeMb
    ? files.find((file) => file.size > maxMemberSizeMb * 1024 * 1024)
    : null;
  if (oversized) {
    return `${oversized.name} dépasse la limite de ${maxMemberSizeMb} Mo par fichier.`;
  }
  const maxTotalSizeMb = limits?.max_uncompressed_size_mb;
  const totalSize = files.reduce((total, file) => total + file.size, 0);
  if (maxTotalSizeMb && totalSize > maxTotalSizeMb * 1024 * 1024) {
    return `Les pièces dépassent la limite totale de ${maxTotalSizeMb} Mo.`;
  }
  return null;
}

function deduplicateFiles(files: File[]): File[] {
  return files.filter(
    (file, index, items) =>
      items.findIndex((candidate) => fileIdentity(candidate) === fileIdentity(file)) === index
  );
}

function fileIdentity(file: Pick<File, "name" | "size"> & Partial<Pick<File, "lastModified">>) {
  return `${file.name}:${file.size}:${file.lastModified ?? 0}`;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}
