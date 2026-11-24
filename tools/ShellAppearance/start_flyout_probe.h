// Runs on the private, non-input test desktop. All source commands are local
// counters; the Settings launcher records the URI without opening Settings.
struct BF_FooterPointerProbe {
    std::vector<std::wstring> labels;
    std::wstring settings;
    BF_FooterPopup source{nullptr};
    size_t target=0;
    size_t submenuRow=SIZE_MAX;
    ULONGLONG start=0;
    bool checked=false,sent=false,expired=false,cancel=false,palette=false,hoverPosted=false,submenuPosted=false;
    bool submenuReadyBeforeInput=false;
    unsigned attempts=0;
    std::string detail, paintDetail;
};
static thread_local BF_FooterPointerProbe* bf_pointerProbe=nullptr;

static bool BF_ProbeFooterSettings(HWND,PCWSTR uri) {
    if (!bf_pointerProbe) return false;
    bf_pointerProbe->settings=uri;
    return true;
}

// Capture the open USER popup at its allocated size on the private desktop.
// Checking the strings or drawing into a larger surface misses clipped labels.
static bool BF_ProbeFooterRow(const BF_FooterMenu& menu,const RECT& row,const std::wstring& label,bool selected,std::string& detail) {
    const POINT center{(row.left+row.right)/2,(row.top+row.bottom)/2};
    const auto popup=WindowFromPoint(center);
    RECT frame{};
    if (!popup || !GetWindowRect(popup,&frame) || !BF_ContainsPanel(frame,row) || label.empty()) return false;
    const int width=row.right-row.left,height=row.bottom-row.top;
    detail=" row_px="+std::to_string(width)+"x"+std::to_string(height);
    if (!menu.font) return true; // Windows draws its own native labels in high contrast.
    HDC dc=CreateCompatibleDC(nullptr);
    if (!dc) return false;
    BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth=frame.right-frame.left;info.bmiHeader.biHeight=frame.top-frame.bottom;
    info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
    void* bits=nullptr;
    auto image=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,nullptr,0);
    if (!image) {DeleteDC(dc);return false;}
    auto previous=SelectObject(dc,image);
    const bool printed=PrintWindow(popup,dc,0)!=FALSE;
    auto oldFont=SelectObject(dc,menu.font);
    std::vector<int> advances(label.size());
    SIZE size{};
    const bool measured=GetTextExtentExPointW(dc,label.data(),static_cast<int>(label.size()),0,nullptr,advances.data(),&size)!=FALSE;
    const int x=row.left-frame.left,y=center.y-frame.top;
    const int textLeft=x+MulDiv(36,menu.dpi,96);
    const int required=textLeft-x+size.cx+MulDiv(7,menu.dpi,96);
    auto hasInk=[&](int left,int right) {
        for (int px=left;px<right;++px) for (int py=y-size.cy/2;py<=y+size.cy/2;++py) {
            const auto color=GetPixel(dc,px,py);
            if (color==CLR_INVALID) continue;
            auto distance=[color](COLORREF other) {return abs(GetRValue(color)-GetRValue(other))+abs(GetGValue(color)-GetGValue(other))+abs(GetBValue(color)-GetBValue(other));};
            if (distance(menu.ink)<distance(menu.fill)) return true;
        }
        return false;
    };
    const bool palette=GetPixel(dc,x+width-3,y)==menu.fill;
    const bool insetHover=!selected || GetPixel(dc,x+MulDiv(7,menu.dpi,96),y)==BF_FooterBlend(menu.fill,menu.ink,10);
    const int w=info.bmiHeader.biWidth,h=-info.bmiHeader.biHeight;
    HRGN region=CreateRectRgn(0,0,0,0);
    const int regionKind=region ? GetWindowRgn(popup,region) : ERROR;
    DWM_WINDOW_CORNER_PREFERENCE corner=DWMWCP_DEFAULT;
    const bool compositor=regionKind==ERROR &&
        std::find(menu.framedWindows.begin(),menu.framedWindows.end(),popup)!=menu.framedWindows.end() &&
        SUCCEEDED(DwmGetWindowAttribute(popup,DWMWA_WINDOW_CORNER_PREFERENCE,&corner,sizeof(corner))) &&
        corner==DWMWCP_ROUND;
    const bool clipped=regionKind==COMPLEXREGION && PtInRegion(region,w/2,h/2) &&
        !PtInRegion(region,2,2) && !PtInRegion(region,w-3,2) && !PtInRegion(region,2,h-3) && !PtInRegion(region,w-3,h-3);
    const int edge=clipped ? 1 : 0;
    const bool frameFill=GetPixel(dc,w/2,edge)==menu.fill && GetPixel(dc,edge,y)==menu.fill &&
        GetPixel(dc,w-1-edge,y)==menu.fill && GetPixel(dc,w/2,h-1-edge)==menu.fill;
    bool divider=true;
    for (int pos=0,n=GetMenuItemCount(menu.handle);pos<n;++pos) {
        MENUITEMINFOW item{sizeof(item)};item.fMask=MIIM_FTYPE;
        if (!GetMenuItemInfoW(menu.handle,pos,TRUE,&item) || !(item.fType&MFT_SEPARATOR)) continue;
        RECT gap{};
        if (!GetMenuItemRect(nullptr,menu.handle,pos,&gap)) {divider=false;break;}
        const int lineY=(gap.top+gap.bottom)/2-frame.top;
        divider=GetPixel(dc,x+3,lineY)==menu.fill && GetPixel(dc,w/2,lineY)==BF_FooterBlend(menu.fill,menu.ink,14);
        if (!divider) break;
    }
    bool complete=printed && (compositor || clipped) && frameFill && divider && measured && width>=required && height>=size.cy && palette && insetHover && hasInk(x+2,textLeft-1);
    int start=0;
    for (size_t i=0;complete && i<label.size();++i) {
        if (label[i]!=L' ' && advances[i]>start) complete=hasInk(textLeft+start,textLeft+advances[i]);
        start=advances[i];
    }
    detail+=" required_px="+std::to_string(required)+" popup_capture="+std::to_string(printed)+
        " compositor_rounding="+std::to_string(compositor)+" region_fallback="+std::to_string(clipped)+
        " frame_fill="+std::to_string(frameFill)+" divider="+std::to_string(divider)+" inset_hover="+std::to_string(selected && insetHover);
    if (printed && selected && (label==L"登录选项" || label==L"更改帐户设置")) {
        // PrintWindow captures the menu pixels before DWM composites them.
        GdiFlush();
        if (clipped) for (int py=0;py<h;++py) for (int px=0;px<w;++px)
            if (!PtInRegion(region,px,py)) static_cast<DWORD*>(bits)[py*w+px]=0x00c2cbd2;
        BF_WriteProbeBitmap(bf_root/(label==L"登录选项" ? L"footer-power.bmp" : L"footer-account.bmp"),w,h,bits);
    }
    if (region) DeleteObject(region);
    SelectObject(dc,oldFont);
    SelectObject(dc,previous);DeleteObject(image);DeleteDC(dc);
    return complete;
}

