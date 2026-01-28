---
description: /issue-doc command
argument-hint: "[issue-number]"
disable-model-invocation: true
---

# /issue-doc command

You are tasked with updating an existing issue file in the `/issues` folder with a well-researched implementation plan.

## Instructions

1. **Find the issue file**: The user will provide an issue number (e.g., "001"). Locate the corresponding file in `/issues/` (e.g., `/issues/001-*.md`)

2. **Read the user's description**: The issue file contains the user's original description of what they want implemented. Read and understand their requirements.

3. **Follow the issue guidelines**: Use the same structure and guidelines from `.claude/commands/issue.md` to create the implementation plan, but:
   - **PRESERVE** the user's original description at the top
   - Add a separator (`---`) after their description
   - Append the implementation plan below

4. **Conduct a technical interview**: Before writing the implementation plan, interview the user in depth using the AskUserQuestion tool. This interview should continue until you have complete clarity.

   ### Interview Guidelines:
   - Ask about **technical implementation details**: architecture choices, data flow, state management, API design
   - Ask about **UI & UX considerations**: user interactions, edge cases, error states, loading states
   - Ask about **concerns and constraints**: performance requirements, security considerations, backwards compatibility
   - Ask about **tradeoffs**: where should we prioritize simplicity vs flexibility, speed vs correctness
   - **Avoid obvious questions** - use your codebase research to ask informed, specific questions
   - Continue asking follow-up questions until you have clarity on all ambiguous aspects

   ### Example Interview Topics:
   - "Based on the existing service pattern in X, should this new feature follow the same approach or would Y be more appropriate given Z?"
   - "I noticed the codebase uses pattern A for similar features. Are there any reasons to deviate from this?"
   - "What should happen when [edge case] occurs?"
   - "How important is [specific tradeoff] for this feature?"

   Do not proceed to writing the implementation plan until the interview is complete.

5. **Key difference from /issue command**:
   - `/issue`: Creates a new issue file from scratch based on user's prompt
   - `/issue-doc`: Updates an existing issue file that already contains the user's requirements

Now, please find and update the issue file numbered: $ARGUMENTS
