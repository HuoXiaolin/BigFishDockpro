using System.Text.Json;
using System.Security.Cryptography;
using System.Text;
using BrimDeck.Core;

var reader = new LogReader();
var now = DateTimeOffset.Parse(args[1]);
foreach (var id in args[2].Split(',').Select(Enum.Parse<ProviderId>))
{
    var first = reader.Read(id, args[0], now, new DateTime(2000, 1, 1));
    var again = reader.Read(id, args[0], now, new DateTime(2000, 1, 1));
    // Compare accounting fields without printing conversation, model or account data.
    var fields = first.Entries.Select(e => new { e.Time, e.Model, e.Input, e.Output, e.CacheRead, e.CacheWrite, e.CacheWriteHour, e.ReportedCostUsd }).Select(e => JsonSerializer.Serialize(e)).Order().ToArray();
    Console.WriteLine(JsonSerializer.Serialize(new { provider = id.ToString(), records = fields.Length, tokens = first.Entries.Sum(e => e.Total), complete = first.UsageComplete,
        note = first.UsageNote, digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("\n", fields)))), repeat = again.Entries.Count == first.Entries.Count,
        quotas = first.Quotas.Count }));
}
