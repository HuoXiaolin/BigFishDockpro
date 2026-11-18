// Runs on the private, non-input test desktop. All source commands are local
// counters; the Settings launcher records the URI without opening Settings.
struct BF_FooterPointerProbe {
    std::vector<std::wstring> labels;
    std::wstring settings;
    BF_FooterPopup source{nullptr};
    size_t target=0;
    ULONGLONG start=0;
    bool checked=false,sent=false,expired=false,cancel=false;
    unsigned attempts=0;
    std::string detail;
};
static thread_local BF_FooterPointerProbe* bf_pointerProbe=nullptr;

static bool BF_ProbeFooterSettings(HWND,PCWSTR uri) {
    if (!bf_pointerProbe) return false;
    bf_pointerProbe->settings=uri;
    return true;
}

static void CALLBACK BF_ProbeMenuPointer(HWND,UINT,UINT_PTR,DWORD) {
    auto probe=bf_pointerProbe;
    if (!probe || !bf_activeFooter) return;
    if (GetTickCount64()-probe->start>1300) {probe->expired=true;EndMenu();return;}
    if (probe->sent) return;
    auto handle=bf_activeFooter->handle;
    bool valid=true;
    unsigned rows=0;
    POINT target{};
    for (int i=0,n=GetMenuItemCount(handle);i<n;++i) {
        MENUITEMINFOW item{sizeof(item)};
        wchar_t text[100]{};
        item.fMask=MIIM_FTYPE|MIIM_ID|MIIM_STRING|MIIM_BITMAP;
        item.dwTypeData=text;item.cch=std::size(text);
        if (!GetMenuItemInfoW(handle,i,TRUE,&item)) return;
        if (item.fType&MFT_SEPARATOR) continue;
        RECT rect{};
        const bool hit=BF_FooterVisibleRow(handle,i,rect);
        if (rows>=probe->labels.size()) return;
        if (rows==probe->target) target={(rect.left+rect.right)/2,(rect.top+rect.bottom)/2};
        valid=valid && hit && probe->labels[rows]==text && item.wID==rows+1 && item.hbmpItem;
        ++rows;
    }
    ++probe->attempts;
    probe->detail=std::to_string(rows)+"rows@"+std::to_string(target.x)+","+std::to_string(target.y);
    if (!valid || rows!=probe->labels.size() || !probe->source || probe->source.IsOpen()) return;
    probe->checked=true;
    auto window=WindowFromPoint(target);
    DWORD pid=0;
    if (GetWindowThreadProcessId(window,&pid)!=GetCurrentThreadId() || pid!=GetCurrentProcessId()) return;
    if (probe->cancel) {probe->sent=true;EndMenu();return;}
    // Address only our fixture's own open USER menu. The desktop guard at
    // BigFishShellProbe's entry excludes the user's interactive desktop.
    // The USER menu tracking loop takes screen coordinates while it owns
    // mouse capture. Ordinary client coordinates would select outside it.
    const auto pos=MAKELPARAM(target.x,target.y);
    probe->sent=PostMessageW(window,WM_MOUSEMOVE,0,pos) && PostMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,pos) &&
                PostMessageW(window,WM_LBUTTONUP,0,pos);
}

static unsigned BF_ProbeFlyoutRows(const Controls::MenuFlyout& menu,const Controls::Button& anchor,
        HWND island,std::initializer_list<PCWSTR> labels,void (*pump)(),bool privateMenu=false) {
    BF_FooterPointerProbe probe;
    std::vector<unsigned> invoked(labels.size());
    std::vector<Controls::MenuFlyoutItem::Click_revoker> subscriptions;
    for (auto label:labels) {
        auto index=probe.labels.size();
        probe.labels.emplace_back(label);
        Controls::MenuFlyoutItem row;
        row.Text(label);
        // The production XAML rows are 28 DIPs. Copying them into a 40-DIP
        // template with the source's total height used to clip the final row.
        row.MinHeight(0);row.Height(28);
        if (index==1) menu.Items().Append(Controls::MenuFlyoutSeparator());
        if (index%2==0 || privateMenu) {
            Controls::FontIcon glyph;glyph.FontFamily(Media::FontFamily(L"Segoe Fluent Icons"));glyph.Glyph(L"\uE713");
            row.Icon(glyph);
        }
        subscriptions.push_back(row.Click(winrt::auto_revoke,[&,index](auto&&,auto&&){++invoked[index];}));
        menu.Items().Append(row);
    }
    Controls::MenuFlyoutItem hidden;
    hidden.Text(L"隐藏的测试项");hidden.Visibility(Visibility::Collapsed);menu.Items().Append(hidden);
    std::ofstream trace(bf_root/L"footer-hit-targets.txt",std::ios::app);
    unsigned verified=0;
    const auto input=BF_PanelScreenRect(anchor,island);
    if (!input) return 0;
    RECT displaced=*input;
    // Reproduce the real host: the source flyout's screen coordinates do not
    // agree with the pointer's button. Both windows stay on the test desktop.
    OffsetRect(&displaced,160,-120);
    for (size_t target=0;target<=probe.labels.size();++target) {
        const bool cancel=target==probe.labels.size();
        probe.target=cancel ? 0 : target;
        probe.cancel=cancel;
        probe.checked=probe.sent=probe.expired=false;probe.settings.clear();probe.attempts=0;probe.detail.clear();
        auto before=invoked;
        menu.ShowAt(anchor);pump();anchor.UpdateLayout();
        auto ready=[&] {
            for (const auto& popup:Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(anchor.XamlRoot()))
                if (auto presenter=BF_FooterPresenter(popup.Child());popup.IsOpen() && presenter && presenter.ActualHeight()>0) {probe.source=popup;return true;}
            return false;
        };
        for (auto until=GetTickCount64()+500;!ready() && GetTickCount64()<until;Sleep(4)) pump();
        if (!ready()) {menu.Hide();return 0;}
        bf_pointerProbe=&probe;
        probe.start=GetTickCount64();
        auto timer=SetTimer(nullptr,0,25,BF_ProbeMenuPointer);
        if (!timer) {bf_pointerProbe=nullptr;menu.Hide();return 0;}
        BF_TryFooterMenu(anchor,island,displaced,true,BF_ProbeFooterSettings);
        for (auto until=GetTickCount64()+1550;!probe.sent && !probe.expired && GetTickCount64()<until;Sleep(2)) pump();
        KillTimer(nullptr,timer);bf_pointerProbe=nullptr;
        pump();
        auto expected=before;PCWSTR uri=nullptr;
        if (!cancel) {
            uri=BF_FooterPresentationFor(probe.labels[target]).settings;
            if (!uri) ++expected[target];
        }
        for (auto until=GetTickCount64()+250;expected!=invoked && GetTickCount64()<until;Sleep(2)) pump();
        bool passed=probe.checked && probe.sent && !probe.expired && expected==invoked &&
            probe.settings==(uri ? uri : L"") && !bf_activeFooter;
        trace<<"row="<<(cancel ? "cancel" : winrt::to_string(winrt::hstring(probe.labels[target])))
             <<" whole_menu_hit="<<probe.checked<<" one_surface="<<(probe.source && !probe.source.IsOpen())
             <<" button_messages="<<probe.sent<<" timeout="<<probe.expired
             <<" settings="<<winrt::to_string(winrt::hstring(probe.settings))<<" passed="<<passed
             <<" observations="<<probe.attempts<<" placement="<<probe.detail<<"\n";
        menu.Hide();pump();
        if (!passed) return 0;
        if (!cancel) ++verified;
    }
    return verified;
}
