#pragma once
#include <limits>
#include <winrt/Windows.UI.Xaml.Controls.Primitives.h>

// Store the local values of app-list and search layout properties for teardown.
struct BF_LocalLayout {
    winrt::weak_ref<FrameworkElement> element;
    std::vector<std::pair<DependencyProperty,wf::IInspectable>> values;

    void set(const FrameworkElement& target,const DependencyProperty& property,const wf::IInspectable& value) {
        if (!element.get()) element=winrt::make_weak(target);
        if (std::none_of(values.begin(),values.end(),[&](const auto& item){return item.first==property;}))
            values.emplace_back(property,target.ReadLocalValue(property));
        target.SetValue(property,value);
    }
    void restore() noexcept {
        // Teardown can run after a native template has been replaced. One
        // unavailable property must not abort the remaining restoration or
        // unwind through the system window hook (seen in the live crash dump).
        auto pending=std::exchange(values,{});
        try {
            if (auto target=element.get()) for (auto& [property,value]:pending) {
                try {
                    if (value==DependencyProperty::UnsetValue()) target.ClearValue(property);
                    else target.SetValue(property,value);
                } catch (...) { Wh_Log(L"Error %08X: restoring Start property",winrt::to_hresult()); }
            }
        } catch (...) { Wh_Log(L"Error %08X: restoring Start element",winrt::to_hresult()); }
        element={};
    }
};

static FrameworkElement BF_FindLayoutElement(const FrameworkElement& parent,std::wstring_view name,int depth=14) {
    if (parent.Name()==name) return parent;
    if (!depth) return nullptr;
    const auto count=Media::VisualTreeHelper::GetChildrenCount(parent);
    for (int index=0;index<count;++index) {
        auto child=Media::VisualTreeHelper::GetChild(parent,index).try_as<FrameworkElement>();
        if (child) if (auto found=BF_FindLayoutElement(child,name,depth-1)) return found;
    }
    return nullptr;
}

static FrameworkElement BF_DirectLayoutChild(const Controls::Grid& parent,FrameworkElement element) {
    while (element) {
        auto ancestor=Media::VisualTreeHelper::GetParent(element);
        if (ancestor==parent) return element;
        element=ancestor.try_as<FrameworkElement>();
    }
    return nullptr;
}

struct BF_StartColumns {
    struct ItemInsets {
        winrt::weak_ref<Controls::Panel> panel;
        double columnWidth=0,left=0,right=0;
        bool fitWidth=false;
    };
    winrt::weak_ref<Controls::Grid> root;
    BF_LocalLayout apps,pinned;
    std::vector<BF_LocalLayout> folders,contents;
    std::vector<ItemInsets> itemInsets;
    winrt::weak_ref<FrameworkElement> appsViewportRow;
    winrt::weak_ref<Controls::Primitives::ScrollBar> appsScrollBar;
    Media::RectangleGeometry appsClip{nullptr};
    double viewportLeft=0,viewportRight=0;
    winrt::weak_ref<FrameworkElement> realizedApps;
    struct StateValue {
        winrt::weak_ref<DependencyObject> element;
        DependencyProperty property;
        wf::IInspectable original;
    };
    std::vector<StateValue> pageAnimations;
    FrameworkElement::LayoutUpdated_revoker layout;
    bool arranging=false;
};
static thread_local std::vector<std::shared_ptr<BF_StartColumns>> bf_startColumns;
static thread_local unsigned bf_startLayoutGeneration=0;

static bool BF_IsStartMenuFlyout(const DependencyObject& node, int depth=4) {
    if (!node) return false;
    if (node.try_as<Controls::MenuFlyoutPresenter>() || node.try_as<Controls::FlyoutPresenter>()) return true;
    if (!depth || node.try_as<Controls::ToolTip>()) return false;
    const auto count=Media::VisualTreeHelper::GetChildrenCount(node);
    for (int i=0;i<count;++i) {
        if (BF_IsStartMenuFlyout(Media::VisualTreeHelper::GetChild(node,i),depth-1)) return true;
    }
    return false;
}

// Some command menus wrap the presenter in a layout root. Hover updates
// inside either kind of popup must leave the underlying page alone.
static bool BF_FooterMenuActive(const XamlRoot& root);
static bool BF_StartMenuFlyoutOpen(const FrameworkElement& element) {
    auto root=element.XamlRoot();
    if (root && BF_FooterMenuActive(root)) return true;
    if (root) for (const auto& popup:Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(root)) {
        if (popup.IsOpen() && BF_IsStartMenuFlyout(popup.Child())) return true;
    }
    return false;
}

static void BF_SuspendStartColumns() {
    ++bf_startLayoutGeneration;
    for (auto& state:bf_startColumns) state->layout.revoke();
}

// Windows keeps additional padding inside its native control templates: the
// header wrapper uses 63 DIPs, PinnedList's root 32 DIPs and the all-apps items
// panel 52 DIPs. Moving just AllAppsRoot/UndockedRoot cannot remove those insets.
// Normalize only the path to each named column part, never its item templates.
static BF_LocalLayout& BF_StartContentState(std::vector<BF_LocalLayout>& layouts,const FrameworkElement& element) {
    std::erase_if(layouts,[](auto& entry){return !entry.element.get();});
    auto found=std::find_if(layouts.begin(),layouts.end(),[&](auto& entry){return entry.element.get()==element;});
    if (found!=layouts.end()) return *found;
    layouts.emplace_back();layouts.back().element=winrt::make_weak(element);
    return layouts.back();
}

