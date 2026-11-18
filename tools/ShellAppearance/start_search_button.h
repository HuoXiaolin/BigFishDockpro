#pragma once

#include <winrt/Windows.UI.Xaml.Automation.h>
#include <winrt/Windows.UI.Xaml.Automation.Peers.h>
#include <winrt/Windows.UI.Xaml.Automation.Provider.h>
#include <winrt/Windows.UI.Xaml.Controls.Primitives.h>

struct BF_StartSearchButton {
    winrt::weak_ref<Controls::Grid> pane;
    Controls::Button button{nullptr};
    FrameworkElement::LayoutUpdated_revoker layout;
    std::vector<Controls::ColumnDefinition> columns;
    std::vector<Controls::RowDefinition> rows;
    BF_LocalLayout root,account,power,places;
    std::vector<BF_LocalLayout> placeItems;
    bool arranged=false;
    bool arranging=false;
};

static thread_local std::vector<BF_StartSearchButton> bf_startSearchButtons;
static thread_local unsigned bf_startSearchGeneration = 0;
namespace bf_popup = winrt::Windows::UI::Xaml::Controls::Primitives;
struct BF_StartPopup {
    winrt::weak_ref<bf_popup::Popup> popup;
    wf::IInspectable originalPlacement;
};
static thread_local std::vector<BF_StartPopup> bf_startPopups;

static bool BF_IsStartFooterAnchor(const FrameworkElement& anchor) {
    for (DependencyObject item=anchor;item;item=Media::VisualTreeHelper::GetParent(item)) {
        auto element=item.try_as<FrameworkElement>();
        if (!element) continue;
        const auto name=element.Name();
        if (name==L"UserTileButton" || name==L"PowerButton") return true;
        const auto type=winrt::get_class_name(element);
        if (type==L"StartDocked.UserTileView" || type==L"StartDocked.PowerOptionsView") return true;
    }
    return false;
}

static void BF_AlignStartPopup(const FrameworkElement& presenter) {
    auto root=presenter.XamlRoot();
    if (!root) return;
    for (auto popup : Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(root)) {
        auto anchor=popup.PlacementTarget();
        if (!anchor || !BF_IsStartFooterAnchor(anchor)) continue;
        auto child=popup.Child();
        bool matches=false;
        for (DependencyObject item=presenter;item;item=Media::VisualTreeHelper::GetParent(item)) {
            if (item==child) {matches=true;break;}
        }
        if (!matches || popup.DesiredPlacement()==bf_popup::PopupPlacementMode::TopEdgeAlignedLeft) continue;
        std::erase_if(bf_startPopups,[](const auto& item){return !item.popup.get();});
        if (std::none_of(bf_startPopups.begin(),bf_startPopups.end(),
                         [&](const auto& item){return item.popup.get()==popup;})) {
            bf_startPopups.push_back({winrt::make_weak(popup),popup.ReadLocalValue(bf_popup::Popup::DesiredPlacementProperty())});
        }
        popup.DesiredPlacement(bf_popup::PopupPlacementMode::TopEdgeAlignedLeft);
    }
}

static void BF_QueueStartPopup(const FrameworkElement& element) {
    if (!bf_is_start_menu || (!element.try_as<Controls::MenuFlyoutPresenter>() && !element.try_as<Controls::FlyoutPresenter>())) return;
    element.Dispatcher().RunAsync(winrt::Windows::UI::Core::CoreDispatcherPriority::Normal,
        [weak=winrt::make_weak(element),generation=bf_startSearchGeneration] {
            if (generation!=bf_startSearchGeneration) return;
            if (auto live=weak.get()) {
                try { BF_AlignStartPopup(live); }
                catch (const winrt::hresult_error& error) { Wh_Log(L"Error %08X: Start flyout position",error.code()); }
            }
        });
}

static FrameworkElement BF_FindNamedControl(const FrameworkElement& parent, std::wstring_view name, int depth) {
    if (parent.Name() == name) return parent;
    if (depth == 0) return nullptr;
    const auto count = Media::VisualTreeHelper::GetChildrenCount(parent);
    for (int index = 0; index < count; ++index) {
        auto child = Media::VisualTreeHelper::GetChild(parent, index).try_as<FrameworkElement>();
        if (child) {
            if (auto found = BF_FindNamedControl(child, name, depth - 1)) return found;
        }
    }
    return nullptr;
}

