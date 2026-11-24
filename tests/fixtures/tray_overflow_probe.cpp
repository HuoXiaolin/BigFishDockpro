#include <windows.h>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <windows.ui.xaml.hosting.desktopwindowxamlsource.h>
#include "taskbar_context_menu.hpp"
#include "undefgetcurrenttime.h"
#include <winrt/Windows.UI.Xaml.Automation.Provider.h>
#include <winrt/Windows.UI.Xaml.Controls.Primitives.h>
#include "redefgetcurrenttime.h"

namespace fs = std::filesystem;

static void require(bool success, const char* message)
{
	if (!success) throw std::runtime_error(message);
}

static void write_style(const fs::path& path, unsigned brush, unsigned long long started,
	PCSTR section = "Appearance", unsigned ink = 0)
{
	std::ofstream file(path);
	file << '[' << section << "]\nBrush=" << brush << "\nTint=814d92bf\nAmount=" << (brush == 2 ? 5000 : 1600)
	     << "\nOwnerPid=" << GetCurrentProcessId() << "\nOwnerStarted=" << started << "\nInk=" << ink
	     << "\nEdgeAlpha=61\n";
	require(bool(file), "fixture settings write");
}

static void pump()
{
	MSG msg{};
	while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE))
	{
		TranslateMessage(&msg);
		DispatchMessageW(&msg);
	}
}

static wuxc::MenuFlyoutPresenter opened_menu(const wuxc::MenuFlyout& flyout, const wuxc::Button& anchor)
{
	flyout.ShowAt(anchor);
	for (const auto deadline = GetTickCount64() + 2000; GetTickCount64() < deadline;)
	{
		pump();
		for (const auto& popup : wux::Media::VisualTreeHelper::GetOpenPopupsForXamlRoot(anchor.XamlRoot()))
			if (const auto presenter = popup.Child().try_as<wuxc::MenuFlyoutPresenter>();
				presenter && presenter.IsLoaded()) return presenter;
		Sleep(5);
	}
	throw std::runtime_error("native taskbar-style popup did not open");
}

static void check_context_menu(const fs::path& ini, unsigned long long started, const wuxc::Button& anchor)
{
	const wuxc::MenuFlyout flyout, other;
	const wuxc::MenuFlyoutItem manager, settings, unrelated;
	const wuxc::SymbolIcon icon(wuxc::Symbol::Setting);
	manager.Text(L"任务管理器");
	settings.Text(L"任务栏设置");
	settings.Icon(icon);
	unrelated.Text(L"Other action");
	flyout.Items().Append(manager);
	flyout.Items().Append(wuxc::MenuFlyoutSeparator());
	flyout.Items().Append(settings);
	other.Items().Append(unrelated);
	bool chosen = false;
	settings.Click([&](auto&&, auto&&) { chosen = true; });
	bigfish::TaskbarContextMenus menus(ini.wstring());
	write_style(ini, 3, started, "TaskbarMenu", 2);
	const auto menu = opened_menu(flyout, anchor);
	const auto corner = menu.CornerRadius();
	const auto originalTheme = menu.RequestedTheme();
	const auto originalInk = settings.ReadLocalValue(wuxc::Control::ForegroundProperty());
	const auto border = wux::Media::VisualTreeHelper::GetChild(menu, 0).try_as<wuxc::Border>();
	const auto originalBrush = border ? border.Background() : menu.Background();
	menus.Add(201, menu);
	const auto brush = (border ? border.Background() : menu.Background()).try_as<wux::Media::XamlCompositionBrushBase>();
	require(brush && brush.FallbackColor().B == 0xbf, "context menu uses the selected notification blur");
	require(menu.CornerRadius().TopLeft == 12 && menu.RequestedTheme() == wux::ElementTheme::Dark,
		"context menu corners and dark theme applied");
	require(settings.Foreground().as<wux::Media::SolidColorBrush>().Color().R == 255 && settings.Foreground() == icon.Foreground(),
		"white text and menu glyph use the same contrast");
	write_style(ini, 1, started, "TaskbarMenu", 1);
	menus.Refresh();
	require(settings.Foreground().as<wux::Media::SolidColorBrush>().Color().R == 0, "live black foreground");
	write_style(ini, 1, started + 1, "TaskbarMenu", 1);
	menus.Refresh();
	require(menu.RequestedTheme() == originalTheme && menu.CornerRadius().TopLeft == corner.TopLeft &&
		settings.ReadLocalValue(wuxc::Control::ForegroundProperty()) == originalInk &&
		(border ? border.Background() : menu.Background()) == originalBrush, "restore menu when owner is stale");
	write_style(ini, 1, started, "TaskbarMenu", 1);
	menus.Refresh();
	require(menu.RequestedTheme() == wux::ElementTheme::Light, "styling enabled while invoking the menu");
	const wux::Automation::Peers::MenuFlyoutItemAutomationPeer peer(settings);
	peer.as<wux::Automation::Provider::IInvokeProvider>().Invoke();
	pump();
	require(chosen && manager.IsEnabled() && settings.IsEnabled(), "native command remains actionable");
	flyout.Hide();
	pump();
	menus.Remove(201);
	write_style(ini, 2, started, "TaskbarMenu", 2);
	const auto ordinary = opened_menu(other, anchor);
	const auto ordinaryBackground = ordinary.Background();
	const auto ordinaryTheme = ordinary.RequestedTheme();
	menus.Add(202, ordinary);
	require(ordinary.Background() == ordinaryBackground && ordinary.RequestedTheme() == ordinaryTheme,
		"unrelated native menu is unchanged");
	menus.Remove(202);
	other.Hide();
	const auto tint = bigfish::SurfaceTint({3, 0x004d92bf, 1600});
	require(bigfish::TaskbarMenuLuminance(tint, RGB(0, 0, 0)) == 0 &&
		bigfish::TaskbarMenuLuminance(tint, RGB(255, 255, 255)) > .99, "transparent contrast follows the backdrop");
}

