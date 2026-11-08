using System.Runtime.InteropServices;
using BrimDeck.Core;
using BrimDeck.Native;
using NAudio.CoreAudioApi;
using NAudio.CoreAudioApi.Interfaces;
using NAudio.Dsp;
using NAudio.Wave;

// A spectrum of the default Windows output, independent of media sessions.
// All WASAPI objects stay on one worker. Audio samples live only in the FFT buffer.
internal sealed class DesktopAudio : IDisposable
{
    readonly ManualResetEvent stop = new(false);
    internal const int Bands = 120;
    volatile DetailedSpectrum? signal;

    internal DesktopAudio()
    {
        var worker = new Thread(Run) { IsBackground = true, Name = "Desktop spectrum" };
        worker.SetApartmentState(ApartmentState.MTA);
        worker.Start();
    }

    internal void Fill(Span<double> levels)
    {
        signal?.Fill(levels, AudioLevelMeter.Now);
    }

    void Run()
    {
        using (stop)
        {
            while (!stop.WaitOne(0))
            {
                try { Capture(); }
                catch (Exception ex) when (ex is COMException or InvalidOperationException or ArgumentException) { }
                finally { signal = null; }
                if (stop.WaitOne(2000)) return;
            }
        }
    }

    void Capture()
    {
        using var enumerator = new MMDeviceEnumerator();
        using var device = enumerator.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia);
        using var client = device.AudioClient;
        using var ready = new AutoResetEvent(false);
        var format = WaveFormat.CreateIeeeFloatWaveFormat(48000, 2);
        var flags = AudioClientStreamFlags.Loopback | AudioClientStreamFlags.EventCallback |
                    AudioClientStreamFlags.AutoConvertPcm | AudioClientStreamFlags.SrcDefaultQuality;
        client.Initialize(AudioClientShareMode.Shared, flags, 0, 0, format, Guid.Empty);
        client.SetEventHandle(ready.SafeWaitHandle.DangerousGetHandle());
        using var capture = client.AudioCaptureClient;
        var analyzer = new DetailedSpectrum(format.SampleRate);
        var buffer = new float[client.BufferSize * format.Channels];
        WaitHandle[] handles = [stop, ready];
        double lastFrame = 0, nextDeviceCheck = 0;
        string deviceId = device.ID;
        client.Start();
        signal = analyzer;
        try
        {
            while (WaitHandle.WaitAny(handles, 500) != 0)
            {
                double now = AudioLevelMeter.Now;
                if (now >= nextDeviceCheck)
                {
                    using var current = enumerator.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia);
                    if (current.ID != deviceId) return;
                    nextDeviceCheck = now + 2;
                }
                bool received = false;
                while (capture.GetNextPacketSize() > 0)
                {
                    nint data = capture.GetBuffer(out int frames, out var packetFlags);
                    try
                    {
                        int count = frames * format.Channels;
                        if (count > buffer.Length) continue;
                        if ((packetFlags & AudioClientBufferFlags.Silent) != 0)
                            Array.Clear(buffer, 0, count);
                        else
                            Marshal.Copy(data, buffer, 0, count);
                        analyzer.Push(buffer.AsSpan(0, count));
                        received = true;
                    }
                    finally { capture.ReleaseBuffer(frames); }
                }
                if (received && now - lastFrame >= .030)
                {
                    analyzer.Advance(now);
                    lastFrame = now;
                }
            }
        }
        finally
        {
            try { client.Stop(); }
            catch (COMException) { } // The default endpoint can disappear during stop.
        }
    }

    public void Dispose() => stop.Set();

    sealed class DetailedSpectrum
    {
        const int LogSize = 13, Size = 1 << LogSize;
        readonly float[][] samples = [new float[Size], new float[Size]];
        readonly float[] window = new float[Size], power = new float[Size / 2];
        readonly Complex[] fft = new Complex[Size];
        readonly int[] edges = new int[Bands + 1];
        readonly double[] output = new double[Bands], next = new double[Bands];
        readonly object gate = new();
        int position, filled;
        double lastFrame;

        internal DetailedSpectrum(int sampleRate)
        {
            for (int i = 0; i < Size; i++)
                window[i] = (float)(.5 - .5 * Math.Cos(2 * Math.PI * i / (Size - 1)));
            int maximum = Math.Min(Size / 2, (int)(18_000d * Size / sampleRate));
            for (int i = 0; i <= Bands; i++)
            {
                double frequency = 30 * Math.Pow(18_000d / 30, (double)i / Bands);
                int bin = (int)Math.Round(frequency * Size / sampleRate);
                edges[i] = Math.Clamp(bin, i == 0 ? 1 : edges[i - 1] + 1, maximum - Bands + i);
            }
        }

        internal void Push(ReadOnlySpan<float> stereo)
        {
            for (int i = 0; i + 1 < stereo.Length; i += 2)
            {
                samples[0][position] = stereo[i];
                samples[1][position] = stereo[i + 1];
                position = (position + 1) & (Size - 1);
            }
            filled = Math.Min(Size, filled + stereo.Length / 2);
        }

        internal void Advance(double now)
        {
            if (filled < Size) return;
            Array.Clear(power);
            foreach (var channel in samples)
            {
                for (int i = 0; i < Size; i++)
                {
                    fft[i].X = channel[(position + i) & (Size - 1)] * window[i];
                    fft[i].Y = 0;
                }
                FastFourierTransform.FFT(true, LogSize, fft);
                for (int i = edges[0]; i < edges[Bands]; i++)
                    power[i] += fft[i].X * fft[i].X + fft[i].Y * fft[i].Y;
            }
            for (int band = 0; band < Bands; band++)
            {
                float strongest = 0;
                for (int bin = edges[band]; bin < edges[band + 1]; bin++)
                    strongest = Math.Max(strongest, power[bin]);
                double db = 10 * Math.Log10(Math.Max(1e-12, strongest * 8));
                next[band] = Math.Clamp((db + 68) / 57, 0, 1);
            }
            lock (gate)
            {
                for (int i = 0; i < Bands; i++)
                    output[i] = next[i] > output[i] ? next[i] : output[i] * .64 + next[i] * .36;
                lastFrame = now;
            }
        }

        internal void Fill(Span<double> target, double now)
        {
            lock (gate)
            {
                double fade = Math.Clamp(1 - (now - lastFrame - .13) * 5, 0, 1);
                for (int i = 0; i < Math.Min(Bands, target.Length); i++) target[i] = output[i] * fade;
            }
        }
    }
}
