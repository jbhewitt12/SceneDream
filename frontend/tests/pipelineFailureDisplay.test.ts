import assert from "node:assert/strict"
import test from "node:test"
import { ChakraProvider } from "@chakra-ui/react"
import React from "react"
import { renderToStaticMarkup } from "react-dom/server"

import {
  PipelineFailureNotice,
  getPipelineFailureDisplay,
} from "../src/features/documents/pipelineFailureDisplay"
import { system } from "../src/theme"

test("structured remediation renders message, hint, and action items", () => {
  const failure = getPipelineFailureDisplay(
    {
      error: {
        message: "OpenAI rejected the configured API key for extraction.",
        metadata: {
          category: "authentication",
          hint: "Replace OPENAI_API_KEY with a valid key and restart the backend.",
          action_items: [
            "Check that the configured API key is valid and active.",
            "Update the key in `.env` if needed.",
            "Restart the backend and rerun the pipeline.",
          ],
        },
      },
      error_message: "legacy fallback",
      usage_summary: {},
    },
    ["Secondary provider detail"],
  )

  assert.ok(failure)

  const markup = renderToStaticMarkup(
    React.createElement(
      ChakraProvider,
      { value: system },
      React.createElement(PipelineFailureNotice, {
        failure,
      }),
    ),
  )

  assert.match(
    markup,
    /OpenAI rejected the configured API key for extraction\./,
  )
  assert.match(
    markup,
    /Replace OPENAI_API_KEY with a valid key and restart the backend\./,
  )
  assert.match(markup, /Update the key in `\.env` if needed\./)
  assert.match(markup, /Secondary provider detail/)
})

test("legacy failures still render cleanly without structured remediation", () => {
  const failure = getPipelineFailureDisplay({
    error: null,
    error_message: "Pipeline run failed.",
    usage_summary: {},
  })

  assert.deepEqual(failure, {
    message: "Pipeline run failed.",
    hint: null,
    actionItems: [],
    secondaryMessages: [],
  })
})