// Exercise the buffered first draw without asking USER to repaint the open window.
// A two-colour backdrop distinguishes screen-positioned glass from a flat fallback.
static bool BF_ProbeBufferedSubmenu(BF_FooterMenu& menu,HMENU submenu,HWND popup,RECT row) {
    MENUITEMINFOW item{sizeof(item)};item.fMask=MIIM_DATA|MIIM_ID;
    if (!GetMenuItemInfoW(submenu,1,TRUE,&item) || !item.dwItemData) return false;
    RECT client{};POINT origin{};
    if (!GetClientRect(popup,&client) || !ClientToScreen(popup,&origin)) return false;
    OffsetRect(&row,-origin.x,-origin.y);
    if (row.right-row.left<12 || row.bottom-row.top<8 || row.right>client.right || row.bottom>client.bottom) return false;
    HDC dc=CreateCompatibleDC(nullptr);
    if (!dc) return false;
    auto dib=[dc](int w,int h,void** pixels){
        BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biPlanes=1;
        info.bmiHeader.biBitCount=32;info.bmiHeader.biWidth=w;info.bmiHeader.biHeight=-h;
        return CreateDIBSection(dc,&info,DIB_RGB_COLORS,pixels,nullptr,0);
    };
    void *source=nullptr,*dest=nullptr;
    auto backdrop=dib(client.right,1,&source), output=dib(client.right,client.bottom,&dest);
    bool passed=false;
    if (backdrop && output && !WindowFromDC(dc) && BF_FindFooterWindow(submenu,dc)==popup) {
        auto pixels=static_cast<DWORD*>(source);
        for (int x=0;x<client.right;++x) pixels[x]=x<client.right/2 ? 0x00d03040 : 0x002050e0;
        auto prior=SelectObject(dc,output);
        auto oldBackdrop=menu.backdrop;auto oldBounds=menu.backdropBounds;auto oldSize=menu.backdropSize;
        menu.backdrop=backdrop;menu.backdropBounds=client;OffsetRect(&menu.backdropBounds,origin.x,origin.y);
        menu.backdropSize={client.right,1};
        DRAWITEMSTRUCT draw{};draw.CtlType=ODT_MENU;draw.itemID=item.wID;draw.itemAction=ODA_DRAWENTIRE;
        draw.itemData=item.dwItemData;draw.hwndItem=reinterpret_cast<HWND>(submenu);draw.hDC=dc;draw.rcItem=row;
        const bool painted=SendMessageW(menu.owner,WM_DRAWITEM,0,reinterpret_cast<LPARAM>(&draw))==TRUE;
        menu.backdrop=oldBackdrop;menu.backdropBounds=oldBounds;menu.backdropSize=oldSize;
        const auto left=GetPixel(dc,row.left+5,row.top+2),right=GetPixel(dc,row.right-6,row.top+2);
        passed=painted && left==RGB(208,48,64) && right==RGB(32,80,224);
        SelectObject(dc,prior);
    }
    if (output) DeleteObject(output);
    if (backdrop) DeleteObject(backdrop);
    DeleteDC(dc);return passed;
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
    HMENU submenu=nullptr;
    for (int i=0,n=GetMenuItemCount(handle);i<n;++i) {
        MENUITEMINFOW item{sizeof(item)};
        wchar_t text[100]{};
        item.fMask=MIIM_FTYPE|MIIM_ID|MIIM_STRING|MIIM_SUBMENU;
        item.dwTypeData=text;item.cch=std::size(text);
        if (!GetMenuItemInfoW(handle,i,TRUE,&item)) return;
        if (item.fType&MFT_SEPARATOR) continue;
        RECT rect{};
        const bool hit=BF_FooterVisibleRow(handle,i,rect);
        if (rows>=probe->labels.size()) return;
        if (rows==probe->target) {
            target={(rect.left+rect.right)/2,(rect.top+rect.bottom)/2};
            submenu=item.hSubMenu;
            if (hit && probe->hoverPosted)
                probe->palette=BF_ProbeFooterRow(*bf_activeFooter,rect,probe->labels[rows],true,probe->paintDetail);
        }
        valid=valid && hit && probe->labels[rows]==text &&
            (rows==probe->submenuRow ? item.hSubMenu!=nullptr : item.wID==rows+1+(rows>probe->submenuRow));
        ++rows;
    }
    ++probe->attempts;
    probe->detail=std::to_string(rows)+"rows@"+std::to_string(target.x)+","+std::to_string(target.y);
    if (!valid || rows!=probe->labels.size() || !probe->source || probe->source.IsOpen()) return;
    probe->checked=true;
    auto window=WindowFromPoint(target);
    DWORD pid=0;
    if (GetWindowThreadProcessId(window,&pid)!=GetCurrentThreadId() || pid!=GetCurrentProcessId()) return;
    // Address only our fixture's own open USER menu. The desktop guard at
    // BigFishShellProbe's entry excludes the user's interactive desktop.
    // The USER menu tracking loop takes screen coordinates while it owns
    // mouse capture. Ordinary client coordinates would select outside it.
    const auto pos=MAKELPARAM(target.x,target.y);
    if (!probe->hoverPosted) {probe->hoverPosted=PostMessageW(window,WM_MOUSEMOVE,0,pos)!=FALSE;return;}
    if (probe->cancel) {probe->sent=true;EndMenu();return;}
    if (submenu) {
        if (!probe->submenuPosted) {
            probe->submenuPosted=PostMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,pos) && PostMessageW(window,WM_LBUTTONUP,0,pos);
        }
        RECT row{};
        if (!BF_FooterVisibleRow(submenu,1,row)) return;
        POINT child{(row.left+row.right)/2,(row.top+row.bottom)/2};
        auto popup=WindowFromPoint(child);
        if (GetWindowThreadProcessId(popup,&pid)!=GetCurrentThreadId() || pid!=GetCurrentProcessId()) return;
        // Inspect the already visible popup. PrintWindow and pointer motion
        // both trigger paint and could conceal a broken first frame.
        const auto& frames=bf_activeFooter->framedWindows;
        if (std::find(frames.begin(),frames.end(),popup)==frames.end()) return;
        DWM_WINDOW_CORNER_PREFERENCE corner=DWMWCP_DEFAULT;
        const bool compositor=SUCCEEDED(DwmGetWindowAttribute(popup,DWMWA_WINDOW_CORNER_PREFERENCE,&corner,sizeof(corner))) && corner==DWMWCP_ROUND;
        HRGN region=CreateRectRgn(0,0,0,0);
        const bool clipped=region && GetWindowRgn(popup,region)==COMPLEXREGION && !PtInRegion(region,0,0);
        if (region) DeleteObject(region);
        if (!compositor && !clipped) return;
        if (!BF_ProbeBufferedSubmenu(*bf_activeFooter,submenu,popup,row)) return;
        probe->submenuReadyBeforeInput=true;
        const auto childPosition=MAKELPARAM(child.x,child.y);
        probe->sent=PostMessageW(popup,WM_LBUTTONDOWN,MK_LBUTTON,childPosition) && PostMessageW(popup,WM_LBUTTONUP,0,childPosition);
        return;
    }
    probe->sent=PostMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,pos) && PostMessageW(window,WM_LBUTTONUP,0,pos);
}

