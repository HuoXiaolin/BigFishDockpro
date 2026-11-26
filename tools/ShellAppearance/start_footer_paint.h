#pragma once
#include <commctrl.h>
#include <dwmapi.h>
#include <algorithm>
#include <string>
#include <string_view>
#include <vector>

struct BF_FooterGlyph {winrt::hstring text, family;};
struct BF_FooterRow {
    HMENU parent;
    UINT position;
    std::wstring label;
    BF_FooterGlyph glyph;
    bool separator=false;
};

struct BF_NativePopup {
    HMENU handle=CreatePopupMenu();
    std::vector<HBITMAP> icons;
    HBRUSH background=nullptr;
    COLORREF fill=0,ink=0;
    COLORREF tint=0;
    BYTE tintOpacity=255;
    int blur=0;
    HBITMAP backdrop=nullptr;
    RECT backdropBounds{};
    SIZE backdropSize{};
    UINT dpi=96;
    HFONT font=nullptr;
    std::vector<BF_FooterRow> rows;
    HWND roundedWindow=nullptr;
    HMENU roundedMenu=nullptr;
    std::vector<HWND> framedWindows;
    HWND owner=nullptr;
    HMENU pendingFrame=nullptr;
    UINT_PTR frameTimer=0;
    ULONGLONG frameDeadline=0;
    BF_NativePopup()=default;
    BF_NativePopup(const BF_NativePopup&)=delete;
    BF_NativePopup& operator=(const BF_NativePopup&)=delete;
    ~BF_NativePopup() {
        if (handle) DestroyMenu(handle);
        if (background) DeleteObject(background);
        if (font) DeleteObject(font);
        if (backdrop) DeleteObject(backdrop);
        for (auto icon:icons) DeleteObject(icon);
    }
};

// USER still owns tracking, keyboard navigation, accessibility and dispatch.
// Only the pixels belonging to this temporary menu are drawn here.
static COLORREF BF_FooterBlend(COLORREF base,COLORREF ink,int percent) {
    auto channel=[percent](int b,int i){return (b*(100-percent)+i*percent+50)/100;};
    return RGB(channel(GetRValue(base),GetRValue(ink)),channel(GetGValue(base),GetGValue(ink)),channel(GetBValue(base),GetBValue(ink)));
}

static void BF_CapturePopupBackdrop(BF_NativePopup& menu,POINT anchor) {
    if (menu.tintOpacity==255) return;
    MONITORINFO monitor{sizeof(monitor)};
    if (!GetMonitorInfoW(MonitorFromPoint(anchor,MONITOR_DEFAULTTONEAREST),&monitor)) return;
    const bool hasSubmenu=std::any_of(menu.rows.begin(),menu.rows.end(),[&](const auto& row){return row.parent!=menu.handle;});
    const LONG wide=MulDiv(440,menu.dpi,96),tall=MulDiv(360,menu.dpi,96);
    // USER can flip the entire cascade above or to the left of its anchor.
    const RECT area=hasSubmenu ? monitor.rcMonitor : RECT{anchor.x-wide,anchor.y-tall,anchor.x+wide,anchor.y+tall};
    if (!IntersectRect(&menu.backdropBounds,&area,&monitor.rcMonitor)) return;
    const auto& rect=menu.backdropBounds;
    const auto width=rect.right-rect.left,height=rect.bottom-rect.top;
    const LONG step=std::max<LONG>(1+std::clamp(menu.blur,0,50)/3,(std::max(width,height)+2559)/2560);
    menu.backdropSize={std::max(1L,(width+step-1)/step),std::max(1L,(height+step-1)/step)};
    BITMAPINFO info{};
    info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth=menu.backdropSize.cx;
    info.bmiHeader.biHeight=-menu.backdropSize.cy;
    info.bmiHeader.biPlanes=1;
    info.bmiHeader.biBitCount=32;
    const HDC desktop=GetDC(nullptr);
    if (!desktop) return;
    const HDC image=CreateCompatibleDC(desktop);
    void* pixels=nullptr;
    const HBITMAP bitmap=image ? CreateDIBSection(image,&info,DIB_RGB_COLORS,&pixels,nullptr,0) : nullptr;
    if (bitmap) {
        const auto previous=SelectObject(image,bitmap);
        SetStretchBltMode(image,HALFTONE);
        SetBrushOrgEx(image,0,0,nullptr);
        if (StretchBlt(image,0,0,menu.backdropSize.cx,menu.backdropSize.cy,desktop,
                       rect.left,rect.top,width,height,SRCCOPY|CAPTUREBLT)) {
            GdiFlush();
            auto colors=static_cast<RGBQUAD*>(pixels);
            const unsigned alpha=menu.tintOpacity;
            const auto channel=[alpha](unsigned behind,unsigned tint) {
                return static_cast<BYTE>((behind*(255-alpha)+tint*alpha+127)/255);
            };
            for (LONG i=0;i<menu.backdropSize.cx*menu.backdropSize.cy;++i) {
                auto& color=colors[i];
                color.rgbRed=channel(color.rgbRed,GetRValue(menu.tint));
                color.rgbGreen=channel(color.rgbGreen,GetGValue(menu.tint));
                color.rgbBlue=channel(color.rgbBlue,GetBValue(menu.tint));
            }
            menu.backdrop=bitmap;
        }
        SelectObject(image,previous);
        if (!menu.backdrop) DeleteObject(bitmap);
    }
    if (image) DeleteDC(image);
    ReleaseDC(nullptr,desktop);
}

