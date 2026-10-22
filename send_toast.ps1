param(
    [string]$Title = "ScreenStash Saved",
    [string]$Message = "AI is organizing your screenshot..."
)

try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName("text")
    $textNodes.Item(0).AppendChild($template.CreateTextNode($Title)) | Out-Null
    $textNodes.Item(1).AppendChild($template.CreateTextNode($Message)) | Out-Null
    
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    $appId = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId)
    $notifier.Show($toast)
} catch {
    # Ignore errors quietly
}
