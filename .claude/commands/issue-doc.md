# /issue-doc command

You are tasked with updating an existing issue file in the `/issues` folder with a well-researched implementation plan.

## Instructions

1. **Find the issue file**: The user will provide an issue number (e.g., "001"). Locate the corresponding file in `/issues/` (e.g., `/issues/001-*.md`)

2. **Read the user's description**: The issue file contains the user's original description of what they want implemented. Read and understand their requirements.

3. **Follow the issue guidelines**: Use the same structure and guidelines from `.claude/commands/issue.md` to create the implementation plan, but:
   - **PRESERVE** the user's original description at the top
   - Add a separator (`---`) after their description
   - Append the implementation plan below

4. **Key difference from /issue command**: 
   - `/issue`: Creates a new issue file from scratch based on user's prompt
   - `/issue-doc`: Updates an existing issue file that already contains the user's requirements

Now, please find and update the issue file numbered: {issue_number}