#pragma once

struct BF_ModernStartLayout {
    winrt::weak_ref<Controls::GridView> apps;
    winrt::weak_ref<Controls::Border> border;
    winrt::weak_ref<Controls::Grid> header, wrapper;
    winrt::weak_ref<Controls::ScrollViewer> appsScroll;
    winrt::weak_ref<FrameworkElement> search, page;
    std::vector<std::pair<winrt::weak_ref<FrameworkElement>, uint32_t>> moved;
    std::vector<BF_LocalLayout> properties;
    BF_LocalLayout searchSize, pageSlot;
    FrameworkElement::LayoutUpdated_revoker layout;
    Input::FocusManager::GettingFocus_revoker focus;
    UIElement::KeyDown_revoker key;
    bool pending=false, updating=false;
};

static thread_local std::vector<std::shared_ptr<BF_ModernStartLayout>> bf_modernStartLayouts;

template<typename T>
static void BF_SetModernStart(BF_ModernStartLayout& layout,const FrameworkElement& element,
                              const DependencyProperty& property,const T& value) {
    const auto current=winrt::unbox_value<T>(element.GetValue(property));
    if constexpr (std::is_same_v<T,double>) {
        if ((std::isnan(current) && std::isnan(value)) || std::abs(current-value)<.5) return;
    }
    if (current!=value) BF_StartContentState(layout.properties,element).set(element,property,winrt::box_value(value));
}

static Controls::Grid BF_StartGridAncestor(FrameworkElement element,std::wstring_view name) {
    while (element) {
        if (element.Name()==name) return element.try_as<Controls::Grid>();
        element=Media::VisualTreeHelper::GetParent(element).try_as<FrameworkElement>();
    }
    return nullptr;
}

static void BF_RestoreModernStart(BF_ModernStartLayout& state) {
    state.focus.revoke();state.key.revoke();
    state.searchSize.restore();state.pageSlot.restore();
    for (auto saved=state.properties.rbegin();saved!=state.properties.rend();++saved) saved->restore();
    state.properties.clear();
    auto border=state.border.get();
    auto header=state.header.get();
    if (border && header) {
        // Keep the original indexes even for the unnamed heading and button
        // containers used by earlier versions of the redesigned Start menu.
        auto wrapper=state.wrapper.get();
        if (wrapper) {
            auto [pinned,apps]=GetSeparatePinnedScrollViewers(wrapper);
            auto content=pinned.as<Controls::ScrollViewer>().Content().as<Controls::Grid>();
            for (auto& [weak,index]:state.moved) if (auto element=weak.get()) {
                uint32_t current=0;
                if (content.Children().IndexOf(element,current)) {
                    content.Children().RemoveAt(current);
                    header.Children().InsertAt(std::min(index,header.Children().Size()),element);
                }
            }
        }
        RevertSeparatePinnedScrollForBorder(border,header,{});
    }
    state.moved.clear();state.border={};state.header={};state.wrapper={};state.appsScroll={};
}

static void BF_SuspendModernStart() {
    for (auto& state:bf_modernStartLayouts) {
        state->layout.revoke();state->focus.revoke();state->key.revoke();
    }
}

static void BF_ClearModernStart() {
    auto layouts=std::exchange(bf_modernStartLayouts,{});
    for (auto& state:layouts) {
        state->layout.revoke();
        try { BF_RestoreModernStart(*state); }
        catch (...) { Wh_Log(L"Error %08X: restoring redesigned Start",winrt::to_hresult()); }
    }
    g_separatePinnedListFocusedIndexes.clear();
}

static int BF_ModernStartDimension(PCWSTR key,int min,int max) {
    auto setting=BF_Setting(key);
    return std::clamp(static_cast<int>(wcstol(setting.c_str(),nullptr,10)),min,max);
}

static void BF_FitModernSearch(BF_ModernStartLayout& state) {
    if (!bf_search_button_ready) {
        if (!state.pageSlot.values.empty()) {
            state.searchSize.restore();state.pageSlot.restore();
        }
        return;
    }
    if (!state.pageSlot.values.empty()) return;
    auto search=state.search.get(), page=state.page.get();
    if (!search || !page || Controls::Grid::GetRow(page)!=1) return;
    state.searchSize.set(search,FrameworkElement::HeightProperty(),winrt::box_value(0.0));
    state.pageSlot.set(page,Controls::Grid::RowProperty(),winrt::box_value(0));
    state.pageSlot.set(page,Controls::Grid::RowSpanProperty(),winrt::box_value(2));
}

