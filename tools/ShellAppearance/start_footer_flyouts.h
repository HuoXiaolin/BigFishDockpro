#pragma once
#include <winrt/Windows.UI.Input.h>

// Only Start's two footer menus use this fallback. The normal XAML flyout is
// kept when its rows are reachable where Windows drew them.
using BF_FooterCommandButton = Controls::Primitives::ButtonBase;
using BF_FooterPopup = Controls::Primitives::Popup;
namespace BF_FooterPeers = winrt::Windows::UI::Xaml::Automation::Peers;
namespace BF_FooterProviders = winrt::Windows::UI::Xaml::Automation::Provider;

struct BF_FooterCommand {
    Controls::MenuFlyoutItem source{nullptr};
    BF_FooterProviders::IInvokeProvider invoke{nullptr};
    BF_FooterProviders::IToggleProvider toggle{nullptr};
};

struct BF_FooterMenu {
    HMENU handle=CreatePopupMenu();
    std::vector<BF_FooterCommand> commands;
    std::vector<HBITMAP> icons;
    HBRUSH background=nullptr;
    winrt::weak_ref<BF_FooterCommandButton> anchor;
    HWND owner=nullptr;
    UINT_PTR measureTimer=0;
    bool cancelled=false;
    ~BF_FooterMenu() {
        if (measureTimer) KillTimer(nullptr,measureTimer);
        if (handle) DestroyMenu(handle);
        if (background) DeleteObject(background);
        for (auto icon:icons) DeleteObject(icon);
    }
};

static thread_local BF_FooterMenu* bf_activeFooter=nullptr;
static thread_local winrt::weak_ref<BF_FooterCommandButton> bf_openingFooter;
static thread_local DispatcherTimer bf_footerTimer{nullptr};
static thread_local unsigned bf_footerRequest=0;

static void BF_ColorFooterMenu(BF_FooterMenu& menu) {
    HIGHCONTRASTW contrast{sizeof(contrast)};
    if (!SystemParametersInfoW(SPI_GETHIGHCONTRAST,sizeof(contrast),&contrast,0) ||
        (contrast.dwFlags&HCF_HIGHCONTRASTON)) return;
    const auto value=BF_Setting(L"bigfish_footer_surface");
    if (value.size()!=7 || value.front()!=L'#') return;
    wchar_t* end=nullptr;
    const auto hex=wcstoul(value.c_str()+1,&end,16);
    if (!end || *end) return;
    COLORREF color=RGB((hex>>16)&255,(hex>>8)&255,hex&255);
    const auto ink=GetSysColor(COLOR_MENUTEXT),base=GetSysColor(COLOR_MENU);
    const auto luminance=[](COLORREF v) {
        const auto linear=[](int c) {double n=c/255.;return n<=.04045 ? n/12.92 : std::pow((n+.055)/1.055,2.4);};
        return .2126*linear(GetRValue(v))+.7152*linear(GetGValue(v))+.0722*linear(GetBValue(v));
    };
    const double fg=luminance(ink);
    const COLORREF original=color;
    for (int step=1;step<=10;++step) {
        const double bg=luminance(color);
        if ((std::max(bg,fg)+.05)/(std::min(bg,fg)+.05)>=4.5) break;
        const auto mix=[step](int a,int b){return (a*(10-step)+b*step)/10;};
        color=RGB(mix(GetRValue(original),GetRValue(base)),mix(GetGValue(original),GetGValue(base)),mix(GetBValue(original),GetBValue(base)));
    }
    menu.background=CreateSolidBrush(color);
    MENUINFO info{sizeof(info)};info.fMask=MIM_BACKGROUND|MIM_APPLYTOSUBMENUS;info.hbrBack=menu.background;
    if (menu.background) SetMenuInfo(menu.handle,&info);
}

static bool BF_FooterMenuActive(const XamlRoot& root) {
    auto button=bf_activeFooter ? bf_activeFooter->anchor.get() : nullptr;
    return button && button.XamlRoot()==root;
}

static void BF_CloseFooterMenu() {
    if (bf_activeFooter) {bf_activeFooter->cancelled=true;EndMenu();}
}

