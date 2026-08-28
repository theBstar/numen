import { useState, useRef, useCallback } from "react";

/**
 * Default deep equality check for arrays of primitives (string[], number[]).
 * Sorts copies before comparing to handle order-independent equality.
 */
function arraysEqual(a: unknown[], b: unknown[]): boolean {
  if (a.length !== b.length) return false;
  const sa = [...a].sort();
  const sb = [...b].sort();
  return sa.every((v, i) => v === sb[i]);
}

function defaultIsEqual<T>(a: T, b: T): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) return arraysEqual(a, b);
  return false;
}

/**
 * Reusable optimistic state hook for inline editing.
 *
 * Solves the problem where a parent re-renders with a new array/object
 * reference (same content) and overwrites optimistic state. Uses deep
 * comparison to only sync from server when the content actually changes.
 *
 * Usage:
 *   const opt = useOptimisticValue(serverValues);
 *   // opt.value - current value (optimistic or server)
 *   // opt.setValue(next) - update optimistically (immediate)
 *   // opt.save(async () => api.update(next)) - persist; reverts on error
 *   // opt.isPending - true while save is in flight
 */
export function useOptimisticValue<T>(
  serverValue: T,
  isEqual?: (a: T, b: T) => boolean,
) {
  const eq = isEqual ?? defaultIsEqual;
  const [optimistic, setOptimistic] = useState(serverValue);
  const [isPending, setIsPending] = useState(false);
  const serverRef = useRef(serverValue);

  // Sync from server only when content actually changes
  if (!eq(serverRef.current, serverValue)) {
    serverRef.current = serverValue;
    if (!isPending) {
      setOptimistic(serverValue);
    }
  }

  const setValue = useCallback((v: T) => {
    setOptimistic(v);
  }, []);

  const save = useCallback(
    async (saveFn: () => Promise<void> | void) => {
      setIsPending(true);
      try {
        await saveFn();
      } catch (err) {
        setOptimistic(serverRef.current);
        throw err;
      } finally {
        setIsPending(false);
      }
    },
    [],
  );

  return { value: optimistic, setValue, isPending, save };
}
