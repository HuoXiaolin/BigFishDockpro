#pragma once

#include <winrt/Windows.UI.Xaml.Automation.h>
#include <winrt/Windows.UI.Xaml.Automation.Peers.h>
#include <winrt/Windows.UI.Xaml.Automation.Provider.h>
#include <winrt/Windows.UI.Xaml.Controls.Primitives.h>
#include "start_footer_flyouts.h"

struct BF_StartSearchButton {
    winrt::weak_ref<Controls::Grid> pane;
    Controls::Button button{nullptr};
    FrameworkElement::LayoutUpdated_revoker layout;
    Media::TranslateTransform offset{nullptr};
    winrt::weak_ref<FrameworkElement> account, power;
    winrt::weak_ref<Controls::ListViewBase> places;
    bool arranging=false;
    std::shared_ptr<BF_FooterAnchor> accountMenu,powerMenu;
};

static thread_local std::vector<BF_StartSearchButton> bf_startSearchButtons;
static thread_local unsigned bf_startSearchGeneration = 0;

static void BF_InvokeWindowsSearch(const Controls::Grid& pane) {
    if (GetEnvironmentVariableW(L"FISHDOCK_TEST_DESKTOP", nullptr, 0)) return;
    BF_PublishStartPanel();
    namespace peers = winrt::Windows::UI::Xaml::Automation::Peers;
    namespace provider = winrt::Windows::UI::Xaml::Automation::Provider;
    try {
        if (auto root = pane.XamlRoot().Content().try_as<FrameworkElement>()) {
            auto toggle = BF_FindLayoutElement(root, L"SearchBoxToggleButton", 14);
            if (!toggle) toggle = BF_FindLayoutElement(root, L"StartMenuSearchBox", 14);
            if (toggle) {
                auto type = winrt::get_class_name(toggle);
                if (type == L"StartMenu.SearchBoxToggleButton" || type == L"StartDocked.SearchBoxToggleButton") {
                    auto peer = peers::FrameworkElementAutomationPeer::CreatePeerForElement(toggle);
                    if (peer) {
                        auto pattern = peer.GetPattern(peers::PatternInterface::Invoke).try_as<provider::IInvokeProvider>();
                        if (pattern) { pattern.Invoke(); return; }
                    }
                }
            }
        }
    } catch (const winrt::hresult_error&) {
        // Some Windows builds provide a search trigger with no usable Invoke pattern.
    }
    INPUT keys[4]{};
    for (auto& key : keys) key.type = INPUT_KEYBOARD;
    keys[0].ki.wVk = keys[3].ki.wVk = VK_LWIN;
    keys[1].ki.wVk = keys[2].ki.wVk = 'S';
    keys[2].ki.dwFlags = keys[3].ki.dwFlags = KEYEVENTF_KEYUP;
    if (SendInput(static_cast<UINT>(std::size(keys)), keys, sizeof(INPUT)) != std::size(keys)) {
        Wh_Log(L"Error opening Windows Search");
        if (bf_status_event) SetEvent(bf_status_event);
    }
}

static wf::Rect BF_FooterBounds(const FrameworkElement& element,const FrameworkElement& layer) {
    if (!element || element.Visibility()!=Visibility::Visible) return {};
    return element.TransformToVisual(layer).TransformBounds(
        {0,0,static_cast<float>(element.ActualWidth()),static_cast<float>(element.ActualHeight())});
}

// The named PowerButton can be a PowerOptionsView containing the actual button.
// Measure the interactive part; the wrapper is sometimes the width of the pane.
static FrameworkElement BF_FooterButton(const FrameworkElement& node) {
    if (!node || node.try_as<Controls::Primitives::ButtonBase>()) return node;
    const int count=Media::VisualTreeHelper::GetChildrenCount(node);
    for (int i=0;i<count;++i) {
        auto child=Media::VisualTreeHelper::GetChild(node,i).try_as<FrameworkElement>();
        if (auto button=BF_FooterButton(child)) return button;
    }
    return nullptr;
}