static void BF_FitModernApps(BF_ModernStartLayout& state,const Controls::GridView& apps) {
    auto scroll=state.appsScroll.get();
    auto panel=apps.ItemsPanelRoot().try_as<Controls::ItemsWrapGrid>();
    if (!scroll || !panel || scroll.ViewportWidth()<80) return;
    using Wrap=Controls::ItemsWrapGrid;
    using FE=FrameworkElement;
    using Control=Controls::Control;
    const auto width=std::floor(scroll.ViewportWidth());
    BF_SetModernStart(state,panel,Wrap::MaximumRowsOrColumnsProperty(),1);
    BF_SetModernStart(state,panel,Wrap::ItemWidthProperty(),width);
    BF_SetModernStart(state,panel,FE::MarginProperty(),Thickness{0,0,0,8});
    auto stretch=[&](const FrameworkElement& node) {
        BF_SetModernStart(state,node,FE::MinWidthProperty(),0.0);
        BF_SetModernStart(state,node,FE::MaxWidthProperty(),width);
        BF_SetModernStart(state,node,FE::WidthProperty(),std::numeric_limits<double>::quiet_NaN());
        BF_SetModernStart(state,node,FE::HorizontalAlignmentProperty(),HorizontalAlignment::Stretch);
    };
    for (auto child:panel.Children()) {
        auto row=child.try_as<Controls::GridViewItem>();
        if (!row) continue;
        stretch(row);
        BF_SetModernStart(state,row,FE::MarginProperty(),Thickness{});
        BF_SetModernStart(state,row,Control::PaddingProperty(),Thickness{});
        BF_SetModernStart(state,row,Control::HorizontalContentAlignmentProperty(),HorizontalAlignment::Stretch);
        // Windows list and suite data templates can embed a full-width grid
        // inside an already compact item container.
        auto content=row.ContentTemplateRoot().try_as<FrameworkElement>();
        if (auto inner=content.try_as<Controls::ContentControl>()) {
            stretch(inner);
            content=inner.ContentTemplateRoot().try_as<FrameworkElement>();
        }
        if (content && (content.MinWidth()>width || content.Width()>width)) stretch(content);
    }
}

