import { createSystem, defaultConfig } from "@chakra-ui/react"
import { buttonRecipe } from "./theme/button.recipe"

export const system = createSystem(defaultConfig, {
  globalCss: {
    html: {
      fontSize: "16px",
    },
    body: {
      fontSize: "0.875rem",
      margin: 0,
      padding: 0,
      background:
        "linear-gradient(180deg, #0a0f14 0%, #0b1820 40%, #0a0f14 100%)",
      color: "var(--chakra-colors-fg-default)",
    },
    ".main-link": {
      color: "ui.main",
      fontWeight: "bold",
    },
    "::selection": {
      backgroundColor: "#00e5ff33",
    },

    // Improve readability in dark mode by slightly lightening text tokens
    ".dark": {
      "--chakra-colors-fg-default": "#e6edf3",
      "--chakra-colors-fg-muted": "#a9b8c2",
      "--chakra-colors-fg-subtle": "#93a6b1",
    },
  },
  theme: {
    tokens: {
      colors: {
        ui: {
          // Neon cyan accent
          main: { value: "#00e5ff" },
        },
      },
    },
    recipes: {
      button: buttonRecipe,
    },
  },
})
