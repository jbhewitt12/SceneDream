import { Box, Flex, Icon, Text } from "@chakra-ui/react"
import { Link as RouterLink } from "@tanstack/react-router"
import { FiBriefcase, FiFilm, FiImage, FiTrendingUp } from "react-icons/fi"
import type { IconType } from "react-icons/lib"

interface SidebarItemsProps {
  onClose?: () => void
}

const items: Array<{ icon: IconType; title: string; path: string }> = [
  { icon: FiFilm, title: "Extracted Scenes", path: "/extracted-scenes" },
  { icon: FiTrendingUp, title: "Scene Rankings", path: "/scene-rankings" },
  { icon: FiFilm, title: "Prompt Gallery", path: "/prompt-gallery" },
  { icon: FiImage, title: "Generated Images", path: "/generated-images" },
]

const SidebarItems = ({ onClose }: SidebarItemsProps) => {
  const listItems = items.map(({ icon, title, path }) => (
    <RouterLink key={title} to={path} onClick={onClose}>
      <Flex
        gap={4}
        px={4}
        py={2}
        _hover={{
          background: "gray.subtle",
        }}
        alignItems="center"
        fontSize="sm"
      >
        <Icon as={icon} alignSelf="center" />
        <Text ml={2}>{title}</Text>
      </Flex>
    </RouterLink>
  ))

  return (
    <>
      <Text fontSize="xs" px={4} py={2} fontWeight="bold">
        Menu
      </Text>
      <Box>{listItems}</Box>
    </>
  )
}

export default SidebarItems
