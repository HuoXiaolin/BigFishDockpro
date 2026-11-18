#pragma once

#include <commctrl.h>
#include <optional>
#include <winrt/Windows.UI.Xaml.Automation.Peers.h>

HWND GetCoreWnd();
using BF_PanelPeer = winrt::Windows::UI::Xaml::Automation::Peers::FrameworkElementAutomationPeer;

// The window associated with this UI thread is the origin of the XAML
// viewport. A process can also own unrelated CoreWindow instances.
static HWND BF_LayoutWindow() {
    struct CoreWindowInterop : IUnknown {
        virtual HRESULT STDMETHODCALLTYPE get_WindowHandle(HWND*) = 0;
    };
    constexpr winrt::guid interfaceId{0x45d64a29,0xa63e,0x4cb6,{0xb4,0x98,0x57,0x81,0xd2,0x98,0xcb,0x4f}};
    auto core = winrt::Windows::UI::Core::CoreWindow::GetForCurrentThread();
    if (core) {
        winrt::com_ptr<CoreWindowInterop> interop;
        HWND window = nullptr;
        if (SUCCEEDED(reinterpret_cast<IUnknown*>(winrt::get_abi(core))->QueryInterface(interfaceId, interop.put_void())) &&
            SUCCEEDED(interop->get_WindowHandle(&window)) && window) return window;
    }
    auto window = GetCoreWnd();
    return window && GetWindowThreadProcessId(window, nullptr)==GetCurrentThreadId() ? window : nullptr;
}

// Pack the pixel rectangle into a single atomic value for the other host.
static uintptr_t BF_EncodePanelRect(const RECT& rect) {
    const auto width = rect.right - rect.left, height = rect.bottom - rect.top;
    if (width < 1 || width > UINT16_MAX || height < 1 || height > UINT16_MAX ||
        rect.left < INT16_MIN || rect.left > INT16_MAX || rect.top < INT16_MIN || rect.top > INT16_MAX) return 0;
    return static_cast<uintptr_t>(static_cast<uint16_t>(rect.left)) |
           (static_cast<uintptr_t>(static_cast<uint16_t>(rect.top)) << 16) |
           (static_cast<uintptr_t>(width) << 32) | (static_cast<uintptr_t>(height) << 48);
}

static std::optional<RECT> BF_PanelScreenRect(const FrameworkElement& panel, HWND window) {
    auto root = panel.XamlRoot();
    if (!root || panel.ActualWidth() < 1 || panel.ActualHeight() < 1 || !window) return std::nullopt;
    POINT clientOrigin{};
    if (!ClientToScreen(window, &clientOrigin)) return std::nullopt;
    // nullptr includes the offsets of the root content and its presenter.
    auto bounds = panel.TransformToVisual(nullptr).TransformBounds(
        {0, 0, static_cast<float>(panel.ActualWidth()), static_cast<float>(panel.ActualHeight())});
    const double scale = root.RasterizationScale();
    const auto x = [&](double value) { return clientOrigin.x + std::lround(value * scale); };
    const auto y = [&](double value) { return clientOrigin.y + std::lround(value * scale); };
    return RECT{x(bounds.X), y(bounds.Y), x(bounds.X + bounds.Width), y(bounds.Y + bounds.Height)};
}

static RECT BF_ClientScreenRect(HWND window) {
    RECT rect{};
    GetClientRect(window,&rect);
    MapWindowPoints(window,nullptr,reinterpret_cast<POINT*>(&rect),2);
    return rect;
}

static bool BF_ContainsPanel(const RECT& viewport,const RECT& panel) {
    return panel.left>=viewport.left-1 && panel.top>=viewport.top-1 &&
        panel.right<=viewport.right+1 && panel.bottom<=viewport.bottom+1;
}

