// Codex's response ledger and its legacy counter events describe the same calls.
// Keep only accounting metadata; never retain prompts, tool results or credentials.
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace BrimDeck.Core;

internal sealed class CodexAccounting(List<TokenEntry> entries)
{
    readonly record struct Counts(long Input, long Read, long Write, long Output)
    {
        public long Total => Input + Output;
        public bool Covers(Counts old) => Input >= old.Input && Read >= old.Read && Write >= old.Write && Output >= old.Output;
        public Counts Minus(Counts old) => new(Input - old.Input, Read - old.Read, Write - old.Write, Output - old.Output);
        public bool Valid => Input >= 0 && Output >= 0 && Read >= 0 && Write >= 0 && Read + Write <= Input;
        public static Counts? Parse(JsonElement obj)
        {
            if (obj.ValueKind != JsonValueKind.Object || obj.Get("input_tokens").Number() is not { } input ||
                obj.Get("output_tokens").Number() is not { } output || input < 0 || output < 0) return null;
            var result = new Counts(obj.Get("input_tokens").Count(), obj.Get("cached_input_tokens").Count(),
                obj.Get("cache_write_input_tokens").Count(), obj.Get("output_tokens").Count());
            return result.Valid ? result : null;
        }
    }

    sealed class Observation(string key, string turn, Counts usage, Counts? total, bool response)
    {
        public string Key = key;
        public readonly string Turn = turn;
        public readonly Counts Usage = usage;
        public readonly Counts? Total = total;
        public bool Response = response, Paired;
    }

    // Response ids give cross-file/fork identity. Values point into the existing
    // entry list; no second copy of the token history is kept.
    readonly Dictionary<string, int> responses = new(StringComparer.Ordinal);
    readonly List<Observation> recent = [];
    readonly Dictionary<string, string> models = new(StringComparer.Ordinal);
    string model = "unknown", session = "", turn = "";
    Counts? checkpoint;

    public void Reindex()
    {
        responses.Clear(); recent.Clear();
        for (int i = 0; i < entries.Count; i++)
            if (entries[i].Key.StartsWith("codex:response:", StringComparison.Ordinal)) responses[entries[i].Key] = i;
    }

    static string Digest(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)).AsSpan(0, 16));
    void SetModel(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return;
        model = string.Intern(value);
        if (turn.Length == 0) return;
        if (models.Count >= 64 && !models.ContainsKey(turn)) models.Remove(models.Keys.First());
        models[turn] = model;
    }
    void Remember(Observation observation)
    {
        if (recent.Count == 32) recent.RemoveAt(0);
        recent.Add(observation);
    }
    Observation? Pair(string activeTurn, Counts usage, Counts? total, bool response)
    {
        var candidates = recent.Where(x => !x.Paired && x.Response != response && x.Turn == activeTurn && x.Usage == usage).ToArray();
        // Exact cumulative counters win. After compaction or a runtime restart,
        // the durable and live counters have different bases: pair only a unique
        // outstanding observation, never every request with identical token counts.
        var exact = total is null ? [] : candidates.Where(x => x.Total == total).ToArray();
        return exact.Length == 1 ? exact[0] : candidates.Length == 1 ? candidates[0] : null;
    }
    void Store(string key, DateTimeOffset time, string usedModel, Counts usage, DateTimeOffset cutoff, Observation? paired)
    {
        if (usage.Total <= 0 || time < cutoff) return;
        var entry = new TokenEntry(key, time, usedModel, usage.Input - usage.Read - usage.Write, usage.Read, usage.Write, 0, usage.Output);
        if (responses.TryGetValue(key, out int index))
        {
            var old = entries[index];
            // Replayed snapshots cannot add another request or move it into a
            // different day. Keep the most complete accounting for this response.
            if (entry.Total >= old.Total) entries[index] = entry with { Time = old.Time, Model = old.Model == "unknown" ? entry.Model : old.Model };
            return;
        }
        if (paired is { Response: false })
        {
            index = entries.FindLastIndex(x => x.Key == paired.Key);
            if (index >= 0)
            {
                entries[index] = entry;
                responses[key] = index;
                return;
            }
        }
        if (key.StartsWith("codex:response:", StringComparison.Ordinal)) responses[key] = entries.Count;
        entries.Add(entry);
    }

    // false means an accounting event existed but its counters were invalid.
    public bool Read(JsonElement obj, DateTimeOffset? at, DateTimeOffset cutoff)
    {
        string type = obj.Get("type").Text();
        var p = obj.Get("payload");
        string kind = p.Get("type").Text();
        if (type == "session_meta")
        {
            session = p.Get("session_id").Text();
            if (session.Length == 0) session = p.Get("id").Text();
            return true;
        }
        if (type == "turn_context" || type == "event_msg" && kind == "task_started")
        {
            var id = p.Get("turn_id").Text();
            if (id.Length > 0) turn = id;
            if (type == "turn_context") SetModel(p.Get("model").Text());
            return true;
        }
        if (type == "event_msg" && kind == "thread_settings_applied")
        {
            SetModel(p.Get("thread_settings").Get("model").Text());
            return true;
        }
        if (at is not { } time) return true;
        if (type == "token_usage_record")
        {
            var response = p.Get("response_id").Text();
            if (response.Length == 0 || Counts.Parse(p.Get("usage")) is not { } usage) return false;
            string activeTurn = p.Get("turn_id").Text();
            if (activeTurn.Length == 0) activeTurn = turn;
            string owner = p.Get("session_id").Text();
            if (owner.Length == 0) owner = session;
            string key = "codex:response:" + Digest(owner + ":" + response);
            Counts? total = Counts.Parse(p.Get("thread_token_usage"));
            var paired = Pair(activeTurn, usage, total, true);
            string usedModel = p.Get("model").Text();
            if (usedModel.Length == 0) usedModel = models.GetValueOrDefault(activeTurn, model);
            Store(key, time, usedModel, usage, cutoff, paired);
            if (paired is not null) { paired.Paired = true; paired.Response = true; paired.Key = key; }
            else if (!recent.Any(x => x.Key == key)) Remember(new(key, activeTurn, usage, total, true));
            return true;
        }
        if (type != "event_msg" || kind != "token_count") return true;
        var info = p.Get("info");
        if (info.ValueKind != JsonValueKind.Object) return true; // Quota-only event.
        Counts? cumulative = Counts.Parse(info.Get("total_token_usage"));
        var last = info.Get("last_token_usage");
        Counts? amount = Counts.Parse(last);
        if (amount is null && last.ValueKind == JsonValueKind.Object) return false;
        if (amount is null && cumulative is { } sum)
            amount = checkpoint is { } old && sum.Covers(old) ? sum.Minus(old) : sum;
        if (amount is null) return false;
        var match = Pair(turn, amount.Value, cumulative, false);
        bool repeated = cumulative is not null && cumulative == checkpoint;
        checkpoint = cumulative ?? checkpoint;
        if (match is not null) { match.Paired = true; return true; }
        if (repeated || amount.Value.Total == 0) return true;
        string legacyKey = "codex:legacy:" + Digest($"{time:O}:{cumulative}:{amount}");
        Store(legacyKey, time, model, amount.Value, cutoff, null);
        Remember(new(legacyKey, turn, amount.Value, cumulative, false));
        return true;
    }
}
