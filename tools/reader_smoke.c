/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Copyright (C) 2026 Saatvik Sharma
 */
/* Inspect and repeatedly open/close one native reader; no template mutation API. */
#include <libfprint/fprint.h>
#include <glib.h>
#include <stdlib.h>

int
main (int argc, char **argv)
{
  guint cycles = argc > 1 ? (guint) atoi (argv[1]) : 3;
  g_autoptr(FpContext) context = fp_context_new ();
  GPtrArray *devices = fp_context_get_devices (context);
  FpDevice *device = NULL;

  if (cycles < 1 || cycles > 10)
    return 2;
  for (guint i = 0; i < devices->len; i++)
    {
      FpDevice *candidate = g_ptr_array_index (devices, i);
      if (g_strcmp0 (fp_device_get_driver (candidate), "validity") == 0)
        {
          if (device != NULL)
            {
              g_printerr ("More than one native Validity reader; refusing selection\n");
              return 1;
            }
          device = candidate;
        }
    }
  if (!device)
    {
      g_printerr ("Native Validity reader was not enumerated\n");
      return 1;
    }
  g_print ("Reader: %s; driver=%s; enrollment stages=%d; features=0x%x\n",
           fp_device_get_name (device), fp_device_get_driver (device),
           fp_device_get_nr_enroll_stages (device), fp_device_get_features (device));

  for (guint i = 0; i < cycles; i++)
    {
      g_autoptr(GError) error = NULL;
      g_autoptr(GPtrArray) prints = NULL;
      gint64 start = g_get_monotonic_time ();
      g_print ("Cycle %u/%u: opening reader\n", i + 1, cycles);
      if (!fp_device_open_sync (device, NULL, &error))
        {
          g_printerr ("Open failed: %s\n", error->message);
          return 1;
        }
      g_print ("Cycle %u: open succeeded in %.3f seconds\n", i + 1,
               (g_get_monotonic_time () - start) / 1000000.0);
      prints = fp_device_list_prints_sync (device, NULL, &error);
      if (!prints)
        {
          g_printerr ("On-device inventory failed: %s\n", error->message);
          g_clear_error (&error);
          fp_device_close_sync (device, NULL, &error);
          return 1;
        }
      g_print ("Cycle %u: on-device template count=%u\n", i + 1, prints->len);
      g_print ("Cycle %u: closing reader\n", i + 1);
      if (!fp_device_close_sync (device, NULL, &error))
        {
          g_printerr ("Close failed: %s\n", error->message);
          return 1;
        }
      g_print ("Cycle %u: close succeeded\n", i + 1);
    }
  return 0;
}
