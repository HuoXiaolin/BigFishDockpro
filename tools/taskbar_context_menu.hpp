#pragma once
#include "taskbar_overflow.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <shlwapi.h>
#include <windowsx.h>
#include "start_footer_paint.h"
#include "undefgetcurrenttime.h"
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.UI.Xaml.Automation.Peers.h>
#include <winrt/Windows.UI.Xaml.Automation.Provider.h>
#include <winrt/Windows.UI.Xaml.Controls.Primitives.h>
#include "redefgetcurrenttime.h"

namespace bigfish
{
struct TaskbarMenuStyle
{
	OverflowStyle brush;
	unsigned ink, edgeAlpha;
	bool flowing;
	bool operator==(const TaskbarMenuStyle&) const = default;
};

inline std::optional<TaskbarMenuStyle> ReadTaskbarMenuStyle(const std::wstring& path)
{
	constexpr PCWSTR section = L"TaskbarMenu";
	const auto brush = ReadOverflowStyle(path, section);
	if (!brush) return std::nullopt;
	const auto ink = GetPrivateProfileIntW(section, L"Ink", 0, path.c_str());
	const auto edge = GetPrivateProfileIntW(section, L"EdgeAlpha", 0, path.c_str());
	const auto flowing = GetPrivateProfileIntW(section, L"Flowing", 0, path.c_str());
	if (ink > 2 || edge > 160 || flowing > 1) return std::nullopt;
	return TaskbarMenuStyle{*brush, ink, edge, flowing != 0};
}

inline std::array<std::wstring, 2> LocalizedTaskbarMenuLabels()
{
	std::array<std::wstring, 2> labels;
	const auto module = GetModuleHandleW(L"Taskbar.View.dll");
	wchar_t path[MAX_PATH]{};
	const auto length = module ? GetModuleFileNameW(module, path, ARRAYSIZE(path)) : 0;
	if (!length || length >= ARRAYSIZE(path)) return labels;
	const std::wstring_view file{path, length};
	const auto last = file.find_last_of(L'\\');
	if (last == file.npos || !last) return labels;
	const auto folder = file.substr(0, last);
	const auto package = folder.substr(folder.find_last_of(L'\\') + 1);
	const auto map = package.substr(0, package.find(L'_'));
	const auto prefix = L"@{" + std::wstring(folder) + L"\\resources.pri?ms-resource://" +
		std::wstring(map) + L"/Taskbar/Resources/";
	constexpr PCWSTR keys[]{L"TaskManagerContextMenuItemText", L"TaskbarSettingsContextMenuItemText"};
	for (size_t i = 0; i < labels.size(); ++i)
	{
		wchar_t label[128]{};
		const auto indirect = prefix + keys[i] + L"}";
		if (SUCCEEDED(SHLoadIndirectString(indirect.c_str(), label, ARRAYSIZE(label), nullptr)))
			labels[i] = label;
	}
	return labels;
}

inline int TaskbarMenuCommand(std::wstring_view label)
{
	if (label == L"Task Manager" || label == L"任务管理器" || label == L"工作管理員") return 0;
	if (label == L"Taskbar settings" || label == L"任务栏设置" || label == L"工作列設定") return 1;
	static const auto localized = LocalizedTaskbarMenuLabels();
	for (size_t i = 0; i < localized.size(); ++i)
		if (!localized[i].empty() && label == localized[i]) return static_cast<int>(i);
	return -1;
}

inline std::array<wuxc::MenuFlyoutItem, 2> TaskbarMenuRows(const wuxc::MenuFlyoutPresenter& menu)
{
	std::array<wuxc::MenuFlyoutItem, 2> rows{nullptr, nullptr};
	for (const auto& element : menu.Items())
	{
		if (element.try_as<wuxc::MenuFlyoutSeparator>()) continue;
		const auto row = element.try_as<wuxc::MenuFlyoutItem>();
		const auto command = row ? TaskbarMenuCommand(row.Text()) : -1;
		if (command < 0 || rows[command]) return {nullptr, nullptr};
		rows[command] = row;
	}
	return rows;
}

inline COLORREF TaskbarMenuComposite(winrt::Windows::UI::Color tint, COLORREF background) noexcept
{
	const auto channel = [a = unsigned(tint.A)](unsigned color, unsigned behind) {
		return (color * a + behind * (255 - a) + 127) / 255;
	};
	return RGB(channel(tint.R, GetRValue(background)), channel(tint.G, GetGValue(background)),
		channel(tint.B, GetBValue(background)));
}

inline double TaskbarMenuLuminance(COLORREF color) noexcept
{
	const auto linear = [](unsigned channel) {
		const double value = channel / 255.0;
		return value <= .04045 ? value / 12.92 : std::pow((value + .055) / 1.055, 2.4);
	};
	return .2126 * linear(GetRValue(color)) + .7152 * linear(GetGValue(color)) +
		.0722 * linear(GetBValue(color));
}

inline COLORREF TaskbarMenuInk(unsigned mode, COLORREF fill) noexcept
{
	// At this luminance white and black have equal contrast.
	const bool white = mode == 2 || (mode == 0 && TaskbarMenuLuminance(fill) < .1791287847);
	return white ? RGB(255, 255, 255) : RGB(0, 0, 0);
}

inline COLORREF TaskbarMenuFill(const RECT& bounds, winrt::Windows::UI::Color tint) noexcept
{
	const auto fallback = RGB(tint.R, tint.G, tint.B);
	if (tint.A == 255) return fallback;
	MONITORINFO display{sizeof(display)};
	if (!GetMonitorInfoW(MonitorFromRect(&bounds, MONITOR_DEFAULTTONULL), &display)) return fallback;
	RECT sample{};
	if (!IntersectRect(&sample, &bounds, &display.rcMonitor)) return fallback;
	std::array<std::pair<double, COLORREF>, 25> colors{};
	size_t count = 0;
	if (const auto dc = GetDC(nullptr))
	{
		for (int row = 1; row <= 5; ++row)
			for (int col = 1; col <= 5; ++col)
			{
				const auto x = sample.left + (sample.right - sample.left) * col / 6;
				const auto y = sample.top + (sample.bottom - sample.top) * row / 6;
				const auto pixel = GetPixel(dc, x, y);
				if (pixel == CLR_INVALID) continue;
				const auto fill = TaskbarMenuComposite(tint, pixel);
				colors[count++] = {TaskbarMenuLuminance(fill), fill};
			}
		ReleaseDC(nullptr, dc);
	}
	if (!count) return fallback;
	const auto middle = colors.begin() + count / 2;
	std::nth_element(colors.begin(), middle, colors.begin() + count);
	return middle->second;
}

inline HWND TaskbarMenuOwner(const RECT& bounds) noexcept
{
	struct Search { HMONITOR monitor; HWND window; };
	Search search{MonitorFromRect(&bounds, MONITOR_DEFAULTTONULL), nullptr};
	if (!search.monitor) return nullptr;
	EnumThreadWindows(GetCurrentThreadId(), [](HWND hwnd, LPARAM data) -> BOOL
	{
		auto& search = *reinterpret_cast<Search*>(data);
		wchar_t name[32]{};
		if (!IsWindowVisible(hwnd) || MonitorFromWindow(hwnd, MONITOR_DEFAULTTONULL) != search.monitor ||
			!GetClassNameW(hwnd, name, ARRAYSIZE(name))) return TRUE;
		if (std::wstring_view(name) != L"Shell_TrayWnd" && std::wstring_view(name) != L"Shell_SecondaryTrayWnd")
			return TRUE;
		search.window = hwnd;
		return FALSE;
	}, reinterpret_cast<LPARAM>(&search));
	return search.window;
}

inline wuxc::Primitives::Popup TaskbarMenuPopup(const wuxc::MenuFlyoutPresenter& menu)
{
	const auto root = menu.XamlRoot();
	if (!root) return nullptr;
	for (const auto& popup : wux::Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(root))
	{
		const auto content = popup.Child();
		for (wux::DependencyObject element = menu; element; element = wux::Media::VisualTreeHelper::GetParent(element))
			if (popup.IsOpen() && element == content) return popup;
	}
	return nullptr;
}

inline RECT TaskbarPresenterBounds(const wuxc::MenuFlyoutPresenter& menu) noexcept try
{
	const wux::Automation::Peers::FrameworkElementAutomationPeer peer(menu);
	const auto face = peer.GetBoundingRectangle();
	return {std::lround(face.X), std::lround(face.Y), std::lround(face.X + face.Width),
		std::lround(face.Y + face.Height)};
}
catch (...) { return {}; }

inline BF_FooterGlyph TaskbarMenuGlyph(const wuxc::MenuFlyoutItem& row, int command)
{
	if (const auto icon = row.Icon())
	{
		if (const auto font = icon.try_as<wuxc::FontIcon>(); font && font.FontFamily() && !font.Glyph().empty())
			return {font.Glyph(), font.FontFamily().Source()};
		if (const auto symbol = icon.try_as<wuxc::SymbolIcon>())
			return {winrt::hstring(std::wstring(1, static_cast<wchar_t>(symbol.Symbol()))), L"Segoe MDL2 Assets"};
	}
	return {command == 0 ? L"\uE9D9" : L"\uE713", L"Segoe Fluent Icons"};
}

using TaskbarInvoke = wux::Automation::Provider::IInvokeProvider;
struct TaskbarNativeMenu : BF_NativePopup
{
	std::array<TaskbarInvoke, 2> actions{nullptr, nullptr};
};

inline bool PopulateTaskbarMenu(TaskbarNativeMenu& native, const wuxc::MenuFlyoutPresenter& source)
{
	if (!native.handle) return false;
	for (const auto& entry : source.Items())
	{
		const auto position = static_cast<UINT>(native.rows.size());
		if (entry.try_as<wuxc::MenuFlyoutSeparator>())
		{
			if (!AppendMenuW(native.handle, MF_SEPARATOR, 0, nullptr)) return false;
			native.rows.push_back({native.handle, position, {}, {}, true});
			continue;
		}
		const auto row = entry.try_as<wuxc::MenuFlyoutItem>();
		const auto command = row ? TaskbarMenuCommand(row.Text()) : -1;
		if (command < 0 || row.Visibility() != wux::Visibility::Visible) return false;
		const bool enabled = row.IsEnabled();
		if (enabled)
		{
			const wux::Automation::Peers::MenuFlyoutItemAutomationPeer peer(row);
			native.actions[command] = peer.try_as<TaskbarInvoke>();
			if (!native.actions[command]) return false;
		}
		std::wstring label(row.Text());
		for (size_t i = 0; (i = label.find(L'&', i)) != std::wstring::npos; i += 2) label.insert(i, 1, L'&');
		if (!AppendMenuW(native.handle, MF_STRING | (enabled ? MF_ENABLED : MF_GRAYED), command + 1, label.c_str()))
			return false;
		native.rows.push_back({native.handle, position, std::wstring(row.Text()), TaskbarMenuGlyph(row, command)});
	}
	return true;
}

// Withhold the XAML presenter while keeping it available for layout and command discovery.
class TaskbarMenuPreview
{
public:
	explicit TaskbarMenuPreview(const wuxc::MenuFlyoutPresenter& menu) :
		m_Menu(winrt::make_weak(menu)), m_Visual(wuxh::ElementCompositionPreview::GetElementVisual(menu)),
		m_Local(menu.ReadLocalValue(wux::UIElement::OpacityProperty())), m_Opacity(menu.Opacity()),
		m_Visible(m_Visual.IsVisible()) {}