static BF_LocalLayout& BF_StartContentState(BF_StartColumns& state,const FrameworkElement& element) {
    return BF_StartContentState(state.contents,element);
}

static Controls::ListViewBase BF_FindStartList(const FrameworkElement& root,int depth=32) {
    if (!depth || root.Name()==L"ZoomedOutListView" || root.Name()==L"ZoomAppsList") return nullptr;
    if (auto list=root.try_as<Controls::ListViewBase>()) return list;
    const int count=Media::VisualTreeHelper::GetChildrenCount(root);
    for (int i=0;i<count;++i) if (auto child=Media::VisualTreeHelper::GetChild(root,i).try_as<FrameworkElement>())
        if (auto found=BF_FindStartList(child,depth-1)) return found;
    return nullptr;
}

static void BF_CompactStartPath(BF_StartColumns& state,FrameworkElement element,const FrameworkElement& boundary) {
    while (element && element!=boundary) {
        auto& saved=BF_StartContentState(state,element);
        // Native Loaded/size handlers can restore these after our first pass.
        // Compare before writing, so a settled layout causes no extra updates.
        {
            double contentWidth=std::numeric_limits<double>::quiet_NaN();
            auto margin=element.Margin();margin.Left=0;margin.Right=0;
            for (const auto& inset:state.itemInsets) if (inset.panel.get()==element) {
                margin.Left=-inset.left;margin.Right=-inset.right;
                if (inset.fitWidth) contentWidth=inset.columnWidth+inset.left+inset.right;
                break;
            }
            if (state.appsViewportRow.get()==element) {
                margin.Left=-state.viewportLeft;
                margin.Right=-state.viewportRight;
            }
            if (std::abs(element.Margin().Left-margin.Left)>.5 || std::abs(element.Margin().Right-margin.Right)>.5)
                saved.set(element,FrameworkElement::MarginProperty(),winrt::box_value(margin));
            if (element.MinWidth()!=0) saved.set(element,FrameworkElement::MinWidthProperty(),winrt::box_value(0.0));
            if ((std::isnan(contentWidth)!=std::isnan(element.Width())) ||
                (!std::isnan(contentWidth) && std::abs(contentWidth-element.Width())>.5))
                saved.set(element,FrameworkElement::WidthProperty(),winrt::box_value(contentWidth));
            if (element.HorizontalAlignment()!=HorizontalAlignment::Stretch)
                saved.set(element,FrameworkElement::HorizontalAlignmentProperty(),winrt::box_value(HorizontalAlignment::Stretch));
            if (auto control=element.try_as<Controls::Control>()) {
                auto padding=control.Padding();padding.Left=0;padding.Right=0;
                if (control.Padding().Left!=0 || control.Padding().Right!=0)
                    saved.set(element,Controls::Control::PaddingProperty(),winrt::box_value(padding));
                if (control.HorizontalContentAlignment()!=HorizontalAlignment::Stretch)
                    saved.set(element,Controls::Control::HorizontalContentAlignmentProperty(),winrt::box_value(HorizontalAlignment::Stretch));
            } else if (auto grid=element.try_as<Controls::Grid>()) {
                auto padding=grid.Padding();padding.Left=0;padding.Right=0;
                if (grid.Padding().Left!=0 || grid.Padding().Right!=0)
                    saved.set(element,Controls::Grid::PaddingProperty(),winrt::box_value(padding));
            } else if (auto border=element.try_as<Controls::Border>()) {
                auto padding=border.Padding();padding.Left=0;padding.Right=0;
                if (border.Padding().Left!=0 || border.Padding().Right!=0)
                    saved.set(element,Controls::Border::PaddingProperty(),winrt::box_value(padding));
            } else if (auto presenter=element.try_as<Controls::ContentPresenter>()) {
                auto padding=presenter.Padding();padding.Left=0;padding.Right=0;
                if (presenter.Padding().Left!=0 || presenter.Padding().Right!=0)
                    saved.set(element,Controls::ContentPresenter::PaddingProperty(),winrt::box_value(padding));
            } else if (auto presenter=element.try_as<Controls::ItemsPresenter>()) {
                auto padding=presenter.Padding();padding.Left=0;padding.Right=0;
                if (presenter.Padding().Left!=0 || presenter.Padding().Right!=0)
                    saved.set(element,Controls::ItemsPresenter::PaddingProperty(),winrt::box_value(padding));
            }
        }
        element=Media::VisualTreeHelper::GetParent(element).try_as<FrameworkElement>();
    }
}

// A render transform belongs to the Start animation. Only the coordinates
// from XAML's arrange pass may be used to set a layout property.
static bool BF_StartLayoutOrigin(UIElement element,const UIElement& ancestor,wf::Point& origin) {
    origin={};
    while (element && element!=ancestor) {
        const auto offset=element.ActualOffset();
        origin.X+=offset.x;
        origin.Y+=offset.y;
        element=Media::VisualTreeHelper::GetParent(element).try_as<UIElement>();
    }
    return element==ancestor && std::isfinite(origin.X) && std::isfinite(origin.Y);
}

static void BF_RecordStartDip(std::atomic<int>& metric,double dip) {
    const int value=static_cast<int>(std::lround(dip*100));
    if (metric.exchange(value)!=value && bf_status_event) SetEvent(bf_status_event);
}

