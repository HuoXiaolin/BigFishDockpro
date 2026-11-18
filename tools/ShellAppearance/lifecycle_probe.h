// Exercise the real hook / XAML diagnostics path inside the owned test host.
// BigFishShellProbe validates a non-input desktop before calling this function.
static int BF_ProbeLifecycle(PCWSTR directory) {
    const auto trace = [&](const char* stage) {
        std::ofstream file(std::filesystem::path(directory)/L"lifecycle-stage.txt", std::ios::app);
        file << stage << "\n";
    };
    try {
        winrt::init_apartment(winrt::apartment_type::single_threaded);
        auto transport=bf_settings;
        transport[L"owner_pid"]=L"2";transport[L"owner_start"]=L"3";
        transport[L"status_handle_400"]=L"12";transport[L"panel_geometry_400"]=L"16";
        const bool transportStable=BF_StyleSettingsEqual(bf_settings,transport);
        transport[L"bigfish_theme"]=BF_Setting(L"bigfish_theme")==L"Dark"?L"Light":L"Dark";
        const bool styleChanges=!BF_StyleSettingsEqual(bf_settings,transport);
        const bool retry = BF_Setting(L"probe_lifecycle") == L"retry";
        const bool cold = BF_Setting(L"probe_lifecycle") != L"warm";
#ifdef BIGFISH_START_ENGINE
        bf_is_start_menu = true;
#endif
        MH_Initialize();
        const auto initialize = [&] {
            trace("mod_init");
            if (!Wh_ModInit()) throw std::runtime_error("mod_init");
            if (MH_EnableHook(MH_ALL_HOOKS) != MH_OK) throw std::runtime_error("hooks");
            trace("hooks_enabled");
            Wh_ModAfterInit();
            trace("after_init");
        };
        if (cold) initialize();
        bool readinessFailure = !retry;
        if (retry) {
#ifndef BIGFISH_START_ENGINE
            InitializeForCurrentThread();
#endif
            InitializeSettingsAndTap();
            readinessFailure = !BF_XamlInitialized() && bf_last_error!=0;
            trace(readinessFailure ? "early_failure_recoverable" : "early_failure_latched");
        }
        trace("create_xaml");
        auto manager = Hosting::WindowsXamlManager::InitializeForCurrentThread();
        WNDCLASSW type{};type.lpfnWndProc=DefWindowProcW;type.hInstance=GetModuleHandleW(nullptr);
        type.lpszClassName=L"Windows.UI.Core.CoreWindow";RegisterClassW(&type);
        HWND window = CreateWindowExW(0,type.lpszClassName,L"Owned Shell lifecycle fixture",WS_OVERLAPPEDWINDOW,
            0,0,640,720,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
        Hosting::DesktopWindowXamlSource source;
        auto native = source.as<IDesktopWindowXamlSourceNative>();
        winrt::check_hresult(native->AttachToWindow(window));
        HWND child = nullptr;native->get_WindowHandle(&child);
        SetWindowPos(child,nullptr,0,0,600,660,SWP_NOZORDER|SWP_SHOWWINDOW);
        Controls::Grid root;
        Controls::Border border;border.Name(L"LifecycleSurface");
        auto original = Media::SolidColorBrush(winrt::Windows::UI::Colors::Red());
        border.Background(original);root.Children().Append(border);
        source.Content(root);ShowWindow(window,SW_SHOWNOACTIVATE);
        trace("xaml_loaded");
        if (!cold) initialize();
        const auto pump = [](unsigned milliseconds) {
            auto until = GetTickCount64()+milliseconds;
            do {
                MSG msg;
                while (PeekMessageW(&msg,nullptr,0,0,PM_REMOVE)) {TranslateMessage(&msg);DispatchMessageW(&msg);}
                Sleep(5);
            } while(GetTickCount64()<until);
        };
        // XAML Islands may not expose a top-level CoreWindow. In that case use
        // the same initializer directly, still going through diagnostics/TAP.
        BF_RequestShellInitialization(window);
        trace("diagnostics_requested");
        bool applied = false;
        for (unsigned i=0;i<80;++i) {
            pump(25);
            if (border.Background()!=original) {applied=true;break;}
        }
        trace(applied ? "applied" : "not_applied");
        bool firstMutation=true;
        bool firstPresentation=true;
        bool calendarFirstOpen=true;
#ifndef BIGFISH_START_ENGINE
        // Keep the global observer, but simulate a new/unprepared UI thread.
        // The very first control must be styled without a later settings refresh.
        UninitializeForCurrentThread();
        Controls::Border late;late.Name(L"LifecycleSurface");late.Background(original);
        root.Children().Append(late);root.UpdateLayout();pump(20);
        firstMutation=g_initializedForThread && late.Background()!=original;
        trace(firstMutation?"first_mutation_styled":"first_mutation_skipped");
        // Model the calendar's first construction report before Windows assigns
        // the name/parent and final background. No second Add or reopen follows.
        // Detach TAP for this one fixture so a later replay cannot hide the bug.
        if (auto watcher=ExchangeVisualTreeWatcher(nullptr)) watcher->UnadviseVisualTreeChange();
        Controls::Border first;first.Background(original);
        ApplyCustomizations(static_cast<ElementId>(900000),first,L"Windows.UI.Xaml.Controls.Border");
        first.Name(L"LifecycleSurface");root.Children().Append(first);
        first.Background(original);root.UpdateLayout();pump(25);
        firstPresentation=first.Background()!=original;
        trace(firstPresentation?"first_presentation_styled":"first_presentation_skipped");
        // The taskbar date panel can first open well after Dock startup. Exercise
        // the actual calendar selector, both naming before and after Loaded,
        // with no second Add event or settings refresh to rescue the result.
        Controls::Grid calendar;calendar.Background(original);
        ApplyCustomizations(static_cast<ElementId>(900001),calendar,L"Windows.UI.Xaml.Controls.Grid");
        if (cold && !retry) pump(2250);
        if (!retry) calendar.Name(L"CalendarCenterGrid");
        calendar.Height(0);
        root.Children().Append(calendar);root.UpdateLayout();pump(25);
        if (retry) calendar.Name(L"CalendarCenterGrid");
        calendar.Background(original);pump(25);
        calendar.Height(120);root.UpdateLayout();pump(25);
        calendar.Background(original);pump(25);
        calendarFirstOpen=calendar.Background()!=original && calendar.CornerRadius().TopLeft==18 && bf_calendar_matched;
        trace(calendarFirstOpen?"calendar_first_open_styled":"calendar_first_open_skipped");
#endif
        bool refreshed = applied;
        for (unsigned i=0;i<3 && applied;++i) {
            Wh_ModSettingsChanged();pump(100);
            refreshed = refreshed && border.Background()!=original;
        }
        const auto errors = bf_errors.load(), matches = bf_matches.load();
        Wh_ModUninit();MH_DisableHook(MH_ALL_HOOKS);MH_RemoveHook(MH_ALL_HOOKS);
        pump(100);
        const bool restored = border.Background()==original;
        trace("uninitialized");
        // Cancel before the queued UI initializer can run, then process the
        // stale posted callback. It must not reapply styles after disable.
        initialize();Wh_ModUninit();
        MH_DisableHook(MH_ALL_HOOKS);MH_RemoveHook(MH_ALL_HOOKS);
        pump(150);
        const bool cancelled = !bf_init_timer && !BF_XamlInitialized() && border.Background()==original;
        std::ofstream report(std::filesystem::path(directory)/L"lifecycle-probe.json");
        const bool passed=applied&&refreshed&&restored&&cancelled&&readinessFailure&&firstMutation&&firstPresentation&&calendarFirstOpen&&errors==0&&transportStable&&styleChanges;
        report << "{\"passed\":" << (passed?"true":"false") << ",\"applied\":" << applied
               << ",\"refreshed\":" << refreshed << ",\"restored\":" << restored
               << ",\"errors\":" << errors << ",\"matches\":" << matches
               << ",\"readiness_failure_recoverable\":" << readinessFailure
               << ",\"cancelled\":" << cancelled << ",\"first_mutation_styled\":"<<firstMutation
               << ",\"first_presentation_styled\":"<<firstPresentation<<",\"calendar_first_open\":"<<calendarFirstOpen
               << ",\"transport_keeps_styles\":"<<transportStable<<",\"style_changes_detected\":"<<styleChanges
               << ",\"last_error\":" << bf_last_error.load() << "}";
        report.close();
        source.Content(nullptr);source.Close();DestroyWindow(window);manager.Close();
        return passed ? 0 : 92;
    } catch (const winrt::hresult_error& error) {
        std::ofstream report(std::filesystem::path(directory)/L"lifecycle-probe.json");
        report << "{\"passed\":false,\"hresult\":" << static_cast<unsigned>(error.code().value) << "}";
        return 93;
    } catch (...) {trace("exception");return 94;}
}
