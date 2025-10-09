import { defineRecipe } from "@chakra-ui/react"

export const buttonRecipe = defineRecipe({
  base: {
    fontWeight: "bold",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    colorPalette: "cyan",
  },
  variants: {
    variant: {
      ghost: {
        bg: "transparent",
        _hover: {
          bg: { base: "whiteAlpha.100", _dark: "whiteAlpha.100" },
        },
        _active: { bg: { base: "whiteAlpha.200", _dark: "whiteAlpha.200" } },
      },
    },
  },
})
