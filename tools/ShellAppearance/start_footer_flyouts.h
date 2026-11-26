#pragma once
#include <dwmapi.h>
#include <winrt/Windows.UI.Input.h>
#include <winrt/Windows.UI.Composition.h>
#include <winrt/Windows.UI.Xaml.Hosting.h>
#include "start_footer_paint.h"

// Start uses the original XAML menu when its visible rows receive input.
using BF_FooterCommandButton = Controls::Primitives::ButtonBase;
using BF_FooterPopup = Controls::Primitives::Popup;
namespace BF_FooterPeers = winrt::Windows::UI::Xaml::Automation::Peers;
namespace BF_FooterProviders = winrt::Windows::UI::Xaml::Automation::Provider;

struct BF_FooterCommand {
    Controls::MenuFlyoutItem source{nullptr};
    BF_FooterProviders::IInvokeProvider invoke{nullptr};
    BF_FooterProviders::IToggleProvider toggle{nullptr};
};

struct BF_FooterMenu : BF_NativePopup {
    std::vector<BF_FooterCommand> commands;
    winrt::weak_ref<FrameworkElement> anchor;
    UINT_PTR measureTimer=0;
    bool cancelled=false;
    ~BF_FooterMenu() {
        if (measureTimer) KillTimer(nullptr,measureTimer);
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
    const COLORREF surface=RGB((hex>>16)&255,(hex>>8)&255,hex&255);
    const auto live=bf_startInkTone.load();
    const bool white=live>=0 ? live!=0 : BF_Setting(L"bigfish_theme")==L"Dark";
    menu.ink=white ? RGB(255,255,255) : RGB(0,0,0);
    menu.fill=BF_FooterBlend(surface,white ? RGB(28,30,33) : RGB(250,251,252),48);
    const auto tint=BF_Setting(L"bigfish_footer_tint");
    if (tint.size()==9 && tint.front()==L'#') {
        const auto argb=wcstoul(tint.c_str()+1,&end,16);
        if (end==tint.c_str()+tint.size()) {
            menu.tint=RGB((argb>>16)&255,(argb>>8)&255,argb&255);
            menu.tintOpacity=static_cast<BYTE>(argb>>24);
            menu.blur=wcstol(BF_Setting(L"bigfish_footer_blur").c_str(),nullptr,10);
            if (menu.tintOpacity==255) menu.fill=menu.tint;
        }
    }
    menu.background=CreateSolidBrush(menu.fill);
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

static bool BF_FooterPopupForButton(const BF_FooterPopup& popup,const BF_FooterCommandButton& button) {
    if (!popup.IsOpen()) return false;
    auto placement=popup.try_as<Controls::Primitives::IPopup4>();
    auto target=placement ? placement.PlacementTarget() : nullptr;
    if (!target) return true;
    for (DependencyObject node=button;node;node=Media::VisualTreeHelper::GetParent(node))
        if (node==target) return true;
    return false;
}

// Leave the XAML items loaded for measurement and command discovery. Only
// withhold their visual while deciding which menu can receive this mouse click.
using BF_FooterVisual=winrt::Windows::UI::Composition::Visual;
struct BF_FooterPreview {
    winrt::weak_ref<UIElement> element;
    BF_FooterVisual visual;
    wf::IInspectable localOpacity;
    double opacity;
    bool visible;
    BF_FooterPreview(const UIElement& target,const BF_FooterVisual& value):element(winrt::make_weak(target)),
        visual(value),localOpacity(target.ReadLocalValue(UIElement::OpacityProperty())),
        opacity(target.Opacity()),visible(value.IsVisible()) {}
    void mask() {
        if (auto target=element.get();target && target.Opacity()!=0) target.Opacity(0);
        if (visual.IsVisible()) visual.IsVisible(false);
    }
    ~BF_FooterPreview() {
        try {
            if (auto target=element.get();target && target.Opacity()==0) {
                if (localOpacity==DependencyProperty::UnsetValue()) target.ClearValue(UIElement::OpacityProperty());
                else {
                    try {target.SetValue(UIElement::OpacityProperty(),localOpacity);}
                    catch (const winrt::hresult_error&) {target.Opacity(opacity);}
                }
            }
            visual.IsVisible(visible);
        } catch (const winrt::hresult_error&) {}
    }
};
static void BF_MaskFlyout(const UIElement& content,std::shared_ptr<BF_FooterPreview>& preview) {
    auto visual=winrt::Windows::UI::Xaml::Hosting::ElementCompositionPreview::GetElementVisual(content);
    if (!visual) return;
    if (!preview || preview->visual!=visual) preview=std::make_shared<BF_FooterPreview>(content,visual);
    preview->mask();
}
static thread_local std::shared_ptr<BF_FooterPreview> bf_footerPreview;
static thread_local winrt::event_token bf_footerRendering{};

static void BF_MaskFooterPreview(const BF_FooterCommandButton& button) {
    if (!button || !button.XamlRoot()) return;
    for (const auto& popup:Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(button.XamlRoot())) {
        if (!BF_FooterPopupForButton(popup,button)) continue;
        auto content=popup.Child();
        if (!content || !BF_FooterPresenter(content)) continue;
        BF_MaskFlyout(content,bf_footerPreview);
        return;
    }
}

static void BF_ArmFooterPreview(const BF_FooterCommandButton& button) {
    bf_openingFooter=winrt::make_weak(button);
    try {
        bf_footerRendering=Media::CompositionTarget::Rendering([](auto&&,auto&&) {
            try {BF_MaskFooterPreview(bf_openingFooter.get());} catch (const winrt::hresult_error&) {}
        });
        BF_MaskFooterPreview(button);
    } catch (const winrt::hresult_error&) {}
}

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
    if (item.try_as<Controls::MenuFlyoutSeparator>()) {
        const auto position=GetMenuItemCount(parent);
        if (position<0 || !AppendMenuW(parent,MF_SEPARATOR,0,nullptr)) return false;
        menu.rows.push_back({parent,static_cast<UINT>(position),{}, {},true});
        return true;
    }
    auto action=item.try_as<Controls::MenuFlyoutItem>();
    auto sub=item.try_as<Controls::MenuFlyoutSubItem>();
    if (!action && !sub) return false;
    // Some Shell extensions populate a submenu only when it opens. Leave the
    // original flyout in charge instead of presenting an empty replacement.
    if (sub && sub.IsEnabled() && !sub.Items().Size()) return false;
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
    menu.rows.push_back({parent,static_cast<UINT>(GetMenuItemCount(parent)-1),std::wstring(action ? action.Text() : sub.Text()),glyph});
    if (menu.rows.back().label.empty()) menu.rows.back().label=winrt::Windows::UI::Xaml::Automation::AutomationProperties::GetName(item);
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

static std::optional<RECT> BF_StartFlyoutBounds(const XamlRoot& root) {
    auto panel=bf_startFrame ? bf_startFrame->panel.get() : nullptr;
    if (!panel || !root || panel.XamlRoot()!=root) return {};
    return BF_PanelScreenRect(panel,bf_startFrame->window);
}

static bool BF_ReachableMenuRows(const Controls::MenuFlyoutPresenter& presenter,const wf::Rect& face) {
    const auto root=presenter.XamlRoot();
    if (!root || !presenter.IsHitTestVisible() || face.Width<1 || face.Height<1) return false;
    const auto scale=root.RasterizationScale();
    // Automation reports clipped extents on some builds. The part drawn beyond
    // those extents still needs a menu window of its own to receive input.
    if (presenter.ActualWidth()*scale>face.Width+1.5 || presenter.ActualHeight()*scale>face.Height+1.5) return false;
    const auto layoutWindow=bf_startFrame && bf_startFrame->window ? bf_startFrame->window : BF_LayoutWindow();
    if (const auto bounds=BF_StartFlyoutBounds(root)) {
        const RECT surface{LONG(std::floor(face.X)),LONG(std::floor(face.Y)),
            LONG(std::ceil(face.X+face.Width)),LONG(std::ceil(face.Y+face.Height))};
        // The shell can dismiss a menu outside its visible panel even if
        // its larger compositor window reports an XAML hit there.
        if (!BF_ContainsPanel(*bounds,surface)) return false;
    }
    unsigned rows=0;
    for (const auto& value:presenter.Items()) {
        auto item=value.try_as<Controls::MenuFlyoutItemBase>();
        if (!item || item.Visibility()!=Visibility::Visible || item.try_as<Controls::MenuFlyoutSeparator>()) continue;
        if (!item.IsHitTestVisible()) return false;
        auto peer=BF_FooterPeers::FrameworkElementAutomationPeer::CreatePeerForElement(item);
        if (!peer) return false;
        auto bounds=peer.GetBoundingRectangle();
        if (bounds.Width<1 || bounds.Height<1 || bounds.X<face.X-1 || bounds.X+bounds.Width>face.X+face.Width+1 ||
            bounds.Y<face.Y-1 || bounds.Y+bounds.Height>face.Y+face.Height+1) return false;
        const double half=bounds.Width*.5, edge=std::min(half,4*scale);
        for (double offset:{edge,half,bounds.Width-edge}) {
            POINT point{LONG(bounds.X+offset),LONG(bounds.Y+bounds.Height/2)};
            DWORD pid=0;wchar_t name[32]{};
            auto hit=WindowFromPoint(point);
            GetWindowThreadProcessId(hit,&pid);GetClassNameW(hit,name,std::size(name));
            if (pid!=GetCurrentProcessId()) return false;
            if (std::wstring_view(name)==L"Xaml_WindowedPopupClass") {
                RECT popup{};
                if (!GetWindowRect(hit,&popup) || bounds.X<popup.left-1 || bounds.X+bounds.Width>popup.right+1 ||
                    bounds.Y<popup.top-1 || bounds.Y+bounds.Height>popup.bottom+1) return false;
                continue;
            }
            if (!layoutWindow || GetAncestor(hit,GA_ROOT)!=GetAncestor(layoutWindow,GA_ROOT) ||
                !ScreenToClient(layoutWindow,&point)) return false;
            wf::Point position{float(point.x/scale),float(point.y/scale)};
            auto top=Media::VisualTreeHelper::FindElementsInHostCoordinates(position,root.Content(),false).First();
            DependencyObject leaf=top.HasCurrent() ? top.Current() : nullptr;
            while (leaf && leaf!=item) leaf=Media::VisualTreeHelper::GetParent(leaf);
            if (!leaf) return false;
        }
        ++rows;
    }
    return rows>0;
}

static bool BF_ReachableXamlFooter(const Controls::MenuFlyoutPresenter& presenter,const RECT& anchor) {
    const auto face=BF_PanelPeer(presenter).GetBoundingRectangle();
    const auto scale=presenter.XamlRoot().RasterizationScale();
    const double gap=std::max({0.,double(anchor.top-face.Y-face.Height),double(face.Y-anchor.bottom)});
    return gap<=16*scale && face.X<=anchor.right+8*scale && face.X+face.Width>=anchor.left-8*scale &&
        BF_ReachableMenuRows(presenter,face);
}

static std::shared_ptr<BF_FooterMenu> BF_CopyStartMenu(const Controls::MenuFlyoutPresenter& presenter,
                                                     const FrameworkElement& anchor,HWND window) {
    auto menu=std::make_shared<BF_FooterMenu>();
    menu->anchor=winrt::make_weak(anchor);
    menu->owner=GetAncestor(window,GA_ROOT);
    if (!menu->handle || !menu->owner) return {};
    menu->dpi=static_cast<UINT>(std::lround(anchor.XamlRoot().RasterizationScale()*96));
    for (const auto& item:presenter.Items())
        if (!BF_AddFooterItem(*menu,menu->handle,item.try_as<Controls::MenuFlyoutItemBase>(),menu->dpi)) return {};
    if (menu->commands.empty()) return {};
    BF_ColorFooterMenu(*menu);
    return menu;
}

static void BF_StopFooterRequest() {
    ++bf_footerRequest;
    bf_openingFooter={};
    if (auto timer=std::exchange(bf_footerTimer,nullptr)) timer.Stop();
    if (bf_footerRendering.value) {
        const auto token=std::exchange(bf_footerRendering,winrt::event_token{});
        try {Media::CompositionTarget::Rendering(token);} catch (const winrt::hresult_error&) {}
    }
    bf_footerPreview.reset();
}

static void BF_TrackFooter(BF_FooterMenu& menu,const RECT& anchor,bool rtl,BF_SettingsLauncher launch,bool atPointer=false) {
    if (bf_activeFooter) return;
    struct ResetActive {~ResetActive() {bf_activeFooter=nullptr;}} reset;
    bf_activeFooter=&menu;
    BF_CapturePopupBackdrop(menu,{rtl ? anchor.right : anchor.left,anchor.top});
    BF_FooterPainting painting(menu);
    if (bf_traceMenuInput) {
        ++bf_footerTracked;bf_footerRows=0;bf_footerHits=0;
        menu.measureTimer=SetTimer(nullptr,0,75,BF_RecordFooterMenu);
        if (bf_status_event) SetEvent(bf_status_event);
    }
    TPMPARAMS placement{sizeof(placement)};placement.rcExclude=anchor;
    const UINT align=atPointer ? TPM_TOPALIGN|TPM_RIGHTBUTTON : TPM_BOTTOMALIGN;
    const UINT flags=TPM_RETURNCMD|TPM_NONOTIFY|align|TPM_WORKAREA|TPM_NOANIMATION|
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
        if (!content || !BF_FooterPopupForButton(original,button)) continue;
        auto presenter=BF_FooterPresenter(content);
        if (!presenter || presenter.ActualHeight()<1 || !presenter.Items().Size()) continue;
        if (BF_ReachableXamlFooter(presenter,anchor)) return settled;
        auto menu=BF_CopyStartMenu(presenter,button,window);
        if (!menu) return true;
        if (bf_traceMenuInput && !original.IsConstrainedToRootBounds()) ++bf_footerWindowed;
        auto preview=std::move(bf_footerPreview);
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
        button.Dispatcher().RunAsync(winrt::Windows::UI::Core::CoreDispatcherPriority::Normal,
            [menu,anchor,rtl,original,generation,launch,preview] {
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
    if (bf_openingFooter.get()!=button) {
        BF_StopFooterRequest();
        BF_ArmFooterPreview(button);
    }
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
    wf::IInspectable pressed{nullptr},released{nullptr},cancelled{nullptr};
    ~BF_FooterAnchor() {
        if (auto live=button.get()) try {
            if (pressed) live.RemoveHandler(UIElement::PointerPressedEvent(),pressed);
            if (released) live.RemoveHandler(UIElement::PointerReleasedEvent(),released);
            if (cancelled) {
                live.RemoveHandler(UIElement::PointerCanceledEvent(),cancelled);
                live.RemoveHandler(UIElement::PointerCaptureLostEvent(),cancelled);
            }
        } catch (const winrt::hresult_error&) {}
    }
    static std::shared_ptr<BF_FooterAnchor> observe(const BF_FooterCommandButton& live) {
        auto state=std::make_shared<BF_FooterAnchor>();
        state->button=winrt::make_weak(live);
        auto weak=std::weak_ptr<BF_FooterAnchor>(state);
        state->pressed=winrt::box_value(Input::PointerEventHandler([weak](auto&&,const Input::PointerRoutedEventArgs& args) {
            if (auto s=weak.lock()) if (auto b=s->button.get()) {
                s->pointer.reset();
                if (args.GetCurrentPoint(b).Properties().IsLeftButtonPressed()) {
                    s->pointer=BF_PointerAnchor(b,args);
                    if (s->pointer && !bf_activeFooter && !bf_footerTimer && bf_openingFooter.get()!=b) {
                        BF_StopFooterRequest();
                        BF_ArmFooterPreview(b);
                    }
                }
            }
        }));
        state->released=winrt::box_value(Input::PointerEventHandler([weak](auto&&,const Input::PointerRoutedEventArgs& args) {
            if (auto s=weak.lock()) if (auto b=s->button.get()) {
                if (args.GetCurrentPoint(b).Properties().PointerUpdateKind()!=winrt::Windows::UI::Input::PointerUpdateKind::LeftButtonReleased) return;
                auto anchor=BF_PointerAnchor(b,args);
                s->pointer.reset();
                if (anchor) BF_QueueFooterPresentation(b,anchor);
                else if (!bf_footerTimer && bf_openingFooter.get()==b) BF_StopFooterRequest();
            }
        }));
        state->cancelled=winrt::box_value(Input::PointerEventHandler([weak](auto&&,auto&&) {
            if (auto s=weak.lock()) if (auto b=s->button.get()) {
                if (!bf_footerTimer && bf_openingFooter.get()==b) BF_StopFooterRequest();
            }
        }));
        state->click=live.Click(winrt::auto_revoke,[weak](auto&&,auto&&) {
            if (auto s=weak.lock()) if (auto b=s->button.get()) BF_QueueFooterPresentation(b,std::exchange(s->pointer,{}));
        });
        live.AddHandler(UIElement::PointerPressedEvent(),state->pressed,true);
        live.AddHandler(UIElement::PointerReleasedEvent(),state->released,true);
        live.AddHandler(UIElement::PointerCanceledEvent(),state->cancelled,true);
        live.AddHandler(UIElement::PointerCaptureLostEvent(),state->cancelled,true);
        if (bf_traceMenuInput) {++bf_footerAttached;if (bf_status_event) SetEvent(bf_status_event);}
        return state;
    }
};
