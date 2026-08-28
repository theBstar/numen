import { renderHook, act } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useOptimisticValue } from "../useOptimisticValue";

describe("useOptimisticValue", () => {
  it("reflects server value initially", () => {
    const { result } = renderHook(() => useOptimisticValue(["a", "b"]));
    expect(result.current.value).toEqual(["a", "b"]);
    expect(result.current.isPending).toBe(false);
  });

  it("setValue updates optimistically (immediate)", () => {
    const { result } = renderHook(() => useOptimisticValue(["a"]));
    act(() => {
      result.current.setValue(["a", "b"]);
    });
    expect(result.current.value).toEqual(["a", "b"]);
  });

  it("syncs from server when server content changes", () => {
    let serverVal = ["a"];
    const { result, rerender } = renderHook(() => useOptimisticValue(serverVal));
    expect(result.current.value).toEqual(["a"]);

    serverVal = ["a", "b"];
    rerender();
    expect(result.current.value).toEqual(["a", "b"]);
  });

  it("does NOT sync when server array has same content but new reference", () => {
    const { result, rerender } = renderHook(
      ({ val }) => useOptimisticValue(val),
      { initialProps: { val: ["a", "b"] } },
    );

    // Set optimistic value
    act(() => {
      result.current.setValue(["a", "b", "c"]);
    });
    expect(result.current.value).toEqual(["a", "b", "c"]);

    // Rerender with NEW array reference but SAME content as original server value
    rerender({ val: ["a", "b"] });

    // Optimistic value should persist because server content hasn't changed
    expect(result.current.value).toEqual(["a", "b", "c"]);
  });

  it("reverts on save error", async () => {
    const { result } = renderHook(() => useOptimisticValue(["a"]));

    act(() => {
      result.current.setValue(["a", "b"]);
    });
    expect(result.current.value).toEqual(["a", "b"]);

    // Save that fails
    await act(async () => {
      try {
        await result.current.save(() => Promise.reject(new Error("fail")));
      } catch {
        // expected
      }
    });

    // Should revert to server value
    expect(result.current.value).toEqual(["a"]);
    expect(result.current.isPending).toBe(false);
  });

  it("isPending is true during save", async () => {
    let resolveSave: () => void;
    const savePromise = new Promise<void>((resolve) => {
      resolveSave = resolve;
    });

    const { result } = renderHook(() => useOptimisticValue(["a"]));

    let saveComplete: Promise<void>;
    act(() => {
      result.current.setValue(["a", "b"]);
      saveComplete = result.current.save(() => savePromise);
    });

    // isPending should be true while save is in flight
    expect(result.current.isPending).toBe(true);

    await act(async () => {
      resolveSave!();
      await saveComplete!;
    });

    expect(result.current.isPending).toBe(false);
  });

  it("does not overwrite optimistic state while save is pending", async () => {
    let resolveSave: () => void;
    const savePromise = new Promise<void>((resolve) => {
      resolveSave = resolve;
    });

    const { result, rerender } = renderHook(
      ({ val }) => useOptimisticValue(val),
      { initialProps: { val: ["a"] } },
    );

    // Start optimistic update + save
    let saveComplete: Promise<void>;
    act(() => {
      result.current.setValue(["a", "b"]);
      saveComplete = result.current.save(() => savePromise);
    });

    expect(result.current.value).toEqual(["a", "b"]);

    // Parent re-renders with NEW server data (different content)
    // During pending save, optimistic value should still win
    rerender({ val: ["a", "x"] });
    expect(result.current.value).toEqual(["a", "b"]);

    // Complete save
    await act(async () => {
      resolveSave!();
      await saveComplete!;
    });

    expect(result.current.isPending).toBe(false);
  });

  it("works with primitive values (string)", () => {
    const { result, rerender } = renderHook(
      ({ val }) => useOptimisticValue(val),
      { initialProps: { val: "hello" } },
    );

    expect(result.current.value).toBe("hello");

    act(() => {
      result.current.setValue("world");
    });
    expect(result.current.value).toBe("world");

    // Same content, re-render shouldn't overwrite
    rerender({ val: "hello" });
    expect(result.current.value).toBe("world");

    // Different content should sync
    rerender({ val: "changed" });
    expect(result.current.value).toBe("changed");
  });
});
