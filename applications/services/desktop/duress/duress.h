#pragma once

/**
 * Duress-PIN handling for the Unleashed Firmware lockscreen.
 *
 * REVISION 2 -- see PATCH_NOTES.md for why. This version takes a raw
 * InputKey array + length instead of a PinCode/DesktopPinCode struct
 * pointer, so it doesn't need to know what that struct is called in your
 * tree (it's been renamed at least once already) or touch DesktopSettings
 * for anything (the pin_code field was removed when internal LFS storage
 * was dropped). The only dependency here is <input/input.h>'s InputKey,
 * about as stable as this codebase gets, and the opaque Desktop type.
 *
 * Drop this pair of files at:
 *   applications/services/desktop/duress/duress.h
 *   applications/services/desktop/duress/duress.c
 */

#include <stdint.h>
#include <stdbool.h>
#include <input/input.h>
#include "../desktop.h" // opaque Desktop type only

#ifdef __cplusplus
extern "C" {
#endif

/** True if the entered key sequence matches the compiled-in duress
 *  sequence. Call it with pin_code->data and pin_code->length straight
 *  from whatever the done-callback in your tree receives -- those field
 *  names should be stable even where the struct's type name isn't. */
bool duress_pin_matches(const InputKey* keys, uint8_t length);

/** Runs the full wipe-and-reset sequence. Does not return. */
void execute_duress_wipe(Desktop* desktop);

#ifdef __cplusplus
}
#endif