static bool BF_FullPanel(const RECT& rect, HWND layoutWindow, const BF_PanelPeer& peer) {
    if (!BF_ContainsPanel(BF_ClientScreenRect(layoutWindow),rect)) return false;
    // The peer provides clipped extents. Its origin can be island-relative,
    // so the physical origin comes from the layout window and full XAML tree.
    const auto visible = peer.GetBoundingRectangle();
    return std::abs(visible.Width-(rect.right-rect.left))<=1.5 &&
           std::abs(visible.Height-(rect.bottom-rect.top))<=1.5;
}

static void BF_RecordPanel(std::atomic<uintptr_t>& field, const RECT& rect) {
    const auto packed = BF_EncodePanelRect(rect);
    if (field.exchange(packed)!=packed && bf_status_event) SetEvent(bf_status_event);
}

struct BF_StartFrame {
    winrt::weak_ref<FrameworkElement> frame, panel;
    FrameworkElement::LayoutUpdated_revoker layout;
    wf::IInspectable originalOpacity;
    BF_PanelPeer peer{nullptr};
    HWND window = nullptr;
    HWND hostWindow = nullptr;
    UINT_PTR revealTimer = 0;
    UINT_PTR boundsTimer = 0;
    bool preparing = true;
};

static thread_local std::optional<BF_StartFrame> bf_startFrame;

static void BF_PublishStartPanel() {
    if (!bf_startFrame) return;
    auto& state = *bf_startFrame;
    auto panel = state.panel.get();
    if (!panel) return;
    if (!state.preparing && BF_StartMenuFlyoutOpen(panel)) return;
    if (!state.window) state.window = BF_LayoutWindow();
    try {
        auto rect = BF_PanelScreenRect(panel, state.window);
        if (!rect || !BF_FullPanel(*rect,state.window,state.peer)) return;
        if (!IsWindowVisible(state.window)) return;
        MONITORINFO display{sizeof(display)};
        auto monitor=MonitorFromWindow(state.window,MONITOR_DEFAULTTONULL);
        if (!monitor || !GetMonitorInfoW(monitor,&display) || !BF_ContainsPanel(display.rcWork,*rect)) return;
        const auto value = BF_EncodePanelRect(*rect);
        if (!value) return;
        BF_WritePanelGeometry(value);
        BF_RecordPanel(bf_startScreenBounds,*rect);
        const auto width = static_cast<unsigned>(std::lround(panel.ActualWidth()));
        const auto height = static_cast<unsigned>(std::lround(panel.ActualHeight()));
        const bool widthChanged = bf_start_width.exchange(width) != width;
        const bool heightChanged = bf_start_height.exchange(height) != height;
        if ((widthChanged || heightChanged) && bf_status_event) SetEvent(bf_status_event);
    } catch (const winrt::hresult_error& error) {
        Wh_Log(L"Error %08X: Start panel bounds", error.code());
    }
}

static void BF_RevealStartFrame() {
    if (!bf_startFrame || !bf_startFrame->preparing) return;
    auto& state = *bf_startFrame;
    state.preparing = false;
    if (state.revealTimer) KillTimer(nullptr, std::exchange(state.revealTimer, 0));
    if (auto frame = state.frame.get()) {
        if (state.originalOpacity == DependencyProperty::UnsetValue()) frame.ClearValue(UIElement::OpacityProperty());
        else frame.SetValue(UIElement::OpacityProperty(), state.originalOpacity);
    }
    state.originalOpacity = nullptr;
}

static LRESULT CALLBACK BF_StartWindowSubclass(HWND window,UINT message,WPARAM wParam,LPARAM lParam,UINT_PTR id,DWORD_PTR);

static void BF_ClearStartFrames() {
    if (!bf_startFrame) return;
    BF_RevealStartFrame();
    if (bf_startFrame->boundsTimer) KillTimer(nullptr,bf_startFrame->boundsTimer);
    if (bf_startFrame->hostWindow) RemoveWindowSubclass(bf_startFrame->hostWindow,BF_StartWindowSubclass,reinterpret_cast<UINT_PTR>(&bf_startFrame));
    BF_WritePanelGeometry(0);
    bf_startFrame.reset();
    bf_startScreenBounds=0;
    bf_start_width = bf_start_height = 0;
}