static void BF_PositionStartFooter(BF_StartSearchButton& entry) {
    auto pane=entry.pane.get();
    if (!pane || !pane.IsLoaded() || entry.arranging || BF_StartMenuFlyoutOpen(pane)) return;
    entry.arranging=true;
    struct Guard {bool& value;~Guard(){value=false;}} guard{entry.arranging};

    auto resolve=[&](auto& reference,PCWSTR name) {
        auto button=reference.get();
        if (!button || !button.IsLoaded()) {
            button=BF_FooterButton(BF_FindLayoutElement(pane,name));
            reference=button ? winrt::make_weak(button) : winrt::weak_ref<FrameworkElement>{};
        }
        return button;
    };
    const auto account=resolve(entry.account,L"UserTileButton");
    const auto power=resolve(entry.power,L"PowerButton");
    auto watch=[](const FrameworkElement& node,std::shared_ptr<BF_FooterAnchor>& state) {
        auto native=node.try_as<BF_FooterCommandButton>();
        if (native && (!state || state->button.get()!=native)) state=BF_FooterAnchor::observe(native);
    };
    watch(account,entry.accountMenu);
    watch(power,entry.powerMenu);
    auto places=entry.places.get();
    if (!places || !places.IsLoaded()) {
        if (auto found=BF_FindLayoutElement(pane,L"NavigationPanePlacesListView")) {
            places=found.try_as<Controls::ListViewBase>();
            if (places) entry.places=winrt::make_weak(places);
        }
    }

    // The only element whose geometry or input state Dock owns is Search.
    // All rectangles are measured in pane coordinates, including RTL templates.
    const double width=pane.ActualWidth(), buttonWidth=entry.button.Width();
    std::vector<std::pair<double,double>> occupied;
    const bool rtl=pane.FlowDirection()==FlowDirection::RightToLeft;
    double placeEdge=rtl ? 0 : width;
    auto reserve=[&](const FrameworkElement& element, bool place=false) {
        auto rect=BF_FooterBounds(element,pane);
        if (rect.Width>0 && rect.Height>0 && rect.X<width && rect.X+rect.Width>0) {
            occupied.emplace_back(std::max(0.0,double(rect.X)),std::min(width,double(rect.X+rect.Width)));
            if (place) placeEdge=rtl ? std::max(placeEdge,occupied.back().second) : std::min(placeEdge,occupied.back().first);
        }
    };
    reserve(account);reserve(power);
    if (places) {
        for (unsigned i=0;i<places.Items().Size();++i)
            reserve(places.ContainerFromIndex(i).try_as<FrameworkElement>(),true);
    }
    std::sort(occupied.begin(),occupied.end());
    const double preferred=rtl ? placeEdge+3 : placeEdge-buttonWidth-3;
    double start=0, target=-1;
    auto consider=[&](double end) {
        if (end-start<buttonWidth+6) return;
        const double x=std::clamp(preferred,start+3,end-buttonWidth-3);
        if (target<0 || std::abs(x-preferred)<std::abs(target-preferred)) target=x;
    };
    for (auto [left,right]:occupied) {
        consider(left);
        start=std::max(start,right);
    }
    consider(width);
    auto rect=BF_FooterBounds(entry.button,pane);
    bool fits=account && power && target>=0 && rect.Width>0 && pane.ActualHeight()>=entry.button.Height();
    if (fits) {
        // Moving just our button after arrange keeps it out of the native
        // grid's size calculation, including auto-sized command columns.
        const double delta=target-rect.X;
        if (std::abs(delta)>.5) entry.offset.X(entry.offset.X()+delta);
    }
    if (entry.button.IsHitTestVisible()!=fits) {
        entry.button.IsHitTestVisible(fits);
        entry.button.IsTabStop(fits);
        entry.button.Opacity(fits ? 1 : 0);
    }
    if (bf_search_button_ready.exchange(fits)!=fits) {
        // Opacity and hit-test state do not trigger another layout pass. Give
        // the redesigned page one so it can release the native search row.
        pane.InvalidateMeasure();
        if (bf_status_event) SetEvent(bf_status_event);
    }
}