int wmain(int argc, wchar_t** argv)
{
	if (argc < 2) return 90;
	wchar_t expected[256]{}, actual[256]{};
	DWORD needed = 0;
	BOOL receivesInput = TRUE;
	if (!GetEnvironmentVariableW(L"FISHDOCK_TEST_DESKTOP", expected, ARRAYSIZE(expected))) return 90;
	const auto isolated = OpenDesktopW(expected, 0, FALSE, 0x01ff);
	if (!isolated || !SetThreadDesktop(isolated)) return 90;
	const auto desktop = GetThreadDesktop(GetCurrentThreadId());
	if (!GetUserObjectInformationW(desktop, UOI_NAME, actual, sizeof(actual), &needed) ||
		wcscmp(expected, actual) ||
		!GetUserObjectInformationW(desktop, 6, &receivesInput, sizeof(receivesInput), &needed) ||
		receivesInput) return 90;
	const fs::path output(argv[argc - 1]);
	try
	{
		winrt::init_apartment(winrt::apartment_type::single_threaded);
		const auto manager = wuxh::WindowsXamlManager::InitializeForCurrentThread();
		const auto window = CreateWindowW(L"STATIC", L"Tray overflow test fixture", WS_OVERLAPPEDWINDOW,
			0, 0, 340, 230, nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
		require(window != nullptr, "fixture host window");
		const wuxh::DesktopWindowXamlSource source;
		const auto native = source.as<IDesktopWindowXamlSourceNative>();
		winrt::check_hresult(native->AttachToWindow(window));
		HWND child = nullptr;
		winrt::check_hresult(native->get_WindowHandle(&child));
		SetWindowPos(child, nullptr, 0, 0, 280, 164, SWP_NOZORDER | SWP_SHOWWINDOW);

		FILETIME created{}, exit{}, kernel{}, user{};
		require(GetProcessTimes(GetCurrentProcess(), &created, &exit, &kernel, &user), "fixture owner times");
		const auto started = (static_cast<unsigned long long>(created.dwHighDateTime) << 32) | created.dwLowDateTime;
		const auto ini = output / L"tray-overflow.ini";
		const auto path = ini.wstring();
		write_style(ini, 1, started);
		bigfish::TrayOverflow style(path);
		const wuxc::Grid root;
		const wuxc::Border surface, ordinary;
		const wuxc::Button icon;
		const auto original = wux::Media::SolidColorBrush({255, 45, 49, 52});
		const wux::CornerRadius corners{8, 8, 8, 8};
		surface.Name(L"OverflowFlyoutBackgroundBorder");
		surface.CornerRadius(corners);
		surface.Background(original);
		ordinary.Name(L"BackgroundBorder");
		ordinary.Background(original);
		icon.Content(winrt::box_value(L"Icon"));
		root.Children().Append(ordinary);
		root.Children().Append(surface);
		root.Children().Append(icon);
		require(bigfish::TrayOverflow::Matches(winrt::name_of<wuxc::Border>(), surface.Name()), "native overflow target name");
		require(!bigfish::TrayOverflow::Matches(winrt::name_of<wuxc::Border>(), ordinary.Name()), "ordinary border excluded");
		style.Add(101, surface);
		style.Add(102, ordinary);
		source.Content(root);
		ShowWindow(window, SW_SHOWNOACTIVATE);
		for (const auto deadline = GetTickCount64() + 4000; GetTickCount64() < deadline && surface.Background() == original;)
		{
			pump();
			Sleep(5);
		}
		require(surface.IsLoaded(), "loaded overflow");
		const auto solid = surface.Background().try_as<wux::Media::SolidColorBrush>();
		require(solid && solid.Color().A == 0x81 && solid.Color().R == 0x4d, "first-open tint");
		require(ordinary.Background() == original && surface.CornerRadius().TopLeft == 8 &&
				icon.IsHitTestVisible() && root.Children().Size() == 3, "sibling, geometry and icon preserved");

		write_style(ini, 2, started);
		style.Refresh();
		const auto acrylic = surface.Background().try_as<wux::Media::AcrylicBrush>();
		require(acrylic && acrylic.TintOpacity() == .5 && acrylic.FallbackColor().A == 0x81, "live acrylic");
		write_style(ini, 3, started);
		style.Refresh();
		const auto blur = surface.Background().try_as<wux::Media::XamlCompositionBrushBase>();
		require(blur && blur.FallbackColor().B == 0xbf, "live composition blur");
		style.Restore();
		require(surface.Background() == original, "worker exit restore");
		style.Refresh();
		require(surface.Background() != original, "worker resumes");
		write_style(ini, 1, started + 1);
		style.Refresh();
		require(surface.Background() == original, "stale owner rejected");
		write_style(ini, 1, started);
		style.Refresh();
		style.Remove(101);
		require(surface.Background() == original, "unloaded border restored");
		check_context_menu(ini, started, icon);
		source.Close();
		DestroyWindow(window);
		std::ofstream(output / "result.json") <<
			R"({"passed":true,"checks":["tray overflow applies all three brushes and restores native state","native two-command menu accepts tint blur corners and black or white text and glyphs","same native command remains actionable","disabled or stale settings restore original properties","unrelated flyouts excluded","transparent contrast follows the sampled background"]})";
		return 0;
	}
	catch (const std::exception& error)
	{
		std::ofstream(output / "failure.txt") << error.what();
	}
	catch (const winrt::hresult_error& error)
	{
		std::ofstream(output / "failure.txt") << winrt::to_string(error.message());
	}
	return 1;
}
