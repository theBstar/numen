import { useState, useCallback, useRef } from "react";
import { Search, X } from "lucide-react";

interface WikiSearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function WikiSearchBar({ value, onChange, placeholder = "Search PRDs..." }: WikiSearchBarProps) {
  const [localValue, setLocalValue] = useState(value);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleChange = useCallback(
    (newValue: string) => {
      setLocalValue(newValue);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => onChange(newValue), 250);
    },
    [onChange],
  );

  const handleClear = useCallback(() => {
    setLocalValue("");
    onChange("");
  }, [onChange]);

  return (
    <div className="relative">
      <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-surface-400" />
      <input
        type="text"
        value={localValue}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-surface-200 bg-white py-1.5 pl-8 pr-8 text-sm text-surface-800 placeholder:text-surface-400 focus:border-primary-300 focus:outline-none focus:ring-1 focus:ring-primary-300"
      />
      {localValue && (
        <button
          onClick={handleClear}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-surface-400 hover:text-surface-600"
        >
          <X size={12} />
        </button>
      )}
    </div>
  );
}