static void CALLBACK BF_RevealPreparedStartFrame(HWND, UINT, UINT_PTR, DWORD) {
    try {
        BF_PublishStartPanel();
        BF_RevealStartFrame();
    } catch (const winrt::hresult_error& error) {
        Wh_Log(L"Error %08X: Start panel first frame", error.code());
    }
}

static void CALLBACK BF_RecordVisibleStartBounds(HWND,UINT,UINT_PTR timer,DWORD) {
    KillTimer(nullptr,timer);
    if (bf_startFrame && bf_startFrame->boundsTimer==timer) {
        bf_startFrame->boundsTimer=0;
        BF_PublishStartPanel();
    }
}

static LRESULT CALLBACK BF_StartWindowSubclass(HWND window,UINT message,WPARAM wParam,LPARAM lParam,UINT_PTR id,DWORD_PTR) {
    if (message==WM_NCDESTROY) RemoveWindowSubclass(window,BF_StartWindowSubclass,id);
    auto result=DefSubclassProc(window,message,wParam,lParam);
    if (auto& state=bf_startFrame;state && (message==WM_WINDOWPOSCHANGED || message==WM_DPICHANGED || (message==WM_SHOWWINDOW && wParam))) {
        if (state->boundsTimer) KillTimer(nullptr,state->boundsTimer);
        state->boundsTimer=SetTimer(nullptr,0,160,BF_RecordVisibleStartBounds);
    }
    return result;
}

static void BF_PrepareStartFrame(const FrameworkElement& frame, const FrameworkElement& panel, HWND window) {
    if (bf_startFrame && bf_startFrame->panel.get() == panel) return;
    BF_ClearStartFrames();
    auto& state = bf_startFrame.emplace();
    state.frame = winrt::make_weak(frame);
    state.panel = winrt::make_weak(panel);
    state.peer = BF_PanelPeer(panel);
    state.window = window;
    state.hostWindow=window ? GetAncestor(window,GA_ROOT) : nullptr;
    if (state.hostWindow) SetWindowSubclass(state.hostWindow,BF_StartWindowSubclass,reinterpret_cast<UINT_PTR>(&bf_startFrame),0);
    state.layout = panel.LayoutUpdated(winrt::auto_revoke, [](auto&&, auto&&) { BF_PublishStartPanel(); });
    state.originalOpacity = frame.ReadLocalValue(UIElement::OpacityProperty());
    frame.Opacity(0);
    state.revealTimer = SetTimer(nullptr, 0, 24, BF_RevealPreparedStartFrame);
    if (!state.revealTimer) BF_RevealPreparedStartFrame(nullptr, 0, 0, 0);
}

static FrameworkElement BF_StartPanelParent(const FrameworkElement& element) {
    if (element.Name() != L"AcrylicBorder" || !element.try_as<Controls::Border>()) return nullptr;
    auto parent = Media::VisualTreeHelper::GetParent(element).try_as<Controls::Grid>();
    if (parent && (parent.Name() == L"RootContent" || parent.Name() == L"MainMenu")) return parent;
    return nullptr;
}

static bool BF_CoincidentPanels(const RECT& a, const RECT& b) {
    // Layout round-off on a fractional display scale can differ by one pixel.
    return std::abs(a.left-b.left) <= 1 && std::abs(a.top-b.top) <= 1 &&
           std::abs(a.right-b.right) <= 1 && std::abs(a.bottom-b.bottom) <= 1;
}

