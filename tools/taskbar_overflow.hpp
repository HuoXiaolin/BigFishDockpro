#pragma once
#include <cwchar>
#include <memory>
#include <optional>
#include <unordered_map>
#include <xamlOM.h>
#include "XamlBlurBrush.h"
#include <winrt/Windows.UI.Core.h>
#include <winrt/Windows.UI.Xaml.Controls.h>
#include <winrt/Windows.UI.Xaml.Hosting.h>
#include "redefgetcurrenttime.h"
#include <wil/resource.h>
#include <wil/win32_helpers.h>

namespace bigfish
{
struct OverflowStyle
{
	unsigned mode;
	unsigned argb;
	unsigned amount;

	bool operator==(const OverflowStyle&) const = default;
};

inline std::wstring OverflowSettingsPath()
{
	std::wstring path(32768, L'\0');
	const auto length = GetModuleFileNameW(wil::GetModuleInstanceHandle(), path.data(), static_cast<DWORD>(path.size()));
	if (!length || length >= path.size()) return {};
	path.resize(length);
	path.resize(path.find_last_of(L'\\') + 1);
	return path + L"tray-overflow.ini";
}

inline std::optional<OverflowStyle> ReadOverflowStyle(const std::wstring& path, PCWSTR section = L"Appearance")
{
	if (path.empty()) return std::nullopt;
	const auto mode = GetPrivateProfileIntW(section, L"Brush", 0, path.c_str());
	const auto pid = GetPrivateProfileIntW(section, L"OwnerPid", 0, path.c_str());
	if (mode < 1 || mode > 3 || !pid) return std::nullopt;
	const wil::unique_process_handle owner(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, pid));
	FILETIME created{}, exit{}, kernel{}, user{};
	if (!owner || WaitForSingleObject(owner.get(), 0) != WAIT_TIMEOUT ||
		!GetProcessTimes(owner.get(), &created, &exit, &kernel, &user)) return std::nullopt;
	wchar_t text[32]{};
	GetPrivateProfileStringW(section, L"OwnerStarted", L"", text, ARRAYSIZE(text), path.c_str());
	const auto started = (static_cast<unsigned long long>(created.dwHighDateTime) << 32) | created.dwLowDateTime;
	if (std::wcstoull(text, nullptr, 10) != started) return std::nullopt;
	if (GetPrivateProfileStringW(section, L"Tint", L"", text, ARRAYSIZE(text), path.c_str()) != 8)
		return std::nullopt;
	wchar_t* end = nullptr;
	const auto argb = std::wcstoul(text, &end, 16);
	if (end != text + 8) return std::nullopt;
	const auto amount = GetPrivateProfileIntW(section, L"Amount", 0, path.c_str());
	if (amount > (mode == 2 ? 10000u : 5000u)) return std::nullopt;
	return OverflowStyle{mode, argb, amount};
}

inline winrt::Windows::UI::Color SurfaceTint(const OverflowStyle& style)
{
	return {static_cast<uint8_t>(style.argb >> 24), static_cast<uint8_t>(style.argb >> 16),
		static_cast<uint8_t>(style.argb >> 8), static_cast<uint8_t>(style.argb)};
}

inline wux::Media::Brush MakeSurfaceBrush(const wux::UIElement& target, const OverflowStyle& style)
{
	const auto tint = SurfaceTint(style);
	if (style.mode == 2)
	{
		wux::Media::AcrylicBrush brush;
		brush.BackgroundSource(wux::Media::AcrylicBackgroundSource::Backdrop);
		brush.TintColor({255, tint.R, tint.G, tint.B});
		brush.TintOpacity(style.amount / 10000.0);
		brush.TintLuminosityOpacity(winrt::box_value(0.0).as<wf::IReference<double>>());
		brush.FallbackColor(tint);
		return brush;
	}
	if (style.mode == 3)
	{
		auto compositor = wuxh::ElementCompositionPreview::GetElementVisual(target).Compositor();
		auto brush = winrt::make<XamlBlurBrush>(std::move(compositor), style.amount / 100.f,
			wfn::float4{tint.R / 255.f, tint.G / 255.f, tint.B / 255.f, tint.A / 255.f});
		brush.FallbackColor(tint);
		return brush;
	}
	return wux::Media::SolidColorBrush(tint);
}

class OverflowSurface
{
public:
	explicit OverflowSurface(const wuxc::Border& border) : m_Border(winrt::make_weak(border)) {}

	void Apply(const std::optional<OverflowStyle>& style) noexcept try
	{
		const auto border = m_Border.get();
		if (!border || !border.Dispatcher().HasThreadAccess()) return;
		const auto current = border.Background();
		const auto property = wuxc::Border::BackgroundProperty();
		const bool owned = m_Applied && current == m_Applied;
		if (!style)
		{
			if (owned)
			{
				try
				{
					if (m_Local == wux::DependencyProperty::UnsetValue()) border.ClearValue(property);
					else border.SetValue(property, m_Local);
				}
				catch (const winrt::hresult_error&) { border.Background(m_Original); }
			}
			m_Applied = m_Original = nullptr;
			m_Local = nullptr;
			m_Style.reset();
			return;
		}
		if (owned && m_Style == style) return;
		const auto brush = MakeSurfaceBrush(border, *style);
		if (!owned)
		{
			m_Local = border.ReadLocalValue(property);
			m_Original = current;
		}
		border.Background(brush);
		m_Applied = brush;
		m_Style = style;
	}
	catch (...) {}

	winrt::event_token loaded{};

	void Detach() noexcept try
	{
		Apply(std::nullopt);
		if (const auto border = m_Border.get()) border.Loaded(loaded);
	}
	catch (...) {}

private:
	winrt::weak_ref<wuxc::Border> m_Border;
	wf::IInspectable m_Local{nullptr};
	wux::Media::Brush m_Original{nullptr}, m_Applied{nullptr};
	std::optional<OverflowStyle> m_Style;
};

class TrayOverflow
{
public:
	explicit TrayOverflow(std::wstring path = OverflowSettingsPath()) : m_Path(std::move(path)) {}

	static bool Matches(std::wstring_view type, std::wstring_view name)
	{
		return type == winrt::name_of<wuxc::Border>() && name == L"OverflowFlyoutBackgroundBorder";
	}

	void Add(InstanceHandle handle, const wuxc::Border& border) noexcept try
	{
		if (m_Surfaces.contains(handle) || !border || border.Name() != L"OverflowFlyoutBackgroundBorder") return;
		auto surface = std::make_shared<OverflowSurface>(border);
		const auto path = m_Path;
		surface->loaded = border.Loaded([weak = std::weak_ptr(surface), path](auto&&, auto&&) noexcept
		{
			try
			{
				if (const auto current = weak.lock()) current->Apply(ReadOverflowStyle(path));
			}
			catch (...) {}
		});
		m_Surfaces.emplace(handle, surface);
		if (border.IsLoaded()) surface->Apply(ReadOverflowStyle(path));
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
		const auto style = ReadOverflowStyle(m_Path);
		for (const auto& [_, surface] : m_Surfaces) surface->Apply(style);
	}
	catch (...) {}

	void Restore() noexcept
	{
		for (const auto& [_, surface] : m_Surfaces) surface->Apply(std::nullopt);
	}

	~TrayOverflow()
	{
		while (!m_Surfaces.empty()) Remove(m_Surfaces.begin()->first);
	}

private:
	const std::wstring m_Path;
	std::unordered_map<InstanceHandle, std::shared_ptr<OverflowSurface>> m_Surfaces;
};
}
