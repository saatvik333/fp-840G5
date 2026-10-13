/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Copyright (C) 2026 Saatvik Sharma
 */
/* Reader must be clear: cancel a fresh native enroll, then check storage/reopen. */
#include <libfprint/fprint.h>

typedef struct
{
  gboolean done;
  gboolean cancelled;
} Result;

static gboolean
cancel_enroll (gpointer data)
{
  g_print ("Cancel native enrollment while waiting for a finger\n");
  g_cancellable_cancel (G_CANCELLABLE (data));
  return G_SOURCE_REMOVE;
}

static void
enrolled (GObject *source, GAsyncResult *async_result, gpointer data)
{
  Result *result = data;
  g_autoptr(GError) error = NULL;
  g_autoptr(FpPrint) print = fp_device_enroll_finish (FP_DEVICE (source), async_result, &error);
  result->cancelled = !print && g_error_matches (error, G_IO_ERROR, G_IO_ERROR_CANCELLED);
  if (result->cancelled)
    g_print ("Enrollment returned G_IO_ERROR_CANCELLED after cleanup\n");
  else
    g_printerr ("Unexpected enrollment result: %s\n", error ? error->message : "completed");
  result->done = TRUE;
}

static gint
inventory (FpDevice *device)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GPtrArray) prints = fp_device_list_prints_sync (device, NULL, &error);
  if (!prints)
    {
      g_printerr ("Inventory failed: %s\n", error->message);
      return -1;
    }
  return (gint) prints->len;
}

int
main (void)
{
  g_autoptr(FpContext) context = fp_context_new ();
  GPtrArray *devices = fp_context_get_devices (context);
  FpDevice *device = NULL;
  g_autoptr(GError) error = NULL;
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(FpPrint) template = NULL;
  Result result = { 0 };
  gint before, after;

  for (guint i = 0; i < devices->len; i++)
    {
      FpDevice *candidate = g_ptr_array_index (devices, i);
      if (g_strcmp0 (fp_device_get_driver (candidate), "validity") == 0)
        {
          if (device)
            return 2;
          device = candidate;
        }
    }
  if (!device || !fp_device_open_sync (device, NULL, &error))
    {
      g_printerr ("Initial open failed: %s\n", error ? error->message : "reader absent");
      return 1;
    }
  before = inventory (device);
  if (before < 0)
    return 1;
  g_print ("Initial on-chip template count=%d\n", before);
  for (guint attempt = 1; attempt <= 2; attempt++)
    {
      g_print ("Native enrollment/cancel attempt %u/2 in the same open session\n", attempt);
      result = (Result) { 0 };
      g_cancellable_reset (cancellable);
      g_clear_object (&template);
      template = g_object_ref_sink (fp_print_new (device));
      fp_print_set_username (template, "fp-840g5-cancellation-test");
      fp_print_set_finger (template, FP_FINGER_UNKNOWN);
      fp_device_enroll (device, template, cancellable, NULL, NULL, NULL, enrolled, &result);
      guint timer = g_timeout_add (2000, cancel_enroll, cancellable);
      while (!result.done)
        g_main_context_iteration (NULL, TRUE);
      if (!g_cancellable_is_cancelled (cancellable))
        g_source_remove (timer);
      if (!result.cancelled)
        return 1;
    }
  after = inventory (device);
  g_print ("After cancellation on-chip template count=%d\n", after);
  if (after != before)
    return 1;
  if (!fp_device_close_sync (device, NULL, &error) ||
      !fp_device_open_sync (device, NULL, &error))
    {
      g_printerr ("Close/reopen after cancelled enrollment failed: %s\n", error->message);
      return 1;
    }
  after = inventory (device);
  g_print ("After reopen on-chip template count=%d\n", after);
  if (after != before || !fp_device_close_sync (device, NULL, &error))
    return 1;
  g_print ("Native enrollment cancellation, inventory and reopen passed\n");
  return 0;
}