static constexpr UINT BF_SearchMoveFlags = SWP_NOACTIVATE | SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_NOCOPYBITS;
struct BF_SearchFrame {
    winrt::weak_ref<FrameworkElement> panel, input;
    FrameworkElement::LayoutUpdated_revoker layout;
    BF_PanelPeer peer{nullptr};
    HWND layoutWindow = nullptr, window = nullptr;
    UINT_PTR repositionTimer = 0;
    unsigned revealStep = 0;
    std::optional<RECT> originalWindow, alignedWindow;
    BF_LocalLayout rootLayout;
    std::vector<BF_LocalLayout> chrome;
    bool moving = false, prepared = false;
};
static thread_local std::optional<BF_SearchFrame> bf_searchFrame;

static std::optional<RECT> BF_SearchAnchor(const RECT& logicalWindow,const RECT& panel,const MONITORINFO& display,
                                          LONG inset) {
    const auto& work=display.rcWork;
    const auto width=panel.right-panel.left,height=panel.bottom-panel.top;
    if (width>work.right-work.left || height>work.bottom-work.top) return std::nullopt;
    const LONG left=logicalWindow.left<=work.left+inset*2 ? work.left+inset :
                    logicalWindow.left+(logicalWindow.right-logicalWindow.left-width)/2;
    const LONG top=work.top>display.rcMonitor.top ? work.top+inset : work.bottom-inset-height;
    const LONG x=std::clamp(left,work.left,work.right-width);
    const LONG y=std::clamp(top,work.top,work.bottom-height);
    return RECT{x,y,x+width,y+height};
}

static bool BF_SetSearchWindow(HWND window,const RECT& rect) {
    return SetWindowPos(window,nullptr,rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top,BF_SearchMoveFlags);
}

static void BF_FitSearchChrome(BF_SearchFrame& search,const FrameworkElement& panel,const FrameworkElement& root) {
    // The automation peer clips at *every* ancestor. Translating the outer
    // HWND cannot recover pixels consumed by the search host's shadow slot.
    for (auto child=panel;child && child!=root;) {
        auto parent=Media::VisualTreeHelper::GetParent(child).try_as<FrameworkElement>();
        if (!parent) break;
        auto saved=[&](const FrameworkElement& part)->BF_LocalLayout& {
            for (auto& entry:search.chrome) if (entry.element.get()==part) return entry;
            auto& entry=search.chrome.emplace_back();entry.element=winrt::make_weak(part);return entry;
        };
        if (child.Name()==L"BorderGrid" || child.Name()==L"OuterBorderGrid") {
            if (auto grid=parent.try_as<Controls::Grid>()) {
                const int columns=static_cast<int>(std::max(1u,grid.ColumnDefinitions().Size()));
                const int rows=static_cast<int>(std::max(1u,grid.RowDefinitions().Size()));
                if (Controls::Grid::GetColumn(child)!=0) saved(child).set(child,Controls::Grid::ColumnProperty(),winrt::box_value(0));
                if (Controls::Grid::GetRow(child)!=0) saved(child).set(child,Controls::Grid::RowProperty(),winrt::box_value(0));
                if (Controls::Grid::GetColumnSpan(child)!=columns) saved(child).set(child,Controls::Grid::ColumnSpanProperty(),winrt::box_value(columns));
                if (Controls::Grid::GetRowSpan(child)!=rows) saved(child).set(child,Controls::Grid::RowSpanProperty(),winrt::box_value(rows));
            }
        }
        if (parent.Margin()!=Thickness{})
            saved(parent).set(parent,FrameworkElement::MarginProperty(),winrt::box_value(Thickness{}));
        if (auto border=parent.try_as<Controls::Border>();border && border.Padding()!=Thickness{})
            saved(parent).set(parent,Controls::Border::PaddingProperty(),winrt::box_value(Thickness{}));
        else if (auto grid=parent.try_as<Controls::Grid>();grid && grid.Padding()!=Thickness{})
            saved(parent).set(parent,Controls::Grid::PaddingProperty(),winrt::box_value(Thickness{}));
        else if (auto control=parent.try_as<Controls::Control>();control && control.Padding()!=Thickness{})
            saved(parent).set(parent,Controls::Control::PaddingProperty(),winrt::box_value(Thickness{}));
        else if (auto presenter=parent.try_as<Controls::ContentPresenter>();presenter && presenter.Padding()!=Thickness{})
            saved(parent).set(parent,Controls::ContentPresenter::PaddingProperty(),winrt::box_value(Thickness{}));
        if (auto clip=parent.Clip()) {
            const auto rect=clip.Rect();
            if (rect.X>.5 || rect.Y>.5 || rect.X+rect.Width<panel.ActualWidth()-.5 || rect.Y+rect.Height<panel.ActualHeight()-.5)
                saved(parent).set(parent,UIElement::ClipProperty(),nullptr);
        }
        child=parent;
    }
}