static void BF_DrawPopupBackdrop(const BF_NativePopup& menu,HDC dc,const RECT& region,POINT screen) {
    if (!menu.backdrop) return;
    const HDC image=CreateCompatibleDC(dc);
    if (!image) return;
    const auto previous=SelectObject(image,menu.backdrop);
    const int saved=SaveDC(dc);
    if (saved) {
        IntersectClipRect(dc,region.left,region.top,region.right,region.bottom);
        SetStretchBltMode(dc,HALFTONE);
        SetBrushOrgEx(dc,0,0,nullptr);
        const auto& bounds=menu.backdropBounds;
        StretchBlt(dc,bounds.left-screen.x,bounds.top-screen.y,bounds.right-bounds.left,bounds.bottom-bounds.top,
            image,0,0,menu.backdropSize.cx,menu.backdropSize.cy,SRCCOPY);
        RestoreDC(dc,saved);
    }
    SelectObject(image,previous);
    DeleteDC(image);
}

static bool BF_FillFooterFrame(HWND window,HDC dc,const BF_NativePopup& menu) {
    RECT frame{},client{};
    if (!dc || !GetWindowRect(window,&frame) || !GetClientRect(window,&client)) return false;
    MapWindowPoints(window,nullptr,reinterpret_cast<POINT*>(&client),2);
    OffsetRect(&client,-frame.left,-frame.top);
    const auto handle=reinterpret_cast<HMENU>(SendMessageW(window,MN_GETHMENU,0,0));
    if (handle && handle!=menu.handle) {
        // USER can paint an additional light line just inside the submenu's
        // client area. Continue the same surface across both sides of that seam.
        const int rim=MulDiv(2,menu.dpi,96);
        InflateRect(&client,-rim,-rim);
    }
    const RECT bounds{0,0,frame.right-frame.left,frame.bottom-frame.top};
    const int saved=SaveDC(dc);
    if (!saved) return false;
    ExcludeClipRect(dc,client.left,client.top,client.right,client.bottom);
    SetDCBrushColor(dc,menu.fill);
    const bool painted=FillRect(dc,&bounds,static_cast<HBRUSH>(GetStockObject(DC_BRUSH)))!=0;
    BF_DrawPopupBackdrop(menu,dc,bounds,{frame.left,frame.top});
    RestoreDC(dc,saved);
    return painted;
}

static void BF_PaintSubmenuClient(HWND window,HDC dc,BF_NativePopup& menu);

