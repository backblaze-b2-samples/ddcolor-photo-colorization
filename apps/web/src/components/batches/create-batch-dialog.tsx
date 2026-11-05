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
  modelLabel,
  OUTPUT_FORMAT_OPTIONS,
} from "@/lib/batch-labels";
import { useCreateBatch, usePhotos } from "@/lib/queries";

// Every finite field is a selector, never free text (form UX convention; see
// components/settings/settings-form.tsx). Safe defaults are pre-selected and
// explained in FormDescription; the name field is pre-filled with a suggestion.
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

/** "<model label>, <date>": the suggested name for a fresh batch. */
function defaultName(model: Values["model_id"], now = new Date()): string {
  const date = now.toLocaleDateString("en-CA"); // YYYY-MM-DD in local time
  return `${modelLabel(model)}, ${date}`.slice(0, 120);
}

/** "<base> (<model label>)": the suggested name for a re-run with another model. */
function suggestedName(nameBase: string, model: Values["model_id"]): string {
  return `${nameBase} (${modelLabel(model)})`.slice(0, 120);
}

function defaults(presetKeys: string[], preset: BatchPreset = {}): Values {
  const model_id = preset.model_id ?? "ddcolor_artistic";
  return {
    name: preset.nameBase
      ? suggestedName(preset.nameBase, model_id)
      : (preset.name ?? defaultName(model_id)),
    description: "",
    source: presetKeys.length > 0 ? "choose" : "all",
    sourceKeys: presetKeys,
    model_id,
    input_size: preset.input_size ?? 512,
    output_format: preset.output_format ?? "jpeg",
    make_comparisons: preset.make_comparisons ?? true,
    run_now: true,
  };
}

/** Pre-filled settings, e.g. "Colorize again with another model" from a batch. */
export type BatchPreset = Partial<
  Pick<Values, "name" | "model_id" | "input_size" | "output_format" | "make_comparisons">
> & {
  /** Source batch name; the suggested name follows the model until the user edits it. */
  nameBase?: string;
};

interface CreateBatchDialogProps {
  trigger: ReactNode;
  /** Pre-select these originals (Photo Library "Colorize selected"). */
  presetKeys?: string[];
  preset?: BatchPreset;
}

export function CreateBatchDialog({ trigger, presetKeys = [], preset }: CreateBatchDialogProps) {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const create = useCreateBatch();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: defaults(presetKeys, preset),
  });
  const source = useWatch({ control: form.control, name: "source" });
  const photos = usePhotos(200, undefined);
  const modelId = useWatch({ control: form.control, name: "model_id" });
  const nameEdited = form.formState.dirtyFields.name === true;
  const nameBase = preset?.nameBase;
  const presetName = preset?.name;

  // Keep the suggested name in step with the chosen model, until the user types their own.
  useEffect(() => {
    if (nameEdited || presetName !== undefined) return;
    form.setValue("name", nameBase ? suggestedName(nameBase, modelId) : defaultName(modelId));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, nameBase, presetName, nameEdited]);

  // Re-seed whenever the dialog opens, so a fresh Photo Library selection lands.
  useEffect(() => {
    if (open) form.reset(defaults(presetKeys, preset));
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
      {/* `grid-cols-[minmax(0,1fr)]`: the base DialogContent is a grid whose single
          auto column grows to its widest child, so one wide child pushed every
          field past the dialog's right edge. The column now stays dialog-wide. */}
      <DialogContent className="flex max-h-[calc(100vh-4rem)] flex-col overflow-hidden sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>New colorization batch</DialogTitle>
          <DialogDescription>
            The model settings are fixed once the batch exists: they define what its outputs and
            manifest mean. To try another model, create another batch.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex min-h-0 flex-1 flex-col gap-4"
          >
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-1 pb-1">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Name this batch" {...field} />
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
                      <SelectTrigger className="w-full min-w-0">
                        {/* Label only: the default SelectValue mirrors the whole item,
                            description included, into this nowrap trigger and made it
                            far wider than the dialog. */}
                        <SelectValue>{modelLabel(field.value)}</SelectValue>
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {MODEL_OPTIONS.map((m) => (
                        <SelectItem key={m.value} value={m.value}>
                          <span className="flex max-w-[28rem] flex-col whitespace-normal">
                            <span>{m.label}</span>
                            <span className="text-xs text-muted-foreground">{m.description}</span>
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Default: DDColor artistic. Results vary per photo and no checkpoint wins on
                    every image: if a result looks flat or sepia, colorize the same photos again
                    with another model from the batch page. Weights (about 900 MB) download from
                    the Hugging Face Hub on first use.
                  </FormDescription>
                </FormItem>
              )}
            />
            <div className="grid items-start gap-5 sm:grid-cols-2 [&>*]:min-w-0">
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
            </div>
            <DialogFooter className="shrink-0">
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