static bool BF_SearchInputVisible(BF_SearchFrame& search, const RECT& panel) {
    auto input=search.input.get();
    if (input && input.IsLoaded() && input.Visibility()==Visibility::Visible) {
        if (auto box=BF_PanelScreenRect(input,search.layoutWindow)) {
            BF_RecordPanel(bf_searchInputBounds,*box);
            const auto visible=BF_PanelPeer(input).GetBoundingRectangle();
            return box->bottom-box->top>8 && box->right-box->left>32 && BF_ContainsPanel(panel,*box) &&
                visible.Height>=box->bottom-box->top-2 && visible.Width>=box->right-box->left-2;
        }
    }
    if (bf_searchInputBounds.exchange(0) && bf_status_event) SetEvent(bf_status_event);
    return false;
}

static bool BF_AlignSearchPanel(BF_SearchFrame& search, const FrameworkElement& panel, bool presenting) {
    if (search.moving) return false;
    search.moving=true;
    struct MovingGuard {bool& flag;~MovingGuard(){flag=false;}} guard{search.moving};
    auto current = BF_PanelScreenRect(panel, search.layoutWindow);
    if (!current) return false;
    BF_RecordPanel(bf_searchScreenBounds,*current);
    RECT windowRect{};
    if (!GetWindowRect(search.window,&windowRect)) return false;
    auto viewport=BF_ClientScreenRect(search.layoutWindow);
    BF_RecordPanel(bf_searchViewportBounds,viewport);
    const auto visible=search.peer.GetBoundingRectangle();
    bf_searchVisibleWidth=std::lround(visible.Width);bf_searchVisibleHeight=std::lround(visible.Height);
    const auto monitor=MonitorFromWindow(search.window,MONITOR_DEFAULTTONULL);
    MONITORINFO display{sizeof(display)};
    if (!monitor || !GetMonitorInfoW(monitor,&display)) return false;
    if (!search.alignedWindow || !EqualRect(&windowRect,&*search.alignedWindow)) search.originalWindow=windowRect;

    std::optional<RECT> target;
    bool matchedStart=false;
    const auto value = BF_ReadPanelGeometry();
    if (value) {
        const auto start=BF_DecodePanelRect(value);
        auto shifted=*current;
        OffsetRect(&shifted,start.left-current->left,start.top-current->top);
        if (MonitorFromRect(&start,MONITOR_DEFAULTTONULL)==monitor && BF_ContainsPanel(display.rcWork,start) &&
            BF_CoincidentPanels(shifted,start)) {
            target=start;
            matchedStart=true;
        }
    }
    if (!target) {
        const auto inset=std::lround(12*panel.XamlRoot().RasterizationScale());
        target=BF_SearchAnchor(*search.originalWindow,*current,display,inset);
    }
    if (!target) return false;
    if (search.prepared && !presenting && BF_CoincidentPanels(*current,*target) &&
        BF_CoincidentPanels(viewport,*target) && BF_FullPanel(*current,search.layoutWindow,search.peer))
        return BF_SearchInputVisible(search,*current) && matchedStart;

    // Size the viewport itself, independently of the page's native centering.
    // Adding the current page offset to the window height feeds that new height
    // back into centering on the next layout and can grow the host offscreen.
    const LONG dx=target->left-viewport.left,dy=target->top-viewport.top;
    RECT aligned{windowRect.left+dx,windowRect.top+dy,
                 target->right+std::max(0L,windowRect.right-viewport.right),
                 target->bottom+std::max(0L,windowRect.bottom-viewport.bottom)};
    const bool moved=!EqualRect(&windowRect,&aligned);
    if (moved && !BF_SetSearchWindow(search.window,aligned)) return false;
    RECT applied{};
    if (GetWindowRect(search.window,&applied)) search.alignedWindow=applied;
    auto root=panel.XamlRoot().Content().try_as<FrameworkElement>();
    if (root) {
        BF_FitSearchChrome(search,panel,root);
        if (!search.prepared) {
            search.rootLayout.set(root,FrameworkElement::MarginProperty(),winrt::box_value(Thickness{}));
            search.rootLayout.set(root,FrameworkElement::MinWidthProperty(),winrt::box_value(0.0));
            search.rootLayout.set(root,FrameworkElement::MinHeightProperty(),winrt::box_value(0.0));
            search.rootLayout.set(root,FrameworkElement::WidthProperty(),winrt::box_value(panel.ActualWidth()));
            search.rootLayout.set(root,FrameworkElement::HeightProperty(),winrt::box_value(panel.ActualHeight()));
            search.rootLayout.set(root,FrameworkElement::HorizontalAlignmentProperty(),winrt::box_value(HorizontalAlignment::Left));
            search.rootLayout.set(root,FrameworkElement::VerticalAlignmentProperty(),winrt::box_value(VerticalAlignment::Top));
            // Search animates its own compositor root. Sampling that animation
            // into an extra translation can leave only a strip until the next input.
            search.prepared=true;
        }
        if (!search.input.get() && (presenting || moved)) {
            for (auto name:{L"SearchTextBox",L"SearchBoxControl",L"TaskbarSearchBackground"}) {
                auto part=BF_FindLayoutElement(root,name,18);
                if (part) { search.input=winrt::make_weak(part);break; }
            }
        }
        if (presenting || moved) root.InvalidateArrange();
        root.UpdateLayout();
        if (presenting || moved) RedrawWindow(search.window,nullptr,nullptr,RDW_INVALIDATE|RDW_ALLCHILDREN);
    }
    auto result=BF_PanelScreenRect(panel,search.layoutWindow);
    if (!result) return false;
    BF_RecordPanel(bf_searchScreenBounds,*result);
    BF_RecordPanel(bf_searchViewportBounds,BF_ClientScreenRect(search.layoutWindow));
    const bool inputVisible=BF_SearchInputVisible(search,*result);
    return matchedStart && inputVisible && BF_CoincidentPanels(*result,*target) && BF_FullPanel(*result,search.layoutWindow,search.peer);
}

