import { Box, Flex, IconButton } from "@chakra-ui/react"
import { useState } from "react"
import { FaBars } from "react-icons/fa"
import {
  DrawerBackdrop,
  DrawerBody,
  DrawerCloseTrigger,
  DrawerContent,
  DrawerRoot,
  DrawerTrigger,
} from "../ui/drawer"
import SidebarItems from "./SidebarItems"

const Sidebar = () => {
  const [open, setOpen] = useState(false)

  return (
    <>
      {/* Mobile */}
      <DrawerRoot
        placement="start"
        open={open}
        onOpenChange={(e) => setOpen(e.open)}
      >
        <DrawerBackdrop />
        <DrawerTrigger asChild>
          <IconButton
            variant="ghost"
            color="inherit"
            display={{ base: "flex", md: "none" }}
            aria-label="Open Menu"
            position="absolute"
            zIndex="100"
            m={4}
          >
            <FaBars />
          </IconButton>
        </DrawerTrigger>
        <DrawerContent maxW="280px">
          <DrawerCloseTrigger />
          <DrawerBody>
            <Flex flexDir="column" justify="space-between">
              <Box>
                <SidebarItems />
              </Box>
            </Flex>
          </DrawerBody>
          <DrawerCloseTrigger />
        </DrawerContent>
      </DrawerRoot>

      {/* Desktop */}

      <Box
        display={{ base: "none", md: "flex" }}
        position="sticky"
        bg="bg.subtle"
        top={0}
        minW="280px"
        h="100vh"
        p={4}
      >
        <Box w="100%">
          <SidebarItems />
        </Box>
      </Box>
    </>
  )
}

export default Sidebar
