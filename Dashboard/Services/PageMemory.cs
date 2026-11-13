namespace Dashboard.Services;

/// <summary>
/// Per-browser-session memory for the pages: a page saves a snapshot of its state when the user navigates away (in <c>Dispose</c>)
/// and restores it when the page is opened again, so switching pages neither loses the user's input nor re-reads the files.
/// The snapshots hold references to the loaded data (no copies); a new session (browser tab) starts empty.
/// </summary>
public sealed class PageMemory
{
    private readonly Dictionary<string, object> _items = new();

    public T? Get<T>(string key) where T : class => _items.TryGetValue(key, out var v) ? v as T : null;

    public void Set(string key, object snapshot) => _items[key] = snapshot;

    public void Forget(string key) => _items.Remove(key);
}
