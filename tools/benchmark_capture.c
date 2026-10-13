/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Copyright (C) 2026 Saatvik Sharma
 */
/* Host command-preparation benchmark. Synthetic calibration, no device I/O. */
#include "drivers/validity/validity.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>

int
main (int argc, char **argv)
{
  FpiDeviceValidity self = { 0 };
  const ValiditySensorTypeInfo *info = validity_sensor_type_info_lookup (0x0199);
  gsize iterations = 10000;
  gsize len = 0;
  gint64 start, uncached_us, cached_us;
  g_autofree guint8 *reference = NULL;

  /* An incomplete synthetic fixture must fail, never produce noisy timings. */
  g_log_set_always_fatal (G_LOG_FATAL_MASK | G_LOG_LEVEL_CRITICAL);

  if (argc > 2)
    return 2;
  if (argc == 2)
    {
      char *end;
      errno = 0;
      iterations = strtoul (argv[1], &end, 10);
      if (errno || *end || end == argv[1] || iterations < 1 || iterations > 1000000)
        return 2;
    }
  self.sensor.type_info = info;
  if (!info || !validity_capture_state_setup (&self.capture, info, 0x0d51, 6, 7, NULL, 0))
    return 1;
  self.capture.factory_calibration_values_len = info->lines_per_calibration_data;
  self.capture.factory_calibration_values = g_malloc0 (self.capture.factory_calibration_values_len);
  self.capture.calib_data_len = (gsize) info->bytes_per_line * info->lines_per_calibration_data;
  self.capture.calib_data = g_malloc0 (self.capture.calib_data_len);
  reference = validity_capture_build_cmd_02 (&self.capture, info, VALIDITY_CAPTURE_IDENTIFY, &len);
  if (!reference)
    {
      validity_capture_state_clear (&self.capture);
      return 1;
    }
  gsize cached_len;
  const guint8 *cached = validity_verify_get_capture_command (&self, &cached_len);
  if (!cached || cached_len != len || memcmp (reference, cached, len) != 0)
    {
      validity_verify_clear_capture_cache (&self);
      validity_capture_state_clear (&self.capture);
      return 1;
    }

  start = g_get_monotonic_time ();
  for (gsize i = 0; i < iterations; i++)
    {
      g_autofree guint8 *cmd = validity_capture_build_cmd_02 (
        &self.capture, info, VALIDITY_CAPTURE_IDENTIFY, &len);
      if (!cmd)
        return 1;
    }
  uncached_us = g_get_monotonic_time () - start;
  start = g_get_monotonic_time ();
  for (gsize i = 0; i < iterations; i++)
    if (!validity_verify_get_capture_command (&self, &cached_len))
      return 1;
  cached_us = g_get_monotonic_time () - start;

  g_print ("{\"iterations\":%zu,\"command_bytes\":%zu,"
           "\"uncached_us_per_call\":%.6f,\"cached_us_per_call\":%.6f,"
           "\"scope\":\"synthetic host preparation; excludes first build, USB, capture and matching\"}\n",
           iterations, len, (double) uncached_us / iterations, (double) cached_us / iterations);
  validity_verify_clear_capture_cache (&self);
  validity_capture_state_clear (&self.capture);
  return 0;
}