static void BF_AddStartSearchButton(const Controls::Grid& pane) {
    std::erase_if(bf_startSearchButtons, [](const auto& entry) { return !entry.pane.get(); });
    if (std::any_of(bf_startSearchButtons.begin(), bf_startSearchButtons.end(),
                    [&](const auto& entry) { return entry.pane.get() == pane; })) return;

    Controls::Button button;
    button.Name(L"BigFishNativeSearchButton");
    button.Width(36); button.Height(34);
    button.Padding({0, 0, 0, 0});
    button.BorderThickness({0, 0, 0, 0});
    button.CornerRadius({8, 8, 8, 8});
    const bool dark = BF_Setting(L"bigfish_theme") == L"Dark";
    button.RequestedTheme(dark ? ElementTheme::Dark : ElementTheme::Light);
    button.Background(Media::SolidColorBrush(winrt::Windows::UI::Colors::Transparent()));
    Controls::FontIcon icon;
    icon.Glyph(L"\uE721");
    icon.FontFamily(Media::FontFamily(L"Segoe MDL2 Assets"));
    icon.FontSize(17);
    icon.Foreground(BF_StartForeground(Media::SolidColorBrush(dark ? winrt::Windows::UI::Colors::White()
                                                                 : winrt::Windows::UI::Colors::Black())));
    button.Content(icon);
    winrt::Windows::UI::Xaml::Automation::AutomationProperties::SetName(button, L"搜索");
    Controls::ToolTipService::SetToolTip(button, winrt::box_value(L"搜索 · Win+S"));
    button.Click([weakPane = winrt::make_weak(pane)](auto&&, auto&&) {
        if (auto live = weakPane.get()) BF_InvokeWindowsSearch(live);
    });

    Controls::Grid::SetColumnSpan(button,std::max(1u,pane.ColumnDefinitions().Size()));
    Controls::Grid::SetRowSpan(button,std::max(1u,pane.RowDefinitions().Size()));
    button.HorizontalAlignment(HorizontalAlignment::Left);
    button.VerticalAlignment(VerticalAlignment::Center);
    button.Opacity(0);
    button.IsHitTestVisible(false);
    button.IsTabStop(false);
    Media::TranslateTransform offset;
    button.RenderTransform(offset);
    pane.Children().Append(button);
    auto weakPane=winrt::make_weak(pane);
    auto watch=pane.LayoutUpdated(winrt::auto_revoke,[weakPane](auto&&,auto&&) {
        auto live=weakPane.get();
        if (!live) return;
        const auto entry=std::find_if(bf_startSearchButtons.begin(),bf_startSearchButtons.end(),
            [&](const auto& state){return state.pane.get()==live;});
        if (entry==bf_startSearchButtons.end()) return;
        try { BF_PositionStartFooter(*entry); }
        catch (const winrt::hresult_error& error) { Wh_Log(L"Error %08X: Start footer",error.code()); }
    });
    BF_StartSearchButton entry{weakPane,button,std::move(watch),offset};
    bf_startSearchButtons.push_back(std::move(entry));
    BF_PositionStartFooter(bf_startSearchButtons.back());
}

static void BF_QueueStartSearchButton(const FrameworkElement& element) {
    if (element.Name() != L"RootPanel") return;
    auto pane = element.try_as<Controls::Grid>();
    auto parent = Media::VisualTreeHelper::GetParent(element);
    if (!pane || !parent || winrt::get_class_name(parent) != L"StartDocked.NavigationPaneView") return;
    element.Dispatcher().RunAsync(winrt::Windows::UI::Core::CoreDispatcherPriority::Normal,
        [weakPane = winrt::make_weak(pane), generation = bf_startSearchGeneration] {
            if (generation != bf_startSearchGeneration) return;
            if (auto live = weakPane.get(); live && live.XamlRoot()) {
                try { BF_AddStartSearchButton(live); }
                catch (const winrt::hresult_error& error) { Wh_Log(L"Error %08X: Start search button", error.code()); }
            }
        });
}

static void BF_ClearStartSearchButtons() {
    ++bf_startSearchGeneration;
    BF_StopFooterRequest();
    BF_CloseFooterMenu();
    bf_search_button_ready = false;
    auto entries=std::exchange(bf_startSearchButtons,{});
    for (auto& entry : entries) {
        entry.layout.revoke();
        if (auto pane = entry.pane.get()) {
            auto children = pane.Children();
            unsigned index = 0;
            if (children.IndexOf(entry.button, index)) children.RemoveAt(index);
        }
    }
}
