// BigFishDockpro, 2026. Project accounting metadata before parsing a JSON DOM.
// Conversation/tool/image values are skipped in a fixed buffer, never retained.
using System.Buffers;
using System.Text.Json;

namespace BrimDeck.Core;

internal sealed class AccountingJsonLines(Stream stream, int limit)
{
    readonly byte[] buffer = new byte[32 * 1024];
    int cursor, count;
    public long Position { get; private set; } = stream.Position;
    static readonly HashSet<string> Containers = new(StringComparer.Ordinal)
    { "payload", "message", "usage", "info", "rate_limits", "primary", "secondary", "total_token_usage", "last_token_usage", "cache_creation", "cost" };
    static readonly HashSet<string> Scalars = new(StringComparer.Ordinal)
    {
        "timestamp", "type", "id", "uuid", "role", "stopReason", "model", "provider", "limit_id", "plan_type",
        "used_percent", "window_minutes", "resets_at", "reset_after_seconds",
        "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens",
        "cache_read_input_tokens", "cache_creation_input_tokens", "cache_write_input_tokens", "ephemeral_1h_input_tokens",
        "input", "output", "cacheRead", "cacheWrite", "cacheWrite1h", "total"
    };
    static bool Keep(string parent, string name) => parent switch
    {
        "" => name is "timestamp" or "type" or "id" or "uuid" or "message" or "payload" or "model" or "provider" or "usage",
        "payload" => name is "type" or "model" or "info" or "rate_limits",
        "message" => name is "role" or "stopReason" or "timestamp" or "usage" or "model" or "provider" or "id",
        "info" => name is "total_token_usage" or "last_token_usage",
        "rate_limits" => name is "limit_id" or "plan_type" or "primary" or "secondary",
        _ => true
    };
    int Peek()
    {
        if (cursor == count) { count = stream.Read(buffer); cursor = 0; }
        return cursor == count ? -1 : buffer[cursor];
    }
    int Pop() { int value = Peek(); if (value >= 0) { cursor++; Position++; } return value; }
    void Spaces() { while (Peek() is 9 or 13 or 32) Pop(); }
    void Expect(int value) { if (Peek() != value) throw new JsonException(); Pop(); }

    byte[] ReadString(int maximum)
    {
        var bytes = new ArrayBufferWriter<byte>(128); Expect('"'); bytes.Write("\""u8);
        bool escaped = false;
        while (true)
        {
            int value = Peek(); if (value < 0 || value == '\n') throw new JsonException();
            Pop(); bytes.GetSpan(1)[0] = (byte)value; bytes.Advance(1);
            if (bytes.WrittenCount > maximum) throw new JsonException();
            if (!escaped && value == '"') return bytes.WrittenSpan.ToArray();
            escaped = !escaped && value == '\\';
        }
    }
    void SkipString()
    {
        Expect('"');
        while (true)
        {
            if (Peek() < 0) throw new JsonException();
            int n = buffer.AsSpan(cursor, count - cursor).IndexOfAny((byte)'"', (byte)'\\', (byte)'\n');
            if (n < 0) { Position += count - cursor; cursor = count; continue; }
            cursor += n; Position += n;
            if (Peek() == '\n') throw new JsonException();
            if (Pop() == '"') return;
            if (Peek() < 0 || Peek() == '\n') throw new JsonException();
            Pop(); // An escaped quote is part of the discarded value.
        }
    }
    void SkipValue()
    {
        Spaces(); int opening = Peek();
        if (opening == '"') { SkipString(); return; }
        int depth = 0;
        while (true)
        {
            int value = Peek();
            if (value < 0 || value == '\n') { if (depth > 0) throw new JsonException(); return; }
            if (depth == 0 && value is ',' or '}' or ']') return;
            if (value == '"') { SkipString(); continue; }
            Pop();
            if (value is '{' or '[') depth++;
            if (value is '}' or ']') { if (--depth == 0) return; }
        }
    }
    void Object(Utf8JsonWriter writer, ArrayBufferWriter<byte> output, int depth, string parent = "")
    {
        if (depth > 12) throw new JsonException();
        Expect('{'); writer.WriteStartObject(); Spaces();
        while (Peek() != '}')
        {
            string name = JsonSerializer.Deserialize<string>(ReadString(512))!;
            Spaces(); Expect(':'); Spaces();
            if (Keep(parent, name) && Containers.Contains(name) && Peek() == '{')
            { writer.WritePropertyName(name); Object(writer, output, depth + 1, name); }
            else if (Keep(parent, name) && Scalars.Contains(name) && Peek() is not ('{' or '['))
            {
                byte[] value;
                if (Peek() == '"') value = ReadString(4096);
                else
                {
                    var token = new ArrayBufferWriter<byte>(32);
                    while (Peek() >= 0 && Peek() is not (',' or '}' or '\n' or '\r'))
                    {
                        token.GetSpan(1)[0] = (byte)Pop(); token.Advance(1);
                        if (token.WrittenCount > 128) throw new JsonException();
                    }
                    value = token.WrittenSpan.ToArray();
                }
                writer.WritePropertyName(name); writer.WriteRawValue(value);
            }
            else SkipValue();
            writer.Flush(); if (output.WrittenCount > limit) throw new JsonException();
            Spaces(); if (Peek() == '}') break;
            Expect(','); Spaces();
        }
        Expect('}'); writer.WriteEndObject();
    }
    // Incomplete last lines are not committed: the append reader retries them.
    public bool Next(out byte[]? json, out bool invalid)
    {
        json = null; invalid = false; Spaces(); if (Peek() < 0) return false;
        var output = new ArrayBufferWriter<byte>(1024);
        try
        {
            using var writer = new Utf8JsonWriter(output);
            if (Position == 0 && Peek() == 0xef) { Expect(0xef); Expect(0xbb); Expect(0xbf); }
            Object(writer, output, 0); writer.Flush(); Spaces();
            if (Peek() != '\n') throw new JsonException();
            json = output.WrittenSpan.ToArray();
        }
        catch (JsonException) { invalid = true; }
        while (Peek() >= 0 && Peek() != '\n') Pop();
        if (Peek() < 0) return false;
        Pop(); return true;
    }
}
