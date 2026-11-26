#pragma once

// Retain Shell-owned, lazily populated menus in their original XAML tree.
// If they cannot be represented by a USER menu, move only the open popup
// into Start's input area and let its own ScrollViewer handle long lists.
struct BF_InlineMenuPlacement {
    BF_LocalLayout offsets,limits;
    bool fitting=false;
    void restore() {offsets.restore();limits.restore();}
    ~BF_InlineMenuPlacement() {restore();}
    void fit(const Controls::MenuFlyoutPresenter& presenter) {
        if (fitting || presenter.ActualWidth()<1 || presenter.ActualHeight()<1) return;
        auto root=presenter.XamlRoot();
        const auto bounds=BF_StartFlyoutBounds(root);
        if (!bounds || IsRectEmpty(&*bounds)) return;
        for (auto popup:Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(root)) {
            if (!popup.IsOpen() || BF_FooterPresenter(popup.Child())!=presenter) continue;
            fitting=true;
            struct Reset {bool& flag;~Reset(){flag=false;}} reset{fitting};
            const double scale=root.RasterizationScale();
            const auto face=BF_PanelPeer(presenter).GetBoundingRectangle();
            if (face.Width<1 || face.Height<1 || scale<=0) return;
            const auto w=(bounds->right-bounds->left)/scale,h=(bounds->bottom-bounds->top)/scale;
            if (presenter.ActualWidth()>w+.5 && presenter.MaxWidth()>w)
                limits.set(presenter,FrameworkElement::MaxWidthProperty(),winrt::box_value(w));
            if (presenter.ActualHeight()>h+.5 && presenter.MaxHeight()>h)
                limits.set(presenter,FrameworkElement::MaxHeightProperty(),winrt::box_value(h));
            const double x=std::clamp<double>(face.X,bounds->left,std::max<double>(bounds->left,bounds->right-face.Width));
            const double y=std::clamp<double>(face.Y,bounds->top,std::max<double>(bounds->top,bounds->bottom-face.Height));
            if (!offsets.values.empty()) return; // Offset takes effect on the next arrange.
            if (std::abs(x-face.X)>1)
                offsets.set(popup,BF_FooterPopup::HorizontalOffsetProperty(),winrt::box_value(popup.HorizontalOffset()+(x-face.X)/scale));
            if (std::abs(y-face.Y)>1)
                offsets.set(popup,BF_FooterPopup::VerticalOffsetProperty(),winrt::box_value(popup.VerticalOffset()+(y-face.Y)/scale));
            return;
        }
    }
};

// Opt-in, aggregate counts on Start's own flyouts. A routed event that is
// already handled by Windows is observed without changing its handled state.
struct BF_MenuInputWatch {
    winrt::weak_ref<FrameworkElement> presenter;
    wf::IInspectable pressed{nullptr}, released{nullptr};
    Controls::MenuFlyoutItem::Click_revoker click;
    std::shared_ptr<BF_InlineMenuPlacement> placement;
    FrameworkElement::Loaded_revoker loaded;
    FrameworkElement::SizeChanged_revoker resized;
    FrameworkElement::Unloaded_revoker unloaded;
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
static void BF_FitOriginalStartMenu(const Controls::MenuFlyoutPresenter& presenter) {
    for (auto& [id,watch]:bf_menuInputWatches) if (watch.placement && watch.presenter.get()==presenter) {
        const auto placement=watch.placement;
        placement->fit(presenter);return;
    }
}
static void BF_MenuInputCount(std::atomic<unsigned>& count) {
    ++count;
    if (bf_status_event) SetEvent(bf_status_event);
}
static void BF_ObserveMenuInput(ElementId id,const FrameworkElement& element) {
    if (!bf_is_start_menu || bf_menuInputWatches.contains(id)) return;
    if (auto menu=element.try_as<Controls::MenuFlyoutPresenter>()) {
        try {
            if (auto button=bf_openingFooter.get()) BF_MaskFooterPreview(button);
            else if (bf_contextSource.get()) BF_MaskContextPreview();
        } catch (const winrt::hresult_error&) {}
        auto& watch=bf_menuInputWatches[id];
        watch.presenter=winrt::make_weak(element);
        watch.placement=std::make_shared<BF_InlineMenuPlacement>();
        auto fit=[weak=std::weak_ptr(watch.placement),source=winrt::make_weak(menu)](auto&&,auto&&) {
            if (bf_contextSource.get() || bf_activeFooter || bf_openingFooter.get()) return;
            try {if (auto state=weak.lock()) if (auto live=source.get()) state->fit(live);}
            catch (const winrt::hresult_error&) {}
        };
        watch.loaded=menu.Loaded(winrt::auto_revoke,fit);
        watch.resized=menu.SizeChanged(winrt::auto_revoke,fit);
        watch.unloaded=menu.Unloaded(winrt::auto_revoke,[weak=std::weak_ptr(watch.placement)](auto&&,auto&&) {
            if (auto state=weak.lock()) state->restore();
        });
        if (menu.IsLoaded()) fit(menu,nullptr);
    }
    if (!bf_traceMenuInput) return;
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
