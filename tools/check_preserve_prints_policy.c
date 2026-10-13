/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Copyright (C) 2026 Saatvik Sharma
 */
/* Production guard tests: fake print GObjects and a mock RTLD_NEXT delete
 * DSO. No FpContext is created, no device is opened, and no USB I/O occurs. */
#include "mock_print_deletes.h"

typedef struct
{
  gboolean done;
  gboolean result;
  GError *error;
} AsyncResult;

static FpPrint *
make_print (const gchar *id, FpFinger finger, gboolean stored, const gchar *driver)
{
  FpPrint *print = g_object_new (FP_TYPE_PRINT,
                                 "driver", driver,
                                 "device-id", "hardware-free-mock",
                                 "device-stored", stored,
                                 "finger", finger,
                                 NULL);

  g_object_ref_sink (print);
  if (id)
    g_object_set (print, "fpi-data", g_variant_new_string (id), NULL);
  /* Mirrors native list output: identity exists while username is unset. */
  g_assert_null (fp_print_get_username (print));
  return print;
}

static void
deleted (GObject *source, GAsyncResult *result, gpointer user_data)
{
  AsyncResult *out = user_data;
  (void) source;

  out->result = fp_device_delete_print_finish (NULL, result, &out->error);
  out->done = TRUE;
}

static void
cleared (GObject *source, GAsyncResult *result, gpointer user_data)
{
  AsyncResult *out = user_data;
  (void) source;

  out->result = fp_device_clear_storage_finish (NULL, result, &out->error);
  out->done = TRUE;
}

static void
check_delete (FpPrint *print, gboolean allowed, gboolean next_fails)
{
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GError) error = NULL;
  const MockPrintDeletes *calls;
  AsyncResult out = { 0 };
  gboolean result;

  mock_print_deletes_reset (next_fails);
  result = fp_device_delete_print_sync (NULL, print, cancellable, &error);
  calls = mock_print_deletes_get ();
  g_assert_cmpuint (calls->delete_sync, ==, allowed ? 1 : 0);
  g_assert_cmpuint (calls->delete_async, ==, 0);
  if (allowed)
    {
      g_assert_true (calls->print == print);
      g_assert_true (calls->cancellable == cancellable);
      g_assert_null (calls->device);
    }
  g_assert_cmpint (result, ==, allowed && !next_fails);
  if (!allowed)
    g_assert_error (error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED);
  else if (next_fails)
    g_assert_error (error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_GENERAL);
  else
    g_assert_no_error (error);

  mock_print_deletes_reset (next_fails);
  fp_device_delete_print (NULL, print, cancellable, deleted, &out);
  calls = mock_print_deletes_get ();
  g_assert_cmpuint (calls->delete_async, ==, allowed ? 1 : 0);
  g_assert_cmpuint (calls->delete_sync, ==, 0);
  if (allowed)
    {
      g_assert_true (calls->print == print);
      g_assert_true (calls->cancellable == cancellable);
      g_assert_true (calls->callback == deleted);
      g_assert_true (calls->user_data == &out);
      g_assert_null (calls->device);
    }
  while (!out.done)
    g_main_context_iteration (NULL, TRUE);
  g_assert_cmpint (out.result, ==, allowed && !next_fails);
  if (!allowed)
    g_assert_error (out.error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED);
  else if (next_fails)
    g_assert_error (out.error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_GENERAL);
  else
    g_assert_no_error (out.error);
  g_clear_error (&out.error);
}

static void
test_native_identities (void)
{
  const struct { const gchar *id; FpFinger finger; } valid[] = {
    { "FP1-20261013-8-0123ABCD-lab-user", FP_FINGER_RIGHT_MIDDLE },
    { "FP1-00000000-0-00000000-nobody", FP_FINGER_UNKNOWN },
    { "FP1-20240229-A-DEADBEEF-test", FP_FINGER_RIGHT_LITTLE },
  };

  for (guint i = 0; i < G_N_ELEMENTS (valid); i++)
    {
      g_autoptr(FpPrint) print = make_print (valid[i].id, valid[i].finger, TRUE, "validity");
      check_delete (print, TRUE, FALSE);
    }
}

static void
test_foreign_and_malformed_identities (void)
{
  const gchar *invalid[] = {
    NULL,
    "",
    "S-1-5-21-1000-2000-3000-1001",
    "FP1-foreign-record",
    "FP1-20261013-8-0123ABCD-",         /* empty username */
    "FP1-20261013-8-0123ABC-lab",      /* short random id */
    "FP1-20261013-8-0123ABCDE-lab",    /* long random id */
    "FP1-20261013-8-0123abcd-lab",     /* generator uses uppercase */
    "FP1-20261013-8-0123ABCG-lab",
    "FP1-20261313-8-0123ABCD-lab",
    "FP1-20260229-8-0123ABCD-lab",
    "FP1-00000101-8-0123ABCD-lab",
    "FP1-20261X13-8-0123ABCD-lab",
    "FP1-20261013-B-0123ABCD-lab",     /* outside finger enum */
    "FP1-20261013-A-0123ABCD-lab",     /* differs from print's finger */
    "FP1-20261013-8-0123ABCD-lab\nuser",
  };

  for (guint i = 0; i < G_N_ELEMENTS (invalid); i++)
    {
      g_autoptr(FpPrint) print = make_print (invalid[i], FP_FINGER_RIGHT_MIDDLE,
                                            TRUE, "validity");
      check_delete (print, FALSE, FALSE);
    }
}