static Controls::MenuFlyoutPresenter BF_FooterPresenter(const DependencyObject& node,int depth=6) {
    if (!node) return nullptr;
    if (auto presenter=node.try_as<Controls::MenuFlyoutPresenter>()) return presenter;
    if (!depth || node.try_as<Controls::ToolTip>()) return nullptr;
    const int count=Media::VisualTreeHelper::GetChildrenCount(node);
    for (int i=0;i<count;++i)
        if (auto presenter=BF_FooterPresenter(Media::VisualTreeHelper::GetChild(node,i),depth-1)) return presenter;
    return nullptr;
}

struct BF_FooterGlyph {winrt::hstring text, family;};

struct BF_FooterPresentation {PCWSTR glyph=L"";PCWSTR settings=nullptr;};

static BF_FooterPresentation BF_FooterPresentationFor(std::wstring_view name) {
    if (name==L"登录选项" || name==L"登入選項" || name==L"Sign-in options")
        return {L"\uE713",L"ms-settings:signinoptions"};
    if (name==L"更改帐户设置" || name==L"更改账户设置" || name==L"變更帳戶設定" || name==L"Change account settings")
        return {L"\uE713",L"ms-settings:yourinfo"};
    if (name==L"睡眠" || name==L"Sleep") return {L"\uE708"};
    if (name==L"关机" || name==L"關機" || name==L"Shut down") return {L"\uE7E8"};
    if (name==L"重启" || name==L"重新启动" || name==L"重新啟動" || name==L"Restart") return {L"\uE72C"};
    if (name==L"锁定" || name==L"鎖定" || name==L"Lock") return {L"\uE72E"};
    if (name==L"注销" || name==L"登出" || name==L"Sign out") return {L"\uF3B1"};
    return {};
}

static BF_FooterGlyph BF_ReadFooterGlyph(const DependencyObject& node,int depth=8) {
    if (!node) return {};
    if (auto font=node.try_as<Controls::FontIcon>())
        return {font.Glyph(),font.FontFamily() ? font.FontFamily().Source() : L"Segoe Fluent Icons"};
    if (auto symbol=node.try_as<Controls::SymbolIcon>())
        return {winrt::hstring(std::wstring(1,static_cast<wchar_t>(symbol.Symbol()))),L"Segoe MDL2 Assets"};
    if (auto label=node.try_as<Controls::TextBlock>()) {
        const auto glyph=label.Text();
        if (glyph.size()==1 && glyph[0]>=0xe000 && glyph[0]<=0xf8ff && label.FontFamily())
            return {glyph,label.FontFamily().Source()};
    }
    if (depth) {
        const auto count=Media::VisualTreeHelper::GetChildrenCount(node);
        for (int i=0;i<count;++i) {
            auto glyph=BF_ReadFooterGlyph(Media::VisualTreeHelper::GetChild(node,i),depth-1);
            if (!glyph.text.empty()) return glyph;
        }
    }
    return {};
}

static HBITMAP BF_FooterBitmap(const BF_FooterGlyph& glyph,UINT dpi) {
    if (glyph.text.empty()) return nullptr;
    const int size=std::max(16,MulDiv(18,dpi,96));
    BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth=size;info.bmiHeader.biHeight=-size;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
    void* bits=nullptr;
    HDC dc=CreateCompatibleDC(nullptr);
    if (!dc) return nullptr;
    HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,nullptr,0);
    HFONT font=CreateFontW(-MulDiv(15,dpi,96),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
        OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,ANTIALIASED_QUALITY,DEFAULT_PITCH,glyph.family.c_str());
    if (!bitmap || !font) {
        if (bitmap) DeleteObject(bitmap);
        if (font) DeleteObject(font);
        DeleteDC(dc);return nullptr;
    }
    auto oldBitmap=SelectObject(dc,bitmap),oldFont=SelectObject(dc,font);
    RECT rect{0,0,size,size};
    PatBlt(dc,0,0,size,size,BLACKNESS);
    SetBkMode(dc,TRANSPARENT);SetTextColor(dc,RGB(255,255,255));
    DrawTextW(dc,glyph.text.c_str(),glyph.text.size(),&rect,DT_CENTER|DT_VCENTER|DT_SINGLELINE|DT_NOPREFIX);
    GdiFlush();
    const COLORREF color=GetSysColor(COLOR_MENUTEXT);
    auto pixels=static_cast<uint32_t*>(bits);
    for (int i=0;i<size*size;++i) {
        const unsigned alpha=pixels[i]&255;
        pixels[i]=(alpha<<24)|((GetRValue(color)*alpha/255)<<16)|((GetGValue(color)*alpha/255)<<8)|(GetBValue(color)*alpha/255);
    }
    SelectObject(dc,oldFont);SelectObject(dc,oldBitmap);DeleteObject(font);DeleteDC(dc);
    return bitmap;
}

