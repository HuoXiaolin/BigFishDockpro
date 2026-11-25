#pragma once

// The shell owns the folder, its items and its outer pager. Scroll within the
// current native item source before passing a wheel notch on to that pager.
struct BF_FolderPage {
    winrt::weak_ref<Controls::GridView> list;
    winrt::weak_ref<Controls::ItemsWrapGrid> panel;
    BF_LocalLayout height, padding;
    FrameworkElement::LayoutUpdated_revoker layout;
    UIElement::PointerWheelChanged_revoker wheel;
    int remainder=0;
};
static thread_local std::vector<std::shared_ptr<BF_FolderPage>> bf_folderPages;

static bool BF_ScrollFolderPage(BF_FolderPage& page,int delta) {
    auto list=page.list.get();
    auto scroll=list ? BF_FindLayoutElement(list,L"ScrollViewer").try_as<Controls::ScrollViewer>() : nullptr;
    if (!delta || !scroll || list.Items().Size()<=9 || scroll.ViewportHeight()<1) return false;
    const double step=scroll.ViewportHeight(), current=scroll.VerticalOffset();
    if ((delta>0 && current<.5) || (delta<0 && current>=scroll.ScrollableHeight()-.5)) {
        page.remainder=0;
        return false;
    }
    if ((page.remainder<0)!=(delta<0)) page.remainder=0;
    page.remainder+=delta;
    const int turns=page.remainder/WHEEL_DELTA;
    if (!turns) return true;
    page.remainder%=WHEEL_DELTA;
    const double index=turns<0 ? std::floor((current+.5)/step) : std::ceil((current-.5)/step);
    return scroll.ChangeView(nullptr,std::clamp((index-turns)*step,0.,scroll.ScrollableHeight()),nullptr,true);
}

static void BF_UpdateFolderPage(BF_FolderPage& page) {
    auto list=page.list.get();
    if (!list || !list.IsLoaded()) return;
    auto panel=list.ItemsPanelRoot().try_as<Controls::ItemsWrapGrid>();
    if (!panel || !std::isfinite(panel.ItemHeight()) || panel.ItemHeight()<1) return;
    const auto rows=(list.Items().Size()+2)/3;
    const double height=std::clamp(rows,1u,3u)*panel.ItemHeight();
    if (list.Height()!=height) page.height.set(list,FrameworkElement::HeightProperty(),winrt::box_value(height));
    if (page.panel.get()!=panel) {
        page.wheel.revoke();
        page.padding.restore();
        page.panel=winrt::make_weak(panel);
        page.remainder=0;
        auto viewport=BF_FindLayoutElement(list,L"ScrollContentPresenter").try_as<UIElement>();
        if (!viewport) viewport=panel;
        page.wheel=viewport.PointerWheelChanged(winrt::auto_revoke,[&page](auto&& sender,const Input::PointerRoutedEventArgs& args) {
            try {
                auto point=args.GetCurrentPoint(sender.template as<UIElement>()).Properties();
                if (!point.IsHorizontalMouseWheel() && BF_ScrollFolderPage(page,point.MouseWheelDelta())) args.Handled(true);
            } catch (const winrt::hresult_error&) {}
        });
    }
    // Pad only the final page, so the tenth icon can start at the top without
    // adding focusable placeholders or changing the shell's item indexes.
    auto presenter=Media::VisualTreeHelper::GetParent(panel).try_as<Controls::ItemsPresenter>();
    if (presenter) {
        auto padding=presenter.Padding();
        const double bottom=rows>3 ? ((3-rows%3)%3)*panel.ItemHeight() : 0.;
        if (padding.Bottom!=bottom) {
            padding.Bottom=bottom;
            page.padding.set(presenter,Controls::ItemsPresenter::PaddingProperty(),winrt::box_value(padding));
        }
    }
}

static void BF_WatchFolderList(const FrameworkElement& element) {
    if (!bf_is_start_menu) return;
    const auto name=element.Name();
    if (name!=L"FolderList" && name!=L"LevelOneGridView" && name!=L"LevelTwoGridView") return;
    auto list=element.try_as<Controls::GridView>();
    if (!list) return;
    auto parent=Media::VisualTreeHelper::GetParent(list).try_as<FrameworkElement>();
    while (parent) {
        const auto type=winrt::get_class_name(parent);
        if (type==L"StartMenu.ExpandedFolderList" || type==L"StartMenu.FolderModal" ||
            parent.Name()==L"ExpandedFolderList" || parent.Name()==L"StartFolderModal") break;
        parent=Media::VisualTreeHelper::GetParent(parent).try_as<FrameworkElement>();
    }
    if (!parent) return;
    std::erase_if(bf_folderPages,[](const auto& page){return !page->list.get();});
    for (const auto& page:bf_folderPages) if (page->list.get()==list) return;
    auto page=std::make_shared<BF_FolderPage>();
    page->list=winrt::make_weak(list);
    page->layout=list.LayoutUpdated(winrt::auto_revoke,[weak=std::weak_ptr(page)](auto&&,auto&&) {
        try {if (auto live=weak.lock()) BF_UpdateFolderPage(*live);} catch (const winrt::hresult_error&) {}
    });
    bf_folderPages.push_back(page);
    BF_UpdateFolderPage(*page);
}

static void BF_ClearFolderPages() {
    for (auto& page:bf_folderPages) {
        page->layout.revoke();page->wheel.revoke();
        page->padding.restore();page->height.restore();
    }
    bf_folderPages.clear();
}
