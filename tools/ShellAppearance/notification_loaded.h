#pragma once

// Shell can build the date flyout while it is hidden and finish its names on
// first use, long after Dock started. Keep weak subscriptions to that UI event.
struct BF_NotificationPendingLoad {
    winrt::weak_ref<FrameworkElement> element;
    FrameworkElement::Loaded_revoker loaded;
    FrameworkElement::LayoutUpdated_revoker firstLayout;
    std::optional<int64_t> nameChanged;
    std::wstring fallback;
};
static thread_local std::map<InstanceHandle,BF_NotificationPendingLoad> bf_notificationLoads;

static void BF_RemoveNotificationLoad(InstanceHandle handle) {
    auto entry=bf_notificationLoads.extract(handle);
    if (entry.empty()) return;
    auto& pending=entry.mapped();
    pending.loaded.revoke();
    pending.firstLayout.revoke();
    if (pending.nameChanged) {
        if (auto element=pending.element.get())
            element.UnregisterPropertyChangedCallback(FrameworkElement::NameProperty(),*pending.nameChanged);
    }
}

static bool BF_IsCalendarPart(std::wstring_view name) {
    return name==L"CalendarCenterGrid" || name==L"CalendarControlScrollViewer" ||
           name==L"CalendarHeaderMinimizedOverlay" || name==L"FocusGrid";
}

static void BF_ClearNotificationLoads() {
    while (!bf_notificationLoads.empty())
        BF_RemoveNotificationLoad(bf_notificationLoads.begin()->first);
}

static void BF_NotificationReady(InstanceHandle handle,unsigned generation) noexcept {
    try {
        if (!bf_init_enabled || generation!=bf_init_generation || !g_initializedForThread) return;
        auto it=bf_notificationLoads.find(handle);
        if (it==bf_notificationLoads.end()) return;
        auto element=it->second.element.get();
        if (!element || element.Name().empty()) return;
        const bool calendar=BF_IsCalendarPart(element.Name());
        if (calendar && !it->second.firstLayout) {
            it->second.firstLayout=element.LayoutUpdated(winrt::auto_revoke,[handle,generation](auto&&,auto&&) {
                BF_NotificationReady(handle,generation);
            });
        }
        if (!element.IsLoaded() || (calendar &&
            (element.ActualWidth()<=0 || element.ActualHeight()<=0 || element.Visibility()!=Visibility::Visible))) return;
        const auto fallback=it->second.fallback;
        BF_RemoveNotificationLoad(handle);
        // Diagnostics may already have released its reference to the hidden
        // tree. Resolve the current identity before handing it to the styler.
        auto id=GetOrCreateElementId(handle,element);
        if (id!=ElementId::None) ApplyCustomizations(id,element,fallback.c_str());
    } catch (...) { Wh_Log(L"Error %08X: first notification presentation",winrt::to_hresult()); }
}

static void BF_QueueNotificationLoaded(const FrameworkElement& element,PCWSTR fallback) {
    if (!bf_init_enabled || (!element.try_as<Controls::Grid>() && !element.try_as<Controls::Border>() &&
                            !element.try_as<Controls::ScrollViewer>())) return;
    const bool unnamed=element.Name().empty();
    const bool calendar=BF_IsCalendarPart(element.Name());
    if (!unnamed && element.IsLoaded() && (!calendar ||
        (element.ActualWidth()>0 && element.ActualHeight()>0 && element.Visibility()==Visibility::Visible))) return;
    const auto handle=HandleFromInspectable(element);
    if (auto found=bf_notificationLoads.find(handle);found!=bf_notificationLoads.end()) {
        if (found->second.element.get()==element) return;
        BF_RemoveNotificationLoad(handle);
    }
    // Weak event sources can disappear without a Remove notification. Leave
    // room for named panel surfaces during large batches of anonymous elements.
    const size_t limit=unnamed?768:1024;
    if (bf_notificationLoads.size()>=limit) {
        std::erase_if(bf_notificationLoads,[](const auto& item){return !item.second.element.get();});
        if (bf_notificationLoads.size()>=limit) return;
    }
    const auto generation=bf_init_generation.load();
    auto& pending=bf_notificationLoads[handle];
    pending.element=winrt::make_weak(element);
    pending.fallback=fallback?fallback:L"";
    if (!element.IsLoaded())
        pending.loaded=element.Loaded(winrt::auto_revoke,[handle,generation](auto&&,auto&&) {
            BF_NotificationReady(handle,generation);
        });
    if (unnamed)
        pending.nameChanged=element.RegisterPropertyChangedCallback(FrameworkElement::NameProperty(),
            [handle,generation](auto&&,auto&&){BF_NotificationReady(handle,generation);});
    if (calendar)
        pending.firstLayout=element.LayoutUpdated(winrt::auto_revoke,[handle,generation](auto&&,auto&&) {
            BF_NotificationReady(handle,generation);
        });
}
