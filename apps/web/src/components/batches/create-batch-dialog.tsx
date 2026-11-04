"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { SegmentedControl } from "@/components/common/segmented-control";
import {
  INPUT_SIZE_OPTIONS,
  MODEL_OPTIONS,
  OUTPUT_FORMAT_OPTIONS,
} from "@/lib/batch-labels";
import { useCreateBatch, usePhotos } from "@/lib/queries";

// Every finite field is a selector, never free text (form UX convention; see
// components/settings/settings-form.tsx). Safe defaults are pre-selected and
// explained in FormDescription; the name field only shows a placeholder.
const schema = z
  .object({
    name: z.string().trim().min(1, "Give the batch a name").max(120),
    description: z.string().max(1000).optional(),
    source: z.enum(["all", "choose"]),
    sourceKeys: z.array(z.string()),
    model_id: z.enum([
      "ddcolor_paper_tiny",
      "ddcolor_modelscope",
      "ddcolor_paper",
      "ddcolor_artistic",
    ]),
    input_size: z.union([z.literal(256), z.literal(512)]),
    output_format: z.enum(["jpeg", "png", "webp"]),
    make_comparisons: z.boolean(),
    run_now: z.boolean(),
  })
  .refine((v) => v.source === "all" || v.sourceKeys.length > 0, {
    path: ["sourceKeys"],
    message: "Choose at least one photo",
  });

type Values = z.infer<typeof schema>;

function defaults(presetKeys: string[]): Values {
  return {
    name: "",
    description: "",
    source: presetKeys.length > 0 ? "choose" : "all",
    sourceKeys: presetKeys,
    model_id: "ddcolor_paper_tiny",
    input_size: 512,
    output_format: "jpeg",
    make_comparisons: true,
    run_now: true,
  };
}

interface CreateBatchDialogProps {
  trigger: ReactNode;
  /** Pre-select these originals (Photo Library "Colorize selected"). */
  presetKeys?: string[];
}

export function CreateBatchDialog({ trigger, presetKeys = [] }: CreateBatchDialogProps) {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const create = useCreateBatch();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: defaults(presetKeys) });
  const source = useWatch({ control: form.control, name: "source" });
  const photos = usePhotos(200, undefined);

  // Re-seed whenever the dialog opens, so a fresh Photo Library selection lands.
  useEffect(() => {
    if (open) form.reset(defaults(presetKeys));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const onSubmit = (values: Values) => {
    create.mutate(
      {
        name: values.name,
        description: values.description || null,
        all_unprocessed: values.source === "all",
        source_keys: values.source === "choose" ? values.sourceKeys : [],
        model_id: values.model_id,
        input_size: values.input_size,
        output_format: values.output_format,
        make_comparisons: values.make_comparisons,
        run_now: values.run_now,
      },
      {
        onSuccess: (batch) => {
          setOpen(false);
          toast.success(values.run_now ? "Batch queued" : "Draft saved", {
            description: `${batch.photo_count} photo(s) in "${batch.name}".`,
          });
          router.push(`/batches/${batch.batch_id}`);
        },
        onError: (error) =>
          toast.error(error.status === 503 ? "DDColor is not installed" : "Could not create batch", {
            description: error.message,
            duration: 12_000,
          }),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>New colorization batch</DialogTitle>
          <DialogDescription>
            The model settings are fixed once the batch exists: they define what its outputs and
            manifest mean. To try another model, create another batch.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Archive box 1" {...field} />
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
                    <Textarea
                      placeholder="Optional: collection, box or accession number"
                      className="resize-none"
                      rows={2}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="source"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Photos</FormLabel>
                  <FormControl>
                    <RadioGroup value={field.value} onValueChange={field.onChange} className="gap-2">
                      <label className="flex cursor-pointer items-center gap-2 text-sm">
                        <RadioGroupItem value="all" /> All not yet colorized
                      </label>
                      <label className="flex cursor-pointer items-center gap-2 text-sm">
                        <RadioGroupItem value="choose" /> Choose photos
                      </label>
                    </RadioGroup>
                  </FormControl>
                  <FormDescription>
                    Default: every ingested original that no batch has colorized yet.
                  </FormDescription>
                </FormItem>
              )}
            />
            {source === "choose" && (
              <FormField
                control={form.control}
                name="sourceKeys"
                render={({ field }) => (
                  <FormItem>
                    <ScrollArea className="h-44 rounded-md border border-border">
                      <div className="space-y-1 p-2">
                        {(photos.data?.items ?? []).map((photo) => {
                          const checked = field.value.includes(photo.key);
                          return (
                            <label
                              key={photo.key}
                              className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted"
                            >
                              <Checkbox
                                checked={checked}
                                onCheckedChange={(on) =>
                                  field.onChange(
                                    on
                                      ? [...field.value, photo.key]
                                      : field.value.filter((k) => k !== photo.key),
                                  )
                                }
                              />
                              <span className="truncate">{photo.filename}</span>
                              {photo.colorized_versions > 0 && (
                                <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                                  {photo.colorized_versions} version(s)
                                </span>
                              )}
                            </label>
                          );
                        })}
                        {photos.data?.items.length === 0 && (
                          <p className="p-2 text-sm text-muted-foreground">
                            No photos yet. Ingest scans first.
                          </p>
                        )}
                      </div>
                    </ScrollArea>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            <FormField
              control={form.control}
              name="model_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Model</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {MODEL_OPTIONS.map((m) => (
                        <SelectItem key={m.value} value={m.value}>
                          <span className="flex flex-col">
                            <span>{m.label}</span>
                            <span className="text-xs text-muted-foreground">{m.description}</span>
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Default: DDColor tiny, the fastest on CPU. Weights download from the Hugging
                    Face Hub on first use.
                  </FormDescription>
                </FormItem>
              )}
            />
            <div className="grid gap-5 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="input_size"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Input size</FormLabel>
                    <FormControl>
                      <SegmentedControl
                        aria-label="Input size"
                        value={field.value}
                        onChange={field.onChange}
                        options={INPUT_SIZE_OPTIONS}
                      />
                    </FormControl>
                    <FormDescription>Default 512. Output keeps the original resolution.</FormDescription>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="output_format"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Output format</FormLabel>
                    <FormControl>
                      <SegmentedControl
                        aria-label="Output format"
                        value={field.value}
                        onChange={field.onChange}
                        options={OUTPUT_FORMAT_OPTIONS}
                      />
                    </FormControl>
                    <FormDescription>Default JPEG.</FormDescription>
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="make_comparisons"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-md border border-border p-3">
                  <div className="space-y-0.5">
                    <FormLabel>Side-by-side comparisons</FormLabel>
                    <FormDescription>Default on. One extra JPEG per photo.</FormDescription>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="run_now"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-md border border-border p-3">
                  <div className="space-y-0.5">
                    <FormLabel>Run now</FormLabel>
                    <FormDescription>Default on. Off saves a draft you can run later.</FormDescription>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Creating..." : "Create batch"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
