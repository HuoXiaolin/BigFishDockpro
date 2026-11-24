#pragma once

// Opt-in, aggregate counts on Start's own flyouts. A routed event that is
// already handled by Windows is observed without changing its handled state.
struct BF_MenuInputWatch {
    winrt::weak_ref<FrameworkElement> presenter;
    wf::IInspectable pressed{nullptr}, released{nullptr};
    Controls::MenuFlyoutItem::Click_revoker click;
    ~BF_MenuInputWatch() {
        try {
            if (auto node=presenter.get()) {
                if (pressed) node.RemoveHandler(UIElement::PointerPressedEvent(),pressed);
                if (released) node.RemoveHandler(UIElement::PointerReleasedEvent(),released);
            }
        } catch (const winrt::hresult_error&) {}
    }
};
static thread_local std::map<ElementId,BF_MenuInputWatch> bf_menuInputWatches;
static void BF_MenuInputCount(std::atomic<unsigned>& count) {
    ++count;
    if (bf_status_event) SetEvent(bf_status_event);
}
static void BF_ObserveMenuInput(ElementId id,const FrameworkElement& element) {
    if (element.try_as<Controls::MenuFlyoutPresenter>()) {
        try {
            if (auto button=bf_openingFooter.get()) BF_MaskFooterPreview(button);
            else if (bf_contextSource.get()) BF_MaskContextPreview();
        } catch (const winrt::hresult_error&) {}
    }
    if (!bf_traceMenuInput || !bf_is_start_menu || bf_menuInputWatches.contains(id)) return;
    if (element.try_as<Controls::MenuFlyoutPresenter>() || element.try_as<Controls::FlyoutPresenter>()) {
        auto& watch=bf_menuInputWatches[id];
        watch.presenter=winrt::make_weak(element);
        watch.pressed=winrt::box_value(Input::PointerEventHandler([](auto&&,auto&&){BF_MenuInputCount(bf_menuPresses);}));
        watch.released=winrt::box_value(Input::PointerEventHandler([](auto&&,auto&&){BF_MenuInputCount(bf_menuReleases);}));
        element.AddHandler(UIElement::PointerPressedEvent(),watch.pressed,true);
        element.AddHandler(UIElement::PointerReleasedEvent(),watch.released,true);
        BF_MenuInputCount(bf_menuPresenters);
    } else if (auto row=element.try_as<Controls::MenuFlyoutItem>()) {
        bf_menuInputWatches[id].click=row.Click(winrt::auto_revoke,[](auto&&,auto&&){BF_MenuInputCount(bf_menuClicks);});
    }
}
