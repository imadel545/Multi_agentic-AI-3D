type JsonBlockProps = {
  value: unknown;
  empty?: string;
};

export function JsonBlock({ value, empty = "No data" }: JsonBlockProps) {
  if (value === undefined || value === null) {
    return <div className="empty-state">{empty}</div>;
  }
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}