static bool BF_AddFooterItem(BF_FooterMenu& menu,HMENU parent,const Controls::MenuFlyoutItemBase& item,UINT dpi) {
    if (!item) return false;
    if (item.Visibility()!=Visibility::Visible) return true;
    if (item.try_as<Controls::MenuFlyoutSeparator>()) return AppendMenuW(parent,MF_SEPARATOR,0,nullptr)!=FALSE;
    auto action=item.try_as<Controls::MenuFlyoutItem>();
    auto sub=item.try_as<Controls::MenuFlyoutSubItem>();
    if (!action && !sub) return false;
    std::wstring label(action ? action.Text() : sub.Text());
    if (label.empty()) label=winrt::Windows::UI::Xaml::Automation::AutomationProperties::GetName(item);
    if (label.empty()) return false;
    // The XAML labels are literal. Preserve ampersands when handing them to USER menus.
    for (size_t i=0;(i=label.find(L'&',i))!=std::wstring::npos;i+=2) label.insert(i,1,L'&');
    MENUITEMINFOW entry{sizeof(entry)};
    entry.fMask=MIIM_FTYPE|MIIM_STATE|MIIM_STRING;
    entry.fState=item.IsEnabled() ? MFS_ENABLED : MFS_DISABLED;
    entry.dwTypeData=label.data();
    if (action) {
        auto peer=BF_FooterPeers::FrameworkElementAutomationPeer::CreatePeerForElement(action);
        BF_FooterCommand command;command.source=action;
        if (auto toggle=action.try_as<Controls::ToggleMenuFlyoutItem>()) {
            if (toggle.IsChecked()) entry.fState|=MFS_CHECKED;
            if (peer) command.toggle=peer.GetPattern(BF_FooterPeers::PatternInterface::Toggle).try_as<BF_FooterProviders::IToggleProvider>();
        } else if (peer) {
            command.invoke=peer.GetPattern(BF_FooterPeers::PatternInterface::Invoke).try_as<BF_FooterProviders::IInvokeProvider>();
        }
        if (item.IsEnabled() && !command.invoke && !command.toggle && !action.Command()) return false;
        menu.commands.push_back(std::move(command));
        entry.fMask|=MIIM_ID;entry.wID=static_cast<UINT>(menu.commands.size());
    } else {
        entry.fMask|=MIIM_SUBMENU;entry.hSubMenu=CreatePopupMenu();
        if (!entry.hSubMenu) return false;
    }
    if (!InsertMenuItemW(parent,GetMenuItemCount(parent),TRUE,&entry)) {
        if (entry.hSubMenu) DestroyMenu(entry.hSubMenu);
        return false;
    }
    auto glyph=BF_ReadFooterGlyph(action ? action.Icon() : sub.Icon());
    if (glyph.text.empty()) glyph=BF_ReadFooterGlyph(item);
    if (glyph.text.empty()) glyph={BF_FooterPresentationFor(label).glyph,L"Segoe Fluent Icons"};
    if (auto icon=BF_FooterBitmap(glyph,dpi)) {
        menu.icons.push_back(icon);
        MENUITEMINFOW art{sizeof(art)};art.fMask=MIIM_BITMAP;art.hbmpItem=icon;
        SetMenuItemInfoW(parent,GetMenuItemCount(parent)-1,TRUE,&art);
    }
    if (sub) for (const auto& child:sub.Items()) if (!BF_AddFooterItem(menu,entry.hSubMenu,child,dpi)) return false;
    return true;
}

