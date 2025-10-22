import Logo from "@/components/Common/Logo"
import { Button, Flex, HStack } from "@chakra-ui/react"
import { Link } from "@tanstack/react-router"

function Navbar() {
  return (
    <Flex
      justify="center"
      position="sticky"
      align="center"
      bg="rgba(10, 18, 26, 0.6)"
      backdropFilter="saturate(140%) blur(10px)"
      borderBottomWidth="1px"
      w="100%"
      top={0}
      px={4}
      py={3}
    >
      <Flex position="absolute" left={4}>
        <Logo size="sm" />
      </Flex>
      <HStack gap={1} alignItems="center">
        <Link to="/extracted-scenes">
          <Button size="sm" variant="ghost" className="main-link">
            Extracted Scenes
          </Button>
        </Link>
        <Link to="/scene-rankings">
          <Button size="sm" variant="ghost" className="main-link">
            Scene Rankings
          </Button>
        </Link>
        <Link to="/prompt-gallery">
          <Button size="sm" variant="ghost" className="main-link">
            Prompt Gallery
          </Button>
        </Link>
        <Link to="/generated-images">
          <Button size="sm" variant="ghost" className="main-link">
            Generated Images
          </Button>
        </Link>
      </HStack>
    </Flex>
  )
}

export default Navbar
