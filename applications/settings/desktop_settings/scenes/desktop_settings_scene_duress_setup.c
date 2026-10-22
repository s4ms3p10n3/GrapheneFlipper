#include <core/check.h>
#include <gui/scene_manager.h>
#include <gui/view_dispatcher.h>
#include <gui/modules/popup.h>

#include "../desktop_settings_app.h"
#include "../desktop_settings_custom_event.h"
#include "desktop_settings_scene.h"
#include "desktop_settings_scene_i.h"
#include <desktop/helpers/pin_code.h>
#include <desktop/views/desktop_view_pin_input.h>

static void duress_setup_back_callback(void* context) {
    DesktopSettingsApp* app = context;
    view_dispatcher_send_custom_event(app->view_dispatcher, DesktopSettingsCustomEventExit);
}

static void duress_setup_popup_done_callback(void* context) {
    DesktopSettingsApp* app = context;
    view_dispatcher_send_custom_event(app->view_dispatcher, DesktopSettingsCustomEventExit);
}

static void duress_setup_done_callback(const DesktopPinCode* pin_code, void* context) {
    furi_assert(pin_code);
    furi_assert(context);
    DesktopSettingsApp* app = context;

    if(!app->pincode_buffer_filled) {
        app->pincode_buffer = *pin_code;
        app->pincode_buffer_filled = true;
        view_dispatcher_send_custom_event(
            app->view_dispatcher, DesktopSettingsCustomEvent1stPinEntered);
    } else {
        app->pincode_buffer_filled = false;
        view_dispatcher_send_custom_event(
            app->view_dispatcher,
            desktop_pin_code_is_equal(&app->pincode_buffer, pin_code) ?
                DesktopSettingsCustomEventPinsEqual : DesktopSettingsCustomEventPinsDifferent);
    }
}

void desktop_settings_scene_duress_setup_on_enter(void* context) {
    DesktopSettingsApp* app = context;
    app->pincode_buffer_filled = false;

    desktop_view_pin_input_set_context(app->pin_input_view, app);
    desktop_view_pin_input_set_back_callback(app->pin_input_view, duress_setup_back_callback);
    desktop_view_pin_input_set_done_callback(app->pin_input_view, duress_setup_done_callback);
    desktop_view_pin_input_set_label_button(app->pin_input_view, "OK");
    desktop_view_pin_input_set_label_primary(app->pin_input_view, 0, 0, NULL);
    desktop_view_pin_input_set_label_secondary(
        app->pin_input_view, 0, 8, "Enter 4 to 10 Duress arrows:");
    desktop_view_pin_input_reset_pin(app->pin_input_view);
    desktop_view_pin_input_unlock_input(app->pin_input_view);
    view_dispatcher_switch_to_view(app->view_dispatcher, DesktopSettingsAppViewIdPinInput);
}

bool desktop_settings_scene_duress_setup_on_event(void* context, SceneManagerEvent event) {
    DesktopSettingsApp* app = context;
    bool consumed = false;

    if(event.type == SceneManagerEventTypeCustom) {
        switch(event.event) {
        case DesktopSettingsCustomEvent1stPinEntered:
            desktop_view_pin_input_set_label_button(app->pin_input_view, "OK");
            desktop_view_pin_input_set_label_primary(app->pin_input_view, 0, 0, NULL);
            desktop_view_pin_input_set_label_secondary(
                app->pin_input_view, 0, 8, "Confirm Duress PIN:");
            desktop_view_pin_input_reset_pin(app->pin_input_view);
            desktop_view_pin_input_unlock_input(app->pin_input_view);
            consumed = true;
            break;
        case DesktopSettingsCustomEventPinsDifferent:
            scene_manager_set_scene_state(
                app->scene_manager,
                DesktopSettingsAppScenePinError,
                SCENE_STATE_PIN_ERROR_DURESS_MISMATCH);
            scene_manager_next_scene(app->scene_manager, DesktopSettingsAppScenePinError);
            consumed = true;
            break;
        case DesktopSettingsCustomEventPinsEqual:
            desktop_duress_code_set(&app->pincode_buffer);
            popup_set_context(app->popup, app);
            popup_set_callback(app->popup, duress_setup_popup_done_callback);
            popup_set_icon(app->popup, 0, 2, &I_DolphinMafia_119x62);
            popup_set_header(app->popup, "Duress PIN Set", 64, 10, AlignCenter, AlignTop);
            popup_set_timeout(app->popup, 1500);
            popup_enable_timeout(app->popup);
            view_dispatcher_switch_to_view(app->view_dispatcher, DesktopSettingsAppViewIdPopup);
            consumed = true;
            break;
        case DesktopSettingsCustomEventExit: {
            bool scene_found = scene_manager_search_and_switch_to_previous_scene(
                app->scene_manager, DesktopSettingsAppSceneDuressMenu);
            if(!scene_found) view_dispatcher_stop(app->view_dispatcher);
            consumed = true;
            break;
        }
        default:
            consumed = true;
            break;
        }
    }
    return consumed;
}

void desktop_settings_scene_duress_setup_on_exit(void* context) {
    furi_assert(context);
    DesktopSettingsApp* app = context;
    desktop_view_pin_input_set_back_callback(app->pin_input_view, NULL);
    desktop_view_pin_input_set_done_callback(app->pin_input_view, NULL);
}
