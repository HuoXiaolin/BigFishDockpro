#include <windows.h>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <windows.ui.xaml.hosting.desktopwindowxamlsource.h>
#include "taskbar_overflow.hpp"
#include <winrt/Windows.Foundation.Collections.h>

namespace fs = std::filesystem;

static void require(bool success, const char* message)
{
	if (!success) throw std::runtime_error(message);
}

static void write_style(const fs::path& path, unsigned brush, unsigned long long started)
{
	std::ofstream file(path);
	file << "[Appearance]\nBrush=" << brush << "\nTint=814d92bf\nAmount=" << (brush == 2 ? 5000 : 1600)
	     << "\nOwnerPid=" << GetCurrentProcessId() << "\nOwnerStarted=" << started << '\n';
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
		source.Close();
		DestroyWindow(window);
		std::ofstream(output / "result.json") <<
			R"({"passed":true,"checks":["first synthetic overflow open has selected tint","solid acrylic and blur apply to the same native Border","icon and corner geometry preserved","worker exit stale owner and unload restore the native brush"]})";
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
