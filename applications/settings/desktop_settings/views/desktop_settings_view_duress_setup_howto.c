#include <furi.h>
#include <gui/elements.h>
#include <gui/canvas.h>
#include <assets_icons.h>

#include "desktop_settings_view_duress_setup_howto.h"

struct DesktopSettingsViewDuressSetupHowto {
    View* view;
    DesktopSettingsViewDuressSetupHowtoDoneCallback callback;
    void* context;
};

static void desktop_settings_view_duress_setup_howto_draw(Canvas* canvas, void* model) {
    furi_assert(canvas);
    UNUSED(model);

    canvas_draw_icon(canvas, 16, 18, &I_Pin_attention_dpad_29x29);
    elements_button_right(canvas, "Next");

    canvas_set_font(canvas, FontPrimary);
    elements_multiline_text_aligned(canvas, 64, 0, AlignCenter, AlignTop, "Setting Up Duress PIN");

    canvas_set_font(canvas, FontSecondary);
    elements_multiline_text(canvas, 58, 24, "Prepare to use\narrows as\nDuress PIN symbols");
}

static bool desktop_settings_view_duress_setup_howto_input(InputEvent* event, void* context) {
    furi_assert(event);
    furi_assert(context);

    DesktopSettingsViewDuressSetupHowto* instance = context;
    if((event->key == InputKeyRight) && (event->type == InputTypeShort)) {
        if(instance->callback) instance->callback(instance->context);
        return true;
    }
    return false;
}

void desktop_settings_view_duress_setup_howto_set_callback(
    DesktopSettingsViewDuressSetupHowto* instance,
    DesktopSettingsViewDuressSetupHowtoDoneCallback callback,
    void* context) {
    furi_assert(instance);
    furi_assert(callback);
    instance->callback = callback;
    instance->context = context;
}

DesktopSettingsViewDuressSetupHowto* desktop_settings_view_duress_setup_howto_alloc(void) {
    DesktopSettingsViewDuressSetupHowto* instance = malloc(sizeof(DesktopSettingsViewDuressSetupHowto));
    instance->view = view_alloc();
    instance->callback = NULL;
    instance->context = NULL;
    view_set_context(instance->view, instance);
    view_set_draw_callback(instance->view, desktop_settings_view_duress_setup_howto_draw);
    view_set_input_callback(instance->view, desktop_settings_view_duress_setup_howto_input);
    return instance;
}

void desktop_settings_view_duress_setup_howto_free(DesktopSettingsViewDuressSetupHowto* instance) {
    furi_assert(instance);
    view_free(instance->view);
    free(instance);
}

View* desktop_settings_view_duress_setup_howto_get_view(DesktopSettingsViewDuressSetupHowto* instance) {
    furi_assert(instance);
    return instance->view;
}