static void BF_FitAppsScrollBar(BF_StartColumns& state,const FrameworkElement& column,const Controls::Panel& panel) {
    // The items viewport can be made wider to recover the native TileGrid's
    // gutters. The ScrollViewer's overlay belongs inside the visible column.
    auto root=state.root.get();
    if (!root || column.ActualWidth()<=0 || column.ActualHeight()<=0) return;
    const wf::Rect bounds{0,0,static_cast<float>(column.ActualWidth()),static_cast<float>(column.ActualHeight())};
    if (!state.appsClip || column.Clip()!=state.appsClip) {
        state.appsClip=Media::RectangleGeometry();state.appsClip.Rect(bounds);
        BF_StartContentState(state,column).set(column,UIElement::ClipProperty(),state.appsClip);
    } else if (state.appsClip.Rect()!=bounds) state.appsClip.Rect(bounds);
    auto bar=state.appsScrollBar.get();
    if (!bar || !bar.IsLoaded()) {
        for (FrameworkElement p=panel;p && p!=column;p=Media::VisualTreeHelper::GetParent(p).try_as<FrameworkElement>()) {
            if (!p.try_as<Controls::ScrollViewer>()) continue;
            bar=BF_FindLayoutElement(p,L"VerticalScrollBar").try_as<Controls::Primitives::ScrollBar>();
            if (bar) {state.appsScrollBar=winrt::make_weak(bar);break;}
        }
    }
    if (!bar || bar.ActualWidth()<=0 || bar.Orientation()!=Controls::Orientation::Vertical) return;
    auto parent=Media::VisualTreeHelper::GetParent(bar).try_as<Controls::Grid>();
    wf::Point origin{};
    if (!parent || !BF_StartLayoutOrigin(parent,column,origin)) return;
    const double overhang=origin.X+parent.ActualWidth()-column.ActualWidth();
    if (overhang>.5 || Controls::Grid::GetColumnSpan(bar)>1) {
        auto& saved=BF_StartContentState(state,bar);
        const int span=static_cast<int>(std::max(1u,parent.ColumnDefinitions().Size()));
        if (Controls::Grid::GetColumn(bar)!=0) saved.set(bar,Controls::Grid::ColumnProperty(),winrt::box_value(0));
        if (Controls::Grid::GetColumnSpan(bar)!=span) saved.set(bar,Controls::Grid::ColumnSpanProperty(),winrt::box_value(span));
        if (bar.HorizontalAlignment()!=HorizontalAlignment::Right)
            saved.set(bar,FrameworkElement::HorizontalAlignmentProperty(),winrt::box_value(HorizontalAlignment::Right));
        auto margin=bar.Margin();
        const auto right=std::max(0.0,overhang);
        if (std::abs(margin.Right-right)>.5) {
            margin.Right=right;saved.set(bar,FrameworkElement::MarginProperty(),winrt::box_value(margin));
        }
    }
    if (BF_StartLayoutOrigin(bar,root,origin)) BF_RecordStartDip(bf_start_scroll_right,origin.X+bar.ActualWidth());
    if (BF_StartLayoutOrigin(column,root,origin)) BF_RecordStartDip(bf_start_apps_right,origin.X+column.ActualWidth());
}

static void BF_AlignStartLetters(BF_StartColumns& state,const FrameworkElement& column,const Controls::Panel& panel) {
    auto logo=BF_FindLayoutElement(panel,L"AppListItemLogo",24);
    if (!logo) logo=BF_FindLayoutElement(panel,L"AllAppsTileLogo",24);
    auto heading=BF_FindLayoutElement(column,L"AllAppsHeading").try_as<Controls::TextBlock>();
    auto root=state.root.get();
    wf::Point glyph{},title{},columnOrigin{};
    if (!root || !logo || !heading || logo.ActualWidth()<=0 || !BF_StartLayoutOrigin(logo,column,glyph) ||
        !BF_StartLayoutOrigin(heading,column,title) || !BF_StartLayoutOrigin(column,root,columnOrigin)) return;
    BF_RecordStartDip(bf_start_logo_x,columnOrigin.X+glyph.X);
    BF_RecordStartDip(bf_start_heading_x,columnOrigin.X+title.X+heading.Padding().Left);
    if (glyph.X<0 || glyph.X>32) return;
    auto padding=heading.Padding();
    const double titleInset=std::clamp<double>(glyph.X-title.X,0,32);
    if (std::abs(padding.Left-titleInset)>.5) {
        padding.Left=titleInset;
        BF_StartContentState(state,heading).set(heading,Controls::TextBlock::PaddingProperty(),winrt::box_value(padding));
    }
    bool firstLetter=true;
    for (auto child:panel.Children()) if (auto item=child.try_as<Controls::ContentControl>()) {
        auto button=BF_FindLayoutElement(item,L"Header",8).try_as<Controls::Button>();
        wf::Point origin{};
        if (!button || button.ActualWidth()<=0 || !BF_StartLayoutOrigin(button,column,origin)) continue;
        auto inset=button.Padding();
        const double target=std::clamp<double>(glyph.X-origin.X-button.BorderThickness().Left,0,32);
        if (std::abs(inset.Left-target)>.5) {
            inset.Left=target;
            BF_StartContentState(state,button).set(button,Controls::Control::PaddingProperty(),winrt::box_value(inset));
        }
        if (firstLetter) {
            auto text=BF_FindLayoutElement(button,L"Text");
            if (text && BF_StartLayoutOrigin(text,root,origin)) {
                BF_RecordStartDip(bf_start_letter_x,origin.X);
                firstLetter=false;
            }
        }
    }
}

