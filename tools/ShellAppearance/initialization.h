// CoreWindow can be reported from inside XAML construction. Initialize only
// after that stack has returned, and retry a bounded number of readiness races.
static bool BF_XamlInitialized() {
#ifdef BIGFISH_START_ENGINE
    return g_targetThreadId.load() != 0;
#else
    return g_initialized.load() && g_initializedForThread;
#endif
}

static void CALLBACK BF_InitializeWhenReady(HWND,UINT,UINT_PTR timer,DWORD) {
    KillTimer(nullptr,timer);
    if (bf_init_timer != timer) return;
    bf_init_timer = 0;
    if (!bf_init_enabled || bf_thread_init_generation != bf_init_generation) return;
    if (BF_XamlInitialized()) return;
    ++bf_thread_init_attempts;
    ++bf_init_attempts;
    bf_init_state = 1;
    const auto priorErrors = bf_errors.load();
    try {
#ifndef BIGFISH_START_ENGINE
        InitializeForCurrentThread();
#endif
        InitializeSettingsAndTap();
    } catch (...) {
        bf_last_error = static_cast<unsigned long>(winrt::to_hresult().value);
#ifdef BIGFISH_START_ENGINE
        g_targetThreadId = 0;
#else
        try {UninitializeForCurrentThread();} catch (...) {}
        g_initialized = false;
#endif
    }
    if (BF_XamlInitialized()) {
        bf_init_state = 2;
        if (bf_status_event) SetEvent(bf_status_event);
        return;
    }
    bf_errors = priorErrors;
    bf_init_state = 3;
    if (bf_thread_init_attempts < 12) {
        const auto delay = std::min(1000u,40u << std::min(bf_thread_init_attempts,5u));
        bf_init_timer = SetTimer(nullptr,0,delay,BF_InitializeWhenReady);
    } else {
        ++bf_errors;
    }
    if (bf_status_event) SetEvent(bf_status_event);
}

static void BF_QueueShellInitialization() {
#ifdef BIGFISH_START_ENGINE
    if (bf_init_enabled) BF_RefreshStartInk();
#endif
    if (!bf_init_enabled || bf_init_timer || BF_XamlInitialized()) return;
    bf_thread_init_generation = bf_init_generation;
    bf_thread_init_attempts = 0;
    bf_init_timer = SetTimer(nullptr,0,16,BF_InitializeWhenReady);
}

static void BF_RequestShellInitialization(HWND window) {
    if (!window || !bf_init_enabled) return;
    if (GetWindowThreadProcessId(window,nullptr)==GetCurrentThreadId()) {
        BF_QueueShellInitialization();
    } else {
        RunFromWindowThreadViaPostMessage(window,[](PVOID){BF_QueueShellInitialization();},nullptr);
    }
}