static unsigned BF_ProbeFlyoutRows(const Controls::MenuFlyout& menu,const FrameworkElement& anchor,
        HWND island,std::initializer_list<PCWSTR> labels,void (*pump)(),bool privateMenu=false,bool contextMenu=false) {
    BF_FooterPointerProbe probe;
    std::vector<unsigned> invoked(labels.size());
    unsigned otherFolderHits=0;
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
        if (index%2==0 || privateMenu || contextMenu) {
            Controls::FontIcon glyph;glyph.FontFamily(Media::FontFamily(L"Segoe Fluent Icons"));
            const auto symbol=BF_FooterPresentationFor(label).glyph;
            glyph.Glyph(*symbol ? symbol : L"\uE713");
            row.Icon(glyph);
        }
        subscriptions.push_back(row.Click(winrt::auto_revoke,[&,index](auto&&,auto&&){++invoked[index];}));
        if (contextMenu && std::wstring_view(label)==L"更多") {
            probe.submenuRow=index;
            Controls::MenuFlyoutSubItem more;
            more.Text(label);more.Icon(row.Icon());row.Icon(nullptr);row.Text(L"文件夹");
            Controls::MenuFlyoutItem other;other.Text(L"文件夹");
            subscriptions.push_back(other.Click(winrt::auto_revoke,[&](auto&&,auto&&){++otherFolderHits;}));
            more.Items().Append(other);
            more.Items().Append(row);menu.Items().Append(more);
        } else menu.Items().Append(row);
    }
    if (contextMenu) anchor.ContextFlyout(menu);
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
        probe.checked=probe.sent=probe.expired=probe.palette=probe.hoverPosted=probe.submenuPosted=probe.submenuReadyBeforeInput=false;
        probe.settings.clear();probe.attempts=0;probe.detail.clear();probe.paintDetail.clear();
        auto before=invoked;
        BF_StopFooterRequest();
        if (contextMenu) {BF_ArmContextPreview(anchor);menu.ShowAt(anchor,{0,0});}
        else {BF_ArmFooterPreview(anchor.as<BF_FooterCommandButton>());menu.ShowAt(anchor);}
        pump();anchor.UpdateLayout();
        auto ready=[&] {
            for (const auto& popup:Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(anchor.XamlRoot()))
                if (auto presenter=BF_FooterPresenter(popup.Child());popup.IsOpen() && presenter && presenter.ActualHeight()>0) {probe.source=popup;return true;}
            return false;
        };
        for (auto until=GetTickCount64()+500;!ready() && GetTickCount64()<until;Sleep(4)) pump();
        if (!ready()) {BF_StopFooterRequest();menu.Hide();return 0;}
        auto sourceVisual=winrt::Windows::UI::Xaml::Hosting::ElementCompositionPreview::GetElementVisual(probe.source.Child());
        for (auto until=GetTickCount64()+250;sourceVisual.IsVisible() && GetTickCount64()<until;Sleep(2)) pump();
        const bool previewHidden=!sourceVisual.IsVisible() && probe.source.Child().Opacity()==0;
        bf_pointerProbe=&probe;
        probe.start=GetTickCount64();
        auto timer=SetTimer(nullptr,0,25,BF_ProbeMenuPointer);
        if (!timer) {bf_pointerProbe=nullptr;BF_StopFooterRequest();menu.Hide();return 0;}
        if (contextMenu) BF_TryStartContextMenu(anchor,island,{displaced.left,displaced.top});
        else BF_TryFooterMenu(anchor.as<BF_FooterCommandButton>(),island,displaced,true,BF_ProbeFooterSettings);
        for (auto until=GetTickCount64()+1550;!probe.sent && !probe.expired && GetTickCount64()<until;Sleep(2)) pump();
        KillTimer(nullptr,timer);bf_pointerProbe=nullptr;
        pump();
        auto expected=before;PCWSTR uri=nullptr;
        if (!cancel) {
            uri=BF_FooterPresentationFor(probe.labels[target]).settings;
            if (!uri) ++expected[target];
        }
        for (auto until=GetTickCount64()+250;expected!=invoked && GetTickCount64()<until;Sleep(2)) pump();
        bool passed=previewHidden && sourceVisual.IsVisible() && probe.palette && probe.checked && probe.sent && !probe.expired && expected==invoked &&
            !otherFolderHits && (cancel || target!=probe.submenuRow || probe.submenuReadyBeforeInput) &&
            probe.settings==(uri ? uri : L"") && !bf_activeFooter;
        trace<<"row="<<(cancel ? "cancel" : winrt::to_string(winrt::hstring(probe.labels[target])))
             <<" whole_menu_hit="<<probe.checked<<" one_surface="<<(probe.source && !probe.source.IsOpen())
             <<" button_messages="<<probe.sent<<" timeout="<<probe.expired<<" submenu_styled_before_input="<<probe.submenuReadyBeforeInput
             <<" source_hidden="<<previewHidden<<" source_restored="<<sourceVisual.IsVisible()<<" menu_colors="<<probe.palette
             <<" settings="<<winrt::to_string(winrt::hstring(probe.settings))<<" passed="<<passed
             <<" observations="<<probe.attempts<<" placement="<<probe.detail<<probe.paintDetail<<"\n";
        menu.Hide();pump();
        if (!passed) return 0;
        if (!cancel) ++verified;
    }
    if (contextMenu) anchor.ContextFlyout(nullptr);
    return verified;
}