static void BF_FitPinnedContent(BF_StartColumns& state,const FrameworkElement& item,bool record) {
    auto presenter=BF_FindLayoutElement(item,L"ContentPresenter",5);
    if (presenter && Media::VisualTreeHelper::GetChildrenCount(presenter)>0) {
        auto grid=Media::VisualTreeHelper::GetChild(presenter,0).try_as<Controls::Grid>();
        if (grid && grid.Width()>item.ActualWidth()+.5 && grid.Width()<=128) {
            // PinnedListItemDataTemplate and PinnedListFolderDataTemplate both
            // carry their own 96-DIP width inside the 76-DIP pointer target.
            BF_StartContentState(state,grid).set(grid,FrameworkElement::WidthProperty(),winrt::box_value(item.ActualWidth()));
        }
    }
    if (!record) return;
    if (auto column=state.pinned.element.get()) {
        auto heading=BF_FindLayoutElement(column,L"PinnedListHeaderText").try_as<Controls::TextBlock>();
        if (heading) {
            if (heading.HorizontalAlignment()!=HorizontalAlignment::Left)
                BF_StartContentState(state,heading).set(heading,FrameworkElement::HorizontalAlignmentProperty(),winrt::box_value(HorizontalAlignment::Left));
            auto wrapper=Media::VisualTreeHelper::GetParent(heading).try_as<FrameworkElement>();
            wf::Point tile{},title{},parent{};
            if (wrapper && heading.ActualWidth()>0 && BF_StartLayoutOrigin(item,column,tile) &&
                BF_StartLayoutOrigin(wrapper,column,parent) && BF_StartLayoutOrigin(heading,column,title)) {
                const double inset=std::max(0.0,tile.X-parent.X+(item.ActualWidth()-heading.ActualWidth())*.5);
                const Thickness margin{inset,8,0,8};
                if (std::abs(heading.Margin().Left-inset)>.5 || heading.Margin().Top!=8 || heading.Margin().Bottom!=8)
                    BF_StartContentState(state,heading).set(heading,FrameworkElement::MarginProperty(),winrt::box_value(margin));
                BF_RecordStartDip(bf_start_pin_title_delta,title.X-tile.X+(heading.ActualWidth()-item.ActualWidth())*.5);
            }
        }
    }
    for (auto name:{L"LogoContainer",L"DisplayName"}) {
        auto part=BF_FindLayoutElement(item,name,18);
        wf::Point origin{};
        if (part && part.ActualWidth()>0 && BF_StartLayoutOrigin(part,item,origin))
            BF_RecordStartDip(std::wstring_view(name)==L"LogoContainer"?bf_start_pin_icon_delta:bf_start_pin_label_delta,
                              origin.X+(part.ActualWidth()-item.ActualWidth())*.5);
    }
}

// The 24H2 list has a separate scroll viewport. Its TileGrid can report zero
// item inset while the viewport itself starts 52 DIPs inside AllAppsRoot.
// Widen the list row around that viewport once, leaving the header, column
// bounds and pinned hit rectangles in their original slots.
static bool BF_FitStartViewport(BF_StartColumns& state,const FrameworkElement& column,
                                const Controls::ListViewBase& list,const Controls::Panel& panel) {
    auto grid=column.try_as<Controls::Grid>();
    auto row=grid?BF_DirectLayoutChild(grid,list):nullptr;
    if (!row || Controls::Grid::GetRow(row)==0 || row==state.appsViewportRow.get()) return false;
    auto heading=BF_FindLayoutElement(column,L"AllAppsHeading");
    if (heading && BF_DirectLayoutChild(grid,heading)==row) return false;
    wf::Point origin{};
    if (!BF_StartLayoutOrigin(panel,column,origin) || origin.X<2 || origin.X>64) return false;
    double right=column.ActualWidth();
    for (FrameworkElement part=panel;part && part!=column;
         part=Media::VisualTreeHelper::GetParent(part).try_as<FrameworkElement>()) {
        if (part.ActualWidth()>0 && BF_StartLayoutOrigin(part,column,origin))
            right=std::min(right,origin.X+part.ActualWidth());
    }
    if (!BF_StartLayoutOrigin(panel,column,origin)) return false;
    const double rightInset=std::clamp(column.ActualWidth()-right,0.0,64.0);
    if (origin.X+rightInset>=column.ActualWidth()*.9) return false;
    state.appsViewportRow=winrt::make_weak(row);
    state.viewportLeft=origin.X;
    state.viewportRight=rightInset;
    auto margin=row.Margin();
    margin.Left=-state.viewportLeft;margin.Right=-state.viewportRight;
    BF_StartContentState(state,row).set(row,FrameworkElement::MarginProperty(),winrt::box_value(margin));
    return true;
}

