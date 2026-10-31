/**
 * SmartRedes — Configuración de Plugin Pinokio
 *
 * Menú dinámico según estado del plugin:
 *   - No instalado: botón de instalación
 *   - Instalado y corriendo: estado activo + botón abrir UI + detener
 *   - Instalado y detenido: botón iniciar
 *
 * Nota: La URL del servidor se almacena en memoria via local.set
 * en start.json (patrón oficial de Pinokio para daemon scripts).
 * Se accede via kernel.memory.local para el botón "Abrir UI".
 */
module.exports = {
  title: "SmartRedes",
  description: "Plataforma de ADN de marca y campañas digitales con IA local para PYMEs — Cámara Colombiana de Comercio Electrónico (CCCE)",
  icon: "icon.png",

  menu: async (kernel, info) => {
    // Verificar si el plugin está instalado (venv creado)
    var installed = await kernel.exists(__dirname, "venv")

    if (!installed) {
      return [
        {
          default: true,
          icon: "fa-solid fa-download",
          text: "Instalar",
          href: "install.json",
        },
      ]
    }

    // Verificar si el servidor está corriendo
    var running = await kernel.script.running(__dirname, "start.json")

    if (running) {
      return [
        {
          icon: "fa-solid fa-circle",
          text: "En ejecución",
          href: "start.json",
          style: "color: #3DAE2B",
        },
        {
          icon: "fa-solid fa-arrow-up-right-from-square",
          text: "Abrir UI",
          href: "start.json",
        },
        {
          icon: "fa-solid fa-stop",
          text: "Detener",
          href: "stop.json",
        },
      ]
    }

    return [
      {
        default: true,
        icon: "fa-solid fa-play",
        text: "Iniciar",
        href: "start.json",
      },
      {
        icon: "fa-solid fa-trash",
        text: "Desinstalar",
        href: "reset.json",
      },
    ]
  },
}
