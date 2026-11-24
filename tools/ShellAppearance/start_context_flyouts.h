#pragma once
#include <winrt/Windows.Devices.Input.h>

static thread_local DispatcherTimer bf_contextTimer{nullptr};
static thread_local unsigned bf_contextRequest=0;
static thread_local winrt::weak_ref<FrameworkElement> bf_contextSource;
static thread_local std::shared_ptr<BF_FooterPreview> bf_contextPreview;
static thread_local winrt::event_token bf_contextRendering{};

static void BF_StopContextRequest() {
    ++bf_contextRequest;
    if (auto timer=std::exchange(bf_contextTimer,nullptr)) timer.Stop();
    bf_contextSource={};
    if (bf_contextRendering.value) {
        const auto token=std::exchange(bf_contextRendering,winrt::event_token{});
        try {Media::CompositionTarget::Rendering(token);} catch (const winrt::hresult_error&) {}
    }
    bf_contextPreview.reset();
}

static void BF_MaskContextPreview() {
    auto source=bf_contextSource.get();
    auto root=source ? source.XamlRoot() : nullptr;
    if (!root || bf_activeFooter || bf_openingFooter.get()) return;
    const auto popups=Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(root);
    for (auto i=popups.Size();i>0;--i) {
        auto popup=popups.GetAt(i-1);
        auto content=popup.Child();
        if (!popup.IsOpen() || !BF_FooterPresenter(content)) continue;
        BF_MaskFlyout(content,bf_contextPreview);
        return;
    }
}

static void BF_ArmContextPreview(const FrameworkElement& source) {
    if (auto previous=bf_contextSource.get();previous && previous.XamlRoot()==source.XamlRoot()) {
        bf_contextSource=winrt::make_weak(source);
        BF_MaskContextPreview();
        return;
    }
    BF_StopContextRequest();
    bf_contextSource=winrt::make_weak(source);
    const auto started=GetTickCount64();
    bf_contextRendering=Media::CompositionTarget::Rendering([started](auto&&,auto&&) {
        try {
            if (!bf_contextSource.get() || (!bf_contextTimer && GetTickCount64()-started>1000))
                BF_StopContextRequest();
            else BF_MaskContextPreview();
        } catch (const winrt::hresult_error&) {BF_StopContextRequest();}
    });
    BF_MaskContextPreview();
}

static void BF_HideStartContext(const FrameworkElement& source,const Controls::MenuFlyoutPresenter& presenter,
                                const BF_FooterPopup& popup) {
    for (DependencyObject node=source;node;node=Media::VisualTreeHelper::GetParent(node)) {
        auto owner=node.try_as<UIElement>();
        auto menu=owner ? owner.ContextFlyout().try_as<Controls::MenuFlyout>() : nullptr;
        uint32_t index=0;
        if (menu && menu.Items().Size() && presenter.Items().IndexOf(menu.Items().GetAt(0),index)) {
            menu.Hide();
            break;
        }
    }
    if (popup.IsOpen()) popup.IsOpen(false);
}

static bool BF_TryStartContextMenu(const FrameworkElement& source,HWND window,POINT pointer) {
    auto root=source.XamlRoot();
    if (!root || !source.IsLoaded() || !IsWindow(window)) return true;
    if (bf_activeFooter || bf_openingFooter.get()) return true;
    auto popups=Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(root);
    for (auto i=popups.Size();i>0;--i) {
        auto popup=popups.GetAt(i-1);
        if (!popup.IsOpen()) continue;
        auto presenter=BF_FooterPresenter(popup.Child());
        if (!presenter || presenter.ActualHeight()<1 || !presenter.Items().Size()) continue;
        const auto face=BF_PanelPeer(presenter).GetBoundingRectangle();
        const double margin=16*root.RasterizationScale();
        const bool atPointer=pointer.x>=face.X-margin && pointer.x<=face.X+face.Width+margin &&
                             pointer.y>=face.Y-margin && pointer.y<=face.Y+face.Height+margin;
        if (atPointer && BF_ReachableMenuRows(presenter,face)) return true;

        auto menu=BF_CopyStartMenu(presenter,source,window);
        if (!menu) return true;
        BF_MaskFlyout(popup.Child(),bf_contextPreview);
        auto preview=std::move(bf_contextPreview);
        // Keep the source masked through close and any outgoing animation.
        BF_HideStartContext(source,presenter,popup);
        BF_StopContextRequest();
        const auto generation=bf_contextRequest;
        const auto rtl=source.FlowDirection()==FlowDirection::RightToLeft;
        const RECT anchor{pointer.x,pointer.y,pointer.x,pointer.y};
        source.Dispatcher().RunAsync(winrt::Windows::UI::Core::CoreDispatcherPriority::Normal,
            [menu,anchor,rtl,popup,generation,preview] {
                auto live=menu->anchor.get();
                if (generation!=bf_contextRequest || !live || !live.IsLoaded() || popup.IsOpen() ||
                    !IsWindow(menu->owner) || !IsWindowVisible(menu->owner)) return;
                try {BF_TrackFooter(*menu,anchor,rtl,BF_OpenFooterSettings,true);}
                catch (const winrt::hresult_error& error) {Wh_Log(L"Error %08X: Start context command",error.code());}
            });
        return true;
    }
    return false;
}

