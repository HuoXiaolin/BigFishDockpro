// BigFishDockpro adapter, 2026. Pinned BrimDeck sources stay in references/BrimDeck
// under Apache-2.0; Core/ adapts its log reader to bounded metadata parsing.
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using BrimDeck.Core;
using BrimDeck.Native;

internal static class Program
{
    static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
    static readonly object OutputGate = new();
    static Dispatcher Ui = null!;
    static MediaSessions? Media;
    static DesktopAudio? DesktopSpectrum;
    static readonly double[] SpectrumFrame = new double[DesktopAudio.Bands], LastSpectrum = new double[DesktopAudio.Bands];
    static readonly LiveAudio Live = new();
    static UsageService? Usage;
    static readonly LyricsService LyricsReader = new();
    static Lyrics Lines = Lyrics.Empty;
    static string Song = "", CoverKey = "", ProviderKey = "";
    static string? Cover;
    static CancellationTokenSource? Reading, LyricReading;
    static bool AiEnabled, LyricsEnabled, Spectrum, Busy, Presentation;
    static string[] Providers = [];
    static DateTimeOffset NextAi;
    static long LastMedia, LastLevels;
    static DeckSettings Settings = new();
    static string Data = "";
    static Pricing? Prices;
    static bool AllHistory;
    static DispatcherTimer Tick = null!;
    const uint AlwaysShowErrorUi = 0x10;
    const uint NoErrorUi = 0x20;

    [DllImport("kernel32")]
    static extern uint GetErrorMode();
    [DllImport("kernel32")]
    static extern uint SetErrorMode(uint mode);
    [DllImport("kernel32")]
    static extern nint GetCurrentProcess();
    [DllImport("kernel32")]
    static extern int WerGetFlags(nint process, out uint flags);
    [DllImport("kernel32")]
    static extern int WerSetFlags(uint flags);

    [STAThread]
    static void Main(string[] args)
    {
        // A background helper reports failures to Dock through its exit code.
        SetErrorMode(GetErrorMode() | 0x0003);
        WerGetFlags(GetCurrentProcess(), out uint faultFlags);
        WerSetFlags((faultFlags & ~AlwaysShowErrorUi) | NoErrorUi);
        Console.InputEncoding = new UTF8Encoding(false); Console.OutputEncoding = new UTF8Encoding(false);
        Loc.Use("zh-CN");
        try { MemoryBudget.Install(); }
        catch (Exception) { Emit(new { type = "memory_error", message = "无法启用工作集上限，AI / 音乐组件已停止" }); return; }
        if (args.Contains("--self-test")) { SelfTest(); return; }
        Data = args.Length > 0 ? args[0] : Path.Combine(Path.GetTempPath(), "BigFishDeckBridge");
        // This is a headless adapter. A dispatcher provides the STA message loop
        // needed by media APIs without constructing WPF's Application/UI services.
        Ui = Dispatcher.CurrentDispatcher;
        Ui.UnhandledException += (_, e) => { Emit(new { type = "error", message = "组件读取失败，请重试" }); e.Handled = true; };
        Tick = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        Tick.Tick += (_, _) =>
        {
            TickMedia();
            TickDesktopSpectrum();
            if (AiEnabled && !Busy && DateTimeOffset.UtcNow >= NextAi) _ = ReadAi();
        };
        Tick.Start();
        Emit(new { type = "ready" });
        _ = Task.Run(async () =>
        {
            string? line;
            while ((line = await Console.In.ReadLineAsync()) is not null)
            {
                if (line.Length > 65536) continue;
                try { using var document = JsonDocument.Parse(line); var input = document.RootElement.Clone(); await Ui.InvokeAsync(() => _ = Command(input)); }
                catch (JsonException) { Emit(new { type = "error", message = "无效的组件命令" }); }
            }
            await Ui.InvokeAsync(() => Ui.InvokeShutdown());
        });
        try { Dispatcher.Run(); }
        finally { Tick.Stop(); Reading?.Cancel(); LyricReading?.Cancel(); DesktopSpectrum?.Dispose(); Live.Dispose(); Media?.Dispose(); Usage?.Dispose(); Prices?.Dispose(); LyricsReader.Dispose(); }
    }