static void BF_UpdateSearchPanel(bool presenting=false) {
    if (!bf_searchFrame || bf_searchFrame->moving) return;
    auto panel = bf_searchFrame->panel.get();
    try {
        const auto aligned = panel && BF_AlignSearchPanel(*bf_searchFrame, panel,presenting);
        if (bf_search_position_ready.exchange(aligned) != aligned && bf_status_event) SetEvent(bf_status_event);
    } catch (const winrt::hresult_error& error) {
        Wh_Log(L"Error %08X: Search panel bounds", error.code());
    }
}

static void CALLBACK BF_RepositionSearchPanel(HWND, UINT, UINT_PTR timer, DWORD) {
    KillTimer(nullptr, timer);
    if (bf_searchFrame && bf_searchFrame->repositionTimer == timer) {
        bf_searchFrame->repositionTimer = 0;
        if (!IsWindowVisible(bf_searchFrame->window)) return;
        BF_UpdateSearchPanel(true);
        // A direct Win+S reveal can end its composition animation without a
        // second LayoutUpdated. Repaint at the end even if the frame was ready early.
        constexpr UINT delays[]{65,180,380,650};
        if (bf_searchFrame && bf_searchFrame->revealStep<std::size(delays) &&
            (bf_searchFrame->revealStep<2 || !bf_search_position_ready)) {
            auto delay=delays[bf_searchFrame->revealStep++];
            bf_searchFrame->repositionTimer=SetTimer(nullptr,0,delay,BF_RepositionSearchPanel);
        }
    }
}

