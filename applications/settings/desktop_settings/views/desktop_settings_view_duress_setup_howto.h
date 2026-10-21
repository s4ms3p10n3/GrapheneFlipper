#pragma once

#include <gui/view.h>

typedef struct DesktopSettingsViewDuressSetupHowto DesktopSettingsViewDuressSetupHowto;

typedef void (*DesktopSettingsViewDuressSetupHowtoDoneCallback)(void*);

void desktop_settings_view_duress_setup_howto_set_callback(
    DesktopSettingsViewDuressSetupHowto* instance,
    DesktopSettingsViewDuressSetupHowtoDoneCallback callback,
    void* context);
DesktopSettingsViewDuressSetupHowto* desktop_settings_view_duress_setup_howto_alloc(void);
void desktop_settings_view_duress_setup_howto_free(DesktopSettingsViewDuressSetupHowto* instance);
View* desktop_settings_view_duress_setup_howto_get_view(DesktopSettingsViewDuressSetupHowto* instance);