static LRESULT CALLBACK BF_PaintFooterFrame(HWND window,UINT msg,WPARAM wp,LPARAM lp,UINT_PTR id,DWORD_PTR context) {
    auto& menu=*reinterpret_cast<BF_NativePopup*>(context);
    if (msg==WM_NCPAINT) {
        if (HDC dc=GetWindowDC(window)) {
            const bool painted=BF_FillFooterFrame(window,dc,menu);
            ReleaseDC(window,dc);
            if (painted) return 0;
        }
    } else if (msg==WM_PAINT || msg==WM_PRINTCLIENT || msg==WM_PRINT) {
        const auto result=DefSubclassProc(window,msg,wp,lp);
        HDC dc=msg==WM_PAINT ? GetDC(window) : reinterpret_cast<HDC>(wp);
        if (dc && (msg!=WM_PRINT || (lp&PRF_CLIENT))) {
            const int saved=SaveDC(dc);
            if (saved) {
                if (msg==WM_PRINT && (lp&PRF_NONCLIENT)) {
                    RECT frame{};POINT client{};
                    if (GetWindowRect(window,&frame) && ClientToScreen(window,&client))
                        OffsetViewportOrgEx(dc,client.x-frame.left,client.y-frame.top,nullptr);
                }
                BF_PaintSubmenuClient(window,dc,menu);
                RestoreDC(dc,saved);
            }
        }
        if (msg==WM_PAINT) {
            if (dc) ReleaseDC(window,dc);
            if (HDC frame=GetWindowDC(window)) {
                BF_FillFooterFrame(window,frame,menu);
                ReleaseDC(window,frame);
            }
        }
        if (msg==WM_PRINT && (lp&PRF_NONCLIENT)) BF_FillFooterFrame(window,dc,menu);
        return result;
    } else if (msg==WM_NCDESTROY) {
        if (menu.roundedWindow==window) {menu.roundedWindow=nullptr;menu.roundedMenu=nullptr;}
        std::erase(menu.framedWindows,window);
        RemoveWindowSubclass(window,BF_PaintFooterFrame,id);
    }
    return DefSubclassProc(window,msg,wp,lp);
}

// Style the native popup before its first completed draw. DWM supplies
// antialiased outer corners, with the same window handling all menu input.
static bool BF_WindowOwnsMenu(HWND window,HMENU handle) {
    wchar_t name[16]{};
    if (!window || GetWindowThreadProcessId(window,nullptr)!=GetCurrentThreadId() ||
        !GetClassNameW(window,name,16) || std::wstring_view(name)!=L"#32768") return false;
    MENUBARINFO bar{sizeof(bar)};
    if (GetMenuBarInfo(window,OBJID_CLIENT,0,&bar) && bar.hMenu==handle) return true;
    return reinterpret_cast<HMENU>(SendMessageW(window,MN_GETHMENU,0,0))==handle;
}

static HWND BF_FindFooterWindow(HMENU handle,HDC dc=nullptr) {
    const HWND direct=dc ? WindowFromDC(dc) : nullptr;
    if (BF_WindowOwnsMenu(direct,handle)) return direct;
    struct Search {HMENU menu;HWND window;}; Search search{handle,nullptr};
    EnumThreadWindows(GetCurrentThreadId(),[](HWND popup,LPARAM data)->BOOL {
        auto& found=*reinterpret_cast<Search*>(data);
        if (!BF_WindowOwnsMenu(popup,found.menu)) return TRUE;
        found.window=popup;return FALSE;
    },reinterpret_cast<LPARAM>(&search));
    return search.window;
}

static void BF_RoundFooterWindow(BF_NativePopup& menu,HMENU parent,HWND window) {
    if (!window || (window==menu.roundedWindow && parent==menu.roundedMenu)) return;
    RECT frame{};
    if (!GetWindowRect(window,&frame)) return;
    const int width=frame.right-frame.left,height=frame.bottom-frame.top;
    if (width<4 || height<4) return;
    menu.roundedWindow=window;
    menu.roundedMenu=parent;
    // The USER menu has a non-client outline of its own, separate from DWM.
    if (SetWindowSubclass(window,BF_PaintFooterFrame,reinterpret_cast<UINT_PTR>(&menu),reinterpret_cast<DWORD_PTR>(&menu))) {
        if (std::find(menu.framedWindows.begin(),menu.framedWindows.end(),window)==menu.framedWindows.end())
            menu.framedWindows.push_back(window);
        if (HDC frameDC=GetWindowDC(window)) {
            BF_FillFooterFrame(window,frameDC,menu);
            ReleaseDC(window,frameDC);
        }
    }
    const DWM_WINDOW_CORNER_PREFERENCE corner=DWMWCP_ROUND;
    const COLORREF border=DWMWA_COLOR_NONE;
    DwmSetWindowAttribute(window,DWMWA_BORDER_COLOR,&border,sizeof(border));
    if (SUCCEEDED(DwmSetWindowAttribute(window,DWMWA_WINDOW_CORNER_PREFERENCE,&corner,sizeof(corner)))) {
        SetWindowRgn(window,nullptr,FALSE);
        return;
    }
    // Keep the corners clipped when the compositor API is unavailable.
    const int diameter=MulDiv(16,menu.dpi,96);
    HRGN region=CreateRoundRectRgn(1,1,width,height,diameter,diameter);
    if (!region) return;
    if (!SetWindowRgn(window,region,FALSE)) {
        menu.roundedWindow=nullptr;menu.roundedMenu=nullptr;
        DeleteObject(region);
    }
}