static bool BF_ApplyModernStart(BF_ModernStartLayout& state,const Controls::GridView& apps) {
    using FE=FrameworkElement;
    using Grid=Controls::Grid;
    using Scroll=Controls::ScrollViewer;
    auto menu=BF_StartGridAncestor(apps,L"MainMenu");
    auto frame=BF_StartGridAncestor(menu,L"FrameRoot");
    if (!menu || !frame || !menu.IsLoaded()) return false;
    auto content=BF_FindLayoutElement(menu,L"MainContent",2).try_as<Grid>();
    if (!content || content.RowDefinitions().Size()!=3) return false;
    auto page=BF_FindLayoutElement(content,L"StartFrame",2).try_as<Controls::Frame>();
    auto surface=BF_FindLayoutElement(menu,L"AcrylicBorder",1).try_as<Controls::Border>();
    auto header=apps.Header().try_as<Grid>();
    if (!page || !surface || !header || header.Name()!=L"TopLevelHeader") return false;

    Controls::Border border{nullptr};
    Scroll original{nullptr};
    if (!IsVisualTreeDescendant(header,apps)) return false;
    for (DependencyObject parent=header;parent && parent!=apps;parent=Media::VisualTreeHelper::GetParent(parent)) {
        auto scroll=parent.try_as<Scroll>();
        if (!scroll) continue;
        auto candidate=Media::VisualTreeHelper::GetParent(scroll).try_as<Controls::Border>();
        if (candidate && candidate.Child()==scroll) {border=candidate;original=scroll;break;}
    }
    if (!border || original.ActualWidth()<1) return false;
    auto pins=BF_FindLayoutElement(header,L"StartMenuPinnedList",4);
    auto pinList=pins ? BF_FindLayoutElement(pins,L"PinnedList").try_as<Controls::GridView>() : nullptr;
    auto appsTitle=BF_FindLayoutElement(header,L"AllListHeading",4).try_as<Grid>();
    auto pinTitle=BF_FindLayoutElement(header,L"PinnedListHeaderText",6).try_as<Controls::TextBlock>();
    if (!pins || !pinList || !appsTitle || !pinTitle || pins.Visibility()!=Visibility::Visible ||
        appsTitle.Visibility()!=Visibility::Visible) return false;
    auto pinHeading=BF_DirectLayoutChild(header,pinTitle);
    if (!pinHeading || BF_DirectLayoutChild(header,pins)!=pins || pinHeading==appsTitle || pinHeading==pins) return false;
    auto showMore=BF_FindLayoutElement(header,L"ShowMorePinnedGrid",4);
    if (!showMore) showMore=BF_FindLayoutElement(header,L"ShowMorePinnedButtonText",8);
    auto more=showMore ? BF_DirectLayoutChild(header,showMore) : nullptr;
    if (more==pinHeading || more==appsTitle || more==pins) more=nullptr;
    auto recommended=BF_FindLayoutElement(header,L"TopLevelSuggestionsRoot",1);

    const auto width=BF_ModernStartDimension(L"bigfish_start_width",480,800);
    const auto height=BF_ModernStartDimension(L"bigfish_start_height",400,900);
    const auto columns=BF_ModernStartDimension(L"bigfish_pin_columns",1,6);
    const auto cellWidth=BF_ModernStartDimension(L"bigfish_pin_cell_width",48,110);
    const auto cellHeight=BF_ModernStartDimension(L"bigfish_pin_cell_height",48,110);
    auto xamlRoot=menu.XamlRoot();
    auto padding=frame.Padding();
    if (!xamlRoot || xamlRoot.Size().Width<width+padding.Left+padding.Right ||
        xamlRoot.Size().Height<height+padding.Top+padding.Bottom || width-columns*cellWidth<160) return false;

    state.border=winrt::make_weak(border);state.header=winrt::make_weak(header);
    state.appsScroll=winrt::make_weak(original);
    state.page=winrt::make_weak(page.as<FrameworkElement>());
    if (auto search=BF_FindLayoutElement(content,L"SearchBoxToggleButton",3)) state.search=winrt::make_weak(search);
    for (uint32_t index=0;index<header.Children().Size();++index) {
        auto part=header.Children().GetAt(index).try_as<FrameworkElement>();
        if (part && (part==pinHeading || part==more || part==pins || part==recommended))
            state.moved.emplace_back(winrt::make_weak(part),index);
    }
    // The pinned and app viewports share the real GridView template. Move the
    // resolved sections in one deferred pass and retain all native controls.
    BF_SetModernStart(state,apps,Scroll::HorizontalScrollModeProperty(),Controls::ScrollMode::Disabled);
    BF_SetModernStart(state,apps,Scroll::HorizontalScrollBarVisibilityProperty(),Controls::ScrollBarVisibility::Disabled);
    BF_StartContentState(state.properties,original).set(original,Grid::ColumnProperty(),winrt::box_value(0));
    bool created=false;
    auto pinContent=EnsureSeparatePinnedScrollViewer(border,&created);
    if (!created || !pinContent) throw winrt::hresult_error(E_UNEXPECTED);
    auto wrapper=border.Child().as<Grid>();
    state.wrapper=winrt::make_weak(wrapper);
    auto pinScroll=Media::VisualTreeHelper::GetParent(pinContent).try_as<Scroll>();
    if (!pinScroll) pinScroll=BF_FindLayoutElement(wrapper,kSeparatePinnedScrollName,1).as<Scroll>();
    wrapper.Padding({18,10,10,6});wrapper.ColumnSpacing(10);
    wrapper.ColumnDefinitions().GetAt(0).Width({1,GridUnitType::Star});
    wrapper.ColumnDefinitions().GetAt(1).Width({columns*cellWidth+24.0,GridUnitType::Pixel});
    Grid::SetColumn(original,0);Grid::SetColumn(pinScroll,1);
    BF_SetModernStart(state,apps,Controls::Control::PaddingProperty(),Thickness{});
    Data::Binding context;
    context.Source(header);context.Path(PropertyPath(L"DataContext"));
    pinContent.SetBinding(FE::DataContextProperty(),context);
    Controls::RowDefinition titleRow, pinsRow, recommendedRow;
    titleRow.Height({36,GridUnitType::Pixel});pinsRow.Height({1,GridUnitType::Auto});
    recommendedRow.Height({1,GridUnitType::Auto});
    pinContent.RowDefinitions().Append(titleRow);pinContent.RowDefinitions().Append(pinsRow);
    pinContent.RowDefinitions().Append(recommendedRow);
    auto place=[&](const FrameworkElement& part,int row,HorizontalAlignment alignment) {
        MoveElementToPinnedContent(part,pinContent);
        BF_SetModernStart(state,part,Grid::RowProperty(),row);
        BF_SetModernStart(state,part,Grid::ColumnProperty(),0);
        BF_SetModernStart(state,part,Grid::ColumnSpanProperty(),1);
        BF_SetModernStart(state,part,FE::MarginProperty(),Thickness{});
        BF_SetModernStart(state,part,FE::HorizontalAlignmentProperty(),alignment);
    };
    place(pinHeading,0,HorizontalAlignment::Left);
    BF_SetModernStart(state,pinHeading,FE::WidthProperty(),static_cast<double>(cellWidth));
    if (more) {
        place(more,0,HorizontalAlignment::Right);
        if (auto button=BF_FindLayoutElement(more,L"ShowMorePinnedButton",4);button)
            BF_SetModernStart(state,button,FE::MarginProperty(),Thickness{});
        else if (auto button=BF_FooterButton(more)) BF_SetModernStart(state,button,FE::MarginProperty(),Thickness{});
    }
    place(pins,1,HorizontalAlignment::Stretch);
    if (recommended) {
        place(recommended,2,HorizontalAlignment::Stretch);
        for (auto name:{L"TopLevelSuggestionsListHeaderText",L"TopLevelSuggestionsContainer",L"ShowMoreSuggestionsButton"})
            if (auto part=BF_FindLayoutElement(recommended,name,5))
                BF_SetModernStart(state,part,FE::MarginProperty(),Thickness{});
    }
    BF_SetModernStart(state,pinTitle,FE::MarginProperty(),Thickness{});
    BF_SetModernStart(state,pinTitle,FE::HorizontalAlignmentProperty(),HorizontalAlignment::Center);
    BF_SetModernStart(state,pinTitle,FE::VerticalAlignmentProperty(),VerticalAlignment::Center);
    BF_SetModernStart(state,pinTitle,Controls::TextBlock::TextAlignmentProperty(),TextAlignment::Center);
    BF_SetModernStart(state,appsTitle,FE::MarginProperty(),Thickness{});
    BF_SetModernStart(state,appsTitle,FE::HeightProperty(),36.0);
    if (auto title=BF_FindLayoutElement(appsTitle,L"AllListHeadingText",3))
        BF_SetModernStart(state,title,FE::MarginProperty(),Thickness{4,0,8,0});
    if (auto choice=BF_FindLayoutElement(appsTitle,L"ViewSelectionButton",3))
        BF_SetModernStart(state,choice,FE::MarginProperty(),Thickness{0,0,10,0});
    const auto automatic=std::numeric_limits<double>::quiet_NaN();
    for (const auto& part:{pins,FrameworkElement(pinList)}) {
        BF_SetModernStart(state,part,FE::MinHeightProperty(),0.0);
        BF_SetModernStart(state,part,FE::MaxHeightProperty(),std::numeric_limits<double>::infinity());
        BF_SetModernStart(state,part,FE::HeightProperty(),automatic);
        BF_SetModernStart(state,part,FE::VerticalAlignmentProperty(),VerticalAlignment::Stretch);
    }
    // The native pinned template has its inner ScrollViewer disabled. Let the
    // right column scroll the pinned grid and recommendations together.
    if (auto panel=pinList.ItemsPanelRoot().try_as<Controls::ItemsWrapGrid>()) {
        BF_SetModernStart(state,panel,Controls::ItemsWrapGrid::MaximumRowsOrColumnsProperty(),columns);
        BF_SetModernStart(state,panel,Controls::ItemsWrapGrid::ItemWidthProperty(),static_cast<double>(cellWidth));
        BF_SetModernStart(state,panel,Controls::ItemsWrapGrid::ItemHeightProperty(),static_cast<double>(cellHeight));
    }

    BF_SetModernStart(state,menu,FE::MinWidthProperty(),0.0);
    BF_SetModernStart(state,menu,FE::MinHeightProperty(),0.0);
    BF_SetModernStart(state,menu,FE::MaxWidthProperty(),static_cast<double>(width));
    BF_SetModernStart(state,menu,FE::WidthProperty(),static_cast<double>(width));
    BF_SetModernStart(state,menu,FE::HeightProperty(),static_cast<double>(height));
    BF_SetModernStart(state,frame,FE::MaxHeightProperty(),height+padding.Top+padding.Bottom);
    BF_SetModernStart(state,frame,FE::HeightProperty(),height+padding.Top+padding.Bottom);
    BF_SetModernStart(state,surface,FE::MarginProperty(),Thickness{});
    if (auto sizing=BF_FindLayoutElement(frame,L"MaxHeightEnforcer",3)) {
        BF_SetModernStart(state,sizing,FE::MaxHeightProperty(),static_cast<double>(height));
        BF_SetModernStart(state,sizing,FE::HeightProperty(),static_cast<double>(height));
    }
    state.focus=Input::FocusManager::GettingFocus(winrt::auto_revoke,[weak=winrt::make_weak(wrapper)](auto&&,const auto& args) {
        if (auto live=weak.get()) OnSeparatePinnedFocusChange(live,args);
    });
    state.key=wrapper.KeyDown(winrt::auto_revoke,[](const wf::IInspectable& sender,const Input::KeyRoutedEventArgs& args) {
        OnSeparatePinnedWrapperKeyDown(sender.as<Grid>(),args);
    });
    return true;
}