static bool BF_FooterVisibleRow(HMENU menu,int position,RECT& rect) {
    if (!GetMenuItemRect(nullptr,menu,position,&rect) || IsRectEmpty(&rect)) return false;
    MONITORINFO display{sizeof(display)};
    if (!GetMonitorInfoW(MonitorFromRect(&rect,MONITOR_DEFAULTTONULL),&display) ||
        !BF_ContainsPanel(display.rcWork,rect)) return false;
    for (auto fraction:{1,2,3}) {
        POINT point{rect.left+(rect.right-rect.left)*fraction/4,(rect.top+rect.bottom)/2};
        DWORD pid=0;wchar_t name[20]{};
        auto window=WindowFromPoint(point);
        GetWindowThreadProcessId(window,&pid);GetClassNameW(window,name,std::size(name));
        if (pid!=GetCurrentProcessId() || std::wstring_view(name)!=L"#32768" ||
            MenuItemFromPoint(nullptr,menu,point)!=position) return false;
    }
    return true;
}

static void CALLBACK BF_RecordFooterMenu(HWND,UINT,UINT_PTR timer,DWORD) {
    if (!bf_activeFooter || timer!=bf_activeFooter->measureTimer) return;
    KillTimer(nullptr,std::exchange(bf_activeFooter->measureTimer,0));
    if (!bf_traceMenuInput) return;
    auto handle=bf_activeFooter->handle;
    unsigned rows=0,hits=0;
    bf_footerFirstBounds=0;bf_footerLastBounds=0;
    for (int i=0,n=GetMenuItemCount(handle);i<n;++i) {
        MENUITEMINFOW item{sizeof(item)};item.fMask=MIIM_FTYPE;
        if (!GetMenuItemInfoW(handle,i,TRUE,&item) || (item.fType&MFT_SEPARATOR)) continue;
        RECT rect{};
        if (BF_FooterVisibleRow(handle,i,rect)) ++hits;
        if (!rows++) bf_footerFirstBounds=BF_EncodePanelRect(rect);
        bf_footerLastBounds=BF_EncodePanelRect(rect);
    }
    bf_footerRows=rows;bf_footerHits=hits;
    if (bf_status_event) SetEvent(bf_status_event);
}

using BF_SettingsLauncher = bool (*)(HWND,PCWSTR);
static bool BF_OpenFooterSettings(HWND owner,PCWSTR uri) {
    return reinterpret_cast<INT_PTR>(ShellExecuteW(owner,L"open",uri,nullptr,nullptr,SW_SHOWNORMAL))>32;
}

static void BF_InvokeFooterCommand(const BF_FooterCommand& command,HWND owner,BF_SettingsLauncher launch) {
    auto source=command.source;
    if (!source || !source.IsEnabled() || source.Visibility()!=Visibility::Visible) return;
    if (const auto uri=BF_FooterPresentationFor(source.Text()).settings;uri && launch(owner,uri)) {
        if (bf_traceMenuInput) {++bf_footerSettings;if (bf_status_event) SetEvent(bf_status_event);}
        return;
    }
    // Use the actual native row, with its original command, policy checks,
    // active account, modifiers, and any follow-up confirmation flyout.
    if (command.toggle) command.toggle.Toggle();
    else if (command.invoke) command.invoke.Invoke();
    else if (auto action=source.Command()) {
        auto parameter=source.CommandParameter();
        if (action.CanExecute(parameter)) action.Execute(parameter);
    }
}