	void Mask()
	{
		if (const auto menu = m_Menu.get()) menu.Opacity(0);
		m_Visual.IsVisible(false);
	}

	~TaskbarMenuPreview()
	{
		try
		{
			if (const auto menu = m_Menu.get(); menu && menu.Opacity() == 0)
			{
				const auto property = wux::UIElement::OpacityProperty();
				try
				{
					if (m_Local == wux::DependencyProperty::UnsetValue()) menu.ClearValue(property);
					else menu.SetValue(property, m_Local);
				}
				catch (const winrt::hresult_error&) { menu.Opacity(m_Opacity); }
			}
			m_Visual.IsVisible(m_Visible);
		}
		catch (...) {}
	}

private:
	winrt::weak_ref<wuxc::MenuFlyoutPresenter> m_Menu;
	winrt::Windows::UI::Composition::Visual m_Visual;
	wf::IInspectable m_Local;
	double m_Opacity;
	bool m_Visible;
};

class MenuValue
{
public:
	~MenuValue() { Restore(); }

	void Set(const wux::DependencyObject& target, const wux::DependencyProperty& property, const wf::IInspectable& value)
	{
		if (m_Target.get() != target || m_Property != property)
		{
			Restore();
			m_Local = target.ReadLocalValue(property);
			m_Original = target.GetValue(property);
			m_Property = property;
			m_Target = winrt::make_weak(target);
		}
		target.SetValue(property, value);
	}

