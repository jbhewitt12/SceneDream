import { Button, Flex, HStack, Text } from "@chakra-ui/react"
import { Link } from "@tanstack/react-router"

function Navbar() {
  return (
    <Flex
      justify="center"
      position="sticky"
      color="white"
      align="center"
      bg="bg.muted"
      w="100%"
      top={0}
      p={4}
    >
      <Link to="/extracted-scenes" style={{ position: "absolute", left: 16 }}>
        <Text fontWeight="bold">SceneDream</Text>
      </Link>
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