// TransformToVisual / UIA can include the popup origin twice on some Start
// hosts. A pointer inside the footer button provides an independent screen anchor.
static std::optional<RECT> BF_PointerAnchor(const BF_FooterCommandButton& button,const Input::PointerRoutedEventArgs& args) {
    const auto point=args.GetCurrentPoint(button).Position();
    const auto root=button.XamlRoot();
    POINT screen{};
    if (!root || !GetCursorPos(&screen)) return {};
    const auto width=button.ActualWidth(),height=button.ActualHeight(),scale=root.RasterizationScale();
    if (width<1 || height<1 || point.X<0 || point.Y<0 || point.X>width || point.Y>height) return {};
    const LONG left=screen.x-std::lround(point.X*scale),top=screen.y-std::lround(point.Y*scale);
    return RECT{left,top,left+static_cast<LONG>(std::lround(width*scale)),top+static_cast<LONG>(std::lround(height*scale))};
}

static bool BF_ReachableXamlFooter(const Controls::MenuFlyoutPresenter& presenter,const RECT& anchor) {
    // Verify the whole original menu, especially its last item, after the
    // opening animation. A matching HWND alone does not identify a row.
    auto face=BF_PanelPeer(presenter).GetBoundingRectangle();
    const auto root=presenter.XamlRoot();
    const auto scale=root.RasterizationScale();
    const auto layoutWindow=BF_LayoutWindow();
    double gap=std::max({0.,double(anchor.top-face.Y-face.Height),double(face.Y-anchor.bottom)});
    if (face.Width<1 || face.Height<1 || gap>16*scale || face.X>anchor.right+8*scale ||
        face.X+face.Width<anchor.left-8*scale) return false;
    unsigned rows=0;
    for (const auto& value:presenter.Items()) {
        auto item=value.try_as<Controls::MenuFlyoutItemBase>();
        if (!item || item.Visibility()!=Visibility::Visible || item.try_as<Controls::MenuFlyoutSeparator>()) continue;
        auto peer=BF_FooterPeers::FrameworkElementAutomationPeer::CreatePeerForElement(item);
        if (!peer) return false;
        auto bounds=peer.GetBoundingRectangle();
        if (bounds.Width<1 || bounds.Height<1 || bounds.Y<face.Y-1 || bounds.Y+bounds.Height>face.Y+face.Height+1) return false;
        POINT center{LONG(bounds.X+bounds.Width/2),LONG(bounds.Y+bounds.Height/2)};
        DWORD pid=0;wchar_t name[32]{};
        auto hit=WindowFromPoint(center);
        GetWindowThreadProcessId(hit,&pid);GetClassNameW(hit,name,std::size(name));
        if (pid!=GetCurrentProcessId()) return false;
        if (std::wstring_view(name)==L"Xaml_WindowedPopupClass") {
            RECT popup{};
            if (!GetWindowRect(hit,&popup) || bounds.X<popup.left-1 || bounds.X+bounds.Width>popup.right+1 ||
                bounds.Y<popup.top-1 || bounds.Y+bounds.Height>popup.bottom+1) return false;
        } else {
            if (!layoutWindow || GetAncestor(hit,GA_ROOT)!=GetAncestor(layoutWindow,GA_ROOT) ||
                !ScreenToClient(layoutWindow,&center)) return false;
            wf::Point position{float(center.x/scale),float(center.y/scale)};
            auto top=Media::VisualTreeHelper::FindElementsInHostCoordinates(position,root.Content(),false).First();
            DependencyObject leaf=top.HasCurrent() ? top.Current() : nullptr;
            while (leaf && leaf!=item) leaf=Media::VisualTreeHelper::GetParent(leaf);
            if (!leaf) return false;
        }
        ++rows;
    }
    return rows>0;
}

static void BF_StopFooterRequest() {
    ++bf_footerRequest;
    bf_openingFooter={};
    if (auto timer=std::exchange(bf_footerTimer,nullptr)) timer.Stop();
}

