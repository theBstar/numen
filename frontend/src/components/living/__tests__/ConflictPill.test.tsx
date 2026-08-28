import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ConflictPill } from "../ConflictPill";

describe("ConflictPill", () => {
  it("renders source count", () => {
    render(<ConflictPill sourceCount={3} />);
    expect(screen.getByTestId("conflict-pill")).toHaveTextContent("3 sources");
  });

  it("calls onClick when clicked", async () => {
    const onClick = vi.fn();
    render(<ConflictPill sourceCount={2} onClick={onClick} />);
    await userEvent.click(screen.getByTestId("conflict-pill"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