	void Restore() noexcept
	{
		try
		{
			if (const auto target = m_Target.get())
			{
				try
				{
					if (m_Local == wux::DependencyProperty::UnsetValue()) target.ClearValue(m_Property);
					else target.SetValue(m_Property, m_Local);
				}
				catch (const winrt::hresult_error&) { target.SetValue(m_Property, m_Original); }
			}
		}
		catch (...) {}
		m_Target = {};
		m_Property = nullptr;
		m_Local = m_Original = nullptr;
	}

private:
	winrt::weak_ref<wux::DependencyObject> m_Target;
	wux::DependencyProperty m_Property{nullptr};
	wf::IInspectable m_Local{nullptr}, m_Original{nullptr};
};

// A windowed taskbar flyout can paint in the correct place while its XAML
// input site ignores clicks. Keep its composited brush and handle clicks at
// the HWND Windows actually reports for the rendered rows.
class TaskbarWindowedMenu
{
public:
	static HWND Find(const RECT& face) noexcept
	{
		struct Search { RECT face; HWND exact = nullptr, only = nullptr; unsigned count = 0; };
		Search search{face};
		EnumThreadWindows(GetCurrentThreadId(), [](HWND window, LPARAM data) -> BOOL
		{
			auto& search = *reinterpret_cast<Search*>(data);
			wchar_t name[40]{};
			RECT rect{};
			if (!IsWindowVisible(window) || !GetClassNameW(window, name, ARRAYSIZE(name)) ||
				std::wstring_view(name) != L"Xaml_WindowedPopupClass" || !GetWindowRect(window, &rect) ||
				rect.right - rect.left < 50 || rect.bottom - rect.top < 30) return TRUE;
			search.only = window;
			++search.count;
			POINT center{(search.face.left + search.face.right) / 2, (search.face.top + search.face.bottom) / 2};
			if (search.face.right > search.face.left && search.face.bottom > search.face.top && PtInRect(&rect, center))
			{
				search.exact = window;
				return FALSE;
			}
			return TRUE;
		}, reinterpret_cast<LPARAM>(&search));
		return search.exact ? search.exact : search.count == 1 ? search.only : nullptr;
	}

