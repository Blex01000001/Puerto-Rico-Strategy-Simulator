using Dashboard.Components;
using Dashboard.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents(o => o.DetailedErrors = builder.Environment.IsDevelopment());
builder.Services.AddScoped<AppState>();
builder.Services.AddScoped<SimulationService>();
builder.Services.AddScoped<PageMemory>();
builder.Services.AddScoped<Loc>();
// Result files can be large (100,000 games is ~40 MB): allow big SignalR messages for uploads.
builder.Services.AddSignalR(o => o.MaximumReceiveMessageSize = 64 * 1024 * 1024);

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
}

app.UseStaticFiles();
app.UseAntiforgery();

// Language switch: sets the cookie the page reads (App.razor) and goes back to the page the button was on.
app.MapGet("/lang/{code}", (string code, string? returnUrl, HttpContext http) =>
{
    if (Loc.Languages.Contains(code))
        http.Response.Cookies.Append(Loc.Cookie, code, new CookieOptions { Path = "/", MaxAge = TimeSpan.FromDays(365), SameSite = SameSiteMode.Lax });
    bool local = !string.IsNullOrEmpty(returnUrl) && returnUrl.StartsWith('/') && !returnUrl.StartsWith("//") && !returnUrl.StartsWith("/\\");
    return Results.Redirect(local ? returnUrl! : "/");
});

app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