static void BF_InvokeWindowsSearch(const Controls::Grid& pane) {
    if (GetEnvironmentVariableW(L"FISHDOCK_TEST_DESKTOP", nullptr, 0)) return;
    BF_PublishStartPanel();
    namespace peers = winrt::Windows::UI::Xaml::Automation::Peers;
    namespace provider = winrt::Windows::UI::Xaml::Automation::Provider;
    try {
        if (auto root = pane.XamlRoot().Content().try_as<FrameworkElement>()) {
            auto toggle = BF_FindNamedControl(root, L"SearchBoxToggleButton", 14);
            if (!toggle) toggle = BF_FindNamedControl(root, L"StartMenuSearchBox", 14);
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

static void BF_PositionStartFooter(BF_StartSearchButton& entry) {
    auto pane=entry.pane.get();
    if (!pane || !pane.IsLoaded() || pane.ActualWidth()<250 || entry.arranging) return;
    entry.arranging=true;
    struct Guard {bool& value;~Guard(){value=false;}} guard{entry.arranging};
    auto user=BF_DirectLayoutChild(pane,BF_FindNamedControl(pane,L"UserTileButton",12));
    auto power=BF_DirectLayoutChild(pane,BF_FindNamedControl(pane,L"PowerButton",12));
    auto places=BF_DirectLayoutChild(pane,BF_FindNamedControl(pane,L"NavigationPanePlacesListView",12));
    if (user && power && user!=power && !entry.arranged) {
        entry.arranged=true;
        for (auto item:pane.ColumnDefinitions()) entry.columns.push_back(item);
        for (auto item:pane.RowDefinitions()) entry.rows.push_back(item);
        pane.ColumnDefinitions().Clear();pane.RowDefinitions().Clear();
        // Reserve Search before assigning the optional Windows places list.
        for (auto length:{GridLength{156,GridUnitType::Pixel},GridLength{40,GridUnitType::Pixel},
                          GridLength{1,GridUnitType::Star},GridLength{40,GridUnitType::Pixel},GridLength{1,GridUnitType::Auto}}) {
            Controls::ColumnDefinition definition;definition.Width(length);pane.ColumnDefinitions().Append(definition);
        }
        entry.root.set(pane,FrameworkElement::FlowDirectionProperty(),winrt::box_value(FlowDirection::LeftToRight));
        entry.root.set(pane,FrameworkElement::MarginProperty(),winrt::box_value(Thickness{}));
        entry.root.set(pane,Controls::Grid::PaddingProperty(),winrt::box_value(Thickness{}));
        BF_SetGridSlot(entry.account,user,0);BF_SetGridSlot(entry.power,power,1);
        for (auto pair:{std::pair{user,&entry.account},std::pair{power,&entry.power}}) {
            pair.second->set(pair.first,FrameworkElement::VerticalAlignmentProperty(),winrt::box_value(VerticalAlignment::Center));
            pair.second->set(pair.first,FrameworkElement::MaxWidthProperty(),winrt::box_value(pair.first==user?156.0:40.0));
            pair.second->set(pair.first,FrameworkElement::FlowDirectionProperty(),winrt::box_value(FlowDirection::LeftToRight));
        }
        if (places && places!=user && places!=power) {
            BF_SetGridSlot(entry.places,places,4);
            entry.places.set(places,FrameworkElement::MaxWidthProperty(),winrt::box_value(210.0));
            entry.places.set(places,FrameworkElement::VerticalAlignmentProperty(),winrt::box_value(VerticalAlignment::Center));
            if (auto control=places.try_as<Controls::Control>()) {
                entry.places.set(places,Controls::Control::PaddingProperty(),winrt::box_value(Thickness{}));
                entry.places.set(places,Controls::Control::VerticalContentAlignmentProperty(),winrt::box_value(VerticalAlignment::Center));
            }
        }
    }
    if (auto list=places.try_as<Controls::ListViewBase>();entry.arranged && list) {
        const double width=std::min(210.0,40.0*list.Items().Size());
        if (std::isnan(places.Width()) || std::abs(places.Width()-width)>.5)
            entry.places.set(places,FrameworkElement::WidthProperty(),winrt::box_value(width));
        for (unsigned index=0;index<std::min(16u,list.Items().Size());++index) {
            auto item=list.ContainerFromIndex(index).try_as<FrameworkElement>();
            if (!item || std::any_of(entry.placeItems.begin(),entry.placeItems.end(),[&](const auto& state){return state.element.get()==item;})) continue;
            BF_LocalLayout state;
            state.set(item,FrameworkElement::MinWidthProperty(),winrt::box_value(0.0));
            state.set(item,FrameworkElement::MinHeightProperty(),winrt::box_value(0.0));
            state.set(item,FrameworkElement::WidthProperty(),winrt::box_value(40.0));
            state.set(item,FrameworkElement::HeightProperty(),winrt::box_value(40.0));
            state.set(item,FrameworkElement::MarginProperty(),winrt::box_value(Thickness{}));
            if (item.try_as<Controls::Control>()) {
                state.set(item,Controls::Control::PaddingProperty(),winrt::box_value(Thickness{}));
                state.set(item,Controls::Control::HorizontalContentAlignmentProperty(),winrt::box_value(HorizontalAlignment::Center));
                state.set(item,Controls::Control::VerticalContentAlignmentProperty(),winrt::box_value(VerticalAlignment::Center));
            }
            entry.placeItems.push_back(std::move(state));
        }
    }
    entry.button.Visibility(Visibility::Visible);
    const auto rect=BF_FooterBounds(entry.button,pane);
    const bool visible=entry.arranged && rect.Width>0 && rect.Height>0 && rect.X>=0 && rect.Y>=0 &&
                       rect.X+rect.Width<=pane.ActualWidth()+1 && rect.Y+rect.Height<=pane.ActualHeight()+1;
    if (bf_search_button_ready.exchange(visible)!=visible && bf_status_event) SetEvent(bf_status_event);
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
    icon.Foreground(Media::SolidColorBrush(dark ? winrt::Windows::UI::Colors::White()
                                                : winrt::Windows::UI::Colors::Black()));
    button.Content(icon);
    winrt::Windows::UI::Xaml::Automation::AutomationProperties::SetName(button, L"搜索");
    Controls::ToolTipService::SetToolTip(button, winrt::box_value(L"搜索 · Win+S"));
    button.Click([weakPane = winrt::make_weak(pane)](auto&&, auto&&) {
        if (auto live = weakPane.get()) BF_InvokeWindowsSearch(live);
    });

    Controls::Grid::SetColumn(button,3);
    Controls::Canvas::SetZIndex(button,6);
    button.HorizontalAlignment(HorizontalAlignment::Center);
    button.VerticalAlignment(VerticalAlignment::Center);
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
    BF_StartSearchButton entry{weakPane,button,std::move(watch)};
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
    bf_search_button_ready = false;
    for (auto& item:bf_startPopups) {
        if (auto popup=item.popup.get();
            popup && popup.DesiredPlacement()==bf_popup::PopupPlacementMode::TopEdgeAlignedLeft) {
            const auto property=bf_popup::Popup::DesiredPlacementProperty();
            if (item.originalPlacement==DependencyProperty::UnsetValue()) popup.ClearValue(property);
            else popup.SetValue(property,item.originalPlacement);
        }
    }
    bf_startPopups.clear();
    auto entries=std::exchange(bf_startSearchButtons,{});
    for (auto& entry : entries) {
        entry.layout.revoke();
        entry.root.restore();
        entry.account.restore();
        entry.power.restore();
        entry.places.restore();
        for(auto& item:entry.placeItems) item.restore();
        if (auto pane = entry.pane.get()) {
            auto children = pane.Children();
            unsigned index = 0;
            if (children.IndexOf(entry.button, index)) children.RemoveAt(index);
            if (entry.arranged) {
                pane.ColumnDefinitions().Clear();pane.RowDefinitions().Clear();
                for (auto definition:entry.columns) pane.ColumnDefinitions().Append(definition);
                for (auto definition:entry.rows) pane.RowDefinitions().Append(definition);
            }
        }
    }
}
