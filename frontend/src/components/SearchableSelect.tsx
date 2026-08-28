import { useState, useEffect, useRef, useMemo } from "react";
import { ChevronDown, X } from "lucide-react";

interface SearchableSelectProps {
  value: string;
  onChange: (email: string) => void;
  members: { email: string; display_name: string | null }[];
  placeholder?: string;
  className?: string;
}

export function SearchableSelect({
  value,
  onChange,
  members,
  placeholder = "Select...",
  className = "",
}: SearchableSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const filtered = useMemo(() => {
    if (!search) return members;
    const q = search.toLowerCase();
    return members.filter(
      (m) => m.email.toLowerCase().includes(q) || (m.display_name?.toLowerCase().includes(q) ?? false),
    );
  }, [members, search]);

  const selected = useMemo(() => {
    if (!value) return null;
    return members.find((m) => m.email === value) ?? null;
  }, [value, members]);

  function select(email: string) {
    onChange(email);
    setOpen(false);
    setSearch("");
  }

  function clear(e: React.MouseEvent) {
    e.stopPropagation();
    onChange("");
    setOpen(false);
    setSearch("");
  }

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="mt-1 flex w-full items-center justify-between rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
      >
        {selected ? (
          <span className="flex items-center gap-2 min-w-0">
            <span className="truncate font-medium text-surface-900">
              {selected.display_name || selected.email}
            </span>
            {selected.display_name && (
              <span className="truncate text-xs text-surface-400">{selected.email}</span>
            )}
          </span>
        ) : (
          <span className="text-surface-400">{placeholder}</span>
        )}
        <span className="flex items-center gap-1 ml-2 shrink-0">
          {value && (
            <span
              role="button"
              tabIndex={-1}
              onClick={clear}
              className="text-surface-400 hover:text-surface-600"
            >
              <X size={14} />
            </span>
          )}
          <ChevronDown size={14} className="text-surface-400" />
        </span>
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-surface-200 bg-white shadow-lg">
          <div className="border-b border-surface-100 p-2">
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or email..."
              className="w-full rounded border border-surface-200 px-2 py-1.5 text-sm focus:border-primary-400 focus:outline-none"
            />
          </div>
          <div className="max-h-48 overflow-y-auto py-1">
            {filtered.map((m) => (
              <button
                key={m.email}
                type="button"
                onClick={() => select(m.email)}
                className={`flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-surface-50 ${
                  m.email === value ? "bg-primary-50 text-primary-700" : "text-surface-700"
                }`}
              >
                <span className="font-medium">{m.display_name || m.email}</span>
                {m.display_name && <span className="text-xs text-surface-400">{m.email}</span>}
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-2 text-sm text-surface-400">No people found</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
