using System;
using System.Device.Location;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Windows.Devices.Geolocation;
using Windows.Security.Authorization.AppCapabilityAccess;

internal static class WeatherLocation {
    internal static object Read() {
        try { return ReadWindowsRuntime(); }
        catch (TypeLoadException) { return ReadLegacy(); }
        catch (COMException error) when ((uint)error.HResult == 0x80040154) { return ReadLegacy(); }
        catch (UnauthorizedAccessException) { return new { status = "permission" }; }
        catch (TimeoutException) { return new { status = "timeout" }; }
        catch (COMException error) when ((uint)error.HResult == 0x800705B4) { return new { status = "timeout" }; }
        catch (COMException) { return new { status = "unavailable" }; }
    }

    // Check existing desktop consent before requesting a position from the Windows provider.
    [MethodImpl(MethodImplOptions.NoInlining)]
    static object ReadWindowsRuntime() {
        var access = AppCapability.Create("location").CheckAccess();
        if (access != AppCapabilityAccessStatus.Allowed)
            return new { status = "permission" };
        var locator = new Geolocator { DesiredAccuracy = PositionAccuracy.Default };
        var result = locator.GetGeopositionAsync(TimeSpan.FromMinutes(30), TimeSpan.FromSeconds(12)).GetAwaiter().GetResult();
        var position = result.Coordinate.Point.Position;
        return RoundedPosition(position.Latitude, position.Longitude);
    }

    static object ReadLegacy() {
        using (var watcher = new GeoCoordinateWatcher(GeoPositionAccuracy.Default)) {
            bool ready = watcher.TryStart(true, TimeSpan.FromSeconds(7));
            if (watcher.Permission == GeoPositionPermission.Denied)
                return new { status = "permission" };
            if (!ready)
                return new { status = "timeout" };
            GeoCoordinate position = watcher.Position.Location;
            if (position == null || position.IsUnknown)
                return new { status = "unavailable" };
            return RoundedPosition(position.Latitude, position.Longitude);
        }
    }

    static object RoundedPosition(double latitude, double longitude) {
        return new { status = "ready", latitude = Math.Round(latitude, 2), longitude = Math.Round(longitude, 2) };
    }
}