    static void Emit(object data)
    {
        lock (OutputGate) { Console.WriteLine(JsonSerializer.Serialize(data, Json)); Console.Out.Flush(); }
    }
    static bool Flag(JsonElement q, string name) => q.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.True;
    static async Task Command(JsonElement q)
    {
        try
        {
            string op = q.Get("op").Text();
            if (op == "quit") { Ui.InvokeShutdown(); return; }
            if (op == "history") { AllHistory = q.Get("range").Text() == "all"; NextAi = DateTimeOffset.MinValue; return; }
            if (op == "configure")
            {
                Presentation = Flag(q, "presentation");
                bool music = Flag(q, "music"), spectrum = Flag(q, "desktopSpectrum");
                if (spectrum && DesktopSpectrum is null)
                    DesktopSpectrum = new DesktopAudio();
                else if (!spectrum && DesktopSpectrum is not null)
                {
                    DesktopSpectrum.Dispose();
                    DesktopSpectrum = null;
                    Array.Clear(LastSpectrum);
                }
                Tick.Interval = TimeSpan.FromMilliseconds(spectrum ? 34 : music && Presentation ? 100 : 1000);
                AiEnabled = Flag(q, "ai"); LyricsEnabled = Flag(q, "lyrics"); Spectrum = q.Get("equalizer").Text() == "spectrum";
                Providers = q.Get("providers").Items().Select(x => x.Text()).Take(7).ToArray();
                var key = string.Join(",", Providers);
                if (key != ProviderKey) { ProviderKey = key; Reading?.Cancel(); NextAi = DateTimeOffset.MinValue; }
                if (!AiEnabled) { Reading?.Cancel(); Usage?.Dispose(); Usage = null; Prices?.Dispose(); Prices = null; }
                if (!LyricsEnabled) { LyricReading?.Cancel(); Lines = Lyrics.Empty; Song = ""; }
                if (music && Media is null)
                {
                    Media = new MediaSessions(Ui);
                    // Do not patch or restart third-party players automatically.
                    Media.NeteaseAutoFullControl = false;
                    Media.NeteaseFileControlWanted = false;
                    Media.KugouFullControlWanted = false;
                    Media.Changed += Changed;
                    Media.SetPresentationActive(Presentation);
                    await Media.StartAsync();
                }
                else if (!music && Media is not null)
                { Live.Dispose(); Media.Dispose(); Media = null; LyricReading?.Cancel(); Song = ""; Lines = Lyrics.Empty; Cover = null; CoverKey = ""; }
                Media?.SetPresentationActive(Presentation);
                Changed(); return;
            }
            if (op == "refresh") { NextAi = DateTimeOffset.MinValue; if (Media is not null) await Media.RefreshAsync(); return; }
            if (Media is null) return;
            var requested = q.Get("id").Text();
            var track = string.IsNullOrEmpty(requested) ? Media.Current : Media.Tracks.FirstOrDefault(x => x.Id == requested);
            bool ok = false;
            if (op == "select") { Media.Select(q.Get("id").Text()); ok = true; }
            else if (op == "pin") { Media.Pin(Flag(q, "on") ? track?.Id : null); ok = true; }
            else if (op == "PlayPause" && track is not null && Live.IsMuted(track.Id)) ok = Live.Resume();
            else if (op == "PlayPause" && track is not null && track.Id == Media.Current?.Id &&
                Media.CurrentOwner is { } owner && LiveAudio.CanPause(track, owner) && Live.TryPause(track.Id, owner)) ok = true;
            else if (op == "seek" && track is not null && track.CanSeek) ok = await Media.SeekAsync(track, Math.Clamp(q.Get("fraction").Number() ?? 0, 0, 1));
            else if (track is not null && Enum.TryParse<MediaCommand>(op, out var command)) ok = await Media.CommandAsync(track.Id, command);
            Emit(new { type = "command", ok, message = ok ? "" : "播放器未支持或未执行此操作" }); Changed();
        }
        catch (Exception) { Emit(new { type = "command", ok = false, message = "播放器读取或控制失败，请重试" }); }
    }

