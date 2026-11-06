using Dashboard.Components;
using Dashboard.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents(o => o.DetailedErrors = builder.Environment.IsDevelopment());
builder.Services.AddScoped<AppState>();
// Result files can be large (100,000 games is ~40 MB): allow big SignalR messages for uploads.
builder.Services.AddSignalR(o => o.MaximumReceiveMessageSize = 64 * 1024 * 1024);

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
}

app.UseStaticFiles();
app.UseAntiforgery();

app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
