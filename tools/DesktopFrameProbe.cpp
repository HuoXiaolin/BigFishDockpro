// Reports desktop image update counts and elapsed time. No surface is mapped or copied.
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>

using Microsoft::WRL::ComPtr;

static ComPtr<IDXGIOutputDuplication> open_output(HMONITOR monitor) {
    ComPtr<IDXGIFactory1> factory;
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory)))) return {};
    ComPtr<IDXGIAdapter1> adapter;
    for (UINT i = 0; SUCCEEDED(factory->EnumAdapters1(i, adapter.ReleaseAndGetAddressOf())); ++i) {
        ComPtr<IDXGIOutput> output;
        for (UINT j = 0; SUCCEEDED(adapter->EnumOutputs(j, output.ReleaseAndGetAddressOf())); ++j) {
            DXGI_OUTPUT_DESC desc{};
            if (FAILED(output->GetDesc(&desc)) || !desc.AttachedToDesktop || desc.Monitor != monitor) continue;
            ComPtr<IDXGIOutput1> source;
            ComPtr<ID3D11Device> device;
            ComPtr<IDXGIOutputDuplication> duplication;
            if (SUCCEEDED(output.As(&source)) &&
                SUCCEEDED(D3D11CreateDevice(adapter.Get(), D3D_DRIVER_TYPE_UNKNOWN, nullptr,
                    D3D11_CREATE_DEVICE_SINGLETHREADED | D3D11_CREATE_DEVICE_BGRA_SUPPORT,
                    nullptr, 0, D3D11_SDK_VERSION, &device, nullptr, nullptr)) &&
                SUCCEEDED(source->DuplicateOutput(device.Get(), &duplication))) return duplication;
            return {};
        }
    }
    return {};
}

struct DisplayTarget { const char* name; HMONITOR monitor; };

static BOOL CALLBACK match_monitor(HMONITOR monitor, HDC, LPRECT, LPARAM context) {
    auto& target = *reinterpret_cast<DisplayTarget*>(context);
    MONITORINFOEXA info{};
    info.cbSize = sizeof(info);
    if (!GetMonitorInfoA(monitor, &info) || _stricmp(info.szDevice, target.name) != 0) return TRUE;
    target.monitor = monitor;
    return FALSE;
}

static HMONITOR selected_monitor(const char* display) {
    if (display) {
        DisplayTarget target{display, nullptr};
        EnumDisplayMonitors(nullptr, nullptr, match_monitor, reinterpret_cast<LPARAM>(&target));
        return target.monitor;
    }
    HWND window = GetForegroundWindow();
    return window ? MonitorFromWindow(window, MONITOR_DEFAULTTOPRIMARY) :
                    MonitorFromPoint(POINT{0, 0}, MONITOR_DEFAULTTOPRIMARY);
}

int main(int argc, char** argv) {
    const char* display = argc >= 3 && std::strcmp(argv[1], "--display") == 0 ? argv[2] : nullptr;
    if (argc > (display ? 4 : 2)) return 1;
    const unsigned limit = argc == (display ? 4 : 2) ? std::strtoul(argv[argc - 1], nullptr, 10) : 0;
    LARGE_INTEGER frequency{}, previous{};
    if (!QueryPerformanceFrequency(&frequency)) return 1;
    HMONITOR monitor = nullptr;
    ComPtr<IDXGIOutputDuplication> duplication;
    bool held = false;
    for (unsigned samples = 0; !limit || samples < limit; ++samples) {
        HMONITOR active = display && duplication ? monitor : selected_monitor(display);
        if (!duplication || active != monitor) {
            if (held) duplication->ReleaseFrame();
            duplication.Reset();
            held = false;
            monitor = active;
            duplication = open_output(monitor);
            if (!duplication) return 2;
            // Discard the initial snapshot, which is not a new presented frame.
            DXGI_OUTDUPL_FRAME_INFO initial{};
            ComPtr<IDXGIResource> ignored;
            HRESULT hr = duplication->AcquireNextFrame(500, &initial, &ignored);
            held = SUCCEEDED(hr);
            if (!held && hr != DXGI_ERROR_WAIT_TIMEOUT) return 3;
            QueryPerformanceCounter(&previous);
        }
        // A nonblocking acquisition immediately after ReleaseFrame can miss
        // a whole interval; the next frame then carries both intervals' counts.
        // Collect into a one-second window and let DXGI wait for the next image.
        LARGE_INTEGER now{};
        unsigned frames = 0;
        do {
            if (held) {
                Sleep(40);
                if (FAILED(duplication->ReleaseFrame())) return 3;
            }
            DXGI_OUTDUPL_FRAME_INFO info{};
            ComPtr<IDXGIResource> unused_surface;
            HRESULT hr = duplication->AcquireNextFrame(100, &info, &unused_surface);
            held = SUCCEEDED(hr);
            if (!held && hr != DXGI_ERROR_WAIT_TIMEOUT) return 3;
            if (held && info.LastPresentTime.QuadPart) frames += info.AccumulatedFrames;
            QueryPerformanceCounter(&now);
        } while (now.QuadPart - previous.QuadPart < frequency.QuadPart);
        const auto microseconds = 1000000ULL * (now.QuadPart - previous.QuadPart) / frequency.QuadPart;
        if (std::printf("%u %llu\n", frames, microseconds) < 0 || std::fflush(stdout) != 0) return 0;
        previous = now;
    }
    if (held) duplication->ReleaseFrame();
    return 0;
}