static void BF_TrackFooter(BF_FooterMenu& menu,const RECT& anchor,bool rtl,BF_SettingsLauncher launch) {
    if (bf_activeFooter) return;
    struct ResetActive {~ResetActive() {bf_activeFooter=nullptr;}} reset;
    bf_activeFooter=&menu;
    if (bf_traceMenuInput) {
        ++bf_footerTracked;bf_footerRows=0;bf_footerHits=0;
        menu.measureTimer=SetTimer(nullptr,0,75,BF_RecordFooterMenu);
        if (bf_status_event) SetEvent(bf_status_event);
    }
    TPMPARAMS placement{sizeof(placement)};placement.rcExclude=anchor;
    const UINT flags=TPM_RETURNCMD|TPM_NONOTIFY|TPM_BOTTOMALIGN|TPM_WORKAREA|TPM_NOANIMATION|
        (rtl ? TPM_RIGHTALIGN|TPM_LAYOUTRTL : TPM_LEFTALIGN);
    SetLastError(ERROR_SUCCESS);
    const UINT selected=TrackPopupMenuEx(menu.handle,flags,rtl ? anchor.right : anchor.left,anchor.top,menu.owner,&placement);
    auto error=selected ? ERROR_SUCCESS : GetLastError();
    if (!selected && error) {bf_footerError=error;return;}
    if (menu.cancelled || !selected || selected>menu.commands.size()) return;
    if (bf_traceMenuInput) {++bf_footerSelected;if (bf_status_event) SetEvent(bf_status_event);}
    BF_InvokeFooterCommand(menu.commands[selected-1],menu.owner,launch);
}

static bool BF_TryFooterMenu(const BF_FooterCommandButton& button,HWND window,const RECT& anchor,bool settled,
                             BF_SettingsLauncher launch=BF_OpenFooterSettings) {
    auto root=button.XamlRoot();
    if (!root || !button.IsLoaded() || !window) return true;
    for (const auto& original:Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(root)) {
        auto content=original.Child().try_as<FrameworkElement>();
        if (!original.IsOpen() || !content) continue;
        auto presenter=BF_FooterPresenter(content);
        if (!presenter || presenter.ActualHeight()<1 || !presenter.Items().Size()) continue;
        auto placement=original.try_as<Controls::Primitives::IPopup4>();
        if (auto target=placement ? placement.PlacementTarget() : nullptr;target && target!=button) {
            bool related=false;
            for (DependencyObject node=button;node;node=Media::VisualTreeHelper::GetParent(node))
                if (node==target) {related=true;break;}
            if (!related) continue;
        }
        if (BF_ReachableXamlFooter(presenter,anchor)) return settled;
        auto menu=std::make_shared<BF_FooterMenu>();
        if (!menu->handle) return true;
        menu->anchor=winrt::make_weak(button);menu->owner=GetAncestor(window,GA_ROOT);
        if (!menu->owner) return true;
        const UINT dpi=static_cast<UINT>(std::lround(root.RasterizationScale()*96));
        for (const auto& item:presenter.Items()) if (!BF_AddFooterItem(*menu,menu->handle,item.try_as<Controls::MenuFlyoutItemBase>(),dpi)) return true;
        if (menu->commands.empty()) return true;
        BF_ColorFooterMenu(*menu);
        if (bf_traceMenuInput && !original.IsConstrainedToRootBounds()) ++bf_footerWindowed;
        BF_StopFooterRequest();
        // Complete the XAML popup lifetime before starting USER's modal menu
        // loop. Opacity alone leaves the compositor's last glass frame visible.
        if (auto owner=button.try_as<Controls::Button>()) {
            auto flyout=owner.Flyout().try_as<Controls::MenuFlyout>();
            uint32_t itemIndex=0;
            if (flyout && flyout.Items().Size() && presenter.Items().IndexOf(flyout.Items().GetAt(0),itemIndex)) flyout.Hide();
        }
        if (original.IsOpen()) original.IsOpen(false);
        const auto generation=bf_footerRequest;
        const auto rtl=button.FlowDirection()==FlowDirection::RightToLeft;
        button.Dispatcher().RunAsync(winrt::Windows::UI::Core::CoreDispatcherPriority::Low,
            [menu,anchor,rtl,original,generation,launch] {
                auto live=menu->anchor.get();
                if (generation!=bf_footerRequest || !live || !live.IsLoaded() || original.IsOpen() ||
                    !IsWindowVisible(menu->owner) || !IsWindow(menu->owner)) return;
                try {BF_TrackFooter(*menu,anchor,rtl,launch);}
                catch (const winrt::hresult_error& e) {bf_footerError=static_cast<unsigned>(e.code().value);}
            });
        return true;
    }
    return false;
}

