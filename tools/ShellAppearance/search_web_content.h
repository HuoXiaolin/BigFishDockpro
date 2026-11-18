#pragma once

static bool BF_IsSearchDocument(const wf::Uri& source) {
    if (!source) return false;
    auto address = std::wstring(source.AbsoluteCanonicalUri());
    if (auto end = address.find_first_of(L"?#"); end != address.npos) address.erase(end);
    for (auto path : {
        L"https://www.bing.com/WS/Init", L"https://cn.bing.com/WS/Init",
        L"https://searchapp.bundleassets.example/desktop/2.html",
        L"https://searchapp.bundleassets.example/desktopdefault/2.html",
        L"ms-appx-web://microsoftwindows.client.cbs/Cortana.UI/cache/svlocal/desktop/2.html",
        L"ms-appx-web://microsoftwindows.client.cbs/Cortana.UI/cache/svlocal/desktopdefault/2.html",
        L"ms-appx-web://microsoftwindows.client.cbs/Cortana.UI/cache/wv2local/desktop/2.html",
        L"ms-appx-web://microsoftwindows.client.cbs/Cortana.UI/cache/wv2local/desktopdefault/2.html",
    }) {
        if (_wcsicmp(address.c_str(), path)==0) return true;
    }
    return false;
}

static bool BF_IsSearchView(const FrameworkElement& element) {
    auto type = winrt::get_class_name(element);
    if (type != L"Windows.UI.Xaml.Controls.WebView" && type != L"WebView2Standalone.Controls.WebView2") return false;
    if (bf_is_start_menu) {
        bool insideSearch = false;
        for (DependencyObject parent = Media::VisualTreeHelper::GetParent(element); parent;
             parent = Media::VisualTreeHelper::GetParent(parent)) {
            if (winrt::get_class_name(parent) == L"Cortana.UI.Views.TaskbarSearchPage") {
                insideSearch = true;
                break;
            }
        }
        if (!insideSearch) return false;
    }
    if (!bf_search_view_seen.exchange(true) && bf_status_event) SetEvent(bf_status_event);
    return true;
}

static void BF_WatchSearchStyles(const wf::IAsyncOperation<winrt::hstring>& operation) {
    if (!operation) return;
    operation.Completed([generation=bf_search_style_generation.load()](const auto& completed, wf::AsyncStatus status) {
        if (generation != bf_search_style_generation.load() || status != wf::AsyncStatus::Completed) return;
        try {
            auto result = completed.GetResults();
            if (result==L"bigfish-search-styled" || result==L"\"bigfish-search-styled\"") {
                if (!bf_search_styles_ready.exchange(true) && bf_status_event) SetEvent(bf_status_event);
            }
        } catch (const winrt::hresult_error& error) {
            Wh_Log(L"Error %08X: Search content styles", error.code());
        }
    });
}

static void BF_ClearSearchStylesStatus() {
    ++bf_search_style_generation;
    bf_search_view_seen = false;
    bf_search_styles_ready = false;
}
