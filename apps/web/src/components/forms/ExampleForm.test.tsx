import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ExampleForm, type ExampleFormValues } from "./ExampleForm";

describe("ExampleForm", () => {
  function setup() {
    const onSubmit = vi.fn<(values: ExampleFormValues) => void>();
    const user = userEvent.setup();
    render(<ExampleForm onSubmit={onSubmit} />);
    const emailInput = screen.getByRole("textbox", { name: /email/i });
    const messageInput = screen.getByRole("textbox", { name: /message/i });
    const submit = screen.getByRole("button", { name: /submit/i });
    return { user, onSubmit, emailInput, messageInput, submit };
  }

  it("submits the collected values when every field is valid", async () => {
    const { user, onSubmit, emailInput, messageInput, submit } = setup();

    await user.type(emailInput, "citizen@example.gov");
    await user.type(messageInput, "Please acknowledge receipt of the FOIA packet.");
    await user.click(submit);

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0]?.[0]).toEqual({
      email: "citizen@example.gov",
      message: "Please acknowledge receipt of the FOIA packet.",
    });
  });

  it("surfaces a required-field error and marks the textarea invalid on empty submit", async () => {
    const { user, onSubmit, emailInput, submit } = setup();

    await user.type(emailInput, "citizen@example.gov");
    await user.click(submit);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findByText(/message is required/i)).toBeInTheDocument();
    const messageInput = screen.getByRole("textbox", { name: /message/i });
    expect(messageInput).toHaveAttribute("aria-invalid", "true");
    expect(messageInput).toHaveAccessibleDescription(/message is required/i);
  });

  it("rejects whitespace-only message content via schema.trim()", async () => {
    const { user, onSubmit, emailInput, messageInput, submit } = setup();

    await user.type(emailInput, "citizen@example.gov");
    await user.type(messageInput, "     ");
    await user.click(submit);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findByText(/message is required/i)).toBeInTheDocument();
  });

  it("reports 'Email is required' (not the format message) when email is blank", async () => {
    const { user, onSubmit, messageInput, submit } = setup();

    await user.type(messageInput, "Context for the review.");
    await user.click(submit);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    expect(screen.queryByText(/enter a valid email/i)).not.toBeInTheDocument();
  });

  it("reports format errors on blur without submitting", async () => {
    const { user, onSubmit, emailInput, messageInput } = setup();

    await user.type(emailInput, "not-an-email");
    await user.click(messageInput);

    expect(await screen.findByText(/enter a valid email/i)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
    expect(emailInput).toHaveAttribute("aria-invalid", "true");
  });

  it("submits the form when Cmd+Enter is pressed inside the form", async () => {
    const { user, onSubmit, emailInput, messageInput } = setup();

    await user.type(emailInput, "citizen@example.gov");
    await user.type(messageInput, "Filed under FOIA request #482.");
    messageInput.focus();
    await user.keyboard("{Meta>}{Enter}{/Meta}");

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0]?.[0]).toEqual({
      email: "citizen@example.gov",
      message: "Filed under FOIA request #482.",
    });
  });

  it("flips aria-invalid and exposes the error via aria-describedby, then clears it after correction", async () => {
    const { user, emailInput, messageInput } = setup();

    expect(emailInput).toHaveAttribute("aria-invalid", "false");

    await user.type(emailInput, "not-an-email");
    await user.click(messageInput);

    expect(emailInput).toHaveAttribute("aria-invalid", "true");
    expect(emailInput).toHaveAccessibleDescription(/enter a valid email/i);

    await user.clear(emailInput);
    await user.type(emailInput, "citizen@example.gov");
    await user.click(messageInput);

    expect(emailInput).toHaveAttribute("aria-invalid", "false");
  });

  it("renders a visible <label> above every input (no placeholder-as-label, no aria-label shortcut)", () => {
    const { emailInput, messageInput } = setup();

    for (const input of [emailInput, messageInput]) {
      expect(input).not.toHaveAttribute("placeholder");
      expect(input).not.toHaveAttribute("aria-label");
      expect(input).not.toHaveAttribute("aria-labelledby");

      const inputId = input.getAttribute("id");
      expect(inputId).toBeTruthy();

      const label = document.querySelector<HTMLLabelElement>(`label[for="${inputId}"]`);
      expect(label).not.toBeNull();
      expect(label!.tagName.toLowerCase()).toBe("label");
      expect(label!.textContent).toMatch(/\*/);
      expect(label!.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }

    expect(screen.getAllByText(/required/i).length).toBeGreaterThanOrEqual(2);
  });
});
