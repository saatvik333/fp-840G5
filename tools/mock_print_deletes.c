/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Copyright (C) 2026 Saatvik Sharma
 */
/* Never reaches a driver: provides the RTLD_NEXT delete APIs for guard tests. */
#include "mock_print_deletes.h"

static MockPrintDeletes calls;
static gboolean fail_delete;

void
mock_print_deletes_reset (gboolean fail)
{
  calls = (MockPrintDeletes) { 0 };
  fail_delete = fail;
}

const MockPrintDeletes *
mock_print_deletes_get (void)
{
  return &calls;
}

static GError *
mock_error (void)
{
  return g_error_new_literal (FP_DEVICE_ERROR, FP_DEVICE_ERROR_GENERAL,
                              "Mock next delete failed");
}

static void
mock_async (FpDevice *device, GCancellable *cancellable,
             GAsyncReadyCallback callback, gpointer user_data, gboolean fail)
{
  g_autoptr(GTask) task = g_task_new (device, cancellable, callback, user_data);

  if (fail)
    g_task_return_error (task, mock_error ());
  else
    g_task_return_boolean (task, TRUE);
}

void
fp_device_delete_print (FpDevice *device, FpPrint *print, GCancellable *cancellable,
                        GAsyncReadyCallback callback, gpointer user_data)
{
  calls.delete_async++;
  calls.device = device;
  calls.print = print;
  calls.cancellable = cancellable;
  calls.callback = callback;
  calls.user_data = user_data;
  mock_async (device, cancellable, callback, user_data, fail_delete);
}

gboolean
fp_device_delete_print_sync (FpDevice *device, FpPrint *print,
                             GCancellable *cancellable, GError **error)
{
  calls.delete_sync++;
  calls.device = device;
  calls.print = print;
  calls.cancellable = cancellable;
  if (fail_delete)
    {
      g_propagate_error (error, mock_error ());
      return FALSE;
    }
  return TRUE;
}

void
fp_device_clear_storage (FpDevice *device, GCancellable *cancellable,
                         GAsyncReadyCallback callback, gpointer user_data)
{
  calls.clear_async++;
  mock_async (device, cancellable, callback, user_data, FALSE);
}

gboolean
fp_device_clear_storage_sync (FpDevice *device, GCancellable *cancellable,
                              GError **error)
{
  (void) device;
  (void) cancellable;
  (void) error;
  calls.clear_sync++;
  return TRUE;
}
