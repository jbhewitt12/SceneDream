import { Flex } from "@chakra-ui/react"
import { Outlet, createFileRoute } from "@tanstack/react-router"

import Navbar from "@/components/Common/Navbar"

export const Route = createFileRoute("/_layout")({
  component: Layout,
})

function Layout() {
  return (
    <Flex
      direction="column"
      h="100vh"
      bgGradient="linear(to-b, #0a0f14, #0b1820, #0a0f14)"
    >
      <Navbar />
      <Flex flex="1" direction="column" p={4} overflowY="auto">
        <Outlet />
      </Flex>
    </Flex>
  )
}

export default Layout
