// Read-only reset-card metadata. No card consumption or account mutation.
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using BrimDeck.Core;

internal sealed record ResetCreditReading(int? Available, string[] Expiries, string Status, DateTimeOffset? UpdatedAt = null);

internal static class CodexResetCredits
{
    const string Origin = "https://chatgpt.com/backend-api/wham/";
    const int MaxBody = 256 * 1024;
    internal static ResetCreditReading Missing(string status = "unavailable") => new(null, [], status);

    internal static ResetCreditReading? Parse(JsonElement root)
    {
        if (root.ValueKind != JsonValueKind.Object) return null;
        if (root.TryGetProperty("rate_limit_reset_credits", out var embedded)) root = embedded;
        var count = root.Get("available_count").Number();
        if (count is null || !double.IsFinite(count.Value) || count < 0 || count > 100_000) return null;
        var expiries = root.Get("credits").Items()
            .Where(c => c.Get("status").Text() is "" or "available")
            .Select(c => c.Get("expires_at").Date())
            .Where(d => d.HasValue).Select(d => d!.Value).Order()
            .Take(128).Select(d => d.ToUniversalTime().ToString("O")).ToArray();
        return new((int)Math.Floor(count.Value), expiries, "ok", DateTimeOffset.UtcNow);
    }

    internal static async Task<(ResetCreditReading Credits, string Plan)> ReadAsync(CancellationToken cancellation, bool readPlan)
    {
        ResetCreditReading? credits = null;
        var plan = "";
        try
        {
            var path = Path.Combine(DataLocations.Detect().CodexHome, "auth.json");
            if (!File.Exists(path) || new FileInfo(path).Length > 1024 * 1024) return (Missing("signin"), plan);
            using var auth = JsonDocument.Parse(await File.ReadAllTextAsync(path, cancellation));
            var tokens = auth.RootElement.Get("tokens");
            var token = tokens.Get("access_token").Text();
            if (token.Length == 0) return (Missing("signin"), plan);
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            timeout.CancelAfter(TimeSpan.FromSeconds(8));
            using var handler = new HttpClientHandler { AllowAutoRedirect = false };
            using var client = new HttpClient(handler);
            foreach (var endpoint in new[] { "rate-limit-reset-credits", "usage" })
            {
                using var request = new HttpRequestMessage(HttpMethod.Get, Origin + endpoint);
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
                request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
                var account = tokens.Get("account_id").Text();
                if (account.Length > 0) request.Headers.TryAddWithoutValidation("ChatGPT-Account-Id", account);
                using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, timeout.Token);
                if (response.StatusCode == HttpStatusCode.Unauthorized) return (credits ?? Missing("signin"), plan);
                if (!response.IsSuccessStatusCode) continue;
                if (response.Content.Headers.ContentLength > MaxBody) continue;
                await using var body = await response.Content.ReadAsStreamAsync(timeout.Token);
                using var data = new MemoryStream();var buffer = new byte[8192];
                int read;
                while ((read = await body.ReadAsync(buffer, timeout.Token)) > 0)
                {
                    if (data.Length + read > MaxBody) throw new InvalidDataException();
                    data.Write(buffer, 0, read);
                }
                using var doc = JsonDocument.Parse(data.ToArray());
                // The account can report a plan even when it has no quota window or reset cards.
                if (readPlan && endpoint == "usage") plan = doc.RootElement.Get("plan_type").Text();
                credits ??= Parse(doc.RootElement);
                if (credits is not null && (!readPlan || plan.Length > 0)) return (credits, plan);
            }
            return (credits ?? Missing("not_provided"), plan);
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { throw; }
        catch (Exception) { return (credits ?? Missing(), plan); }
    }

    internal static void SelfTest()
    {
        using var data = JsonDocument.Parse("""{"available_count":2,"credits":[{"expires_at":"2026-12-02T01:00:00Z"},{"status":"available","expires_at":1796086800},{"status":"consumed","expires_at":"2026-12-01T01:00:00Z"}]}""");
        var result = Parse(data.RootElement);
        if (result?.Available != 2 || result.Expiries.Length != 2 || string.CompareOrdinal(result.Expiries[0], result.Expiries[1]) > 0) throw new Exception("reset credits parsing");
        foreach (var sample in new[] { "{}", "null", "{\"available_count\":-1}", "{\"available_count\":\"NaN\"}" })
        { using var invalid = JsonDocument.Parse(sample);if (Parse(invalid.RootElement) is not null) throw new Exception("unknown reset credits must not be zero"); }
        using var zero = JsonDocument.Parse("""{"rate_limit_reset_credits":{"available_count":0}}""");
        if (Parse(zero.RootElement)?.Available != 0) throw new Exception("zero reset credits");
    }
}
