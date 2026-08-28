import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { InlineEditMultiSelect } from "../InlineEdit";

const options = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

/** Get the dropdown list element (the absolute-positioned div with options). */
function getDropdown() {
  // The dropdown is the element with role-like class; find via the checkbox marker
  const buttons = screen.getAllByRole("button");
  // Dropdown buttons have the checkbox span inside them
  return buttons.filter((b) => b.querySelector("span.h-4"));
}

describe("InlineEditMultiSelect", () => {
  it("renders current values as pills", () => {
    render(
      <InlineEditMultiSelect values={["a", "b"]} options={options} onSave={vi.fn()} />,
    );
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.queryByText("Gamma")).not.toBeInTheDocument();
  });

  it("shows placeholder when no values", () => {
    render(
      <InlineEditMultiSelect values={[]} options={options} onSave={vi.fn()} placeholder="Pick items" />,
    );
    expect(screen.getByText("Pick items")).toBeInTheDocument();
  });

  it("clicking checkbox immediately toggles visual state (optimistic)", async () => {
    const user = userEvent.setup();
    // onSave never resolves - simulates slow network
    const onSave = vi.fn(() => new Promise<void>(() => {}));

    render(
      <InlineEditMultiSelect values={["a"]} options={options} onSave={onSave} />,
    );

    // Open dropdown by clicking the pills/placeholder area
    await user.click(screen.getByTitle("Click to edit"));

    // Find the Gamma button in the dropdown (it's a button with checkbox span)
    const dropdownButtons = getDropdown();
    const gammaBtn = dropdownButtons.find((b) => b.textContent?.includes("Gamma"))!;
    expect(gammaBtn).toBeTruthy();

    // Click "Gamma" to add it
    await user.click(gammaBtn);

    // Should immediately show as checked (optimistic) - look for it in the pills
    const pills = screen.getAllByText("Gamma");
    // One is in pills area, potentially another in dropdown
    expect(pills.length).toBeGreaterThanOrEqual(1);

    // The pill with the primary-50 class means it's in the selected pills
    const pill = pills.find((el) =>
      el.className.includes("rounded-full"),
    );
    expect(pill).toBeTruthy();

    // onSave should have been called with new values
    expect(onSave).toHaveBeenCalledWith(["a", "c"]);
  });

  it("on save error, value reverts", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(() => Promise.reject(new Error("fail")));

    render(
      <InlineEditMultiSelect values={["a"]} options={options} onSave={onSave} />,
    );

    // Open dropdown
    await user.click(screen.getByTitle("Click to edit"));

    // Find and click Beta button in dropdown
    const dropdownButtons = getDropdown();
    const betaBtn = dropdownButtons.find((b) => b.textContent?.includes("Beta"))!;
    await user.click(betaBtn);

    // After error, Beta should revert to unchecked in the dropdown
    // The dropdown button should have surface-700 class (unchecked)
    expect(betaBtn.className).toContain("text-surface-700");
  });

  it("new array reference with same content does not reset state", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(() => new Promise<void>(() => {}));

    const { rerender } = render(
      <InlineEditMultiSelect values={["a"]} options={options} onSave={onSave} />,
    );

    // Open dropdown and add "Beta"
    await user.click(screen.getByTitle("Click to edit"));
    const dropdownButtons = getDropdown();
    const betaBtn = dropdownButtons.find((b) => b.textContent?.includes("Beta"))!;
    await user.click(betaBtn);

    // Parent re-renders with new array ref but same content ["a"]
    rerender(
      <InlineEditMultiSelect values={["a"]} options={options} onSave={onSave} />,
    );

    // Optimistic state (["a", "b"]) should persist - Beta should appear in pills
    const betaElements = screen.getAllByText("Beta");
    const betaPill = betaElements.find((el) =>
      el.className.includes("rounded-full"),
    );
    expect(betaPill).toBeTruthy();
  });
});