	TaskbarWindowedMenu(const wuxc::MenuFlyoutPresenter& menu,
		const std::array<wuxc::MenuFlyoutItem, 2>& rows, HWND window) :
		m_Menu(menu), m_Rows(rows), m_Window(window) {}

	bool Attach(const TaskbarMenuStyle& style, RECT face)
	{
		RECT window{};
		if (!GetWindowRect(m_Window, &window)) return false;
		const double scale = m_Menu.XamlRoot() ? m_Menu.XamlRoot().RasterizationScale() : 1.;
		const LONG width = std::lround(m_Menu.ActualWidth() * scale);
		const LONG height = std::lround(m_Menu.ActualHeight() * scale);
		if (width <= 0 || height <= 0 || width > window.right - window.left + 2 ||
			height > window.bottom - window.top + 2) return false;
		if (face.left < window.left - 2 || face.top < window.top - 2 ||
			face.right > window.right + 2 || face.bottom > window.bottom + 2 || IsRectEmpty(&face))
		{
			const LONG x = (window.left + window.right - width) / 2;
			const LONG y = (window.top + window.bottom - height) / 2;
			face = {x, y, x + width, y + height};
		}
		for (size_t i = 0; i < m_Rows.size(); ++i)
		{
			const auto& row = m_Rows[i];
			const auto origin = row.TransformToVisual(m_Menu).TransformPoint({0, 0});
			m_HitAreas[i] = {
				face.left + std::lround(origin.X * scale),
				face.top + std::lround(origin.Y * scale),
				face.left + std::lround((origin.X + row.ActualWidth()) * scale),
				face.top + std::lround((origin.Y + row.ActualHeight()) * scale)};
			if (IsRectEmpty(&m_HitAreas[i])) return false;
		}
		if (!Watch(m_Window)) return false;
		EnumChildWindows(m_Window, [](HWND child, LPARAM data) -> BOOL
		{
			auto& menu = *reinterpret_cast<TaskbarWindowedMenu*>(data);
			if (GetWindowThreadProcessId(child, nullptr) == GetCurrentThreadId()) menu.Watch(child);
			return TRUE;
		}, reinterpret_cast<LPARAM>(this));

		const auto color = TaskbarMenuInk(style.ink, TaskbarMenuFill(face, SurfaceTint(style.brush)));
		const wux::Media::SolidColorBrush ink({255, GetRValue(color), GetGValue(color), GetBValue(color)});
		m_HoverBrush = wux::Media::SolidColorBrush({static_cast<uint8_t>(GetRValue(color) ? 52 : 32),
			GetRValue(color), GetGValue(color), GetBValue(color)});
		const auto corners = winrt::box_value(wux::CornerRadius{12, 12, 12, 12});
		m_Corners.Set(m_Menu, wuxc::Control::CornerRadiusProperty(), corners);
		m_Foreground.Set(m_Menu, wuxc::Control::ForegroundProperty(), ink);
		const auto border = wux::Media::VisualTreeHelper::GetChildrenCount(m_Menu)
			? wux::Media::VisualTreeHelper::GetChild(m_Menu, 0).try_as<wuxc::Border>() : nullptr;
		const auto brush = MakeSurfaceBrush(m_Menu, style.brush);
		const auto edge = Edge(style);
		if (border)
		{
			m_BorderCorners.Set(border, wuxc::Border::CornerRadiusProperty(), corners);
			m_Background.Set(border, wuxc::Border::BackgroundProperty(), brush);
			m_Edge.Set(border, wuxc::Border::BorderBrushProperty(), edge);
		}
		else
		{
			m_Background.Set(m_Menu, wuxc::Control::BackgroundProperty(), brush);
			m_Edge.Set(m_Menu, wuxc::Control::BorderBrushProperty(), edge);
		}
		for (size_t i = 0; i < m_Rows.size(); ++i)
		{
			m_RowInk[i].Set(m_Rows[i], wuxc::Control::ForegroundProperty(), ink);
			if (const auto icon = m_Rows[i].Icon()) m_IconInk[i].Set(icon, wuxc::IconElement::ForegroundProperty(), ink);
		}
		return true;
	}