static void BF_QueueFooterFrame(BF_NativePopup& menu,HMENU handle) {
    if (menu.pendingFrame==handle) return;
    menu.pendingFrame=handle;
    menu.frameDeadline=GetTickCount64()+300;
    if (!menu.frameTimer) menu.frameTimer=SetTimer(menu.owner,reinterpret_cast<UINT_PTR>(&menu),16,nullptr);
}

static LRESULT CALLBACK BF_PaintFooterItem(HWND owner,UINT msg,WPARAM wp,LPARAM lp,UINT_PTR,DWORD_PTR ref) {
    auto& menu=*reinterpret_cast<BF_NativePopup*>(ref);
    if (msg==WM_INITMENUPOPUP) {
        const auto handle=reinterpret_cast<HMENU>(wp);
        if (handle && handle!=menu.handle) BF_QueueFooterFrame(menu,handle);
        return DefSubclassProc(owner,msg,wp,lp);
    }
    if (msg==WM_TIMER && menu.frameTimer && wp==menu.frameTimer) {
        const auto handle=menu.pendingFrame;
        const auto window=handle ? BF_FindFooterWindow(handle) : nullptr;
        RECT bounds{};
        const bool shown=window && IsWindowVisible(window) && GetWindowRect(window,&bounds) &&
            bounds.right-bounds.left>3 && bounds.bottom-bounds.top>3;
        if (shown || GetTickCount64()>=menu.frameDeadline) {
            KillTimer(owner,menu.frameTimer);menu.frameTimer=0;menu.pendingFrame=nullptr;
            if (shown) {
                BF_RoundFooterWindow(menu,handle,window);
                RedrawWindow(window,nullptr,nullptr,RDW_INVALIDATE|RDW_FRAME);
            }
        }
        return 0;
    }
    if ((msg!=WM_DRAWITEM && msg!=WM_MEASUREITEM) || !lp || wp!=0) return DefSubclassProc(owner,msg,wp,lp);
    auto measure=msg==WM_MEASUREITEM ? reinterpret_cast<MEASUREITEMSTRUCT*>(lp) : nullptr;
    auto draw=msg==WM_DRAWITEM ? reinterpret_cast<DRAWITEMSTRUCT*>(lp) : nullptr;
    if ((measure ? measure->CtlType : draw->CtlType)!=ODT_MENU) return DefSubclassProc(owner,msg,wp,lp);
    const ULONG_PTR data=measure ? measure->itemData : draw->itemData;
    auto row=std::find_if(menu.rows.begin(),menu.rows.end(),[data](const auto& r){return reinterpret_cast<ULONG_PTR>(&r)==data;});
    if (row==menu.rows.end()) return DefSubclassProc(owner,msg,wp,lp);
    auto px=[&menu](int dip){return MulDiv(dip,menu.dpi,96);};
    if (measure) {
        if (row->parent!=menu.handle) BF_QueueFooterFrame(menu,row->parent);
        if (row->separator) {measure->itemHeight=px(7);measure->itemWidth=0;return TRUE;}
        HDC dc=GetDC(owner);
        if (!dc) return DefSubclassProc(owner,msg,wp,lp);
        auto original=SelectObject(dc,menu.font);
        SIZE size{};GetTextExtentPoint32W(dc,row->label.c_str(),static_cast<int>(row->label.size()),&size);
        SelectObject(dc,original);ReleaseDC(owner,dc);
        measure->itemHeight=std::max(LONG(px(32)),size.cy+px(8));
        measure->itemWidth=size.cx+px(70);
        return TRUE;
    }
    HDC dc=draw->hDC;
    const auto window=BF_FindFooterWindow(row->parent,dc);
    if (window && IsWindowVisible(window)) BF_RoundFooterWindow(menu,row->parent,window);
    else BF_QueueFooterFrame(menu,row->parent);
    const int saved=SaveDC(dc);
    const auto brush=static_cast<HBRUSH>(GetStockObject(DC_BRUSH));
    SetDCBrushColor(dc,menu.fill);
    FillRect(dc,&draw->rcItem,brush);
    POINT surface{};
    RECT screenRow{};
    if (window && ClientToScreen(window,&surface)) BF_DrawPopupBackdrop(menu,dc,draw->rcItem,surface);
    else if (GetMenuItemRect(nullptr,row->parent,row->position,&screenRow))
        BF_DrawPopupBackdrop(menu,dc,draw->rcItem,{screenRow.left-draw->rcItem.left,screenRow.top-draw->rcItem.top});
    if (row->separator) {
        RECT line=draw->rcItem;
        line.left+=px(12);line.right-=px(12);
        line.top=(line.top+line.bottom)/2;line.bottom=line.top+1;
        SetDCBrushColor(dc,BF_FooterBlend(menu.fill,menu.ink,14));FillRect(dc,&line,brush);
        if (saved) RestoreDC(dc,saved);
        return TRUE;
    }
    const bool disabled=(draw->itemState&(ODS_DISABLED|ODS_GRAYED))!=0;
    const bool selected=(draw->itemState&(ODS_SELECTED|ODS_HOTLIGHT))!=0;
    const bool focus=(draw->itemState&ODS_FOCUS) && !(draw->itemState&ODS_NOFOCUSRECT);
    const COLORREF fill=selected && !disabled ? BF_FooterBlend(menu.fill,menu.ink,10) : menu.fill;
    if ((selected && !disabled) || focus) {
        RECT surface=draw->rcItem;
        InflateRect(&surface,-px(4),-px(2));
        SelectObject(dc,brush);SetDCBrushColor(dc,fill);
        SelectObject(dc,GetStockObject(focus ? DC_PEN : NULL_PEN));
        if (focus) SetDCPenColor(dc,BF_FooterBlend(menu.fill,menu.ink,65));
        RoundRect(dc,surface.left,surface.top,surface.right,surface.bottom,px(10),px(10));
    }
    SetTextColor(dc,disabled ? BF_FooterBlend(fill,menu.ink,55) : menu.ink);
    SetBkMode(dc,TRANSPARENT);
    SelectObject(dc,menu.font);
    RECT label=draw->rcItem,glyph=label;
    const bool rtl=(GetLayout(dc)&LAYOUT_RTL)!=0;
    glyph.left+=px(10);glyph.right=glyph.left+px(18);
    label.left+=px(36);label.right-=px(7);
    const UINT flags=DT_SINGLELINE|DT_VCENTER|DT_NOPREFIX;
    DrawTextW(dc,row->label.c_str(),static_cast<int>(row->label.size()),&label,flags|(rtl ? DT_RTLREADING : 0));
    const bool checked=(draw->itemState&ODS_CHECKED)!=0;
    if (checked || !row->glyph.text.empty()) {
        const auto family=checked ? L"Segoe Fluent Icons" : row->glyph.family.c_str();
        HFONT icon=CreateFontW(-px(16),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
                               OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,ANTIALIASED_QUALITY,DEFAULT_PITCH,family);
        if (icon) {
            const auto old=SelectObject(dc,icon);
            DrawTextW(dc,checked ? L"\uE73E" : row->glyph.text.c_str(),-1,&glyph,flags|DT_CENTER);
            SelectObject(dc,old);DeleteObject(icon);
        }
    }
    if (saved) RestoreDC(dc,saved);
    return TRUE;
}

