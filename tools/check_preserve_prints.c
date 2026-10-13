/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Copyright (C) 2026 Saatvik Sharma
 */
/* Verify the loaded guard and the real libfprint finish API, without USB IO. */
#include <libfprint/fprint.h>

static guint completed;

static void
check_error (GError *error)
{
  g_assert_error (error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED);
  g_assert_nonnull (g_strstr_len (error->message, -1, "preservation lab"));
}

static void
deleted (GObject *source, GAsyncResult *result, gpointer data)
{
  g_autoptr(GError) error = NULL;
  (void) source;
  (void) data;
  g_assert_false (fp_device_delete_print_finish (NULL, result, &error));
  check_error (error);
  completed++;
}

static void
cleared (GObject *source, GAsyncResult *result, gpointer data)
{
  g_autoptr(GError) error = NULL;
  (void) source;
  (void) data;
  g_assert_false (fp_device_clear_storage_finish (NULL, result, &error));
  check_error (error);
  completed++;
}

int
main (void)
{
  g_autoptr(GError) error = NULL;
  g_assert_false (fp_device_delete_print_sync (NULL, NULL, NULL, &error));
  check_error (error);
  g_clear_error (&error);
  g_assert_false (fp_device_clear_storage_sync (NULL, NULL, &error));
  check_error (error);
  fp_device_delete_print (NULL, NULL, NULL, deleted, NULL);
  fp_device_clear_storage (NULL, NULL, cleared, NULL);
  while (completed != 2)
    g_main_context_iteration (NULL, TRUE);
  g_print ("Preservation guard: all four deletion entry points blocked; no USB IO\n");
  return 0;
}
