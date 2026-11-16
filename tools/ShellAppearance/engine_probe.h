// Isolated native regression. This never attaches to another process.
#include <windows.ui.xaml.hosting.desktopwindowxamlsource.h>

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
    HWND window=nullptr;
    try {
        winrt::init_apartment(winrt::apartment_type::single_threaded);
        auto manager=Hosting::WindowsXamlManager::InitializeForCurrentThread();
        window=CreateWindowExW(0,L"STATIC",L"BigFish native shell fixture",WS_OVERLAPPEDWINDOW,0,0,680,760,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
        Hosting::DesktopWindowXamlSource source;
        auto native=source.as<IDesktopWindowXamlSourceNative>();winrt::check_hresult(native->AttachToWindow(window));
        HWND child=nullptr;native->get_WindowHandle(&child);SetWindowPos(child,nullptr,0,0,640,710,SWP_NOZORDER|SWP_SHOWWINDOW);
        Controls::Grid root;root.Name(L"FrameRoot");
        Controls::Border border;
#ifdef BIGFISH_START_ENGINE
        border.Name(L"AcrylicBorder");
#else
        border.Name(L"ToastBackgroundBorder");
#endif
        auto original=Media::SolidColorBrush(winrt::Windows::UI::Colors::Orange());
        border.Background(original);border.CornerRadius({3,3,3,3});root.Children().Append(border);
#ifdef BIGFISH_START_ENGINE
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
#endif
        std::vector<Controls::Grid> regions;
#ifndef BIGFISH_START_ENGINE
        Controls::Grid quickInner;
        Controls::TextBlock quickLabel;
        quickInner.Name(L"L1Grid");
        quickInner.RequestedTheme(ElementTheme::Dark);
        quickLabel.Text(L"亮度与音量");
        quickInner.Children().Append(quickLabel);
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
        ApplyCustomizations(static_cast<ElementId>(1),root,L"Windows.UI.Xaml.Controls.Grid");
        ApplyCustomizations(static_cast<ElementId>(2),border,L"Windows.UI.Xaml.Controls.Border");
#ifdef BIGFISH_START_ENGINE
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
#else
        ApplyCustomizations(static_cast<ElementId>(100),quickInner,L"Windows.UI.Xaml.Controls.Grid");
#endif
        for(size_t i=0;i<regions.size();++i)ApplyCustomizations(static_cast<ElementId>(3+i),regions[i],L"Windows.UI.Xaml.Controls.Grid");
        pump();root.UpdateLayout();
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
            columns.Size()==2&&columns.GetAt(0).Width().Value==270&&columns.GetAt(1).Width().Value==368;
        auto foreground=allApps.Foreground().try_as<Media::SolidColorBrush>();
        auto pinnedForeground=pinned.Foreground().try_as<Media::SolidColorBrush>();
        auto clear=overlay.Background().try_as<Media::SolidColorBrush>();
        BYTE expectedInk=BF_Setting(L"bigfish_theme")==L"Dark"?255:0;
        applied=applied&&foreground&&pinnedForeground&&foreground.Color()==pinnedForeground.Color()&&foreground.Color().R==expectedInk;
        applied=applied&&clear&&clear.Color().A==0&&overlay.BorderThickness().Left==0&&overlay.Margin().Top==0;
        applied=applied&&overlay.Visibility()==Visibility::Collapsed;
        for (auto shadow : shadows) applied=applied&&shadow.Visibility()==Visibility::Collapsed;
#else
        auto expectedTheme = BF_Setting(L"bigfish_theme")==L"Dark" ? ElementTheme::Dark : ElementTheme::Light;
        applied=applied&&quickInner.RequestedTheme()==expectedTheme&&quickLabel.ActualTheme()==expectedTheme;
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
        CleanupCustomizations(static_cast<ElementId>(100));
#endif
        bool restored=border.Background()==original && border.CornerRadius().TopLeft==3;
#ifdef BIGFISH_START_ENGINE
        restored=restored&&overlay.Background()==original&&overlay.BorderThickness().Left==2&&allApps.Foreground()==white&&pinned.Foreground()==black;
        restored=restored&&overlay.Visibility()==Visibility::Visible;
        for (auto shadow : shadows) restored=restored&&shadow.Visibility()==Visibility::Visible;
        auto originalColumns=wrapper.ColumnDefinitions();
        restored=restored&&pinnedScroll.Visibility()==Visibility::Visible&&wrapper.Children().Size()==2&&
            originalColumns.Size()==2&&originalColumns.GetAt(0).Width().Value==1&&originalColumns.GetAt(1).Width().Value==1;
#else
        restored=restored&&quickInner.RequestedTheme()==ElementTheme::Dark;
#endif
        for(auto grid:regions)restored=restored && grid.Background()==original && grid.CornerRadius().TopLeft==3;
        int result=applied&&tint&&restored&&errors==0?0:92;
#ifdef BIGFISH_START_ENGINE
        UninitializeSettingsAndTap();
#else
        UninitializeForCurrentThread();
#endif
        std::ofstream report(bf_root/(std::wstring(BF_KIND)+L"-probe.json"));
        report<<"{\"passed\":"<<(result==0?"true":"false")<<",\"applied\":"<<applied<<",\"tint\":"<<tint<<",\"restored\":"<<restored<<",\"errors\":"<<errors<<",\"matches\":"<<matches<<"}";
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
