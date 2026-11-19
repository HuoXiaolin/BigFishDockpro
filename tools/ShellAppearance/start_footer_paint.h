#pragma once

// USER still owns tracking, keyboard navigation, accessibility and dispatch.
// Only the pixels belonging to this temporary menu are drawn here.
static COLORREF BF_FooterBlend(COLORREF base,COLORREF ink,int percent) {
    auto channel=[percent](int b,int i){return (b*(100-percent)+i*percent+50)/100;};
    return RGB(channel(GetRValue(base),GetRValue(ink)),channel(GetGValue(base),GetGValue(ink)),channel(GetBValue(base),GetBValue(ink)));
}

// The first on-screen item draw already has the native menu's final bounds.
// Clip just this popup. Its original window and USER hit targets stay together.
static void BF_RoundFooterWindow(BF_FooterMenu& menu,HMENU parent,HDC dc) {
    const HWND window=WindowFromDC(dc);
    if (!window || (window==menu.roundedWindow && parent==menu.roundedMenu)) return;
    MENUBARINFO bar{sizeof(bar)};
    RECT frame{};
    if (GetWindowThreadProcessId(window,nullptr)!=GetCurrentThreadId() ||
        !GetMenuBarInfo(window,OBJID_CLIENT,0,&bar) || bar.hMenu!=parent || !GetWindowRect(window,&frame)) return;
    const int width=frame.right-frame.left,height=frame.bottom-frame.top;
    if (width<4 || height<4) return;
    const int diameter=MulDiv(20,menu.dpi,96);
    // Exclude the one-pixel square system border as well as its corners.
    HRGN region=CreateRoundRectRgn(1,1,width,height,diameter,diameter);
    if (!region) return;
    menu.roundedWindow=window;
    menu.roundedMenu=parent;
    if (!SetWindowRgn(window,region,FALSE)) {
        menu.roundedWindow=nullptr;menu.roundedMenu=nullptr;
        DeleteObject(region);
    }
}

static LRESULT CALLBACK BF_PaintFooterItem(HWND owner,UINT msg,WPARAM wp,LPARAM lp,UINT_PTR,DWORD_PTR ref) {
    auto& menu=*reinterpret_cast<BF_FooterMenu*>(ref);
    if ((msg!=WM_DRAWITEM && msg!=WM_MEASUREITEM) || !lp || wp!=0) return DefSubclassProc(owner,msg,wp,lp);
    auto measure=msg==WM_MEASUREITEM ? reinterpret_cast<MEASUREITEMSTRUCT*>(lp) : nullptr;
    auto draw=msg==WM_DRAWITEM ? reinterpret_cast<DRAWITEMSTRUCT*>(lp) : nullptr;
    if ((measure ? measure->CtlType : draw->CtlType)!=ODT_MENU) return DefSubclassProc(owner,msg,wp,lp);
    const ULONG_PTR data=measure ? measure->itemData : draw->itemData;
    auto row=std::find_if(menu.rows.begin(),menu.rows.end(),[data](const auto& r){return reinterpret_cast<ULONG_PTR>(&r)==data;});
    if (row==menu.rows.end()) return DefSubclassProc(owner,msg,wp,lp);
    auto px=[&menu](int dip){return MulDiv(dip,menu.dpi,96);};
    if (measure) {
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
    BF_RoundFooterWindow(menu,row->parent,dc);
    const int saved=SaveDC(dc);
    const auto brush=static_cast<HBRUSH>(GetStockObject(DC_BRUSH));
    SetDCBrushColor(dc,menu.fill);
    FillRect(dc,&draw->rcItem,brush);
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

struct BF_FooterPainting {
    BF_FooterMenu& menu;
    bool attached=false;
    explicit BF_FooterPainting(BF_FooterMenu& value):menu(value) {
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
        if (attached) RemoveWindowSubclass(menu.owner,BF_PaintFooterItem,reinterpret_cast<UINT_PTR>(this));
    }
};