	~TaskbarWindowedMenu()
	{
		for (const auto window : m_Attached) RemoveWindowSubclass(window, WindowInput, reinterpret_cast<UINT_PTR>(this));
	}

private:
	static wux::Media::Brush Edge(const TaskbarMenuStyle& style)
	{
		if (!style.flowing) return wux::Media::SolidColorBrush({static_cast<uint8_t>(style.edgeAlpha), 255, 255, 255});
		const wux::Media::LinearGradientBrush brush;
		brush.EndPoint({1, 1});
		const wux::Media::GradientStop start, end;
		start.Color({184, 100, 232, 222});
		end.Color({184, 138, 100, 235});
		end.Offset(1);
		brush.GradientStops().Append(start);
		brush.GradientStops().Append(end);
		return brush;
	}

	bool Watch(HWND window)
	{
		if (!SetWindowSubclass(window, WindowInput, reinterpret_cast<UINT_PTR>(this), reinterpret_cast<DWORD_PTR>(this)))
			return false;
		m_Attached.push_back(window);
		return true;
	}

	int RowAt(POINT position) const noexcept
	{
		for (size_t i = 0; i < m_HitAreas.size(); ++i)
			if (PtInRect(&m_HitAreas[i], position)) return static_cast<int>(i);
		return -1;
	}

	void SetHover(int index)
	{
		if (index >= 0 && !m_Rows[index].IsEnabled()) index = -1;
		if (m_Hovered == index) return;
		m_HoverSurface.Restore();
		m_HoverRow.Restore();
		m_Hovered = index;
		if (index < 0) return;
		const auto& row = m_Rows[index];
		m_HoverRow.Set(row, wuxc::Control::BackgroundProperty(), m_HoverBrush);
		if (!wux::Media::VisualTreeHelper::GetChildrenCount(row)) return;
		const auto surface = wux::Media::VisualTreeHelper::GetChild(row, 0);
		if (const auto panel = surface.try_as<wuxc::Panel>())
			m_HoverSurface.Set(panel, wuxc::Panel::BackgroundProperty(), m_HoverBrush);
		else if (const auto border = surface.try_as<wuxc::Border>())
			m_HoverSurface.Set(border, wuxc::Border::BackgroundProperty(), m_HoverBrush);
	}

