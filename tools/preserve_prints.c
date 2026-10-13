/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Copyright (C) 2026 Saatvik Sharma
 */
/* Preserve foreign chip records during fprintd storage management.
 * Default: block every delete/clear operation for lab tests.
 * FP840G5_ALLOW_NATIVE_PRINT_DELETE=1: permit individual native Validity FP1
 * prints, but keep foreign/unknown prints and whole-storage clearing blocked.
 * FP1 is a structured ownership marker, not a cryptographic provenance claim.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <dlfcn.h>
#include <libfprint/fprint.h>

typedef void (*DeletePrint) (FpDevice *, FpPrint *, GCancellable *,
                             GAsyncReadyCallback, gpointer);
typedef gboolean (*DeletePrintSync) (FpDevice *, FpPrint *, GCancellable *, GError **);

static gboolean
production_mode (void)
{
  return g_strcmp0 (g_getenv ("FP840G5_ALLOW_NATIVE_PRINT_DELETE"), "1") == 0;
}

static gboolean
uppercase_hex (gchar c)
{
  return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F');
}

static guint
decimal (const gchar *digits, guint count)
{
  guint value = 0;

  for (guint i = 0; i < count; i++)
    value = value * 10 + (digits[i] - '0');
  return value;
}

static gboolean
native_print (FpPrint *print)
{
  g_autoptr(GVariant) data = NULL;
  const gchar *id;
  const gchar *username;
  gsize len;
  guint year, month, day, finger;

  if (!FP_IS_PRINT (print) ||
      g_strcmp0 (fp_print_get_driver (print), "validity") != 0 ||
      !fp_print_get_device_stored (print) ||
      !fp_print_get_device_id (print) || !*fp_print_get_device_id (print))
    return FALSE;

  g_object_get (print, "fpi-data", &data, NULL);
  if (!data || !g_variant_is_of_type (data, G_VARIANT_TYPE_STRING))
    return FALSE;

  /* fpi_print_generate_user_id(): FP1-YYYYMMDD-F-RRRRRRRR-username.
   * Do not rely on fp_print_get_username(): the native storage-list path
   * currently supplies the identity and finger, without filling username. */
  id = g_variant_get_string (data, &len);
  if (len < 25 || !g_str_has_prefix (id, "FP1-") ||
      id[12] != '-' || id[14] != '-' || id[23] != '-')
    return FALSE;

  for (guint i = 4; i < 12; i++)
    if (id[i] < '0' || id[i] > '9')
      return FALSE;
  for (guint i = 15; i < 23; i++)
    if (!uppercase_hex (id[i]))
      return FALSE;

  if (!uppercase_hex (id[13]))
    return FALSE;
  finger = id[13] <= '9' ? id[13] - '0' : id[13] - 'A' + 10;
  if (finger > FP_FINGER_LAST || (guint) fp_print_get_finger (print) != finger)
    return FALSE;

  year = decimal (id + 4, 4);
  month = decimal (id + 8, 2);
  day = decimal (id + 10, 2);
  /* The generator uses all zeros when the enrollment date is unknown. */
  if ((year != 0 || month != 0 || day != 0) &&
      !g_date_valid_dmy (day, month, year))
    return FALSE;

  username = id + 24;
  if (!g_utf8_validate (username, -1, NULL))
    return FALSE;
  for (const gchar *p = username; *p; p = g_utf8_next_char (p))
    if (g_unichar_iscntrl (g_utf8_get_char (p)))
      return FALSE;

  return TRUE;
}

static GError *
blocked (void)
{
  return g_error_new_literal (FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED,
                             production_mode () ?
                             "Deletion is blocked to preserve foreign or unknown fingerprint records" :
                             "Deletion is disabled in the fingerprint preservation lab");
}

static void
blocked_async (FpDevice *device, GCancellable *cancellable,
               GAsyncReadyCallback callback, gpointer user_data)
{
  g_autoptr(GTask) task = g_task_new (device, cancellable, callback, user_data);
  g_task_return_error (task, blocked ());
}

void
fp_device_delete_print (FpDevice *device, FpPrint *print, GCancellable *cancellable,
                        GAsyncReadyCallback callback, gpointer user_data)
{
  if (production_mode () && native_print (print))
    {
      DeletePrint real_delete = (DeletePrint) dlsym (RTLD_NEXT, "fp_device_delete_print");

      if (real_delete)
        {
          real_delete (device, print, cancellable, callback, user_data);
          return;
        }
      /* Missing next API fails closed instead of invoking a fallback that
       * could bypass the individual-record policy. */
    }
  blocked_async (device, cancellable, callback, user_data);
}

gboolean
fp_device_delete_print_sync (FpDevice *device, FpPrint *print,
                             GCancellable *cancellable, GError **error)
{
  if (production_mode () && native_print (print))
    {
      DeletePrintSync real_delete = (DeletePrintSync) dlsym (RTLD_NEXT,
                                                            "fp_device_delete_print_sync");

      if (real_delete)
        return real_delete (device, print, cancellable, error);
    }
  g_propagate_error (error, blocked ());
  return FALSE;
}

void
fp_device_clear_storage (FpDevice *device, GCancellable *cancellable,
                         GAsyncReadyCallback callback, gpointer user_data)
{
  blocked_async (device, cancellable, callback, user_data);
}

gboolean
fp_device_clear_storage_sync (FpDevice *device, GCancellable *cancellable,
                              GError **error)
{
  (void) device;
  (void) cancellable;
  g_propagate_error (error, blocked ());
  return FALSE;
}
