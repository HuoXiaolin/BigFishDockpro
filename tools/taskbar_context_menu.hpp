#pragma once
#include "taskbar_overflow.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <shlwapi.h>
#include "undefgetcurrenttime.h"
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.UI.Xaml.Automation.Peers.h>
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

inline double TaskbarMenuLuminance(winrt::Windows::UI::Color tint, COLORREF backdrop) noexcept
{
	const auto linear = [](double value) {
		return value <= .04045 ? value / 12.92 : std::pow((value + .055) / 1.055, 2.4);
	};
	const auto channel = [&](unsigned color, unsigned behind) {
		const double alpha = tint.A / 255.0;
		return linear((color * alpha + behind * (1 - alpha)) / 255.0);
	};
	return .2126 * channel(tint.R, GetRValue(backdrop)) + .7152 * channel(tint.G, GetGValue(backdrop)) +
		.0722 * channel(tint.B, GetBValue(backdrop));
}

inline bool TaskbarMenuDark(const wuxc::MenuFlyoutPresenter& menu, winrt::Windows::UI::Color tint)
{
	const auto luminance = [&]() noexcept {
		return TaskbarMenuLuminance({255, tint.R, tint.G, tint.B}, 0);
	};
	constexpr double threshold = .1791287847; // Equal contrast for black and white.
	if (tint.A == 255) return luminance() < threshold;
	const wux::Automation::Peers::FrameworkElementAutomationPeer peer(menu);
	const auto face = peer.GetBoundingRectangle();
	if (face.Width < 20 || face.Height < 20) return luminance() < threshold;
	const RECT bounds{std::lround(face.X), std::lround(face.Y), std::lround(face.X + face.Width),
		std::lround(face.Y + face.Height)};
	MONITORINFO monitor{sizeof(monitor)};
	if (!GetMonitorInfoW(MonitorFromRect(&bounds, MONITOR_DEFAULTTONULL), &monitor))
		return luminance() < threshold;
	std::array<double, 12> samples{};
	size_t count = 0;
	if (const HDC dc = GetDC(nullptr))
	{
		const auto add = [&](LONG x, LONG y) {
			if (!PtInRect(&monitor.rcWork, {x, y})) return;
			const auto pixel = GetPixel(dc, x, y);
			if (pixel != CLR_INVALID) samples[count++] = TaskbarMenuLuminance(tint, pixel);
		};
		// Read just outside the flyout so its own foreground and fill are absent.
		for (LONG fraction = 1; fraction <= 3; ++fraction)
		{
			const auto x = bounds.left + (bounds.right - bounds.left) * fraction / 4;
			const auto y = bounds.top + (bounds.bottom - bounds.top) * fraction / 4;
			add(x, bounds.top - 4);
			add(x, bounds.bottom + 4);
			add(bounds.left - 4, y);
			add(bounds.right + 4, y);
		}
		ReleaseDC(nullptr, dc);
	}
	if (!count) return luminance() < threshold;
	const auto middle = samples.begin() + count / 2;
	std::nth_element(samples.begin(), middle, samples.begin() + count);
	return *middle < threshold;
}

// Retain native/theme values so disabled styling restores this same popup instance.
class MenuValue
{
public:
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

class TaskbarMenuSurface
{
public:
	explicit TaskbarMenuSurface(const wuxc::MenuFlyoutPresenter& menu) : m_Menu(winrt::make_weak(menu)) {}

