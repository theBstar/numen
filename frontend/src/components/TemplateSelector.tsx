import { useTemplates } from "@/hooks/queries";

interface TemplateSelectorProps {
  onSelect: (templateId: string) => void;
}

export function TemplateSelector({ onSelect }: TemplateSelectorProps) {
  const { data } = useTemplates();
  const templates = data?.items ?? [];

  if (templates.length === 0) return null;

  return (
    <div>
      <label className="block text-sm font-medium text-surface-700">
        Template
      </label>
      <select
        onChange={(e) => {
          if (e.target.value) onSelect(e.target.value);
        }}
        className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        defaultValue=""
      >
        <option value="">Start from scratch</option>
        {templates.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
            {t.description ? ` - ${t.description}` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