    static async Task ReadAi()
    {
        Busy = true; NextAi = DateTimeOffset.UtcNow.AddSeconds(60);
        var enabled = Providers.ToArray(); var key = ProviderKey;
        Reading?.Dispose(); Reading = new CancellationTokenSource(TimeSpan.FromSeconds(90)); var cancellation = Reading.Token;
        try
        {
            Directory.CreateDirectory(Data);
            Usage ??= new UsageService(new DesktopSources(), quotaCache: Path.Combine(Data, "claude-quota.json"), kimiQuotaCache: Path.Combine(Data, "kimi-quota.json"));
            Settings = new DeckSettings { IncludeWsl = false, UsagePage = true, Apps = enabled.Where(x => Enum.TryParse<ProviderId>(x, out _)).Select(x => new AppEntry { QuotaSource = Enum.Parse<ProviderId>(x), UsageSource = Enum.Parse<ProviderId>(x) }).ToList() };
            var reader = Usage;
            var snapshots = await Task.Run(() => reader.RefreshAsync(Settings, cancellation, AllHistory ? new DateTime(2000, 1, 1) : null), cancellation);
            if (!AiEnabled || key != ProviderKey || cancellation.IsCancellationRequested) return;
            Prices ??= new Pricing(Data);
            try { await Prices.RefreshAsync(cancellation: cancellation); } catch (Exception) { }
            if (!AiEnabled || key != ProviderKey || cancellation.IsCancellationRequested) return;
            var columns = DashboardUsage.Columns(Settings, snapshots);
            (ResetCreditReading? Credits, string Plan) codexAccount = (null, "");
            if (columns.FirstOrDefault(c => c.Entry.Id == ProviderId.Codex) is { } codex)
                codexAccount = await CodexResetCredits.ReadAsync(cancellation, !codex.Quota.LiveQuota || string.IsNullOrWhiteSpace(codex.Quota.Plan));
            if (!AiEnabled || key != ProviderKey || cancellation.IsCancellationRequested) return;
            Emit(new { type = "ai", at = DateTimeOffset.Now, providers = columns.Select(c => Provider(c, DateTime.Today, codexAccount.Credits, codexAccount.Plan)).ToArray() });
        }
        catch (OperationCanceledException) { }
        catch (OutOfMemoryException)
        {
            Reading?.Cancel(); Usage?.Dispose(); Usage = null; Prices?.Dispose(); Prices = null;
            NextAi = DateTimeOffset.UtcNow.AddMinutes(5);
            Emit(new { type = "ai_error", message = "已达到 50 MB 内存预算，保留上次统计，稍后重试" });
        }
        catch (Exception) { if (AiEnabled) Emit(new { type = "ai_error", message = "额度读取失败，稍后自动重试" }); }
        finally { Busy = false; }
    }

    static object Provider(DashboardColumn c, DateTime today, ResetCreditReading? resetCredits = null, string codexPlan = "")
    {
        object Summary(IEnumerable<TokenEntry> entries)
        {
            var list = entries.ToList();
            var cost = Prices?.Summarize(list);
            return new { tokens = list.Sum(t => t.Total), input = list.Sum(t => t.Input), output = list.Sum(t => t.Output), cacheRead = list.Sum(t => t.CacheRead), cacheWrite = list.Sum(t => t.CacheWrite + t.CacheWriteHour), records = list.Count,
                cost = list.Count == 0 ? 0m : cost?.HasValue == true ? cost.Amount : list.Any(t => t.ReportedCostUsd.HasValue) ? list.Sum(t => t.ReportedCostUsd ?? 0) : (decimal?)null,
                estimated = cost?.IsEstimate ?? false, unpriced = cost?.Unpriced ?? list.Count(t => !t.ReportedCostUsd.HasValue) };
        }
        var isCodex = c.Entry.Id == ProviderId.Codex;
        var plan = isCodex && !string.IsNullOrWhiteSpace(codexPlan) ? codexPlan : c.Quota.Plan;
        var stale = c.Quota.IsStale || (isCodex && !c.Quota.LiveQuota && c.Quota.Quotas.Count > 0);
        return new { id = c.Entry.Id.ToString(), name = c.Entry.Name, plan, status = c.Quota.StatusLabel, note = c.Quota.Status,
            stale, source = c.Quota.Source, usageNote = c.Usage.UsageNote, usageAvailable = c.Usage.UsageAvailable, usageComplete = c.Usage.UsageComplete, historyStart = c.Usage.UsageStart?.ToString("yyyy-MM-dd"), allHistory = AllHistory,
            resetCredits = isCodex ? resetCredits : null,
            quotas = c.Quota.Metrics.Select(m => new { label = m.Label, kind = m.Kind.ToString().ToLowerInvariant(), percent = m.UsedPercent, value = m.ValueText, reset = m.ResetAt, detail = m.Description }),
            today = Summary(c.Usage.Entries.Where(t => t.Time.LocalDateTime.Date == today)), week = Summary(c.Usage.Entries.Where(t => t.Time.LocalDateTime.Date >= today.AddDays(-6))),
            hours = c.Usage.Entries.Where(t => t.Time.LocalDateTime.Date >= today.AddDays(-1)).GroupBy(t => t.Time.LocalDateTime.ToString("yyyy-MM-dd'T'HH")).Select(g => new { date = g.Key, summary = Summary(g) }).ToArray(),
            days = c.Usage.Entries.GroupBy(t => (day: t.Time.LocalDateTime.ToString("yyyy-MM-dd"), t.Model)).Select(g => new { date = g.Key.day, model = g.Key.Model, summary = Summary(g) }).ToArray() };
    }

