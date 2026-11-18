#pragma once

// Start owns one UI thread for its menu and flyouts. Updating this brush also
// repaints open presenters without unloading their controls or command handlers.
static thread_local Media::SolidColorBrush bf_startTextBrush{nullptr};

static void BF_RefreshStartInk() {
    const int tone=bf_startInkTone.load();
    if (!bf_is_start_menu || tone<0 || !bf_startTextBrush) return;
    const auto color=tone ? winrt::Windows::UI::Colors::White() : winrt::Windows::UI::Colors::Black();
    if (bf_startTextBrush.Color()!=color) bf_startTextBrush.Color(color);
    if (bf_appliedStartInk.exchange(tone)!=tone && bf_status_event) SetEvent(bf_status_event);
}

static Media::SolidColorBrush BF_StartForeground(const Media::SolidColorBrush& fallback) {
    if (!bf_is_start_menu || bf_startInkTone.load()<0) return fallback;
    if (!bf_startTextBrush) bf_startTextBrush=Media::SolidColorBrush(fallback.Color());
    BF_RefreshStartInk();
    return bf_startTextBrush;
}

static void BF_StyleStartForeground(const DependencyProperty& property, wf::IInspectable& value) {
    if (!bf_is_start_menu || bf_startInkTone.load()<0 || !value) return;
    if (property!=Controls::TextBlock::ForegroundProperty() && property!=Controls::Control::ForegroundProperty() &&
        property!=Controls::IconElement::ForegroundProperty()) return;
    auto brush=value.try_as<Media::SolidColorBrush>();
    if (!brush) return;
    const auto color=brush.Color();
    if (color==winrt::Windows::UI::Colors::White() || color==winrt::Windows::UI::Colors::Black())
        value=BF_StartForeground(brush);
}
