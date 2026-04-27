import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Settings } from "lucide-react";

import { ExampleForm } from "@/components/forms/ExampleForm";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

/**
 * UX-DR39–41 — pattern reference in the host app (shadcn primitives live in `apps/web`).
 * Component composites ship from `@deployai/shared-ui`; these stories are the interaction
 * contract for buttons, forms, and overlays (see `docs/design-system/governance.md`).
 */
const meta: Meta = {
  title: "Patterns/Design system consistency (UX-DR39–41)",
  tags: ["autodocs"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          'Primary (one decisive action per surface), secondary outline, ghost tertiary, destructive only for irreversible flows. Forms: label above control, explicit required text, `aria-invalid` + `aria-describedby` via shadcn Form. Overlays: destructive confirmations → `Dialog` with `role="alertdialog"` when shipping irreversible actions; heavy multi-field settings → `Sheet`; lightweight metadata → `Popover`.',
      },
    },
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const ButtonHierarchy: Story = {
  render: () => (
    <div className="flex min-h-32 flex-wrap items-center gap-3">
      <Button className="min-h-9">Primary action</Button>
      <Button variant="secondary" className="min-h-9">
        Secondary
      </Button>
      <Button variant="ghost" className="min-h-9">
        Tertiary / ghost
      </Button>
      <Button variant="destructive" className="min-h-9">
        Destructive
      </Button>
      <Button
        size="icon"
        variant="outline"
        className="size-11 min-h-11 min-w-11"
        aria-label="Settings"
      >
        <Settings className="size-4" />
      </Button>
    </div>
  ),
};

export const CanonicalFormStack: Story = {
  parameters: {
    docs: {
      description: {
        story:
          "Keyboard: Tab through fields; **Cmd+Enter** (mac) or **Ctrl+Enter** (Windows/Linux) submits when focus is inside the form (scoped handler — does not steal Epic 8 ⌃K). Screen reader: required fields use visible asterisk plus sr-only “required”; errors tie to inputs with `aria-describedby`.",
      },
    },
  },
  render: () => (
    <div className="mx-auto max-w-md space-y-3">
      <ExampleForm onSubmit={() => {}} />
    </div>
  ),
};

export const ModalSheetPopoverStack: Story = {
  parameters: {
    docs: {
      description: {
        story:
          "**Dialog** — blocking confirmation (here: destructive-style body copy). **Sheet** — multi-section settings that need horizontal real estate. **Popover** — transient metadata without a full modal.",
      },
    },
  },
  render: () => (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="pat-dialog" className="space-y-2">
        <h2 id="pat-dialog" className="text-sm font-semibold">
          Dialog (destructive / irreversible)
        </h2>
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="destructive" className="min-h-9">
              Open delete confirmation
            </Button>
          </DialogTrigger>
          <DialogContent role="alertdialog" aria-modal="true">
            <DialogHeader>
              <DialogTitle>Remove deployment tag?</DialogTitle>
              <DialogDescription>
                This action cannot be undone in the mock. Production flows must wire audit +
                rollback per policy.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="gap-2 sm:gap-0">
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  Cancel
                </Button>
              </DialogClose>
              <DialogClose asChild>
                <Button type="button" variant="destructive">
                  Delete tag
                </Button>
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </section>

      <section aria-labelledby="pat-sheet" className="space-y-2">
        <h2 id="pat-sheet" className="text-sm font-semibold">
          Sheet (heavy settings)
        </h2>
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="secondary" className="min-h-9">
              Open integration settings
            </Button>
          </SheetTrigger>
          <SheetContent side="right" className="flex flex-col gap-4">
            <SheetHeader>
              <SheetTitle>Integration defaults</SheetTitle>
              <SheetDescription>
                Placeholder layout for multi-field settings that do not belong in a small popover.
              </SheetDescription>
            </SheetHeader>
            <p className="text-muted-foreground text-sm">
              Stack form sections here; keep primary save actions in a sticky footer when the list
              grows (Epic 10 / control-plane surfaces).
            </p>
          </SheetContent>
        </Sheet>
      </section>

      <section aria-labelledby="pat-popover" className="space-y-2">
        <h2 id="pat-popover" className="text-sm font-semibold">
          Popover (metadata)
        </h2>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="min-h-9">
              Show citation envelope
            </Button>
          </PopoverTrigger>
          <PopoverContent className="text-sm">
            <p className="font-medium text-foreground">RFC-3161 digest</p>
            <p className="text-muted-foreground mt-1">
              Mock envelope metadata only — real payloads ship from Cartographer / Oracle (Epic 6).
            </p>
          </PopoverContent>
        </Popover>
      </section>
    </div>
  ),
};