static void BF_UpdateModernStart(const std::shared_ptr<BF_ModernStartLayout>& state) {
    if (state->updating) return;
    auto apps=state->apps.get();
    if (!apps || !apps.IsLoaded()) return;
    if (state->wrapper.get()) {
        state->updating=true;
        try { BF_FitModernSearch(*state);BF_FitModernApps(*state,apps); }
        catch (...) { Wh_Log(L"Error %08X: fitting redesigned Start",winrt::to_hresult()); }
        state->updating=false;
        return;
    }
    if (state->pending) return;
    state->pending=true;
    apps.Dispatcher().RunAsync(winrt::Windows::UI::Core::CoreDispatcherPriority::Normal,[weak=std::weak_ptr(state)] {
        auto live=weak.lock();
        if (!live) return;
        live->pending=false;
        auto list=live->apps.get();
        if (!list || !list.IsLoaded()) return;
        DeferCustomizationsScope deferred;
        live->updating=true;
        try { BF_ApplyModernStart(*live,list); }
        catch (...) {
            Wh_Log(L"Error %08X: redesigned Start layout",winrt::to_hresult());
            live->layout.revoke();
            try { BF_RestoreModernStart(*live); }
            catch (...) { Wh_Log(L"Error %08X: rolling back redesigned Start",winrt::to_hresult()); }
        }
        live->updating=false;
    });
}

static void BF_QueueModernStart(const FrameworkElement& element) {
    if (!bf_is_start_menu || element.Name()!=L"AllAppsGrid") return;
    auto apps=element.try_as<Controls::GridView>();
    if (!apps || !BF_StartGridAncestor(apps,L"MainMenu")) return;
    std::erase_if(bf_modernStartLayouts,[](auto& state){ return !state->apps.get(); });
    if (std::any_of(bf_modernStartLayouts.begin(),bf_modernStartLayouts.end(),[&](auto& state){ return state->apps.get()==apps; })) return;
    auto state=std::make_shared<BF_ModernStartLayout>();
    state->apps=winrt::make_weak(apps);
    state->layout=apps.LayoutUpdated(winrt::auto_revoke,[weak=std::weak_ptr(state)](auto&&,auto&&) {
        if (auto live=weak.lock()) BF_UpdateModernStart(live);
    });
    bf_modernStartLayouts.push_back(state);
    BF_UpdateModernStart(state);
}