// TileGrid can reserve space in ArrangeOverride without exposing Margin/Padding.
// Measure realized item bounds inside that panel, then compensate the panel's
// slot inside the unchanged scroll viewport. This recovers label width as well
// as position; moving the whole column would move the heading and scrollbar too.
static void BF_AlignStartItems(BF_StartColumns& state,const FrameworkElement& column,bool pinned) {
    auto list=BF_FindStartList(column);
    if (!list || !list.ItemsPanelRoot() || std::abs(column.ActualWidth()-column.Width())>1) return;
    auto panel=list.ItemsPanelRoot();
    if (panel.ActualWidth()<=0) return;
    if (!pinned && BF_FitStartViewport(state,column,list,panel)) return;
    if (!pinned) {
        BF_FitAppsScrollBar(state,column,panel);
        BF_AlignStartLetters(state,column,panel);
    }
    std::erase_if(state.itemInsets,[](const auto& entry){return !entry.panel.get();});
    auto found=std::find_if(state.itemInsets.begin(),state.itemInsets.end(),[&](const auto& entry){return entry.panel.get()==panel;});
    if (found!=state.itemInsets.end() && std::abs(found->columnWidth-column.ActualWidth())>=1) {
        // Measure afresh after a genuine viewport resize, never accumulate the
        // same displacement on every LayoutUpdated or recycled item.
        state.itemInsets.erase(found);
        auto margin=panel.Margin();margin.Left=0;margin.Right=0;
        BF_StartContentState(state,panel).set(panel,FrameworkElement::MarginProperty(),winrt::box_value(margin));
        return;
    }
    double left=panel.ActualWidth(),right=0;unsigned count=0;
    for (auto child:panel.Children()) if (auto item=child.try_as<FrameworkElement>();item &&
        (item.try_as<Controls::ListViewItem>() || item.try_as<Controls::GridViewItem>()) &&
        item.Visibility()==Visibility::Visible && item.ActualWidth()>0 && item.ActualHeight()>0) {
        const double x=item.ActualOffset().x;
        if (pinned) BF_FitPinnedContent(state,item,count==0);
        else if (!count) BF_RecordStartDip(bf_start_row_width,item.ActualWidth());
        left=std::min(left,x);right=std::max(right,x+item.ActualWidth());++count;
    }
    if (!count) return;
    wf::Point origin{};
    if (auto root=state.root.get(); root && BF_StartLayoutOrigin(panel,root,origin)) {
        auto& position=pinned?bf_start_pinned_item_x:bf_start_apps_item_x;
        if (position.exchange(static_cast<int>((origin.X+left)*100+.5))!=static_cast<int>((origin.X+left)*100+.5) && bf_status_event)
            SetEvent(bf_status_event);
    }
    if (found!=state.itemInsets.end()) return;
    // Only compensate native gutter-sized values. A transition or an invalid
    // layout must never be latched as an inset.
    left=std::max(0.0,left);
    right=pinned?0.0:std::max(0.0,panel.ActualWidth()-right);
    if (!std::isfinite(left+right) || left>64 || right>64 || left+right>=column.ActualWidth()*.9) return;
    auto& metric=pinned?bf_start_pinned_inset:bf_start_apps_inset;
    const int total=static_cast<int>((left+(pinned?0:state.viewportLeft))*100+.5);
    if (metric.exchange(total)!=total && bf_status_event) SetEvent(bf_status_event);
    if (left<.5 && right<.5) return;
    state.itemInsets.push_back({winrt::make_weak(panel),column.ActualWidth(),left,right,!pinned});
    auto margin=panel.Margin();margin.Left=-left;margin.Right=-right;
    if (!pinned) {
        auto& saved=BF_StartContentState(state,panel);
        const double width=column.ActualWidth()+left+right;
        if (!std::isinf(panel.MaxWidth())) saved.set(panel,FrameworkElement::MaxWidthProperty(),winrt::box_value(std::numeric_limits<double>::infinity()));
        if (std::isnan(panel.Width()) || std::abs(panel.Width()-width)>.5)
            saved.set(panel,FrameworkElement::WidthProperty(),winrt::box_value(width));
    }
    if (std::abs(panel.Margin().Left-margin.Left)>.5 || std::abs(panel.Margin().Right-margin.Right)>.5)
        BF_StartContentState(state,panel).set(panel,FrameworkElement::MarginProperty(),winrt::box_value(margin));
}

static void BF_CompactStartContents(BF_StartColumns& state,const FrameworkElement& column,bool pinned) {
    auto heading=BF_FindLayoutElement(column,pinned?L"PinnedListHeaderText":L"AllAppsHeading");
    if (heading) {
        auto wrapper=Media::VisualTreeHelper::GetParent(heading).try_as<FrameworkElement>();
        if (wrapper && wrapper!=column) {
            auto& saved=BF_StartContentState(state,wrapper);
            if (wrapper.Margin().Top!=0 || wrapper.Margin().Bottom!=0)
                saved.set(wrapper,FrameworkElement::MarginProperty(),winrt::box_value(Thickness{}));
            if (wrapper.Height()!=36)
                saved.set(wrapper,FrameworkElement::HeightProperty(),winrt::box_value(36.0));
            if (wrapper.VerticalAlignment()!=VerticalAlignment::Top)
                saved.set(wrapper,FrameworkElement::VerticalAlignmentProperty(),winrt::box_value(VerticalAlignment::Top));
            BF_CompactStartPath(state,wrapper,column);
        }
    }
    auto list=BF_FindLayoutElement(column,pinned?L"PinnedList":L"AllAppsGrid");
    if (!list && !pinned) list=BF_FindLayoutElement(column,L"AppsList");
    if (!list || !list.try_as<Controls::ListViewBase>()) list=BF_FindStartList(list?list:column);
    if (list) {
        BF_CompactStartPath(state,list,column);
        if (auto items=list.try_as<Controls::ItemsControl>()) if (auto panel=items.ItemsPanelRoot()) {
            BF_CompactStartPath(state,panel,list);
            // Newer builds use a grouped GridView for the same one-column app
            // list. Its native list-cell width was sized for the full menu.
            if (!pinned && list.Name()==L"AllAppsGrid") if (auto wrap=panel.try_as<Controls::ItemsWrapGrid>()) {
                auto& saved=BF_StartContentState(state,wrap);
                const double width=column.ActualWidth();
                if (width>0 && (std::isnan(wrap.ItemWidth()) || std::abs(wrap.ItemWidth()-width)>.5))
                    saved.set(wrap,Controls::ItemsWrapGrid::ItemWidthProperty(),winrt::box_value(width));
                if (wrap.MaximumRowsOrColumns()!=1)
                    saved.set(wrap,Controls::ItemsWrapGrid::MaximumRowsOrColumnsProperty(),winrt::box_value(1));
            }
        }
    }
}