// USER can cache a submenu's first owner-draw in a memory DC before placing
// its HWND. Recompose the client (including the gutters) in its final screen
// coordinates, preserving the original USER selection and command IDs.
static void BF_PaintSubmenuClient(HWND window,HDC dc,BF_NativePopup& menu) {
    auto handle=reinterpret_cast<HMENU>(SendMessageW(window,MN_GETHMENU,0,0));
    if (!handle || handle==menu.handle) return;
    RECT client{};POINT origin{};
    if (!GetClientRect(window,&client) || !ClientToScreen(window,&origin)) return;
    FillRect(dc,&client,menu.background);
    BF_DrawPopupBackdrop(menu,dc,client,origin);
    for (const auto& row:menu.rows) {
        if (row.parent!=handle) continue;
        MENUITEMINFOW item{sizeof(item)};
        item.fMask=MIIM_STATE|MIIM_ID|MIIM_SUBMENU;
        DRAWITEMSTRUCT draw{};
        if (!GetMenuItemInfoW(handle,row.position,TRUE,&item) || !GetMenuItemRect(nullptr,handle,row.position,&draw.rcItem)) continue;
        OffsetRect(&draw.rcItem,-origin.x,-origin.y);
        draw.CtlType=ODT_MENU;draw.itemAction=ODA_DRAWENTIRE;draw.itemID=item.wID;
        draw.itemState=(item.fState&MFS_HILITE ? ODS_SELECTED : 0)|(item.fState&MFS_DISABLED ? ODS_DISABLED : 0)|
                       (item.fState&MFS_CHECKED ? ODS_CHECKED : 0);
        draw.itemData=reinterpret_cast<ULONG_PTR>(&row);draw.hDC=dc;draw.hwndItem=reinterpret_cast<HWND>(handle);
        BF_PaintFooterItem(menu.owner,WM_DRAWITEM,0,reinterpret_cast<LPARAM>(&draw),0,reinterpret_cast<DWORD_PTR>(&menu));
        if (item.hSubMenu) {
            RECT arrow=draw.rcItem;
            arrow.left=arrow.right-MulDiv(18,menu.dpi,96);
            auto old=SelectObject(dc,menu.font);
            SetTextColor(dc,menu.ink);SetBkMode(dc,TRANSPARENT);
            DrawTextW(dc,L"\u203a",1,&arrow,DT_CENTER|DT_VCENTER|DT_SINGLELINE);
            SelectObject(dc,old);
        }
    }
}

