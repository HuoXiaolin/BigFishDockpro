using System.IO;
using System.Text.Json;
using BrimDeck.Core;

static class CodexAccountingTests
{
    public static void Run()
    {
        string root = Path.Combine(Path.GetTempPath(), "bigfish-codex-accounting-" + Guid.NewGuid().ToString("N"));
        string sessions = Path.Combine(root, "sessions"); Directory.CreateDirectory(sessions);
        try
        {
            var at = new DateTimeOffset(2026, 11, 15, 10, 0, 0, TimeSpan.Zero);
            object Usage(long input, long read, long output, long write = 0) => new
            { input_tokens = input, cached_input_tokens = read, cache_write_input_tokens = write, output_tokens = output, reasoning_output_tokens = output / 2, total_tokens = input + output };
            string Line(int second, string type, object payload) => JsonSerializer.Serialize(new { timestamp = at.AddSeconds(second), type, payload }) + "\n";
            string Context(int second, string model) => Line(second, "turn_context", new { turn_id = "turn", model });
            string Count(int second, object total, object? last) => Line(second, "event_msg", new { type = "token_count", info = new { total_token_usage = total, last_token_usage = last } });
            string Record(int second, string id, object usage, object? total = null) => Line(second, "token_usage_record", new
            { session_id = "thread", turn_id = "turn", response_id = id, usage, thread_token_usage = total });
            ProviderSnapshot Read(LogReader? reader = null) => (reader ?? new LogReader()).Read(ProviderId.Codex, root, at.AddHours(2), at.LocalDateTime.Date);
            void Check(bool ok, string name) { if (!ok) throw new Exception("Codex accounting: " + name); }
            string file = Path.Combine(sessions, "fixture.jsonl");
            var u = Usage(100, 60, 10, 20);
            File.WriteAllText(file, Context(0, "model-a") + Record(1, "first", u, u) + Count(2, u, u) +
                Line(3, "event_msg", new { type = "thread_settings_applied", thread_settings = new { model = "model-b" } }) +
                Record(4, "second", u, Usage(200, 120, 20, 40)) + Count(5, Usage(200, 120, 20, 40), u) +
                Record(6, "compact", Usage(50, 0, 5)) + // No counter event: still a real call.
                Count(8, Usage(300, 180, 30, 60), u) + Record(7, "third", u, Usage(350, 180, 35, 60)) +
                Record(9, "second", u, Usage(200, 120, 20, 40)) + Record(10, "first", u, u));
            var s = Read();
            Check(s.UsageComplete && s.Entries.Count == 4, "one response, one record, both event orders and compaction");
            Check(s.Entries.Sum(e => e.Total) == 385 && s.Entries.Sum(e => e.Input) == 110 && s.Entries.Sum(e => e.CacheWrite) == 60, "cache writes disjoint; reasoning included once");
            Check(s.Entries.Single(e => e.Time == at.AddSeconds(1)).Model == "model-a" && s.Entries.Count(e => e.Model == "model-b") == 3, "in-turn model switch");
            Check(s.Entries.Any(e => e.Time == at.AddSeconds(7)), "canonical completion time replaces checkpoint time");
            File.Copy(file, Path.Combine(sessions, "fork.jsonl"));
            Check(Read().Entries.Count == 4, "copied response history deduplicated across files");
            File.Delete(Path.Combine(sessions, "fork.jsonl"));

            File.WriteAllText(file, Context(0, "legacy") + Count(1, u, u) + Count(2, u, u) +
                Count(3, Usage(200, 120, 20, 40), null) + Count(4, Usage(10, 0, 1), Usage(10, 0, 1)) +
                Count(5, Usage(9000, 0, 100), Usage(0, 0, 0)));
            s = Read();
            Check(s.UsageComplete && s.Entries.Count == 3 && s.Entries.Sum(e => e.Total) == 231, "legacy delta, reset, duplicate checkpoint, zero-usage fork snapshot");

            using (var writer = new StreamWriter(file))
            {
                writer.Write(Context(0, "large"));
                writer.Write("{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"output\":\"");
                string chunk = new('x', 8192);
                for (int i = 0; i < 256; i++) writer.Write(chunk);
                writer.Write("\"}}\n"); writer.Write(Record(2, "large-test", u));
            }
            s = Read(); Check(s.UsageComplete && s.Entries.Count == 1, "bounded projection skips large tool content");

            var reader = new LogReader();
            File.WriteAllText(file, Context(0, "append") + Count(2, u, u));
            Check(Read(reader).Entries.Count == 1, "legacy append baseline");
            var tail = Record(1, "append-test", u, u);
            File.AppendAllText(file, tail[..^1]);
            Check(Read(reader).Entries.Count == 1, "partial last line is retried");
            File.AppendAllText(file, "\n");
            s = Read(reader); Check(s.Entries.Count == 1 && s.Entries[0].Time == at.AddSeconds(1), "late ledger append replaces legacy entry");
            Check(Read(reader).Entries.Count == 1, "unchanged refresh stable");

            File.WriteAllText(file, Context(0, "delayed") + Record(1, "a", u, u) + Record(2, "b", Usage(200, 80, 20), Usage(300, 140, 30, 20)) +
                Count(3, u, u) + Count(4, Usage(300, 140, 30, 20), Usage(200, 80, 20)));
            s = Read(); Check(s.UsageComplete && s.Entries.Count == 2, "delayed counter paired by cumulative identity");

            File.WriteAllText(file, Context(-86401, "range") + Record(-86400, "old-day", u) + Record(1, "current-day", u));
            reader = new LogReader();
            Check(Read(reader).Entries.Count == 1, "recent range excludes previous day");
            Check(reader.Read(ProviderId.Codex, root, at.AddHours(2), at.LocalDateTime.Date.AddDays(-1)).Entries.Count == 2, "widened range reparses complete history");
            Check(Read(reader).Entries.Count == 1, "narrowed range discards older entries");
            File.AppendAllText(file, Record(3, "current-day", u));
            s = Read(reader); Check(s.UsageComplete && s.Entries.Count == 1, "response index remains valid after date range changes");
        }
        finally { Directory.Delete(root, recursive: true); }
    }
}
