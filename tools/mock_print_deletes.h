/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Copyright (C) 2026 Saatvik Sharma
 */
/* Hardware-free replacement of the real delete APIs for guard policy tests. */
#pragma once
#include <libfprint/fprint.h>

typedef struct
{
  guint delete_sync;
  guint delete_async;
  guint clear_sync;
  guint clear_async;
  FpDevice *device;
  FpPrint *print;
  GCancellable *cancellable;
  GAsyncReadyCallback callback;
  gpointer user_data;
} MockPrintDeletes;

void mock_print_deletes_reset (gboolean fail);
const MockPrintDeletes *mock_print_deletes_get (void);