	void Apply(const std::optional<TaskbarMenuStyle>& style) noexcept try
	{
		const auto menu = m_Menu.get();
		if (!menu || !menu.Dispatcher().HasThreadAccess() || !menu.IsLoaded()) return;
		HIGHCONTRASTW contrast{sizeof(contrast)};
		if (!style || (SystemParametersInfoW(SPI_GETHIGHCONTRAST, sizeof(contrast), &contrast, 0) &&
			(contrast.dwFlags & HCF_HIGHCONTRASTON)))
		{
			Restore();
			return;
		}
		if (m_Style == style) return;
		const auto rows = TaskbarMenuRows(menu);
		if (!rows[0] || !rows[1]) return;
		if (style->ink == 0 && !m_AutoDark) m_AutoDark = TaskbarMenuDark(menu, SurfaceTint(style->brush));
		const bool dark = style->ink ? style->ink == 2 : *m_AutoDark;
		const auto ink = wux::Media::SolidColorBrush(dark ? winrt::Windows::UI::Color{255, 255, 255, 255} :
			winrt::Windows::UI::Color{255, 0, 0, 0});
		const auto corners = winrt::box_value(wux::CornerRadius{12, 12, 12, 12});
		m_Theme.Set(menu, wux::FrameworkElement::RequestedThemeProperty(),
			winrt::box_value(dark ? wux::ElementTheme::Dark : wux::ElementTheme::Light));
		m_Corners.Set(menu, wuxc::Control::CornerRadiusProperty(), corners);
		m_Foreground.Set(menu, wuxc::Control::ForegroundProperty(), ink);
		const auto border = wux::Media::VisualTreeHelper::GetChildrenCount(menu)
			? wux::Media::VisualTreeHelper::GetChild(menu, 0).try_as<wuxc::Border>() : nullptr;
		const auto brush = MakeSurfaceBrush(menu, style->brush);
		const auto edge = MakeEdge(*style);
		if (border)
		{
			m_BorderCorners.Set(border, wuxc::Border::CornerRadiusProperty(), corners);
			m_Background.Set(border, wuxc::Border::BackgroundProperty(), brush);
			m_Edge.Set(border, wuxc::Border::BorderBrushProperty(), edge);
		}
		else
		{
			m_BorderCorners.Restore();
			m_Background.Set(menu, wuxc::Control::BackgroundProperty(), brush);
			m_Edge.Set(menu, wuxc::Control::BorderBrushProperty(), edge);
		}
		for (size_t i = 0; i < rows.size(); ++i)
		{
			m_Rows[i].Set(rows[i], wuxc::Control::ForegroundProperty(), ink);
			if (const auto icon = rows[i].Icon()) m_Icons[i].Set(icon, wuxc::IconElement::ForegroundProperty(), ink);
		}
		m_Style = style;
	}
	catch (...) { Restore(); }

	void Restore() noexcept
	{
		for (auto& icon : m_Icons) icon.Restore();
		for (auto& row : m_Rows) row.Restore();
		m_Background.Restore();
		m_Edge.Restore();
		m_BorderCorners.Restore();
		m_Corners.Restore();
		m_Foreground.Restore();
		m_Theme.Restore();
		m_Style.reset();
		m_AutoDark.reset();
	}

	void Detach() noexcept try
	{
		Restore();
		if (const auto menu = m_Menu.get())
		{
			menu.Loaded(loaded);
			menu.Unloaded(unloaded);
		}
	}
	catch (...) {}

	winrt::event_token loaded{}, unloaded{};

private:
	static wux::Media::Brush MakeEdge(const TaskbarMenuStyle& style)
	{
		if (!style.flowing)
			return wux::Media::SolidColorBrush({static_cast<uint8_t>(style.edgeAlpha), 255, 255, 255});
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

	winrt::weak_ref<wuxc::MenuFlyoutPresenter> m_Menu;
	MenuValue m_Theme, m_Corners, m_BorderCorners, m_Background, m_Edge, m_Foreground;
	std::array<MenuValue, 2> m_Rows, m_Icons;
	std::optional<TaskbarMenuStyle> m_Style;
	std::optional<bool> m_AutoDark;
};

class TaskbarContextMenus
{
public:
	explicit TaskbarContextMenus(std::wstring path = OverflowSettingsPath()) : m_Path(std::move(path)) {}

	void Add(InstanceHandle handle, const wuxc::MenuFlyoutPresenter& menu) noexcept try
	{
		if (!menu || m_Surfaces.contains(handle)) return;
		auto surface = std::make_shared<TaskbarMenuSurface>(menu);
		const auto path = m_Path;
		surface->loaded = menu.Loaded([weak = std::weak_ptr(surface), path](auto&&, auto&&) noexcept
		{
			try
			{
				if (const auto current = weak.lock()) current->Apply(ReadTaskbarMenuStyle(path));
			}
			catch (...) {}
		});
		surface->unloaded = menu.Unloaded([weak = std::weak_ptr(surface)](auto&&, auto&&) noexcept
		{
			if (const auto current = weak.lock()) current->Restore();
		});
		m_Surfaces.emplace(handle, surface);
		if (menu.IsLoaded()) surface->Apply(ReadTaskbarMenuStyle(path));
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

	void Refresh() noexcept try
	{
		if (m_Surfaces.empty()) return;
		const auto style = ReadTaskbarMenuStyle(m_Path);
		for (const auto& [_, surface] : m_Surfaces) surface->Apply(style);
	}
	catch (...) {}

	void Restore() noexcept
	{
		for (const auto& [_, surface] : m_Surfaces) surface->Restore();
	}

	~TaskbarContextMenus()
	{
		while (!m_Surfaces.empty()) Remove(m_Surfaces.begin()->first);
	}

private:
	const std::wstring m_Path;
	std::unordered_map<InstanceHandle, std::shared_ptr<TaskbarMenuSurface>> m_Surfaces;
};
}
