import { useState, useRef, useEffect, useMemo } from "react";
import { useOptimisticValue } from "@/hooks/useOptimisticValue";

/* ------------------------------------------------------------------ */
/*  InlineEditText                                                     */
/* ------------------------------------------------------------------ */

interface InlineEditTextProps {
  value: string;
  onSave: (value: string) => Promise<void> | void;
  placeholder?: string;
  displayClassName?: string;
  inputClassName?: string;
  inputType?: "text" | "email";
}

export function InlineEditText({
  value,
  onSave,
  placeholder = "Click to edit",
  displayClassName = "text-surface-900",
  inputClassName,
  inputType = "text",
}: InlineEditTextProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setDraft(value); }, [value]);
  useEffect(() => { if (editing) inputRef.current?.focus(); }, [editing]);

  async function commit() {
    const trimmed = draft.trim();
    setEditing(false);
    if (trimmed === value) return;
    setSaving(true);
    try {
      await onSave(trimmed);
    } catch {
      setDraft(value);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        type={inputType}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); commit(); }
          if (e.key === "Escape") { setDraft(value); setEditing(false); }
        }}
        className={inputClassName ?? "w-full rounded border border-surface-200 px-2 py-1 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"}
      />
    );
  }

  return (
    <span
      onClick={() => setEditing(true)}
      className={`cursor-pointer rounded px-1 -mx-1 hover:bg-surface-100 transition-colors ${saving ? "opacity-50" : ""} ${displayClassName}`}
      title="Click to edit"
    >
      {value || <span className="text-surface-400 italic">{placeholder}</span>}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  InlineEditTextarea                                                 */
/* ------------------------------------------------------------------ */

interface InlineEditTextareaProps {
  value: string;
  onSave: (value: string) => Promise<void> | void;
  placeholder?: string;
  displayClassName?: string;
}

export function InlineEditTextarea({
  value,
  onSave,
  placeholder = "Click to add description",
  displayClassName = "text-sm text-surface-600 whitespace-pre-wrap",
}: InlineEditTextareaProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { setDraft(value); }, [value]);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);

  async function commit() {
    const trimmed = draft.trim();
    setEditing(false);
    if (trimmed === value) return;
    setSaving(true);
    try {
      await onSave(trimmed);
    } catch {
      setDraft(value);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <textarea
        ref={ref}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Escape") { setDraft(value); setEditing(false); }
        }}
        rows={4}
        className="w-full rounded border border-surface-200 px-2 py-1 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
      />
    );
  }

  return (
    <div
      onClick={() => setEditing(true)}
      className={`cursor-pointer rounded px-1 -mx-1 hover:bg-surface-100 transition-colors ${saving ? "opacity-50" : ""} ${displayClassName}`}
      title="Click to edit"
    >
      {value || <span className="text-surface-400 italic">{placeholder}</span>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  InlineEditSelect                                                   */
/* ------------------------------------------------------------------ */

interface InlineEditSelectProps {
  value: string;
  options: { value: string; label: string }[];
  onSave: (value: string) => Promise<void> | void;
  displayClassName?: string;
  renderDisplay?: (value: string, label: string) => React.ReactNode;
  compact?: boolean;
}

export function InlineEditSelect({
  value,
  options,
  onSave,
  displayClassName,
  renderDisplay,
  compact = false,
}: InlineEditSelectProps) {
  const [saving, setSaving] = useState(false);

  const currentOption = options.find((o) => o.value === value);
  const label = currentOption?.label ?? value;

  async function handleChange(newValue: string) {
    if (newValue === value) return;
    setSaving(true);
    try {
      await onSave(newValue);
    } catch {
      // revert handled by parent refetch
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`inline-flex items-center ${saving ? "opacity-50" : ""}`}>
      {renderDisplay ? (
        <label className="cursor-pointer relative">
          {renderDisplay(value, label)}
          <select
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            className="absolute inset-0 opacity-0 cursor-pointer"
          >
            {options.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
      ) : (
        <select
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          className={displayClassName ?? `rounded border border-surface-200 ${compact ? "px-1.5 py-0.5 text-xs" : "px-2 py-1 text-sm"} text-surface-600 focus:border-primary-300 focus:outline-none cursor-pointer`}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  InlineEditDate                                                     */
/* ------------------------------------------------------------------ */

interface InlineEditDateProps {
  value: string;
  onSave: (value: string) => Promise<void> | void;
  placeholder?: string;
  displayClassName?: string;
}

export function InlineEditDate({
  value,
  onSave,
  placeholder = "Set date",
  displayClassName = "text-surface-900",
}: InlineEditDateProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setDraft(value); }, [value]);
  useEffect(() => {
    if (editing) {
      inputRef.current?.showPicker?.();
      inputRef.current?.focus();
    }
  }, [editing]);

  function formatDisplay(dateStr: string): string {
    if (!dateStr) return "";
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short", day: "numeric", year: "numeric",
    });
  }

  async function commit(dateValue: string) {
    setEditing(false);
    if (dateValue === value) return;
    setSaving(true);
    try {
      await onSave(dateValue);
    } catch {
      setDraft(value);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="date"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => commit(draft)}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); commit(draft); }
          if (e.key === "Escape") { setDraft(value); setEditing(false); }
        }}
        className="rounded border border-surface-200 px-2 py-1 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
      />
    );
  }

  return (
    <span
      onClick={() => setEditing(true)}
      className={`cursor-pointer rounded px-1 -mx-1 hover:bg-surface-100 transition-colors inline-flex items-center ${saving ? "opacity-50" : ""}`}
      title="Click to edit"
    >
      <span className={displayClassName}>
        {value ? formatDisplay(value) : <span className="text-surface-400 italic">{placeholder}</span>}
      </span>
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  InlineEditLabels                                                   */
/* ------------------------------------------------------------------ */

interface InlineEditLabelsProps {
  labels: string[];
  onSave: (labels: string[]) => Promise<void> | void;
}

export function InlineEditLabels({ labels, onSave }: InlineEditLabelsProps) {
  const [input, setInput] = useState("");
  const [saving, setSaving] = useState(false);

  async function addLabel(value: string) {
    const trimmed = value.trim();
    if (!trimmed || labels.includes(trimmed)) return;
    setSaving(true);
    try {
      await onSave([...labels, trimmed]);
    } catch {
      // revert handled by parent refetch
    } finally {
      setSaving(false);
    }
  }

  async function removeLabel(label: string) {
    setSaving(true);
    try {
      await onSave(labels.filter((l) => l !== label));
    } catch {
      // revert handled by parent refetch
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${saving ? "opacity-50" : ""}`}>
      {labels.map((label) => (
        <span key={label} className="inline-flex items-center gap-1 rounded-full bg-surface-100 px-2.5 py-0.5 text-xs text-surface-600">
          {label}
          <button type="button" onClick={() => removeLabel(label)} className="text-surface-400 hover:text-surface-600">&times;</button>
        </span>
      ))}
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            addLabel(input);
            setInput("");
          }
        }}
        placeholder="Add label…"
        className="rounded border border-transparent px-2 py-0.5 text-xs text-surface-600 hover:border-surface-200 focus:border-primary-300 focus:outline-none w-24"
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  InlineEditAssignee                                                 */
/* ------------------------------------------------------------------ */

interface InlineEditAssigneeProps {
  value: string | null;
  members: { email: string; display_name: string | null }[];
  onSave: (email: string | null) => Promise<void> | void;
  compact?: boolean;
}

export function InlineEditAssignee({ value, members, onSave, compact = false }: InlineEditAssigneeProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState(false);
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

  const displayName = useMemo(() => {
    if (!value) return null;
    const m = members.find((m) => m.email === value);
    return m?.display_name || value;
  }, [value, members]);

  async function select(email: string | null) {
    setOpen(false);
    setSearch("");
    if (email === value) return;
    setSaving(true);
    try {
      await onSave(email);
    } catch {
      // revert handled by parent
    } finally {
      setSaving(false);
    }
  }

  return (
    <div ref={containerRef} className={`relative inline-block ${saving ? "opacity-50" : ""}`}>
      <span
        onClick={() => setOpen(!open)}
        className={`cursor-pointer rounded px-1 -mx-1 hover:bg-surface-100 transition-colors ${compact ? "text-xs text-surface-500" : "text-sm text-surface-900"}`}
        title="Click to change assignee"
      >
        {displayName ?? <span className="text-surface-400 italic">Unassigned</span>}
      </span>

      {open && (
        <div className="absolute z-50 mt-1 w-64 rounded-lg border border-surface-200 bg-white shadow-lg">
          <div className="p-2 border-b border-surface-100">
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search people…"
              className="w-full rounded border border-surface-200 px-2 py-1.5 text-sm focus:border-primary-400 focus:outline-none"
            />
          </div>
          <div className="max-h-48 overflow-y-auto py-1">
            {value && (
              <button
                onClick={() => select(null)}
                className="w-full px-3 py-2 text-left text-sm text-surface-500 hover:bg-surface-50 italic"
              >
                Unassign
              </button>
            )}
            {filtered.map((m) => (
              <button
                key={m.email}
                onClick={() => select(m.email)}
                className={`w-full px-3 py-2 text-left text-sm hover:bg-surface-50 flex flex-col ${m.email === value ? "bg-primary-50 text-primary-700" : "text-surface-700"}`}
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

/* ------------------------------------------------------------------ */
/*  InlineEditSingleSelect (for project picker etc.)                   */
/* ------------------------------------------------------------------ */

interface InlineEditSingleSelectProps {
  value: string | null;
  options: { value: string; label: string }[];
  onSave: (value: string | null) => Promise<void> | void;
  placeholder?: string;
  displayClassName?: string;
  allowClear?: boolean;
}

export function InlineEditSingleSelect({
  value,
  options,
  onSave,
  placeholder = "None",
  displayClassName = "text-sm text-surface-900",
  allowClear = true,
}: InlineEditSingleSelectProps) {
  const [saving, setSaving] = useState(false);

  async function handleChange(newValue: string) {
    const resolved = newValue === "__clear__" ? null : newValue;
    if (resolved === value) return;
    setSaving(true);
    try {
      await onSave(resolved);
    } catch {
      // revert handled by parent
    } finally {
      setSaving(false);
    }
  }

  return (
    <select
      value={value ?? "__clear__"}
      onChange={(e) => handleChange(e.target.value)}
      className={`cursor-pointer rounded border border-surface-200 px-2 py-1 text-sm focus:border-primary-300 focus:outline-none ${saving ? "opacity-50" : ""} ${displayClassName}`}
    >
      {allowClear && <option value="__clear__">{placeholder}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

/* ------------------------------------------------------------------ */
/*  InlineEditMultiSelect (for goals picker)                           */
/* ------------------------------------------------------------------ */

interface InlineEditMultiSelectProps {
  values: string[];
  options: { value: string; label: string }[];
  onSave: (values: string[]) => Promise<void> | void;
  placeholder?: string;
}

export function InlineEditMultiSelect({
  values,
  options,
  onSave,
  placeholder = "None",
}: InlineEditMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const { value: selected, setValue: setSelected, isPending, save } = useOptimisticValue(values);
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

  const selectedLabels = selected
    .map((v) => options.find((o) => o.value === v)?.label ?? v)
    .filter(Boolean);

  async function toggle(optValue: string) {
    const next = selected.includes(optValue)
      ? selected.filter((v) => v !== optValue)
      : [...selected, optValue];
    setSelected(next);
    try {
      await save(() => onSave(next));
    } catch {
      // useOptimisticValue reverts automatically on error
    }
  }

  return (
    <div ref={containerRef} className={`relative inline-block ${isPending ? "opacity-50" : ""}`}>
      <div
        onClick={() => setOpen(!open)}
        className="cursor-pointer rounded px-1 -mx-1 hover:bg-surface-100 transition-colors"
        title="Click to edit"
      >
        {selectedLabels.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {selectedLabels.map((label, i) => (
              <span key={selected[i]} className="rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-medium text-primary-700">
                {label}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-surface-400 italic text-sm">{placeholder}</span>
        )}
      </div>

      {open && (
        <div className="absolute z-50 mt-1 w-64 rounded-lg border border-surface-200 bg-white shadow-lg max-h-48 overflow-y-auto py-1">
          {options.map((o) => {
            const checked = selected.includes(o.value);
            return (
              <button
                key={o.value}
                onClick={() => toggle(o.value)}
                className={`w-full px-3 py-2 text-left text-sm hover:bg-surface-50 flex items-center gap-2 ${checked ? "text-primary-700 bg-primary-50" : "text-surface-700"}`}
              >
                <span className={`h-4 w-4 rounded border flex items-center justify-center text-xs ${checked ? "bg-primary-600 border-primary-600 text-white" : "border-surface-300"}`}>
                  {checked && "✓"}
                </span>
                {o.label}
              </button>
            );
          })}
          {options.length === 0 && (
            <div className="px-3 py-2 text-sm text-surface-400">No options available</div>
          )}
        </div>
      )}
    </div>
  );
}
