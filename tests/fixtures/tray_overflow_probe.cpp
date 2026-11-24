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
	PCSTR section = "Appearance", unsigned ink = 0, PCSTR tint = "814d92bf")
{
	std::ofstream file(path);
	file << '[' << section << "]\nBrush=" << brush << "\nTint=" << tint << "\nAmount=" << (brush == 2 ? 5000 : 1600)
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

static void open_presenter(const wuxc::Primitives::Popup& popup, const wuxc::MenuFlyoutPresenter& menu)
{
	popup.IsOpen(true);
	for (const auto deadline = GetTickCount64() + 1800;
		(!menu.IsLoaded() || menu.ActualHeight() < 1) && GetTickCount64() < deadline; Sleep(5)) pump();
	require(menu.IsLoaded() && menu.ActualHeight() > 1, "popup presenter laid out");
}

struct ContextPointer
{
	wuxc::Primitives::Popup source{nullptr};
	UINT action;
	ULONGLONG deadline;
	bool sent = false, timedOut = false;
};

static ContextPointer* contextPointer;

static void CALLBACK click_context_row(HWND, UINT, UINT_PTR, DWORD)
{
	auto& probe = *contextPointer;
	if (probe.sent) return;
	if (GetTickCount64() >= probe.deadline)
	{
		probe.timedOut = true;
		EndMenu();
		return;
	}
	if (probe.source.IsOpen()) return;
	EnumThreadWindows(GetCurrentThreadId(), [](HWND window, LPARAM data) -> BOOL
	{
		auto& probe = *reinterpret_cast<ContextPointer*>(data);
		wchar_t type[16]{};
		if (!IsWindowVisible(window) || !GetClassNameW(window, type, ARRAYSIZE(type)) ||
			std::wstring_view(type) != L"#32768") return TRUE;
		MENUBARINFO info{sizeof(info)};
		if (!GetMenuBarInfo(window, OBJID_CLIENT, 0, &info)) return TRUE;
		POINT target{};
		for (int position = 0; position < GetMenuItemCount(info.hMenu); ++position)
		{
			const auto id = GetMenuItemID(info.hMenu, position);
			if (id != 1 && id != 2) continue;
			RECT bounds{};
			if (!GetMenuItemRect(nullptr, info.hMenu, position, &bounds)) return TRUE;
			const POINT center{(bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2};
			if (WindowFromPoint(center) != window) return TRUE;
			if (id == probe.action) target = center;
		}
		if (!target.x && !target.y) return TRUE;
		// USER's tracking loop receives screen coordinates while it owns capture.
		const auto pos = MAKELPARAM(target.x, target.y);
		probe.sent = PostMessageW(window, WM_MOUSEMOVE, 0, pos) &&
			PostMessageW(window, WM_LBUTTONDOWN, MK_LBUTTON, pos) &&
			PostMessageW(window, WM_LBUTTONUP, 0, pos);
		return FALSE;
	}, reinterpret_cast<LPARAM>(&probe));
}

static void check_context_menu(const fs::path& ini, unsigned long long started, const wuxc::Button& anchor)
{
	const wuxc::MenuFlyout other;
	const wuxc::MenuFlyoutPresenter menu;
	const wuxc::Primitives::Popup source;
	source.XamlRoot(anchor.XamlRoot());
	source.ShouldConstrainToRootBounds(true);
	source.HorizontalOffset(18);
	source.VerticalOffset(12);
	source.Child(menu);
	const wuxc::MenuFlyoutItem manager, settings, unrelated;
	const wuxc::SymbolIcon icon(wuxc::Symbol::Setting);
	manager.Text(L"任务管理器");
	settings.Text(L"任务栏设置");
	settings.Icon(icon);
	unrelated.Text(L"Other action");
	menu.Items().Append(manager);
	menu.Items().Append(wuxc::MenuFlyoutSeparator());
	menu.Items().Append(settings);
	other.Items().Append(unrelated);
	std::array<unsigned, 2> chosen{};
	manager.Click([&](auto&&, auto&&) { ++chosen[0]; });
	settings.Click([&](auto&&, auto&&) { ++chosen[1]; });
	bigfish::TaskbarContextMenus menus(ini.wstring());
	for (UINT action = 1; action <= 2; ++action)
	{
		write_style(ini, 3, started, "TaskbarMenu", 0, action == 1 ? "ff20252b" : "fff7f8fa");
		open_presenter(source, menu);
		menu.IsHitTestVisible(false);
		require(bigfish::TaskbarMenuPopup(menu) == source && source.IsOpen(), "original taskbar popup identified");
		ContextPointer probe{source, action, GetTickCount64() + 2000};
		contextPointer = &probe;
		const auto timer = SetTimer(nullptr, 0, 20, click_context_row);
		require(timer != 0, "mouse probe timer");
		menus.Add(201, menu);
		require(menu.Opacity() == 0, "original presenter hidden before native popup");
		for (; GetTickCount64() < probe.deadline && !chosen[action - 1]; Sleep(5)) pump();
		KillTimer(nullptr, timer);
		contextPointer = nullptr;
		menus.Remove(201);
		require(probe.sent && !probe.timedOut && !source.IsOpen(), "both rendered rows hit the single native menu");
		require(chosen[action - 1] == 1, "native mouse click invokes the original command");
		require(menu.Opacity() != 0, "original presenter properties restored");
		menu.IsHitTestVisible(true);
	}
	write_style(ini, 1, started + 1, "TaskbarMenu");
	open_presenter(source, menu);
	menus.Add(201, menu);
	require(menu.Opacity() != 0 && source.IsOpen(), "stale owner keeps the native menu");
	menus.Remove(201);
	source.IsOpen(false);
	pump();
	write_style(ini, 2, started, "TaskbarMenu", 2);
	const auto ordinary = opened_menu(other, anchor);
	const auto ordinaryBackground = ordinary.Background();
	const auto ordinaryTheme = ordinary.RequestedTheme();
	menus.Add(202, ordinary);
	require(ordinary.Background() == ordinaryBackground && ordinary.RequestedTheme() == ordinaryTheme,
		"unrelated native menu is unchanged");
	menus.Remove(202);
	other.Hide();
	const auto tint = bigfish::SurfaceTint({3, 0x09f7f7fb, 300});
	const auto dark = bigfish::TaskbarMenuComposite(tint, RGB(15, 24, 36));
	const auto light = bigfish::TaskbarMenuComposite(tint, RGB(240, 245, 250));
	require(bigfish::TaskbarMenuInk(0, dark) == RGB(255, 255, 255) &&
		bigfish::TaskbarMenuInk(0, light) == RGB(0, 0, 0) &&
		bigfish::TaskbarMenuInk(1, dark) == RGB(0, 0, 0) &&
		bigfish::TaskbarMenuInk(2, light) == RGB(255, 255, 255), "auto and manual ink on contrasting backdrops");
}

static void check_windowed_context(const fs::path& ini, unsigned long long started, const wuxc::Button& anchor)
{
	const wuxc::Primitives::Popup source;
	const wuxc::MenuFlyoutPresenter menu;
	source.XamlRoot(anchor.XamlRoot());
	source.ShouldConstrainToRootBounds(false);
	source.HorizontalOffset(85);
	source.VerticalOffset(12);
	source.Child(menu);
	std::array<wuxc::MenuFlyoutItem, 2> items;
	items[0].Text(L"任务管理器");
	items[1].Text(L"任务栏设置");
	std::array<unsigned, 2> hits{};
	for (size_t i = 0; i < items.size(); ++i)
	{
		items[i].Click([&, i](auto&&, auto&&) { ++hits[i]; });
		menu.Items().Append(items[i]);
	}
	bigfish::TaskbarContextMenus menus(ini.wstring());
	for (size_t action = 0; action < items.size(); ++action)
	{
		write_style(ini, 3, started, "TaskbarMenu", 0, action == 0 ? "ff20252b" : "fff7f8fa");
		open_presenter(source, menu);
		const auto deadline=GetTickCount64()+2000;
		// The window owns the screen rectangle while its rows ignore XAML input.
		for (const auto& row : items) row.IsHitTestVisible(false);
		menus.Add(301, menu);
		while (menu.Opacity() == 0 && GetTickCount64() < deadline) { pump(); Sleep(5); }
		const auto popup = bigfish::TaskbarWindowedMenu::Find(bigfish::TaskbarPresenterBounds(menu));
		require(popup && source.IsOpen(), "a windowed XAML popup remains active");
		const auto tint = bigfish::TaskbarMenuInk(0, action == 0 ? RGB(32,37,43) : RGB(247,248,250));
		const auto foreground = items[action].Foreground().try_as<wux::Media::SolidColorBrush>();
		require(foreground && foreground.Color().R == GetRValue(tint), "windowed popup applies automatic ink");
		const auto border = wux::Media::VisualTreeHelper::GetChild(menu,0).try_as<wuxc::Border>();
		require(bool((border ? border.Background() : menu.Background()).try_as<wux::Media::XamlCompositionBrushBase>()),
			"windowed popup keeps the composited material");
		// The accessibility rectangle can be offset on an independently hosted
		// popup. Sample the centers of the two visible rows in the actual HWND.
		RECT bounds{};
		require(GetWindowRect(popup,&bounds), "windowed popup screen rectangle");
		POINT target{(bounds.left+bounds.right)/2,
			bounds.top+(bounds.bottom-bounds.top)*(action == 0 ? 1 : 3)/4};
		const auto window = WindowFromPoint(target);
		require(window && (window == popup || IsChild(popup, window)) && ScreenToClient(window, &target),
			"windowed row center hits its native window");
		const auto point = MAKELPARAM(target.x,target.y);
		require(PostMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,point) &&
			PostMessageW(window,WM_LBUTTONUP,0,point), "windowed row mouse messages");
		while (hits[action] == 0 && GetTickCount64() < deadline) { pump(); Sleep(5); }
		require(hits[action] == 1, "native windowed click runs the original handler once");
		menus.Remove(301);
		source.IsOpen(false);
		pump();
	}
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
		const auto instance = GetModuleHandleW(nullptr);
		WNDCLASSW host{};
		host.lpfnWndProc = DefWindowProcW;
		host.hInstance = instance;
		host.lpszClassName = L"Shell_TrayWnd";
		require(RegisterClassW(&host), "isolated taskbar host class");
		const auto window = CreateWindowW(host.lpszClassName, L"Tray overflow test fixture", WS_OVERLAPPEDWINDOW,
			0, 0, 620, 340, nullptr, nullptr, instance, nullptr);
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
		try { check_context_menu(ini, started, icon); }
		catch (const std::exception& error) { throw std::runtime_error(std::string("Inline context: ") + error.what()); }
		try { check_windowed_context(ini, started, icon); }
		catch (const std::exception& error) { throw std::runtime_error(std::string("Windowed context: ") + error.what()); }
		source.Close();
		DestroyWindow(window);
		std::ofstream(output / "result.json") <<
			R"({"passed":true,"checks":["tray overflow applies all three brushes and restores native state","inline inaccessible XAML menu replaced by one hit-testable native popup","mouse messages reach both original taskbar command handlers","old presenter is masked before switching and restored after closing","stale settings and unrelated flyouts keep the original menu","automatic and manual ink on light and dark backgrounds","windowed XAML taskbar popup receives native mouse clicks on both rows and keeps its composited glass"]})";
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