static void BF_QueueStartContextMenu(const FrameworkElement& source,POINT pointer) {
    const auto window=BF_LayoutWindow();
    if (!window || bf_activeFooter || bf_openingFooter.get()) return;
    BF_ArmContextPreview(source);
    if (auto timer=std::exchange(bf_contextTimer,nullptr)) timer.Stop();
    const auto generation=++bf_contextRequest;
    const auto started=GetTickCount64();
    bf_contextTimer=DispatcherTimer();
    bf_contextTimer.Interval(std::chrono::milliseconds(45));
    bf_contextTimer.Tick([weak=winrt::make_weak(source),window,pointer,generation,started](auto&&,auto&&) {
        if (generation!=bf_contextRequest) return;
        try {
            auto live=weak.get();
            const auto elapsed=GetTickCount64()-started;
            if (!live || elapsed>450 || (elapsed>=80 && BF_TryStartContextMenu(live,window,pointer)))
                if (generation==bf_contextRequest) BF_StopContextRequest();
        } catch (const winrt::hresult_error& error) {
            BF_StopContextRequest();
            Wh_Log(L"Error %08X: Start context menu",error.code());
        }
    });
    bf_contextTimer.Start();
}

struct BF_StartContextWatch {
    winrt::weak_ref<FrameworkElement> root;
    wf::IInspectable pressed{nullptr},tapped{nullptr};
    ~BF_StartContextWatch() {
        if (auto live=root.get()) try {
            if (pressed) live.RemoveHandler(UIElement::PointerPressedEvent(),pressed);
            if (tapped) live.RemoveHandler(UIElement::RightTappedEvent(),tapped);
        } catch (const winrt::hresult_error&) {}
    }
};
static thread_local std::unique_ptr<BF_StartContextWatch> bf_startContextWatch;

static void BF_WatchStartContext(const XamlRoot& xaml) {
    auto root=xaml ? xaml.Content().try_as<FrameworkElement>() : nullptr;
    if (!root || (bf_startContextWatch && bf_startContextWatch->root.get()==root)) return;
    auto watch=std::make_unique<BF_StartContextWatch>();
    watch->root=winrt::make_weak(root);
    watch->pressed=winrt::box_value(Input::PointerEventHandler([weak=watch->root](auto&&,const Input::PointerRoutedEventArgs& args) {
        auto live=weak.get();
        if (!live || bf_activeFooter || bf_openingFooter.get()) return;
        const auto point=args.GetCurrentPoint(live);
        if (point.PointerDevice().PointerDeviceType()!=winrt::Windows::Devices::Input::PointerDeviceType::Mouse ||
            point.Properties().PointerUpdateKind()!=winrt::Windows::UI::Input::PointerUpdateKind::RightButtonPressed) return;
        try {BF_ArmContextPreview(live);} catch (const winrt::hresult_error&) {BF_StopContextRequest();}
    }));
    watch->tapped=winrt::box_value(Input::RightTappedEventHandler([weak=watch->root](auto&&,const Input::RightTappedRoutedEventArgs& args) {
        if (args.PointerDeviceType()!=winrt::Windows::Devices::Input::PointerDeviceType::Mouse) return;
        POINT point{};
        if (!GetCursorPos(&point)) return;
        auto source=args.OriginalSource().try_as<FrameworkElement>();
        if (!source) source=weak.get();
        if (source) try {BF_QueueStartContextMenu(source,point);}
        catch (const winrt::hresult_error&) {BF_StopContextRequest();}
    }));
    root.AddHandler(UIElement::PointerPressedEvent(),watch->pressed,true);
    root.AddHandler(UIElement::RightTappedEvent(),watch->tapped,true);
    bf_startContextWatch=std::move(watch);
}
