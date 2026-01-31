import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/")({
  component: () => null,
  beforeLoad: () => {
    throw redirect({ to: "/generated-images" })
  },
})