// A classic AllAppsPane uses a custom TileGrid under SemanticZoom, while newer
// builds expose AllAppsGrid. Walk structural containers, not just the first
// ListViewBase: private wrappers and deferred templates can hide the real panel.
// Stop at item containers so icon spacing and folder indentation remain native.
static void BF_CompactStartContainers(BF_StartColumns& state,const FrameworkElement& element,
                                      const FrameworkElement& column,int depth=48) {
    if (!depth || element.Name()==L"AllAppsPaneHeader" || element.Name()==L"ZoomAppsList" ||
        element.Name()==L"ZoomedOutListView" || element.Name()==L"PinnedListPipsPager" ||
        element.Name()==L"ExpandedFolderList" || element.try_as<Controls::ListViewItem>() ||
        element.try_as<Controls::GridViewItem>() || element.try_as<Controls::GridViewHeaderItem>() ||
        element.try_as<Controls::Primitives::ScrollBar>() || element.try_as<Controls::Primitives::ButtonBase>()) return;
    const auto type=winrt::get_class_name(element);
    if (type==L"StartMenu.ExpandedFolderList" || type==L"StartMenu.FolderModal") return;
    const bool container=element.try_as<Controls::Panel>() || element.try_as<Controls::Control>() ||
        element.try_as<Controls::Border>() || element.try_as<Controls::ContentPresenter>() ||
        element.try_as<Controls::ItemsPresenter>();
    if (container && element!=column)
        BF_CompactStartPath(state,element,Media::VisualTreeHelper::GetParent(element).try_as<FrameworkElement>());
    const int count=Media::VisualTreeHelper::GetChildrenCount(element);
    for (int i=0;i<count;++i) if (auto child=Media::VisualTreeHelper::GetChild(element,i).try_as<FrameworkElement>())
        BF_CompactStartContainers(state,child,column,depth-1);
}

static void BF_PositionStartColumn(BF_LocalLayout& state,const FrameworkElement& element,
                                   const Controls::Grid& root,double x,double y,double width,double height) {
    if (!state.values.empty() && state.element.get()!=element) state.restore();
    if (state.values.empty()) {
        // Do not reparent Shell template parts or freeze their inherited view model.
        // Native navigation, commands, namescopes and lifecycle retain their ancestry.
        // Native show/hide and search Storyboards address CompositeTransform
        // members by type. A TranslateTransform breaks those paths on reopen.
        state.set(element,UIElement::RenderTransformProperty(),Media::CompositeTransform());
        state.set(element,FrameworkElement::MinWidthProperty(),winrt::box_value(0.0));
        state.set(element,FrameworkElement::MinHeightProperty(),winrt::box_value(0.0));
        state.set(element,FrameworkElement::MaxWidthProperty(),winrt::box_value(std::numeric_limits<double>::infinity()));
        state.set(element,FrameworkElement::MaxHeightProperty(),winrt::box_value(std::numeric_limits<double>::infinity()));
        state.set(element,FrameworkElement::HorizontalAlignmentProperty(),winrt::box_value(HorizontalAlignment::Left));
        state.set(element,FrameworkElement::VerticalAlignmentProperty(),winrt::box_value(VerticalAlignment::Top));
        state.set(element,FrameworkElement::MarginProperty(),winrt::box_value(Thickness{}));
    }
    if (std::isnan(element.Width()) || std::abs(element.Width()-width)>.5)
        state.set(element,FrameworkElement::WidthProperty(),winrt::box_value(width));
    if (std::isnan(element.Height()) || std::abs(element.Height()-height)>.5)
        state.set(element,FrameworkElement::HeightProperty(),winrt::box_value(height));
    auto parent=Media::VisualTreeHelper::GetParent(element).try_as<FrameworkElement>();
    if (!parent) return;
    // Grid row/column slots belong to Windows. Offset within that existing slot;
    // never change its definitions, remove children or capture DataContext.
    auto slot=Controls::Primitives::LayoutInformation::GetLayoutSlot(element);
    wf::Point origin{};
    if (!BF_StartLayoutOrigin(parent,root,origin)) return;
    const double dx=x-origin.X-slot.X,dy=y-origin.Y-slot.Y;
    if (!std::isfinite(dx) || !std::isfinite(dy) ||
        std::abs(dx)>root.ActualWidth() || std::abs(dy)>root.ActualHeight()) return;
    // A positive offset must not consume the original parent's available size:
    // XAML otherwise adds an implicit layout clip, even though ActualWidth and
    // TransformToVisual report the full, correctly positioned element bounds.
    const Thickness margin{dx,dy,-std::max(0.0,dx),-std::max(0.0,dy)};
    const auto current=element.Margin();
    if (std::abs(current.Left-margin.Left)>.5 || std::abs(current.Top-margin.Top)>.5 ||
        std::abs(current.Right-margin.Right)>.5 || std::abs(current.Bottom-margin.Bottom)>.5)
        state.set(element,FrameworkElement::MarginProperty(),winrt::box_value(margin));
}

