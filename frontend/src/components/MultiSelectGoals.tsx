import { useState, useEffect, useRef } from "react";
import { ChevronDown, X } from "lucide-react";

interface MultiSelectGoalsProps {
  value: string[];
  onChange: (ids: string[]) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  className?: string;
}

export function MultiSelectGoals({
  value,
  onChange,
  options,
  placeholder = "Link to goals...",
  className = "",
}: MultiSelectGoalsProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const selectedLabels = value
    .map((v) => ({ id: v, label: options.find((o) => o.value === v)?.label ?? v }))
    .filter((s) => s.label);

  function toggle(optValue: string) {
    const next = value.includes(optValue)
      ? value.filter((v) => v !== optValue)
      : [...value, optValue];
    onChange(next);
  }

  function remove(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    onChange(value.filter((v) => v !== id));
  }

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="mt-1 flex w-full items-center justify-between rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100 min-h-[38px]"
      >
        {selectedLabels.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {selectedLabels.map((s) => (
              <span
                key={s.id}
                className="inline-flex items-center gap-1 rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-medium text-primary-700"
              >
                {s.label}
                <span
                  role="button"
                  tabIndex={-1}
                  onClick={(e) => remove(s.id, e)}
                  className="text-primary-400 hover:text-primary-600"
                >
                  <X size={12} />
                </span>
              </span>
            ))}
          </div>
        ) : (
          <span className="text-surface-400">{placeholder}</span>
        )}
        <ChevronDown size={14} className="ml-2 shrink-0 text-surface-400" />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-surface-200 bg-white shadow-lg max-h-48 overflow-y-auto py-1">
          {options.map((o) => {
            const checked = value.includes(o.value);
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => toggle(o.value)}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-50 ${
                  checked ? "bg-primary-50 text-primary-700" : "text-surface-700"
                }`}
              >
                <span
                  className={`flex h-4 w-4 items-center justify-center rounded border text-xs ${
                    checked ? "border-primary-600 bg-primary-600 text-white" : "border-surface-300"
                  }`}
                >
                  {checked && "\u2713"}
                </span>
                {o.label}
              </button>
            );
          })}
          {options.length === 0 && (
            <div className="px-3 py-2 text-sm text-surface-400">No goals available</div>
          )}
        </div>
      )}
    </div>
  );
}