static void BF_QueueFooterPresentation(const BF_FooterCommandButton& button,std::optional<RECT> pointer={}) {
    if (bf_activeFooter || (bf_footerTimer && bf_openingFooter.get()==button)) return;
    if (!pointer && button.FocusState()==FocusState::Keyboard) return;
    HWND window=BF_LayoutWindow();
    auto anchor=pointer ? pointer : BF_PanelScreenRect(button,window);
    if (!anchor || !window) return;
    BF_StopFooterRequest();
    bf_openingFooter=winrt::make_weak(button);
    const auto generation=bf_footerRequest;
    const auto started=GetTickCount64();
    auto present=[generation,started,anchor=*anchor,window] {
        if (generation!=bf_footerRequest) return;
        try {
            auto live=bf_openingFooter.get();
            const auto elapsed=GetTickCount64()-started;
            if (!live || elapsed>750 || BF_TryFooterMenu(live,window,anchor,elapsed>=150))
                if (generation==bf_footerRequest) BF_StopFooterRequest();
        } catch (const winrt::hresult_error& error) {
            BF_StopFooterRequest();bf_footerError=static_cast<unsigned>(error.code().value);
            Wh_Log(L"Error %08X: Start footer menu",error.code());
        }
    };
    bf_footerTimer=DispatcherTimer();
    bf_footerTimer.Interval(std::chrono::milliseconds(35));
    bf_footerTimer.Tick([present](auto&&,auto&&){present();});
    bf_footerTimer.Start();
    button.Dispatcher().RunAsync(winrt::Windows::UI::Core::CoreDispatcherPriority::Normal,present);
}

struct BF_FooterAnchor {
    winrt::weak_ref<BF_FooterCommandButton> button;
    std::optional<RECT> pointer;
    BF_FooterCommandButton::Click_revoker click;
    wf::IInspectable pressed{nullptr},released{nullptr};
    ~BF_FooterAnchor() {
        if (auto live=button.get()) try {
            if (pressed) live.RemoveHandler(UIElement::PointerPressedEvent(),pressed);
            if (released) live.RemoveHandler(UIElement::PointerReleasedEvent(),released);
        } catch (const winrt::hresult_error&) {}
    }
    static std::shared_ptr<BF_FooterAnchor> observe(const BF_FooterCommandButton& live) {
        auto state=std::make_shared<BF_FooterAnchor>();
        state->button=winrt::make_weak(live);
        auto weak=std::weak_ptr<BF_FooterAnchor>(state);
        state->pressed=winrt::box_value(Input::PointerEventHandler([weak](auto&&,const Input::PointerRoutedEventArgs& args) {
            if (auto s=weak.lock()) if (auto b=s->button.get()) {
                s->pointer.reset();
                if (args.GetCurrentPoint(b).Properties().IsLeftButtonPressed()) s->pointer=BF_PointerAnchor(b,args);
            }
        }));
        state->released=winrt::box_value(Input::PointerEventHandler([weak](auto&&,const Input::PointerRoutedEventArgs& args) {
            if (auto s=weak.lock()) if (auto b=s->button.get()) {
                if (args.GetCurrentPoint(b).Properties().PointerUpdateKind()!=winrt::Windows::UI::Input::PointerUpdateKind::LeftButtonReleased) return;
                auto anchor=BF_PointerAnchor(b,args);
                s->pointer.reset();
                if (anchor) BF_QueueFooterPresentation(b,anchor);
            }
        }));
        state->click=live.Click(winrt::auto_revoke,[weak](auto&&,auto&&) {
            if (auto s=weak.lock()) if (auto b=s->button.get()) BF_QueueFooterPresentation(b,std::exchange(s->pointer,{}));
        });
        live.AddHandler(UIElement::PointerPressedEvent(),state->pressed,true);
        live.AddHandler(UIElement::PointerReleasedEvent(),state->released,true);
        if (bf_traceMenuInput) {++bf_footerAttached;if (bf_status_event) SetEvent(bf_status_event);}
        return state;
    }
};
