import { Flex, Heading, Icon, Text } from "@chakra-ui/react"
import { Link } from "@tanstack/react-router"
import { FiAperture } from "react-icons/fi"

interface LogoProps {
  size?: "sm" | "md" | "lg"
}

function Logo({ size = "md" }: LogoProps) {
  const sizeMap = {
    sm: { icon: 4, text: "md" as const },
    md: { icon: 5, text: "lg" as const },
    lg: { icon: 6, text: "xl" as const },
  }

  const s = sizeMap[size]

  return (
    <Link to="/extracted-scenes" aria-label="SceneDream Home">
      <Flex align="center" gap={2}
        _hover={{ opacity: 0.95 }}
      >
        <Flex
          align="center"
          justify="center"
          w={8}
          h={8}
          rounded="md"
          bgGradient="to-br" gradientFrom="#00e5ff" gradientTo="#7f5af0"
          overflow="hidden"
          boxShadow="0 0 24px 2px #00e5ff33"
        >
          <Icon as={FiAperture} boxSize={s.icon} color="white" />
        </Flex>
        <Heading
          size={s.text}
          bgGradient="to-r"
          gradientFrom="#00e5ff"
          gradientTo="#7f5af0"
          bgClip="text"
        >
          SceneDream
        </Heading>
      </Flex>
    </Link>
  )
}

export default Logo


