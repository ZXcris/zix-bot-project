# Guarda XKIRO_API_KEY como variable de usuario de Windows.
# La key se escribe oculta (no se muestra en pantalla) y NO queda en ningún
# archivo del proyecto (.env queda intacto). ZIX y OpenCode la leen al arrancar.
# Uso: clic derecho -> "Ejecutar con PowerShell", o desde la carpeta del proyecto:
#   powershell -ExecutionPolicy Bypass -File scripts\set_xkiro_key.ps1
$secure = Read-Host "Pega tu XKIRO_API_KEY (no se vera en pantalla)" -AsSecureString
$plain = [System.Net.NetworkCredential]::new("", $secure).Password
if ([string]::IsNullOrWhiteSpace($plain)) {
    Write-Output "Vacia, no se guardo nada."
    exit 1
}
[System.Environment]::SetEnvironmentVariable("XKIRO_API_KEY", $plain.Trim(), "User")
Write-Output "Guardada en tu usuario de Windows."
Write-Output "Cierra y reabre las terminales para que aplique, y avisa con 'listo'."
