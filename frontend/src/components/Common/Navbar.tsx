import { Button, Flex, HStack } from "@chakra-ui/react"
import { Link } from "@tanstack/react-router"
import Logo from "@/components/Common/Logo"

function Navbar() {
  return (
    <Flex
      justify="center"
      position="sticky"
      align="center"
      bg="white"
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
          <Button size="sm" variant="ghost">Extracted Scenes</Button>
        </Link>
        <Link to="/scene-rankings">
          <Button size="sm" variant="ghost">Scene Rankings</Button>
        </Link>
        <Link to="/prompt-gallery">
          <Button size="sm" variant="ghost">Prompt Gallery</Button>
        </Link>
      </HStack>
    </Flex>
  )
}

export default Navbar