	bool HandleInput(HWND window, UINT message, WPARAM wparam, LPARAM position)
	{
		if (message == WM_MOUSEMOVE || message == WM_POINTERUPDATE)
		{
			POINT point{GET_X_LPARAM(position), GET_Y_LPARAM(position)};
			if (message == WM_MOUSEMOVE)
			{
				if (!ClientToScreen(window, &point)) return false;
				if (m_Tracking != window)
				{
					TRACKMOUSEEVENT tracking{sizeof(tracking), TME_LEAVE, window, 0};
					if (TrackMouseEvent(&tracking)) m_Tracking = window;
				}
			}
			SetHover(RowAt(point));
			return false;
		}
		if (message == WM_MOUSELEAVE || message == WM_POINTERLEAVE)
		{
			if (message == WM_MOUSELEAVE && window != m_Tracking) return false;
			m_Tracking = nullptr;
			POINT point{};
			if (GetCursorPos(&point))
			{
				const HWND next = WindowFromPoint(point);
				if (next != window && (next == m_Window || IsChild(m_Window, next))) return false;
			}
			SetHover(-1);
			return false;
		}
		if (message == WM_CANCELMODE || message == WM_CAPTURECHANGED) { m_Pressed = -1; return false; }
		const bool down = message == WM_LBUTTONDOWN || message == WM_POINTERDOWN;
		if (!down && message != WM_LBUTTONUP && message != WM_POINTERUP) return false;
		if (message == WM_POINTERDOWN || message == WM_POINTERUP)
		{
			POINTER_INFO pointer{};
			if (!GetPointerInfo(GET_POINTERID_WPARAM(wparam), &pointer) ||
				pointer.ButtonChangeType != (down ? POINTER_CHANGE_FIRSTBUTTON_DOWN : POINTER_CHANGE_FIRSTBUTTON_UP))
				return false;
		}
		POINT point{GET_X_LPARAM(position), GET_Y_LPARAM(position)};
		if (message == WM_LBUTTONDOWN || message == WM_LBUTTONUP) ClientToScreen(window, &point);
		const auto row = RowAt(point);
		if (down)
		{
			m_Pressed = row;
			return row >= 0;
		}
		const auto pressed = std::exchange(m_Pressed, -1);
		if (pressed < 0) return false;
		if (pressed == row)
		{
			const auto selected = m_Rows[row];
			if (selected.IsEnabled())
				selected.Dispatcher().RunAsync(winrt::Windows::UI::Core::CoreDispatcherPriority::Normal, [selected]
				{
					try
					{
						if (!selected.IsLoaded() || !selected.IsEnabled()) return;
						const wux::Automation::Peers::MenuFlyoutItemAutomationPeer peer(selected);
						if (const auto action = peer.try_as<TaskbarInvoke>()) action.Invoke();
					}
					catch (...) {}
				});
		}
		return true;
	}

	static LRESULT CALLBACK WindowInput(HWND window, UINT message, WPARAM wparam, LPARAM lparam, UINT_PTR id, DWORD_PTR ref)
	{
		if (message == WM_NCDESTROY) RemoveWindowSubclass(window, WindowInput, id);
		else
		{
			try
			{
				if (reinterpret_cast<TaskbarWindowedMenu*>(ref)->HandleInput(window, message, wparam, lparam)) return 0;
			}
			catch (...) {}
		}
		return DefSubclassProc(window, message, wparam, lparam);
	}

