"use client";

import { useEffect, useState } from "react";
import type { Batch } from "@ddcolor-photo-colorization/shared";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil } from "lucide-react";
import { z } from "zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formatLabel, modelLabel } from "@/lib/batch-labels";
import { useUpdateBatch } from "@/lib/queries";

const schema = z.object({
  name: z.string().trim().min(1, "Give the batch a name").max(120),
  description: z.string().max(1000),
});

type Values = z.infer<typeof schema>;

/** Rename / describe a batch. The model configuration is shown read-only. */
export function EditBatchDialog({ batch }: { batch: Batch }) {
  const [open, setOpen] = useState(false);
  const update = useUpdateBatch(batch.batch_id);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: batch.name, description: batch.description ?? "" },
  });

  useEffect(() => {
    if (open) form.reset({ name: batch.name, description: batch.description ?? "" });
  }, [open, batch.name, batch.description, form]);

  const onSubmit = (values: Values) =>
    update.mutate(
      { name: values.name, description: values.description || null },
      {
        onSuccess: () => {
          setOpen(false);
          toast.success("Batch updated");
        },
        onError: (error) => toast.error("Could not update batch", { description: error.message }),
      },
    );

  const config = [
    ["Model", modelLabel(batch.model_id)],
    ["Input size", String(batch.input_size)],
    ["Output", formatLabel(batch.output_format)],
    ["Comparisons", batch.make_comparisons ? "On" : "Off"],
  ];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Pencil aria-hidden className="h-3.5 w-3.5" />
          Edit
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit batch</DialogTitle>
          <DialogDescription>
            Name and description only. The configuration below defines what this batch&apos;s
            outputs mean, so it cannot change; create a new batch to use another model.
          </DialogDescription>
        </DialogHeader>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-md border border-border bg-muted/30 p-3 text-sm">
          {config.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-medium">{value}</dd>
            </div>
          ))}
        </dl>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea className="resize-none" rows={3} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={update.isPending}>
                {update.isPending ? "Saving..." : "Save"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
