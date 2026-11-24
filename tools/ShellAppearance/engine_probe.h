// Isolated native regression. This never attaches to another process.
#include <windows.ui.xaml.hosting.desktopwindowxamlsource.h>
#include <winrt/Windows.UI.Xaml.Controls.Primitives.h>
#ifdef BIGFISH_START_ENGINE
#include "start_layout_probe.h"
#include "start_modern_probe.h"
#include "start_flyout_probe.h"
#endif
#include "lifecycle_probe.h"

static bool BF_ProbeTint(const Media::Brush& brush, unsigned percent, unsigned alpha) {
    if (auto solid = brush.try_as<Media::SolidColorBrush>()) return solid.Color().A == alpha;
    if (auto acrylic = brush.try_as<Media::AcrylicBrush>()) {
        return std::abs(acrylic.TintOpacity() - percent / 100.0) < 0.00001 &&
            acrylic.TintLuminosityOpacity() && acrylic.TintLuminosityOpacity().Value() == 0 &&
            acrylic.FallbackColor().A == alpha;
    }
    auto native = brush.try_as<Media::IXamlCompositionBrushBaseProtected>();
    if (!native) return false;
    auto composition = native.CompositionBrush();
    if (!composition) return false;
    if (auto fallback = composition.try_as<wuc::CompositionColorBrush>()) {
        if (fallback.Color().A != alpha) return false;
    }
    auto style = BF_Setting(L"controlStyles[0].styles[0]");
    auto parsed = ParseNonXamlPropertyOverrideValue(std::wstring_view(style).substr(style.find(L":=") + 2));
    auto blur = parsed ? std::get_if<XamlBlurBrushParams>(&*parsed) : nullptr;
    return blur && blur->tint.A == alpha && blur->fallbackColor && blur->fallbackColor->A == alpha;
}

