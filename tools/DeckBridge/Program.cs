// BigFishDockpro adapter, 2026. Pinned BrimDeck sources stay in references/BrimDeck
// under Apache-2.0; Core/ adapts its log reader to bounded metadata parsing.
using System.IO;
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
    static UsageService? Usage;
    static readonly LyricsService LyricsReader = new();
    static Lyrics Lines = Lyrics.Empty;
    static string Song = "", CoverKey = "", ProviderKey = "";
    static string? Cover;
    static CancellationTokenSource? Reading, LyricReading;
    static bool AiEnabled, LyricsEnabled, Spectrum, Busy, Presentation;
    static string[] Providers = [];
    static DateTimeOffset NextAi;
    static long LastMedia;
    static DeckSettings Settings = new();
    static string Data = "";
    static Pricing? Prices;
    static bool AllHistory;
    static DispatcherTimer Tick = null!;

    [STAThread]
    static void Main(string[] args)
    {
        Console.InputEncoding = new UTF8Encoding(false); Console.OutputEncoding = new UTF8Encoding(false);
        Loc.Use("zh-CN");
        try { MemoryBudget.Install(); }
        catch (Exception) { Emit(new { type = "memory_error", message = "无法启用 50 MB 内存限制，AI / 音乐组件已停止" }); return; }
        if (args.Contains("--self-test")) { SelfTest(); return; }
        Data = args.Length > 0 ? args[0] : Path.Combine(Path.GetTempPath(), "BigFishDeckBridge");
        // This is a headless adapter. A dispatcher provides the STA message loop
        // needed by media APIs without constructing WPF's Application/UI services.
        Ui = Dispatcher.CurrentDispatcher;
        Ui.UnhandledException += (_, e) => { Emit(new { type = "error", message = "组件读取失败，请重试" }); e.Handled = true; };
        Tick = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        Tick.Tick += (_, _) => { TickMedia(); if (AiEnabled && !Busy && DateTimeOffset.UtcNow >= NextAi) _ = ReadAi(); };
        Tick.Start();
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
        finally { Tick.Stop(); Reading?.Cancel(); LyricReading?.Cancel(); Media?.Dispose(); Usage?.Dispose(); Prices?.Dispose(); LyricsReader.Dispose(); MemoryBudget.Close(); }
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
                Tick.Interval = TimeSpan.FromMilliseconds(Flag(q, "music") && Presentation ? 100 : 1000);
                AiEnabled = Flag(q, "ai"); LyricsEnabled = Flag(q, "lyrics"); Spectrum = q.Get("equalizer").Text() == "spectrum";
                Providers = q.Get("providers").Items().Select(x => x.Text()).Take(7).ToArray();
                var key = string.Join(",", Providers);
                if (key != ProviderKey) { ProviderKey = key; Reading?.Cancel(); NextAi = DateTimeOffset.MinValue; }
                if (!AiEnabled) { Reading?.Cancel(); Usage?.Dispose(); Usage = null; Prices?.Dispose(); Prices = null; }
                if (!LyricsEnabled) { LyricReading?.Cancel(); Lines = Lyrics.Empty; Song = ""; }
                if (Flag(q, "music") && Media is null)
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
                else if (!Flag(q, "music") && Media is not null)
                { Media.Dispose(); Media = null; LyricReading?.Cancel(); Song = ""; Lines = Lyrics.Empty; Cover = null; CoverKey = ""; }
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
            Emit(new { type = "ai", at = DateTimeOffset.Now, providers = columns.Select(c => Provider(c, DateTime.Today)).ToArray() });
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

    static object Provider(DashboardColumn c, DateTime today)
    {
        object Summary(IEnumerable<TokenEntry> entries)
        {
            var list = entries.ToList();
            var cost = Prices?.Summarize(list);
            return new { tokens = list.Sum(t => t.Total), input = list.Sum(t => t.Input), output = list.Sum(t => t.Output), cacheRead = list.Sum(t => t.CacheRead), cacheWrite = list.Sum(t => t.CacheWrite + t.CacheWriteHour), records = list.Count,
                cost = list.Count == 0 ? 0m : cost?.HasValue == true ? cost.Amount : list.Any(t => t.ReportedCostUsd.HasValue) ? list.Sum(t => t.ReportedCostUsd ?? 0) : (decimal?)null,
                estimated = cost?.IsEstimate ?? false, unpriced = cost?.Unpriced ?? list.Count(t => !t.ReportedCostUsd.HasValue) };
        }
        return new { id = c.Entry.Id.ToString(), name = c.Entry.Name, plan = c.Quota.Plan, status = c.Quota.StatusLabel, note = c.Quota.Status,
            stale = c.Quota.IsStale, source = c.Quota.Source, usageNote = c.Usage.UsageNote, usageAvailable = c.Usage.UsageAvailable, usageComplete = c.Usage.UsageComplete, historyStart = c.Usage.UsageStart?.ToString("yyyy-MM-dd"), allHistory = AllHistory,
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
        if (Presentation && t?.State == MediaState.Playing)
        {
            var levels = new double[8]; Media.FlowLevels(levels, Spectrum ? EqualizerMode.Spectrum : EqualizerMode.Flow);
            Emit(new { type = "levels", levels });
        }
        if (Environment.TickCount64 - LastMedia < 500) return;
        LastMedia = Environment.TickCount64;
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
            track = t is null ? null : new { id = t.Id, title = t.Title, artist = t.Artist, source = t.Source, state = t.State.ToString(),
                duration = t.Duration.TotalSeconds, position = t.Position(now).TotalSeconds, t.CanToggle, t.CanPrevious, t.CanNext, t.CanSeek, t.CanShuffle, t.CanRepeat,
                shuffle = t.Shuffle, repeat = t.Repeat.ToString(), lyric = t.CurrentLyric ?? Lines.At(t, now).Current, lyricSource = Lines.Source },
            pictureChanged, cover = pictureChanged ? Cover : null });
    }

    static void SelfTest()
    {
        var q = new Quota("测试", 80, null); if (q.Remaining != 20) throw new Exception("quota");
        var lines = Lyrics.Parse("[00:01.00]第一行\n[00:03.00]第二行", null, 10, "fixture");
        if (lines.At(2).Current != "第一行") throw new Exception("lyric");
        var sample = new ProviderSnapshot(ProviderId.Codex) { Quotas = [q], Entries = [new("fixture", DateTimeOffset.Now, "fixture", 10, 2, 0, 0, 3)] };
        var result = JsonSerializer.Serialize(Provider(new(new AppEntry { QuotaSource = ProviderId.Codex }, sample, sample), DateTime.Today), Json);
        if (!result.Contains("\"tokens\":15") || !result.Contains("\"cacheRead\":2") || !result.Contains("\"records\":1")) throw new Exception("usage");
        if (MemoryBudget.InstalledLimit() != MemoryBudget.Bytes) throw new Exception("memory limit");
        Emit(new { passed = true, processCommitLimit = MemoryBudget.InstalledLimit(), managedHeapLimit = GC.GetGCMemoryInfo().TotalAvailableMemoryBytes,
            checks = new[] { "quota", "synchronized lyrics", "usage projection without auth or conversation content", "OS process commit budget 50 MiB" } });
    }
}