	wuxc::MenuFlyoutPresenter m_Menu;
	std::array<wuxc::MenuFlyoutItem, 2> m_Rows;
	HWND m_Window;
	std::array<RECT, 2> m_HitAreas{};
	std::vector<HWND> m_Attached;
	int m_Pressed = -1;
	int m_Hovered = -1;
	HWND m_Tracking = nullptr;
	wux::Media::SolidColorBrush m_HoverBrush{nullptr};
	MenuValue m_HoverSurface, m_HoverRow;
	MenuValue m_Corners, m_BorderCorners, m_Foreground, m_Background, m_Edge;
	std::array<MenuValue, 2> m_RowInk, m_IconInk;
};


struct TaskbarMenuSession
{
	std::wstring path;
	bool tracking = false;
	bool cancelled = false;
};

class TaskbarMenuSurface : public std::enable_shared_from_this<TaskbarMenuSurface>
{
public:
	TaskbarMenuSurface(const wuxc::MenuFlyoutPresenter& menu, std::shared_ptr<TaskbarMenuSession> session) :
		m_Menu(winrt::make_weak(menu)), m_Session(std::move(session)) {}

	void Queue() noexcept try
	{
		const auto menu = m_Menu.get();
		HIGHCONTRASTW contrast{sizeof(contrast)};
		if (m_Timer || m_Windowed || !menu || !menu.Dispatcher().HasThreadAccess() || !menu.IsLoaded() || m_Session->tracking ||
			!ReadTaskbarMenuStyle(m_Session->path) ||
			(SystemParametersInfoW(SPI_GETHIGHCONTRAST, sizeof(contrast), &contrast, 0) &&
				(contrast.dwFlags & HCF_HIGHCONTRASTON))) return;
		if (const auto rows = TaskbarMenuRows(menu); rows[0] && rows[1]) Mask(menu);
		m_Deadline = GetTickCount64() + 750;
		m_Timer = wux::DispatcherTimer();
		m_Timer.Interval(std::chrono::milliseconds(16));
		m_Timer.Tick([weak = weak_from_this()](auto&&, auto&&) noexcept
		{
			if (const auto current = weak.lock()) current->Open();
		});
		m_Timer.Start();
	}
	catch (...) { Cancel(); }

	void Cancel() noexcept
	{
		StopWaiting();
		m_Windowed.reset();
	}

	void StopWaiting() noexcept
	{
		if (auto timer = std::exchange(m_Timer, nullptr))
		{
			try { timer.Stop(); }
			catch (...) {}
		}
		m_Preview.reset();
	}

	void Detach() noexcept try
	{
		Cancel();
		if (const auto menu = m_Menu.get())
		{
			menu.Loaded(loaded);
			menu.Unloaded(unloaded);
		}
	}
	catch (...) {}

	winrt::event_token loaded{}, unloaded{};

private:
	void Mask(const wuxc::MenuFlyoutPresenter& menu)
	{
		if (m_Preview) return;
		m_Preview = std::make_unique<TaskbarMenuPreview>(menu);
		m_Preview->Mask();
		m_MaskedAt = GetTickCount64();
	}