struct BF_FooterPainting {
    BF_NativePopup& menu;
    bool attached=false;
    explicit BF_FooterPainting(BF_NativePopup& value):menu(value) {
        if (!menu.background || menu.rows.empty()) return;
        NONCLIENTMETRICSW metrics{sizeof(metrics)};
        if (!SystemParametersInfoForDpi(SPI_GETNONCLIENTMETRICS,sizeof(metrics),&metrics,0,menu.dpi)) return;
        menu.font=CreateFontIndirectW(&metrics.lfMenuFont);
        if (!menu.font || !SetWindowSubclass(menu.owner,BF_PaintFooterItem,reinterpret_cast<UINT_PTR>(this),reinterpret_cast<DWORD_PTR>(&menu))) return;
        attached=true;
        MENUINFO info{sizeof(info)};info.fMask=MIM_BACKGROUND|MIM_APPLYTOSUBMENUS;info.hbrBack=menu.background;
        SetMenuInfo(menu.handle,&info);
        for (auto& row:menu.rows) {
            MENUITEMINFOW item{sizeof(item)};item.fMask=MIIM_FTYPE|MIIM_DATA;
            if (!GetMenuItemInfoW(row.parent,row.position,TRUE,&item)) continue;
            // A real hbmpItem makes USER size the row from the bitmap and skip
            // WM_MEASUREITEM. Our owner-draw path already draws the glyph.
            item.fMask|=MIIM_BITMAP;item.hbmpItem=nullptr;
            item.fType|=MFT_OWNERDRAW;item.dwItemData=reinterpret_cast<ULONG_PTR>(&row);
            SetMenuItemInfoW(row.parent,row.position,TRUE,&item);
        }
    }
    ~BF_FooterPainting() {
        if (menu.frameTimer) KillTimer(menu.owner,menu.frameTimer);
        for (HWND window:menu.framedWindows)
            RemoveWindowSubclass(window,BF_PaintFooterFrame,reinterpret_cast<UINT_PTR>(&menu));
        if (attached) RemoveWindowSubclass(menu.owner,BF_PaintFooterItem,reinterpret_cast<UINT_PTR>(this));
    }
};