// This native page normally switches between "Undocked" and "AllApps".
// Its four page-switch storyboards end by hiding one of the two columns.
// Preserve the timelines and completion events used by Windows. Only those
// two grid targets need a neutral final value in side-by-side mode.
static void BF_PrepareStartPage(BF_StartColumns& state,const FrameworkElement& apps,const Controls::Grid& root) {
    using namespace Media::Animation;
    if (state.realizedApps.get()==apps) return;
    state.realizedApps=winrt::make_weak(apps);
    apps.FindName(L"AllAppsPanel");
    auto owner=root.as<FrameworkElement>();
    while (owner) {
        bool contentStates=false;
        for (const auto& group:VisualStateManager::GetVisualStateGroups(owner))
            if (group.Name()==L"ContentStates") {contentStates=true;break;}
        if (contentStates) break;
        owner=Media::VisualTreeHelper::GetParent(owner).try_as<FrameworkElement>();
    }
    if (!owner) return;
    const auto set=[&](const DependencyObject& target,const DependencyProperty& property,const wf::IInspectable& value) {
        state.pageAnimations.push_back({winrt::make_weak(target),property,target.ReadLocalValue(property)});
        target.SetValue(property,value);
    };
    for (const auto& group:VisualStateManager::GetVisualStateGroups(owner)) {
        if (group.Name()!=L"ContentStates") continue;
        for (const auto& mode:group.States()) {
            const auto name=mode.Name();
            if (name!=L"Undocked" && name!=L"AllApps" && name!=L"FlipToUndocked" && name!=L"FlipToAllApps") continue;
            const auto board=mode.Storyboard();
            if (!board) continue;
            bool columnsOnly=true;
            for (const auto& track:board.Children()) {
                const auto target=Storyboard::GetTargetName(track),property=Storyboard::GetTargetProperty(track);
                if (target!=L"AllAppsRoot" && target!=L"UndockedRoot") {columnsOnly=false;continue;}
                if (property==L"Opacity" || property==L"(UIElement.RenderTransform).(CompositeTransform.TranslateX)") {
                    const auto animation=track.try_as<DoubleAnimationUsingKeyFrames>();
                    if (!animation) {columnsOnly=false;continue;}
                    for (const auto& frame:animation.KeyFrames())
                        set(frame,DoubleKeyFrame::ValueProperty(),winrt::box_value(property==L"Opacity"?1.0:0.0));
                } else if (property==L"Visibility") {
                    const auto animation=track.try_as<ObjectAnimationUsingKeyFrames>();
                    if (!animation) {columnsOnly=false;continue;}
                    for (const auto& frame:animation.KeyFrames())
                        set(frame,ObjectKeyFrame::ValueProperty(),winrt::box_value(Visibility::Visible));
                } else {columnsOnly=false;continue;}
                set(track,Timeline::FillBehaviorProperty(),winrt::box_value(FillBehavior::Stop));
            }
            if (columnsOnly && group.CurrentState()==mode && board.GetCurrentState()==ClockState::Filling)
                board.Stop();
        }
    }
}

static void BF_UpdateStartColumns(const std::shared_ptr<BF_StartColumns>& state) {
    auto root=state->root.get();
    if (!root || !root.IsLoaded() || root.ActualWidth()<300 || root.ActualHeight()<200 || state->arranging) return;
    auto apps=BF_FindLayoutElement(root,L"AllAppsRoot"),pinned=BF_FindLayoutElement(root,L"UndockedRoot");
    if (!apps || !pinned || !apps.IsLoaded() || !pinned.IsLoaded()) return;
    state->arranging=true;
    struct Guard {bool& value;~Guard(){value=false;}} guard{state->arranging};
    BF_PrepareStartPage(*state,apps,root);
    const double leftEdge=18,rightEdge=10,inner=root.ActualWidth()-leftEdge-rightEdge,gap=10,left=(inner-gap)*.4;
    BF_PositionStartColumn(state->apps,apps,root,leftEdge,14,left,root.ActualHeight()-78);
    BF_PositionStartColumn(state->pinned,pinned,root,leftEdge+left+gap,14,inner-left-gap,root.ActualHeight()-78);
    BF_CompactStartContents(*state,apps,false);
    BF_CompactStartContainers(*state,apps,apps);
    BF_CompactStartContents(*state,pinned,true);
    BF_CompactStartContainers(*state,pinned,pinned);
    BF_AlignStartItems(*state,apps,false);
    BF_AlignStartItems(*state,pinned,true);
    for (auto& folder:state->folders) if (auto panel=folder.element.get();panel && panel.IsLoaded()) {
        const bool first=folder.values.empty();
        BF_PositionStartColumn(folder,panel,root,leftEdge+left+gap,50,inner-left-gap,root.ActualHeight()-114);
        if (first) {
            if (auto parent=Media::VisualTreeHelper::GetParent(panel).try_as<Controls::Grid>()) {
                folder.set(panel,Controls::Grid::RowProperty(),winrt::box_value(0));
                folder.set(panel,Controls::Grid::RowSpanProperty(),winrt::box_value(static_cast<int>(std::max(1u,parent.RowDefinitions().Size()))));
            }
            if (panel.try_as<Controls::Control>()) {
                folder.set(panel,Controls::Control::HorizontalContentAlignmentProperty(),winrt::box_value(HorizontalAlignment::Stretch));
                folder.set(panel,Controls::Control::VerticalContentAlignmentProperty(),winrt::box_value(VerticalAlignment::Stretch));
            }
        }
    }
}

