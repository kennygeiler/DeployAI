"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

/**
 * Canonical shadcn-Form + zod reference component. Exercises the contract
 * documented in `ux-design-specification.md` §Form Patterns (lines 877–883)
 * and `epics.md#UX-DR40`:
 *
 *  - Label renders above the input (never placeholder-as-label).
 *  - Required indicator is asterisk + sr-only "required" text
 *    (never color-only per UX-DR28).
 *  - Validation mode is `onBlur` for format, `onSubmit` for completeness.
 *  - `aria-invalid` + `aria-describedby` wiring flows through shadcn's
 *    `<FormControl>` / `<FormMessage>` automatically.
 *  - Cmd+Enter (or Ctrl+Enter) submits — listener is form-scoped so it
 *    never conflicts with Cmd+K or other global hotkeys (Epic 8).
 */
export const exampleFormSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  message: z
    .string()
    .trim()
    .min(1, "Message is required")
    .max(500, "Message must be 500 characters or fewer"),
});

export type ExampleFormValues = z.infer<typeof exampleFormSchema>;

export interface ExampleFormProps {
  onSubmit: (values: ExampleFormValues) => void;
}

export function ExampleForm({ onSubmit }: ExampleFormProps) {
  const form = useForm<ExampleFormValues>({
    resolver: zodResolver(exampleFormSchema),
    mode: "onBlur",
    defaultValues: { email: "", message: "" },
  });

  const submit = form.handleSubmit(onSubmit);

  return (
    <Form {...form}>
      {/* jsx-a11y gate-appeal: `<form onKeyDown>` for Cmd/Ctrl+Enter submit
          is a keyboard-accessibility *enhancement* additive to the submit
          button's native behavior — it gives keyboard-only users a
          shortcut and costs no SR discoverability (the button remains
          the primary path). See docs/a11y-gates.md §Appeal process and
          Story 1.6 Dev Agent Record for rationale. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
      <form
        onSubmit={submit}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
            event.preventDefault();
            void submit();
          }
        }}
        className="space-y-4"
        noValidate
      >
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Email <span aria-hidden="true">*</span>
                <span className="sr-only"> required</span>
              </FormLabel>
              <FormControl>
                <Input type="email" autoComplete="email" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="message"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Message <span aria-hidden="true">*</span>
                <span className="sr-only"> required</span>
              </FormLabel>
              <FormControl>
                <Textarea rows={5} {...field} />
              </FormControl>
              <FormDescription>Cmd+Enter submits the form.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <Button type="submit">Submit</Button>
      </form>
    </Form>
  );
}
