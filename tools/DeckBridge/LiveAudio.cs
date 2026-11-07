using BrimDeck.Core;
using BrimDeck.Native;
using NAudio.CoreAudioApi;
using NAudio.CoreAudioApi.Interfaces;

// A live player can resume its own transport immediately. Hold its unique audio
// session muted until the user resumes or the bridge shuts down.
internal sealed class LiveAudio : IDisposable
{
    private string? trackId;
    private MMDevice? device;
    private AudioSessionControl? session;

    public static bool CanPause(MediaTrack track, MediaAppOwner? owner) =>
        track.Id.StartsWith("system:", StringComparison.Ordinal) && !track.HasTimeline &&
        track.State == MediaState.Playing && owner is not null &&
        (owner.ProcessId is > 0 || owner.AppId.Length > 0 || owner.ProcessName.Length > 0);

    public bool IsMuted(string id) => id == trackId;

    public bool TryPause(string id, MediaAppOwner owner)
    {
        if (session is not null) return false;
        AudioSessionControl? match = null;
        MMDevice? matchDevice = null;
        try
        {
            using var enumerator = new MMDeviceEnumerator();
            var devices = enumerator.EnumerateAudioEndPoints(DataFlow.Render, DeviceState.Active);
            for (int index = 0; index < devices.Count; index++)
            {
                var endpoint = devices[index];
                try
                {
                    var sessions = endpoint.AudioSessionManager.Sessions;
                    for (int row = 0; row < sessions.Count; row++)
                    {
                        var candidate = sessions[row];
                        try
                        {
                            if (candidate.IsSystemSoundsSession || candidate.State != AudioSessionState.AudioSessionStateActive ||
                                !MediaAppTarget.Plays(owner, AppIdentity.Describe((int)candidate.GetProcessID))) continue;
                            if (match is not null) return false;
                            match = candidate;
                            matchDevice = endpoint;
                        }
                        finally { if (candidate != match) candidate.Dispose(); }
                    }
                }
                finally { if (endpoint != matchDevice) endpoint.Dispose(); }
            }
            if (match is null || match.SimpleAudioVolume.Mute) return false;
            match.SimpleAudioVolume.Mute = true;
            trackId = id;
            session = match;
            device = matchDevice;
            match = null;
            matchDevice = null;
            return true;
        }
        catch { return false; }
        finally { match?.Dispose(); matchDevice?.Dispose(); }
    }

    public bool Resume()
    {
        if (session is null) return false;
        try { session.SimpleAudioVolume.Mute = false; }
        catch { return false; }
        Release();
        return true;
    }

    private void Release()
    {
        session?.Dispose(); device?.Dispose();
        trackId = null; session = null; device = null;
    }

    public void Dispose()
    {
        if (!Resume()) Release();
    }
}