	void Open() noexcept try
	{
		const auto menu = m_Menu.get();
		const auto now = GetTickCount64();
		if (!m_Timer || !menu || !menu.IsLoaded() || m_Session->tracking)
		{
			Cancel();
			return;
		}
		const auto rows = TaskbarMenuRows(menu);
		if (!rows[0] || !rows[1])
		{
			if (now >= m_Deadline) Cancel();
			return;
		}
		Mask(menu);
		// Allow the hidden XAML surface to leave the composed frame before sampling its rectangle.
		if (now < m_MaskedAt + 24) return;
		const auto style = ReadTaskbarMenuStyle(m_Session->path);
		if (!style)
		{
			Cancel();
			return;
		}
		const auto bounds = TaskbarPresenterBounds(menu);
		if (const auto window = TaskbarWindowedMenu::Find(bounds))
		{
			auto live = std::make_unique<TaskbarWindowedMenu>(menu, rows, window);
			if (live->Attach(*style, bounds))
			{
				m_Windowed = std::move(live);
				StopWaiting();
				return;
			}
		}
		const auto popup = TaskbarMenuPopup(menu);
		if (!popup || IsRectEmpty(&bounds))
		{
			if (now >= m_Deadline) Cancel();
			return;
		}
		const auto owner = TaskbarMenuOwner(bounds);
		TaskbarNativeMenu native;
		if (!owner || !PopulateTaskbarMenu(native, menu))
		{
			Cancel();
			return;
		}
		native.owner = owner;
		native.dpi = std::max(96u, GetDpiForWindow(owner));
		const auto tint = SurfaceTint(style->brush);
		native.tint = RGB(tint.R, tint.G, tint.B);
		native.tintOpacity = tint.A;
		native.blur = style->brush.mode == 3 ? style->brush.amount / 100 : style->brush.mode == 2 ? 12 : 0;
		native.fill = TaskbarMenuFill(bounds, tint);
		native.ink = TaskbarMenuInk(style->ink, native.fill);
		native.background = CreateSolidBrush(native.fill);
		BF_CapturePopupBackdrop(native, {bounds.left, bounds.top});
		const BF_FooterPainting paint(native);
		if (!paint.attached)
		{
			Cancel();
			return;
		}

		const bool rtl = menu.FlowDirection() == wux::FlowDirection::RightToLeft;
		const auto preview = std::move(m_Preview);
		Cancel();
		const auto session = m_Session;
		session->tracking = true;
		session->cancelled = false;
		struct EndTracking { TaskbarMenuSession& session; ~EndTracking() { session.tracking = false; } } end{*session};
		popup.IsOpen(false);
		if (popup.IsOpen() || session->cancelled || !IsWindow(owner)) return;
		const UINT align = rtl ? TPM_RIGHTALIGN | TPM_LAYOUTRTL : TPM_LEFTALIGN;
		const UINT command = TrackPopupMenuEx(native.handle,
			TPM_RETURNCMD | TPM_NONOTIFY | TPM_WORKAREA | TPM_NOANIMATION | TPM_RIGHTBUTTON | align,
			rtl ? bounds.right : bounds.left, bounds.top, owner, nullptr);
		if (!session->cancelled && command >= 1 && command <= native.actions.size())
			if (const auto& invoke = native.actions[command - 1]) invoke.Invoke();
	}
	catch (...) { Cancel(); }

	winrt::weak_ref<wuxc::MenuFlyoutPresenter> m_Menu;
	std::shared_ptr<TaskbarMenuSession> m_Session;
	wux::DispatcherTimer m_Timer{nullptr};
	std::unique_ptr<TaskbarMenuPreview> m_Preview;
	std::unique_ptr<TaskbarWindowedMenu> m_Windowed;
	ULONGLONG m_Deadline{}, m_MaskedAt{};
};

class TaskbarContextMenus
{
public:
	explicit TaskbarContextMenus(std::wstring path = OverflowSettingsPath()) :
		m_Session(std::make_shared<TaskbarMenuSession>(TaskbarMenuSession{std::move(path)})) {}

	void Add(InstanceHandle handle, const wuxc::MenuFlyoutPresenter& menu) noexcept try
	{
		if (!menu || m_Surfaces.contains(handle)) return;
		auto surface = std::make_shared<TaskbarMenuSurface>(menu, m_Session);
		surface->loaded = menu.Loaded([weak = std::weak_ptr(surface)](auto&&, auto&&) noexcept
		{
			if (const auto current = weak.lock()) current->Queue();
		});
		surface->unloaded = menu.Unloaded([weak = std::weak_ptr(surface)](auto&&, auto&&) noexcept
		{
			if (const auto current = weak.lock()) current->Cancel();
		});
		m_Surfaces.emplace(handle, surface);
		surface->Queue();
	}
	catch (...) {}

	void Remove(InstanceHandle handle) noexcept
	{
		const auto found = m_Surfaces.find(handle);
		if (found == m_Surfaces.end()) return;
		auto surface = std::move(found->second);
		m_Surfaces.erase(found);
		surface->Detach();
	}

	void Refresh() noexcept
	{
		for (const auto& [_, surface] : m_Surfaces) surface->Queue();
	}

	void Restore() noexcept
	{
		for (const auto& [_, surface] : m_Surfaces) surface->Cancel();
		if (m_Session->tracking)
		{
			m_Session->cancelled = true;
			EndMenu();
		}
	}

	~TaskbarContextMenus()
	{
		Restore();
		while (!m_Surfaces.empty()) Remove(m_Surfaces.begin()->first);
	}

private:
	const std::shared_ptr<TaskbarMenuSession> m_Session;
	std::unordered_map<InstanceHandle, std::shared_ptr<TaskbarMenuSurface>> m_Surfaces;
};
}