static void
test_print_metadata (void)
{
  const gchar *id = "FP1-20261013-8-0123ABCD-lab";
  g_autoptr(FpPrint) not_stored = make_print (id, FP_FINGER_RIGHT_MIDDLE, FALSE, "validity");
  g_autoptr(FpPrint) other_driver = make_print (id, FP_FINGER_RIGHT_MIDDLE, TRUE, "synaptics");
  g_autoptr(FpPrint) wrong_type = make_print (id, FP_FINGER_RIGHT_MIDDLE, TRUE, "validity");
  g_autoptr(FpPrint) unknown_device = g_object_ref_sink (g_object_new (FP_TYPE_PRINT,
                                                                    "driver", "validity",
                                                                    "device-id", "",
                                                                    "finger", FP_FINGER_RIGHT_MIDDLE,
                                                                    "device-stored", TRUE,
                                                                    "fpi-data", g_variant_new_string (id), NULL));

  g_object_set (wrong_type, "fpi-data", g_variant_new_uint32 (42), NULL);
  check_delete (not_stored, FALSE, FALSE);
  check_delete (other_driver, FALSE, FALSE);
  check_delete (wrong_type, FALSE, FALSE);
  check_delete (unknown_device, FALSE, FALSE);
  check_delete (NULL, FALSE, FALSE);
}

static void
test_next_api_error (void)
{
  g_autoptr(FpPrint) print = make_print ("FP1-20261013-8-0123ABCD-lab",
                                        FP_FINGER_RIGHT_MIDDLE, TRUE, "validity");
  check_delete (print, TRUE, TRUE);
}

static void
test_clear_always_blocked (void)
{
  g_autoptr(GError) error = NULL;
  AsyncResult out = { 0 };
  const MockPrintDeletes *calls;

  mock_print_deletes_reset (FALSE);
  g_assert_false (fp_device_clear_storage_sync (NULL, NULL, &error));
  g_assert_error (error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED);
  fp_device_clear_storage (NULL, NULL, cleared, &out);
  while (!out.done)
    g_main_context_iteration (NULL, TRUE);
  g_assert_false (out.result);
  g_assert_error (out.error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED);
  calls = mock_print_deletes_get ();
  g_assert_cmpuint (calls->clear_sync, ==, 0);
  g_assert_cmpuint (calls->clear_async, ==, 0);
  g_clear_error (&out.error);
}

static void
test_exact_opt_in (void)
{
  if (g_test_subprocess ())
    {
      const gchar *mode = g_getenv ("FP840G5_GUARD_TEST_MODE");
      g_autoptr(FpPrint) print = make_print ("FP1-20261013-8-0123ABCD-lab",
                                            FP_FINGER_RIGHT_MIDDLE, TRUE, "validity");
      g_autoptr(GError) error = NULL;

      if (g_strcmp0 (mode, "unset") == 0)
        g_unsetenv ("FP840G5_ALLOW_NATIVE_PRINT_DELETE");
      else
        g_setenv ("FP840G5_ALLOW_NATIVE_PRINT_DELETE", mode, TRUE);
      mock_print_deletes_reset (FALSE);
      g_assert_false (fp_device_delete_print_sync (NULL, print, NULL, &error));
      g_assert_error (error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED);
      g_assert_cmpuint (mock_print_deletes_get ()->delete_sync, ==, 0);
      return;
    }

  const gchar *modes[] = { "unset", "0", "true", "yes", "01", "1 " };
  for (guint i = 0; i < G_N_ELEMENTS (modes); i++)
    {
      g_auto(GStrv) envp = g_get_environ ();

      envp = g_environ_setenv (envp, "FP840G5_GUARD_TEST_MODE", modes[i], TRUE);
      g_test_trap_subprocess_with_envp (NULL, (const gchar * const *) envp,
                                      5 * G_USEC_PER_SEC, G_TEST_SUBPROCESS_DEFAULT);
      g_test_trap_assert_passed ();
    }
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_assert_cmpstr (g_getenv ("FP840G5_ALLOW_NATIVE_PRINT_DELETE"), ==, "1");
  g_test_add_func ("/preservation/mode/exact-opt-in", test_exact_opt_in);
  g_test_add_func ("/preservation/native-identities", test_native_identities);
  g_test_add_func ("/preservation/foreign-and-malformed", test_foreign_and_malformed_identities);
  g_test_add_func ("/preservation/print-metadata", test_print_metadata);
  g_test_add_func ("/preservation/next-api-error", test_next_api_error);
  g_test_add_func ("/preservation/clear-always-blocked", test_clear_always_blocked);
  return g_test_run ();
}