extern "C" __declspec(dllexport) int WINAPI BigFishShellTransportProbe(PCWSTR directory) {
    wchar_t expected[256]{},actual[256]{};DWORD needed=0;BOOL input=TRUE;
    auto desktop=GetThreadDesktop(GetCurrentThreadId());
    if(!GetEnvironmentVariableW(L"FISHDOCK_TEST_DESKTOP",expected,256)||
       !GetUserObjectInformationW(desktop,UOI_NAME,actual,sizeof(actual),&needed)||wcscmp(expected,actual)||
       !GetUserObjectInformationW(desktop,6,&input,sizeof(input),&needed)||input)return 90;
    bf_root=directory;if(!BF_LoadSettings())return 91;
    bf_matches=1;BF_Status("applied");
    if(!bf_status_file)return 92;
    CloseHandle(bf_status_file);bf_status_file=nullptr;return 0;
}
extern "C" __declspec(dllexport) int WINAPI BigFishShellProbe(PCWSTR directory) {
    BOOL receiving=TRUE;DWORD needed=0;wchar_t expected[256]{},actual[256]{};
    auto desktop=GetThreadDesktop(GetCurrentThreadId());
    if(!GetEnvironmentVariableW(L"FISHDOCK_TEST_DESKTOP",expected,256) ||
       !GetUserObjectInformationW(desktop,UOI_NAME,actual,sizeof(actual),&needed) || wcscmp(expected,actual) ||
       !GetUserObjectInformationW(desktop,6,&receiving,sizeof(receiving),&needed) || receiving)return 90;
    bf_root=directory;bf_matches=0;bf_errors=0;
    if(!BF_LoadSettings())return 91;
    if (!BF_Setting(L"probe_lifecycle").empty()) return BF_ProbeLifecycle(directory);
    HWND window=nullptr;
    try {
        winrt::init_apartment(winrt::apartment_type::single_threaded);
        auto manager=Hosting::WindowsXamlManager::InitializeForCurrentThread();
#ifdef BIGFISH_START_ENGINE
        if (BF_Setting(L"probe_observer_layout")==L"1") return BF_ProbeStartLayout(directory)?0:95;
        if (const auto layout=BF_Setting(L"probe_redesigned_start");!layout.empty())
            return BF_ProbeModernStart(directory,layout==L"named")?0:95;
#endif
        WNDCLASSW fixtureClass{};
        fixtureClass.hInstance=GetModuleHandleW(nullptr);
        fixtureClass.lpfnWndProc=DefWindowProcW;
        fixtureClass.lpszClassName=L"BigFishXamlInputFixture";
        RegisterClassW(&fixtureClass);
        window=CreateWindowExW(0,fixtureClass.lpszClassName,L"BigFish native shell fixture",WS_OVERLAPPEDWINDOW,0,0,870,900,nullptr,nullptr,fixtureClass.hInstance,nullptr);
        Hosting::DesktopWindowXamlSource source;
        auto native=source.as<IDesktopWindowXamlSourceNative>();winrt::check_hresult(native->AttachToWindow(window));
        HWND child=nullptr;native->get_WindowHandle(&child);SetWindowPos(child,nullptr,24,16,795,840,SWP_NOZORDER|SWP_SHOWWINDOW);
        Controls::Grid root;root.Name(L"FrameRoot");
        Controls::Border border;
#ifdef BIGFISH_START_ENGINE
        root.Margin({14,8,0,0});
        border.Name(L"AcrylicBorder");
#else
        border.Name(L"ToastBackgroundBorder");
#endif
        auto original=Media::SolidColorBrush(winrt::Windows::UI::Colors::Orange());
        border.Background(original);border.CornerRadius({3,3,3,3});
#ifdef BIGFISH_START_ENGINE
        Controls::Grid mainMenu, classicRoot;
        mainMenu.Name(L"MainMenu");classicRoot.Name(L"RootContent");
        // The panel fixture isolates shared physical bounds from the StartHome
        // adapter, which sizes a complete redesigned menu in its own probe.
        mainMenu.Width(std::stod(BF_Setting(L"probe_start_width")));
        mainMenu.Height(std::stod(BF_Setting(L"probe_start_height")));
        mainMenu.Children().Append(border);
        root.Children().Append(mainMenu);
        Controls::Border classicBorder;
        classicBorder.Name(L"AcrylicBorder");classicRoot.Children().Append(classicBorder);
        Controls::Grid classicSizingFrame;
        classicSizingFrame.Name(L"StartSizingFrame");classicSizingFrame.Children().Append(classicRoot);
        root.Children().Append(classicSizingFrame);
        Controls::Border overlay;overlay.Name(L"AcrylicOverlay");overlay.Background(original);overlay.BorderThickness({2,2,2,2});root.Children().Append(overlay);
        std::vector<Controls::Border> shadows;
        for (auto name : {L"DropShadow", L"StartDropShadow", L"RootGridDropShadow", L"RightCompanionDropShadow"}) {
            Controls::Border shadow;
            shadow.Name(name);
            shadow.Background(original);
            root.Children().Append(shadow);
            shadows.push_back(shadow);
        }
        Controls::TextBlock allApps,pinned;
        auto white=Media::SolidColorBrush(winrt::Windows::UI::Colors::White());
        auto black=Media::SolidColorBrush(winrt::Windows::UI::Colors::Black());
        allApps.Foreground(white);pinned.Foreground(black);allApps.Text(L"全部应用");pinned.Text(L"已固定");
        root.Children().Append(allApps);root.Children().Append(pinned);
        Controls::Grid undocked, appsRoot, wrapper;
        Controls::ScrollViewer appsScroll, pinnedScroll;
        undocked.Name(L"UndockedRoot");appsRoot.Name(L"AllAppsRoot");wrapper.Name(L"SideBySidePinnedWrapper");
        appsScroll.Name(L"ScrollViewer");pinnedScroll.Name(L"SideBySidePinnedScrollViewer");
        for (int i=0; i<2; ++i) {
            Controls::ColumnDefinition column;
            column.Width({1,GridUnitType::Star});
            wrapper.ColumnDefinitions().Append(column);
        }
        Controls::ListView appsList;
        appsList.Items().Append(winrt::box_value(L"文件资源管理器"));
        appsScroll.Content(appsList);
        Controls::TextBlock pinnedContent;
        pinnedContent.Text(L"系统固定应用");pinnedScroll.Content(pinnedContent);
        Controls::Grid::SetColumn(appsScroll,0);Controls::Grid::SetColumn(pinnedScroll,1);
        wrapper.Children().Append(appsScroll);
        wrapper.Children().Append(pinnedScroll);
        appsRoot.Children().Append(wrapper);
        undocked.Children().Append(appsRoot);
        root.Children().Append(undocked);
        Controls::MenuFlyoutPresenter menu;
        Controls::MenuFlyoutItem menuItem;
        menuItem.Text(L"睡眠");menuItem.Foreground(white);
        menu.Items().Append(menuItem);
        menu.Height(100);menu.Width(160);menu.HorizontalAlignment(HorizontalAlignment::Left);
        menu.Background(original);
        menu.Template(Markup::XamlReader::Load(LR"(<ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
            TargetType="MenuFlyoutPresenter"><Border Background="{TemplateBinding Background}" CornerRadius="{TemplateBinding CornerRadius}"><ItemsPresenter/></Border></ControlTemplate>)").as<Controls::ControlTemplate>());
        root.Children().Append(menu);
        Controls::Grid searchPage, searchRoot, searchOuter, searchFrame;
        Controls::Border searchBorder, searchInput;
        searchPage.Name(L"TaskbarSearchPage");searchPage.Children().Append(searchRoot);
        searchRoot.Name(L"RootGrid");searchOuter.Name(L"OuterBorderGrid");searchFrame.Name(L"BorderGrid");
        searchBorder.Name(L"AppBorder");searchInput.Name(L"TaskbarSearchBackground");
        searchBorder.Background(original);searchInput.Background(original);
        searchInput.Height(36);searchInput.VerticalAlignment(VerticalAlignment::Top);searchInput.Margin({16,16,16,0});
        searchFrame.Children().Append(searchBorder);searchOuter.Children().Append(searchFrame);
        searchRoot.Children().Append(searchOuter);searchRoot.Children().Append(searchInput);
        HWND searchWindow = CreateWindowExW(0,L"STATIC",L"BigFish search panel fixture",WS_POPUP,264,184,875,710,
                                           nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
        Hosting::DesktopWindowXamlSource searchSource;
        auto nativeSearch = searchSource.as<IDesktopWindowXamlSourceNative>();
        winrt::check_hresult(nativeSearch->AttachToWindow(searchWindow));
        HWND searchChild = nullptr;nativeSearch->get_WindowHandle(&searchChild);
        auto viewportSubclass=[](HWND parent,UINT msg,WPARAM wp,LPARAM lp,UINT_PTR id,DWORD_PTR data)->LRESULT {
            if (msg==WM_SIZE) {
                RECT clip{};
                GetClientRect(parent,&clip);
                SetWindowPos(reinterpret_cast<HWND>(data),nullptr,36,21,std::max(1L,clip.right-36),
                             std::max(1L,clip.bottom-21),SWP_NOZORDER|SWP_NOACTIVATE|SWP_SHOWWINDOW);
            }
            return DefSubclassProc(parent,msg,wp,lp);
        };
        SetWindowSubclass(searchWindow,viewportSubclass,1,reinterpret_cast<DWORD_PTR>(searchChild));
        SendMessageW(searchWindow,WM_SIZE,SIZE_RESTORED,MAKELPARAM(875,710));
        Controls::Grid searchShell;
        searchShell.Margin({45,24,0,0});
        Media::TranslateTransform searchOpening;searchShell.RenderTransform(searchOpening);
        Controls::Border searchInset;searchInset.Padding({12,12,12,12});searchInset.Child(searchPage);
        Media::RectangleGeometry searchClip;searchClip.Rect({0,0,536,600});searchInset.Clip(searchClip);
        searchShell.Children().Append(searchInset);
        searchSource.Content(searchShell);ShowWindow(searchWindow, SW_SHOW);
        Controls::Grid navigation,userView,powerView;
        navigation.Height(56);navigation.VerticalAlignment(VerticalAlignment::Bottom);
        for (auto length:{GridLength{1,GridUnitType::Auto},GridLength{1,GridUnitType::Auto},
                          GridLength{1,GridUnitType::Star},GridLength{1,GridUnitType::Auto}}) {
            Controls::ColumnDefinition column;column.Width(length);navigation.ColumnDefinitions().Append(column);
        }
        Controls::ListView places;
        places.Name(L"NavigationPanePlacesListView");places.Width(50);places.MinWidth(0);places.Padding({});
        places.HorizontalAlignment(HorizontalAlignment::Right);
        Controls::ListViewItem gear;
        gear.Content(winrt::box_value(L"设置"));gear.Width(50);gear.MinWidth(0);gear.Margin({});
        places.Items().Append(gear);Controls::Grid::SetColumn(places,3);navigation.Children().Append(places);
        Controls::Button user,power;
        user.Name(L"UserTileButton");user.Content(winrt::box_value(L"示例用户"));
        user.Width(125);user.Height(36);user.HorizontalAlignment(HorizontalAlignment::Right);
        power.Name(L"PowerButton");power.Content(winrt::box_value(L"电源"));
        power.Width(36);power.Height(36);power.HorizontalAlignment(HorizontalAlignment::Center);
        userView.Children().Append(user);userView.Width(145);
        powerView.Name(L"PowerButton");powerView.Width(40);Controls::Grid::SetColumn(powerView,1);
        powerView.Children().Append(power);
        navigation.Children().Append(userView);navigation.Children().Append(powerView);
        root.Children().Append(navigation);
#endif
        std::vector<Controls::Grid> regions;
#ifndef BIGFISH_START_ENGINE
        root.Children().Append(border);
        Controls::Grid quickInner;
        Controls::TextBlock quickLabel;
        quickInner.Name(L"L1Grid");
        quickInner.RequestedTheme(ElementTheme::Dark);
        quickLabel.Text(L"亮度与音量");
        quickInner.Children().Append(quickLabel);
        Controls::Primitives::ToggleButton quickSwitch;quickSwitch.Name(L"ToggleButton");
        quickSwitch.Template(Markup::XamlReader::Load(LR"(<ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="ToggleButton">
          <ContentPresenter x:Name="ContentPresenter" Background="{TemplateBinding Background}">
            <VisualStateManager.VisualStateGroups><VisualStateGroup x:Name="CommonStates">
              <VisualState x:Name="Normal"/><VisualState x:Name="PointerOver"/><VisualState x:Name="Pressed"/>
            </VisualStateGroup></VisualStateManager.VisualStateGroups>
          </ContentPresenter></ControlTemplate>)").as<Controls::ControlTemplate>());
        const auto accentState=Media::SolidColorBrush(winrt::Windows::UI::Color{255,0,103,192});
        quickSwitch.IsChecked(true);quickSwitch.Background(accentState);quickInner.Children().Append(quickSwitch);
        for(auto name:{L"NotificationCenterGrid",L"CalendarCenterGrid",L"ControlCenterRegion",L"MediaTransportControlsRegion"}) {
            Controls::Grid grid;grid.Name(name);grid.Background(original);grid.CornerRadius({3,3,3,3});
            if (std::wstring_view(name) == L"ControlCenterRegion") grid.Children().Append(quickInner);
            root.Children().Append(grid);regions.push_back(grid);
        }
#endif
        source.Content(root);ShowWindow(window,SW_SHOW);
        auto pump=[] {MSG msg;while(PeekMessageW(&msg,nullptr,0,0,PM_REMOVE)){TranslateMessage(&msg);DispatchMessageW(&msg);}};
        pump();root.UpdateLayout();
        ProcessAllStylesFromSettings();
#ifdef BIGFISH_START_ENGINE
        root.Opacity(0.75);
        bf_is_start_menu = true;
        auto mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(uint64_t), nullptr);
        BF_BindPanelGeometry(mapping, true);
        BF_PrepareStartFrame(root, border, child);
        const bool heldBeforeLayout = root.Opacity()==0.0;
#endif
        ApplyCustomizations(static_cast<ElementId>(1),root,L"Windows.UI.Xaml.Controls.Grid");
        ApplyCustomizations(static_cast<ElementId>(2),border,L"Windows.UI.Xaml.Controls.Border");
#ifdef BIGFISH_START_ENGINE
        // This fixture covers both hosts; production loads these rules only in SearchHost.
        ProcessWebStylesFromSettings({}, {});
        ApplyCustomizations(static_cast<ElementId>(100),overlay,L"Windows.UI.Xaml.Controls.Border");
        ApplyCustomizations(static_cast<ElementId>(101),allApps,L"Windows.UI.Xaml.Controls.TextBlock");
        ApplyCustomizations(static_cast<ElementId>(102),pinned,L"Windows.UI.Xaml.Controls.TextBlock");
        for (size_t i=0; i<shadows.size(); ++i)
            ApplyCustomizations(static_cast<ElementId>(103+i),shadows[i],L"Windows.UI.Xaml.Controls.Border");
        ApplyCustomizations(static_cast<ElementId>(120),undocked,L"Windows.UI.Xaml.Controls.Grid");
        ApplyCustomizations(static_cast<ElementId>(121),appsRoot,L"Windows.UI.Xaml.Controls.Grid");
        ApplyCustomizations(static_cast<ElementId>(122),wrapper,L"Windows.UI.Xaml.Controls.Grid");
        ApplyCustomizations(static_cast<ElementId>(123),appsScroll,L"Windows.UI.Xaml.Controls.ScrollViewer");
        ApplyCustomizations(static_cast<ElementId>(124),pinnedScroll,L"Windows.UI.Xaml.Controls.ScrollViewer");
        menu.ApplyTemplate();root.UpdateLayout();
        auto menuBorder=Media::VisualTreeHelper::GetChild(menu,0).as<Controls::Border>();
        ApplyCustomizations(static_cast<ElementId>(130),menu,L"Windows.UI.Xaml.Controls.MenuFlyoutPresenter");
        ApplyCustomizations(static_cast<ElementId>(131),menuBorder,L"Windows.UI.Xaml.Controls.Border");
        ApplyCustomizations(static_cast<ElementId>(132),menuItem,L"Windows.UI.Xaml.Controls.MenuFlyoutItem");
        ApplyCustomizations(static_cast<ElementId>(133),searchBorder,L"Windows.UI.Xaml.Controls.Border");
        ApplyCustomizations(static_cast<ElementId>(134),searchInput,L"Windows.UI.Xaml.Controls.Border");
        ApplyCustomizations(static_cast<ElementId>(135),searchFrame,L"Windows.UI.Xaml.Controls.Grid");
        ApplyCustomizations(static_cast<ElementId>(136),mainMenu,L"Windows.UI.Xaml.Controls.Grid");
        ApplyCustomizations(static_cast<ElementId>(137),classicSizingFrame,L"Windows.UI.Xaml.Controls.Grid");
        bf_is_start_menu = false;
        ApplyCustomizations(static_cast<ElementId>(138),classicBorder,L"Windows.UI.Xaml.Controls.Border");
        ApplyCustomizations(static_cast<ElementId>(139),searchPage,L"Windows.UI.Xaml.Controls.Grid");
        ApplyCustomizations(static_cast<ElementId>(140),searchRoot,L"Windows.UI.Xaml.Controls.Grid");
        ApplyCustomizations(static_cast<ElementId>(141),searchOuter,L"Windows.UI.Xaml.Controls.Grid");
        bf_is_start_menu = true;
        root.UpdateLayout();
        const auto nativeUser=BF_FooterBounds(user,navigation),nativePower=BF_FooterBounds(power,navigation),
                   nativeGear=BF_FooterBounds(gear,navigation);
        BF_AddStartSearchButton(navigation);
        BF_AddStartSearchButton(navigation);
#else
        ApplyCustomizations(static_cast<ElementId>(100),quickInner,L"Windows.UI.Xaml.Controls.Grid");
        auto quickFace=Media::VisualTreeHelper::GetChild(quickSwitch,0).as<Controls::ContentPresenter>();
        VisualStateManager::GoToState(quickSwitch,L"Normal",false);
        ApplyCustomizations(static_cast<ElementId>(101),quickFace,L"Windows.UI.Xaml.Controls.ContentPresenter");
#endif
        for(size_t i=0;i<regions.size();++i)ApplyCustomizations(static_cast<ElementId>(3+i),regions[i],L"Windows.UI.Xaml.Controls.Grid");
        pump();root.UpdateLayout();
#ifdef BIGFISH_START_ENGINE
        for (int i=0; i<32 && root.Opacity()==0; ++i) { Sleep(2); pump(); }
        const auto frameOpacity = root.Opacity();
        const bool revealed = frameOpacity==0.75;
#endif
        bool applied=border.Background()!=original && border.CornerRadius().TopLeft==18;
        for(auto grid:regions)applied=applied && grid.Background()!=original && grid.CornerRadius().TopLeft==18;
        auto probePercent = BF_Setting(L"probe_tint_percent");
        bool tint = true;
        if (!probePercent.empty()) {
            unsigned percent = wcstoul(probePercent.c_str(), nullptr, 10);
            unsigned alpha = wcstoul(BF_Setting(L"probe_tint_alpha").c_str(), nullptr, 10);
            tint = BF_ProbeTint(border.Background(), percent, alpha);
            for (auto grid : regions) tint = tint && BF_ProbeTint(grid.Background(), percent, alpha);
        }
#ifdef BIGFISH_START_ENGINE
        auto columns=wrapper.ColumnDefinitions();
        applied=applied&&undocked.Visibility()==Visibility::Visible&&appsRoot.Visibility()==Visibility::Visible&&
            appsScroll.Visibility()==Visibility::Visible&&pinnedScroll.Visibility()==Visibility::Visible&&
            appsScroll.ActualWidth()>0&&pinnedScroll.ActualWidth()>0&&appsList.Items().Size()==1&&
            columns.Size()==2&&columns.GetAt(0).Width().Value==1&&columns.GetAt(1).Width().Value==1;
        auto foreground=allApps.Foreground().try_as<Media::SolidColorBrush>();
        auto pinnedForeground=pinned.Foreground().try_as<Media::SolidColorBrush>();
        auto clear=overlay.Background().try_as<Media::SolidColorBrush>();
        BYTE expectedInk=BF_Setting(L"bigfish_theme")==L"Dark"?255:0;
        applied=applied&&foreground&&pinnedForeground&&foreground.Color()==pinnedForeground.Color()&&foreground.Color().R==expectedInk;
        applied=applied&&clear&&clear.Color().A==0&&overlay.BorderThickness().Left==0&&overlay.Margin().Top==0;
        applied=applied&&overlay.Visibility()==Visibility::Collapsed;
        for (auto shadow : shadows) applied=applied&&shadow.Visibility()==Visibility::Collapsed;
        auto menuInk=menu.Foreground().try_as<Media::SolidColorBrush>();
        auto menuSurface=menuBorder.Background();
        applied=applied&&menuInk&&menuInk.Color().R==expectedInk&&menuSurface!=original&&menuSurface==menu.Background()&&
            menuItem.Foreground()==white&&menuBorder.IsHitTestVisible()&&menuItem.IsHitTestVisible()&&menuBorder.CornerRadius().TopLeft==12;
        applied=applied&&searchBorder.Background()!=original&&searchBorder.CornerRadius().TopLeft==18&&
            searchInput.Background()!=original&&searchInput.CornerRadius().TopLeft==12;
        if (!probePercent.empty()) {
            auto percent = wcstoul(probePercent.c_str(), nullptr, 10);
            auto alpha = wcstoul(BF_Setting(L"probe_tint_alpha").c_str(), nullptr, 10);
            tint = tint && BF_ProbeTint(searchBorder.Background(),percent,alpha)&&BF_ProbeTint(menuSurface,percent,alpha);
        }
        const auto searchCss = CreateWebViewJsCodeForApply();
        auto searchWidth=wcstoul(BF_Setting(L"probe_start_width").c_str(),nullptr,10);
        auto searchHeight=wcstoul(BF_Setting(L"probe_start_height").c_str(),nullptr,10);
        auto measuredWidth=searchFrame.MaxWidth(), measuredHeight=searchFrame.MaxHeight();
        const auto startWidth = bf_start_width.load(), startHeight = bf_start_height.load();
        const bool classicSized = classicSizingFrame.Width()==searchWidth && classicSizingFrame.Height()==searchHeight &&
            std::abs(classicBorder.ActualWidth()-searchWidth)<=.5 && std::abs(classicBorder.ActualHeight()-searchHeight)<=.5 &&
            BF_StartPanelParent(classicBorder)==classicRoot;
        const auto startRect = BF_PanelScreenRect(border, child);
        pump();searchShell.UpdateLayout();
        const auto searchRect = BF_PanelScreenRect(searchBorder,searchChild);
        RECT originalSearchWindow{};
        GetWindowRect(searchWindow,&originalSearchWindow);
        const bool reproducedClip=searchRect && !BF_FullPanel(*searchRect,searchChild,BF_PanelPeer(searchBorder));
        const auto publishedStart=BF_ReadPanelGeometry();
        if (bf_startFrame) bf_startFrame->layout.revoke();
        BF_WritePanelGeometry(0);
        BF_TrackSearchFrame(searchBorder,searchChild);
        BF_UpdateSearchPanel();
        pump();searchShell.UpdateLayout();pump();
        MONITORINFO monitor{sizeof(monitor)};
        GetMonitorInfoW(MonitorFromWindow(searchWindow,MONITOR_DEFAULTTONEAREST),&monitor);
        const auto fallbackRect=BF_PanelScreenRect(searchBorder,searchChild);
        const auto expectedAnchor=searchRect ? BF_SearchAnchor(originalSearchWindow,*searchRect,monitor,
            std::lround(12*searchShell.XamlRoot().RasterizationScale())) : std::nullopt;
        const bool directSearchAnchored=fallbackRect && expectedAnchor && EqualRect(&*fallbackRect,&*expectedAnchor) &&
            BF_FullPanel(*fallbackRect,searchChild,BF_PanelPeer(searchBorder)) && !bf_search_position_ready;
        BF_WritePanelGeometry(publishedStart);
        // Keep the Shell's opening transform alive while only the bottom of
        // the page is visible, then finish the animation without any input.
        searchOpening.Y(-440);
        BF_UpdateSearchPanel(true);
        pump();searchShell.UpdateLayout();pump();
        const bool shellOwnsAnimation=searchShell.RenderTransform()==searchOpening && !bf_search_position_ready;
        searchOpening.Y(0);
        const auto settleDeadline=GetTickCount64()+750;
        while (!bf_search_position_ready && GetTickCount64()<settleDeadline) {pump();Sleep(4);}
        const auto alignedRect = BF_PanelScreenRect(searchBorder,searchChild);
        const auto inputRect=BF_PanelScreenRect(searchInput,searchChild);
        const bool searchAligned = shellOwnsAnimation && bf_search_position_ready && startRect && searchRect && alignedRect &&
            inputRect && BF_ContainsPanel(*alignedRect,*inputRect) && bf_searchInputBounds==BF_EncodePanelRect(*inputRect) &&
            !BF_CoincidentPanels(*searchRect,*startRect) && EqualRect(&*alignedRect,&*startRect) &&
            BF_FullPanel(*alignedRect,searchChild,BF_PanelPeer(searchBorder));
        Media::RectangleGeometry hiddenInput;hiddenInput.Rect({0,0,64,1});searchInput.Clip(hiddenInput);
        BF_UpdateSearchPanel();const bool rejectsHiddenInput=!bf_search_position_ready;
        searchInput.Clip(nullptr);
        bool searchStable=true;
        for (int retry=0;retry<8;++retry) {
            if (retry==4) SetWindowPos(searchWindow,nullptr,180,20,900,1000,BF_SearchMoveFlags);
            BF_UpdateSearchPanel();pump();searchShell.UpdateLayout();pump();
            auto face=BF_PanelScreenRect(searchBorder,searchChild);
            searchStable=searchStable&&face&&startRect&&BF_CoincidentPanels(*face,*startRect)&&
                BF_CoincidentPanels(BF_ClientScreenRect(searchChild),*startRect);
        }
        if (bf_searchFrame) bf_searchFrame->originalWindow=originalSearchWindow;
        BF_ClearSearchFrames();
        const bool innerClipRestored=searchInset.Padding().Right==12 && searchInset.Clip()==searchClip;
        RECT restoredWindow{};
        GetWindowRect(searchWindow,&restoredWindow);
        const bool positionRestored=EqualRect(&restoredWindow,&originalSearchWindow);
        applied=applied&&measuredWidth==searchWidth&&measuredHeight==searchHeight&&
            mainMenu.Width()==searchWidth&&mainMenu.Height()==searchHeight&&
            heldBeforeLayout&&revealed&&startWidth==searchWidth&&startHeight==searchHeight&&
            classicSized&&reproducedClip&&directSearchAnchored&&searchAligned&&rejectsHiddenInput&&positionRestored&&searchStable&&innerClipRestored;
        applied=applied&&g_webContentJs.empty()&&g_webContentCss.contains(L".previewContainer")&&
            g_webContentCss.contains(L"[data-region=\"TopApps\"]")&&g_webContentCss.contains(L"QuickSearch")&&
            g_webContentCss.contains(L".curatedSettingsGroup")&&g_webContentCss.contains(L".topItemsGroup")&&
            g_webContentCss.contains(expectedInk==255 ? L"color: #ffffff !important" : L"color: #000000 !important")&&
            g_webContentCss.contains(L"outline: 1px solid")&&
            BF_IsSearchDocument(wf::Uri(L"https://www.bing.com/WS/Init?locale=zh-CN"))&&
            BF_IsSearchDocument(wf::Uri(L"https://cn.bing.com/WS/Init?cc=CN#root"))&&
            BF_IsSearchDocument(wf::Uri(L"https://searchapp.bundleassets.example/desktop/2.html?offline=1"))&&
            !BF_IsSearchDocument(wf::Uri(L"https://www.bing.com/search?q=test"))&&
            searchCss.contains(L"bigfish-windows-search-style")&&
            searchCss.contains(L"bigfish-search-styled")&&
            std::wstring_view(CreateWebViewJsCodeForClear()).contains(L"bigfish-windows-search-style");
        auto shortcut=navigation.Children().GetAt(navigation.Children().Size()-1).as<Controls::Button>();
        auto userBounds=BF_FooterBounds(user,navigation),powerBounds=BF_FooterBounds(power,navigation),gearBounds=BF_FooterBounds(gear,navigation);
        auto shortcutBounds=BF_FooterBounds(shortcut,navigation);
        const bool footerAligned=userBounds==nativeUser && powerBounds==nativePower && gearBounds==nativeGear &&
            userBounds.X>=0 && powerBounds.X>=userBounds.X+userBounds.Width &&
            gearBounds.Width>0 && gearBounds.X+gearBounds.Width<=navigation.ActualWidth()+1 &&
            shortcutBounds.X>=powerBounds.X+powerBounds.Width && shortcutBounds.X+shortcutBounds.Width<=gearBounds.X &&
            shortcut.IsHitTestVisible() && shortcut.IsTabStop() && bf_search_button_ready;
        Controls::MenuFlyout accountMenu,powerMenu;
        using Placement=Controls::Primitives::FlyoutPlacementMode;
        powerMenu.Placement(Placement::Top);
        const auto accountPlacement=accountMenu.Placement();
        user.Flyout(accountMenu);Controls::Primitives::FlyoutBase::SetAttachedFlyout(power,powerMenu);
        const bool nativePolicy=!accountMenu.ShouldConstrainToRootBounds() && !powerMenu.ShouldConstrainToRootBounds();
        const bool nativePlacement=accountMenu.Placement()==accountPlacement && powerMenu.Placement()==Placement::Top;
        const bool testRows=BF_Setting(L"probe_footer_hit_test")==L"1";
        unsigned popupHitRows=0;
        unsigned privateHitRows=0;
        unsigned contextHitRows=0;
        if (testRows) {
            // The search positioning checks used a second owned window.
            ShowWindow(searchWindow,SW_HIDE);
            SetWindowPos(window,HWND_TOP,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_SHOWWINDOW);
            SetActiveWindow(window);SetFocus(child);pump();
            popupHitRows=BF_ProbeFlyoutRows(accountMenu,user,child,{L"更改帐户设置",L"锁定",L"注销"},pump);
            popupHitRows+=BF_ProbeFlyoutRows(powerMenu,power,child,{L"登录选项",L"睡眠",L"关机",L"重启"},pump);
            Controls::MenuFlyout privateMenu;
            privateHitRows=BF_ProbeFlyoutRows(privateMenu,power,child,{L"示例设置"},pump,true);
            Controls::MenuFlyout appMenu,settingsMenu;
            contextHitRows=BF_ProbeFlyoutRows(appMenu,user,child,{L"固定到“开始”屏幕",L"更多",L"卸载"},pump,false,true);
            contextHitRows+=BF_ProbeFlyoutRows(settingsMenu,gear,child,{L"“开始”菜单设置"},pump,false,true);
        }
        const auto searchGlyph=shortcut.Content().as<Controls::FontIcon>();
        bool liveInk=true;
        if (bf_startInkTone.load()>=0) {
            const int originalTone=bf_startInkTone.load();
            for (int tone:{255-originalTone,originalTone}) {
                bf_startInkTone=tone;BF_RefreshStartInk();
                for (auto brush:{allApps.Foreground(),pinned.Foreground(),menu.Foreground(),searchGlyph.Foreground()})
                    liveInk=liveInk && brush==bf_startTextBrush && brush.as<Media::SolidColorBrush>().Color().R==tone;
            }
        }
        applied=applied&&liveInk&&nativePolicy&&(!testRows || (popupHitRows==7 && privateHitRows==1 && contextHitRows==4));
        applied=applied&&footerAligned&&nativePlacement&&navigation.Children().Size()==4&&shortcut.Visibility()==Visibility::Visible&&
            shortcutBounds.X+shortcutBounds.Width<=gearBounds.X&&
            shortcut.Content().as<Controls::FontIcon>().Foreground().as<Media::SolidColorBrush>().Color().R==expectedInk&&
            winrt::Windows::UI::Xaml::Automation::AutomationProperties::GetName(shortcut)==L"搜索";
#else
        auto expectedTheme = BF_Setting(L"bigfish_theme")==L"Dark" ? ElementTheme::Dark : ElementTheme::Light;
        const bool firstChecked=quickFace.CornerRadius().TopLeft==30 && quickFace.Background()==accentState;
        quickSwitch.IsChecked(false);quickSwitch.Background(original);pump();
        const bool unchecked=quickFace.Background()==original;
        quickSwitch.IsChecked(true);quickSwitch.Background(accentState);pump();
        const bool switchColors=firstChecked&&unchecked&&quickFace.Background()==accentState;
        applied=applied&&quickInner.RequestedTheme()==expectedTheme&&quickLabel.ActualTheme()==expectedTheme&&switchColors;
#endif
        auto errors=bf_errors.load();auto matches=bf_matches.load();
        CleanupCustomizations(static_cast<ElementId>(2));
        CleanupCustomizations(static_cast<ElementId>(1));
        for(size_t i=0;i<regions.size();++i)CleanupCustomizations(static_cast<ElementId>(3+i));
#ifdef BIGFISH_START_ENGINE
        CleanupCustomizations(static_cast<ElementId>(100));
        CleanupCustomizations(static_cast<ElementId>(101));
        CleanupCustomizations(static_cast<ElementId>(102));
        for (size_t i=0; i<shadows.size(); ++i) CleanupCustomizations(static_cast<ElementId>(103+i));
        for (int id=124; id>=120; --id) CleanupCustomizations(static_cast<ElementId>(id));
#else
        CleanupCustomizations(static_cast<ElementId>(101));
        CleanupCustomizations(static_cast<ElementId>(100));
#endif
        bool restored=border.Background()==original && border.CornerRadius().TopLeft==3;
#ifdef BIGFISH_START_ENGINE
        restored=restored&&overlay.Background()==original&&overlay.BorderThickness().Left==2&&allApps.Foreground()==white&&pinned.Foreground()==black;
        restored=restored&&overlay.Visibility()==Visibility::Visible;
        for (auto shadow : shadows) restored=restored&&shadow.Visibility()==Visibility::Visible;
        for (int id=141; id>=130; --id) CleanupCustomizations(static_cast<ElementId>(id));
        BF_ClearStartSearchButtons();
        restored=restored&&!accountMenu.ShouldConstrainToRootBounds()&&!powerMenu.ShouldConstrainToRootBounds()&&
            accountMenu.Placement()==accountPlacement&&powerMenu.Placement()==Placement::Top&&
            navigation.Children().Size()==3&&menuBorder.Background()==original&&
            menuItem.Foreground()==white&&searchBorder.Background()==original&&searchInput.Background()==original&&
            std::isinf(searchFrame.MaxWidth())&&std::isinf(searchFrame.MaxHeight());
        auto originalColumns=wrapper.ColumnDefinitions();
        restored=restored&&pinnedScroll.Visibility()==Visibility::Visible&&wrapper.Children().Size()==2&&
            originalColumns.Size()==2&&originalColumns.GetAt(0).Width().Value==1&&originalColumns.GetAt(1).Width().Value==1;
#else
        restored=restored&&quickInner.RequestedTheme()==ElementTheme::Dark;
#endif
        for(auto grid:regions)restored=restored && grid.Background()==original && grid.CornerRadius().TopLeft==3;
        int result=applied&&tint&&restored&&errors==0?0:92;
#ifdef BIGFISH_START_ENGINE
        const bool fullLayout=BF_ProbeStartLayout(bf_root);
        if (!fullLayout) result=92;
        UninitializeSettingsAndTap();
        BF_UnbindPanelGeometry();
        RemoveWindowSubclass(searchWindow,viewportSubclass,1);
        searchSource.Content(nullptr);searchSource.Close();DestroyWindow(searchWindow);
#else
        UninitializeForCurrentThread();
#endif
        std::ofstream report(bf_root/(std::wstring(BF_KIND)+L"-probe.json"));
        report<<"{\"passed\":"<<(result==0?"true":"false")<<",\"applied\":"<<applied<<",\"tint\":"<<tint<<",\"restored\":"<<restored<<",\"errors\":"<<errors<<",\"matches\":"<<matches;
#ifdef BIGFISH_START_ENGINE
        report<<",\"held\":"<<heldBeforeLayout<<",\"revealed\":"<<revealed<<",\"frame_opacity\":"<<frameOpacity
              <<",\"start_box\":["<<startWidth<<","<<startHeight<<"]"
              <<",\"classic_sized\":"<<classicSized<<",\"search_aligned\":"<<searchAligned
              <<",\"clipped_before\":"<<reproducedClip<<",\"direct_search_anchored\":"<<directSearchAnchored
              <<",\"footer_aligned\":"<<footerAligned<<",\"popup_native_placement\":"<<nativePlacement
              <<",\"footer_xw\":["<<navigation.ActualWidth()<<","<<userBounds.X<<","<<userBounds.Width<<","<<powerBounds.X<<","<<powerBounds.Width
              <<","<<shortcutBounds.X<<","<<shortcutBounds.Width<<","<<gearBounds.X<<","<<gearBounds.Width<<"]"
              <<",\"popup_screen_hit_rows\":"<<popupHitRows<<",\"private_menu_hit_rows\":"<<privateHitRows<<",\"live_start_ink\":"<<liveInk
              <<",\"context_menu_hit_rows\":"<<contextHitRows
              <<",\"search_position_restored\":"<<positionRestored;
        report<<",\"search_stable\":"<<searchStable<<",\"complete_layout\":"<<fullLayout;
        if (startRect && alignedRect) {
            report<<",\"start_edges\":["<<startRect->left<<","<<startRect->top<<","<<startRect->right<<","<<startRect->bottom<<"]"
                  <<",\"search_edges\":["<<alignedRect->left<<","<<alignedRect->top<<","<<alignedRect->right<<","<<alignedRect->bottom<<"]";
        }
#endif
        report<<"}";
        report.close();
        source.Content(nullptr);source.Close();source=nullptr;native=nullptr;
        regions.clear();root=nullptr;border=nullptr;original=nullptr;pump();
        DestroyWindow(window);window=nullptr;manager.Close();manager=nullptr;
        return result;
    }catch(winrt::hresult_error const& error) {
        std::ofstream report(bf_root/(std::wstring(BF_KIND)+L"-probe.json"));
        report<<"{\"passed\":false,\"hresult\":"<<(unsigned long)error.code().value<<",\"stage\":\"native_xaml\"}";
        if(window)DestroyWindow(window);return 93;
    }catch(...) {if(window)DestroyWindow(window);return 94;}
}