static bool BF_ArrangeStartColumns(const Controls::Grid& root) {
    if (std::any_of(bf_startColumns.begin(),bf_startColumns.end(),[&](const auto& s){return s->root.get()==root;})) return true;
    // The newer Windows layout already has a real two-column native wrapper.
    if (BF_FindLayoutElement(root,L"SideBySidePinnedWrapper")) return false;
    // RootContent is observed before x:Load creates AllAppsRoot. Register now
    // and let LayoutUpdated handle the later arrival of either native column.
    auto state=std::make_shared<BF_StartColumns>();state->root=winrt::make_weak(root);
    state->layout=root.LayoutUpdated(winrt::auto_revoke,[weak=std::weak_ptr(state)](auto&&,auto&&) {
        if (auto live=weak.lock()) try {
            if (auto root=live->root.get();root && !BF_StartMenuFlyoutOpen(root)) BF_UpdateStartColumns(live);
        }
        catch(const winrt::hresult_error& error){Wh_Log(L"Error %08X: Start column layout",error.code());}
    });
    bf_startColumns.push_back(state);
    BF_UpdateStartColumns(state);
    return true;
}

static void BF_QueueStartColumns(const FrameworkElement& element) {
    if (!bf_is_start_menu || (element.Name()!=L"RootContent" && element.Name()!=L"AllAppsRoot" && element.Name()!=L"UndockedRoot")) return;
    auto root=element;
    while (root && root.Name()!=L"RootContent") root=Media::VisualTreeHelper::GetParent(root).try_as<FrameworkElement>();
    if (!root || !root.try_as<Controls::Grid>()) return;
    element.Dispatcher().RunAsync(winrt::Windows::UI::Core::CoreDispatcherPriority::Normal,
        [weak=winrt::make_weak(root),generation=bf_startLayoutGeneration] {
            if (generation!=bf_startLayoutGeneration) return;
            if (auto live=weak.get()) try { BF_ArrangeStartColumns(live.as<Controls::Grid>()); }
            catch (const winrt::hresult_error& error) {Wh_Log(L"Error %08X: Start columns",error.code());}
        });
}

static void BF_QueueStartFolder(const FrameworkElement& element) {
    if (!bf_is_start_menu) return;
    const auto type=winrt::get_class_name(element);
    if (type!=L"StartMenu.ExpandedFolderList" && type!=L"StartMenu.FolderModal" && element.Name()!=L"ExpandedFolderList") return;
    auto root=element;
    while (root && root.Name()!=L"RootContent") root=Media::VisualTreeHelper::GetParent(root).try_as<FrameworkElement>();
    if (!root || !root.try_as<Controls::Grid>()) return;
    element.Dispatcher().RunAsync(winrt::Windows::UI::Core::CoreDispatcherPriority::Normal,
        [weak=winrt::make_weak(element),parent=winrt::make_weak(root),generation=bf_startLayoutGeneration] {
            if (generation!=bf_startLayoutGeneration) return;
            auto panel=weak.get(),root=parent.get();
            if (!panel || !root) return;
            try {
                BF_ArrangeStartColumns(root.as<Controls::Grid>());
                for (auto& state:bf_startColumns) if (state->root.get()==root) {
                    std::erase_if(state->folders,[](auto& entry){return !entry.element.get();});
                    if (std::none_of(state->folders.begin(),state->folders.end(),[&](auto& entry){return entry.element.get()==panel;})) {
                        BF_LocalLayout entry;
                        entry.element=winrt::make_weak(panel);
                        state->folders.push_back(std::move(entry));
                    }
                    BF_UpdateStartColumns(state);
                    break;
                }
            } catch (const winrt::hresult_error& error) {Wh_Log(L"Error %08X: Start folder layout",error.code());}
        });
}

static void BF_ClearStartColumns() {
    ++bf_startLayoutGeneration;
    auto states=std::exchange(bf_startColumns,{});
    for (auto& state:states) {
        state->layout.revoke();
        for (auto it=state->pageAnimations.rbegin();it!=state->pageAnimations.rend();++it) {
            try {if (auto target=it->element.get()) {
                if (it->original==DependencyProperty::UnsetValue()) target.ClearValue(it->property);
                else target.SetValue(it->property,it->original);
            }} catch (const winrt::hresult_error& e) {Wh_Log(L"Error %08X: restoring Start animation",e.code());}
        }
        for (auto& folder:state->folders) folder.restore();
        for (auto it=state->contents.rbegin();it!=state->contents.rend();++it) it->restore();
        state->apps.restore();state->pinned.restore();
    }
}