    static async void Changed()
    {
        var media = Media; if (media is null) return;
        var track = media.Current;
        if (track is not null && LyricsEnabled && Song != track.SongKey)
        {
            Song = track.SongKey; Lines = Lyrics.Empty; LyricReading?.Cancel(); LyricReading?.Dispose(); LyricReading = new();
            var token = LyricReading.Token;
            try { var found = await LyricsReader.FindAsync(track, true, token); if (!token.IsCancellationRequested && Media == media && Song == track.SongKey) Lines = found; }
            catch (Exception) { }
        }
        LastMedia = 0; TickMedia();
    }
    static void TickMedia()
    {
        if (Media is null) return;
        var t = Media.Current; var now = DateTimeOffset.Now;
        bool liveMuted = t is not null && Live.IsMuted(t.Id);
        long elapsed = Environment.TickCount64;
        if (Presentation && t?.State == MediaState.Playing && !liveMuted && elapsed - LastLevels >= 90)
        {
            LastLevels = elapsed;
            var levels = new double[8]; Media.FlowLevels(levels, Spectrum ? EqualizerMode.Spectrum : EqualizerMode.Flow);
            Emit(new { type = "levels", levels });
        }
        if (elapsed - LastMedia < 500) return;
        LastMedia = elapsed;
        bool liveAudio = liveMuted || t is not null && LiveAudio.CanPause(t, Media.CurrentOwner);
        string pictureKey = (t?.SongKey ?? "") + ":" + (Media.Cover?.GetHashCode() ?? 0);
        bool pictureChanged = pictureKey != CoverKey;
        if (pictureChanged)
        {
            CoverKey = pictureKey; Cover = null;
            if (Media.Cover is { } bitmap)
            {
                BitmapSource thumbnail = bitmap;
                if (Math.Max(bitmap.PixelWidth, bitmap.PixelHeight) > 256)
                {
                    var scale = 256.0 / Math.Max(bitmap.PixelWidth, bitmap.PixelHeight);
                    thumbnail = new TransformedBitmap(bitmap, new ScaleTransform(scale, scale)); thumbnail.Freeze();
                }
                var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(thumbnail));
                using var memory = new MemoryStream(); encoder.Save(memory);
                if (memory.Length < 2 * 1024 * 1024) Cover = Convert.ToBase64String(memory.ToArray());
            }
        }
        Emit(new { type = "media", status = Media.Error ?? (t is null ? "没有正在播放的媒体" : ""), pinned = Media.Pinned is not null,
            tracks = Media.Tracks.Select(x => new { id = x.Id, source = x.Source, title = x.Title }),
            track = t is null ? null : new { id = t.Id, title = t.Title, artist = t.Artist, source = t.Source, state = liveMuted ? "Paused" : t.State.ToString(),
                duration = t.Duration.TotalSeconds, position = t.Position(now).TotalSeconds, canToggle = t.CanToggle || liveAudio, liveAudio, t.CanPrevious, t.CanNext, t.CanSeek, t.CanShuffle, t.CanRepeat,
                shuffle = t.Shuffle, repeat = t.Repeat.ToString(), lyric = t.CurrentLyric ?? Lines.At(t, now).Current, lyricSource = Lines.Source },
            pictureChanged, cover = pictureChanged ? Cover : null });
    }

    static void TickDesktopSpectrum()
    {
        if (DesktopSpectrum is null) return;
        Array.Clear(SpectrumFrame);
        DesktopSpectrum.Fill(SpectrumFrame);
        for (int i = 0; i < SpectrumFrame.Length; i++)
            SpectrumFrame[i] = Math.Round(SpectrumFrame[i], 2);
        if (SpectrumFrame.AsSpan().SequenceEqual(LastSpectrum)) return;
        SpectrumFrame.CopyTo(LastSpectrum, 0);
        Emit(new { type = "spectrum", levels = SpectrumFrame });
    }

    static void SelfTest()
    {
        CodexResetCredits.SelfTest();
        var live = new MediaTrack { Id = "system:fixture", State = MediaState.Playing, PositionKnown = false };
        var owner = new MediaAppOwner(null, "chrome", "Chrome");
        if (!LiveAudio.CanPause(live, owner) || LiveAudio.CanPause(live, null) ||
            LiveAudio.CanPause(live with { PositionKnown = true, End = TimeSpan.FromMinutes(2) }, owner)) throw new Exception("live audio selection");
        var q = new Quota("测试", 80, null); if (q.Remaining != 20) throw new Exception("quota");
        var lines = Lyrics.Parse("[00:01.00]第一行\n[00:03.00]第二行", null, 10, "fixture");
        if (lines.At(2).Current != "第一行") throw new Exception("lyric");
        var sample = new ProviderSnapshot(ProviderId.Codex) { Quotas = [q], Entries = [new("fixture", DateTimeOffset.Now, "fixture", 10, 2, 0, 0, 3)] };
        var entry = new AppEntry { QuotaSource = ProviderId.Codex };
        var result = JsonSerializer.Serialize(Provider(new(entry, sample, sample), DateTime.Today), Json);
        if (!result.Contains("\"tokens\":15") || !result.Contains("\"cacheRead\":2") || !result.Contains("\"records\":1")) throw new Exception("usage");
        var planOnly = JsonSerializer.Serialize(Provider(new(entry, new(ProviderId.Codex), sample), DateTime.Today, codexPlan: "go"), Json);
        if (!planOnly.Contains("\"plan\":\"go\"") || !planOnly.Contains("\"quotas\":[]")) throw new Exception("account plan without quota windows");
        using var periods = JsonDocument.Parse("""{"rate_limit":{"primary_window":{"used_percent":10,"limit_window_seconds":3600},"secondary_window":{"used_percent":20,"limit_window_seconds":2592000}}}""");
        if (!QuotaParser.Codex(periods.RootElement, DateTimeOffset.Now, true).Select(item => item.Label).SequenceEqual(new[] { "每小时额度", "30 天额度" }))
            throw new Exception("quota window labels");
        if (MemoryBudget.InstalledLimit() != MemoryBudget.Bytes) throw new Exception("memory limit");
        if (WerGetFlags(GetCurrentProcess(), out uint faultFlags) != 0 || (faultFlags & NoErrorUi) == 0)
            throw new Exception("headless error reporting");
        var buffers = new byte[12][];
        for (int i = 0; i < 512; i++)
        {
            // Rotate short-lived large buffers under the small bridge heap.
            var buffer = new byte[(96 + i * 53 % 228) * 1024];
            buffer[0] = (byte)i;
            buffers[i % buffers.Length] = buffer;
        }
        GC.KeepAlive(buffers);
        Emit(new { passed = true, workingSetLimit = MemoryBudget.InstalledLimit(), managedHeapLimit = GC.GetGCMemoryInfo().TotalAvailableMemoryBytes, processErrorMode = GetErrorMode(),
            gcRegionSize = GC.GetConfigurationVariables().GetValueOrDefault("GCRegionSize"),
            checks = new[] { "quota", "read-only reset credits: quantity, sorted expiries, embedded fallback, zero versus unavailable", "synchronized lyrics", "usage projection without auth or conversation content", "OS working set limit 47 MiB", "bridge fault reporting runs without UI", "repeated large-object allocation under the managed heap limit" } });
    }
}
