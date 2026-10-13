/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Copyright (C) 2026 Saatvik Sharma
 */
/* Offline check using the actual compiled driver's data and firmware loaders. */
#include "drivers_api.h"
#include "validity_data.h"
#include "validity_fwext.h"
#include <glib.h>

int
main (void)
{
  ValidityDataStore device, common;
  ValidityFwextFile fwext;
  g_autoptr(GError) error = NULL;
  g_autofree gchar *firmware_path = NULL;
  g_autofree gchar *reset_sha = NULL;
  const guint8 *reset;
  gsize reset_size = 0;

  validity_data_store_init (&device);
  validity_data_store_init (&common);
  if (!validity_data_load_device (&device, 0x138a, 0x00ab, &error) ||
      !validity_data_load_common (&common, &error))
    g_error ("Staged data load failed: %s", error->message);

  reset = validity_data_get_bytes (&device, VALIDITY_DATA_RESET, &reset_size);
  g_assert_nonnull (reset);
  g_assert_cmpuint (reset_size, ==, 11973);
  reset_sha = g_compute_checksum_for_data (G_CHECKSUM_SHA256, reset, reset_size);
  g_assert_cmpstr (reset_sha, ==,
                   "7f379b1648326f031753d2d0a974bae75bc59a95f847b9c6478a124f32b3c17a");

  firmware_path = validity_fwext_find_firmware (0x138a, 0x00ab, &error);
  if (!firmware_path || !validity_fwext_load_file (firmware_path, &fwext, &error))
    g_error ("Staged firmware load failed: %s", error->message);
  g_assert_cmpuint (fwext.payload_len, ==, 196512);
  g_print ("Native loader verified HP reset (%zu bytes), common data, "
           "and encrypted firmware (%zu bytes) at %s\n",
           reset_size, fwext.payload_len, firmware_path);
  validity_fwext_file_clear (&fwext);
  validity_data_store_free (&common);
  validity_data_store_free (&device);
  return 0;
}
