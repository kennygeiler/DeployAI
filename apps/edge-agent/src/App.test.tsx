import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("Edge agent App shell", () => {
  it("renders the scaffold heading", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /DeployAI Edge Agent/i })).toBeInTheDocument();
  });
});