static LRESULT CALLBACK BF_SearchWindowSubclass(HWND window, UINT message, WPARAM wParam, LPARAM lParam,
                                              UINT_PTR id, DWORD_PTR) {
    if (message == WM_NCDESTROY) RemoveWindowSubclass(window, BF_SearchWindowSubclass, id);
    const auto result = DefSubclassProc(window, message, wParam, lParam);
    if (auto& state = bf_searchFrame; state && !state->moving && !state->repositionTimer &&
        (message == WM_WINDOWPOSCHANGED || message == WM_DPICHANGED || (message == WM_SHOWWINDOW && wParam))) {
        state->revealStep=0;
        state->repositionTimer = SetTimer(nullptr, 0, 16, BF_RepositionSearchPanel);
    }
    return result;
}

static void BF_ClearSearchFrames() {
    if (!bf_searchFrame) return;
    auto& state = *bf_searchFrame;
    state.layout.revoke();
    state.rootLayout.restore();
    for (auto it=state.chrome.rbegin();it!=state.chrome.rend();++it) it->restore();
    if (state.repositionTimer) KillTimer(nullptr, state.repositionTimer);
    RemoveWindowSubclass(state.window, BF_SearchWindowSubclass, reinterpret_cast<UINT_PTR>(&bf_searchFrame));
    RECT current{};
    if (state.originalWindow && state.alignedWindow && GetWindowRect(state.window,&current) &&
        EqualRect(&current,&*state.alignedWindow)) BF_SetSearchWindow(state.window,*state.originalWindow);
    bf_searchFrame.reset();
    bf_search_position_ready = false;
    bf_searchScreenBounds=bf_searchViewportBounds=bf_searchInputBounds=0;
    bf_searchVisibleWidth=bf_searchVisibleHeight=0;
}

static void BF_TrackSearchFrame(const FrameworkElement& element, HWND layoutWindow) {
    if (element.Name() != L"AppBorder" || !element.try_as<Controls::Border>()) return;
    auto window=GetAncestor(layoutWindow,GA_ROOT);
    if (!window || GetWindowThreadProcessId(window, nullptr) != GetCurrentThreadId()) return;
    auto borderGrid = Media::VisualTreeHelper::GetParent(element).try_as<Controls::Grid>();
    if (!borderGrid || borderGrid.Name() != L"BorderGrid") return;
    auto outerGrid = Media::VisualTreeHelper::GetParent(borderGrid).try_as<Controls::Grid>();
    if (!outerGrid || outerGrid.Name() != L"OuterBorderGrid") return;
    if (bf_searchFrame && bf_searchFrame->panel.get() == element) return;
    BF_ClearSearchFrames();
    auto& state = bf_searchFrame.emplace();
    state.panel = winrt::make_weak(element);
    state.peer = BF_PanelPeer(element);
    state.layoutWindow = layoutWindow;
    state.window = window;
    state.layout = element.LayoutUpdated(winrt::auto_revoke, [](auto&&, auto&&) { BF_UpdateSearchPanel(); });
    SetWindowSubclass(window, BF_SearchWindowSubclass, reinterpret_cast<UINT_PTR>(&bf_searchFrame), 0);
    state.repositionTimer=SetTimer(nullptr,0,16,BF_RepositionSearchPanel);
}

static void BF_WatchShellPanel(const FrameworkElement& element) {
    if (bf_is_start_menu) {
        if (auto parent = BF_StartPanelParent(element)) BF_PrepareStartFrame(parent, element, BF_LayoutWindow());
    } else if (element.Name() == L"AppBorder") {
        BF_TrackSearchFrame(element, BF_LayoutWindow());
    }
}
